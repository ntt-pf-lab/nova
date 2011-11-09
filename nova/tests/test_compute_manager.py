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

from nova import db
from nova import compute
from nova import context
from nova import test
from nova import utils
from nova import flags
from nova import volume
from nova import exception
from nova import block_device
from nova.compute import instance_types
from nova.notifier import test_notifier
from nose.plugins.attrib import attr
import nova.image.fake

FLAGS = flags.FLAGS
flags.DECLARE('stub_network', 'nova.compute.manager')

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

    @attr(kind='small')
    def test_setup_block_device_mapping_database_vol_id_is_none(self):
        """ Ensure raise exception(RebuildRequiresActiveInstance)
            when corrupted state of block device mapping """
        def stub_bdm_get(context, instance_id):
            return [{'volume_id': None,
                    'snapshot_id': 1,
                    'no_device': None,
                    'virtual_name': None,
                    'delete_on_termination': True,
                    'volume_size': None,
                    'snapshot': None,
                    'id': 5,
                    'device_name': '/dev/sda'}]

        def stub_is_ephemeral(device_name):
            return device_name

        def stub_volume_api_create(*args, **kwargs):
            return {'id': None}

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

        c = context.get_admin_context()
        instance_id = self._create_instance()
        self.assertRaises(exception.RebuildRequiresActiveInstance,
                          self.compute._setup_block_device_mapping,
                          c,
                          instance_id)
