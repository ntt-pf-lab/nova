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
Tests For nova.manager
"""

import sys
from nova import flags
from nova import manager
from nova import test
from nose.plugins.attrib import attr

FLAGS = flags.FLAGS


class ManagerTestCase(test.TestCase):
    """Test for nova.manager.Manager. """
    def setUp(self):
        super(ManagerTestCase, self).setUp()
        self.manager = manager.Manager('testhost')

    @attr(kind='small')
    def test_init(self):
        """Test for nova.manager.Manager.__init__. """
        ref = manager.Manager('testhost')
        self.assertEqual('testhost', ref.host)
        self.assertTrue(FLAGS.db_driver in sys.modules)

    @attr(kind='small')
    def test_init_parameter_not_host(self):
        """Test for nova.manager.Manager.__init__. """
        ref = manager.Manager()
        self.assertEqual(FLAGS.host, ref.host)
        self.assertTrue(FLAGS.db_driver in sys.modules)

    @attr(kind='small')
    def test_periodic_tasks(self):
        """Test for nova.manager.Manager.periodic_tasks. """
        self.manager.periodic_tasks(None)

    @attr(kind='small')
    def test_init_host(self):
        """Test for nova.manager.Manager.init_host. """
        self.manager.init_host()


class SchedulerDependentManagerTestCase(test.TestCase):
    """Test for nova.manager.SchedulerDependentManager. """
    def setUp(self):
        super(SchedulerDependentManagerTestCase, self).setUp()
        self.manager = manager.SchedulerDependentManager('testhost')

    @attr(kind='small')
    def test_init(self):
        """Test for nova.manager.SchedulerDependentManager.__init__. """
        ref = manager.SchedulerDependentManager('testhost')
        self.assertEqual(None, ref.last_capabilities)
        self.assertEqual('undefined', ref.service_name)
        self.assertEqual('testhost', ref.host)
        self.assertTrue(FLAGS.db_driver in sys.modules)

    @attr(kind='small')
    def test_update_service_capabilities(self):
        """
        Test for nova.manager.SchedulerDependentManager
                             .update_service_capabilities."""
        capabilities = {'a': 1}
        self.manager.update_service_capabilities(capabilities)
        self.assertEqual(capabilities, self.manager.last_capabilities)

    @attr(kind='small')
    def test_periodic_tasks_configuration_not_last_capabilities(self):
        """Test for nova.manager.SchedulerDependentManager.periodic_tasks. """
        self._count = 0

        def stub_update_service_capabilities(
                            context, service_name, host, capabilities):
            self._count += 1

        self.stubs.Set(manager.api, "update_service_capabilities",
                                    stub_update_service_capabilities)

        self.manager.periodic_tasks()
        self.assertEqual(0, self._count)

    @attr(kind='small')
    def test_periodic_tasks_configuration_last_capabilities(self):
        """Test for nova.manager.SchedulerDependentManager.periodic_tasks. """
        self._context = None
        self._service_name = None
        self._host = None
        self._capabilities = None
        self._count = 0

        def stub_update_service_capabilities(
                            context, service_name, host, capabilities):
            self._context = context
            self._service_name = service_name
            self._host = host
            self._capabilities = capabilities
            self._count += 1

        self.stubs.Set(manager.api, "update_service_capabilities",
                                    stub_update_service_capabilities)

        capabilities = {'a': 1}
        self.manager.update_service_capabilities(capabilities)
        self.manager.periodic_tasks()
        self.assertEqual(None, self._context)
        self.assertEqual('undefined', self._service_name)
        self.assertEqual('testhost', self._host)
        self.assertEqual(capabilities, self._capabilities)
        self.assertEqual(1, self._count)
