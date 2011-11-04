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
Tests For Scheduler.simple
"""

import datetime
from nose.plugins.attrib import attr
from nova import context
from nova import db
from nova import exception
from nova import flags
from nova import service
from nova import test
from nova import utils
from nova.scheduler import driver
from nova.scheduler import manager
from nova.compute import power_state
from nova.compute import vm_states


FLAGS = flags.FLAGS
flags.DECLARE('max_cores', 'nova.scheduler.simple')
flags.DECLARE('stub_network', 'nova.compute.manager')


class SimpleSchedulerTestCase(test.TestCase):
    """Test case for simple driver"""
    def setUp(self):
        super(SimpleSchedulerTestCase, self).setUp()
        self.flags(connection_type='fake',
                   stub_network=True,
                   max_cores=4,
                   max_gigabytes=4,
                   network_manager='nova.network.manager.FlatManager',
                   volume_driver='nova.volume.driver.FakeISCSIDriver',
                   scheduler_driver='nova.scheduler.simple.SimpleScheduler')
        self.scheduler = manager.SchedulerManager()
        self.context = context.get_admin_context()
        self.user_id = 'fake'
        self.project_id = 'fake'

    def _create_instance(self, **kwargs):
        """Create a test instance"""
        inst = {}
        # NOTE(jk0): If an integer is passed as the image_ref, the image
        # service will use the default image service (in this case, the fake).
        inst['image_ref'] = '1'
        inst['reservation_id'] = 'r-fakeres'
        inst['user_id'] = self.user_id
        inst['project_id'] = self.project_id
        inst['instance_type_id'] = '1'
        inst['vcpus'] = kwargs.get('vcpus', 1)
        inst['ami_launch_index'] = 0
        inst['availability_zone'] = kwargs.get('availability_zone', None)
        inst['host'] = kwargs.get('host', 'dummy')
        inst['memory_mb'] = kwargs.get('memory_mb', 20)
        inst['local_gb'] = kwargs.get('local_gb', 30)
        inst['launched_on'] = kwargs.get('launghed_on', 'dummy')
        inst['vm_state'] = kwargs.get('vm_state', vm_states.ACTIVE)
        inst['task_state'] = kwargs.get('task_state', None)
        inst['power_state'] = kwargs.get('power_state', power_state.RUNNING)
        return db.instance_create(self.context, inst)['id']

    def _create_volume(self, **kwargs):
        """Create a test volume"""
        vol = {}
        vol['size'] = 1
        vol['availability_zone'] = kwargs.get('availability_zone', 'test')
        return db.volume_create(self.context, vol)['id']

    @attr(kind='small')
    def test_schedule_start_instance(self):
        """Ensure that it returns the same results as schedule_run_instance"""
        compute1 = service.Service('host1',
                                   'nova-compute',
                                   'compute',
                                   FLAGS.compute_manager)
        compute1.start()
        compute2 = service.Service('host2',
                                   'nova-compute',
                                   'compute',
                                   FLAGS.compute_manager)
        compute2.start()
        instance_id1 = self._create_instance()
        compute1.run_instance(self.context, instance_id1)
        instance_id2 = self._create_instance()
        host = self.scheduler.driver.schedule_start_instance(self.context,
                                                             instance_id2)
        self.assertEqual(host, 'host2')
        compute1.terminate_instance(self.context, instance_id1)
        db.instance_destroy(self.context, instance_id2)
        compute1.kill()
        compute2.kill()

    @attr(kind='small')
    def test_schedule_run_instance_database_service_get(self):
        """Ensure raise exception when compute services can not be obtained"""
        instance_id = self._create_instance()
        self.assertRaises(driver.NoValidHost,
                          self.scheduler.driver.schedule_run_instance,
                          self.context, instance_id)

    @attr(kind='small')
    def test_schedule_run_instance_configuration_service_is_down(self):
        """Ensure raise exception when host not available"""
        compute1 = self.start_service('compute', host='host1')
        s1 = db.service_get_by_args(self.context, 'host1', 'nova-compute')
        now = utils.utcnow()
        delta = datetime.timedelta(seconds=FLAGS.service_down_time * 2)
        past = now - delta
        db.service_update(self.context, s1['id'], {'updated_at': past})
        instance_id2 = self._create_instance()
        self.assertRaises(driver.NoValidHost,
                          self.scheduler.driver.schedule_run_instance,
                          self.context,
                          instance_id2)
        db.instance_destroy(self.context, instance_id2)
        compute1.kill()

    @attr(kind='small')
    def test_schedule_run_instance_exception_instance_not_found(self):
        """Ensure raise exception when instance dose not exist"""
        compute1 = self.start_service('compute', host='host1')
        instance_id = 99999
        self.assertRaises(exception.InstanceNotFound,
                          self.scheduler.driver.schedule_run_instance,
                          self.context,
                          instance_id)
        compute1.kill()

    @attr(kind='small')
    def test_schedule_run_instance_exception_binary_not_found(self):
        """Ensure raise exception when host binary dose not exist"""
        compute1 = service.Service('host1',
                                   'nova-compute',
                                   'compute',
                                   FLAGS.compute_manager)
        compute1.start()
        compute2 = service.Service('host2',
                                   'nova-compute',
                                   'compute',
                                   FLAGS.compute_manager)
        compute2.start()
        instance_id1 = self._create_instance()
        compute1.run_instance(self.context, instance_id1)
        instance_id2 = self._create_instance(availability_zone='nova:host9')
        self.assertRaises(exception.HostBinaryNotFound,
                          self.scheduler.driver.schedule_run_instance,
                          self.context,
                          instance_id2)
        compute1.terminate_instance(self.context, instance_id1)
        compute1.kill()
        compute2.kill()

    @attr(kind='small')
    def test_schedule_create_volume_database_service_get(self):
        """Ensure raise exception when volume services can not be obtained"""
        volume_id = self._create_volume()
        self.assertRaises(driver.NoValidHost,
                          self.scheduler.driver.schedule_create_volume,
                          self.context, volume_id)

    @attr(kind='small')
    def test_schedule_create_volume_database_availability_zone(self):
        """Ensures the host with less gigabytes gets the next one"""
        volume1 = service.Service('host1',
                                   'nova-volume',
                                   'volume',
                                   FLAGS.volume_manager)
        volume1.start()
        volume2 = service.Service('host2',
                                   'nova-volume',
                                   'volume',
                                   FLAGS.volume_manager)
        volume2.start()
        volume_id1 = self._create_volume()
        volume1.create_volume(self.context, volume_id1)
        volume_id2 = self._create_volume(availability_zone='nova:host2')
        host = self.scheduler.driver.schedule_create_volume(self.context,
                                                            volume_id2)
        self.assertEqual(host, 'host2')

        volume1.delete_volume(self.context, volume_id1)
        db.volume_destroy(self.context, volume_id2)
        volume1.kill()
        volume2.kill()

    @attr(kind='small')
    def test_schedule_create_volume_cfg_not_available(self):
        """Ensure raise exception when host not available"""
        volume1 = service.Service('host1',
                                   'nova-volume',
                                   'volume',
                                   FLAGS.volume_manager)
        volume1.start()
        volume2 = service.Service('host2',
                                   'nova-volume',
                                   'volume',
                                   FLAGS.volume_manager)
        volume2.start()

        volume_id1 = self._create_volume()
        volume1.create_volume(self.context, volume_id1)

        s1 = db.service_get_by_args(self.context, 'host2', 'nova-volume')
        now = utils.utcnow()
        delta = datetime.timedelta(seconds=FLAGS.service_down_time * 2)
        past = now - delta
        db.service_update(self.context, s1['id'], {'updated_at': past})

        volume_id2 = self._create_volume(availability_zone='nova:host2')
        self.assertRaises(driver.WillNotSchedule,
                          self.scheduler.driver.schedule_create_volume,
                          self.context, volume_id2)

        volume1.delete_volume(self.context, volume_id1)
        db.volume_destroy(self.context, volume_id2)
        volume1.kill()
        volume2.kill()

    @attr(kind='small')
    def test_schedule_create_volume_configuration_service_is_down(self):
        """Ensure raise exception when host not available"""
        volume1 = service.Service('host1',
                                   'nova-volume',
                                   'volume',
                                   FLAGS.volume_manager)
        volume1.start()
        s1 = db.service_get_by_args(self.context, 'host1', 'nova-volume')
        now = utils.utcnow()
        delta = datetime.timedelta(seconds=FLAGS.service_down_time * 2)
        past = now - delta
        db.service_update(self.context, s1['id'], {'updated_at': past})
        volume_id1 = self._create_volume()
        self.assertRaises(driver.NoValidHost,
                          self.scheduler.driver.schedule_create_volume,
                          self.context, volume_id1)
        db.volume_destroy(self.context, volume_id1)
        volume1.kill()

    @attr(kind='small')
    def test_schedule_create_volume_exception_instance_not_found(self):
        """Ensure raise exception when instance dose not exist"""
        compute1 = self.start_service('compute', host='host1')
        volume_id = 99999
        self.assertRaises(exception.VolumeNotFound,
                          self.scheduler.driver.schedule_create_volume,
                          self.context,
                          volume_id)
        compute1.kill()

    @attr(kind='small')
    def test_schedule_create_volume_exception_binary_not_found(self):
        """Ensure raise exception when host binary dose not exist"""
        volume1 = service.Service('host1',
                                   'nova-volume',
                                   'volume',
                                   FLAGS.volume_manager)
        volume1.start()
        volume2 = service.Service('host2',
                                   'nova-volume',
                                   'volume',
                                   FLAGS.volume_manager)
        volume2.start()
        volume_id1 = self._create_volume()
        volume1.create_volume(self.context, volume_id1)
        volume_id2 = self._create_volume(availability_zone='nova:host9')
        self.assertRaises(exception.HostBinaryNotFound,
                          self.scheduler.driver.schedule_create_volume,
                          self.context,
                          volume_id2)

        volume1.delete_volume(self.context, volume_id1)
        volume1.kill()
        volume2.kill()

    @attr(kind='small')
    def test_schedule_set_network_host(self):
        """Ensure return host name"""
        nt = self.start_service('network', host='host3')
        host = self.scheduler.driver.schedule_set_network_host(self.context)
        self.assertEqual('host3', host)
        nt.kill()

    @attr(kind='small')
    def test_schedule_set_network_host_database_service_get(self):
        """Ensure raise exception when network services can not be obtained"""
        self.assertRaises(driver.NoValidHost,
                          self.scheduler.driver.schedule_set_network_host,
                          self.context)

    @attr(kind='small')
    def test_schedule_set_network_host_configuration_too_many_networks(self):
        """Ensure raise exception when over max networks"""
        self.flags(max_networks=0)
        nt = self.start_service('network', host='host4')
        self.assertRaises(driver.NoValidHost,
                          self.scheduler.driver.schedule_set_network_host,
                          self.context)
        nt.kill()

    @attr(kind='small')
    def test_schedule_set_network_host_configuration_service_is_down(self):
        """Ensure raise exception when host not available"""
        nt = self.start_service('network', host='host5')
        s1 = db.service_get_by_args(self.context, 'host5', 'nova-network')
        now = utils.utcnow()
        delta = datetime.timedelta(seconds=FLAGS.service_down_time * 2)
        past = now - delta
        db.service_update(self.context, s1['id'], {'updated_at': past})
        self.assertRaises(driver.NoValidHost,
                          self.scheduler.driver.schedule_set_network_host,
                          self.context)
        nt.kill()
