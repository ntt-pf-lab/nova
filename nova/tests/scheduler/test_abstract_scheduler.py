# Copyright 2011 OpenStack LLC.
# All Rights Reserved.
# Copyright 2011 NTT
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
"""
Tests For Abstract Scheduler.
"""

import json

import nova.db

from nova import exception
from nova import rpc
from nova import test
from nova.compute import api as compute_api
from nova.scheduler import driver
from nova.scheduler import abstract_scheduler
from nova.scheduler import base_scheduler
from nova.scheduler import zone_manager

from nova import db
from nova.scheduler import api

from nose.plugins.attrib import attr
import stubout
import M2Crypto
from novaclient import v1_1 as novaclient
from novaclient.v1_1 import servers
from novaclient import exceptions as novaclient_exceptions
from nova.db import base
from nova import context


def _host_caps(multiplier):
    # Returns host capabilities in the following way:
    # host1 = memory:free 10 (100max)
    #         disk:available 100 (1000max)
    # hostN = memory:free 10 + 10N
    #         disk:available 100 + 100N
    # in other words: hostN has more resources than host0
    # which means ... don't go above 10 hosts.
    return {'host_name-description': 'XenServer %s' % multiplier,
            'host_hostname': 'xs-%s' % multiplier,
            'host_memory_total': 100,
            'host_memory_overhead': 10,
            'host_memory_free': 10 + multiplier * 10,
            'host_memory_free-computed': 10 + multiplier * 10,
            'host_other-config': {},
            'host_ip_address': '192.168.1.%d' % (100 + multiplier),
            'host_cpu_info': {},
            'disk_available': 100 + multiplier * 100,
            'disk_total': 1000,
            'disk_used': 0,
            'host_uuid': 'xxx-%d' % multiplier,
            'host_name-label': 'xs-%s' % multiplier}


def fake_zone_manager_service_states(num_hosts):
    states = {}
    for x in xrange(num_hosts):
        states['host%02d' % (x + 1)] = {'compute': _host_caps(x)}
    return states


class FakeAbstractScheduler(abstract_scheduler.AbstractScheduler):
    # No need to stub anything at the moment
    pass


class FakeBaseScheduler(base_scheduler.BaseScheduler):
    # No need to stub anything at the moment
    pass


class FakeZoneManager(zone_manager.ZoneManager):
    def __init__(self):
        self.service_states = {
            'host1': {
                'compute': {'host_memory_free': 1073741824},
            },
            'host2': {
                'compute': {'host_memory_free': 2147483648},
            },
            'host3': {
                'compute': {'host_memory_free': 3221225472},
            },
            'host4': {
                'compute': {'host_memory_free': 999999999},
            },
        }


class FakeEmptyZoneManager(zone_manager.ZoneManager):
    def __init__(self):
        self.service_states = {}


def fake_empty_call_zone_method(context, method, specs, zones):
    return []


# Hmm, I should probably be using mox for this.
was_called = False


def fake_provision_resource(context, item, instance_id, request_spec, kwargs):
    global was_called
    was_called = True


def fake_ask_child_zone_to_create_instance(context, zone_info,
                                           request_spec, kwargs):
    global was_called
    was_called = True


def fake_provision_resource_locally(context, build_plan, request_spec, kwargs):
    global was_called
    was_called = True


def fake_provision_resource_from_blob(context, item, instance_id,
                                      request_spec, kwargs):
    global was_called
    was_called = True


def fake_decrypt_blob_returns_local_info(blob):
    return {'hostname': 'foooooo'}  # values aren't important.


def fake_decrypt_blob_returns_child_info(blob):
    return {'child_zone': True,
            'child_blob': True}  # values aren't important. Keys are.


def fake_call_zone_method(context, method, specs, zones):
    return [
        (1, [
            dict(weight=1, blob='AAAAAAA'),
            dict(weight=111, blob='BBBBBBB'),
            dict(weight=112, blob='CCCCCCC'),
            dict(weight=113, blob='DDDDDDD'),
        ]),
        (2, [
            dict(weight=120, blob='EEEEEEE'),
            dict(weight=2, blob='FFFFFFF'),
            dict(weight=122, blob='GGGGGGG'),
            dict(weight=123, blob='HHHHHHH'),
        ]),
        (3, [
            dict(weight=130, blob='IIIIIII'),
            dict(weight=131, blob='JJJJJJJ'),
            dict(weight=132, blob='KKKKKKK'),
            dict(weight=3, blob='LLLLLLL'),
        ]),
    ]


