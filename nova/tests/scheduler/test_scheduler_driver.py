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
Tests For nova.scheduler.driver
"""

from nova import compute
from nova import context
from nova import db
from nova import exception
from nova import rpc
from nova import test
from nova import utils
from nose.plugins.attrib import attr
from nova.scheduler import driver
from nova.scheduler import zone_manager
from eventlet import greenthread
from nova.compute import instance_types


class NoValidHostTestCase(test.TestCase):
    """Test for nova.scheduler.driver.NoValidHost."""
    def setUp(self):
        super(NoValidHostTestCase, self).setUp()

    @attr(kind='small')
    def test_novalidhost(self):
        """Test for nova.scheduler.driver.NoValidHost.
        Just verify exception type because the class has no other implements"""

        err = driver.NoValidHost()
        self.assertTrue(isinstance(err, exception.Error))


class WillNotScheduleTestCase(test.TestCase):
    """Test for nova.scheduler.driver.NoValidHost."""
    def setUp(self):
        super(WillNotScheduleTestCase, self).setUp()

    @attr(kind='small')
    def test_willnotschedule(self):
        """Test for nova.scheduler.driver.WillNotSchedule.
        Just verify exception type because the class has no other implements"""

        err = driver.WillNotSchedule()
        self.assertTrue(isinstance(err, exception.Error))


class SchedulerTestCase(test.TestCase):
    """Test for nova.scheduler.driver.Scheduler."""
    def setUp(self):
        super(SchedulerTestCase, self).setUp()
        self.scheduler = driver.Scheduler()
        self.context = context.RequestContext('user_id1', 'project_id1')
        self.flags(service_down_time=60)

    def _create_instance(self, params=None):
        """Create a test instance"""
        if not params:
            params = {}

        inst = {}
        inst['image_ref'] = 1
        inst['reservation_id'] = '12'
        inst['launch_time'] = '30'
        inst['user_id'] = 'user_id1'
        inst['project_id'] = 'project_id1'
        type_id = instance_types.get_instance_type_by_name('m1.tiny')['id']
        inst['instance_type_id'] = type_id
        inst['ami_launch_index'] = 0
        inst.update(params)
        return db.instance_create(self.context, inst)['id']

    @attr(kind='small')
    def test_set_zone_manager(self):
        """Test for nova.scheduler.driver.Scheduler.set_zone_manager.
        Verify zone manager be assign to zone_manager field"""

        zm = zone_manager.ZoneManager()
        ref = self.scheduler.set_zone_manager(zone_manager=zm)

        self.assertEqual(None, ref)
        self.assertEqual(zm, self.scheduler.zone_manager)

    @attr(kind='small')
    def test_service_is_up(self):
        """Test for nova.scheduler.driver.Scheduler.service_is_up.
        Return True if duration of host updated_at
        is little than service_down_time flag"""

        sv = dict(updated_at=utils.utcnow())

        ref = self.scheduler.service_is_up(service=sv)

        self.assertEqual(True, ref)

    @attr(kind='small')
    def test_service_is_up_parameter_createtime(self):
        """Test for nova.scheduler.driver.Scheduler.service_is_up.
        Return false if duration of host created_at
        is large than service_down_time flag"""

        self.flags(service_down_time=0)

        sv = dict(updated_at=None, created_at=utils.utcnow())
        ref = self.scheduler.service_is_up(service=sv)

        self.assertEqual(False, ref)

    @attr(kind='small')
    def test_service_is_up_parameter_updatetime(self):
        """Test for nova.scheduler.driver.Scheduler.service_is_up.
        Return false if duration of host updated_at
        is large than service_down_time flag"""

        self.flags(service_down_time=0)

        sv = dict(updated_at=utils.utcnow(), created_at=None)
        ref = self.scheduler.service_is_up(service=sv)

        self.assertEqual(False, ref)

    @attr(kind='small')
    def test_service_is_up_configuration(self):
        """Test for nova.scheduler.driver.Scheduler.service_is_up.
        Return false if duration of host created_at or updated_at
        is large than service_down_time flag"""

        self.flags(service_down_time=0.1)
        sv = dict(updated_at=utils.utcnow(), created_at=None)
        greenthread.sleep(0.2)

        ref = self.scheduler.service_is_up(service=sv)

        self.assertEqual(False, ref)

    @attr(kind='small')
    def test_hosts_up_parameter_exist(self):
        """Test for nova.scheduler.driver.Scheduler.hosts_up.
        Return host name if host associated with topic is up"""

        topic = 'compute'
        host = 'host1'
        values = dict(host=host, topic=topic)
        db.service_create(context.get_admin_context(), values)

        ref = self.scheduler.hosts_up(context.get_admin_context(), topic)

        self.assertEqual(1, len(ref))
        self.assertEqual(host, ref[0])

    @attr(kind='small')
    def test_hosts_up_parameter_notexist(self):
        """Test for nova.scheduler.driver.Scheduler.hosts_up.
        Return [] for not exist topic"""

        topic = 'notexist'

        ref = self.scheduler.hosts_up(context.get_admin_context(), topic)

        self.assertEqual(0, len(ref))

    @attr(kind='small')
    def test_hosts_up_parameter_notup(self):
        """Test for nova.scheduler.driver.Scheduler.hosts_up.
        Return [] if host searched by topic is not up"""

        self.flags(service_down_time=0)

        topic = 'compute1'
        host = 'host1'
        values = dict(host=host, topic=topic)
        db.service_create(context.get_admin_context(), values)

        ref = self.scheduler.hosts_up(context.get_admin_context(), topic)

        self.assertEqual(0, len(ref))

    @attr(kind='small')
    def test_hosts_up_exception(self):
        """Test for nova.scheduler.driver.Scheduler.hosts_up.
        Need administration context"""

        topic = 'compute1'

        self.assertRaises(exception.AdminRequired,
                self.scheduler.hosts_up, self.context, topic)

    @attr(kind='small')
    def test_schedule_exception(self):
        """Test for nova.scheduler.driver.Scheduler.schedule.
        Just raise NotImplementedError, need implement at child class"""

        self.assertRaises(NotImplementedError,
            self.scheduler.schedule, self.context, 'topic')

    @attr(kind='small')
    def test_schedule_live_migration(self):
        """Test for nova.scheduler.driver.Scheduler.schedule_live_migration.
        Return instance's host if migration success"""

        def fake_resource(context, instance_ref, dest, block_migration):
            pass

        self.stubs.Set(self.scheduler,
                'assert_compute_node_has_enough_resources', fake_resource)

        def fake_mount(context, instance_ref, dest):
            pass

        self.stubs.Set(self.scheduler,
                'mounted_on_same_shared_storage', fake_mount)

        def fake_call(context, topic, msg):
            pass

        self.stubs.Set(rpc, 'call', fake_call)

        instance_id = self._create_instance()

        dest = 'host2'
        topic = 'compute'
        host = 'host1'
        sv = dict(host=host, topic=topic)
        sv_ref_host = db.service_create(context.get_admin_context(), values=sv)

        sv = dict(host=dest, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        nd = dict(service_id=sv_ref['id'], vcpus='12', memory_mb='10',
            local_gb='20', vcpus_used='3', memory_mb_used='4', cpu_info='s',
            local_gb_used='5', hypervisor_type='hdest', hypervisor_version='1')
        db.compute_node_create(context.get_admin_context(), values=nd)

        nd['service_id'] = sv_ref_host['id']
        db.compute_node_create(context.get_admin_context(), values=nd)

        values = dict(power_state=compute.power_state.RUNNING, host=host,
                      launched_on=host)
        db.instance_update(self.context, instance_id, values)

        values = dict(instance_id=instance_id, status='c')
        volume_ref = db.volume_create(context.get_admin_context(), values)
        sv = dict(host=host, topic='volume')
        sv_ref_host = db.service_create(context.get_admin_context(), values=sv)

        ref = self.scheduler.schedule_live_migration(
                                    context.get_admin_context(), instance_id,
                                    dest=dest, block_migration=False)

        # confirm db
        volume_ref = db.volume_get(context.get_admin_context(),
                                   volume_ref['id'])

        self.assertEqual(host, ref)
        self.assertEqual('migrating', volume_ref['status'])

    @attr(kind='small')
    def test_schedule_live_migration_parameter(self):
        """Test for nova.scheduler.driver.Scheduler.schedule_live_migration.
        Raise InstanceNotFound if any invalid parameter inputed"""

        self.assertRaises(exception.InstanceNotFound,
                self.scheduler.schedule_live_migration,
                    context.get_admin_context(), instance_id=None,
                    dest=None, block_migration=False)

    @attr(kind='small')
    def test_schedule_live_migration_exception_src_not_running(self):
        """Test for nova.scheduler.driver.Scheduler.schedule_live_migration.
        Raise InstanceNotRunning if instance power_state is not  running"""

        instance_id = self._create_instance()

        values = dict(power_state=None)
        db.instance_update(self.context, instance_id, values)

        self.assertRaises(exception.InstanceNotRunning,
            self.scheduler.schedule_live_migration, self.context, instance_id,
                'dest_host1', block_migration=False)

    @attr(kind='small')
    def test_schedule_live_migration_exception_volume(self):
        """Test for nova.scheduler.driver.Scheduler.schedule_live_migration.
        Raise VolumeServiceUnavailable if without service with volume topic"""

        def fake_resource(context, instance_ref, dest, block_migration):
            pass

        self.stubs.Set(self.scheduler,
                'assert_compute_node_has_enough_resources', fake_resource)

        def fake_mount(context, instance_ref, dest):
            pass

        self.stubs.Set(self.scheduler,
                'mounted_on_same_shared_storage', fake_mount)

        def fake_call(context, topic, msg):
            pass

        self.stubs.Set(rpc, 'call', fake_call)

        instance_id = self._create_instance()

        dest = 'host2'
        topic = 'compute'
        host = 'host1'
        sv = dict(host=host, topic=topic)
        sv_ref_host = db.service_create(context.get_admin_context(), values=sv)

        sv = dict(host=dest, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        nd = dict(service_id=sv_ref['id'], vcpus='12', memory_mb='10',
            local_gb='20', vcpus_used='3', memory_mb_used='4', cpu_info='s',
            local_gb_used='5', hypervisor_type='hdest', hypervisor_version='1')
        db.compute_node_create(context.get_admin_context(), values=nd)

        nd['service_id'] = sv_ref_host['id']
        db.compute_node_create(context.get_admin_context(), values=nd)

        values = dict(power_state=compute.power_state.RUNNING, host=host,
                      launched_on=host)
        db.instance_update(self.context, instance_id, values)

        values = dict(instance_id=instance_id, status='c')
        db.volume_create(context.get_admin_context(), values)

        # volume associate to instance , but no volume service
        self.assertRaises(exception.VolumeServiceUnavailable,
                    self.scheduler.schedule_live_migration,
                        context.get_admin_context(), instance_id,
                        dest=dest, block_migration=False)

    @attr(kind='small')
    def test_schedule_live_migration_exception_service_notup(self):
        """Test for nova.scheduler.driver.Scheduler.schedule_live_migration.
        Raise ComputeServiceUnavailable if service is not up"""

        self.flags(service_down_time=0)

        def fake_resource(context, instance_ref, dest, block_migration):
            pass

        self.stubs.Set(self.scheduler,
                'assert_compute_node_has_enough_resources', fake_resource)

        def fake_mount(context, instance_ref, dest):
            pass

        self.stubs.Set(self.scheduler,
                'mounted_on_same_shared_storage', fake_mount)

        def fake_call(context, topic, msg):
            pass

        self.stubs.Set(rpc, 'call', fake_call)

        instance_id = self._create_instance()

        dest = 'host2'
        topic = 'compute'
        host = 'host1'
        sv = dict(host=host, topic=topic)
        sv_ref_host = db.service_create(context.get_admin_context(), values=sv)

        sv = dict(host=dest, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        nd = dict(service_id=sv_ref['id'], vcpus='12', memory_mb='10',
            local_gb='20', vcpus_used='3', memory_mb_used='4', cpu_info='s',
            local_gb_used='5', hypervisor_type='hdest', hypervisor_version='1')
        db.compute_node_create(context.get_admin_context(), values=nd)

        nd['service_id'] = sv_ref_host['id']
        db.compute_node_create(context.get_admin_context(), values=nd)

        values = dict(power_state=compute.power_state.RUNNING, host=host,
                      launched_on=host)
        db.instance_update(self.context, instance_id, values)

        self.assertRaises(exception.ComputeServiceUnavailable,
                    self.scheduler.schedule_live_migration,
                        context.get_admin_context(), instance_id,
                        dest=dest, block_migration=False)

    @attr(kind='small')
    def test_schedule_live_migration_exception_service_notup_dest(self):
        """Test for nova.scheduler.driver.Scheduler.schedule_live_migration.
        Raise ComputeServiceUnavailable if dest service is not up"""

        self.flags(service_down_time=0)

        def fake_service_is_up(service):
            if service['host'] == 'host2':
                return False
            return True

        self.stubs.Set(self.scheduler,
                'service_is_up', fake_service_is_up)

        def fake_resource(context, instance_ref, dest, block_migration):
            pass

        self.stubs.Set(self.scheduler,
                'assert_compute_node_has_enough_resources', fake_resource)

        def fake_mount(context, instance_ref, dest):
            pass

        self.stubs.Set(self.scheduler,
                'mounted_on_same_shared_storage', fake_mount)

        def fake_call(context, topic, msg):
            pass

        self.stubs.Set(rpc, 'call', fake_call)

        instance_id = self._create_instance()

        dest = 'host2'
        topic = 'compute'
        host = 'host1'
        sv = dict(host=host, topic=topic)
        sv_ref_host = db.service_create(context.get_admin_context(), values=sv)

        sv = dict(host=dest, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        nd = dict(service_id=sv_ref['id'], vcpus='12', memory_mb='10',
            local_gb='20', vcpus_used='3', memory_mb_used='4', cpu_info='s',
            local_gb_used='5', hypervisor_type='hdest', hypervisor_version='1')
        db.compute_node_create(context.get_admin_context(), values=nd)

        nd['service_id'] = sv_ref_host['id']
        db.compute_node_create(context.get_admin_context(), values=nd)

        values = dict(power_state=compute.power_state.RUNNING, host=host,
                      launched_on=host)
        db.instance_update(self.context, instance_id, values)

        self.assertRaises(exception.ComputeServiceUnavailable,
                    self.scheduler.schedule_live_migration,
                        context.get_admin_context(), instance_id,
                        dest=dest, block_migration=False)

    @attr(kind='small')
    def test_schedule_live_migration_exception_no_service(self):
        """Test for nova.scheduler.driver.Scheduler.schedule_live_migration.
        Raise ComputeHostNotFound if service dose not exist in db"""

        instance_id = self._create_instance()

        values = dict(power_state=compute.power_state.RUNNING)
        db.instance_update(self.context, instance_id, values)

        self.assertRaises(exception.ComputeHostNotFound,
                self.scheduler.schedule_live_migration,
                    context.get_admin_context(), instance_id,
                        'dest_host1', block_migration=False)

    @attr(kind='small')
    def test_schedule_live_migration_exception_admin(self):
        """Test for nova.scheduler.driver.Scheduler.schedule_live_migration.
        Need administration context"""

        instance_id = self._create_instance()

        values = dict(power_state=compute.power_state.RUNNING)
        db.instance_update(self.context, instance_id, values)

        self.assertRaises(exception.AdminRequired,
            self.scheduler.schedule_live_migration, self.context, instance_id,
                                        'dest_host1', block_migration=False)

    @attr(kind='small')
    def test_schedule_live_migration_exception_desthost(self):
        """Test for nova.scheduler.driver.Scheduler.schedule_live_migration.
        Raise ComputeHostNotFound if destination dose not exist in db"""

        instance_id = self._create_instance()
        dest = 'dest_host1'

        topic = 'compute'
        host = 'host1'
        sv = dict(host=host, topic=topic)
        db.service_create(context.get_admin_context(), values=sv)

        values = dict(power_state=compute.power_state.RUNNING, host=host)
        db.instance_update(self.context, instance_id, values)

        # destination be not found
        self.assertRaises(exception.ComputeHostNotFound,
                  self.scheduler.schedule_live_migration,
                        context.get_admin_context(), instance_id,
                        dest, block_migration=False)

    @attr(kind='small')
    def test_schedule_live_migration_exception_samehost(self):
        """Test for nova.scheduler.driver.Scheduler.schedule_live_migration.
        Raise UnableToMigrateToSelf
        if destination is same with instance host"""

        instance_id = self._create_instance()

        topic = 'compute'
        host = 'host1'
        sv = dict(host=host, topic=topic)
        db.service_create(context.get_admin_context(), values=sv)

        values = dict(power_state=compute.power_state.RUNNING, host=host)
        db.instance_update(self.context, instance_id, values)

        # destination is instance's host
        self.assertRaises(exception.UnableToMigrateToSelf,
            self.scheduler.schedule_live_migration,
                                    context.get_admin_context(), instance_id,
                                    dest=host, block_migration=False)

    @attr(kind='small')
    def test_schedule_live_migration_exception_storage(self):
        """Test for nova.scheduler.driver.Scheduler.schedule_live_migration.
        Raise InvalidSharedStorage if mount at same storage
        and block_migration is True"""

        def fake_resource(context, instance_ref, dest, block_migration):
            pass

        self.stubs.Set(self.scheduler,
                'assert_compute_node_has_enough_resources', fake_resource)

        def fake_mount(context, instance_ref, dest):
            pass

        self.stubs.Set(self.scheduler,
                'mounted_on_same_shared_storage', fake_mount)

        instance_id = self._create_instance()

        dest = 'host2'
        topic = 'compute'
        host = 'host1'
        sv = dict(host=host, topic=topic)
        db.service_create(context.get_admin_context(), values=sv)

        sv = dict(host=dest, topic=topic)
        db.service_create(context.get_admin_context(), values=sv)

        values = dict(power_state=compute.power_state.RUNNING, host=host)
        db.instance_update(self.context, instance_id, values)

        # mount at same storage and block_migration is True
        self.assertRaises(exception.InvalidSharedStorage,
            self.scheduler.schedule_live_migration,
                                    context.get_admin_context(), instance_id,
                                    dest=dest, block_migration=True)

    @attr(kind='small')
    def test_schedule_live_migration_exception_file(self):
        """Test for nova.scheduler.driver.Scheduler.schedule_live_migration.
        Raise FileNotFound if does not mount at same storage """

        def fake_resource(context, instance_ref, dest, block_migration):
            pass

        self.stubs.Set(self.scheduler,
                'assert_compute_node_has_enough_resources', fake_resource)

        def fake_mount(context, instance_ref, dest):
            raise exception.FileNotFound

        self.stubs.Set(self.scheduler,
                'mounted_on_same_shared_storage', fake_mount)

        instance_id = self._create_instance()

        dest = 'host2'
        topic = 'compute'
        host = 'host1'
        sv = dict(host=host, topic=topic)
        db.service_create(context.get_admin_context(), values=sv)

        sv = dict(host=dest, topic=topic)
        db.service_create(context.get_admin_context(), values=sv)

        values = dict(power_state=compute.power_state.RUNNING, host=host)
        db.instance_update(self.context, instance_id, values)

        # dose not mount as same storage
        self.assertRaises(exception.FileNotFound,
            self.scheduler.schedule_live_migration,
                                    context.get_admin_context(), instance_id,
                                    dest=dest, block_migration=False)

    @attr(kind='small')
    def test_schedule_live_migration_exception_nolaunch(self):
        """Test for nova.scheduler.driver.Scheduler.schedule_live_migration.
        Raise SourceHostUnavailable if instance has not launched_on"""

        def fake_resource(context, instance_ref, dest, block_migration):
            pass

        self.stubs.Set(self.scheduler,
                'assert_compute_node_has_enough_resources', fake_resource)

        def fake_mount(context, instance_ref, dest):
            pass

        self.stubs.Set(self.scheduler,
                'mounted_on_same_shared_storage', fake_mount)

        instance_id = self._create_instance()

        dest = 'host2'
        topic = 'compute'
        host = 'host1'
        sv = dict(host=host, topic=topic)
        db.service_create(context.get_admin_context(), values=sv)

        sv = dict(host=dest, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        nd = dict(service_id=sv_ref['id'], vcpus='12', memory_mb='10',
            local_gb='20', vcpus_used='3', memory_mb_used='4', cpu_info='s',
            local_gb_used='5', hypervisor_type='sn', hypervisor_version='1')
        db.compute_node_create(context.get_admin_context(), values=nd)

        values = dict(power_state=compute.power_state.RUNNING, host=host)
        db.instance_update(self.context, instance_id, values)

        # instance without launched_on
        self.assertRaises(exception.SourceHostUnavailable,
            self.scheduler.schedule_live_migration,
                                    context.get_admin_context(), instance_id,
                                    dest=dest, block_migration=False)

    @attr(kind='small')
    def test_schedule_live_migration_exception_hypervisor(self):
        """Test for nova.scheduler.driver.Scheduler.schedule_live_migration.
        Raise DestinationHypervisorTooOld if destination's hypervisor type
        is different between instance and destination"""

        def fake_resource(context, instance_ref, dest, block_migration):
            pass

        self.stubs.Set(self.scheduler,
                'assert_compute_node_has_enough_resources', fake_resource)

        def fake_mount(context, instance_ref, dest):
            pass

        self.stubs.Set(self.scheduler,
                'mounted_on_same_shared_storage', fake_mount)

        # prepare instance , service and compute node in db
        instance_id = self._create_instance()

        dest = 'host2'
        topic = 'compute'
        host = 'host1'
        sv = dict(host=host, topic=topic)
        sv_ref_host = db.service_create(context.get_admin_context(), values=sv)

        sv = dict(host=dest, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        nd = dict(service_id=sv_ref['id'], vcpus='12', memory_mb='10',
            local_gb='20', vcpus_used='3', memory_mb_used='4', cpu_info='s',
            local_gb_used='5', hypervisor_type='hdest', hypervisor_version='1')
        db.compute_node_create(context.get_admin_context(), values=nd)

        nd['service_id'] = sv_ref_host['id']
        nd['hypervisor_type'] = 'hhost'
        db.compute_node_create(context.get_admin_context(), values=nd)

        values = dict(power_state=compute.power_state.RUNNING, host=host,
                      launched_on=host)
        db.instance_update(self.context, instance_id, values)

        # hypervisor_type is different
        self.assertRaises(exception.InvalidHypervisorType,
            self.scheduler.schedule_live_migration,
                                    context.get_admin_context(), instance_id,
                                    dest=dest, block_migration=False)

    @attr(kind='small')
    def test_schedule_live_migration_exception_hypervisor_ver(self):
        """Test for nova.scheduler.driver.Scheduler.schedule_live_migration.
        Raise DestinationHypervisorTooOld if destination's hypervisor version
        is older than instance's"""

        def fake_resource(context, instance_ref, dest, block_migration):
            pass

        self.stubs.Set(self.scheduler,
                'assert_compute_node_has_enough_resources', fake_resource)

        def fake_mount(context, instance_ref, dest):
            pass

        self.stubs.Set(self.scheduler,
                'mounted_on_same_shared_storage', fake_mount)

        # prepare instance , service and compute node
        instance_id = self._create_instance()

        dest = 'host2'
        topic = 'compute'
        host = 'host1'
        sv = dict(host=host, topic=topic)
        sv_ref_host = db.service_create(context.get_admin_context(), values=sv)

        sv = dict(host=dest, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        nd = dict(service_id=sv_ref['id'], vcpus='12', memory_mb='10',
            local_gb='20', vcpus_used='3', memory_mb_used='4', cpu_info='s',
            local_gb_used='5', hypervisor_type='hdest', hypervisor_version='1')
        db.compute_node_create(context.get_admin_context(), values=nd)

        nd['service_id'] = sv_ref_host['id']
        nd['hypervisor_version'] = '2'
        db.compute_node_create(context.get_admin_context(), values=nd)

        values = dict(power_state=compute.power_state.RUNNING, host=host,
                      launched_on=host)
        db.instance_update(self.context, instance_id, values)

        # hypervisor_version: 1 < 2
        self.assertRaises(exception.DestinationHypervisorTooOld,
            self.scheduler.schedule_live_migration,
                                    context.get_admin_context(), instance_id,
                                    dest=dest, block_migration=False)

    @attr(kind='small')
    def test_schedule_live_migration_exception_rpc(self):
        """Test for nova.scheduler.driver.Scheduler.schedule_live_migration.
        Pass through rpc.RemoteError raise at cpuinfo checking"""

        def fake_resource(context, instance_ref, dest, block_migration):
            pass

        self.stubs.Set(self.scheduler,
                'assert_compute_node_has_enough_resources', fake_resource)

        def fake_mount(context, instance_ref, dest):
            pass

        self.stubs.Set(self.scheduler,
                'mounted_on_same_shared_storage', fake_mount)

        def fake_call(context, topic, msg):
            raise rpc.RemoteError('exc_type', 'value', 'traceback')

        self.stubs.Set(rpc, 'call', fake_call)

        # prepare service , instance and compute node
        instance_id = self._create_instance()

        dest = 'host2'
        topic = 'compute'
        host = 'host1'
        sv = dict(host=host, topic=topic)
        sv_ref_host = db.service_create(context.get_admin_context(), values=sv)

        sv = dict(host=dest, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        nd = dict(service_id=sv_ref['id'], vcpus='12', memory_mb='10',
            local_gb='20', vcpus_used='3', memory_mb_used='4', cpu_info='s',
            local_gb_used='5', hypervisor_type='hdest', hypervisor_version='1')
        db.compute_node_create(context.get_admin_context(), values=nd)

        nd['service_id'] = sv_ref_host['id']
        db.compute_node_create(context.get_admin_context(), values=nd)

        values = dict(power_state=compute.power_state.RUNNING, host=host,
                      launched_on=host)
        db.instance_update(self.context, instance_id, values)

        # raise at resource checking
        self.assertRaises(rpc.RemoteError,
            self.scheduler.schedule_live_migration,
                        context.get_admin_context(), instance_id,
                        dest=dest, block_migration=False)

    @attr(kind='small')
    def test_assert_compute_node_has_enough_resources(self):
        """Test for driver.Scheduler.assert_compute_node_has_enough_resources.
        Return None if has enough memory and disk"""

        def fake_memory(context, instance_ref, dest):
            pass

        self.stubs.Set(self.scheduler,
                'assert_compute_node_has_enough_memory', fake_memory)

        ref = self.scheduler.assert_compute_node_has_enough_resources(
                self.context, 'instance_ref', 'dest', block_migration=False)

        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_assert_compute_node_has_enough_resources_parameter(self):
        """Test for driver.Scheduler.assert_compute_node_has_enough_resources.
        Also check disk if parameter block_migration is true"""

        def fake_resource(context, instance_ref, dest):
            pass

        self.stubs.Set(self.scheduler,
                'assert_compute_node_has_enough_memory', fake_resource)

        self.stubs.Set(self.scheduler,
                'assert_compute_node_has_enough_disk', fake_resource)

        ref = self.scheduler.assert_compute_node_has_enough_resources(
                self.context, 'instance_ref', 'dest', block_migration=True)

        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_assert_compute_node_has_enough_resources_exception(self):
        """Test for driver.Scheduler.assert_compute_node_has_enough_resources.
        Raise MigrationError if destination has not enough memory or disk"""

        def fake_resource(context, instance_ref, dest):
            raise exception.MigrationError

        self.stubs.Set(self.scheduler,
                'assert_compute_node_has_enough_memory', fake_resource)

        self.stubs.Set(self.scheduler,
                'assert_compute_node_has_enough_disk', fake_resource)

        self.assertRaises(exception.MigrationError,
            self.scheduler.assert_compute_node_has_enough_resources,
                self.context, 'instance_ref', 'dest', block_migration=True)

    @attr(kind='small')
    def test_assert_compute_node_has_enough_memory(self):
        """Test for driver.Scheduler.assert_compute_node_has_enough_memory.
        Return None if compute node has enough memory"""

        instance_id = self._create_instance()

        dest = 'host2'
        topic = 'compute'

        sv = dict(host=dest, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        nd = dict(service_id=sv_ref['id'], vcpus='12', memory_mb=8,
            local_gb='20', vcpus_used='3', memory_mb_used='4', cpu_info='s',
            local_gb_used='5', hypervisor_type='hdest', hypervisor_version='1')
        db.compute_node_create(context.get_admin_context(), values=nd)

        values = dict(power_state=compute.power_state.RUNNING, memory_mb=7)
        db.instance_update(self.context, instance_id, values)
        instance_ref = db.instance_get(context.get_admin_context(),
                                       instance_id)

        # memory_mb: 8 > 7
        ref = self.scheduler.assert_compute_node_has_enough_memory(
                    context.get_admin_context(), instance_ref, dest)

        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_assert_compute_node_has_enough_memory_parameter(self):
        """Test for driver.Scheduler.assert_compute_node_has_enough_memory.
        Raise ComputeHostNotFound if any invalid parameter inputed"""

        self.assertRaises(exception.ComputeHostNotFound,
                self.scheduler.assert_compute_node_has_enough_memory,
                    context.get_admin_context(), instance_ref=None, dest=None)

    @attr(kind='small')
    def test_assert_compute_node_has_enough_memory_database(self):
        """Test for driver.Scheduler.assert_compute_node_has_enough_memory.
        Raise MigrationError if destination host has not enough memory"""

        instance_id = self._create_instance()

        dest = 'host2'
        topic = 'compute'

        sv = dict(host=dest, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        nd = dict(service_id=sv_ref['id'], vcpus='12', memory_mb=8,
            local_gb='20', vcpus_used='3', memory_mb_used='4', cpu_info='s',
            local_gb_used='5', hypervisor_type='hdest', hypervisor_version='1')
        db.compute_node_create(context.get_admin_context(), values=nd)

        values = dict(memory_mb=10)
        db.instance_update(self.context, instance_id, values)
        instance_ref = db.instance_get(context.get_admin_context(),
                                       instance_id)

        # memory_mb: 8 < 10
        self.assertRaises(exception.MigrationError,
                self.scheduler.assert_compute_node_has_enough_memory,
                    context.get_admin_context(), instance_ref, dest)

    @attr(kind='small')
    def test_assert_compute_node_has_enough_memory_exception_lack(self):
        """Test for driver.Scheduler.assert_compute_node_has_enough_memory.
        Raise MigrationError if destination host has not enough memory"""

        def fake_exception(ex, **kwargs):
            # confirm error message
            self.assertTrue(kwargs['reason'].lower().find('memory') >= 0)

        self.stubs.Set(exception.NovaException, '__init__', fake_exception)

        instance_id = self._create_instance()

        dest = 'host2'
        topic = 'compute'

        sv = dict(host=dest, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        nd = dict(service_id=sv_ref['id'], vcpus='12', memory_mb=8,
            local_gb='20', vcpus_used='3', memory_mb_used='4', cpu_info='s',
            local_gb_used='5', hypervisor_type='hdest', hypervisor_version='1')
        db.compute_node_create(context.get_admin_context(), values=nd)

        values = dict(memory_mb=8)
        db.instance_update(self.context, instance_id, values)
        instance_ref = db.instance_get(context.get_admin_context(),
                                       instance_id)

        # memory_mb: 8 == 8
        self.assertRaises(exception.MigrationError,
                self.scheduler.assert_compute_node_has_enough_memory,
                    context.get_admin_context(), instance_ref, dest)

    @attr(kind='small')
    def test_assert_compute_node_has_enough_memory_exception_inst(self):
        """Test for driver.Scheduler.assert_compute_node_has_enough_memory.
        Raise MigrationError if instance's memory_mb is none"""

        instance_id = self._create_instance()

        dest = 'host2'
        topic = 'compute'

        sv = dict(host=dest, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        nd = dict(service_id=sv_ref['id'], vcpus='12', memory_mb=8,
            local_gb='20', vcpus_used='3', memory_mb_used='4', cpu_info='s',
            local_gb_used='5', hypervisor_type='hdest', hypervisor_version='1')
        db.compute_node_create(context.get_admin_context(), values=nd)

        instance_ref = db.instance_get(context.get_admin_context(),
                                       instance_id)

        # instance has no memory_mb
        self.assertRaises(exception.MigrationError,
                self.scheduler.assert_compute_node_has_enough_memory,
                    context.get_admin_context(), instance_ref, dest)

    @attr(kind='small')
    def test_assert_compute_node_has_enough_memory_exception_used(self):
        """Test for driver.Scheduler.assert_compute_node_has_enough_memory.
        Raise MigrationError if destination host free memory is lower than
        instance needed """

        # prepare instance that memory_mb is large than node's free memory
        instance_id = self._create_instance()

        dest = 'host2'
        topic = 'compute'

        sv = dict(host=dest, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        nd = dict(service_id=sv_ref['id'], vcpus='12', memory_mb=8,
            local_gb='20', vcpus_used='3', memory_mb_used='4', cpu_info='s',
            local_gb_used='5', hypervisor_type='hdest', hypervisor_version='1')
        db.compute_node_create(context.get_admin_context(), values=nd)

        values = dict(host=dest, memory_mb=7)
        db.instance_update(self.context, instance_id, values)
        instance_ref = db.instance_get(context.get_admin_context(),
                                       instance_id)

        # memory_mb: 8-7 < 8
        self.assertRaises(exception.MigrationError,
                self.scheduler.assert_compute_node_has_enough_memory,
                    context.get_admin_context(), instance_ref, dest)

    @attr(kind='small')
    def test_assert_compute_node_has_enough_disk(self):
        """Test for ndriver.Scheduler.assert_compute_node_has_enough_disk.
        Return None if has enough disk """

        # prepare service , compute node and instance
        instance_id = self._create_instance()

        dest = 'host2'
        topic = 'compute'

        sv = dict(host=dest, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        nd = dict(service_id=sv_ref['id'], vcpus='12', memory_mb=8,
            local_gb=20, vcpus_used='3', memory_mb_used='4', cpu_info='s',
            local_gb_used='5', hypervisor_type='hdest', hypervisor_version='1')
        db.compute_node_create(context.get_admin_context(), values=nd)

        values = dict(local_gb=19)
        db.instance_update(self.context, instance_id, values)
        instance_ref = db.instance_get(context.get_admin_context(),
                                       instance_id)

        # local_gb: 20> 19
        ref = self.scheduler.assert_compute_node_has_enough_disk(
                    context.get_admin_context(), instance_ref, dest)

        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_assert_compute_node_has_enough_disk_parameter(self):
        """Test for driver.Scheduler.assert_compute_node_has_enough_disk.
        Raise ComputeHostNotFound if any invalid parameter inputed"""

        self.assertRaises(exception.ComputeHostNotFound,
                self.scheduler.assert_compute_node_has_enough_disk,
                    context.get_admin_context(), instance_ref=None, dest=None)

    @attr(kind='small')
    def test_assert_compute_node_has_enough_disk_exception_lack(self):
        """Test for driver.Scheduler.assert_compute_node_has_enough_disk.
        Raise MigrationError if destination host has not enough disk"""

        def fake_exception(ex, **kwargs):
            # confirm error message
            self.assertTrue(kwargs['reason'].lower().find('disk') >= 0)

        self.stubs.Set(exception.NovaException, '__init__', fake_exception)

        # prepare instance thant local_gb equals dest node had
        instance_id = self._create_instance()

        dest = 'host2'
        topic = 'compute'

        sv = dict(host=dest, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        nd = dict(service_id=sv_ref['id'], vcpus='12', memory_mb=8,
            local_gb=20, vcpus_used='3', memory_mb_used='4', cpu_info='s',
            local_gb_used='5', hypervisor_type='hdest', hypervisor_version='1')
        db.compute_node_create(context.get_admin_context(), values=nd)

        values = dict(local_gb=20)
        db.instance_update(self.context, instance_id, values)
        instance_ref = db.instance_get(context.get_admin_context(),
                                       instance_id)

        # local_gb: 20 == 20
        self.assertRaises(exception.MigrationError,
                self.scheduler.assert_compute_node_has_enough_disk,
                    context.get_admin_context(), instance_ref, dest)

    @attr(kind='small')
    def test_assert_compute_node_has_enough_disk_exception_inst(self):
        """Test for driver.Scheduler.assert_compute_node_has_enough_disk.
        Size check is OK if migrate instance has no local_gb value"""

        # prepare instance without local_gb
        instance_id = self._create_instance()

        dest = 'host2'
        topic = 'compute'

        sv = dict(host=dest, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        nd = dict(service_id=sv_ref['id'], vcpus='12', memory_mb=8,
            local_gb=20, vcpus_used='3', memory_mb_used='4', cpu_info='s',
            local_gb_used='5', hypervisor_type='hdest', hypervisor_version='1')
        db.compute_node_create(context.get_admin_context(), values=nd)
        instance_ref = db.instance_get(context.get_admin_context(),
                                       instance_id)

        self.scheduler.assert_compute_node_has_enough_disk(
                    context.get_admin_context(), instance_ref, dest)

    @attr(kind='small')
    def test_assert_compute_node_has_enough_disk_param_local_gb_0(self):
        """Test for driver.Scheduler.assert_compute_node_has_enough_disk.
        Size check is OK if migrate instance's local_gb is zero"""

        # prepare instance with local_gb=0
        instance_id = self._create_instance({'local_gb': 0})

        dest = 'host2'
        topic = 'compute'

        sv = dict(host=dest, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        nd = dict(service_id=sv_ref['id'], vcpus='12', memory_mb=8,
            local_gb=20, vcpus_used='3', memory_mb_used='4', cpu_info='s',
            local_gb_used='5', hypervisor_type='hdest', hypervisor_version='1')
        db.compute_node_create(context.get_admin_context(), values=nd)
        instance_ref = db.instance_get(context.get_admin_context(),
                                       instance_id)

        self.scheduler.assert_compute_node_has_enough_disk(
                    context.get_admin_context(), instance_ref, dest)

    @attr(kind='small')
    def test_assert_compute_node_has_enough_disk_exception_used(self):
        """Test for driver.Scheduler.assert_compute_node_has_enough_disk.
        Raise MigrationError if destination host free disk is lower than
        instance needed"""

        # prepare service, compute node and instance
        instance_id = self._create_instance()

        dest = 'host2'
        topic = 'compute'

        sv = dict(host=dest, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        nd = dict(service_id=sv_ref['id'], vcpus='12', memory_mb=8,
            local_gb=20, vcpus_used='3', memory_mb_used='4', cpu_info='s',
            local_gb_used='5', hypervisor_type='hdest', hypervisor_version='1')
        db.compute_node_create(context.get_admin_context(), values=nd)

        values = dict(local_gb=15, host=dest)
        db.instance_update(self.context, instance_id, values)
        instance_ref = db.instance_get(context.get_admin_context(),
                                       instance_id)

        # node has 20g and used 15g
        self.assertRaises(exception.MigrationError,
                self.scheduler.assert_compute_node_has_enough_disk,
                    context.get_admin_context(), instance_ref, dest)

    @attr(kind='small')
    def test_mounted_on_same_shared_storage(self):
        """Test for driver.Scheduler.mounted_on_same_shared_storage.
        Return None if mounted on same storage, Otherwise raise exception"""

        def fake_call(context, topic, msg):
            return 'filename1'

        self.stubs.Set(rpc, 'call', fake_call)

        # prepare instance with host
        dest = 'host2'
        instance_id = self._create_instance()
        values = dict(local_gb=15, host=dest)
        db.instance_update(self.context, instance_id, values)
        instance_ref = db.instance_get(context.get_admin_context(),
                                       instance_id)

        ref = self.scheduler.mounted_on_same_shared_storage(
                        context.get_admin_context(), instance_ref, dest)

        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_mounted_on_same_shared_storage_parameter(self):
        """Test for driver.Scheduler.mounted_on_same_shared_storage.
        Raise exception depended on rpc.call if invalid parameter inputed"""

        def fake_call(context, topic, msg):
            raise rpc.RemoteError('', '', '')

        self.stubs.Set(rpc, 'call', fake_call)

        # prepare instance without host
        instance_id = self._create_instance()
        values = dict(host=None)
        db.instance_update(self.context, instance_id, values)
        instance_ref = db.instance_get(context.get_admin_context(),
                                       instance_id)

        self.assertRaises(rpc.RemoteError,
                self.scheduler.mounted_on_same_shared_storage,
                        context.get_admin_context(), instance_ref, dest=None)

    @attr(kind='small')
    def test_mounted_on_same_shared_storage_exception(self):
        """Test for driver.Scheduler.mounted_on_same_shared_storage.
        Raise FileNotFound if check_shared_storage_test_file rpc.call
        return false"""

        def fake_call(context, topic, msg):
            if msg['method'] == 'create_shared_storage_test_file':
                return 'filename1'
            elif msg['method'] == 'check_shared_storage_test_file':
                return False

        self.stubs.Set(rpc, 'call', fake_call)

        # prepare instance object with host
        dest = 'host2'
        instance_id = self._create_instance()
        values = dict(host=dest)
        db.instance_update(self.context, instance_id, values)
        instance_ref = db.instance_get(context.get_admin_context(),
                                       instance_id)

        self.assertRaises(exception.FileNotFound,
                self.scheduler.mounted_on_same_shared_storage,
                        context.get_admin_context(), instance_ref, dest=dest)
