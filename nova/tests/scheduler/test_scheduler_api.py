# vim: tabstop=4 shiftwidth=4 softtabstop=4

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
Tests For nova.scheduler.api
"""

import functools
import mox
from nova import compute
from nova import context
from nova import db
from nova import exception
from nova import flags
from nova import log as logging
from nova import rpc
from nova import test
from nova import utils
from nose.plugins.attrib import attr
from nova.scheduler import api
from nova.scheduler import manager
from nova.scheduler import multi
from nova.compute import power_state
from nova.compute import vm_states
from novaclient import v1_1 as novaclient
from novaclient import exceptions as novaclient_exceptions
from eventlet import greenpool
from nova.compute import instance_types
from nova.tests.api.openstack import common
from nova.tests.api.openstack import fakes
import datetime
import nova.db.api
from nova.compute import vm_states
from nova.compute import instance_types
from nova.db.sqlalchemy.session import get_session


class FakeContext(object):
    auth_token = None

FLAGS = flags.FLAGS
flags.DECLARE('max_cores', 'nova.scheduler.simple')
flags.DECLARE('stub_network', 'nova.compute.manager')
flags.DECLARE('instances_path', 'nova.compute.manager')


class FakeReturnValue(object):
    def __init__(self):
        self._results = "test"
        self.manager = "test"
        self.test = "test"


class ApiTestCase(test.TestCase):
    """Test for nova.scheduler.api. """
    def setUp(self):
        super(ApiTestCase, self).setUp()
        driver = 'nova.tests.scheduler.test_scheduler.TestDriver'
        self.flags(scheduler_driver=driver)
        self.ctxt = context.get_admin_context()
        api.zone_create(self.ctxt, dict(zone_id="001",
        api_url="http:\/\/localhost:8080\/"))
        api.zone_create(self.ctxt, dict(zone_id="002",
        api_url="http:\/\/localhost:8080\/"))

    @attr(kind='small')
    def test_get_host_list(self):
        """Test for nova.scheduler.api.get_host_list. """
        self.mock_call_called = False

        def mock_call(context, topic, msg):
            self.mock_call_called = True

        self.stubs.Set(rpc, 'call', mock_call)
        api.get_host_list(self.ctxt)
        self.assertEqual(self.mock_call_called, True)

    @attr(kind='small')
    def test_get_host_list_parameter(self):
        """Test for nova.scheduler.api.get_host_list. """
        self.mock_call_called_count = 0

        def mock_call(context, topic, msg):
            self.mock_call_called_count += 1

        self.stubs.Set(rpc, 'call', mock_call)
        ref = api.get_host_list('Str')
        ref = api.get_host_list(1)
        ref = api.get_host_list(None)
        self.assertEqual(self.mock_call_called_count, 3)

    @attr(kind='small')
    def test_get_zone_list(self):
        """Test for nova.scheduler.api.get_zone_list. """

        """one item"""
        def mock_call(context, topic, msg):
            return [dict(api_url="http:\/\/localhost:8080\/")]

        self.stubs.Set(rpc, 'call', mock_call)
        ref = api.get_zone_list(self.ctxt)
        self.assertEqual("http://localhost:8080/", ref[0]['api_url'])

        """no item"""
        def mock_call2(context, topic, msg):
            return []

        self.stubs.Set(rpc, 'call', mock_call2)
        ref = api.get_zone_list(self.ctxt)
        self.assertEqual(2, len(ref))

    @attr(kind='small')
    def test_get_zone_list_configration(self):
        """Test for nova.scheduler.api.get_zone_list. """
        self.flags(scheduler_topic="test_topic")

        def mock_call(context, topic, msg):
            self.assertEqual("test_topic", topic)
            return [dict(api_url="http:\/\/localhost:8080\/")]

        self.stubs.Set(rpc, 'call', mock_call)
        ref = api.get_zone_list(self.ctxt)

    @attr(kind='small')
    def test_zone_get(self):
        """Test for nova.scheduler.api.zone_get. """
        ref = dict(api.zone_get(self.ctxt, "002").iteritems())

        self.assertEqual(2, ref["id"])

    @attr(kind='small')
    def test_zone_delete(self):
        """Test for nova.scheduler.api.zone_delete. """
        api.zone_delete(self.ctxt, "001")
        self.assertRaises(exception.ZoneNotFound,
                api.zone_get, self.ctxt, "001")

        api.zone_create(self.ctxt, dict(zone_id="001"))

    @attr(kind='small')
    def test_zone_create(self):
        """Test for nova.scheduler.api.zone_create. """
        api.zone_create(self.ctxt, dict(zone_id="003", username="u3"))
        ref = dict(api.zone_get(self.ctxt, "003").iteritems())
        self.assertEqual("u3", ref["username"])

    @attr(kind='small')
    def test_zone_update(self):
        """Test for nova.scheduler.api.zone_update. """
        api.zone_update(self.ctxt, "001", dict(username="u001"))
        ref = dict(api.zone_get(self.ctxt, "001").iteritems())
        self.assertEqual("u001", ref["username"])

    @attr(kind='small')
    def test_get_zone_capabilities(self):
        """Test for nova.scheduler.api.get_zone_capabilities. """
        self.get_zone_capabilities_called = False

        def mock_call(context, topic, msg):
            self.get_zone_capabilities_called = True

        self.stubs.Set(rpc, 'call', mock_call)
        ref = api.get_zone_capabilities(self.ctxt)

        self.assertEqual(True, self.get_zone_capabilities_called)

    @attr(kind='small')
    def test_select(self):
        """Test for nova.scheduler.api.select. """
        self.select_called = False

        def mock_call(context, topic, msg):
            self.select_called = True

        self.stubs.Set(rpc, 'call', mock_call)

        ref = api.select(context)
        self.assertEqual(True, self.select_called)

    @attr(kind='small')
    def test_select_parameter(self):
        """Test for nova.scheduler.api.select. """
        self.select_called = False

        def mock_call(context, topic, msg):
            self.select_called = True

        self.stubs.Set(rpc, 'call', mock_call)

        ref = api.select(context, "aaa")
        self.assertEqual(True, self.select_called)

        self.select_called = False

        ref = api.select(context, 1)
        self.assertEqual(True, self.select_called)

    @attr(kind='small')
    def test_update_service_capabilities(self):
        """Test for nova.scheduler.api.update_service_capabilities. """
        self.update_service_capabilities_called = False

        def mock_fanout_cast(context, topic, msg):
            self.update_service_capabilities_called = True

        self.stubs.Set(rpc, 'fanout_cast', mock_fanout_cast)

        api.update_service_capabilities(self.ctxt,
        "service_name", "host", "capabilities")

        self.assertEqual(True, self.update_service_capabilities_called)

    @attr(kind='small')
    def test_child_zone_helper(self):
        """Test for nova.scheduler.api.child_zone_helper. """
        self.test_func_called = False

        def test_func(*args, **kwargs):
            self.test_func_called = True

        def mock_authenticate(self):
            pass

        self.stubs.Set(novaclient.Client, 'authenticate',
        mock_authenticate)

        ref = api.child_zone_helper(
        [api.zone_get(self.ctxt, "001"), api.zone_get(self.ctxt, "002")],
        test_func)

        self.assertEqual(2, len(ref))
        self.assertEqual(True, self.test_func_called)

    @attr(kind='small')
    def test_child_zone_helper_exception(self):
        """Test for nova.scheduler.api.child_zone_helper. """
        self.test_func_called = False

        def test_func(*args, **kwargs):
            self.test_func_called = True

        def mock_authenticate(self):
            raise novaclient_exceptions.BadRequest('foo')

        self.stubs.Set(novaclient.Client, 'authenticate',
        mock_authenticate)

        ref = api.child_zone_helper(
        [api.zone_get(self.ctxt, "001"), api.zone_get(self.ctxt, "002")],
        test_func)
        self.assertEqual('1 or more Zones could not complete the request',
        ref[0][0])

    @attr(kind='small')
    def test_wrap_novaclient_function(self):
        """Test for nova.scheduler.api.wrap_novaclient_function. """
        self.test_func_called = False

        def test_func(*args, **kwargs):
            self.test_func_called = True

        ref = api.wrap_novaclient_function(test_func, "collection",
        "test_method")

        zone = api.zone_get(self.ctxt, "001")
        nova = novaclient.Client(zone.username, zone.password, None,
                    zone.api_url)

        ref(nova, zone)

        self.assertEqual(True, self.test_func_called)

    @attr(kind='small')
    def test_redirect_handler(self):
        """Test for nova.scheduler.api.redirect_handler. """
        self.test_func_called = False

        def test_func(*args, **kwargs):
            self.test_func_called = True

        ref = api.redirect_handler(test_func)()
        self.assertEqual(True, self.test_func_called)

    @attr(kind='small')
    def test_redirect_handler_exception(self):
        """Test for nova.scheduler.api.redirect_handler. """
        self.test_func_called = False

        def make_BaseException_func(*args, **kwargs):
            pass

        zone1 = api.zone_get(self.ctxt, "001")
        zone2 = api.zone_get(self.ctxt, "001")

        results = api.child_zone_helper([zone1, zone2],
                    make_BaseException_func)

        """single BaseException"""
        def test_func_s(*args, **kwargs):
            raise api.RedirectResult(results[0])

        ref = api.redirect_handler(test_func_s)()
        self.assertEqual('1 or more Zones could not complete the request',
                         ref[0])

        """multiple BaseException"""
        def test_func_m(*args, **kwargs):
            raise api.RedirectResult(results)

        ref = api.redirect_handler(test_func_m)()
        self.assertEqual('1 or more Zones could not complete the request',
                         ref[0][0])
        self.assertEqual('1 or more Zones could not complete the request',
                         ref[1][0])


class Reroute_computeTestCase(test.TestCase):
    """Test for nova.scheduler.api.reroute_compute. """
    def setUp(self):
        super(Reroute_computeTestCase, self).setUp()

        driver = 'nova.tests.scheduler.test_scheduler.TestDriver'
        self.flags(scheduler_driver=driver)
        self.ctxt = context.get_admin_context()

        api.zone_create(self.ctxt, dict(zone_id="001",
        api_url="http:\/\/localhost:8080\/"))

        api.zone_create(self.ctxt, dict(zone_id="002",
        api_url="http:\/\/localhost:8080\/"))

        self.reroute_compute = api.reroute_compute('foo')

    @attr(kind='small')
    def test___call__(self):
        """Test for nova.scheduler.api.
           reroute_compute.replace_uuid_with_id. """
        self.test_func_called = False

        def test_func(*args, **kwargs):
            self.test_func_called = True

        self.reroute_compute(test_func)(context=self.ctxt,
        instance_id='aaaaaaaa')

        self.assertEqual(True, self.test_func_called)

        self.test_func_called = False

        def fake_instance_get_by_uuid(context, uuid):
            return {'id': 1}

        self.stubs.Set(db, 'instance_get_by_uuid',
                       fake_instance_get_by_uuid)

        ref = self.reroute_compute(test_func)(context=self.ctxt,
        instance_id='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa')

        self.assertEqual(True, self.test_func_called)

    @attr(kind='small')
    def test___call___exception(self):
        """Test for nova.scheduler.api.reroute_compute.
           replace_uuid_with_id. """
        self.test_func_called = False

        def test_func(*args, **kwargs):
            self.test_func_called = True

        self.assertRaises(exception.InstanceNotFound,
                          self.reroute_compute(test_func),
                          context=self.ctxt,
                          instance_id='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa')

    def _create_instance(self, params=None):
        """Create a test instance"""
        if not params:
            params = {}

        inst = {}
        inst['image_ref'] = 1
        inst['reservation_id'] = 'r-fakeres'
        inst['launch_time'] = '10'
        inst['user_id'] = 'fake'
        inst['project_id'] = 'fake'
        type_id = 'fake'
        inst['instance_type_id'] = 'fake'
        inst['ami_launch_index'] = 0
        inst.update(params)
        return db.instance_create(self.ctxt, inst)['id']

    @attr(kind='small')
    def test___call___database(self):
        """Test for nova.scheduler.api.
           reroute_compute.replace_uuid_with_id. """
        self.instance_get_by_uuid_success = False

        def fake_replace_uuid_with_id(args, kwargs, replacement_id):
            self.instance_get_by_uuid_success = True

        self.stubs.Set(self.reroute_compute, 'replace_uuid_with_id',
                       fake_replace_uuid_with_id)

        def test_func(*args, **kwargs):
            pass

        instance_id = self._create_instance(params={'config_drive': True, })
        instance = db.instance_get(self.ctxt, instance_id)
        self.reroute_compute(test_func)("test",
        self.ctxt, instance.get('uuid'))

        self.assertEqual(True, self.instance_get_by_uuid_success)

    @attr(kind='small')
    def test_replace_uuid_with_id(self):
        """Test for nova.scheduler.api.reroute_compute.
           replace_uuid_with_id. """
        temp_kwargs = {'id': 1,
                       'instance_id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'}

        self.reroute_compute.replace_uuid_with_id([],
        temp_kwargs, replacement_id='xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx')

        self.assertEqual('xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx',
                         temp_kwargs['instance_id'])

        temp_args = [1, 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa']

        self.reroute_compute.replace_uuid_with_id(temp_args, {},
        replacement_id='xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx')

        self.assertEqual('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', temp_args[1])

    @attr(kind='small')
    def test_unmarshall_result_parameter(self):
        """Test for nova.scheduler.api.reroute_compute.unmarshall_result. """

        def mock_authenticate(self):
            pass

        self.stubs.Set(novaclient.Client, 'authenticate', mock_authenticate)

        zone1 = api.zone_get(self.ctxt, "001")
        zone2 = api.zone_get(self.ctxt, "001")

        self.test_func_called = False

        def test_func(*args, **kwargs):
            self.test_func_called = True

        """BaseException result"""
        result = api.child_zone_helper([zone1, zone2], test_func)
        self.reroute_compute.item_uuid = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        #self.reroute_compute.unmarshall_result(result)
        self.assertRaises(exception.InstanceNotFound,
                          self.reroute_compute.unmarshall_result, result)
        #self.assertEqual(True, self.test_func_called)

        self.test_func_called = False

        def test_func2(*args, **kwargs):
            self.test_func_called = True
            return FakeReturnValue()

        """Normal result"""
        result = api.child_zone_helper([zone1, zone2],
                    test_func2)

        self.reroute_compute.unmarshall_result(result)
        self.assertEqual(True, self.test_func_called)