def fake_zone_get_all(context):
    return [
        dict(id=1, api_url='zone1',
             username='admin', password='password',
             weight_offset=0.0, weight_scale=1.0),
        dict(id=2, api_url='zone2',
             username='admin', password='password',
             weight_offset=1000.0, weight_scale=1.0),
        dict(id=3, api_url='zone3',
             username='admin', password='password',
             weight_offset=0.0, weight_scale=1000.0),
    ]


class AbstractSchedulerTestCase(test.TestCase):
    """Test case for Abstract Scheduler."""

    def test_abstract_scheduler(self):
        """
        Create a nested set of FakeZones, try to build multiple instances
        and ensure that a select call returns the appropriate build plan.
        """
        sched = FakeAbstractScheduler()
        self.stubs.Set(sched, '_call_zone_method', fake_call_zone_method)
        self.stubs.Set(nova.db, 'zone_get_all', fake_zone_get_all)

        zm = FakeZoneManager()
        sched.set_zone_manager(zm)

        fake_context = {}
        build_plan = sched.select(fake_context,
                {'instance_type': {'memory_mb': 512},
                    'num_instances': 4})

        # 4 from local zones, 12 from remotes
        self.assertEqual(16, len(build_plan))

        hostnames = [plan_item['hostname']
                     for plan_item in build_plan if 'hostname' in plan_item]
        # 4 local hosts
        self.assertEqual(4, len(hostnames))

    def test_adjust_child_weights(self):
        """Make sure the weights returned by child zones are
        properly adjusted based on the scale/offset in the zone
        db entries.
        """
        sched = FakeAbstractScheduler()
        child_results = fake_call_zone_method(None, None, None, None)
        zones = fake_zone_get_all(None)
        sched._adjust_child_weights(child_results, zones)
        scaled = [130000, 131000, 132000, 3000]
        for zone, results in child_results:
            for item in results:
                w = item['weight']
                if zone == 'zone1':  # No change
                    self.assertTrue(w < 1000.0)
                if zone == 'zone2':  # Offset +1000
                    self.assertTrue(w >= 1000.0 and w < 2000)
                if zone == 'zone3':  # Scale x1000
                    self.assertEqual(scaled.pop(0), w)

    def test_empty_abstract_scheduler(self):
        """
        Ensure empty hosts & child_zones result in NoValidHosts exception.
        """
        sched = FakeAbstractScheduler()
        self.stubs.Set(sched, '_call_zone_method', fake_empty_call_zone_method)
        self.stubs.Set(nova.db, 'zone_get_all', fake_zone_get_all)

        zm = FakeEmptyZoneManager()
        sched.set_zone_manager(zm)

        fake_context = {}
        self.assertRaises(driver.NoValidHost, sched.schedule_run_instance,
                          fake_context, 1,
                          dict(host_filter=None, instance_type={}))

    def test_schedule_do_not_schedule_with_hint(self):
        """
        Check the local/child zone routing in the run_instance() call.
        If the zone_blob hint was passed in, don't re-schedule.
        """
        global was_called
        sched = FakeAbstractScheduler()
        was_called = False
        self.stubs.Set(sched, '_provision_resource', fake_provision_resource)
        request_spec = {
                'instance_properties': {},
                'instance_type': {},
                'filter_driver': 'nova.scheduler.host_filter.AllHostsFilter',
                'blob': "Non-None blob data",
            }

        result = sched.schedule_run_instance(None, 1, request_spec)
        self.assertEquals(None, result)
        self.assertTrue(was_called)

    def test_provision_resource_local(self):
        """Provision a resource locally or remotely."""
        global was_called
        sched = FakeAbstractScheduler()
        was_called = False
        self.stubs.Set(sched, '_provision_resource_locally',
                       fake_provision_resource_locally)

        request_spec = {'hostname': "foo"}
        sched._provision_resource(None, request_spec, 1, request_spec, {})
        self.assertTrue(was_called)

    def test_provision_resource_remote(self):
        """Provision a resource locally or remotely."""
        global was_called
        sched = FakeAbstractScheduler()
        was_called = False
        self.stubs.Set(sched, '_provision_resource_from_blob',
                       fake_provision_resource_from_blob)

        request_spec = {}
        sched._provision_resource(None, request_spec, 1, request_spec, {})
        self.assertTrue(was_called)

    def test_provision_resource_from_blob_empty(self):
        """Provision a resource locally or remotely given no hints."""
        global was_called
        sched = FakeAbstractScheduler()
        request_spec = {}
        self.assertRaises(abstract_scheduler.InvalidBlob,
                          sched._provision_resource_from_blob,
                          None, {}, 1, {}, {})

    def test_provision_resource_from_blob_with_local_blob(self):
        """
        Provision a resource locally or remotely when blob hint passed in.
        """
        global was_called
        sched = FakeAbstractScheduler()
        was_called = False

        def fake_create_db_entry_for_new_instance(self, context,
                image, base_options, security_group,
                block_device_mapping, num=1):
            global was_called
            was_called = True
            # return fake instances
            return {'id': 1, 'uuid': 'f874093c-7b17-49c0-89c3-22a5348497f9'}

        def fake_rpc_cast(*args, **kwargs):
            pass

        self.stubs.Set(sched, '_decrypt_blob',
                       fake_decrypt_blob_returns_local_info)
        self.stubs.Set(compute_api.API,
                'create_db_entry_for_new_instance',
                fake_create_db_entry_for_new_instance)
        self.stubs.Set(rpc, 'cast', fake_rpc_cast)

        build_plan_item = {'blob': "Non-None blob data"}
        request_spec = {'image': {}, 'instance_properties': {}}

        sched._provision_resource_from_blob(None, build_plan_item, 1,
                                            request_spec, {})
        self.assertTrue(was_called)

    def test_provision_resource_from_blob_with_child_blob(self):
        """
        Provision a resource locally or remotely when child blob hint
        passed in.
        """
        global was_called
        sched = FakeAbstractScheduler()
        self.stubs.Set(sched, '_decrypt_blob',
                       fake_decrypt_blob_returns_child_info)
        was_called = False
        self.stubs.Set(sched, '_ask_child_zone_to_create_instance',
                       fake_ask_child_zone_to_create_instance)

        request_spec = {'blob': "Non-None blob data"}

        sched._provision_resource_from_blob(None, request_spec, 1,
                                            request_spec, {})
        self.assertTrue(was_called)

    def test_provision_resource_from_blob_with_immediate_child_blob(self):
        """
        Provision a resource locally or remotely when blob hint passed in
        from an immediate child.
        """
        global was_called
        sched = FakeAbstractScheduler()
        was_called = False
        self.stubs.Set(sched, '_ask_child_zone_to_create_instance',
                       fake_ask_child_zone_to_create_instance)

        request_spec = {'child_blob': True, 'child_zone': True}

        sched._provision_resource_from_blob(None, request_spec, 1,
                                            request_spec, {})
        self.assertTrue(was_called)

    def test_decrypt_blob(self):
        """Test that the decrypt method works."""

        fixture = FakeAbstractScheduler()
        test_data = {"foo": "bar"}

        class StubDecryptor(object):
            def decryptor(self, key):
                return lambda blob: blob

        self.stubs.Set(abstract_scheduler, 'crypto',
                       StubDecryptor())

        self.assertEqual(fixture._decrypt_blob(test_data),
                         json.dumps(test_data))

    def test_empty_local_hosts(self):
        """
        Create a nested set of FakeZones, try to build multiple instances
        and ensure that a select call returns the appropriate build plan.
        """
        sched = FakeAbstractScheduler()
        self.stubs.Set(sched, '_call_zone_method', fake_call_zone_method)
        self.stubs.Set(nova.db, 'zone_get_all', fake_zone_get_all)

        zm = FakeZoneManager()
        # patch this to have no local hosts
        zm.service_states = {}
        sched.set_zone_manager(zm)

        fake_context = {}
        build_plan = sched.select(fake_context,
                {'instance_type': {'memory_mb': 512},
                    'num_instances': 4})

        # 0 from local zones, 12 from remotes
        self.assertEqual(12, len(build_plan))

    @attr(kind='small')
    def test_call_zone_method(self):

        class StubCallZoneMethod(object):

            count_ck = 0

            def call_zone_method(self, context, method_name,
                                 errors_to_ignore=None,
                                 novaclient_collection_name='zones',
                                 zones=None, *args, **kwargs):
                self.count_ck += 1
                sc_count = self.count_ck
                return sc_count

        def mock_success(cls, *args):
            self.success_count += 1

        sched = FakeAbstractScheduler()
        self.success_count = 0
        self.stubs.Set(abstract_scheduler, 'api', StubCallZoneMethod())

        self.success_count = sched._call_zone_method(None, None, None, None)
        self.assertEqual(1, self.success_count)

    @attr(kind='small')
    def test_decrypt_blob_exception(self):

        class StubDecryptor(object):
            def decryptor(self, key):
                return lambda blob: blob

        def mock_exception(cls, *args):
            self.exception_count += 1
            raise M2Crypto.EVP.EVPError

        sched = FakeAbstractScheduler()
        test_data = {"foo": "bar"}
        self.exception_count = 0
        self.stubs.Set(abstract_scheduler, 'crypto', StubDecryptor())
        self.stubs.Set(json, 'dumps', mock_exception)

        sched._decrypt_blob(test_data)
        self.assertEqual(1, self.exception_count)

    @attr(kind='small')
    def test_adjust_child_weights_exception(self):

        def fake_zone_get_all(context):
            return [
                dict(id=1, api_url='zone1',
                     username='admin', password='password',
                     weight_offset=0.0, weight_key=1.1)]

        def fake_call_zone_method(context, method, specs, zones):
            return [('a', False),
                    (1, [dict(weight=1, blob='AAAAAAA')])]

        def mock_exception(msg):
            self.exception_count += 1

        self.exception_count = 0
        sched = FakeAbstractScheduler()

        child_results = fake_call_zone_method(None, None, None, None)
        zones = fake_zone_get_all(None)

        self.stubs.Set(abstract_scheduler.LOG, 'exception', mock_exception)

        sched._adjust_child_weights(child_results, zones)
        self.assertEqual(1, self.exception_count)

    @attr(kind='small')
    def test_ask_child_zone_to_create_instance(self):

        def mock_zone_get(context, child_zone):
            return dict(id=1, api_url='http://example.com', username='bob',
                            password='xxx', weight_scale=1.0,
                            weight_offset=0.0)

        def mock_client(self, username, api_key, project_id,
                        auth_url, timeout=None, token=None, region_name=None):

            self.servers = servers.ServerManager(self)
            return None

        def mock_authenticate(*args):
            self.success_count += 1

        def mock_create(self, name, image, flavor, meta=None, files=None,
               zone_blob=None, reservation_id=None, min_count=None,
               max_count=None, security_groups=None, userdata=None,
               key_name=None):
            pass

        class FakeDB(object):

            def __init__(self, name='child'):
                self.id = 1
                self.api_url = 'http://example.com'
                self.username = 'testuser'
                self.password = 'bbb'
                self.name = name

            def zone_get(self, context, child_zone):
                return self

        self.success_count = 0

        request_spec = {'instance_type': dict(flavorid='flav'),
                        'instance_properties': dict(display_name='aaa',
                                                     image_ref='image',
                                                     metadata='metameta',
                                                     reservation_id='bbb')}
        zone_info = {'child_zone': 1, 'child_blob': 2}
        kwargs = {'injected_files': 'aaa'}

        self.stubs.Set(abstract_scheduler,
                       'db',
                       FakeDB())
        self.stubs.Set(novaclient.Client,
                       '__init__',
                       mock_client)
        self.stubs.Set(novaclient.Client,
                       'authenticate',
                       mock_authenticate)
        self.stubs.Set(novaclient.servers.ServerManager,
                       'create',
                       mock_create)

        sched = FakeAbstractScheduler()
        sched._ask_child_zone_to_create_instance(context.get_admin_context(),
                                                 zone_info,
                                                 request_spec, kwargs)
        self.assertEqual(1, self.success_count)

    @attr(kind='small')
    def test_ask_child_zone_to_create_instance_exception(self):

        class FakeDb(object):

            def __init__(self, name='child'):
                self.id = 1
                self.api_url = 'http://example.com'
                self.username = 'testuser'
                self.password = 'bbb'
                self.name = name

            def zone_get(self, context, child_zone):
                return self

        def mock_client(self, username, api_key, project_id,
                        auth_url, timeout=None, token=None, region_name=None):

            self.servers = servers.ServerManager(self)
            return None

        def mock_authenticate(self):
            raise novaclient_exceptions.BadRequest(self)

        self.success_count = 0

        request_spec = {'instance_type': dict(flavorid='flav'),
                        'instance_properties': dict(display_name='aaa',
                                                     image_ref='image',
                                                     metadata='metameta',
                                                     reservation_id='bbb')}
        zone_info = {'child_zone': 1, 'child_blob': 2}
        kwargs = {'injected_files': 'aaa'}

        self.stubs.Set(abstract_scheduler,
                       'db',
                       FakeDb())
        self.stubs.Set(novaclient.Client,
                       '__init__',
                       mock_client)
        self.stubs.Set(novaclient.Client,
                       'authenticate',
                       mock_authenticate)

        sched = FakeAbstractScheduler()
        self.assertRaises(exception.NotAuthorized,
                          sched._ask_child_zone_to_create_instance,
                          context.get_admin_context(),
                          zone_info, request_spec, kwargs)

    @attr(kind='small')
    def test_private_schedule_exception(self):

        def mock_exception(cls, *args):
            self.exception_count += 1

        sched = FakeAbstractScheduler()

        self.assertRaises(NotImplementedError,
                          sched._schedule, {}, 'difference_param', {})

    @attr(kind='small')
    def test_schedule_exception(self):

        request_spec = {'instance_type': dict(flavorid='flav'),
                        'instance_properties': dict(display_name='aaa',
                                                     image_ref='image',
                                                     metadata='metameta',
                                                     reservation_id='bbb')}

        sched = FakeAbstractScheduler()
        self.assertRaises(driver.NoValidHost,
            sched.schedule, {}, 'difference_param', request_spec)

    @attr(kind='small')
    def test_schedule_run_instance_configuration(self):

        def mock_select(self, context, request_spec, *args, **kwargs):
            return [False, True]

        def mock_provision_resource(sself, context, build_plan_item,
                                    instance_id, request_spec, kwargs):
            pass

        request_spec = {'instance_type': dict(flavorid='flav'),
                        'instance_properties': dict(display_name='aaa',
                                                     image_ref='image',
                                                     metadata='metameta',
                                                     reservation_id='bbb'),
                        'num_instances': 5,
                         'blob': False}

        self.stubs.Set(abstract_scheduler.AbstractScheduler,
                       'select',
                       mock_select)
        self.stubs.Set(abstract_scheduler.AbstractScheduler,
                       '_provision_resource',
                       mock_provision_resource)

        sched = FakeAbstractScheduler()
        ret = sched.schedule_run_instance({}, 'aaa', request_spec)
        self.assertEqual(None, ret)

    @attr(kind='small')
    def test_provision_resource_locally(self):

        class fake_api(base.Base):

            def create_db_entry_for_new_instance(self, context,
                                                 instance_type, image,
                                                 base_options, security_group,
                                                 block_device_mapping, num=1):
                return {'id': 'testid'}

        def mock_queue_get_for(context, topic, physical_node_id, *args):
            self.success_count += 1
            return 'test'

        def mock_rpt(context, topic, msg):
            pass

        self.success_count = 0
        request_spec = {'instance_type': dict(flavorid='flav'),
                        'instance_properties': dict(display_name='aaa',
                                                    image_ref='image',
                                                    metadata='metameta',
                                                    reservation_id='bbb'),
                        'image': 'abc'}
        build_plan_item = {'hostname': "testhost"}

        self.stubs.Set(compute_api, 'API', fake_api)
        self.stubs.Set(db, 'queue_get_for', mock_queue_get_for)
        self.stubs.Set(rpc, 'cast', mock_rpt)

        sched = FakeAbstractScheduler()
        sched._provision_resource_locally({},
                                          build_plan_item,
                                          request_spec,
                                          {'instance_id': 'aa'})

        self.assertEqual(1, self.success_count)


class BaseSchedulerTestCase(test.TestCase):
    """Test case for Base Scheduler."""

    def test_weigh_hosts(self):
        """
        Try to weigh a short list of hosts and make sure enough
        entries for a larger number instances are returned.
        """

        sched = FakeBaseScheduler()

        # Fake out a list of hosts
        zm = FakeZoneManager()
        hostlist = [(host, services['compute'])
                    for host, services in zm.service_states.items()
                    if 'compute' in services]

        # Call weigh_hosts()
        num_instances = len(hostlist) * 2 + len(hostlist) / 2
        instlist = sched.weigh_hosts('compute',
                                     dict(num_instances=num_instances),
                                     hostlist)

        # Should be enough entries to cover all instances
        self.assertEqual(len(instlist), num_instances)
