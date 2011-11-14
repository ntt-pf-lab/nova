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
Tests For nova.virt.vif
"""

from nova import test
from nova.virt import vif
from nose.plugins.attrib import attr


class AbstarctVIFDriverTestCase(test.TestCase):
    """Test for nova.virt.vif.VIFDriver. """

    @attr(kind='small')
    def test_plug(self):
        """Test for nova.virt.vif.VIFDriver.plug. """
        self.vifdriver = vif.VIFDriver()
        self.assertRaises(NotImplementedError, self.vifdriver.plug,
                          'fake_instance', 'fake_network', 'fake_mapping')

    @attr(kind='small')
    def test_unplug(self):
        """Test for nova.virt.vif.VIFDriver.unplug. """
        self.vifdriver = vif.VIFDriver()
        self.assertRaises(NotImplementedError, self.vifdriver.unplug,
                          'fake_instance', 'fake_network', 'fake_mapping')
