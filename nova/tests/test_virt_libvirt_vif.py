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
Tests For nova.virt.libvirt.vif
"""

from nova import exception
from nova import flags
from nova import test
from nova import utils
from nova import log as logging
from nova.network import linux_net
from nova.virt.libvirt import vif
from nova.virt.libvirt import connection
from nova.virt import libvirt
from nose.plugins.attrib import attr

LOG = logging.getLogger('nova.virt.libvirt.vif')
FLAGS = flags.FLAGS

instances = [{'id': 0,
              'host': 'fake_instance00',
              'hostname': 'fake_instance00',
              'created_at': utils.utcnow(),
              'updated_at': None},
             {'id': 1,
              'host': 'fake_instance01',
              'hostname': 'fake_instance01',
              'name': 'test_instances_name',
              'created_at': utils.utcnow(),
              'updated_at': utils.utcnow()}]

networks = [{'id': 0,
             'uuid': "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
             'label': 'test0',
             'injected': False,
             'multi_host': False,
             'cidr': '192.168.0.0/24',
             'cidr_v6': '2001:db8::/64',
             'gateway_v6': '2001:db8::1',
             'netmask_v6': '64',
             'netmask': '255.255.255.0',
             'bridge': 'fa0',
             'bridge_interface': 'fake_fa0',
             'gateway': '192.168.0.1',
             'broadcast': '192.168.0.255',
             'dns1': '192.168.0.1',
             'dns2': '192.168.0.2',
             'dhcp_server': '0.0.0.0',
             'dhcp_start': '192.168.100.1',
             'vlan': None,
             'host': None,
             'project_id': 'fake_project',
             'vpn_public_address': '192.168.0.2'},
            {'id': 1,
             'uuid': None,
             'label': 'test1',
             'injected': False,
             'multi_host': False,
             'cidr': '192.168.1.0/24',
             'cidr_v6': '2001:db9::/64',
             'gateway_v6': '2001:db9::1',
             'netmask_v6': '64',
             'netmask': '255.255.255.0',
             'bridge': 'fa1',
             'bridge_interface': 'fake_fa1',
             'gateway': '192.168.1.1',
             'broadcast': '192.168.1.255',
             'dns1': '192.168.0.1',
             'dns2': '192.168.0.2',
             'dhcp_server': '0.0.0.0',
             'dhcp_start': '192.168.100.1',
             'vlan': None,
             'host': None,
             'project_id': 'fake_project',
             'vpn_public_address': '192.168.1.2'}]

info = [{'id':0,
        'label': 'fake',
        'gateway': 'fake',
        'dhcp_server': 'fake',
        'broadcast': 'fake',
        'mac': 'DE:AD:BE:EF:00:00',
        'vif_uuid': 'fake',
        'rxtx_cap': 'fake',
        'dns': [],
        'ips': [{'ip': '10.0.0.1'}],
        'should_create_bridge': False,
        'should_create_vlan': False,
        'gateway6': '2001:db8:0:%x::1'},
        {'id':1,
        'label': 'fake',
        'gateway': 'fake',
        'dhcp_server': 'fake',
        'broadcast': 'fake',
        'mac': 'fake',
        'vif_uuid': 'fake',
        'rxtx_cap': 'fake',
        'dns': [],
        'ips': [{'ip': '10.0.0.1'}],
        'should_create_bridge': False,
        'should_create_vlan': False,
        'gateway6': None},
        {'id':2,
        'label': 'fake',
        'gateway': 'fake',
        'dhcp_server': 'fake',
        'broadcast': 'fake',
        'mac': 'fake',
        'vif_uuid': 'fake',
        'rxtx_cap': 'fake',
        'dns': [],
        'ips': [{'ip': '10.0.0.1'}],
        'should_create_bridge': True,
        'should_create_vlan': False,
        'gateway6': None},
        {'id':3,
        'label': 'fake',
        'gateway': 'fake',
        'dhcp_server': 'fake',
        'broadcast': 'fake',
        'mac': 'fake',
        'vif_uuid': 'fake',
        'rxtx_cap': 'fake',
        'dns': [],
        'ips': [{'ip': '10.0.0.1'}],
        'should_create_bridge': True,
        'should_create_vlan': True,
        'gateway6': None}]


class LibvirtBridgeDriverTestCase(test.TestCase):
    """Test for nova.virt.libvirt.vif.LibvirtBridgeDriver. """
    def setUp(self):
        super(LibvirtBridgeDriverTestCase, self).setUp()
        self.libvirtbridgedriver = vif.LibvirtBridgeDriver()

    @attr(kind='small')
    def test_get_configuration_flags_use_ipv6_is_false(self):
        """Test for nova.virt.libvirt.vif.LibvirtBridgeDriver.plug. """
        self.flags(use_ipv6=False)
        ref = self.libvirtbridgedriver.plug(instance=instances[0],
                                            network=networks[0],
                                            mapping=info[0])
        self.ref_flg = False
        if "PROJNETV6" and "PROJMASKV6" not in ref.get('extra_params'):
            self.ref_flg = True
        self.assert_(self.ref_flg)

    @attr(kind='small')
    def test_get_configuration_flags_use_ipv6_is_true(self):
        """Test for nova.virt.libvirt.vif.LibvirtBridgeDriver.plug. """
        ref = self.libvirtbridgedriver.plug(instance=instances[0],
                                            network=networks[0],
                                            mapping=info[0])
        self.ref_flg = False
        if "PROJNETV6" and "PROJMASKV6" in ref.get('extra_params'):
            self.ref_flg = True
        self.assert_(self.ref_flg)

    @attr(kind='small')
    def test_get_configuration_flags_allow_same_net_traffic_is_false(self):
        """Test for nova.virt.libvirt.vif.LibvirtBridgeDriver.plug. """
        self.flags(allow_same_net_traffic=False)
        ref = self.libvirtbridgedriver.plug(instance=instances[0],
                                            network=networks[0],
                                            mapping=info[0])
        self.assertEqual("\n", ref.get('extra_params'))

    @attr(kind='small')
    def test_get_configuration_parameter_gateway6_is_none(self):
        """Test for nova.virt.libvirt.vif.LibvirtBridgeDriver.plug. """
        self.flags(allow_same_net_traffic=False)
        ref = self.libvirtbridgedriver.plug(instance=instances[0],
                                            network=networks[0],
                                            mapping=info[1])
        self.ref_flg = True
        if 'gateway6' in ref:
            self.ref_flg = False
        self.assert_(self.ref_flg)

    @attr(kind='small')
    def test_get_configuration_parameter_gateway6_has_value(self):
        """Test for nova.virt.libvirt.vif.LibvirtBridgeDriver.plug. """
        self.flags(allow_same_net_traffic=False)
        ref = self.libvirtbridgedriver.plug(instance=instances[0],
                                            network=networks[0],
                                            mapping=info[0])
        result = ref.get('gateway6')
        expected_result = '2001:db8:0:%x::1/128'
        self.assertEquals(expected_result, result)

    @attr(kind='small')
    def test_plug(self):
        """Test for nova.virt.libvirt.vif.LibvirtBridgeDriver.plug. """
        ref = self.libvirtbridgedriver.plug(instance=instances[0],
                                            network=networks[0],
                                            mapping=info[0])
        expected_result = {'mac_address': 'DE:AD:BE:EF:00:00',
                        'gateway6': '2001:db8:0:%x::1/128',
                        'bridge_name': 'fa0',
                        'extra_params':
                        '<parameter name="PROJNET"value="192.168.0.0" />\n'
                        '<parameter name="PROJMASK"value="255.255.255.0" />\n'
                        '<parameter name="PROJNETV6"value="2001:db8::" />\n'
                        '<parameter name="PROJMASKV6"value="64" />\n',
                        'dhcp_server': 'fake',
                        'ip_address': '10.0.0.1',
                        'id': 'DEADBEEF0000'}

        self.assertEqual(expected_result, ref)

    @attr(kind='small')
    def test_plug_parameter_should_create_vlan_is_false(self):
        """Test for nova.virt.libvirt.vif.LibvirtBridgeDriver.plug. """
        self.stub_flg_for_debug = False

        def fake_debug_log(msg, *args, **kwargs):
            if 'Ensuring bridge' in msg:
                self.stub_flg_for_debug = True

        self.stubs.Set(LOG, 'debug', fake_debug_log)
        self.libvirtbridgedriver.plug(instance=instances[0],
                                      network=networks[0],
                                      mapping=info[2])
        self.assert_(self.stub_flg_for_debug)

    @attr(kind='small')
    def test_plug_parameter_should_create_vlan_is_true(self):
        """Test for nova.virt.libvirt.vif.LibvirtBridgeDriver.plug. """
        self.stub_flg_for_debug = False

        def fake_debug_log(msg, *args, **kwargs):
            if 'Ensuring vlan' in msg:
                self.stub_flg_for_debug = True

        self.stubs.Set(LOG, 'debug', fake_debug_log)
        self.libvirtbridgedriver.plug(instance=instances[0],
                                      network=networks[0],
                                      mapping=info[3])
        self.assert_(self.stub_flg_for_debug)

    @attr(kind='small')
    def test_unplug(self):
        """Test for nova.virt.libvirt.vif.LibvirtBridgeDriver.unplug. """
        ref = self.libvirtbridgedriver.unplug(instance=instances[0],
                                              network=networks[0],
                                              mapping=info[0])
        self.assertEqual(None, ref)


class LibvirtOpenVswitchDriverTestCase(test.TestCase):
    """Test for nova.virt.libvirt.vif.LibvirtOpenVswitchDriver. """
    def setUp(self):
        super(LibvirtOpenVswitchDriverTestCase, self).setUp()
        self.libvirtopenvswitchdriver = vif.LibvirtOpenVswitchDriver()

    @attr(kind='small')
    def test_plug(self):
        """Test for nova.virt.libvirt.vif.LibvirtOpenVswitchDriver.plug. """
        self.stub_num = 1

        def fake_utils_execute(*args, **kwargs):
            self.stub_num += 1

        self.stubs.Set(utils, 'execute', fake_utils_execute)
        ref = self.libvirtopenvswitchdriver.plug(instance=instances[0],
                                                 network=networks[0],
                                                 mapping=info[0])
        self.assertEquals(2, self.stub_num)
        expected_result = {'mac_address': 'DE:AD:BE:EF:00:00',
                           'name': 'tapfake',
                           'script': ''}
        self.assertEquals(expected_result, ref)

    @attr(kind='small')
    def test_plug_parameter_linux_net_device_exists_is_none(self):
        """Test for nova.virt.libvirt.vif.LibvirtOpenVswitchDriver.plug. """
        self.stub_linux_flg = False
        self.stub_execute_flg = False
        self.stub_num = 0

        def fake_linux_net_device_exists(*args, **kwargs):
            self.stub_linux_flg = True

        def fake_utils_execute(*args, **kwargs):
            self.stub_num += 1
            if self.stub_num == 3:
                self.stub_execute_flg = True

        self.stubs.Set(linux_net,
                       '_device_exists',
                       fake_linux_net_device_exists)
        self.stubs.Set(utils, 'execute', fake_utils_execute)
        ref = self.libvirtopenvswitchdriver.plug(instance=instances[1],
                                                 network=networks[1],
                                                 mapping=info[0])
        self.assert_(self.stub_linux_flg)
        self.assert_(self.stub_execute_flg)
        expected_result = {'mac_address': 'DE:AD:BE:EF:00:00',
                           'name': 'tapfake',
                           'script': ''}
        self.assertEqual(expected_result, ref)

    @attr(kind='small')
    def test_plug_exception(self):
        """Test for nova.virt.libvirt.vif.LibvirtOpenVswitchDriver.unplug. """

        def fake_utils_execute_for_plug(*args, **kwargs):
            raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', fake_utils_execute_for_plug)
        self.assertRaises(exception.ProcessExecutionError,
                          self.libvirtopenvswitchdriver.plug,
                          instance=instances[1],
                          network=networks[1],
                          mapping=info[0])

    @attr(kind='small')
    def test_unplug(self):
        """Test for nova.virt.libvirt.vif.LibvirtOpenVswitchDriver.unplug. """
        self.stub_flg = False
        self.stub_num = 0

        def fake_utils_execute(*args, **kwargs):
            self.stub_num += 1
            if self.stub_num == 2:
                self.stub_flg = True

        self.stubs.Set(utils, 'execute', fake_utils_execute)
        self.libvirtopenvswitchdriver.unplug(instance=instances[1],
                                             network=networks[0],
                                             mapping=info[0])
        self.assert_(self.stub_flg)

    @attr(kind='small')
    def test_unplug_exception(self):
        """Test for nova.virt.libvirt.vif.LibvirtOpenVswitchDriver.unplug. """

        def fake_utils_execute_for_unplug(*args, **kwargs):
            raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', fake_utils_execute_for_unplug)
        self.assertRaises(exception.ProcessExecutionError,
                          self.libvirtopenvswitchdriver.unplug,
                          instance=instances[1],
                          network=networks[1],
                          mapping=info[0])
