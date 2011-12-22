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
Tests For nova.compute.api.API
"""
from datetime import datetime

from nova import compute
from nova.compute import instance_types
from nova.compute import power_state
from nova.compute import vm_states
from nova import context
from nova import db
from nova.db.sqlalchemy import models
from nova import exception
from nova import flags
import nova.image.fake
from nova import log as logging
from nova import rpc
from nova import test
from nova import utils
from nova.notifier import test_notifier

from nova.scheduler import api as scheduler_api
from nova import volume
from nova import quota
from nose.plugins.attrib import attr

LOG = logging.getLogger('nova.tests.compute.api')
FLAGS = flags.FLAGS
flags.DECLARE('stub_network', 'nova.compute.manager')
flags.DECLARE('live_migration_retry_count', 'nova.compute.manager')

flags.DEFINE_string('tests_compute_api_result', False, 'for message assert')
flags.DEFINE_string('tests_compute_api_rpc_args', {}, 'for message assert')
flags.DEFINE_string('tests_compute_api_name', '', 'for message test')


class FakeTime(object):
    def __init__(self):
        self.counter = 0

    def sleep(self, t):
        self.counter += t


def nop_report_driver_status(self):
    pass


class ComputeAPITestCase(test.TestCase):
    """Test case for compute api"""
    def setUp(self):
        super(ComputeAPITestCase, self).setUp()
        self.flags(connection_type='fake',
                   stub_network=True,
                   notification_driver='nova.notifier.test_notifier',
                   network_manager='nova.network.manager.FlatManager')
        self.compute = utils.import_object(FLAGS.compute_manager)
        self.compute_api = compute.API()
        self.user_id = 'fake'
        self.project_id = 'fake'
        self.context = context.RequestContext(self.user_id, self.project_id)
        test_notifier.NOTIFICATIONS = []

        def fake_show(meh, context, id):
            return {'id': 1, 'properties': {'kernel_id': 1, 'ramdisk_id': 1}}

        self.stubs.Set(nova.image.fake._FakeImageService, 'show', fake_show)

    def _create_instance(self, params=None):
        """Create a test instance"""
        if not params:
            params = {}

        inst = {}
        inst['image_ref'] = 1
        inst['reservation_id'] = 'r-fakeres'
        inst['launch_time'] = '10'
        inst['user_id'] = self.user_id
        inst['project_id'] = self.project_id
        type_id = instance_types.get_instance_type_by_name('m1.tiny')['id']
        inst['instance_type_id'] = type_id
        inst['ami_launch_index'] = 0
        inst.update(params)
        return db.instance_create(self.context, inst)['id']

    def _create_group(self):
        values = {'name': 'testgroup',
                  'description': 'testgroup',
                  'user_id': self.user_id,
                  'project_id': self.project_id}
        return db.security_group_create(self.context, values)

    @test.skip_test('ignore this case')
    @attr(kind='small')
    def test_create_parameter_display_name_blank(self):
        """Verify that an instance can be created using default display name.
        display_name will be 'Server {id}' if input is blank
        """
        cases = [dict(display_name='')]
        for instance in cases:
            ref = self.compute_api.create(self.context,
                instance_types.get_default_instance_type(), None, **instance)

            self.assertTrue(ref[0]['display_name'].startswith('Server'))

    @test.skip_test('ignore this case')
    @attr(kind='small')
    def test_default_hostname_generator_parameter(self):
        """Verify that an instance can be created using default hostname.
        hostname will be 'Server-{id}' if input is blank
        """
        cases = [('', 'server-1'),
                 (u'\u6587\u5b57\u5217Server-a', 'Server-a')]
        for display_name, hostname in cases:
            ref = self.compute_api.create(self.context,
                instance_types.get_default_instance_type(), None,
                display_name=display_name)

            self.assertEqual(hostname, ref[0]['hostname'])

    @attr(kind='small')
    def test_volume_size_parameter_zero(self):
        """Verify volume size is 0 if device name is not swap and ephemeral0"""
        local_size = 2
        inst_type = {'local_gb': local_size}
        size = self.compute_api._volume_size(inst_type, 'ephemeral01')
        self.assertEqual(0, size)

    @attr(kind='small')
    def test_volume_size_parameter_ephemeral1(self):
        """Verify volume size is 0 ,
        if device name is ephemeral and sequence>0"""
        local_size = 2
        inst_type = {'local_gb': local_size}
        size = self.compute_api._volume_size(inst_type, 'ephemeral1')
        self.assertEqual(0, size)
        size = self.compute_api._volume_size(inst_type, 'ephemeral10')
        self.assertEqual(0, size)

    @attr(kind='small')
    def test_volume_size_parameter_ephemeral0(self):
        """Verify volume size is input value if device name is ephemeral0"""
        local_size = 2
        inst_type = {'local_gb': local_size}
        size = self.compute_api._volume_size(inst_type, 'ephemeral0')
        self.assertEqual(local_size, size)

    @attr(kind='small')
    def test_volume_size_parameter_swap(self):
        """Verify volume size is 0 if device name is not swap and ephemeral0"""
        local_size = 2
        inst_type = {'swap': local_size}
        size = self.compute_api._volume_size(inst_type, 'swap')
        self.assertEqual(local_size, size)

    @test.skip_test('ignore this case for issue741') 
    @attr(kind='small')
    def test_create_parameter_instance_associates_config_drive(self):
        """Make sure create instance that config_drive is a image id.
        config_drive's value be registed to config_drive_id"""

        image_id = '1'
        param = dict(config_drive=image_id)

        self.compute_api.create(self.context,
            instance_types.get_default_instance_type(), None, **param)
        instances = db.instance_get_all(context.get_admin_context())
        instance = instances[0]

        self.assertTrue(hasattr(instance, 'config_drive_id'))
        self.assertEqual(image_id, instance.config_drive_id)

    @test.skip_test('ignore this case for issue741') 
    @attr(kind='small')
    def test_create_parameter_associates_config_drive_none(self):
        """Make sure create instance that config_drive is none.
        config_drive and config_drive_id will be empty in database record
        """
        image_id = None
        param = dict(config_drive=image_id)

        self.compute_api.create(self.context,
            instance_types.get_default_instance_type(), None, **param)
        instances = db.instance_get_all(context.get_admin_context())
        instance = instances[0]

        self.assertTrue(hasattr(instance, 'config_drive_id'))
        self.assertEqual('', instance.config_drive_id)
        self.assertEqual('', instance.config_drive)

    @attr(kind='small')
    def test_create_exception_associates_config_drive_id_notexist(self):
        """Make sure create instance that config_drive is none.
        config_drive and config_drive_id will be empty in database record
        """
        def fake_image_show(meh, context, id):
            if id == '999':
                raise exception.ImageNotFound(image_id=id)
            return {'id': 1, 'properties': {'kernel_id': 1, 'ramdisk_id': 1}}

        self.stubs.Set(nova.image.fake._FakeImageService,
                       'show', fake_image_show)

        # not exist image id
        image_id = '999'
        param = dict(config_drive=image_id)

        self.assertRaises(exception.ImageNotFound,
            self.compute_api.create, self.context,
                instance_types.get_default_instance_type(), None, **param)

    @attr(kind='small')
    def test_create_parameter_multiple_instances(self):
        """Make sure create multiple instances once time"""
        ins_count = 3
        self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None,
                max_count=ins_count)

        self.assertEqual(ins_count, len(db.instance_get_all(
                context.get_admin_context())))

    @attr(kind='small')
    def test_create_parameter_multiple_instances_zero(self):
        """Make sure 1 instance be created  when max_count is None or zero"""
        ins_count = 0
        self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None,
                max_count=ins_count)

        self.assertEqual(1, len(db.instance_get_all(
                context.get_admin_context())))

    @attr(kind='small')
    def test_create_exception_multiple_instances_minus(self):
        """Make sure raise quota error when max_count is minus value"""
        ins_count = -1
        self.assertRaises(quota.QuotaError,
            self.compute_api.create,
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None,
                max_count=ins_count)

    @attr(kind='small')
    def test_create_exception_multiple_instances_invalid(self):
        """Make sure raise ApiError when max_count is not number"""

        ins_count = 'a'
        self.assertRaises(exception.ApiError,
            self.compute_api.create,
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None,
                max_count=ins_count)

    @attr(kind='small')
    def test_create_parameter(self):
        """Test create instances with parameter checking"""
        def fake_service(context, image_href):
            ImageService = utils.import_class(FLAGS.image_service)
            return (ImageService(), 1)

        self.flags(tests_compute_api_name='create')
        self.stubs.Set(rpc, 'call', self._fake_cast)
        self.stubs.Set(nova.image, 'get_image_service', fake_service)

        inparam = dict(
                image_href='http://localhost:9292/images/1',
                kernel_id='2',
                ramdisk_id='3',
                min_count=1,
                max_count=2,
                display_name='Server_All',
                display_description='a instance with all parameters',
                key_name='user_id1',
                key_data='AABBXXDD',
                security_group='default',
                availability_zone='Tokyo',
                user_data='a test',
                metadata={'meta1': 'value1'},
                injected_files=[{'path': '/var/log/', 'contents': 'contents'}],
                admin_password='password1',
                zone_blob='zone1',
                reservation_id='4',
                block_device_mapping=[{'device_name': '/dev/sda1'}],
                access_ip_v4='192.168.1.1',
                access_ip_v6='192.168.1.2',
                requested_networks=[{'networkuuid':123}],
                config_drive=True)

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                **inparam)
        ins = ref[0]

        self.assertEqual(inparam['image_href'], ins['image_ref'])
        self.assertEqual(inparam['kernel_id'], ins['kernel_id'])
        self.assertEqual(inparam['ramdisk_id'], ins['ramdisk_id'])
        self.assertEqual(inparam['display_name'], ins['display_name'])
        self.assertEqual(inparam['display_description'],
                                        ins['display_description'])
        self.assertEqual(inparam['key_name'], ins['key_name'])
        self.assertEqual(inparam['key_data'], ins['key_data'])
        self.assertEqual(inparam['security_group'],
                                        ins['security_groups'][0]['name'])
        self.assertEqual(inparam['availability_zone'],
                                        ins['availability_zone'])
        self.assertEqual(inparam['user_data'], ins['user_data'])
        self.assertEqual(inparam['metadata']['meta1'],
                                        ins['metadata'][0]['value'])
        self.assertEqual(inparam['reservation_id'], ins['reservation_id'])
        self.assertEqual(inparam['access_ip_v4'], ins['access_ip_v4'])
        self.assertEqual(inparam['access_ip_v6'], ins['access_ip_v6'])
        self.assertEqual('1', ins['config_drive'])

    @attr(kind='small')
    def test_create_all_at_once_parameter(self):
        """Test create all instances with parameter checking"""
        def fake_service(context, image_href):
            ImageService = utils.import_class(FLAGS.image_service)
            return (ImageService(), 1)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='create_all_at_once')
        self.stubs.Set(rpc, 'call', self._fake_cast)
        self.stubs.Set(rpc, 'cast', self._fake_cast)
        self.stubs.Set(nova.image, 'get_image_service', fake_service)

        inparam = dict(
                image_href='http://localhost:9292/images/1',
                kernel_id='2',
                ramdisk_id='3',
                min_count=1,
                max_count=2,
                display_name='Server_All',
                display_description='a instance with all parameters',
                key_name='user_id1',
                key_data='AABBXXDD',
                security_group='default',
                availability_zone='Tokyo',
                user_data='a test',
                metadata={'meta1': 'value1'},
                injected_files=[{'path': '/var/log/', 'contents': 'contents'}],
                admin_password='password1',
                zone_blob='zone1',
                block_device_mapping=[{'device_name': '/dev/sda1'}],
                access_ip_v4='192.168.1.1',
                access_ip_v6='192.168.1.2',
                requested_networks=[{'networkuuid':123}],
                config_drive=True)

        ref = self.compute_api.create_all_at_once(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                **inparam)

        self.assertTrue(ref)
        self.assertTrue(FLAGS.tests_compute_api_result)

        # verify rpc message parameters
        for i, v in enumerate(inparam['injected_files']):
            self.assertEqual(v,
                FLAGS.tests_compute_api_rpc_args['injected_files'][i])

        for i, v in enumerate(inparam['requested_networks']):
            self.assertEqual(v,
                FLAGS.tests_compute_api_rpc_args['requested_networks'][i])

        argsDic = FLAGS.tests_compute_api_rpc_args
        del argsDic['topic']
        del argsDic['instance_id']
        del argsDic['request_spec']
        del argsDic['injected_files']
        del argsDic['requested_networks']

        self.assertSubDictMatch(argsDic, inparam)

    @attr(kind='small')
    def test_create_all_at_once_parameter_quota(self):
        """Test create all instances with min_count > max_count"""
        def fake_service(context, image_href):
            ImageService = utils.import_class(FLAGS.image_service)
            return (ImageService(), 1)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='create_all_at_once')
        self.stubs.Set(rpc, 'call', self._fake_cast)
        self.stubs.Set(rpc, 'cast', self._fake_cast)
        self.stubs.Set(nova.image, 'get_image_service', fake_service)

        inparam = dict(
                image_href='1',
                min_count=2,
                max_count=1)

        self.assertRaises(quota.QuotaError,
            self.compute_api.create_all_at_once,
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                **inparam)

    @attr(kind='small')
    def test_create_all_at_once_parameter_image_id_notexist(self):
        """Test create all instances with none image id"""
        def fake_service(context, image_href):
            ImageService = utils.import_class(FLAGS.image_service)
            return (ImageService(), 1)

        def fake_image_show(meh, context, id):
            raise exception.ImageNotFound(image_id=id)

        self.stubs.Set(nova.image.fake._FakeImageService,
                       'show', fake_image_show)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='create_all_at_once')
        self.stubs.Set(rpc, 'call', self._fake_cast)
        self.stubs.Set(rpc, 'cast', self._fake_cast)
        self.stubs.Set(nova.image, 'get_image_service', fake_service)

        inparam = dict(
                image_href=None)

        self.assertRaises(exception.ImageNotFound,
            self.compute_api.create_all_at_once,
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                **inparam)

    @attr(kind='small')
    def test_create_all_at_once_parameter_keydata_notexist(self):
        """Test create all instances with keydata"""
        def fake_service(context, image_href):
            ImageService = utils.import_class(FLAGS.image_service)
            return (ImageService(), 1)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='create_all_at_once')
        self.stubs.Set(rpc, 'call', self._fake_cast)
        self.stubs.Set(rpc, 'cast', self._fake_cast)
        self.stubs.Set(nova.image, 'get_image_service', fake_service)

        inparam = dict(image_href='1', key_name='user_id1', key_data=None)

        self.assertRaises(exception.KeypairNotFound,
            self.compute_api.create_all_at_once,
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                **inparam)

    @test.skip_test('ignore this case')
    @attr(kind='small')
    def test_create_all_at_once_parameter_keydata_blank(self):
        """Test create all instances with keydata"""
        def fake_service(context, image_href):
            ImageService = utils.import_class(FLAGS.image_service)
            return (ImageService(), 1)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='create_all_at_once')
        self.stubs.Set(rpc, 'call', self._fake_cast)
        self.stubs.Set(rpc, 'cast', self._fake_cast)
        self.stubs.Set(nova.image, 'get_image_service', fake_service)

        inparam = dict(image_href='1', key_name='user_id1', key_data='')

        self.assertRaises(exception.KeypairNotFound,
            self.compute_api.create_all_at_once,
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                **inparam)

    @attr(kind='small')
    def test_remove_security_group(self):
        """Make sure destroying security groups from instances"""

        group = self._create_group()

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None,
                security_group=['testgroup'])

        # power_state or vm_state? waiting for api bug fix
        self.compute_api.update(self.context,
                ref[0]['id'], power_state=power_state.RUNNING)

        groups = db.security_group_get(context.get_admin_context(),
                            group['id'])
        self.assertEqual(1, len(groups.instances))

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='remove_security_group')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        self.compute_api.remove_security_group(
            self.context, ref[0]['id'], 'testgroup')

        groups = db.security_group_get(context.get_admin_context(),
                                       group['id'])

        self.assertEqual(0, len(groups.instances))
        self.assertTrue(FLAGS.tests_compute_api_result)

        # verify rpc message parameters
        self.assertEqual(dict(security_group_id=group['id']),
                FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_remove_security_group_exception_unavailable_state(self):
        """Make sure cannot destroying security groups from instances if not
        running
        """
        self._create_group()

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None,
                security_group=['testgroup'])

        self.assertRaises(exception.InstanceNotRunning,
                self.compute_api.remove_security_group,
                self.context, ref[0]['id'], 'testgroup')

    @attr(kind='small')
    def test_remove_security_group_exception_disassociated(self):
        """Make sure destroying security groups failure if not in group"""
        self._create_group()

        # instance with default security_group
        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.assertRaises(exception.SecurityGroupNotExistsForInstance,
                self.compute_api.remove_security_group,
                self.context, ref[0]['id'], 'testgroup')

    @attr(kind='small')
    def test_add_security_group_database(self):
        """Make sure security groups associating to instance"""
        group = self._create_group()

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.compute_api.update(self.context,
                ref[0]['id'], power_state=power_state.RUNNING)

        groups = db.security_group_get(context.get_admin_context(),
                            group['id'])
        self.assertEqual(0, len(groups.instances))

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='add_security_group')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        self.compute_api.add_security_group(
            self.context, ref[0]['id'], 'testgroup')

        groups = db.security_group_get(context.get_admin_context(),
                                       group['id'])

        self.assertEqual(1, len(groups.instances))
        self.assertTrue(FLAGS.tests_compute_api_result)

        # verify rpc message parameters
        self.assertEqual(dict(security_group_id=group['id']),
                FLAGS.tests_compute_api_rpc_args)

    @test.skip_test('delete is available for this state')
    @attr(kind='small')
    def test_delete_exception_unavailable_state(self):
        """Make sure return value when destroying instance error"""

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        # shutdown not available vm state[ACTIVE,REBUILDING,BUILDING]
        self.compute_api.update(self.context,
                ref[0]['id'], vm_state=vm_states.SUSPENDED)

        self.assertRaises(exception.ApiError,
                self.compute_api.delete, self.context, ref[0]['id'])

    @attr(kind='small')
    def test_stop_exception_unavailable_state(self):
        """Make sure return value when stopping instance error"""

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        # shutdown not available vm state[ACTIVE,REBUILDING,BUILDING]
        self.compute_api.update(self.context,
                ref[0]['id'], vm_state=vm_states.SUSPENDED)

        self.assertRaises(exception.ApiError,
                self.compute_api.stop, self.context, ref[0]['id'])

    @attr(kind='small')
    def test_start_exception_unavailable_state(self):
        """Make sure return value when starting instance error"""

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        # start not available vm state[STOPPED]
        self.compute_api.update(self.context,
                ref[0]['id'], vm_state=vm_states.SUSPENDED)

        self.assertRaises(exception.ApiError,
                self.compute_api.start, self.context, ref[0]['id'])

    @attr(kind='small')
    def test_ensure_default_security_group_database(self):
        """Make sure create the default security group when not inputed"""

        group_name = 'default'
        db.security_group_destroy_all(self.context)

        self.compute_api.ensure_default_security_group(self.context)

        self.assertTrue(db.security_group_exists(
                self.context, self.context.project_id, group_name))

    @test.skip_test('ignore this case')
    @attr(kind='small')
    def test_update_parameter_invalid_display_name(self):
        """Make sure instance's display_name be updated
        but not be empty String"""

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        param = dict(display_name='', display_description='aaaaa')

        self.compute_api.update(self.context, ref[0]['id'], **param)

        instance = db.instance_get_all(context.get_admin_context())[0]

        self.assertTrue(instance['display_name'])

    @test.skip_test('ignore this case')
    @attr(kind='small')
    def test_update_parameter_invalid_description(self):
        """Make sure instance's display_description be updated with long String
        """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        desc = '1'.zfill(1024)

        param = dict(display_name='Server test1', display_description=desc)

        self.assertRaises(exception.ApiError,
            self.compute_api.update, self.context, ref[0]['id'], **param)

        instance = db.instance_get_all(context.get_admin_context())[0]
        self.assertTrue(len(instance['display_description']) <= 256)

    @attr(kind='small')
    def test_update_instance_metadata(self):
        """Make sure instance's metadata be updated """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        meta1 = {'meta1': 'value1'}
        meta2 = {'meta2': 'value2', 'meta3': 'value3'}
        meta3 = {'meta1': 'value1', 'meta2': 'value2'}

        self.compute_api.update_instance_metadata(self.context,
                ref[0]['id'], meta1, True)

        # not exist meta update
        instance = db.instance_get_all(context.get_admin_context())[0]

        self.assertEqual('value1', instance['metadata'][0].value)

        # delete before update
        self.compute_api.update_instance_metadata(self.context,
                ref[0]['id'], meta2, True)
        instance = db.instance_get_all(context.get_admin_context())[0]

        self.assertEqual(2, len(instance['metadata']))
        self.assertEqual('value2', instance['metadata'][0].value)

        # update without delete
        self.compute_api.update_instance_metadata(self.context,
                ref[0]['id'], meta3, False)

        instance = db.instance_get_all(context.get_admin_context())[0]
        self.assertEqual(3, len(instance['metadata']))
        self.assertEqual('value1', instance['metadata'][2].value)

    @attr(kind='small')
    def test_update_instance_metadata_exception_quota_over(self):
        """Make sure count quota of metadata be checked """

        self.flags(quota_metadata_items=1)

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        meta1 = {'meta1': 'value1', 'meta2': 'value2'}

        self.assertRaises(quota.QuotaError,
                self.compute_api.update_instance_metadata,
                self.context, ref[0]['id'], meta1, True)

    @attr(kind='small')
    def test_update_instance_metadata_exception_content_quotaover(self):
        """Make sure contests quota of metadata be checked """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        desc = '1'.zfill(256)
        meta1 = {'meta1': desc}

        self.assertRaises(quota.QuotaError,
                self.compute_api.update_instance_metadata,
                self.context, ref[0]['id'], meta1, True)

    @attr(kind='small')
    def test_get_instance_metadata_database(self):
        """Make sure all of metadatas be found by instance id"""

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        metas = {'meta1': 'value1', 'meta2': 'value2'}
        self.compute_api.update_instance_metadata(self.context,
                ref[0]['id'], metas, True)

        instance = db.instance_get_all(context.get_admin_context())[0]
        self.assertEqual(2, len(instance['metadata']))

        meta_ref = self.compute_api.get_instance_metadata(self.context,
            ref[0]['id'])

        self.assertEqual(metas, meta_ref)

    @attr(kind='small')
    def test_delete_instance_metadata_database(self):
        """Make sure instance's metadata be deleted """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        metas = {'meta1': 'value1', 'meta2': 'value2'}
        self.compute_api.update_instance_metadata(self.context,
                ref[0]['id'], metas, True)

        instance = db.instance_get_all(context.get_admin_context())[0]
        self.assertEqual(2, len(instance['metadata']))

        self.compute_api.delete_instance_metadata(self.context,
            ref[0]['id'], 'meta1')

        instance = db.instance_get_all(context.get_admin_context())[0]
        self.assertEqual(1, len(instance['metadata']))
        self.assertEqual('value2', instance['metadata'][0].value)

    @attr(kind='small')
    def test_rebuild_exception_unavailabe_state(self):
        """Make sure instance cannot rebuild with disable vm state """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        # rebuild not available vm state[STOPPED]
        self.compute_api.update(self.context,
                ref[0]['id'],
                vm_state=vm_states.SUSPENDED)

        self.assertRaises(exception.RebuildRequiresActiveInstance,
                self.compute_api.rebuild,
                self.context, ref[0]['id'],
                image_href=None,
                admin_password=None,
                name=None, metadata=None,
                files_to_inject=None)

    @attr(kind='small')
    def test_rebuild_exception_injectedfile_quota_over(self):
        """Make sure injected file count quota be checked when rebuild
        """

        self.flags(quota_max_injected_files=1)
        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        files = ['', '']

        # rebuild available vm state[ACTIVE]
        self.compute_api.update(self.context,
                ref[0]['id'], vm_state=vm_states.ACTIVE)

        self.assertRaises(quota.QuotaError,
                self.compute_api.rebuild,
                self.context, ref[0]['id'],
                image_href=None, admin_password=None, name=None,
                metadata=None, files_to_inject=files)

    @attr(kind='small')
    def test_rebuild_exception_injectedfile_path_over(self):
        """Make sure files_to_inject's path be checked when rebuild """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        # file path is over quota_max_injected_file_path_bytes
        desc = '1'.zfill(256)

        files = [(desc, 'contents1')]

        # rebuild available vm state[ACTIVE]
        self.compute_api.update(self.context,
                ref[0]['id'],
                vm_state=vm_states.ACTIVE)

        self.assertRaises(quota.QuotaError,
                self.compute_api.rebuild,
                self.context, ref[0]['id'],
                image_href=None, admin_password=None, name=None,
                metadata=None, files_to_inject=files)

    @attr(kind='small')
    def test_rebuild_exception_injectedfile_contents_over(self):
        """Make sure files_to_inject contents be checked when rebuild
        """

        self.flags(quota_max_injected_file_content_bytes=255)
        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        # file path is over quota_max_injected_file_content_bytes
        desc = '1'.zfill(256)

        files = [('path1', desc)]

        # rebuild available vm state[ACTIVE]
        self.compute_api.update(self.context,
                ref[0]['id'], vm_state=vm_states.ACTIVE)

        self.assertRaises(quota.QuotaError,
                self.compute_api.rebuild,
                self.context, ref[0]['id'],
                image_href=None, admin_password=None, name=None,
                metadata=None, files_to_inject=files)

    @test.skip_test('ignore this case')
    @attr(kind='small')
    def test_reboot_exception_unavailable_state(self):
        """Make sure instance's vm state is active when reboot """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        # reboot not available vm state[REBUILDING]
        self.compute_api.update(self.context,
                ref[0]['id'], vm_state=vm_states.REBUILDING)

        self.assertRaises(exception.ApiError,
                self.compute_api.reboot,
#                self.context,ref[0]['id'], reboot_type=None)
                self.context, ref[0]['id'])

    @attr(kind='small')
    def test_backup(self):
        """Make sure backup's rpc message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='backup')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        inparam = dict(name=None, backup_type='daily', rotation=3)
        ret_data = self.compute_api.backup(
                self.context, ref[0]['id'], **inparam)

        self.assertTrue(FLAGS.tests_compute_api_result)

        # verify rpc message parameters
        inparam['instance_id'] = ref[0]['id']
        inparam['image_id'] = ret_data['id']
        inparam['image_type'] = 'backup'
        del inparam['name']
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_snapshot(self):
        """Make sure snapshot's rpc message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='snapshot')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        inparam = dict(name=None)
        ret_data = self.compute_api.snapshot(
                self.context, ref[0]['id'], **inparam)

        self.assertTrue(FLAGS.tests_compute_api_result)

        # verify rpc message parameters
        inparam['instance_id'] = ref[0]['id']
        inparam['image_id'] = ret_data['id']
        inparam['image_type'] = 'snapshot'
        del inparam['name']
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_resize(self):
        """Make sure resize's rpc message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='resize')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        self.compute_api.resize(self.context, ref[0]['id'])

        self.assertTrue(FLAGS.tests_compute_api_result)

        # verify rpc message parameters
        inparam = dict()
        inparam['instance_id'] = ref[0]['uuid']
        inparam['instance_type_id'] = \
                    instance_types.get_default_instance_type()['id']
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_revert_resize(self):
        """Make sure revert_resize's rpc message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.compute_api.resize(self.context, ref[0]['id'])

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='revert_resize')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        # revert_resize available
        migration_ref = db.migration_create(context.get_admin_context(),
            {'instance_uuid': ref[0]['uuid'],
             'source_compute': ref[0]['host'],
             'dest_compute': FLAGS.host,
             'old_instance_type_id': ref[0]['instance_type_id'],
             'new_instance_type_id': ref[0]['instance_type_id'],
             'status': 'finished'})

        self.compute_api.revert_resize(self.context, ref[0]['id'])

        self.assertTrue(FLAGS.tests_compute_api_result)

        # verify rpc message parameters
        inparam = dict()
        inparam['instance_id'] = ref[0]['uuid']
        inparam['migration_id'] = migration_ref['id']
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_confirm_resize(self):
        """Make sure confirm_resize's rpc message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.compute_api.resize(self.context, ref[0]['id'])

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='confirm_resize')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        # confirm_resize available
        migration_ref = db.migration_create(context.get_admin_context(),
            {'instance_uuid': ref[0]['uuid'],
             'source_compute': ref[0]['host'],
             'dest_compute': FLAGS.host,
             'old_instance_type_id': ref[0]['instance_type_id'],
             'new_instance_type_id': ref[0]['instance_type_id'],
             'status': 'finished'})

        self.compute_api.confirm_resize(self.context, ref[0]['id'])

        self.assertTrue(FLAGS.tests_compute_api_result)

        # verify rpc message parameters
        inparam = dict()
        inparam['instance_id'] = ref[0]['uuid']
        inparam['migration_id'] = migration_ref['id']
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_attach_volume(self):
        """Make sure attach_volume's rpc message """
        def _fake_check_attach(self, context, volume_id):
            pass

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='attach_volume')
        self.stubs.Set(rpc, 'cast', self._fake_cast)
        self.stubs.Set(volume.api.API, 'check_attach', _fake_check_attach)

        inparam = dict(volume_id='1', device='/dev/ads')
        self.compute_api.attach_volume(
                self.context, ref[0]['id'],
                **inparam)

        self.assertTrue(FLAGS.tests_compute_api_result)

        # verify rpc message parameters
        inparam['instance_id'] = ref[0]['id']
        inparam['mountpoint'] = inparam['device']
        del inparam['device']
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @test.skip_test('ignore this case')
    @attr(kind='small')
    def test_attach_volume_device_exception_format(self):
        """Make sure attach volume's naming format"""
        def _fake_check_attach(self, context, volume_id):
            pass

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='attach_volume')
        self.stubs.Set(rpc, 'cast', self._fake_cast)
        self.stubs.Set(volume.api.API, 'check_attach', _fake_check_attach)

        self.compute_api.attach_volume(
                self.context, ref[0]['id'],
                volume_id='1', device='/dev/ads1')

        self.assertTrue(FLAGS.tests_compute_api_result)

    @attr(kind='small')
    def test_detach_volume(self):
        """Make sure detach_volume's rpc message """
        def _fake_check_detach(self, context, volume_id):
            pass

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        volume_ref = db.volume_create(context.get_admin_context(),
                            {'size': 1, 'instance_id': ref[0]['id']})

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='detach_volume')
        self.stubs.Set(rpc, 'cast', self._fake_cast)
        self.stubs.Set(volume.api.API, 'check_detach', _fake_check_detach)

        self.compute_api.detach_volume(
                self.context, volume_id=volume_ref['id'])

        self.assertTrue(FLAGS.tests_compute_api_result)

        # verify rpc message parameters
        inparam = dict()
        inparam['instance_id'] = ref[0]['id']
        inparam['volume_id'] = volume_ref['id']
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_resume(self):
        """Make sure resume's rpc  message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='resume')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        self.compute_api.resume(self.context, ref[0]['id'])

        self.assertTrue(FLAGS.tests_compute_api_result)
        # verify rpc message parameters
        inparam = dict()
        inparam['instance_id'] = ref[0]['id']
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_suspend(self):
        """Make sure suspend's rpc message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='suspend')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        self.compute_api.suspend(self.context, ref[0]['id'])

        self.assertTrue(FLAGS.tests_compute_api_result)
        # verify rpc message parameters
        inparam = dict()
        inparam['instance_id'] = ref[0]['id']
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_rescue(self):
        """Make sure rescue's rpc message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='rescue')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        inparam = dict()
#        inparam = dict(rescue_password=None) # not exist in diablo
        self.compute_api.rescue(self.context, ref[0]['id'], **inparam)

        self.assertTrue(FLAGS.tests_compute_api_result)

        # verify rpc message parameters
        inparam['instance_id'] = ref[0]['id']
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_unrescue(self):
        """Make sure unrescue's rpc  message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='unrescue')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        self.compute_api.unrescue(self.context, ref[0]['id'])

        self.assertTrue(FLAGS.tests_compute_api_result)

        # verify rpc message parameters
        inparam = dict()
        inparam['instance_id'] = ref[0]['id']
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_pause(self):
        """Make sure pause's rpc message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='pause')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        self.compute_api.pause(self.context, ref[0]['id'])

        self.assertTrue(FLAGS.tests_compute_api_result)
        # verify rpc message parameters
        inparam = dict()
        inparam['instance_id'] = ref[0]['id']
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_unpause(self):
        """Make sure unpause's rpc message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='unpause')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        self.compute_api.unpause(self.context, ref[0]['id'])

        self.assertTrue(FLAGS.tests_compute_api_result)
        # verify rpc message parameters
        inparam = dict()
        inparam['instance_id'] = ref[0]['id']
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_trigger_provider_fw_rules_refresh(self):
        """Make sure trigger_provider_fw_rules_refresh's rpc message """
        self._create_group()
        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None,
                security_group=['testgroup'])

        self.compute_api.update(self.context,
                    ref[0]['id'], host=FLAGS.host, vcpus=1)

        db.service_create(context.get_admin_context(),
                          dict(host=ref[0]['host'], topic='compute'))

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='trigger_provider_fw_rules_refresh')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        self.compute_api.trigger_provider_fw_rules_refresh(
                context.get_admin_context())

        self.assertTrue(FLAGS.tests_compute_api_result)
        # verify rpc message parameters
        self.assertEqual({}, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_trigger_security_group_members_refresh(self):
        """Make sure trigger_security_group_members_refresh's rpc message """
        group = self._create_group()

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None,
                security_group=['testgroup'])

        self.compute_api.update(self.context, ref[0]['id'], host=FLAGS.host)

        db.security_group_rule_create(context.get_admin_context(), dict(
                    group_id=group['id'],
                    parent_group_id=group['id']))

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(
            tests_compute_api_name='trigger_security_group_members_refresh')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        self.compute_api.trigger_security_group_members_refresh(
                self.context, [group['id']])

        self.assertTrue(FLAGS.tests_compute_api_result)
        # verify rpc message parameters
        inparam = dict()
        inparam['security_group_id'] = group['id']
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_trigger_security_group_rules_refresh(self):
        """Make sure trigger_security_group_rules_refresh's rpc message """
        group = self._create_group()

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None,
                security_group=['testgroup'])

        self.compute_api.update(self.context,
                    ref[0]['id'],
                    host=FLAGS.host)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(
            tests_compute_api_name='trigger_security_group_rules_refresh')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        self.compute_api.trigger_security_group_rules_refresh(
                self.context, group['id'])

        self.assertTrue(FLAGS.tests_compute_api_result)
        # verify rpc message parameters
        inparam = dict()
        inparam['security_group_id'] = group['id']
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_get_vnc_console(self):
        """Make sure get_vnc_console's rpc message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='get_vnc_console')
        self.stubs.Set(rpc, 'call', self._fake_cast)

        self.compute_api.get_vnc_console(
                self.context, ref[0]['id'])

        self.assertTrue(FLAGS.tests_compute_api_result)
        # verify rpc message parameters
        inparam = dict(token='t1', host='h1', port='p1')
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_get_ajax_console(self):
        """Make sure get_ajax_console's rpc message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='get_ajax_console')
        self.stubs.Set(rpc, 'call', self._fake_cast)
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        self.compute_api.get_ajax_console(
                self.context, ref[0]['id'])

        self.assertTrue(FLAGS.tests_compute_api_result)
        # verify rpc message parameters
        inparam = dict(token='t1', host='h1', port='p1')
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_get_console_output(self):
        """Make sure get_console_output's rpc message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='get_console_output')
        self.stubs.Set(rpc, 'call', self._fake_cast)

        self.compute_api.get_console_output(
                self.context, ref[0]['id'])

        self.assertTrue(FLAGS.tests_compute_api_result)
        # verify rpc message parameters
        inparam = dict(instance_id=ref[0]['id'])
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_associate_floating_ip_exception_noips(self):
        """Make sure associate_floating_ip failure when no ips exist """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='associate_floating_ip')
        self.stubs.Set(rpc, 'call', self._fake_cast)

        self.assertRaises(exception.ApiError,
                self.compute_api.associate_floating_ip,
                self.context, ref[0]['id'], address='192.168.1.1')

        self.assertTrue(FLAGS.tests_compute_api_result)

    @attr(kind='small')
    def test_has_finished_migration(self):
        """Make sure instance's migration status """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        # not finished
        db.migration_create(context.get_admin_context(),
            {'instance_uuid': ref[0]['uuid'],
             'source_compute': ref[0]['host'],
             'dest_compute': FLAGS.host,
             'old_instance_type_id': ref[0]['instance_type_id'],
             'new_instance_type_id': ref[0]['instance_type_id'],
             'status': 'migrating'})

        self.assertTrue(not self.compute_api.has_finished_migration(
                context.get_admin_context(), ref[0]['uuid']))

        # finished
        db.migration_create(context.get_admin_context(),
            {'instance_uuid': ref[0]['uuid'],
             'source_compute': ref[0]['host'],
             'dest_compute': FLAGS.host,
             'old_instance_type_id': ref[0]['instance_type_id'],
             'new_instance_type_id': ref[0]['instance_type_id'],
             'status': 'finished'})
        # instance id is not correct
        self.assertTrue(not self.compute_api.has_finished_migration(
                context.get_admin_context(), ref[0]['id']))

        # instance uuid is right
        self.assertTrue(self.compute_api.has_finished_migration(
                context.get_admin_context(), ref[0]['uuid']))

    @attr(kind='small')
    def test_set_admin_password_exception_nohost(self):
        """Make sure set_admin_password raise Error when host not found"""

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(find_host_timeout=3)
        # instance['host'] not setting
        self.assertRaises(exception.Error,
                self.compute_api.set_admin_password,
                self.context, ref[0]['id'], password='')

    @attr(kind='small')
    def test_add_network_to_project(self):
        """Make sure add_network_to_project's rpc message """

        self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        pref = db.project_create(self.context,
                dict(id=self.project_id, name='test_project'))

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='add_network_to_project')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        self.compute_api.add_network_to_project(self.context, pref['id'])

        self.assertTrue(FLAGS.tests_compute_api_result)
        # verify rpc message parameters
        inparam = dict(project_id=pref['id'])
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_add_network_to_project_exception_notexist(self):
        """Make sure add_network_to_project raising Exception when not found"""

        self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.assertRaises(exception.ProjectNotFound,
            self.compute_api.add_network_to_project, self.context, '12')

    @attr(kind='small')
    def test_set_host_enabled(self):
        """Make sure set_host_enabled's rpc message """

        self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='set_host_enabled')
        self.stubs.Set(rpc, 'call', self._fake_cast)

        inparam = dict(enabled='enabled')
        self.compute_api.set_host_enabled(
                self.context, host=None, **inparam)

        self.assertTrue(FLAGS.tests_compute_api_result)
        # verify rpc message parameters
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_host_power_action(self):
        """Make sure host_power_action's rpc message """

        self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='host_power_action')
        self.stubs.Set(rpc, 'call', self._fake_cast)

        inparam = dict(action='any')
        self.compute_api.host_power_action(
                self.context, host=None, **inparam)

        self.assertTrue(FLAGS.tests_compute_api_result)
        # verify rpc message parameters
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_get_all_parameter_recurse_zones(self):
        """Test searching instances by recurse_zones"""

        def _fake_call_zone_method(context, method_name,
                                   errors_to_ignore=None,
                     novaclient_collection_name='zones', zones=None,
                     *args, **kwargs):

            class FakeClientServer(object):
                def __init__(self):
                    self._info = models.Instance()

            return dict(zone1=[FakeClientServer()]).iteritems()

        self.stubs.Set(scheduler_api, 'call_zone_method',
                       _fake_call_zone_method)

        c = context.get_admin_context()
        instance_id1 = self._create_instance({'display_name': 'aabbcc'})

        instances = self.compute_api.get_all(c,
                search_opts={'name': 'aab.*', 'recurse_zones': True})

        self.assertEqual(2, len(instances))

        db.instance_destroy(c, instance_id1)

    @attr(kind='small')
    def test_lock(self):
        """Make sure lock's rpc message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='lock')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        self.compute_api.lock(self.context, ref[0]['id'])

        self.assertTrue(FLAGS.tests_compute_api_result)
        # verify rpc message parameters
        inparam = dict(instance_id=ref[0]['id'])
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_unlock(self):
        """Make sure unlock's rpc message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='unlock')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        self.compute_api.unlock(self.context, ref[0]['id'])

        self.assertTrue(FLAGS.tests_compute_api_result)
        # verify rpc message parameters
        inparam = dict(instance_id=ref[0]['id'])
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_get_lock_database(self):
        """Make sure lock state be setted"""

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        lock = self.compute_api.get_lock(self.context, ref[0]['id'])
        self.assertTrue(not lock)

        self.compute_api.update(self.context,
            ref[0]['id'],
            locked=True)

        lock = self.compute_api.get_lock(self.context, ref[0]['id'])
        self.assertTrue(lock)

    @attr(kind='small')
    def test_reset_network(self):
        """Make sure reset_network's rpc message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='reset_network')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        self.compute_api.reset_network(self.context, ref[0]['id'])

        self.assertTrue(FLAGS.tests_compute_api_result)
        # verify rpc message parameters
        inparam = dict(instance_id=ref[0]['id'])
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_inject_network_info(self):
        """Make sure inject_network_info's rpc message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='inject_network_info')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        self.compute_api.inject_network_info(self.context, ref[0]['id'])

        self.assertTrue(FLAGS.tests_compute_api_result)
        # verify rpc message parameters
        inparam = dict(instance_id=ref[0]['id'])
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_inject_file_exception(self):
        """Make sure inject_file raise exception when be lock state """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='inject_file')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        # lock state
        self.compute_api.update(self.context, ref[0]['id'], locked=True)

        # be lock state and not be admin
        self.assertRaises(exception.ApiError,
            self.compute_api.inject_file,
                self.context, ref[0]['id'])

    @attr(kind='small')
    def test_get_diagnostics(self):
        """Make sure get_diagnostics's rpc message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='get_diagnostics')
        self.stubs.Set(rpc, 'call', self._fake_cast)

        diag = self.compute_api.get_diagnostics(self.context, ref[0]['id'])

        self.assertTrue(FLAGS.tests_compute_api_result)
        self.assertTrue(not diag['Unable to retrieve diagnostics'])
        # verify rpc message parameters
        inparam = dict(instance_id=ref[0]['id'])
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_get_actions_database(self):
        """Make sure instance'action be searched """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        action = dict(action='test_action', error=None,
                      instance_id=ref[0]['id'])

        action_ref = self.compute_api.get_actions(
                            context.get_admin_context(), ref[0]['id'])
        self.assertTrue(not action_ref)

        db.instance_action_create(context.get_admin_context(),
                        action)
        action_ref = self.compute_api.get_actions(
                            context.get_admin_context(), ref[0]['id'])
        self.assertTrue(action_ref)
        self.assertEqual('test_action', action_ref[0]['action'])

    @attr(kind='small')
    def test_add_fixed_ip(self):
        """Make sure add_fixed_ip's rpc message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='add_fixed_ip')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        inparam = dict(instance_id=ref[0]['id'], network_id='11')
        self.compute_api.add_fixed_ip(self.context, **inparam)

        self.assertTrue(FLAGS.tests_compute_api_result)
        # verify rpc message parameters
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_remove_fixed_ip(self):
        """Make sure remove_fixed_ip's rpc message """

        ref = self.compute_api.create(
                self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.flags(tests_compute_api_result=False,
                   tests_compute_api_rpc_args={})
        self.flags(tests_compute_api_name='remove_fixed_ip')
        self.stubs.Set(rpc, 'cast', self._fake_cast)

        inparam = dict(instance_id=ref[0]['id'], address='11')
        self.compute_api.remove_fixed_ip(self.context, **inparam)

        self.assertTrue(FLAGS.tests_compute_api_result)
        # verify rpc message parameters
        self.assertSubDictMatch(inparam, FLAGS.tests_compute_api_rpc_args)

    @attr(kind='small')
    def test_get_active_by_window_database(self):
        """Make sure get_active_by_window's db state """

        pref = db.project_create(self.context,
                dict(id=self.project_id, name='test_project'))

        ref = self.compute_api.create(self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None)

        self.compute_api.update(self.context,
            ref[0]['id'], project_id=pref['id'], launched_at=utils.utcnow())

        start = datetime.strptime('2050-09-01', "%Y-%m-%d")
        instances = self.compute_api.get_active_by_window(
            self.context, begin=start, end=None, project_id=pref['id'])
        self.assertEqual(1, len(instances))

    @attr(kind='small')
    def test_get_instance_type_exception(self):
        """Make sure get_instance_type throwing exception when not found """

        types = self.compute_api.get_instance_type(
            self.context, '1')
        self.assertEqual(1, types['id'])

        self.assertRaises(exception.InstanceTypeNotFound,
                          self.compute_api.get_instance_type,
                                self.context, 'id')

    @attr(kind='small')
    def test_get_database(self):
        """Make sure instance be searched by id"""

        ref = self.compute_api.create(self.context,
                instance_type=instance_types.get_default_instance_type(),
                image_href=None, display_name='test123')

        instance = self.compute_api.get(
            self.context, instance_id=ref[0]['id'])
        self.assertEqual('test123', instance['display_name'])

        instance = self.compute_api.get(
            self.context, instance_id=ref[0]['uuid'])
        self.assertEqual('test123', instance['display_name'])

        self.assertRaises(exception.InstanceNotFound,
            self.compute_api.get,
                self.context,
                instance_id='cc8f830b-49ef-4ac8-bfc6-05b26c73f6c4xxx')

    @attr(kind='small')
    def test_routing_get_exception(self):
        """Make sure instance be searched by uuid under child zones"""

        self.assertRaises(exception.InstanceNotFound,
            self.compute_api.routing_get,
                self.context,
                instance_id='cc8f830b-49ef-4ac8-bfc6-05b26c73f6c4')

    def _fake_cast(self, context, topic, msg):
        """ fake function for rpc.cast and rpc.call
            if topic and method be not in mapping tables,
            then set return flag to False.
        """
        self.flags(tests_compute_api_result=True)
        self.flags(tests_compute_api_rpc_args=msg['args'])
        _api_compute_message = {
            'backup': 'snapshot_instance',
            'snapshot': 'snapshot_instance',
            'revert_resize': 'revert_resize',
            'confirm_resize': 'confirm_resize',
            'attach_volume': 'attach_volume',
            'detach_volume': 'detach_volume',
            'resume': 'resume_instance',
            'suspend': 'suspend_instance',
            'rescue': 'rescue_instance',
            'unrescue': 'unrescue_instance',
            'unpause': 'unpause_instance',
            'pause': 'pause_instance',
            'trigger_provider_fw_rules_refresh': 'refresh_provider_fw_rules',
            'trigger_security_group_members_refresh':
                'refresh_security_group_members',
            'trigger_security_group_rules_refresh':
                'refresh_security_group_rules',
            'get_vnc_console': 'get_vnc_console',
            'get_ajax_console': 'get_ajax_console',
            'get_console_output': 'get_console_output',
            'set_host_enabled': 'set_host_enabled',
            'host_power_action': 'host_power_action',
            'rebuild': 'rebuild_instance',
            'get_diagnostics': 'get_diagnostics',
            'lock': 'lock_instance',
            'unlock': 'unlock_instance',
            'reset_network': 'reset_network',
            'inject_network_info': 'inject_network_info',
            'inject_file': 'inject_file',
            'add_fixed_ip': 'add_fixed_ip_to_instance',
            'remove_fixed_ip': 'remove_fixed_ip_from_instance',
            'remove_security_group': 'refresh_security_group_rules',
            'add_security_group': 'refresh_security_group_rules'}

        _api_scheduler_message = {
                    'resize': 'prep_resize',
                    'create_all_at_once': 'run_instance',
                    'create': 'run_instance'}

        _api_ajax_message = {
                    'get_ajax_console': 'authorize_ajax_console'}
        _api_vnc_message = {
                    'get_vnc_console': 'authorize_vnc_console'}

        _api_network_message = {
                    'associate_floating_ip': 'get_instance_nw_info',
                    'add_network_to_project': 'add_network_to_project',
                    'create_all_at_once': 'validate_networks',
                    'create': 'validate_networks'}

        mapping = {'compute': _api_compute_message,
                   'scheduler': _api_scheduler_message,
                   'ajax_proxy': _api_ajax_message,
                   'vncproxy': _api_vnc_message,
                   'network': _api_network_message}

        api = FLAGS.tests_compute_api_name
        top = topic.split('.')[0]

        if mapping[top][api] != msg['method']:
            # if topic and method is dismatching, then return false
            self.flags(tests_compute_api_result=False)

        if msg['method'].endswith('_console'):
            return dict(token='t1', host='h1', port='p1')

        if msg['method'].endswith('nw_info'):
            network_dict = {
                'bridge': '',
                'id': ''}
            info = {
                'label': '',
                'gateway': '',
                'dns': [],
                'ips': []}
            return [(network_dict, info)]

        if msg['method'].endswith('get_diagnostics'):
            return {"Unable to retrieve diagnostics": False}
