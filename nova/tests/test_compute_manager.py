# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 NTT
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
"""
Tests For Compute
"""
from nose.plugins.attrib import attr
import socket
import sys
import time
import os
import datetime

from nova import compute
from nova.compute import instance_types
from nova.compute import manager as compute_manager
from nova.compute import power_state
from nova.compute import vm_states
from nova import context
from nova import db
from nova.db.sqlalchemy import models
from nova.db.sqlalchemy import api as sqlalchemy_api
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
from nova import block_device
#from nova.tests import fake_network

LOG = logging.getLogger('nova.tests.compute')
FLAGS = flags.FLAGS
flags.DECLARE('stub_network', 'nova.compute.manager')
flags.DECLARE('live_migration_retry_count', 'nova.compute.manager')


class FakeTime(object):
    def __init__(self):
        self.counter = 0

    def sleep(self, t):
        self.counter += t


def nop_report_driver_status(self):
    pass


class ComputeTestCase(test.TestCase):
    """Test case for compute"""
    def setUp(self):
        super(ComputeTestCase, self).setUp()
        self.flags(connection_type='fake',
                   stub_network=True,
                   notification_driver='nova.notifier.test_notifier',
                   network_manager='nova.network.manager.FlatManager')
        self.compute = utils.import_object(FLAGS.compute_manager)
        self.compute_api = compute.API()
        self.volume = utils.import_object(FLAGS.volume_manager)
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

    def _get_dummy_instance(self):
        """Get mock-return-value instance object
           Use this when any testcase executed later than test_run_terminate
        """
        vol1 = models.Volume()
        vol1['id'] = 1
        vol2 = models.Volume()
        vol2['id'] = 2
        instance_ref = models.Instance()
        instance_ref['id'] = 1
        instance_ref['volumes'] = [vol1, vol2]
        instance_ref['hostname'] = 'hostname-1'
        instance_ref['host'] = 'dummy'
        return instance_ref

    def _create_volume(self, size='0', snapshot_id=None):
        """Create a volume object."""
        vol = {}
        vol['size'] = size
        vol['snapshot_id'] = snapshot_id
        vol['user_id'] = self.user_id
        vol['project_id'] = self.project_id
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        return db.volume_create(context.get_admin_context(), vol)['id']

    def test_create_instance_with_img_ref_associates_config_drive(self):
        """Make sure create associates a config drive."""

        instance_id = self._create_instance(params={'config_drive': '1234', })

        try:
            self.compute.run_instance(self.context, instance_id)
            instances = db.instance_get_all(context.get_admin_context())
            instance = instances[0]

            self.assertTrue(instance.config_drive)
        finally:
            db.instance_destroy(self.context, instance_id)

    def test_create_instance_associates_config_drive(self):
        """Make sure create associates a config drive."""

        instance_id = self._create_instance(params={'config_drive': True, })

        try:
            self.compute.run_instance(self.context, instance_id)
            instances = db.instance_get_all(context.get_admin_context())
            instance = instances[0]

            self.assertTrue(instance.config_drive)
        finally:
            db.instance_destroy(self.context, instance_id)

    def test_run_terminate(self):
        """Make sure it is possible to  run and terminate instance"""
        instance_id = self._create_instance()

        self.compute.run_instance(self.context, instance_id)

        instances = db.instance_get_all(context.get_admin_context())
        LOG.info(_("Running instances: %s"), instances)
        self.assertEqual(len(instances), 1)

        self.compute.terminate_instance(self.context, instance_id)

        instances = db.instance_get_all(context.get_admin_context())
        LOG.info(_("After terminating instances: %s"), instances)
        self.assertEqual(len(instances), 0)

    def test_run_terminate_timestamps(self):
        """Make sure timestamps are set for launched and destroyed"""
        instance_id = self._create_instance()
        instance_ref = db.instance_get(self.context, instance_id)
        self.assertEqual(instance_ref['launched_at'], None)
        self.assertEqual(instance_ref['deleted_at'], None)
        launch = utils.utcnow()
        self.compute.run_instance(self.context, instance_id)
        instance_ref = db.instance_get(self.context, instance_id)
        self.assert_(instance_ref['launched_at'] > launch)
        self.assertEqual(instance_ref['deleted_at'], None)
        terminate = utils.utcnow()
        self.compute.terminate_instance(self.context, instance_id)
        self.context = self.context.elevated(True)
        instance_ref = db.instance_get(self.context, instance_id)
        self.assert_(instance_ref['launched_at'] < terminate)
        self.assert_(instance_ref['deleted_at'] > terminate)

    @attr(kind='small')
    def test_stop(self):
        """Ensure instance can be stopped"""
        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        instance = db.instance_get(self.context, instance_id)
        self.assertEquals(vm_states.ACTIVE, instance['vm_state'])

        self.compute.stop_instance(self.context, instance_id)

        instance = db.instance_get(self.context, instance_id)
        self.assertEquals(vm_states.STOPPED, instance['vm_state'])

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_start(self):
        """Ensure instance can be started"""
        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        self.compute.stop_instance(self.context, instance_id)

        instance = db.instance_get(self.context, instance_id)
        self.assertEquals(vm_states.STOPPED, instance['vm_state'])

        self.compute.start_instance(self.context, instance_id)

        instance = db.instance_get(self.context, instance_id)
        self.assertEquals(vm_states.ACTIVE, instance['vm_state'])

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_pause(self):
        """Ensure instance can be paused"""
        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        instance = db.instance_get(self.context, instance_id)
        self.assertEquals(vm_states.ACTIVE, instance['vm_state'])

        self.compute.pause_instance(self.context, instance_id)

        instance = db.instance_get(self.context, instance_id)
        self.assertEquals(vm_states.PAUSED, instance['vm_state'])

        self.compute.unpause_instance(self.context, instance_id)

        instance = db.instance_get(self.context, instance_id)
        self.assertEquals(vm_states.ACTIVE, instance['vm_state'])

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_suspend(self):
        """ensure instance can be suspended"""
        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        instance = db.instance_get(self.context, instance_id)
        self.assertEquals(vm_states.ACTIVE, instance['vm_state'])

        self.compute.suspend_instance(self.context, instance_id)

        instance = db.instance_get(self.context, instance_id)
        self.assertEquals(vm_states.SUSPENDED, instance['vm_state'])

        self.compute.resume_instance(self.context, instance_id)

        instance = db.instance_get(self.context, instance_id)
        self.assertEquals(vm_states.ACTIVE, instance['vm_state'])

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_reboot(self):
        """Ensure instance can be rebooted"""
        self.instance_id = None
        self.network_info = None

        def stub_driver_reboot(instance_ref, network_info):
            self.instance_id = instance_ref['id']
            self.network_info = network_info

        self.stubs.Set(self.compute.driver, 'reboot', stub_driver_reboot)
        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        self.assertEquals(None, self.instance_id)
        self.assertEquals(None, self.network_info)
        self.compute.reboot_instance(self.context, instance_id)
        self.assertEquals(instance_id, self.instance_id)
        self.assertEquals([], self.network_info)

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_set_admin_password(self):
        """Ensure instance can have its admin password set"""
        self.new_pass = None

        def stub_driver_set_admin_password(instance, new_pass):
            self.new_pass = new_pass

        self.stubs.Set(self.compute.driver, 'set_admin_password',
                       stub_driver_set_admin_password)

        instance_id = self._create_instance()

        self.compute.run_instance(self.context, instance_id)

        self.assertEquals(None, self.new_pass)
        self.compute.set_admin_password(self.context, instance_id)
        self.assertNotEquals(None, self.new_pass)

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_inject_file(self):
        """Ensure we can write a file to an instance"""
        self.instance_id = None
        self.path = None
        self.file_contents = None

        def stub_driver_inject_file(instance_ref, path, file_contents):
            self.instance_id = instance_ref['id']
            self.path = path
            self.file_contents = file_contents

        self.stubs.Set(self.compute.driver, 'inject_file',
                       stub_driver_inject_file)

        instance_id = self._create_instance()
        path = "/tmp/test"
        file_contents = "File Contents"
        self.compute.run_instance(self.context, instance_id)

        self.assertEquals(None, self.instance_id)
        self.assertEquals(None, self.path)
        self.assertEquals(None, self.file_contents)
        self.compute.inject_file(self.context, instance_id, path,
                                 file_contents)
        self.assertEquals(instance_id, self.instance_id)
        self.assertEquals(path, self.path)
        self.assertEquals(file_contents, self.file_contents)

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_agent_update(self):
        """Ensure instance can have its agent updated"""
        self.instance_id = None
        self.url = None
        self.md5hash = None

        def stub_driver_agent_update(instance_ref, url, md5hash):
            self.instance_id = instance_ref['id']
            self.url = url
            self.md5hash = md5hash

        self.stubs.Set(self.compute.driver, 'agent_update',
                       stub_driver_agent_update)

        instance_id = self._create_instance()
        url = 'http://127.0.0.1/agent'
        md5hash = '00112233445566778899aabbccddeeff'

        self.compute.run_instance(self.context, instance_id)

        self.assertEquals(None, self.instance_id)
        self.assertEquals(None, self.url)
        self.assertEquals(None, self.md5hash)
        self.compute.agent_update(self.context, instance_id, url, md5hash)
        self.assertEquals(instance_id, self.instance_id)
        self.assertEquals(url, self.url)
        self.assertEquals(md5hash, self.md5hash)

        self.compute.terminate_instance(self.context, instance_id)

    def test_snapshot(self):
        """Ensure instance can be snapshotted"""
        self.image_id = None

        def stub_driver_snapshot(context, instance_ref, image_id):
            self.image_id = image_id

        self.stubs.Set(self.compute.driver, 'snapshot', stub_driver_snapshot)

        instance_id = self._create_instance()
        name = "myfakesnapshot"
        self.compute.run_instance(self.context, instance_id)

        self.assertEquals(None, self.image_id)
        self.compute.snapshot_instance(self.context, instance_id, name)
        self.assertEquals(name, self.image_id)

        self.compute.terminate_instance(self.context, instance_id)

    def test_console_output(self):
        """Make sure we can get console output from instance"""
        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        console = self.compute.get_console_output(self.context,
                                                        instance_id)
        self.assert_(console)
        self.compute.terminate_instance(self.context, instance_id)

    def test_ajax_console(self):
        """Make sure we can get console output from instance"""
        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        console = self.compute.get_ajax_console(self.context,
                                                instance_id)
        self.assert_(set(['token', 'host', 'port']).issubset(console.keys()))
        self.compute.terminate_instance(self.context, instance_id)

    def test_vnc_console(self):
        """Make sure we can a vnc console for an instance."""
        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        console = self.compute.get_vnc_console(self.context,
                                               instance_id)
        self.assert_(console)
        self.compute.terminate_instance(self.context, instance_id)

    def test_run_instance_usage_notification(self):
        """Ensure run instance generates apropriate usage notification"""
        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)
        self.assertEquals(len(test_notifier.NOTIFICATIONS), 1)
        msg = test_notifier.NOTIFICATIONS[0]
        self.assertEquals(msg['priority'], 'INFO')
        self.assertEquals(msg['event_type'], 'compute.instance.create')
        payload = msg['payload']
        self.assertEquals(payload['project_id'], self.project_id)
        self.assertEquals(payload['user_id'], self.user_id)
        self.assertEquals(payload['instance_id'], instance_id)
        self.assertEquals(payload['instance_type'], 'm1.tiny')
        type_id = instance_types.get_instance_type_by_name('m1.tiny')['id']
        self.assertEquals(str(payload['instance_type_id']), str(type_id))
        self.assertTrue('display_name' in payload)
        self.assertTrue('created_at' in payload)
        self.assertTrue('launched_at' in payload)
        self.assertEquals(payload['image_ref'], '1')
        self.compute.terminate_instance(self.context, instance_id)

    def test_terminate_usage_notification(self):
        """Ensure terminate_instance generates
            apropriate usage notification"""
        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)
        test_notifier.NOTIFICATIONS = []
        self.compute.terminate_instance(self.context, instance_id)

        self.assertEquals(len(test_notifier.NOTIFICATIONS), 1)
        msg = test_notifier.NOTIFICATIONS[0]
        self.assertEquals(msg['priority'], 'INFO')
        self.assertEquals(msg['event_type'], 'compute.instance.delete')
        payload = msg['payload']
        self.assertEquals(payload['project_id'], self.project_id)
        self.assertEquals(payload['user_id'], self.user_id)
        self.assertEquals(payload['instance_id'], instance_id)
        self.assertEquals(payload['instance_type'], 'm1.tiny')
        type_id = instance_types.get_instance_type_by_name('m1.tiny')['id']
        self.assertEquals(str(payload['instance_type_id']), str(type_id))
        self.assertTrue('display_name' in payload)
        self.assertTrue('created_at' in payload)
        self.assertTrue('launched_at' in payload)
        self.assertEquals(payload['image_ref'], '1')

    def test_run_instance_existing(self):
        """Ensure failure when running an instance that already exists"""
        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)
        self.assertRaises(exception.Error,
                          self.compute.run_instance,
                          self.context,
                          instance_id)
        self.compute.terminate_instance(self.context, instance_id)

    def test_lock(self):
        """ensure locked instance cannot be changed"""
        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        non_admin_context = context.RequestContext(None, None, False, False)

        # decorator should return False(fail) with locked nonadmin context
        self.compute.lock_instance(self.context, instance_id)
        ret_val = self.compute.reboot_instance(non_admin_context, instance_id)
        self.assertEqual(ret_val, False)

        # decorator should return None(success) with unlocked nonadmin context
        self.compute.unlock_instance(self.context, instance_id)
        ret_val = self.compute.reboot_instance(non_admin_context, instance_id)
        self.assertEqual(ret_val, None)

        self.compute.terminate_instance(self.context, instance_id)

    def test_finish_resize(self):
        """Contrived test to ensure finish_resize doesn't raise anything"""

        def fake(*args, **kwargs):
            pass

        self.stubs.Set(self.compute.driver, 'finish_migration', fake)
        self.stubs.Set(self.compute.network_api, 'get_instance_nw_info', fake)
        context = self.context.elevated()
        instance_id = self._create_instance()
        instance_ref = db.instance_get(context, instance_id)
        self.compute.prep_resize(context, instance_ref['uuid'], 1)
        migration_ref = db.migration_get_by_instance_and_status(context,
                instance_ref['uuid'], 'pre-migrating')
        try:
            self.compute.finish_resize(context, instance_ref['uuid'],
                    int(migration_ref['id']), {})
        except KeyError, e:
            # Only catch key errors. We want other reasons for the test to
            # fail to actually error out so we don't obscure anything
            self.fail()

        self.compute.terminate_instance(self.context, instance_id)

    def test_resize_instance_notification(self):
        """Ensure notifications on instance migrate/resize"""
        instance_id = self._create_instance()
        context = self.context.elevated()
        inst_ref = db.instance_get(context, instance_id)

        self.compute.run_instance(self.context, instance_id)
        test_notifier.NOTIFICATIONS = []

        db.instance_update(self.context, instance_id, {'host': 'foo'})
        self.compute.prep_resize(context, inst_ref['uuid'], 1)
        migration_ref = db.migration_get_by_instance_and_status(context,
                inst_ref['uuid'], 'pre-migrating')

        self.assertEquals(len(test_notifier.NOTIFICATIONS), 1)
        msg = test_notifier.NOTIFICATIONS[0]
        self.assertEquals(msg['priority'], 'INFO')
        self.assertEquals(msg['event_type'], 'compute.instance.resize.prep')
        payload = msg['payload']
        self.assertEquals(payload['project_id'], self.project_id)
        self.assertEquals(payload['user_id'], self.user_id)
        self.assertEquals(payload['instance_id'], instance_id)
        self.assertEquals(payload['instance_type'], 'm1.tiny')
        type_id = instance_types.get_instance_type_by_name('m1.tiny')['id']
        self.assertEquals(str(payload['instance_type_id']), str(type_id))
        self.assertTrue('display_name' in payload)
        self.assertTrue('created_at' in payload)
        self.assertTrue('launched_at' in payload)
        self.assertEquals(payload['image_ref'], '1')
        self.compute.terminate_instance(context, instance_id)

    def test_resize_instance(self):
        """Ensure instance can be migrated/resized"""
        instance_id = self._create_instance()
        context = self.context.elevated()
        inst_ref = db.instance_get(context, instance_id)

        self.compute.run_instance(self.context, instance_id)
        db.instance_update(self.context, inst_ref['uuid'],
                           {'host': 'foo'})
        self.compute.prep_resize(context, inst_ref['uuid'], 1)
        migration_ref = db.migration_get_by_instance_and_status(context,
                inst_ref['uuid'], 'pre-migrating')
        self.compute.resize_instance(context, inst_ref['uuid'],
                migration_ref['id'])
        self.compute.terminate_instance(context, instance_id)

    def test_finish_revert_resize(self):
        """Ensure that the flavor is reverted to the original on revert"""
        context = self.context.elevated()
        instance_id = self._create_instance()

        def fake(*args, **kwargs):
            pass

        self.stubs.Set(self.compute.driver, 'finish_migration', fake)
        self.stubs.Set(self.compute.driver, 'revert_migration', fake)
        self.stubs.Set(self.compute.network_api, 'get_instance_nw_info', fake)

        self.compute.run_instance(self.context, instance_id)

        # Confirm the instance size before the resize starts
        inst_ref = db.instance_get(context, instance_id)
        instance_type_ref = db.instance_type_get(context,
                inst_ref['instance_type_id'])
        self.assertEqual(instance_type_ref['flavorid'], 1)

        db.instance_update(self.context, instance_id, {'host': 'foo'})

        new_instance_type_ref = db.instance_type_get_by_flavor_id(context, 3)
        self.compute.prep_resize(context, inst_ref['uuid'],
                                 new_instance_type_ref['id'])

        migration_ref = db.migration_get_by_instance_and_status(context,
                inst_ref['uuid'], 'pre-migrating')

        self.compute.resize_instance(context, inst_ref['uuid'],
                migration_ref['id'])
        self.compute.finish_resize(context, inst_ref['uuid'],
                    int(migration_ref['id']), {})

        # Prove that the instance size is now the new size
        inst_ref = db.instance_get(context, instance_id)
        instance_type_ref = db.instance_type_get(context,
                inst_ref['instance_type_id'])
        self.assertEqual(instance_type_ref['flavorid'], 3)

        # Finally, revert and confirm the old flavor has been applied
        self.compute.revert_resize(context, inst_ref['uuid'],
                migration_ref['id'])
        self.compute.finish_revert_resize(context, inst_ref['uuid'],
                migration_ref['id'])

        inst_ref = db.instance_get(context, instance_id)
        instance_type_ref = db.instance_type_get(context,
                inst_ref['instance_type_id'])
        self.assertEqual(instance_type_ref['flavorid'], 1)

        self.compute.terminate_instance(context, instance_id)

    def test_get_by_flavor_id(self):
        type = instance_types.get_instance_type_by_flavor_id(1)
        self.assertEqual(type['name'], 'm1.tiny')

    @attr(kind='small')
    def test_resize_same_source_fails(self):
        """Ensure instance fails to migrate when source and destination are
        the same host"""
        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)
        inst_ref = db.instance_get(self.context, instance_id)
        self.assertRaises(exception.MigrationError, self.compute.prep_resize,
                self.context, inst_ref['uuid'], 1)
        self.compute.terminate_instance(self.context, instance_id)

    def _setup_other_managers(self):
        self.volume_manager = utils.import_object(FLAGS.volume_manager)
        self.network_manager = utils.import_object(FLAGS.network_manager)
        self.compute_driver = utils.import_object(FLAGS.compute_driver)

    def test_pre_live_migration_instance_has_no_fixed_ip(self):
        """Confirm raising exception if instance doesn't have fixed_ip."""
        instance_ref = self._get_dummy_instance()
        c = context.get_admin_context()
        i_id = instance_ref['id']

        dbmock = self.mox.CreateMock(db)
        dbmock.instance_get(c, i_id).AndReturn(instance_ref)
        dbmock.instance_get_fixed_addresses(c, i_id).AndReturn(None)

        self.compute.db = dbmock
        self.mox.ReplayAll()
        self.assertRaises(exception.NotFound,
                          self.compute.pre_live_migration,
                          c, instance_ref['id'], time=FakeTime())

    def test_pre_live_migration_instance_has_volume(self):
        """Confirm setup_compute_volume is called when volume is mounted."""
        i_ref = self._get_dummy_instance()
        c = context.get_admin_context()

        self._setup_other_managers()
        dbmock = self.mox.CreateMock(db)
        volmock = self.mox.CreateMock(self.volume_manager)
        drivermock = self.mox.CreateMock(self.compute_driver)

        dbmock.instance_get(c, i_ref['id']).AndReturn(i_ref)
        dbmock.instance_get_fixed_addresses(c, i_ref['id']).AndReturn('dummy')
        for i in range(len(i_ref['volumes'])):
            vid = i_ref['volumes'][i]['id']
            volmock.setup_compute_volume(c, vid).InAnyOrder('g1')
        drivermock.plug_vifs(i_ref, [])
        drivermock.ensure_filtering_rules_for_instance(i_ref, [])

        self.compute.db = dbmock
        self.compute.volume_manager = volmock
        self.compute.driver = drivermock

        self.mox.ReplayAll()
        ret = self.compute.pre_live_migration(c, i_ref['id'])
        self.assertEqual(ret, None)

    def test_pre_live_migration_instance_has_no_volume(self):
        """Confirm log meg when instance doesn't mount any volumes."""
        i_ref = self._get_dummy_instance()
        i_ref['volumes'] = []
        c = context.get_admin_context()

        self._setup_other_managers()
        dbmock = self.mox.CreateMock(db)
        drivermock = self.mox.CreateMock(self.compute_driver)

        dbmock.instance_get(c, i_ref['id']).AndReturn(i_ref)
        dbmock.instance_get_fixed_addresses(c, i_ref['id']).AndReturn('dummy')
        self.mox.StubOutWithMock(compute_manager.LOG, 'info')
        compute_manager.LOG.info(_("%s has no volume."), i_ref['hostname'])
        drivermock.plug_vifs(i_ref, [])
        drivermock.ensure_filtering_rules_for_instance(i_ref, [])

        self.compute.db = dbmock
        self.compute.driver = drivermock

        self.mox.ReplayAll()
        ret = self.compute.pre_live_migration(c, i_ref['id'], time=FakeTime())
        self.assertEqual(ret, None)

    def test_pre_live_migration_setup_compute_node_fail(self):
        """Confirm operation setup_compute_network() fails.

        It retries and raise exception when timeout exceeded.

        """

        i_ref = self._get_dummy_instance()
        c = context.get_admin_context()

        self._setup_other_managers()
        dbmock = self.mox.CreateMock(db)
        netmock = self.mox.CreateMock(self.network_manager)
        volmock = self.mox.CreateMock(self.volume_manager)
        drivermock = self.mox.CreateMock(self.compute_driver)

        dbmock.instance_get(c, i_ref['id']).AndReturn(i_ref)
        dbmock.instance_get_fixed_addresses(c, i_ref['id']).AndReturn('dummy')
        for i in range(len(i_ref['volumes'])):
            volmock.setup_compute_volume(c, i_ref['volumes'][i]['id'])
        for i in range(FLAGS.live_migration_retry_count):
            drivermock.plug_vifs(i_ref, []).\
                AndRaise(exception.ProcessExecutionError())

        self.compute.db = dbmock
        self.compute.network_manager = netmock
        self.compute.volume_manager = volmock
        self.compute.driver = drivermock

        self.mox.ReplayAll()
        self.assertRaises(exception.ProcessExecutionError,
                          self.compute.pre_live_migration,
                          c, i_ref['id'], time=FakeTime())

    def test_live_migration_works_correctly_with_volume(self):
        """Confirm check_for_export to confirm volume health check."""
        i_ref = self._get_dummy_instance()
        c = context.get_admin_context()
        topic = db.queue_get_for(c, FLAGS.compute_topic, i_ref['host'])

        dbmock = self.mox.CreateMock(db)
        dbmock.instance_get(c, i_ref['id']).AndReturn(i_ref)
        self.mox.StubOutWithMock(rpc, 'call')
        rpc.call(c, FLAGS.volume_topic, {"method": "check_for_export",
                                         "args": {'instance_id': i_ref['id']}})
        dbmock.queue_get_for(c, FLAGS.compute_topic, i_ref['host']).\
                             AndReturn(topic)
        rpc.call(c, topic, {"method": "pre_live_migration",
                            "args": {'instance_id': i_ref['id'],
                                     'block_migration': False,
                                     'disk': None}})

        self.mox.StubOutWithMock(self.compute.driver, 'live_migration')
        self.compute.driver.live_migration(c, i_ref, i_ref['host'],
                                  self.compute.post_live_migration,
                                  self.compute.rollback_live_migration,
                                  False)

        self.compute.db = dbmock
        self.mox.ReplayAll()
        ret = self.compute.live_migration(c, i_ref['id'], i_ref['host'])
        self.assertEqual(ret, None)

    def test_live_migration_dest_raises_exception(self):
        """Confirm exception when pre_live_migration fails."""
        i_ref = self._get_dummy_instance()
        c = context.get_admin_context()
        topic = db.queue_get_for(c, FLAGS.compute_topic, i_ref['host'])

        dbmock = self.mox.CreateMock(db)
        dbmock.instance_get(c, i_ref['id']).AndReturn(i_ref)
        self.mox.StubOutWithMock(rpc, 'call')
        rpc.call(c, FLAGS.volume_topic, {"method": "check_for_export",
                                         "args": {'instance_id': i_ref['id']}})
        dbmock.queue_get_for(c, FLAGS.compute_topic, i_ref['host']).\
                             AndReturn(topic)
        rpc.call(c, topic, {"method": "pre_live_migration",
                            "args": {'instance_id': i_ref['id'],
                                     'block_migration': False,
                                     'disk': None}}).\
                            AndRaise(rpc.RemoteError('', '', ''))
        dbmock.instance_update(c, i_ref['id'], {'vm_state': vm_states.ACTIVE,
                                                'task_state': None,
                                                'host': i_ref['host']})
        for v in i_ref['volumes']:
            dbmock.volume_update(c, v['id'], {'status': 'in-use'})
            # mock for volume_api.remove_from_compute
            rpc.call(c, topic, {"method": "remove_volume",
                                "args": {'volume_id': v['id']}})

        self.compute.db = dbmock
        self.mox.ReplayAll()
        self.assertRaises(rpc.RemoteError,
                          self.compute.live_migration,
                          c, i_ref['id'], i_ref['host'])

    def test_live_migration_dest_raises_exception_no_volume(self):
        """Same as above test(input pattern is different) """
        i_ref = self._get_dummy_instance()
        i_ref['volumes'] = []
        c = context.get_admin_context()
        topic = db.queue_get_for(c, FLAGS.compute_topic, i_ref['host'])

        dbmock = self.mox.CreateMock(db)
        dbmock.instance_get(c, i_ref['id']).AndReturn(i_ref)
        dbmock.queue_get_for(c, FLAGS.compute_topic, i_ref['host']).\
                             AndReturn(topic)
        self.mox.StubOutWithMock(rpc, 'call')
        rpc.call(c, topic, {"method": "pre_live_migration",
                            "args": {'instance_id': i_ref['id'],
                                     'block_migration': False,
                                     'disk': None}}).\
                            AndRaise(rpc.RemoteError('', '', ''))
        dbmock.instance_update(c, i_ref['id'], {'vm_state': vm_states.ACTIVE,
                                                'task_state': None,
                                                'host': i_ref['host']})

        self.compute.db = dbmock
        self.mox.ReplayAll()
        self.assertRaises(rpc.RemoteError,
                          self.compute.live_migration,
                          c, i_ref['id'], i_ref['host'])

    def test_live_migration_works_correctly_no_volume(self):
        """Confirm live_migration() works as expected correctly."""
        i_ref = self._get_dummy_instance()
        i_ref['volumes'] = []
        c = context.get_admin_context()
        topic = db.queue_get_for(c, FLAGS.compute_topic, i_ref['host'])

        dbmock = self.mox.CreateMock(db)
        dbmock.instance_get(c, i_ref['id']).AndReturn(i_ref)
        self.mox.StubOutWithMock(rpc, 'call')
        dbmock.queue_get_for(c, FLAGS.compute_topic, i_ref['host']).\
                             AndReturn(topic)
        rpc.call(c, topic, {"method": "pre_live_migration",
                            "args": {'instance_id': i_ref['id'],
                                     'block_migration': False,
                                     'disk': None}})
        self.mox.StubOutWithMock(self.compute.driver, 'live_migration')
        self.compute.driver.live_migration(c, i_ref, i_ref['host'],
                                  self.compute.post_live_migration,
                                  self.compute.rollback_live_migration,
                                  False)

        self.compute.db = dbmock
        self.mox.ReplayAll()
        ret = self.compute.live_migration(c, i_ref['id'], i_ref['host'])
        self.assertEqual(ret, None)

    def test_post_live_migration_working_correctly(self):
        """Confirm post_live_migration() works as expected correctly."""
        dest = 'desthost'
        flo_addr = '1.2.1.2'

        # Preparing datas
        c = context.get_admin_context()
        instance_id = self._create_instance()
        i_ref = db.instance_get(c, instance_id)
        db.instance_update(c, i_ref['id'], {'vm_state': vm_states.MIGRATING,
                                            'power_state': power_state.PAUSED})
        v_ref = db.volume_create(c, {'size': 1, 'instance_id': instance_id})
        fix_addr = db.fixed_ip_create(c, {'address': '1.1.1.1',
                                          'instance_id': instance_id})
        fix_ref = db.fixed_ip_get_by_address(c, fix_addr)
        flo_ref = db.floating_ip_create(c, {'address': flo_addr,
                                        'fixed_ip_id': fix_ref['id']})
        # reload is necessary before setting mocks
        i_ref = db.instance_get(c, instance_id)

        # Preparing mocks
        self.mox.StubOutWithMock(self.compute.volume_manager,
                                 'remove_compute_volume')
        for v in i_ref['volumes']:
            self.compute.volume_manager.remove_compute_volume(c, v['id'])
        self.mox.StubOutWithMock(self.compute.driver, 'unfilter_instance')
        self.compute.driver.unfilter_instance(i_ref, [])
        self.mox.StubOutWithMock(rpc, 'call')
        rpc.call(c, db.queue_get_for(c, FLAGS.compute_topic, dest),
            {"method": "post_live_migration_at_destination",
             "args": {'instance_id': i_ref['id'], 'block_migration': False}})

        # executing
        self.mox.ReplayAll()
        ret = self.compute.post_live_migration(c, i_ref, dest)

        # make sure every data is rewritten to dest
        i_ref = db.instance_get(c, i_ref['id'])
        c1 = (i_ref['host'] == dest)
        flo_refs = db.floating_ip_get_all_by_host(c, dest)
        c2 = (len(flo_refs) != 0 and flo_refs[0]['address'] == flo_addr)

        # post operaton
        self.assertTrue(c1 and c2)
        db.instance_destroy(c, instance_id)
        db.volume_destroy(c, v_ref['id'])
        db.floating_ip_destroy(c, flo_addr)

    def test_run_kill_vm(self):
        """Detect when a vm is terminated behind the scenes"""
        self.stubs.Set(compute_manager.ComputeManager,
                '_report_driver_status', nop_report_driver_status)

        instance_id = self._create_instance()

        self.compute.run_instance(self.context, instance_id)

        instances = db.instance_get_all(context.get_admin_context())
        LOG.info(_("Running instances: %s"), instances)
        self.assertEqual(len(instances), 1)

        instance_name = instances[0].name
        self.compute.driver.test_remove_vm(instance_name)

        # Force the compute manager to do its periodic poll
        error_list = self.compute.periodic_tasks(context.get_admin_context())
        self.assertFalse(error_list)

        instances = db.instance_get_all(context.get_admin_context())
        LOG.info(_("After force-killing instances: %s"), instances)
        self.assertEqual(len(instances), 1)
        self.assertEqual(power_state.NOSTATE, instances[0]['power_state'])

    @attr(kind='small')
    def test_init_host_instance_not_running(self):
        """Ensure do nothing when instance not running."""
        instances = db.instance_get_all(context.get_admin_context())
        self.assertEqual(len(instances), 0)
        self.compute.init_host()
        self.assertEqual(len(instances), 0)

    @attr(kind='small')
    def test_init_host_reboot_instance(self):
        """Ensure instance is rebooting"""
        c = context.get_admin_context()
        instance_id = self._create_instance()
        self.compute.run_instance(c, instance_id)

        instance = db.instance_get(c, instance_id)
        db.instance_update(c, instance['id'],
                           {'power_state': power_state.PAUSED})
        instance = db.instance_get(c, instance_id)

        # pre-condition
        FLAGS.start_guests_on_host_boot = True
        self.assertEquals(power_state.PAUSED, instance['power_state'])

        db_state = instance['power_state']
        drv_state = self.compute._get_power_state(c, instance)
        expect_running = db_state == power_state.RUNNING \
                         and drv_state != db_state
        #Conditions for reboot
        self.assert_((expect_running
                      and FLAGS.resume_guests_state_on_host_boot)\
                      or FLAGS.start_guests_on_host_boot)

        self.compute.init_host()

        instance = db.instance_get(c, instance_id)
        # post-condition
        self.assertEquals(power_state.RUNNING, instance['power_state'])

        FLAGS.start_guests_on_host_boot = False
        self.compute.terminate_instance(c, instance_id)

    @attr(kind='small')
    def test_init_host_drv_state_running(self):
        """Ensure instance is not rebooting"""
        self.stub_flag = False

        def stub_driver_ensure_filtering_rules_for_instance(
                                instance_ref, network_info):
            self.stub_flag = True

        self.stubs.Set(self.compute.driver,
                       'ensure_filtering_rules_for_instance',
                       stub_driver_ensure_filtering_rules_for_instance)

        c = context.get_admin_context()
        instance_id = self._create_instance()
        self.compute.run_instance(c, instance_id)

        instance = db.instance_get(c, instance_id)
        db.instance_update(c, instance['id'],
                           {'power_state': power_state.PAUSED})

        # pre-condition
        instance = db.instance_get(c, instance_id)
        self.assertEquals(power_state.PAUSED, instance['power_state'])

        self.compute.init_host()

        # post-condition
        instance = db.instance_get(c, instance_id)
        self.assertEquals(power_state.PAUSED, instance['power_state'])
        self.assertTrue(self.stub_flag)

        self.compute.terminate_instance(c, instance_id)

    @attr(kind='small')
    def test_init_host_drv_state_running_not_implemented(self):
        """Ensure instance is not rebooting and driver
           raise NotImplementedError"""
        self.stub_flag = False

        def stub_driver_ensure_filtering_rules_for_instance(
                                instance_ref, network_info):
            self.stub_flag = True
            raise NotImplementedError

        self.stubs.Set(self.compute.driver,
                       'ensure_filtering_rules_for_instance',
                       stub_driver_ensure_filtering_rules_for_instance)

        c = context.get_admin_context()
        instance_id = self._create_instance()
        self.compute.run_instance(c, instance_id)

        instance = db.instance_get(c, instance_id)
        db.instance_update(c, instance['id'],
                           {'power_state': power_state.PAUSED})

        # pre-condition
        instance = db.instance_get(c, instance_id)
        self.assertEquals(power_state.PAUSED, instance['power_state'])

        self.compute.init_host()

        # post-condition
        instance = db.instance_get(c, instance_id)
        self.assertEquals(power_state.PAUSED, instance['power_state'])
        self.assertTrue(self.stub_flag)

        self.compute.terminate_instance(c, instance_id)

    @attr(kind='small')
    def test_init_host_do_nothing(self):
        """Ensure reboot condition is not aligned"""
        self.stub_flag = False

        def stub_get_power_state(*args, **kwargs):
            self.stub_flag = True
            return 2

        self.stubs.Set(self.compute, '_get_power_state',
                       stub_get_power_state)

        c = context.get_admin_context()
        instance_id = self._create_instance()
        self.compute.run_instance(c, instance_id)

        instance = db.instance_get(c, instance_id)
        db.instance_update(c, instance['id'],
                           {'power_state': power_state.PAUSED})

        instance = db.instance_get(c, instance_id)
        db_state = instance['power_state']
        drv_state = self.compute._get_power_state(c, instance)
        expect_running = db_state == power_state.RUNNING \
                         and drv_state != db_state

        #Conditions for do nothing
        self.assertFalse((expect_running and
                          FLAGS.resume_guests_state_on_host_boot)\
                      or FLAGS.start_guests_on_host_boot)
        self.assertNotEquals(power_state.RUNNING, drv_state)

        self.compute.init_host()

        # post-condition
        instance = db.instance_get(c, instance_id)
        self.assertEquals(power_state.PAUSED, instance['power_state'])
        self.assertTrue(self.stub_flag)

        self.compute.terminate_instance(c, instance_id)

    @attr(kind='small')
    def test_get_console_topic(self):
        """ Ensure get_console_topic returned console_topic.hostname."""
        console_topic = FLAGS.console_topic
        hostname = socket.gethostname()
        self.assertEqual("%s.%s" % (console_topic, hostname),
                         self.compute.get_console_topic(self.context))

    @attr(kind='small')
    def test_get_console_pool_info(self):
        """ Ensure include username, password and address in return value."""
        console_type = None
        console_pool = self.compute.get_console_pool_info(self.context,
                                                          console_type)
        self.assertIn('username', console_pool)
        self.assertIn('password', console_pool)
        self.assertIn('address', console_pool)

    @attr(kind='small')
    def test_refresh_security_group_rules(self):
        """ Ensure call driver.refresh_security_group_rules"""

        def stub_driver_refresh_security_group_rules(security_group_id):
            return security_group_id

        self.stubs.Set(self.compute.driver, 'refresh_security_group_rules',
                       stub_driver_refresh_security_group_rules)

        security_group_id = 1
        rtn = self.compute.refresh_security_group_rules(self.context,
                                                        security_group_id)
        self.assertEquals(security_group_id, rtn)

    @attr(kind='small')
    def test_refresh_security_group_members(self):
        """ Ensure call driver.refresh_security_group_members"""

        def stub_driver_refresh_security_group_members(security_group_id):
            return security_group_id

        self.stubs.Set(self.compute.driver, 'refresh_security_group_members',
                       stub_driver_refresh_security_group_members)

        security_group_id = 1
        rtn = self.compute.refresh_security_group_members(self.context,
                                                          security_group_id)
        self.assertEquals(security_group_id, rtn)

    @attr(kind='small')
    def test_refresh_provider_fw_rules(self):
        """ Ensure call driver.refresh_provider_fw_rules"""
        self.stub_flag = False

        def stub_driver_refresh_provider_fw_rules():
            self.stub_flag = True

        self.stubs.Set(self.compute.driver, 'refresh_provider_fw_rules',
                       stub_driver_refresh_provider_fw_rules)

        self.assertFalse(self.stub_flag)
        self.compute.refresh_provider_fw_rules(self.context)
        self.assertTrue(self.stub_flag)

    @attr(kind='small')
    def test_reset_network(self):
        """ Ensure call driver.reset_network."""
        self.stub_flag = False

        def stub_driver_reset_network(instance):
            self.stub_flag = True

        self.stubs.Set(self.compute.driver, 'reset_network',
                       stub_driver_reset_network)

        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        self.assertFalse(self.stub_flag)
        self.compute.reset_network(self.context, instance_id)
        self.assertTrue(self.stub_flag)

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_inject_network_info(self):
        """ Ensure call driver.inject_network_info."""
        self.stub_flag = False

        def stub_driver_inject_network_info(instance, nw_info):
            self.stub_flag = True

        self.stubs.Set(self.compute.driver, 'inject_network_info',
                       stub_driver_inject_network_info)

        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        self.assertFalse(self.stub_flag)
        self.compute.inject_network_info(self.context, instance_id)
        self.assertTrue(self.stub_flag)

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_get_diagnostics_instance_running(self):
        """ Ensure call driver.get_diagnostics"""
        self.instance_id = None

        def stub_driver_get_diagnostics(instance_ref):
            self.instance_id = instance_ref['id']

        self.stubs.Set(self.compute.driver, 'get_diagnostics',
                       stub_driver_get_diagnostics)

        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        self.assertEquals(None, self.instance_id)
        self.compute.get_diagnostics(self.context, instance_id)
        self.assertEquals(instance_id, self.instance_id)

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_get_diagnostics_when_instance_not_running(self):
        """ Ensure return None when instance is not running."""
        instance_id = self._create_instance()
        instance = db.instance_get(self.context, instance_id)
        self.assertNotEquals(power_state.RUNNING, instance['power_state'])
        self.assertEquals(None,
                          self.compute.get_diagnostics(self.context,
                                                       instance_id))

    @attr(kind='small')
    def test_rebuild_instance(self):
        """Ensure instance is rebuild and running."""

        def stub_get_instance_nw_info(context, instance):
            network_info = []
            return network_info

        self.stubs.Set(self.compute.network_api, 'get_instance_nw_info',
                       stub_get_instance_nw_info)

        c = context.get_admin_context()
        instance_id = self._create_instance()
        self.compute.run_instance(c, instance_id)

        instance = db.instance_get(c, instance_id)
        db.instance_update(c, instance['id'],
                           {'power_state': power_state.PAUSED})
        instance = db.instance_get(c, instance_id)
        # pre-condition
        self.assertEquals(power_state.PAUSED, instance['power_state'])

        self.compute.rebuild_instance(context=c, instance_id=instance_id)

        instance = db.instance_get(c, instance_id)
        # post-condition
        self.assertEquals(power_state.RUNNING, instance['power_state'])

        self.compute.terminate_instance(c, instance_id)

    @attr(kind='small')
    def test_snapshot_instance_when_image_type_is_backup_and_no_rotation(self):
        """ Ensure raise exception(RotationRequiredForBackup)
            when image_type is backup and no rotation
        """
        instance_id = self._create_instance()
        name = "myfakesnapshot"

        self.compute.run_instance(self.context, instance_id)

        # condition
        #  image_type:backup
        #  rotation:None
        self.assertRaises(exception.RotationRequiredForBackup,
                          self.compute.snapshot_instance,
                          self.context, instance_id, name, image_type='backup')
        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_snapshot_instance_when_image_type_is_not_snapshot_and_backup(self):
        """ Ensure raise exception
            when image_type is not snapshot and backup."""
        instance_id = self._create_instance()
        name = "myfakesnapshot"

        self.compute.run_instance(self.context, instance_id)

        # condition
        #  image_type:not snapshot and backup
        self.assertRaises(Exception,
                          self.compute.snapshot_instance,
                          self.context, instance_id, name, image_type='bkup')
        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_snapshot_instance_when_image_type_is_snapshot_and_rotation(self):
        """ Ensure raise exception(ImageRotationNotAllowed)
            when image_type is snapshot and rotation
        """
        instance_id = self._create_instance()
        name = "myfakesnapshot"

        self.compute.run_instance(self.context, instance_id)
        # condition
        #  image_type:snapshot
        #  rotation:not None
        self.assertRaises(exception.ImageRotationNotAllowed,
                          self.compute.snapshot_instance,
                          self.context, instance_id, name, rotation=1)
        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_snapshot_instance_when_instance_is_not_running(self):
        """ Ensure instance can be snapshotted
            and state is changed running."""
        c = context.get_admin_context()
        name = "myfakesnapshot"

        instance_id = self._create_instance()

        self.compute.run_instance(c, instance_id)
        instance_ref = db.instance_get(c, instance_id)
        self.assertEqual(power_state.RUNNING, instance_ref['power_state'])

        db.instance_update(c, instance_ref['id'],
                           {'vm_state': vm_states.MIGRATING,
                           'power_state': power_state.PAUSED})
        # pre-condition
        instance_ref = db.instance_get(c, instance_id)
        self.assertEqual(power_state.PAUSED, instance_ref['power_state'])

        self.compute.snapshot_instance(c, instance_id, name)

        # post-condition
        instance_ref = db.instance_get(c, instance_id)
        self.assertEqual(power_state.RUNNING, instance_ref['power_state'])

        self.compute.terminate_instance(c, instance_id)

    @attr(kind='small')
    def test_snapshot_instance_with_delete_image(self):
        """ Ensure instance can be backuped and old backups are deleted."""
        ComputeTestCase.stub_flag = False

        def stub_get_default_image_service():
            class ImageService():
                def detail(self, context, filters,
                            marker, sort_key, sort_dir):
                    images = [{'id':1}, {'id':2}, {'id':3}]
                    if marker == None:
                        return images
                    else:
                        return None

                def delete(self, context, image_id):
                    ComputeTestCase.stub_flag = True

                def show(self, context, image_id):
                    return {}

            image_service = ImageService()
            return image_service

        self.stubs.Set(nova.image, 'get_default_image_service',
                       stub_get_default_image_service)

        instance_id = self._create_instance()
        name = "myfakesnapshot"
        self.compute.run_instance(self.context, instance_id)

        # condition
        #  image_type:backup
        #  rotation:not None
        #  (stub_get_default_image_service.detail return list > rotaion)
        self.assertFalse(ComputeTestCase.stub_flag)
        self.compute.snapshot_instance(self.context, instance_id, name,
                                       image_type="backup", rotation=2)
        self.assertTrue(ComputeTestCase.stub_flag)

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_snapshot_instance_with_not_delete_image(self):
        """ Ensure instance can be backuped
            and old backups are not deleted."""
        ComputeTestCase.stub_flag = False

        def stub_get_default_image_service():
            class ImageService():
                def detail(self, context, filters,
                           marker, sort_key, sort_dir):
                    images = [{'id':1}, {'id':2}, {'id':3}]
                    if marker == None:
                        return images
                    else:
                        return None

                def delete(self, context, image_id):
                    ComputeTestCase.stub_flag = True

                def show(self, context, image_id):
                    return {}

            image_service = ImageService()
            return image_service

        self.stubs.Set(nova.image, 'get_default_image_service',
                       stub_get_default_image_service)

        instance_id = self._create_instance()
        name = "myfakesnapshot"
        self.compute.run_instance(self.context, instance_id)

        # condition
        #  image_type:backup
        #  rotation:not None
        #  (stub_get_default_image_service.detail return list < rotaion)
        self.assertFalse(ComputeTestCase.stub_flag)
        self.compute.snapshot_instance(self.context, instance_id, name,
                                       image_type="backup", rotation=5)
        self.assertFalse(ComputeTestCase.stub_flag)

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_set_admin_password_with_new_password(self):
        """Ensure admin password is changed to new password"""
        self.new_pass = '000000000000'

        def stub_driver_set_admin_password(instance, new_pass):
            self.new_pass = new_pass

        self.stubs.Set(self.compute.driver, 'set_admin_password',
                       stub_driver_set_admin_password)

        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)
        new_pass = '123456789012'

        self.assertEquals('000000000000', self.new_pass)
        self.compute.set_admin_password(self.context, instance_id, new_pass)
        self.assertEquals('123456789012', self.new_pass)

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_set_admin_password_when_instance_not_runnning(self):
        """Ensure raise exception when instance is not runnning."""
        instance_id = self._create_instance()
        self.assertRaises(exception.InstanceNotRunning,
                          self.compute.set_admin_password,
                          self.context, instance_id)

    @attr(kind='small')
    def test_set_admin_password_when_driver_not_implement(self):
        """Ensure not change password
            when driver raise exception(NotImplementedError)."""
        self.stub_flag = False

        def stub_driver_set_admin_password(instance_ref, new_pass):
            self.stub_flag = True
            raise NotImplementedError

        self.stubs.Set(self.compute.driver, 'set_admin_password',
                       stub_driver_set_admin_password)

        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        self.assertFalse(self.stub_flag)
        self.compute.set_admin_password(self.context, instance_id)
        self.assertTrue(self.stub_flag)

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_set_admin_password_when_driver_raise_exception(self):
        """Ensure retry 10times ,exception to the final."""
        self.stub_pass_cnt = 0

        def stub_driver_set_admin_password(instance_ref, new_pass):
            self.stub_pass_cnt += 1
            raise TypeError

        def stub_sleep(s):
            pass

        self.stubs.Set(self.compute.driver, 'set_admin_password',
                       stub_driver_set_admin_password)
        self.stubs.Set(time, 'sleep', stub_sleep)

        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        self.assertRaises(exception.Error, self.compute.set_admin_password,
                          self.context, instance_id)
        self.assertEquals(10, self.stub_pass_cnt)

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_reboot_instance_when_instance_not_running(self):
        """Ensure instance can be rebooted when instance is not running"""
        c = context.get_admin_context()
        instance_id = self._create_instance()
        self.compute.run_instance(c, instance_id)

        instance = db.instance_get(c, instance_id)
        db.instance_update(c, instance['id'],
                           {'power_state': power_state.PAUSED})

        # pre-condition
        instance_ref = db.instance_get(c, instance_id)
        self.assertEqual(power_state.PAUSED, instance_ref['power_state'])

        self.compute.reboot_instance(c, instance_id)

        # post-condition
        instance_ref = db.instance_get(self.context, instance_id)
        self.assertEqual(power_state.RUNNING, instance_ref['power_state'])

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_init_check_isinstance_raise_import_error(self):
        """Ensure system exit when unable to load the virtualization driver."""

        def fake_exit(code):
            raise ImportError

        def stub_check_isinstance(obj, cls):
            raise ImportError

        self.stubs.Set(sys, 'exit', fake_exit)
        self.stubs.Set(utils, 'check_isinstance', stub_check_isinstance)

        compute_driver = FLAGS.compute_driver
        self.assertRaises(ImportError, compute_manager.ComputeManager,
                          compute_driver)

    @attr(kind='small')
    def test_run_instance_image_is_too_large(self):
        """ Ensure raise exception when size_bytes > allowed_size_bytes"""

        def stub_db_instance_type_get(context, id):
            flavor = {'id': 0,
                      'name': 'fake_flavor',
                      'memory_mb': 2048,
                      'vcpus': 2,
                      'local_gb': 10,
                      'flavor_id': 0,
                      'swap': 0,
                      'rxtx_quota': 0,
                      'rxtx_cap': 3}

            return flavor

        def stub_image_get_image_service(context, image_href):
            class ImageService():
                def show(self, context, image_id):
                    return {'size': 20000000000}

            image_service = ImageService()
            image_id = 999
            return (image_service, image_id)

        self.stubs.Set(nova.image, 'get_image_service',
                       stub_image_get_image_service)
        self.stubs.Set(self.compute.db, 'instance_type_get',
                       stub_db_instance_type_get)

        instance_id = self._create_instance()
        self.assertRaises(exception.ImageTooLarge,
                          self.compute.run_instance,
                          self.context, instance_id)
        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_run_instance_image_is_allowed_size(self):
        """ Ensure instance is running
            when size_bytes <= allowed_size_bytes"""

        def stub_db_instance_type_get(context, id):
            flavor = {'id': 0,
                      'name': 'fake_flavor',
                      'memory_mb': 2048,
                      'vcpus': 2,
                      'local_gb': 10,
                      'flavor_id': 0,
                      'swap': 0,
                      'rxtx_quota': 0,
                      'rxtx_cap': 3}

            return flavor

        def stub_image_get_image_service(context, image_href):
            class ImageService():
                def show(self, context, image_id):
                    return {'size': 1000}

            image_service = ImageService()
            image_id = 999
            return (image_service, image_id)

        self.stubs.Set(nova.image, 'get_image_service',
                       stub_image_get_image_service)
        self.stubs.Set(self.compute.db, 'instance_type_get',
                       stub_db_instance_type_get)

        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        instance_ref = db.instance_get(self.context, instance_id)
        self.assertEqual(power_state.RUNNING, instance_ref['power_state'])

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_run_instance_allowed_size_is_zero(self):
        """ Ensure instance is running when allowed_size_bytes is zero"""

        def stub_db_instance_type_get(context, id):
            flavor = {'id': 0,
                      'name': 'fake_flavor',
                      'memory_mb': 2048,
                      'vcpus': 2,
                      'local_gb': 0,
                      'flavor_id': 0,
                      'swap': 0,
                      'rxtx_quota': 0,
                      'rxtx_cap': 3}

            return flavor

        def stub_image_get_image_service(context, image_href):
            class ImageService():
                def show(self, context, image_id):
                    return {'size': 1000}

            image_service = ImageService()
            image_id = 999
            return (image_service, image_id)

        self.stubs.Set(nova.image, 'get_image_service',
                       stub_image_get_image_service)
        self.stubs.Set(self.compute.db, 'instance_type_get',
                       stub_db_instance_type_get)

        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        instance_ref = db.instance_get(self.context, instance_id)
        self.assertEqual(power_state.RUNNING, instance_ref['power_state'])

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_run_instance_instance_not_found(self):
        """ Ensure raise exception when instance not found"""
        self.stub_cnt = 0

        def stub_usage_from_instance(instance_ref, **kw):
            self.stub_cnt += 1
            if self.stub_cnt == 1:
                raise exception.InstanceNotFound
            else:
                pass

        self.stubs.Set(utils, 'usage_from_instance', stub_usage_from_instance)

        instance_id = self._create_instance()

        self.compute.run_instance(self.context, instance_id)
        self.assertEquals(1, self.stub_cnt)

        self.compute.terminate_instance(self.context, instance_id)
        self.assertEquals(2, self.stub_cnt)

    @attr(kind='small')
    def test_run_instance_stub_network_is_false(self):
        """ Ensure instance is running when stub_network is false."""

        def stub_allocate_for_instance(context, instance, **kwargs):
            network_info = []
            return network_info

        self.stubs.Set(self.compute.network_api, 'allocate_for_instance',
                       stub_allocate_for_instance)

        instance_id = self._create_instance()
        FLAGS.stub_network = False

        self.compute.run_instance(self.context, instance_id)
        instance_ref = db.instance_get(self.context, instance_id)
        self.assertEqual(power_state.RUNNING, instance_ref['power_state'])
        FLAGS.stub_network = True
        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_run_instance_driver_spawn_exception(self):
        """ Ensure instance failed to spawn."""

        def stub_spawn(context, instance, network_info=None,
                        block_device_info=None):
            raise NotImplementedError

        self.stubs.Set(self.compute.driver, 'spawn', stub_spawn)

        instance_id = self._create_instance()

        self.compute.run_instance(self.context, instance_id)

        instance_ref = db.instance_get(self.context, instance_id)
        self.assertNotEqual(power_state.RUNNING, instance_ref['power_state'])
        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_rescue_instance(self):
        """ Ensure instance can be rescued
            and vm state is changed rescued."""
        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        # pre-condition
        instance_ref = db.instance_get(self.context, instance_id)
        self.assertEqual(vm_states.ACTIVE, instance_ref['vm_state'])

        self.compute.rescue_instance(self.context, instance_id)

        # post-condition
        instance_ref = db.instance_get(self.context, instance_id)
        self.assertEqual(vm_states.RESCUED, instance_ref['vm_state'])

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_unrescue_instance(self):
        """ Ensure instance can be unrescued
            and vm state is changed active."""

        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        self.compute.rescue_instance(self.context, instance_id)

        # pre-condition
        instance_ref = db.instance_get(self.context, instance_id)
        self.assertEqual(vm_states.RESCUED, instance_ref['vm_state'])

        self.compute.unrescue_instance(self.context, instance_id)

        # post-condition
        instance_ref = db.instance_get(self.context, instance_id)
        self.assertEqual(vm_states.ACTIVE, instance_ref['vm_state'])

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_confirm_resize(self):
        """ Ensure call driver.destroy"""
        self.stub_flag = False

        def stub_driver_destroy(instance_ref, network_info):
            self.stub_flag = True

        self.stubs.Set(self.compute.driver, 'destroy',
                       stub_driver_destroy)

        c = context.get_admin_context()
        instance_id = self._create_instance()
        inst_ref = db.instance_get(c, instance_id)

        self.compute.run_instance(c, instance_id)
        self.assertEquals(None, inst_ref['host'])
        db.instance_update(c, inst_ref['uuid'], {'host': 'foo'})
        self.compute.prep_resize(c, inst_ref['uuid'], 1)
        migration_ref = db.migration_get_by_instance_and_status(
                                c, inst_ref['uuid'], 'pre-migrating')
        self.compute.resize_instance(c, inst_ref['uuid'],
                                     migration_ref['id'])

        self.compute.confirm_resize(c, instance_id, migration_ref['id'])
        self.assert_(self.stub_flag)

        self.compute.terminate_instance(c, instance_id)

    @attr(kind='small')
    def test_add_fixed_ip_to_instance(self):
        """ Ensure call network.api.add_fixed_ip_to_instance"""
        self.instance_id = None
        self.network_id = None

        def stub_nw_api_add_fixed_ip_to_instance(
                                                 context,
                                                 instance_id, host,
                                                 network_id):
            self.instance_id = instance_id
            self.network_id = network_id

        self.stubs.Set(self.compute.network_api,
                       'add_fixed_ip_to_instance',
                       stub_nw_api_add_fixed_ip_to_instance)

        network_id = 1
        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        self.assertEquals(None, self.instance_id)
        self.assertEquals(None, self.network_id)
        self.compute.add_fixed_ip_to_instance(self.context,
                                              instance_id,
                                              network_id)
        self.assertEquals(instance_id, self.instance_id)
        self.assertEquals(network_id, self.network_id)
        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_remove_fixed_ip_from_instance(self):
        """ Ensure call network.api.remove_fixed_ip_from_instance"""
        self.instance_id = None
        self.address = None

        def stub_nw_api_remove_fixed_ip_from_instance(
                                                      context,
                                                      instance_id,
                                                      address):
            self.instance_id = instance_id
            self.address = address

        self.stubs.Set(self.compute.network_api,
                       'remove_fixed_ip_from_instance',
                       stub_nw_api_remove_fixed_ip_from_instance)

        address = '90:12:34:56:78:90'
        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        self.assertEquals(None, self.instance_id)
        self.assertEquals(None, self.address)
        self.compute.remove_fixed_ip_from_instance(self.context,
                                                   instance_id,
                                                   address)
        self.assertEquals(instance_id, self.instance_id)
        self.assertEquals(address, self.address)

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_host_power_action(self):
        """ Ensure call driver.host_power_action"""
        self.action = None

        def stub_driver_host_power_action(host, action):
            self.action = action

        self.stubs.Set(self.compute.driver, 'host_power_action',
                       stub_driver_host_power_action)

        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        self.assertEquals(None, self.action)
        self.compute.host_power_action(self.context)
        self.assertEquals(None, self.action)

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_host_power_action_with_parameter(self):
        """ Ensure call driver.host_power_action with parameter"""
        self.action = None

        def stub_driver_host_power_action(host, action):
            self.action = action

        self.stubs.Set(self.compute.driver, 'host_power_action',
                       stub_driver_host_power_action)

        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        self.assertEquals(None, self.action)
        self.compute.host_power_action(self.context, action='Reboots')
        self.assertEquals('Reboots', self.action)

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_set_host_enabled(self):
        """ Ensure call driver.set_host_enabled"""
        self.enabled = None

        def stub_driver_set_host_enabled(host, enabled):
            self.enabled = enabled

        self.stubs.Set(self.compute.driver, 'set_host_enabled',
                       stub_driver_set_host_enabled)

        self.assertEquals(None, self.enabled)
        self.compute.set_host_enabled(self.context)
        self.assertEquals(None, self.enabled)

    @attr(kind='small')
    def test_set_host_enabled_with_parameter(self):
        """ Ensure call driver.set_host_enabled with parameter"""
        self.enabled = None

        def stub_driver_set_host_enabled(host, enabled):
            self.enabled = enabled

        self.stubs.Set(self.compute.driver, 'set_host_enabled',
                       stub_driver_set_host_enabled)

        self.assertEquals(None, self.enabled)
        self.compute.set_host_enabled(self.context, enabled=True)
        self.assert_(self.enabled)

    @attr(kind='small')
    def test_attach_and_detach_volume(self):
        """Ensure volume can be attached/detached from instance."""
        c = context.get_admin_context()
        instance_id = self._create_instance()
        mountpoint = "/dev/sdf"
        volume_id = self._create_volume()
        self.volume.create_volume(c, volume_id)

        self.compute.attach_volume(c, instance_id, volume_id, mountpoint)

        vol = db.volume_get(c, volume_id)
        self.assertEqual(vol['status'], "in-use")
        self.assertEqual(vol['attach_status'], "attached")
        self.assertEqual(vol['mountpoint'], mountpoint)
        instance_ref = db.volume_get_instance(c, volume_id)
        self.assertEqual(instance_ref['id'], instance_id)

        self.compute.detach_volume(c, instance_id, volume_id)

        vol = db.volume_get(c, volume_id)
        self.assertEqual(vol['status'], "available")

        self.volume.delete_volume(c, volume_id)
        self.assertRaises(exception.VolumeNotFound,
                          db.volume_get,
                          self.context, volume_id)

    @attr(kind='small')
    def test_attach_volume_raise_exception(self):
        """Ensure raise exception when attach failed."""

        def stub_db_volume_attached(context, volume_id,
                                       instance_id,
                                       mountpoint):
            raise NotImplementedError

        self.stubs.Set(self.compute.db,
                       'volume_attached',
                       stub_db_volume_attached)

        c = context.get_admin_context()
        instance_id = self._create_instance()
        mountpoint = "/dev/sdf"
        volume_id = self._create_volume()
        self.volume.create_volume(c, volume_id)

        self.assertRaises(NotImplementedError,
                          self.compute.attach_volume,
                          c, instance_id, volume_id, mountpoint)

    @attr(kind='small')
    def test_remove_volume(self):
        """ Ensure call volume_manager.remove_compute_volume"""
        self.volume_id = None

        def stub_volume_manager_remove_compute_volume(
                                                      context,
                                                      volume_id):
            self.volume_id = volume_id

        self.stubs.Set(self.compute.volume_manager,
                       'remove_compute_volume',
                       stub_volume_manager_remove_compute_volume)

        c = context.get_admin_context()
        volume_id = self._create_volume()

        self.assertEquals(None, self.volume_id)
        self.compute.remove_volume(c, volume_id)
        self.assertEquals(volume_id, self.volume_id)

    @attr(kind='small')
    def test_compare_cpu(self):
        """ Ensure call driver.compare_cpu"""

        def stub_driver_compare_cpu(cpu_info):
            return cpu_info

        self.stubs.Set(self.compute.driver, 'compare_cpu',
                       stub_driver_compare_cpu)

        cpu_info = '''{ "topology": {
                               "sockets": 1,
                               "cores": 2,
                               "threads": 1 },
                        "features": [
                            "xtpr",
                            "tm2",
                            "est",
                            "vmx",
                            "ds_cpl",
                            "monitor",
                            "pbe",
                            "tm",
                            "ht",
                            "ss",
                            "acpi",
                            "ds",
                            "vme"],
                        "arch": "x86_64",
                        "model": "Penryn",
                        "vendor": "Intel" }'''

        rtn = self.compute.compare_cpu(self.context, cpu_info)
        self.assertEquals(cpu_info, rtn)

    @attr(kind='small')
    def test_create_shared_storage_test_file(self):
        """ Ensure tempfile exist."""
        path = FLAGS.instances_path
        FLAGS.instances_path = '/tmp'
        basename = self.compute.create_shared_storage_test_file(self.context)
        filename = os.path.join(FLAGS.instances_path, basename)
        self.assert_(os.path.exists(filename))
        os.remove(filename)
        FLAGS.instances_path = path

    @attr(kind='small')
    def test_check_shared_storage_test_file(self):
        """ Ensure return true when tempfile exist,
            return false when tempfile not exist"""
        path = FLAGS.instances_path
        FLAGS.instances_path = '/tmp'
        basename = self.compute.create_shared_storage_test_file(self.context)
        filename = os.path.join(FLAGS.instances_path, basename)

        self.assert_(os.path.exists(filename))
        self.assert_(self.compute.check_shared_storage_test_file(
                                            self.context, basename))

        os.remove(filename)
        self.assertFalse(os.path.exists(filename))
        self.assertFalse(self.compute.check_shared_storage_test_file(
                                            self.context, basename))

        FLAGS.instances_path = path

    @attr(kind='small')
    def test_cleanup_shared_storage_test_file(self):
        """ Ensure tempfile not exist."""
        path = FLAGS.instances_path
        FLAGS.instances_path = '/tmp'
        basename = self.compute.create_shared_storage_test_file(self.context)
        filename = os.path.join(FLAGS.instances_path, basename)

        self.assert_(os.path.exists(filename))
        self.compute.cleanup_shared_storage_test_file(self.context, basename)
        self.assertFalse(os.path.exists(filename))

        FLAGS.instances_path = path

    @attr(kind='small')
    def test_update_available_resource(self):
        """ Ensure call driver.update_available_resource"""

        def stub_driver_update_available_resource(context, host):
            return True

        self.stubs.Set(self.compute.driver, 'update_available_resource',
                       stub_driver_update_available_resource)

        self.assert_(self.compute.update_available_resource(self.context))

    @attr(kind='small')
    def test_post_live_migration_at_destination(self):
        """ Ensure call driver.post_live_migration_at_destination"""
        self.instance_id = None

        def stub_driver_post_live_migration_at_destination(context,
                                                       instance_ref,
                                                       network_info,
                                                       block_migration):
            self.instance_id = instance_ref['id']

        self.stubs.Set(self.compute.driver,
                       'post_live_migration_at_destination',
                       stub_driver_post_live_migration_at_destination)

        instance_id = self._create_instance()

        self.assertEquals(None, self.instance_id)
        self.compute.post_live_migration_at_destination(self.context,
                                                        instance_id)
        self.assertEquals(instance_id, self.instance_id)

    @attr(kind='small')
    def test_rollback_live_migration_at_destination(self):
        """ Ensure call driver.destroy"""
        self.instance_id = None

        def stub_driver_destroy(instance_ref, network_info):
            self.instance_id = instance_ref['id']

        self.stubs.Set(self.compute.driver, 'destroy',
                       stub_driver_destroy)

        instance_id = self._create_instance()

        self.assertEquals(None, self.instance_id)
        self.compute.rollback_live_migration_at_destination(self.context,
                                                            instance_id)
        self.assertEquals(instance_id, self.instance_id)

    @attr(kind='small')
    def test_periodic_tasks_update_host_status(self):
        """ Ensure call update_service_capabilities"""
        self.capabilities = {}

        def stub_update_service_capabilities(capabilities):
            self.capabilities = capabilities

        self.stubs.Set(self.compute, 'update_service_capabilities',
                       stub_update_service_capabilities)

        error_list = self.compute.periodic_tasks(context.get_admin_context())
        self.assertFalse(error_list)
        self.assertNotEquals({}, self.capabilities)

    @attr(kind='small')
    def test_periodic_tasks_not_update_host_status(self):
        """ Ensure update_service_capabilities is not called"""
        host_state_interval = FLAGS.host_state_interval
        FLAGS.host_state_interval = 9999999999.00

        self.capabilities = {}

        def stub_update_service_capabilities(capabilities):
            self.capabilities = capabilities

        self.stubs.Set(self.compute, 'update_service_capabilities',
                       stub_update_service_capabilities)

        error_list = self.compute.periodic_tasks(context.get_admin_context())
        self.assertFalse(error_list)
        self.assertEquals({}, self.capabilities)

        FLAGS.host_state_interval = host_state_interval

    @attr(kind='small')
    def test_periodic_tasks_rescue_timeout(self):
        """ Ensure call driver.poll_rescued_instances"""
        self.timeout = 0

        def stub_driver_poll_rescued_instances(timeout):
            self.timeout = timeout

        self.stubs.Set(self.compute.driver, 'poll_rescued_instances',
                       stub_driver_poll_rescued_instances)

        rescue_timeout = FLAGS.rescue_timeout
        FLAGS.rescue_timeout = 1
        error_list = self.compute.periodic_tasks(context.get_admin_context())
        self.assertFalse(error_list)
        self.assertEquals(FLAGS.rescue_timeout, self.timeout)
        FLAGS.rescue_timeout = rescue_timeout

    @attr(kind='small')
    def test_periodic_tasks_return_error_list(self):
        """Ensure error list included 3 errors"""

        def stub_return_exception(*args, **kwargs):
            raise TypeError

        self.stubs.Set(self.compute.driver,
                'poll_rescued_instances', stub_return_exception)

        self.stubs.Set(compute_manager.ComputeManager,
                '_report_driver_status', stub_return_exception)

        self.stubs.Set(compute_manager.ComputeManager,
                '_sync_power_states', stub_return_exception)

        rescue_timeout = FLAGS.rescue_timeout
        FLAGS.rescue_timeout = 1
        error_list = self.compute.periodic_tasks(context.get_admin_context())
        self.assertTrue(error_list)
        self.assertEquals(3, len(error_list))
        FLAGS.rescue_timeout = rescue_timeout

    @attr(kind='small')
    def test_periodic_tasks_when_power_state_not_running(self):
        """ Ensure instance is running when power_state is not running"""
        c = context.get_admin_context()
        instance_id = self._create_instance()

        self.compute.run_instance(c, instance_id)

        instance = db.instance_get(c, instance_id)
        db.instance_update(c, instance['id'],
                           {'power_state': power_state.SUSPENDED})
        instance = db.instance_get(c, instance_id)
        self.assertEquals(power_state.SUSPENDED, instance['power_state'])

        error_list = self.compute.periodic_tasks(c)

        instance = db.instance_get(c, instance_id)
        self.assertEquals(power_state.RUNNING, instance['power_state'])
        self.assertFalse(error_list)

        self.compute.terminate_instance(c, instance_id)

    @attr(kind='small')
    def test_run_instance_setup_volumes(self):
        """ Ensure run instance with setup volumes
                             case1  case2  case3  case4        case5
        ===============================================================
        bdm['no_device']     True   None   None   None         None
        bdm['virtual_name']  None   None   'swap' 'ephemeral0  None
        bdm['snapshot_id']   None   None   None   None         1
        bdm['volume_id']     None   None   None   None         None

        """

        def stub_bdm_get(context, instance_id):
            return [{'volume_id': None,
                     'snapshot_id': None,
                     'no_device': True,
                     'virtual_name': None,
                     'delete_on_termination': True,
                     'volume_size': None,
                     'snapshot': None,
                     'id': 1,
                     'device_name': '/dev/sda'},
                    {'volume_id': None,
                     'snapshot_id': None,
                     'no_device': None,
                     'virtual_name': None,
                     'delete_on_termination': True,
                     'volume_size': None,
                     'snapshot': None,
                     'id': 2,
                     'device_name': '/dev/sdb'},
                    {'volume_id': None,
                     'snapshot_id': None,
                     'no_device': None,
                     'virtual_name': 'swap',
                     'delete_on_termination': True,
                     'volume_size': None,
                     'snapshot': None,
                     'id': 3,
                     'device_name': '/dev/sdc'},
                    {'volume_id': None,
                     'snapshot_id': None,
                     'no_device': None,
                     'virtual_name': 'ephemeral0',
                     'delete_on_termination': True,
                     'volume_size': None,
                     'snapshot': None,
                     'id': 4,
                     'device_name': '/dev/sdd'},
                    {'volume_id': None,
                     'snapshot_id': 1,
                     'no_device': None,
                     'virtual_name': None,
                     'delete_on_termination': True,
                     'volume_size': None,
                     'snapshot': None,
                     'id': 5,
                     'device_name': '/dev/sdd'},
                    ]

        def stub_is_ephemeral(device_name):
            return device_name

        def stub_volume_api_create(*args, **kwargs):
            return {'id': 1}

        def stub_pass(*args, **kwargs):
            pass

        def stub_setup_compute_volume(*args, **kwargs):
            return '/test'

        self.stubs.Set(self.compute.db,
                       'block_device_mapping_get_all_by_instance',
                       stub_bdm_get)
        self.stubs.Set(block_device, 'is_ephemeral', stub_is_ephemeral)
        self.stubs.Set(volume.API, 'create', stub_volume_api_create)
        self.stubs.Set(volume.API, 'wait_creation', stub_pass)
        self.stubs.Set(self.compute.db,
                       'block_device_mapping_update',
                       stub_pass)
        self.stubs.Set(volume.API, 'check_attach', stub_pass)
        self.stubs.Set(self.compute.volume_manager,
                       'setup_compute_volume',
                       stub_setup_compute_volume)
        self.stubs.Set(self.compute.db, 'volume_attached', stub_pass)

        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)
        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_terminate_instance_stub_network_is_false(self):
        """ Ensure instance is terminated when stub_network is false"""
        self.stub_flag = False

        def stub_get_instance_nw_info(context, instance):
            network_info = [1, 2, 3]
            return network_info

        def stub_deallocate_for_instance(context, instance):
            self.stub_flag = True
            pass

        self.stubs.Set(self.compute.network_api,
                       'get_instance_nw_info',
                       stub_get_instance_nw_info)
        self.stubs.Set(self.compute.network_api,
                       'deallocate_for_instance',
                       stub_deallocate_for_instance)

        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        instances = db.instance_get_all(context.get_admin_context())
        self.assertNotEqual(len(instances), 0)

        FLAGS.stub_network = False

        self.compute.terminate_instance(self.context, instance_id)
        self.assert_(self.stub_flag)

        instances = db.instance_get_all(context.get_admin_context())
        self.assertEqual(len(instances), 0)

        FLAGS.stub_network = True

    @attr(kind='small')
    def test_terminate_instance_power_state_shutoff(self):
        """ Ensure raise exception.Error when power_state is shutoff."""
        c = context.get_admin_context()
        instance_id = self._create_instance()
        self.compute.run_instance(c, instance_id)

        instance = db.instance_get(c, instance_id)
        db.instance_update(c, instance['id'],
                           {'power_state': power_state.SHUTOFF})
        instance = db.instance_get(c, instance_id)
        # pre-condition
        self.assertEquals(power_state.SHUTOFF, instance['power_state'])

        self.assertRaises(exception.Error,
                          self.compute.terminate_instance, c, instance_id)

    @attr(kind='small')
    def test_terminate_instance_with_detach_volume(self):
        """ Ensure detach volume from instance when instance terminate."""
        self.instance_name = None

        def stub_driver_detach_volume(instance_name, mountpoint):
            self.instance_name = instance_name

        self.stubs.Set(self.compute.driver,
                       'detach_volume',
                       stub_driver_detach_volume)

        c = context.get_admin_context()
        instance_id = self._create_instance()
        self.compute.run_instance(c, instance_id)

        instance = db.instance_get(c, instance_id)

        vol1 = models.Volume()
        vol1['id'] = 1
        vol2 = models.Volume()
        vol2['id'] = 2
        db.instance_update(c, instance['id'], {'volumes': [vol1, vol2]})
        instance = db.instance_get(c, instance_id)
        instance_name = instance['name']

        self.assertEquals(1, instance['volumes'][0]['id'])
        self.assertEquals(2, instance['volumes'][1]['id'])

        self.assertEquals(None, self.instance_name)
        self.compute.terminate_instance(c, instance_id)
        self.assertEquals(instance_name, self.instance_name)

    @attr(kind='small')
    def test_inject_file_when_instance_not_running(self):
        """Ensure we can write a file to an instance
            when instance is not running"""
        self.instance_id = None
        self.path = None
        self.file_contents = None

        def stub_driver_inject_file(instance_ref, path, file_contents):
            self.instance_id = instance_ref['id']
            self.path = path
            self.file_contents = file_contents

        self.stubs.Set(self.compute.driver,
                       'inject_file',
                       stub_driver_inject_file)

        c = context.get_admin_context()
        instance_id = self._create_instance()

        path = "/tmp/test"
        file_contents = "File Contents"
        self.compute.run_instance(c, instance_id)

        instance = db.instance_get(c, instance_id)
        db.instance_update(c, instance['id'],
                           {'power_state': power_state.PAUSED})

        self.assertEquals(None, self.instance_id)
        self.assertEquals(None, self.path)
        self.assertEquals(None, self.file_contents)
        self.compute.inject_file(c, instance_id, path, file_contents)
        self.assertEquals(instance_id, self.instance_id)
        self.assertEquals(path, self.path)
        self.assertEquals(file_contents, self.file_contents)

        self.compute.terminate_instance(c, instance_id)

    @attr(kind='small')
    def test_agent_update_when_instance_not_running(self):
        """Ensure instance can have its agent updated
            when instance is not running"""
        self.instance_id = None
        self.url = None
        self.md5hash = None

        def stub_driver_agent_update(instance_ref, url, md5hash):
            self.instance_id = instance_ref['id']
            self.url = url
            self.md5hash = md5hash

        self.stubs.Set(self.compute.driver,
                       'agent_update',
                       stub_driver_agent_update)

        instance_id = self._create_instance()
        url = 'http://127.0.0.1/agent'
        md5hash = '00112233445566778899aabbccddeeff'

        c = context.get_admin_context()
        self.compute.run_instance(c, instance_id)

        instance = db.instance_get(c, instance_id)
        db.instance_update(c, instance['id'],
                           {'power_state': power_state.PAUSED})

        self.assertEquals(None, self.instance_id)
        self.assertEquals(None, self.url)
        self.assertEquals(None, self.md5hash)
        self.compute.agent_update(c, instance_id, url, md5hash)
        self.assertEquals(instance_id, self.instance_id)
        self.assertEquals(url, self.url)
        self.assertEquals(md5hash, self.md5hash)

        self.compute.terminate_instance(c, instance_id)

    @attr(kind='small')
    def test_finish_resize_old_type_id_equal_new(self):
        """Ensure finish_resize
            when old_instance _id = new_instance_id."""
        def fake(*args, **kwargs):
            pass

        self.stubs.Set(self.compute.driver, 'finish_migration', fake)
        self.stubs.Set(self.compute.network_api,
                       'get_instance_nw_info', fake)

        context = self.context.elevated()
        instance_id = self._create_instance()
        instance = db.instance_get(context, instance_id)

        self.compute.prep_resize(context, instance['uuid'], 1)

        migration = db.migration_get_by_instance_and_status(
                                            context, instance['uuid'],
                                            'pre-migrating')
        migration = db.migration_get(context, int(migration['id']))
        old_instance_type_id = migration['old_instance_type_id']
        new_instance_type_id = migration['new_instance_type_id']
        db.migration_update(context, int(migration['id']),
                            {'old_instance_type_id': new_instance_type_id, })
        migration = db.migration_get(context, int(migration['id']))

        # pre-condition
        self.assertEquals(migration['old_instance_type_id'],
                          migration['new_instance_type_id'])
        self.assertEquals('pre-migrating', migration['status'])

        self.compute.finish_resize(context, instance['uuid'],
                                   int(migration['id']), {})

        # post-condition
        migration = db.migration_get(context, int(migration['id']))
        self.assertEquals('finished', migration['status'])

        db.migration_update(context, int(migration['id']),
                            {'old_instance_type_id': old_instance_type_id, })
        self.compute.terminate_instance(context, instance_id)

    @attr(kind='small')
    def test_pause_unpause_instance_with_callback_not_none(self):
        """Ensure instance can be paused/unpaused
           and callback is not none"""
        self.stub_flag = False

        def fake(instance, callback):
            self.stub_flag = True
            callback(True)

        self.stubs.Set(self.compute.driver, 'pause', fake)
        self.stubs.Set(self.compute.driver, 'unpause', fake)

        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        instance = db.instance_get(self.context, instance_id)
        self.assertEquals(vm_states.ACTIVE, instance['vm_state'])

        self.compute.pause_instance(self.context, instance_id)

        instance = db.instance_get(self.context, instance_id)
        self.assertEquals(vm_states.PAUSED, instance['vm_state'])

        self.compute.unpause_instance(self.context, instance_id)

        instance = db.instance_get(self.context, instance_id)
        self.assertEquals(vm_states.ACTIVE, instance['vm_state'])

        self.assert_(self.stub_flag)

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_suspend_resume_instance_callback_is_not_none(self):
        """ensure instance can be suspended and callback is not none"""
        self.stub_flag = False

        def fake(instance, callback):
            self.stub_flag = True
            callback(True)

        self.stubs.Set(self.compute.driver, 'suspend', fake)
        self.stubs.Set(self.compute.driver, 'resume', fake)

        instance_id = self._create_instance()
        self.compute.run_instance(self.context, instance_id)

        instance = db.instance_get(self.context, instance_id)
        self.assertEquals(vm_states.ACTIVE, instance['vm_state'])

        self.compute.suspend_instance(self.context, instance_id)

        instance = db.instance_get(self.context, instance_id)
        self.assertEquals(vm_states.SUSPENDED, instance['vm_state'])

        self.compute.resume_instance(self.context, instance_id)

        instance = db.instance_get(self.context, instance_id)
        self.assertEquals(vm_states.ACTIVE, instance['vm_state'])

        self.assert_(self.stub_flag)

        self.compute.terminate_instance(self.context, instance_id)

    @attr(kind='small')
    def test_rollback_live_migration_block_migration_true(self):
        """ Ensure call rpc.cast when block_migration is true"""
        self.instance_id = None

        def stub_rpc_cast(*args, **kwargs):
            self.instance_id = args[2]['args']['instance_id']

        self.stubs.Set(rpc, 'cast', stub_rpc_cast)

        instance_id = self._create_instance()
        instance = db.instance_get(self.context, instance_id)
        self.compute.rollback_live_migration(self.context,
                                             instance, None, True)
        self.assertEquals(instance_id, self.instance_id)

    @attr(kind='small')
    def test_post_live_migration_volume_manager_raise_notfound(self):
        """ Ensure call rpc.call when volume_manager raise notfound"""
        self.instance_id = None
        self.stub_flag = False

        def stub_volume_manager_remove_compute_volume(
                                            context, volume_id):
            self.stub_flag = True
            raise exception.NotFound

        def stub_driver_unfilter_instance(instance_ref, network_info):
            pass

        def stub_db_instance_get_floating_address(context, instance_id):
            return None

        def stub_rpc_call(*args, **kwargs):
            self.instance_id = args[2]['args']['instance_id']

        self.stubs.Set(self.compute.volume_manager, 'remove_compute_volume',
                       stub_volume_manager_remove_compute_volume)
        self.stubs.Set(self.compute.driver, 'unfilter_instance',
                       stub_driver_unfilter_instance)
        self.stubs.Set(self.compute.db, 'instance_get_floating_address',
                       stub_db_instance_get_floating_address)
        self.stubs.Set(rpc, 'call', stub_rpc_call)

        c = context.get_admin_context()
        instance_id = self._create_instance()
        vol1 = models.Volume()
        vol1['id'] = 1
        vol2 = models.Volume()
        vol2['id'] = 2
        instance = db.instance_get(c, instance_id)
        db.instance_update(c, instance['id'], {'volumes': [vol1, vol2]})
        self.compute.post_live_migration(c, instance, None)
        self.assert_(self.stub_flag)
        self.assertEquals(instance_id, self.instance_id)

    @attr(kind='small')
    def test_post_live_migration_db_raise_notfound(self):
        """ Ensure call rpc.call when db raise notfound"""
        self.instance_id = None
        self.stub_flag = False

        def stub_driver_unfilter_instance(instance_ref, network_info):
            pass

        def stub_db_instance_get_floating_address(context, instance_id):
            self.stub_flag = True
            raise exception.NotFound

        def stub_rpc_call(*args, **kwargs):
            self.instance_id = args[2]['args']['instance_id']

        self.stubs.Set(self.compute.driver, 'unfilter_instance',
                       stub_driver_unfilter_instance)
        self.stubs.Set(self.compute.db, 'instance_get_floating_address',
                       stub_db_instance_get_floating_address)
        self.stubs.Set(rpc, 'call', stub_rpc_call)

        c = context.get_admin_context()
        instance_id = self._create_instance()
        vol1 = models.Volume()
        vol1['id'] = 1
        vol2 = models.Volume()
        vol2['id'] = 2
        instance = db.instance_get(c, instance_id)
        db.instance_update(c, instance['id'], {'volumes': [vol1, vol2]})
        self.compute.post_live_migration(c, instance, None)
        self.assert_(self.stub_flag)
        self.assertEquals(instance_id, self.instance_id)

    @attr(kind='small')
    def test_post_live_migration_db_raise_exception(self):
        """ Ensure call rpc.call when db raise exception(non notfound)"""
        self.instance_id = None
        self.stub_flag = False

        def stub_driver_unfilter_instance(instance_ref, network_info):
            pass

        def stub_db_instance_get_floating_address(context, instance_id):
            self.stub_flag = True
            raise exception.NotAllowed

        def stub_rpc_call(*args, **kwargs):
            self.instance_id = args[2]['args']['instance_id']

        self.stubs.Set(self.compute.driver, 'unfilter_instance',
                       stub_driver_unfilter_instance)
        self.stubs.Set(self.compute.db, 'instance_get_floating_address',
                       stub_db_instance_get_floating_address)
        self.stubs.Set(rpc, 'call', stub_rpc_call)

        c = context.get_admin_context()
        instance_id = self._create_instance()
        vol1 = models.Volume()
        vol1['id'] = 1
        vol2 = models.Volume()
        vol2['id'] = 2
        instance = db.instance_get(c, instance_id)
        db.instance_update(c, instance['id'], {'volumes': [vol1, vol2]})
        self.compute.post_live_migration(c, instance, None)
        self.assert_(self.stub_flag)
        self.assertEquals(instance_id, self.instance_id)

    @attr(kind='small')
    def test_post_live_migration_block_migration_true(self):
        """ Ensure call driver.destroy when block_migration is true"""
        self.instance_id = None

        def stub_driver_unfilter_instance(instance_ref, network_info):
            pass

        def stub_db_instance_get_floating_address(context, instance_id):
            return None

        def stub_rpc_call(*args, **kwargs):
            pass

        def stub_driver_destroy(instance_ref, network_info):
            self.instance_id = instance_ref['id']

        self.stubs.Set(self.compute.driver, 'unfilter_instance',
                       stub_driver_unfilter_instance)
        self.stubs.Set(self.compute.db, 'instance_get_floating_address',
                       stub_db_instance_get_floating_address)
        self.stubs.Set(rpc, 'call', stub_rpc_call)
        self.stubs.Set(self.compute.driver, 'destroy', stub_driver_destroy)

        c = context.get_admin_context()
        instance_id = self._create_instance()
        vol1 = models.Volume()
        vol1['id'] = 1
        vol2 = models.Volume()
        vol2['id'] = 2
        instance = db.instance_get(c, instance_id)
        db.instance_update(c, instance['id'], {'volumes': [vol1, vol2]})
        self.compute.post_live_migration(c, instance, None, True)
        self.assertEquals(instance_id, self.instance_id)

    @attr(kind='small')
    def test_live_migration_block_migration_true(self):
        """ Ensure call driver.get_instance_disk_info
            when block_migration is true"""
        self.disk_info = []

        def stub_driver_get_instance_disk_info(context, instance_ref):
            disk_info = [{'type': 'raw', 'path': '/test/disk',
                          'local_gb': '10G'},
                         {'type': 'qcow2', 'path': '/test/disk.local',
                          'local_gb': '20G'}]
            return disk_info

        def stub_rpc_call(*args, **kwargs):
            if args[2]['method'] == 'pre_live_migration':
                self.disk_info = args[2]['args']['disk']

        self.stubs.Set(self.compute.driver, 'get_instance_disk_info',
                       stub_driver_get_instance_disk_info)
        self.stubs.Set(rpc, 'call', stub_rpc_call)

        c = context.get_admin_context()
        instance_id = self._create_instance()
        self.assertEquals([], self.disk_info)
        self.compute.live_migration(c, instance_id, None, True)
        self.assertTrue(self.disk_info[0]['type'] == 'raw' and
                        self.disk_info[1]['type'] == 'qcow2' and
                        self.disk_info[0]['path'] == '/test/disk' and
                        self.disk_info[1]['path'] == '/test/disk.local' and
                        self.disk_info[0]['local_gb'] == '10G' and
                        self.disk_info[1]['local_gb'] == '20G')

    @attr(kind='small')
    def test_pre_live_migration_network_info_is_empty(self):
        """ Ensure raise exception when network info is empty"""

        def stub_get_instance_nw_info(context, instance_ref):
            return []

        self.stubs.Set(self.compute, '_get_instance_nw_info',
                       stub_get_instance_nw_info)

        c = context.get_admin_context()
        instance_id = self._create_instance()

        self.assertRaises(exception.FixedIpNotFoundForInstance,
                          self.compute.pre_live_migration,
                          c, instance_id, time=None,
                          block_migration=False, disk=None)

    @attr(kind='small')
    def test_pre_live_migration_retry_count_zero(self):
        """ Ensure not call driver.plug_vifs
            when live_migration_retry_count is zero"""
        self.stub_flag = False

        def stub_instance_get_fixed_addresses(context, instance_id):
            return 'fake'

        def stub_get_instance_nw_info(context, instance_ref):
            nw_info = [[1, {'ips': '10.1.2.3'}],
                       [2, {'ips': '192.1.2.3'}]]

            return nw_info

        def stub_driver_plug_vifs(instance_ref, network_info):
            self.stub_flag = True

        def stub_driver_ensure_filtering_rules_for_instance(
                                                instance_ref, network_info):
            pass

        self.stubs.Set(self.compute.db, 'instance_get_fixed_addresses',
                       stub_instance_get_fixed_addresses)
        self.stubs.Set(self.compute, '_get_instance_nw_info',
                       stub_get_instance_nw_info)
        self.stubs.Set(self.compute.driver, 'plug_vifs',
                       stub_driver_plug_vifs)
        self.stubs.Set(self.compute.driver,
                       'ensure_filtering_rules_for_instance',
                       stub_driver_ensure_filtering_rules_for_instance)

        max_retry = FLAGS.live_migration_retry_count
        FLAGS.live_migration_retry_count = 0

        c = context.get_admin_context()
        instance_id = self._create_instance()

        self.assertFalse(self.stub_flag)
        self.compute.pre_live_migration(c, instance_id, time=None,
                                        block_migration=False, disk=None)
        self.assertFalse(self.stub_flag)

        FLAGS.live_migration_retry_count = max_retry

    @attr(kind='small')
    def test_pre_live_migration_block_migration_true(self):
        """ Ensure call driver.pre_block_migration
            when block_migration is true"""
        self.instance_id = None
        self.disk_info = []

        def stub_instance_get_fixed_addresses(context, instance_id):
            return 'fake'

        def stub_get_instance_nw_info(context, instance_ref):
            nw_info = [[1, {'ips': '10.1.2.3'}],
                       [2, {'ips': '192.1.2.3'}]]
            return nw_info

        def stub_driver_plug_vifs(instance_ref, network_info):
            pass

        def stub_driver_ensure_filtering_rules_for_instance(
                                                instance_ref, network_info):
            pass

        def stub_driver_pre_block_migration(context, instance_ref, disk):
            self.instance_id = instance_ref['id']
            self.disk_info = disk

        self.stubs.Set(self.compute.db, 'instance_get_fixed_addresses',
                       stub_instance_get_fixed_addresses)
        self.stubs.Set(self.compute, '_get_instance_nw_info',
                       stub_get_instance_nw_info)
        self.stubs.Set(self.compute.driver, 'plug_vifs',
                       stub_driver_plug_vifs)
        self.stubs.Set(self.compute.driver,
                       'ensure_filtering_rules_for_instance',
                       stub_driver_ensure_filtering_rules_for_instance)
        self.stubs.Set(self.compute.driver, 'pre_block_migration',
                       stub_driver_pre_block_migration)

        disk = [{'type': 'raw', 'path': '/test/disk',
                 'local_gb': '10G'},
                {'type': 'qcow2', 'path': '/test/disk.local',
                 'local_gb': '20G'}]

        c = context.get_admin_context()
        instance_id = self._create_instance()

        self.assertEquals(None, self.instance_id)
        self.assertEquals([], self.disk_info)
        self.compute.pre_live_migration(c, instance_id, time=None,
                                        block_migration=True, disk=disk)
        self.assertEquals(instance_id, self.instance_id)
        self.assertEquals(disk, self.disk_info)

    @attr(kind='small')
    def test_get_lock_by_instance_id(self):
        """Ensure get lock by instance id"""
        c = context.get_admin_context()
        instance_id = self._create_instance()
        self.compute.run_instance(c, instance_id)

        instance = db.instance_get(c, instance_id)
        db.instance_update(c, instance['id'], {'locked': False})

        rtn = self.compute.get_lock(c, instance_id)
        self.assertFalse(rtn)

        self.compute.terminate_instance(c, instance_id)

    @attr(kind='small')
    def test_get_lock_by_uuid(self):
        """Ensure get lock by uuid"""
        c = context.get_admin_context()
        instance_id = self._create_instance()
        self.compute.run_instance(c, instance_id)

        instance = db.instance_get(c, instance_id)
        uuid = instance['uuid']
        db.instance_update(c, instance['id'], {'locked': False})

        rtn = self.compute.get_lock(c, uuid)
        self.assertFalse(rtn)

        self.compute.terminate_instance(c, instance_id)
