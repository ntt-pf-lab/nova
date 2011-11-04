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
Tests For nova.compute.utils
"""

import mox
from nova import db
from nova import exception
from nova import test
from nova.compute import utils
from nova.volume import api as volume_api
from nose.plugins.attrib import attr

block_device_mappings = [{'id': 1,
                          'volume_id': 'vol-00000001',
                          'delete_on_termination': False},
                          {'id': 2,
                          'volume_id': 'vol-00000002',
                          'delete_on_termination': True}]


class UtilsTestCase(test.TestCase):
    """Test for nova.compute.utils. """
    def setUp(self):
        super(UtilsTestCase, self).setUp()
        self.utils = utils
        self.context = None

    @attr(kind='small')
    def test_terminate_volumes(self):
        """Test for nova.compute.utils.terminate_volumes. """
        self._bdm_id = None

        def stub_block_device_mapping_destroy(context, bdm_id):
            self._bdm_id = bdm_id

        self.mox.StubOutWithMock(db,
                            'block_device_mapping_get_all_by_instance')
        self.stubs.Set(db, 'block_device_mapping_destroy',
                            stub_block_device_mapping_destroy)
        db.block_device_mapping_get_all_by_instance(mox.IgnoreArg(),
                                                    mox.IgnoreArg()).\
                                AndReturn([block_device_mappings[0]])
        self.mox.ReplayAll()

        self.utils.terminate_volumes(db, self.context, 1)
        self.assertEqual(block_device_mappings[0]['id'], self._bdm_id)

    @attr(kind='small')
    def test_terminate_volumes_param_instance_not_found(self):
        """
        InstanceNotFound is raised when specified instance is not found
        """
        self.assertRaises(exception.InstanceNotFound,
                          self.utils.terminate_volumes,
                          db, self.context, 99999)

    @attr(kind='small')
    def test_terminate_volumes_db_bdm_delete_on_termination_is_true(self):
        """Test for nova.compute.utils.terminate_volumes. """
        self._volume_id = None

        def stub_delete(caller, context, volume_id):
            self._volume_id = volume_id

        self.mox.StubOutWithMock(db,
                            'block_device_mapping_get_all_by_instance')
        self.stubs.Set(volume_api.API, 'delete', stub_delete)
        self.mox.StubOutWithMock(db, 'block_device_mapping_destroy')
        db.block_device_mapping_get_all_by_instance(mox.IgnoreArg(),
                                                    mox.IgnoreArg()).\
                                AndReturn([block_device_mappings[1]])
        db.block_device_mapping_destroy(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        self.utils.terminate_volumes(db, self.context, 1)
        self.assertEqual(block_device_mappings[1]['volume_id'],
                         self._volume_id)

    @attr(kind='small')
    def test_terminate_volumes_ex_volume_api_delete(self):
        """
        All BlockDeviceMappings are deleted
        even when exception is raised in volume_api.delete()
        """
        self._count = 0

        def stub_delete(caller, context, volume_id):
            self._count += 1
            raise exception.ApiError()

        self.mox.StubOutWithMock(db,
                            'block_device_mapping_get_all_by_instance')
        self.stubs.Set(volume_api.API, 'delete', stub_delete)
        self.mox.StubOutWithMock(db, 'block_device_mapping_destroy')
        db.block_device_mapping_get_all_by_instance(mox.IgnoreArg(),
                                                    mox.IgnoreArg()).\
                                            AndReturn(block_device_mappings)
        db.block_device_mapping_destroy(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        self.assertRaises(exception.ApiError, self.utils.terminate_volumes,
                          db, self.context, 1)
        self.assertEqual(2, self._count)
