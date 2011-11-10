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


class LibvirtOpenVswitchDriverTestCase(test.TestCase):
    """Test for nova.virt.libvirt.vif.LibvirtOpenVswitchDriver. """
    def setUp(self):
        super(LibvirtOpenVswitchDriverTestCase, self).setUp()
        self.libvirtopenvswitchdriver = vif.LibvirtOpenVswitchDriver()

    @attr(kind='small')
    def test_plug_parameter_process_execution_error_occur(self):
        """Test for nova.virt.libvirt.vif.LibvirtOpenVswitchDriver.plug. """

        def fake_linux_net_device_exists(*args, **kwargs):
            self.stub_linux_flg = False

        def fake_utils_execute_ip_link_set_up(*cmd, **kwargs):
            if cmd[4] == 'mode':
                pass
            elif cmd[4] == 'up':
                raise exception.ProcessExecutionError
            elif cmd[4] == 'down':
                self.stub_flg = True

        self.stubs.Set(linux_net,
                       '_device_exists',
                       fake_linux_net_device_exists)
        self.stubs.Set(utils, 'execute', fake_utils_execute_ip_link_set_up)
        self.assertRaises(exception.ProcessExecutionError,
                          self.libvirtopenvswitchdriver.plug,
                          instance=instances[1],
                          network=networks[0],
                          mapping=info[0])
        self.assertTrue(self.stub_flg)
