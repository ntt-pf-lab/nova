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

from nova import context
from nova import db
from nova import exception
from nova import flags
from nova import log as logging
from nova import test
from nova import utils
from nova.network import manager as network_manager
from nova.network import linux_net

from nose.plugins.attrib import attr
import mox
import shutil
import os

FLAGS = flags.FLAGS

LOG = logging.getLogger('nova.tests.network')

HOST = "testhost"

instances = [{'id': 0,
              'host': 'fake_instance00',
              'hostname': 'fake_instance00',
              'created_at': utils.utcnow(),
              'updated_at': None},
             {'id': 1,
              'host': 'fake_instance01',
              'hostname': 'fake_instance01',
              'created_at': utils.utcnow(),
              'updated_at': utils.utcnow()},
             {'id': 2,
              'host': FLAGS.host,
              'hostname': FLAGS.host,
              'created_at': utils.utcnow(),
              'updated_at': utils.utcnow()}]

addresses = [{"address": "10.0.0.1"},
             {"address": "10.0.0.2"},
             {"address": "10.0.0.3"},
             {"address": "10.0.0.4"},
             {"address": "10.0.0.5"},
             {"address": "10.0.0.6"},
             {"address": "10.0.0.7"}]

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
             'uuid': "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
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
             'vpn_public_address': '192.168.1.2'},
            {'id': 2,
             'uuid': "cccccccc-cccc-cccc-cccc-cccccccccccc",
             'label': 'test3',
             'injected': False,
             'multi_host': True,
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
             'vlan': 100,
             'host': None,
             'project_id': 'fake_project',
             'vpn_public_address': '192.168.1.2'}]

fixed_ips = [{'id': 0,
              'network_id': 0,
              'address': '192.168.0.100',
              'instance_id': 0,
              'allocated': True,
              'virtual_interface_id': 0,
              'virtual_interface': addresses[0],
              'instance': instances[0],
              'floating_ips': []},
             {'id': 1,
              'network_id': 1,
              'address': '192.168.1.100',
              'instance_id': 0,
              'allocated': True,
              'virtual_interface_id': 1,
              'virtual_interface': addresses[1],
              'instance': instances[0],
              'floating_ips': []},
             {'id': 2,
              'network_id': 1,
              'address': '192.168.0.101',
              'instance_id': 1,
              'allocated': True,
              'virtual_interface_id': 2,
              'virtual_interface': addresses[2],
              'instance': instances[1],
              'floating_ips': []},
             {'id': 3,
              'network_id': 0,
              'address': '192.168.1.101',
              'instance_id': 1,
              'allocated': True,
              'virtual_interface_id': 3,
              'virtual_interface': addresses[3],
              'instance': instances[1],
              'floating_ips': []},
             {'id': 4,
              'network_id': 0,
              'address': '192.168.0.102',
              'instance_id': 0,
              'allocated': True,
              'virtual_interface_id': 4,
              'virtual_interface': addresses[4],
              'instance': instances[0],
              'floating_ips': []},
             {'id': 5,
              'network_id': 1,
              'address': '192.168.1.102',
              'instance_id': 1,
              'allocated': True,
              'virtual_interface_id': 5,
              'virtual_interface': addresses[5],
              'instance': instances[1],
              'floating_ips': []},
             {'id': 6,
              'network_id': 1,
              'address': '192.168.1.102',
              'instance_id': 2,
              'allocated': True,
              'virtual_interface_id': 6,
              'virtual_interface': addresses[6],
              'instance': instances[2],
              'floating_ips': []}]

vifs = [{'id': 0,
         'address': 'DE:AD:BE:EF:00:00',
         'uuid': '00000000-0000-0000-0000-0000000000000000',
         'network_id': 0,
         'network': networks[0],
         'instance_id': 0},
        {'id': 1,
         'address': 'DE:AD:BE:EF:00:01',
         'uuid': '00000000-0000-0000-0000-0000000000000001',
         'network_id': 1,
         'network': networks[1],
         'instance_id': 0},
        {'id': 2,
         'address': 'DE:AD:BE:EF:00:02',
         'uuid': '00000000-0000-0000-0000-0000000000000002',
         'network_id': 1,
         'network': networks[1],
         'instance_id': 1},
        {'id': 3,
         'address': 'DE:AD:BE:EF:00:03',
         'uuid': '00000000-0000-0000-0000-0000000000000003',
         'network_id': 0,
         'network': networks[0],
         'instance_id': 1},
        {'id': 4,
         'address': 'DE:AD:BE:EF:00:04',
         'uuid': '00000000-0000-0000-0000-0000000000000004',
         'network_id': 0,
         'network': networks[0],
         'instance_id': 0},
        {'id': 5,
         'address': 'DE:AD:BE:EF:00:05',
         'uuid': '00000000-0000-0000-0000-0000000000000005',
         'network_id': 1,
         'network': networks[1],
         'instance_id': 1},
        {'id': 6,
         'address': 'DE:AD:BE:EF:00:06',
         'uuid': '00000000-0000-0000-0000-0000000000000005',
         'network_id': 1,
         'network': networks[2],
         'instance_id': 2}]


class LinuxNetworkTestCase(test.TestCase):

    def setUp(self):
        super(LinuxNetworkTestCase, self).setUp()
        network_driver = FLAGS.network_driver
        self.driver = utils.import_object(network_driver)
        self.driver.db = db

    def test_update_dhcp_for_nw00(self):
        self.flags(use_single_default_gateway=True,
                   fake_network=False)
        self.cmd = None

        def stub_utils_execute(*cmd, **kwargs):
            if cmd[0] == 'FLAGFILE=%s' % FLAGS.dhcpbridge_flagfile:
                self.cmd = cmd
            return 'fake', ''

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        self.mox.StubOutWithMock(db, 'network_get_associated_fixed_ips')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')

        db.network_get_associated_fixed_ips(mox.IgnoreArg(),
                                            mox.IgnoreArg())\
                                            .AndReturn([fixed_ips[0],
                                                        fixed_ips[3]])

        db.network_get_associated_fixed_ips(mox.IgnoreArg(),
                                            mox.IgnoreArg())\
                                            .AndReturn([fixed_ips[0],
                                                        fixed_ips[3]])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg())\
                                             .AndReturn([vifs[0], vifs[1]])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg())\
                                             .AndReturn([vifs[2], vifs[3]])
        self.mox.ReplayAll()

        self.driver.update_dhcp(None, "eth0", networks[0])
        self.assertEqual(self.cmd[1],
                         'NETWORK_ID=%s' % str(networks[0]['id']))
        self.assertEqual(self.cmd[8],
                         '--listen-address=%s' % networks[0]['dhcp_server'])
        self.assertEqual(self.cmd[10],
                         '--dhcp-range=%s,static,120s'
                          % networks[0]['dhcp_start'])

        # use_single_default_gateway=True
        self.assertEqual(self.cmd[15],
                         '--dhcp-optsfile=%s'
                          % linux_net._dhcp_file("eth0", 'opts'))

    def test_update_dhcp_for_nw01(self):
        self.flags(use_single_default_gateway=True)
        self.mox.StubOutWithMock(db, 'network_get_associated_fixed_ips')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')

        db.network_get_associated_fixed_ips(mox.IgnoreArg(),
                                            mox.IgnoreArg())\
                                            .AndReturn([fixed_ips[1],
                                                        fixed_ips[2]])

        db.network_get_associated_fixed_ips(mox.IgnoreArg(),
                                            mox.IgnoreArg())\
                                            .AndReturn([fixed_ips[1],
                                                        fixed_ips[2]])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg())\
                                             .AndReturn([vifs[0], vifs[1]])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg())\
                                             .AndReturn([vifs[2], vifs[3]])
        self.mox.ReplayAll()

        self.driver.update_dhcp(None, "eth0", networks[0])

    def test_get_dhcp_hosts_for_nw00(self):
        self.flags(use_single_default_gateway=True)
        self.mox.StubOutWithMock(db, 'network_get_associated_fixed_ips')

        db.network_get_associated_fixed_ips(mox.IgnoreArg(),
                                            mox.IgnoreArg())\
                                            .AndReturn([fixed_ips[0],
                                                        fixed_ips[3]])
        self.mox.ReplayAll()

        expected = \
        "10.0.0.1,fake_instance00.novalocal,"\
            "192.168.0.100,net:NW-i00000000-0\n"\
        "10.0.0.4,fake_instance01.novalocal,"\
            "192.168.1.101,net:NW-i00000001-0"
        actual_hosts = self.driver.get_dhcp_hosts(None, networks[1])

        self.assertEquals(actual_hosts, expected)

    def test_get_dhcp_hosts_for_nw01(self):
        self.flags(use_single_default_gateway=True)
        self.mox.StubOutWithMock(db, 'network_get_associated_fixed_ips')

        db.network_get_associated_fixed_ips(mox.IgnoreArg(),
                                            mox.IgnoreArg())\
                                            .AndReturn([fixed_ips[1],
                                                        fixed_ips[2]])
        self.mox.ReplayAll()

        expected = \
        "10.0.0.2,fake_instance00.novalocal,"\
            "192.168.1.100,net:NW-i00000000-1\n"\
        "10.0.0.3,fake_instance01.novalocal,"\
            "192.168.0.101,net:NW-i00000001-1"
        actual_hosts = self.driver.get_dhcp_hosts(None, networks[0])

        self.assertEquals(actual_hosts, expected)

    def test_get_dhcp_opts_for_nw00(self):
        self.mox.StubOutWithMock(db, 'network_get_associated_fixed_ips')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')

        db.network_get_associated_fixed_ips(mox.IgnoreArg(),
                                            mox.IgnoreArg())\
                                            .AndReturn([fixed_ips[0],
                                                        fixed_ips[3],
                                                        fixed_ips[4]])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg())\
                                             .AndReturn([vifs[0],
                                                         vifs[1],
                                                         vifs[4]])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg())\
                                             .AndReturn([vifs[2],
                                                         vifs[3],
                                                         vifs[5]])
        self.mox.ReplayAll()

        expected_opts = 'NW-i00000001-0,3'
        actual_opts = self.driver.get_dhcp_opts(None, networks[0])

        self.assertEquals(actual_opts, expected_opts)

    def test_get_dhcp_opts_for_nw01(self):
        self.mox.StubOutWithMock(db, 'network_get_associated_fixed_ips')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')

        db.network_get_associated_fixed_ips(mox.IgnoreArg(),
                                            mox.IgnoreArg())\
                                            .AndReturn([fixed_ips[1],
                                                        fixed_ips[2],
                                                        fixed_ips[5]])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg())\
                                             .AndReturn([vifs[0],
                                                         vifs[1],
                                                         vifs[4]])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg())\
                                             .AndReturn([vifs[2],
                                                         vifs[3],
                                                         vifs[5]])
        self.mox.ReplayAll()

        expected_opts = "NW-i00000000-1,3"
        actual_opts = self.driver.get_dhcp_opts(None, networks[1])

        self.assertEquals(actual_opts, expected_opts)

    def test_dhcp_opts_not_default_gateway_network(self):
        expected = "NW-i00000000-0,3"
        actual = self.driver._host_dhcp_opts(fixed_ips[0])
        self.assertEquals(actual, expected)

    def test_host_dhcp_without_default_gateway_network(self):
        expected = ("10.0.0.1,fake_instance00.novalocal,192.168.0.100")
        actual = self.driver._host_dhcp(fixed_ips[0])
        self.assertEquals(actual, expected)

    @attr(kind='small')
    def _test_initialize_gateway(self, existing, expected):
        self.flags(fake_network=False)
        executes = []

        def fake_execute(*args, **kwargs):
            if args[0] != 'route':
                executes.append(args)

            if args[0] == 'ip' and args[1] == 'addr' and args[2] == 'show':
                return existing, ""
            elif args[0] == 'route' and args[1] == '-n':
                return ("192.168.0.0 0.0.0.0 255.255.255.0 U 1 0 0 eth0\n"
                        "1.1.1.1 0.0.0.0 255.255.0.0 U 1000 0 0 eth0\n"
                        "0.0.0.0 1.1.1.1 0.0.0.0 UG 0 0 0 eth0"), ""

        self.stubs.Set(utils, 'execute', fake_execute)
        network = {'dhcp_server': '192.168.1.1',
                   'cidr': '192.168.1.0/24',
                   'broadcast': '192.168.1.255',
                   'cidr_v6': '2001:db8::/64'}
        self.driver.initialize_gateway_device('eth0', network)
        self.assertEqual(executes, expected)

    def test_initialize_gateway_moves_wrong_ip(self):
        existing = ("2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> "
            "    mtu 1500 qdisc pfifo_fast state UNKNOWN qlen 1000\n"
            "    link/ether de:ad:be:ef:be:ef brd ff:ff:ff:ff:ff:ff\n"
            "    inet 192.168.0.1/24 brd 192.168.0.255 scope global eth0\n"
            "    inet6 dead::beef:dead:beef:dead/64 scope link\n"
            "    valid_lft forever preferred_lft forever\n")
        expected = [
            ('ip', 'addr', 'show', 'dev', 'eth0', 'scope', 'global'),
            ('ip', 'addr', 'del', '192.168.0.1/24',
             'brd', '192.168.0.255', 'scope', 'global', 'dev', 'eth0'),
            ('ip', 'addr', 'add', '192.168.1.1/24',
             'brd', '192.168.1.255', 'dev', 'eth0'),
            ('ip', 'addr', 'add', '192.168.0.1/24',
             'brd', '192.168.0.255', 'scope', 'global', 'dev', 'eth0'),
            ('ip', '-f', 'inet6', 'addr', 'change',
             '2001:db8::/64', 'dev', 'eth0'),
            ('ip', 'link', 'set', 'dev', 'eth0', 'promisc', 'on'),
        ]
        self._test_initialize_gateway(existing, expected)

    def test_initialize_gateway_no_move_right_ip(self):
        existing = ("2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> "
            "    mtu 1500 qdisc pfifo_fast state UNKNOWN qlen 1000\n"
            "    link/ether de:ad:be:ef:be:ef brd ff:ff:ff:ff:ff:ff\n"
            "    inet 192.168.1.1/24 brd 192.168.1.255 scope global eth0\n"
            "    inet 192.168.0.1/24 brd 192.168.0.255 scope global eth0\n"
            "    inet6 dead::beef:dead:beef:dead/64 scope link\n"
            "    valid_lft forever preferred_lft forever\n")
        expected = [
            ('ip', 'addr', 'show', 'dev', 'eth0', 'scope', 'global'),
            ('ip', '-f', 'inet6', 'addr', 'change',
             '2001:db8::/64', 'dev', 'eth0'),
            ('ip', 'link', 'set', 'dev', 'eth0', 'promisc', 'on'),
        ]
        self._test_initialize_gateway(existing, expected)

    def test_initialize_gateway_add_if_blank(self):
        existing = ("2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> "
            "    mtu 1500 qdisc pfifo_fast state UNKNOWN qlen 1000\n"
            "    link/ether de:ad:be:ef:be:ef brd ff:ff:ff:ff:ff:ff\n"
            "    inet6 dead::beef:dead:beef:dead/64 scope link\n"
            "    valid_lft forever preferred_lft forever\n")
        expected = [
            ('ip', 'addr', 'show', 'dev', 'eth0', 'scope', 'global'),
            ('ip', 'addr', 'add', '192.168.1.1/24',
             'brd', '192.168.1.255', 'dev', 'eth0'),
            ('ip', '-f', 'inet6', 'addr', 'change',
             '2001:db8::/64', 'dev', 'eth0'),
            ('ip', 'link', 'set', 'dev', 'eth0', 'promisc', 'on'),
        ]
        self._test_initialize_gateway(existing, expected)

    @attr(kind='small')
    def test_metadata_forward(self):
        """ Ensure call utils.execute"""
        self.flags(fake_network=False)
        self.stub_flag = False

        def stub_utils_execute(*cmd, **kwargs):

            str = ("-s 0.0.0.0/0 -d 169.254.169.254/32 "
                   "-p tcp -m tcp --dport 80 -j DNAT "
                   "--to-destination %s:%s"
                   % (FLAGS.ec2_dmz_host, FLAGS.ec2_port))

            process_input = ''
            if cmd == ('iptables-restore',):
                process_input = kwargs['process_input']

            if str in process_input:
                self.stub_flag = True

            return 'fake', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        linux_net.metadata_forward()
        self.assert_(self.stub_flag)

    @attr(kind='small')
    def test_metadata_forward_exception_command_failed(self):
        """ Ensure raise exception when command failed"""
        self.flags(fake_network=False)

        def stub_utils_execute(*cmd, **kwargs):
            raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        self.assertRaises(exception.ProcessExecutionError,
                          linux_net.metadata_forward)

    @attr(kind='small')
    def test_init_host(self):
        """ Ensure call utils.execute"""
        self.flags(fake_network=False)
        self.stub_flag = False

        def stub_utils_execute(*cmd, **kwargs):
            str1 = '-s %s -j SNAT --to-source %s' \
                   % (FLAGS.fixed_range, FLAGS.routing_source_ip)
            str2 = '-s %s -d %s -j ACCEPT' \
                   % (FLAGS.fixed_range, FLAGS.dmz_cidr)
            str3 = '-s %(range)s -d %(range)s -j ACCEPT' \
                   % {'range': FLAGS.fixed_range}

            process_input = ''
            if cmd == ('iptables-restore',):
                process_input = kwargs['process_input']

            if (str1 in process_input and
                str2 in process_input and
                str3 in process_input):
                    self.stub_flag = True

            return 'fake', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        linux_net.init_host()
        self.assert_(self.stub_flag)

    @attr(kind='small')
    def test_init_host_exception_command_failed(self):
        """ Ensure raise exception when command failed"""
        self.flags(fake_network=False)

        def stub_utils_execute(*cmd, **kwargs):
            raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        self.assertRaises(exception.ProcessExecutionError,
                          linux_net.init_host)

    @attr(kind='small')
    def test_bind_floating_ip(self):
        """ Ensure call utils.execute"""
        self.flags(fake_network=False)
        self.floating_ip = None

        def stub_utils_execute(*cmd, **kwargs):
            self.floating_ip = cmd[3]
            return 'fake', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        floating_ip = '1.2.3.4'
        linux_net.bind_floating_ip(floating_ip)
        self.assertEquals(floating_ip, self.floating_ip)

    @attr(kind='small')
    def test_bind_floating_ip_configuration_send_arp_true(self):
        """ Ensure call utils.execute when FLAGS.send_arp_for_ha is true"""
        self.flags(fake_network=False,
                   send_arp_for_ha=True)
        self.floating_ip = None

        def stub_utils_execute(*cmd, **kwargs):
            if cmd[0] == 'arping':
                self.floating_ip = cmd[2]
            return 'fake', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        floating_ip = '1.2.3.4'
        linux_net.bind_floating_ip(floating_ip)
        self.assertEquals(floating_ip, self.floating_ip)

    @attr(kind='small')
    def test_bind_floating_ip_exception_command_failed(self):
        """ Ensure raise exception when command failed"""
        self.flags(fake_network=False)

        def stub_utils_execute(*cmd, **kwargs):
            raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        floating_ip = '1.2.3.4'
        self.assertRaises(exception.ProcessExecutionError,
                          linux_net.bind_floating_ip,
                          floating_ip)

    @attr(kind='small')
    def test_unbind_floating_ip(self):
        """ Ensure call utils.execute"""
        self.flags(fake_network=False)
        self.floating_ip = None

        def stub_utils_execute(*cmd, **kwargs):
            self.floating_ip = cmd[3]
            return 'fake', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        floating_ip = '1.2.3.4'
        linux_net.unbind_floating_ip(floating_ip)
        self.assertEquals(floating_ip, self.floating_ip)

    @attr(kind='small')
    def test_unbind_floating_ip_exception_command_failed(self):
        """ Ensure raise exception when command failed"""
        self.flags(fake_network=False)

        def stub_utils_execute(*cmd, **kwargs):
            raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        floating_ip = '1.2.3.4'
        self.assertRaises(exception.ProcessExecutionError,
                          linux_net.unbind_floating_ip,
                          floating_ip)

    @attr(kind='small')
    def test_ensure_metadata_ip(self):
        """ Ensure call utils.execute"""
        self.flags(fake_network=False)
        self.stub_flag = False

        def stub_utils_execute(*cmd, **kwargs):
            if cmd[3] == '169.254.169.254/32':
                self.stub_flag = True
            return 'fake', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        linux_net.ensure_metadata_ip()
        self.assert_(self.stub_flag)

    @attr(kind='small')
    def test_ensure_metadata_ip_exception_command_failed(self):
        """ Ensure raise exception when command failed"""
        self.flags(fake_network=False)

        def stub_utils_execute(*cmd, **kwargs):
            raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        self.assertRaises(exception.ProcessExecutionError,
                          linux_net.ensure_metadata_ip)

    @attr(kind='small')
    def test_ensure_vpn_forward(self):
        """ Ensure call utils.execute"""
        self.flags(fake_network=False)
        self.public_ip = '1.1.1.1'
        self.private_ip = '192.168.1.1'
        self.port = '5000'
        self.stub_cnt = 0

        def stub_utils_execute(*cmd, **kwargs):
            str1 = '-d %s -p udp --dport 1194 -j ACCEPT' \
                   % self.private_ip
            str2 = '-d %s -p udp --dport %s -j DNAT --to %s:1194' \
                   % (self.public_ip, self.port, self.private_ip)
            process_input = ''
            if cmd == ('iptables-restore',):
                process_input = kwargs['process_input']
            if str1 in process_input:
                self.stub_cnt += 1
            elif str2 in process_input:
                self.stub_cnt += 1

            return 'fake', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        linux_net.ensure_vpn_forward(self.public_ip,
                                     self.port, self.private_ip)
        self.assertEquals(2, self.stub_cnt)

    @attr(kind='small')
    def test_ensure_vpn_forward_exception_command_failed(self):
        """ Ensure raise exception when command failed"""
        self.flags(fake_network=False)

        def stub_utils_execute(*cmd, **kwargs):
            raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        self.assertRaises(exception.ProcessExecutionError,
                          linux_net.ensure_vpn_forward,
                          '1.1.1.1', '5000', '192.168.1.1')

    @attr(kind='small')
    def test_ensure_floating_forward(self):
        """ Ensure call utils.execute"""
        self.flags(fake_network=False)
        self.floating_ip = '1,1,1,1'
        self.fixed_ip = '10.10.10.10'
        self.stub_flag = False

        def stub_utils_execute(*cmd, **kwargs):
            str1 = '-d %s -j DNAT --to %s' \
                   % (self.floating_ip, self.fixed_ip)
            str2 = '-s %s -j SNAT --to %s' \
                   % (self.fixed_ip, self.floating_ip)

            process_input = ''
            if cmd == ('iptables-restore',):
                process_input = kwargs['process_input']
            if (str1 in process_input and
                str2 in process_input):
                self.stub_flag = True
            return 'fake', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        linux_net.ensure_floating_forward(self.floating_ip,
                                          self.fixed_ip)
        self.assert_(self.stub_flag)

        linux_net.remove_floating_forward(self.floating_ip,
                                          self.fixed_ip)

    @attr(kind='small')
    def test_ensure_floating_forward_exception_command_failed(self):
        """ Ensure raise exception when command failed"""
        self.flags(fake_network=False)

        def stub_utils_execute(*cmd, **kwargs):
            raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        self.assertRaises(exception.ProcessExecutionError,
                          linux_net.ensure_floating_forward,
                          '1.1.1.1', '10.10.10.10')

    @attr(kind='small')
    def test_remove_floating_forward(self):
        """ Ensure call utils.execute"""
        self.flags(fake_network=False)
        self.floating_ip = '1,1,1,1'
        self.fixed_ip = '10.10.10.10'
        self.stub_flag = False

        def stub_utils_execute(*cmd, **kwargs):
            str1 = '-d %s -j DNAT --to %s' \
                   % (self.floating_ip, self.fixed_ip)
            str2 = '-s %s -j SNAT --to %s' \
                   % (self.fixed_ip, self.floating_ip)

            process_input = ''
            if cmd == ('iptables-restore',):
                process_input = kwargs['process_input']
            if (str1 in process_input and
                str2 in process_input):
                self.stub_flag = True

            return 'fake', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        linux_net.ensure_floating_forward(self.floating_ip,
                                          self.fixed_ip)
        self.assert_(self.stub_flag)

        self.stub_flag = False
        linux_net.remove_floating_forward(self.floating_ip,
                                          self.fixed_ip)
        self.assertFalse(self.stub_flag)

    @attr(kind='small')
    def test_remove_floating_forward_exception_command_failed(self):
        """ Ensure raise exception when command failed"""
        self.flags(fake_network=False)

        def stub_utils_execute(*cmd, **kwargs):
            raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        self.assertRaises(exception.ProcessExecutionError,
                          linux_net.remove_floating_forward,
                          '1.1.1.1', '10.10.10.10')

    @attr(kind='small')
    def test_get_dhcp_leases(self):
        """ Ensure return network's hosts config"""

        def stub_db_network_get_associated_fixed_ips(
                                            context, network_id):
            return fixed_ips

        self.stubs.Set(db, 'network_get_associated_fixed_ips',
                       stub_db_network_get_associated_fixed_ips)

        c = context.get_admin_context()
        dhcp_leases = linux_net.get_dhcp_leases(c, networks[0])
        self.assertEquals(len(fixed_ips), len(dhcp_leases.split('\n')))

    @attr(kind='small')
    def test_get_dhcp_leases_database(self):
        """ Ensure return network's hosts config only host = FLAGS.host"""

        def stub_db_network_get_associated_fixed_ips(
                                            context, network_id):
            return fixed_ips

        self.stubs.Set(db, 'network_get_associated_fixed_ips',
                       stub_db_network_get_associated_fixed_ips)

        c = context.get_admin_context()
        dhcp_leases = linux_net.get_dhcp_leases(c, networks[2])
        self.assertEquals(1, len(dhcp_leases.split('\n')))

    @attr(kind='small')
    def test_get_dhcp_hosts_database(self):
        """ Ensure return network's hosts config only host = FLAGS.host"""

        def stub_db_network_get_associated_fixed_ips(
                                            context, network_id):
            return fixed_ips

        self.stubs.Set(db, 'network_get_associated_fixed_ips',
                       stub_db_network_get_associated_fixed_ips)

        c = context.get_admin_context()
        dhcp_leases = linux_net.get_dhcp_hosts(c, networks[2])
        self.assertEquals(1, len(dhcp_leases.split('\n')))

    @attr(kind='small')
    def test_release_dhcp(self):
        """ Ensure call utils.execute"""
        self.dev = None
        self.address = None
        self.mac_address = None

        def stub_utils_execute(*cmd, **kwargs):
            self.dev = cmd[1]
            self.address = cmd[2]
            self.mac_address = cmd[3]
            return 'fake', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        dev = 'eth0'
        address = '1.1.1.1'
        mac_address = '00-00-00-00-00-00-00-E0'
        linux_net.release_dhcp(dev, address, mac_address)
        self.assertEquals((dev, address, mac_address),
                          (self.dev, self.address, self.mac_address))

    @attr(kind='small')
    def test_release_dhcpexception_command_failed(self):
        """ Ensure raise exception when command failed"""

        def stub_utils_execute(*cmd, **kwargs):
            raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        dev = 'eth0'
        address = '1.1.1.1'
        mac_address = '00-00-00-00-00-00-00-E0'
        self.assertRaises(exception.ProcessExecutionError,
                          linux_net.release_dhcp, dev,
                          address, mac_address)

    @attr(kind='small')
    def test_update_ra(self):
        """ Ensure exec radvd command"""
        self.flags(fake_network=False,
                   networks_path='/tmp/test_linux_net')
        self.stub_flag = False

        def stub_utils_execute(*cmd, **kwargs):
            if 'eth0' in cmd[2]:
                self.stub_flag = True

            return 'fake', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        # pre-condition
        #  - networks_path not exists
        self.assertFalse(os.path.exists(FLAGS.networks_path))

        c = context.get_admin_context()
        linux_net.update_ra(c, 'eth0', networks[0])
        self.assert_(self.stub_flag)

        self.assert_(os.path.exists(linux_net._ra_file('eth0', 'conf')))
        self.assertFalse(os.path.exists(linux_net._ra_file('eth0', 'pid')))
        shutil.rmtree(FLAGS.networks_path)

    @attr(kind='small')
    def test_update_ra_Configuration_kill_pid(self):
        """ Ensure exec radvd command when radvd is already running"""
        self.flags(fake_network=False,
                   networks_path='/tmp/test_linux_net')
        self.stub_cnt = 0

        def stub_utils_execute(*cmd, **kwargs):
            if 'cat' == cmd[0] and '123' in cmd[1]:
                self.stub_cnt += 1
                return linux_net._ra_file('eth0', 'conf'), 0
            elif 'kill' == cmd[0] and 123 == cmd[1]:
                self.stub_cnt += 1
                return 'fake', 0
            elif 'radvd' == cmd[0] and 'eth0' in cmd[2]:
                self.stub_cnt += 1
                return 'fake', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        # pre-condition
        #  - conf file not exists
        #  - pid file exist

        # make pid file
        self.assertFalse(os.path.exists(FLAGS.networks_path))
        pid_file = linux_net._ra_file('eth0', 'pid')
        with open(pid_file, 'w') as f:
            f.write('123')

        c = context.get_admin_context()
        linux_net.update_ra(c, 'eth0', networks[0])
        self.assertEquals(3, self.stub_cnt)

        self.assert_(os.path.exists(linux_net._ra_file('eth0', 'conf')))
        self.assert_(os.path.exists(linux_net._ra_file('eth0', 'pid')))
        shutil.rmtree(FLAGS.networks_path)

    @attr(kind='small')
    def test_update_ra_exception_failed_to_kill_pid(self):
        """ Ensure exec radvd command when failed to kill the pid"""
        self.flags(fake_network=False,
                   networks_path='/tmp/test_linux_net')
        self.stub_cnt = 0

        def stub_utils_execute(*cmd, **kwargs):
            if 'cat' == cmd[0] and '123' in cmd[1]:
                self.stub_cnt += 1
                return linux_net._ra_file('eth0', 'conf'), 0
            elif 'kill' == cmd[0] and 123 == cmd[1]:
                self.stub_cnt += 1
                raise exception.ProcessExecutionError
            elif 'radvd' == cmd[0] and 'eth0' in cmd[2]:
                self.stub_cnt += 1
                return 'fake', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        # pre-condition
        #   - pid file exists

        # make pid file
        self.assertFalse(os.path.exists(FLAGS.networks_path))
        pid_file = linux_net._ra_file('eth0', 'pid')
        with open(pid_file, 'w') as f:
            f.write('123')

        c = context.get_admin_context()
        linux_net.update_ra(c, 'eth0', networks[0])
        self.assertEquals(3, self.stub_cnt)

        self.assert_(os.path.exists(linux_net._ra_file('eth0', 'conf')))
        self.assert_(os.path.exists(linux_net._ra_file('eth0', 'pid')))
        shutil.rmtree(FLAGS.networks_path)

    @attr(kind='small')
    def test_update_ra_Configuration_pid_stale(self):
        """ Ensure exec radvd command when pid is stale"""
        self.flags(fake_network=False,
                   networks_path='/tmp/test_linux_net')
        self.stub_cnt = 0

        def stub_utils_execute(*cmd, **kwargs):
            if 'cat' == cmd[0] and '123' in cmd[1]:
                self.stub_cnt += 1
            elif 'kill' == cmd[0]:
                self.stub_cnt -= 1
            elif 'radvd' == cmd[0] and 'eth0' in cmd[2]:
                self.stub_cnt += 1

            return 'fake', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        # pre-condition
        #   - pid file exists

        # make pid file
        self.assertFalse(os.path.exists(FLAGS.networks_path))
        pid_file = linux_net._ra_file('eth0', 'pid')
        with open(pid_file, 'w') as f:
            f.write('123')

        c = context.get_admin_context()
        linux_net.update_ra(c, 'eth0', networks[0])
        self.assertEquals(2, self.stub_cnt)

        self.assert_(os.path.exists(linux_net._ra_file('eth0', 'conf')))
        self.assert_(os.path.exists(linux_net._ra_file('eth0', 'pid')))
        shutil.rmtree(FLAGS.networks_path)

    @attr(kind='small')
    def test_update_ra_exception_radvd_command_failed(self):
        """ Ensure raise exception when radvd command failed"""
        self.flags(fake_network=False,
                   networks_path='/tmp/test_linux_net')
        self.stub_flag = False

        def stub_utils_execute(*cmd, **kwargs):
            if 'radvd' == cmd[0] and 'eth0' in cmd[2]:
                raise exception.ProcessExecutionError

            return 'fake', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        # pre-condition
        #  - pid file not exists
        self.assertFalse(os.path.exists(FLAGS.networks_path))

        c = context.get_admin_context()
        self.assertRaises(exception.ProcessExecutionError,
                          linux_net.update_ra, c, 'eth0', networks[0])

        self.assert_(os.path.exists(linux_net._ra_file('eth0', 'conf')))
        shutil.rmtree(FLAGS.networks_path)

    @attr(kind='small')
    def test_stop_dnsmasq(self):
        """ Ensure stops the dnsmasq instance for a given network"""
        self.flags(fake_network=False,
                   networks_path='/tmp/test_linux_net')
        self.stub_flag = False

        def stub_utils_execute(*cmd, **kwargs):
            if cmd == ('kill', '-TERM', 123):
                self.stub_flag = True
            return 'fake', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        # pre-condition
        #  - pid file exists

        # make pid file
        self.assertFalse(os.path.exists(FLAGS.networks_path))
        pid_file = linux_net._dhcp_file('eth0', 'pid')
        with open(pid_file, 'w') as f:
            f.write('123')

        linux_net._stop_dnsmasq('eth0')
        self.assert_(self.stub_flag)

        self.assert_(os.path.exists(linux_net._dhcp_file('eth0', 'pid')))
        shutil.rmtree(FLAGS.networks_path)

    @attr(kind='small')
    def test_stop_dnsmasq_configuration_do_nothing(self):
        """ Ensure not exec command when pid not exists"""
        self.flags(fake_network=False,
                   networks_path='/tmp/test_linux_net')
        self.stub_flag = True

        def stub_utils_execute(*cmd, **kwargs):
            self.stub_flag = False
            return 'fake', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        # pre-condition
        #  - pid file not exists
        self.assertFalse(os.path.exists(FLAGS.networks_path))

        linux_net._stop_dnsmasq('eth0')
        self.assert_(self.stub_flag)

        self.assertFalse(os.path.exists(linux_net._ra_file('eth0', 'pid')))
        shutil.rmtree(FLAGS.networks_path)

    @attr(kind='small')
    def test_stop_dnsmasq_exception_command_failed(self):
        """ Ensure pass when command failed"""
        self.flags(fake_network=False,
                   networks_path='/tmp/test_linux_net')
        self.stub_flag = False

        def stub_utils_execute(*cmd, **kwargs):
            raise exception.ProcessExecutionError

        def stub_debug(msg, *args, **kwargs):
            if msg == 'Killing dnsmasq threw %s':
                self.stub_flag = True

        self.stubs.Set(utils, 'execute', stub_utils_execute)
        self.stubs.Set(logging.getLogger("nova.linux_net"),
                       'debug', stub_debug)

        # pre-condition
        #  - pid file exists

        # make pid file
        self.assertFalse(os.path.exists(FLAGS.networks_path))
        pid_file = linux_net._dhcp_file('eth0', 'pid')
        with open(pid_file, 'w') as f:
            f.write('123')

        linux_net._stop_dnsmasq('eth0')
        self.assert_(self.stub_flag)

        self.assert_(os.path.exists(linux_net._dhcp_file('eth0', 'pid')))
        shutil.rmtree(FLAGS.networks_path)

    @attr(kind='small')
    def test_initialize_gateway_device_parameter_is_none(self):
        """ Ensure do nothing when parameter is none"""
        self.flags(fake_network=False)
        self.stub_flag = True

        def stub_utils_execute(*cmd, **kwargs):
            self.stub_flag = False
            return 'fake', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        linux_net.initialize_gateway_device('eth0', None)
        self.assert_(self.stub_flag)

    @attr(kind='small')
    def test_initialize_gateway_device_configuration_flags(self):
        """ Ensure exec command by FLAGS configuration"""
        self.flags(fake_network=False,
                   send_arp_for_ha=True,
                   use_ipv6=False,
                   public_interface='eth1')

        existing = ("2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> "
            "    mtu 1500 qdisc pfifo_fast state UNKNOWN qlen 1000\n"
            "    link/ether de:ad:be:ef:be:ef brd ff:ff:ff:ff:ff:ff\n"
            "    inet6 dead::beef:dead:beef:dead/64 scope link\n"
            "    valid_lft forever preferred_lft forever\n")
        expected = [
            ('ip', 'addr', 'show', 'dev', 'eth0', 'scope', 'global'),
            ('ip', 'addr', 'add', '192.168.1.1/24',
             'brd', '192.168.1.255', 'dev', 'eth0'),
            ('arping', '-U', '192.168.1.1', '-A', '-I', 'eth0', '-c', 1),
        ]

        executes = []

        def stub_utils_execute(*args, **kwargs):
            if args[0] != 'route':
                executes.append(args)

            if (args[0] == 'ip' and
                args[1] == 'addr' and
                args[2] == 'show'):
                return existing, ""

            elif args[0] == 'route' and args[1] == '-n':
                return ("192.168.0.0 0.0.0.0 255.255.255.0 U 1 0 0 eth0\n"
                        "1.1.1.1 0.0.0.0 255.255.0.0 U 1000 0 0 eth0\n"
                        "0.0.0.0 1.1.1.1 0.0.0.0 UG 0 0 0 eth0"), ""

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        network = {'dhcp_server': '192.168.1.1',
                   'cidr': '192.168.1.0/24',
                   'broadcast': '192.168.1.255',
                   'cidr_v6': '2001:db8::/64'}
        linux_net.initialize_gateway_device('eth0', network)
        self.assertEqual(executes, expected)

    @attr(kind='small')
    def test_initialize_gateway_device_exception_command_failed(self):
        """ Ensure raise exception when command failed """
        self.flags(fake_network=False)

        def stub_utils_execute(*args, **kwargs):
            raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        network = {'dhcp_server': '192.168.1.1',
                   'cidr': '192.168.1.0/24',
                   'broadcast': '192.168.1.255',
                   'cidr_v6': '2001:db8::/64'}
        self.assertRaises(exception.ProcessExecutionError,
                          linux_net.initialize_gateway_device,
                          'eth0', network)

    @attr(kind='small')
    def test_get_dhcp_opts_database_ips_empty(self):
        """ Ensure return empty list"""
        self.mox.StubOutWithMock(db, 'network_get_associated_fixed_ips')

        db.network_get_associated_fixed_ips(mox.IgnoreArg(),
                                            mox.IgnoreArg())\
                                            .AndReturn([])
        self.mox.ReplayAll()

        expected_opts = ''
        actual_opts = self.driver.get_dhcp_opts(None, networks[0])
        self.assertEquals(actual_opts, expected_opts)

    @attr(kind='small')
    def test_get_dhcp_opts_database_vifs_empty(self):
        """ Ensure return empty list"""
        self.mox.StubOutWithMock(db, 'network_get_associated_fixed_ips')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')

        db.network_get_associated_fixed_ips(mox.IgnoreArg(),
                                            mox.IgnoreArg())\
                                            .AndReturn([fixed_ips[0],
                                                        fixed_ips[3],
                                                        fixed_ips[4]])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg())\
                                             .AndReturn([])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg())\
                                             .AndReturn([])
        self.mox.ReplayAll()

        expected_opts = ''
        actual_opts = self.driver.get_dhcp_opts(None, networks[0])
        self.assertEquals(actual_opts, expected_opts)

    @attr(kind='small')
    def test_update_dhcp_configuration_dnsserver_not_none(self):
        """ Ensure exec command when dns server is not none"""
        self.flags(dns_server='fake_dns',
                   fake_network=False)
        self.cmd = None

        def stub_utils_execute(*cmd, **kwargs):
            if cmd[0] == 'FLAGFILE=%s' % FLAGS.dhcpbridge_flagfile:
                self.cmd = cmd
            return 'fake', ''

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        self.mox.StubOutWithMock(db, 'network_get_associated_fixed_ips')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')

        db.network_get_associated_fixed_ips(mox.IgnoreArg(),
                                            mox.IgnoreArg())\
                                            .AndReturn([fixed_ips[0],
                                                        fixed_ips[3]])
        self.mox.ReplayAll()
        self.driver.update_dhcp(None, "eth0", networks[0])

        self.assertEqual(self.cmd[1],
                         'NETWORK_ID=%s' % str(networks[0]['id']))
        self.assertEqual(self.cmd[8],
                         '--listen-address=%s'
                         % networks[0]['dhcp_server'])
        self.assertEqual(self.cmd[10],
                         '--dhcp-range=%s,static,120s'
                         % networks[0]['dhcp_start'])

        # dns_server not none
        self.assertEqual(self.cmd[15], '-h')
        self.assertEqual(self.cmd[16], '-R')
        self.assertEqual(self.cmd[17],
                         '--server=%s' % FLAGS.dns_server)

    @attr(kind='small')
    def test_update_dhcp_configuration_pid_kill(self):
        """ Ensure kill pid when pid is not none"""
        self.flags(fake_network=False)
        self.stub_flag = False

        def stub_utils_execute(*cmd, **kwargs):
            if cmd[0] == 'cat':
                conffile = linux_net._dhcp_file("eth0", 'conf')
                return conffile, ''
            elif cmd[0] == 'kill':
                self.stub_flag = True

            return 'fake', ''

        def stub_dnsmasq_pid_for(dev):
            return 123

        self.stubs.Set(utils, 'execute', stub_utils_execute)
        self.stubs.Set(linux_net, '_dnsmasq_pid_for', stub_dnsmasq_pid_for)

        self.mox.StubOutWithMock(db, 'network_get_associated_fixed_ips')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')

        db.network_get_associated_fixed_ips(mox.IgnoreArg(),
                                            mox.IgnoreArg())\
                                            .AndReturn([fixed_ips[0],
                                                        fixed_ips[3]])
        self.mox.ReplayAll()

        self.driver.update_dhcp(None, "eth0", networks[0])
        self.assert_(self.stub_flag)

    @attr(kind='small')
    def test_update_dhcp_configuration_pid_is_stale(self):
        """ Ensure """
        self.flags(fake_network=False)
        self.stub_flag = False

        def stub_utils_execute(*cmd, **kwargs):
            return 'fake', ''

        def stub_dnsmasq_pid_for(dev):
            return 123

        def stub_debug(msg, *args, **kwargs):
            if msg == 'Pid %d is stale, relaunching dnsmasq':
                self.stub_flag = True

        self.stubs.Set(utils, 'execute', stub_utils_execute)
        self.stubs.Set(linux_net, '_dnsmasq_pid_for', stub_dnsmasq_pid_for)
        self.stubs.Set(logging.getLogger("nova.linux_net"),
                       'debug', stub_debug)

        self.mox.StubOutWithMock(db, 'network_get_associated_fixed_ips')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')

        db.network_get_associated_fixed_ips(mox.IgnoreArg(),
                                            mox.IgnoreArg())\
                                            .AndReturn([fixed_ips[0],
                                                        fixed_ips[3]])
        self.mox.ReplayAll()

        self.driver.update_dhcp(None, "eth0", networks[0])
        self.assert_(self.stub_flag)

    @attr(kind='small')
    def test_update_dhcp_exception_failed_to_kill_pid(self):
        """ Ensure """
        self.flags(fake_network=False)
        self.stub_flag = False

        def stub_utils_execute(*cmd, **kwargs):
            if cmd[0] == 'cat':
                conffile = linux_net._dhcp_file("eth0", 'conf')
                return conffile, ''
            elif cmd[0] == 'kill':
                raise exception.ProcessExecutionError

            return 'fake', ''

        def stub_dnsmasq_pid_for(dev):
            return 123

        def stub_debug(msg, *args, **kwargs):
            if msg == 'Hupping dnsmasq threw %s':
                self.stub_flag = True

        self.stubs.Set(utils, 'execute', stub_utils_execute)
        self.stubs.Set(linux_net, '_dnsmasq_pid_for', stub_dnsmasq_pid_for)
        self.stubs.Set(logging.getLogger("nova.linux_net"),
                       'debug', stub_debug)

        self.mox.StubOutWithMock(db, 'network_get_associated_fixed_ips')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')

        db.network_get_associated_fixed_ips(mox.IgnoreArg(),
                                            mox.IgnoreArg())\
                                            .AndReturn([fixed_ips[0],
                                                        fixed_ips[3]])
        self.mox.ReplayAll()

        self.driver.update_dhcp(None, "eth0", networks[0])
        self.assert_(self.stub_flag)


class IptablesRuleTestCase(test.TestCase):

    @attr(kind='small')
    def test_eq(self):
        """ Ensure eq"""
        chain = 'nova-filter-top'
        rule = '-j nova-filter-top'
        wrap = False
        top = True

        cls1 = linux_net.IptablesRule(chain, rule, wrap, top)
        cls2 = linux_net.IptablesRule(chain, rule, wrap, top)

        self.assertEquals(cls1, cls2)

    @attr(kind='small')
    def test_ne(self):
        """ Ensure ne"""
        chain = 'nova-filter-top'
        rule = '-j nova-filter-top'
        wrap = False
        top = True

        cls1 = linux_net.IptablesRule(chain, rule, wrap, top)

        chain = 'local'
        rule = '-j $local'
        wrap = False
        top = False

        cls2 = linux_net.IptablesRule(chain, rule, wrap, top)

        self.assertNotEquals(cls1, cls2)


class IptablesTableTestCase(test.TestCase):

    def setUp(self):
        super(IptablesTableTestCase, self).setUp()
        network_driver = FLAGS.network_driver
        self.driver = utils.import_object(network_driver)
        self.driver.db = db

    @attr(kind='small')
    def test_remove_chain(self):
        """ Ensure remove chain(when wrap is true)"""
        chain = 'sg-fallback'
        iptables = linux_net.iptables_manager
        iptables.ipv4['filter'].add_chain(chain)

        self.assert_(chain in iptables.ipv4['filter'].chains)
        self.assert_(chain not in iptables.ipv4['filter'].unwrapped_chains)
        iptables.ipv4['filter'].remove_chain(chain)
        self.assert_(chain not in iptables.ipv4['filter'].chains)
        self.assert_(chain not in iptables.ipv4['filter'].unwrapped_chains)

    @attr(kind='small')
    def test_remove_chain_parameter_wrap_is_false(self):
        """ Ensure remove chain when wrap is false"""
        chain = 'sg-fallback'
        iptables = linux_net.iptables_manager
        iptables.ipv4['filter'].add_chain(chain, wrap=False)

        self.assert_(chain not in iptables.ipv4['filter'].chains)
        self.assert_(chain in iptables.ipv4['filter'].unwrapped_chains)
        iptables.ipv4['filter'].remove_chain(chain, wrap=False)
        self.assert_(chain not in iptables.ipv4['filter'].chains)
        self.assert_(chain not in iptables.ipv4['filter'].unwrapped_chains)

    @attr(kind='small')
    def test_remove_chain_parameter_chain_not_in_chains(self):
        """ Ensure not remove chain when chain is not in chains"""
        add_chain = 'sg-fallback'
        del_chain = 'sg-fallbackkkk'
        iptables = linux_net.iptables_manager
        iptables.ipv4['filter'].add_chain(add_chain)

        self.assert_(add_chain in iptables.ipv4['filter'].chains)
        self.assert_(add_chain not in \
                     iptables.ipv4['filter'].unwrapped_chains)
        self.assert_(del_chain not in iptables.ipv4['filter'].chains)
        self.assert_(del_chain not in \
                     iptables.ipv4['filter'].unwrapped_chains)
        iptables.ipv4['filter'].remove_chain(del_chain)
        self.assert_(add_chain in iptables.ipv4['filter'].chains)
        self.assert_(add_chain not in \
                     iptables.ipv4['filter'].unwrapped_chains)
        self.assert_(del_chain not in iptables.ipv4['filter'].chains)
        self.assert_(del_chain not in \
                     iptables.ipv4['filter'].unwrapped_chains)

        iptables.ipv4['filter'].remove_chain(add_chain)

    @attr(kind='small')
    def test_add_rule_parameter_chain_not_in_chains(self):
        """ Ensure raise exception when chain is not in chains"""
        chain = 'sg-fallback'
        rule = '-j DROP'
        iptables = linux_net.iptables_manager
        self.assertRaises(ValueError,
                          iptables.ipv4['filter'].add_rule, chain, rule)

    @attr(kind='small')
    def test_remove_rule(self):
        """ Ensure remove rule"""
        chain = 'sg-fallback'
        rule = '-j DROP'
        iptables = linux_net.iptables_manager
        iptables.ipv4['filter'].add_chain(chain)
        iptables.ipv4['filter'].add_rule(chain, rule)

        cnt_before = len(iptables.ipv4['filter'].rules)
        iptables.ipv4['filter'].remove_rule(chain, rule)
        cnt_after = len(iptables.ipv4['filter'].rules)

        self.assertEqual(cnt_before - 1, cnt_after)

        iptables.ipv4['filter'].remove_chain(chain)

    @attr(kind='small')
    def test_remove_rule_exception_handling_remove_fail(self):
        """ Ensure not remove rule when chain is not in chains"""
        add_chain = 'sg-fallback'
        del_chain = 'sg-fallbackkkk'
        rule = '-j DROP'
        iptables = linux_net.iptables_manager
        iptables.ipv4['filter'].add_chain(add_chain)
        iptables.ipv4['filter'].add_rule(add_chain, rule)

        cnt_before = len(iptables.ipv4['filter'].rules)
        iptables.ipv4['filter'].remove_rule(del_chain, rule)
        cnt_after = len(iptables.ipv4['filter'].rules)

        self.assertEqual(cnt_before, cnt_after)

        iptables.ipv4['filter'].remove_rule(add_chain, rule)
        iptables.ipv4['filter'].remove_chain(add_chain)

    @attr(kind='small')
    def test_empty_chain(self):
        """ Ensure remove all rules from a chain"""
        chain = 'sg-fallback'
        iptables = linux_net.iptables_manager
        iptables.ipv4['filter'].add_chain(chain)
        iptables.ipv4['filter'].add_rule(chain, '-j DROP1')
        iptables.ipv4['filter'].add_rule(chain, '-j DROP2')
        iptables.ipv4['filter'].add_rule(chain, '-j DROP3')

        cnt_before = len(iptables.ipv4['filter'].rules)
        iptables.ipv4['filter'].empty_chain(chain)
        cnt_after = len(iptables.ipv4['filter'].rules)

        self.assertEqual(cnt_before - 3, cnt_after)

        iptables.ipv4['filter'].remove_chain(chain)

    @attr(kind='small')
    def test_empty_chain_parameter_chain_not_in_chains(self):
        """ Ensure not remove when chain is not in chains"""
        chain = 'sg-fallback'
        iptables = linux_net.iptables_manager
        iptables.ipv4['filter'].add_chain(chain)
        iptables.ipv4['filter'].add_rule(chain, '-j DROP1')
        iptables.ipv4['filter'].add_rule(chain, '-j DROP2')
        iptables.ipv4['filter'].add_rule(chain, '-j DROP3')

        cnt_before = len(iptables.ipv4['filter'].rules)
        iptables.ipv4['filter'].empty_chain('sg-fallbackkkkkk')
        cnt_after = len(iptables.ipv4['filter'].rules)

        self.assertEqual(cnt_before, cnt_after)

        iptables.ipv4['filter'].empty_chain(chain)
        iptables.ipv4['filter'].remove_chain(chain)


class IptablesManagerTestCase(test.TestCase):

    def setUp(self):
        super(IptablesManagerTestCase, self).setUp()
        network_driver = FLAGS.network_driver
        self.driver = utils.import_object(network_driver)
        self.driver.db = db

    @attr(kind='small')
    def test_init_parameter_execute_is_not_none(self):
        """ Ensure execute is not none"""
        iptables = linux_net.IptablesManager(execute=linux_net._execute)
        self.assertNotEquals(0, len(iptables.ipv4['filter'].chains))

    @attr(kind='small')
    def test_apply_configuration_use_ipv6_false(self):
        """ Ensure not using ipv6"""
        self.flags(fake_network=False)
        self.stub_flag = False

        def stub_utils_execute(*cmd, **kwargs):
            if cmd[0] == 'ip6tables-save':
                self.stub_flag = True
            return 'fake', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        iptables = linux_net.iptables_manager
        iptables.apply()
        self.assert_(self.stub_flag)

        self.flags(use_ipv6=False)
        self.stub_flag = False

        iptables.apply()
        self.assertFalse(self.stub_flag)

    @attr(kind='small')
    def test_apply_exception_command_failed(self):
        """ Ensure raise exception when command failed"""
        self.flags(fake_network=False)

        def stub_utils_execute(*cmd, **kwargs):
            raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        iptables = linux_net.iptables_manager
        self.assertRaises(exception.ProcessExecutionError,
                          iptables.apply)


class LinuxNetInterfaceDriverTestcase(test.TestCase):

    def setUp(self):
        super(LinuxNetInterfaceDriverTestcase, self).setUp()
        network_driver = FLAGS.network_driver
        self.driver = utils.import_object(network_driver)
        self.driver.db = db
        test_driver = 'nova.network.linux_net.LinuxNetInterfaceDriver'
        linux_net.interface_driver = utils.import_object(test_driver)

    def tearDown(self):
        linux_net.interface_driver = \
            utils.import_object(FLAGS.linuxnet_interface_driver)
        super(LinuxNetInterfaceDriverTestcase, self).tearDown()

    @attr(kind='small')
    def test_plug(self):
        """ Ensure raise exception"""
        self.assertRaises(NotImplementedError,
                          linux_net.plug,
                          networks[0],
                          '00-00-00-00-00-00-00-E0')

    @attr(kind='small')
    def test_unplug(self):
        """ Ensure raise exception"""
        self.assertRaises(NotImplementedError,
                          linux_net.unplug,
                          networks[0])

    @attr(kind='small')
    def test_get_dev(self):
        """ Ensure raise exception"""
        self.assertRaises(NotImplementedError,
                          linux_net.get_dev,
                          networks[0])


class LinuxBridgeInterfaceDriverTestcase(test.TestCase):

    def setUp(self):
        super(LinuxBridgeInterfaceDriverTestcase, self).setUp()
        network_driver = FLAGS.network_driver
        self.driver = utils.import_object(network_driver)
        self.driver.db = db
        test_driver = 'nova.network.linux_net.LinuxBridgeInterfaceDriver'
        linux_net.interface_driver = utils.import_object(test_driver)

    def tearDown(self):
        linux_net.interface_driver = \
            utils.import_object(FLAGS.linuxnet_interface_driver)
        super(LinuxBridgeInterfaceDriverTestcase, self).tearDown()

    @attr(kind='small')
    def test_plug(self):
        """ Ensure create Linux device, return device name"""
        rtn = linux_net.plug(networks[0], '00-00-00-00-00-00-00-E0')
        self.assertEquals(networks[0]['bridge'], rtn)

    @attr(kind='small')
    def test_plug_database_vlan(self):
        """ Ensure create Linux device, return device name"""
        rtn = linux_net.plug(networks[2], '00-00-00-00-00-00-00-E0')
        self.assertEquals(networks[2]['bridge'], rtn)

    @attr(kind='small')
    def test_plug_configuration_all_command_exec(self):
        """ Ensure exec all command(=15)"""
        self.flags(fake_network=False)
        self.stub_cnt = 0

        def stub_device_exists(device):
            return False

        def stub_utils_execute(*cmd, **kwargs):
            self.stub_cnt += 1
            if cmd == ('route', '-n'):
                return '0.0.0.0 1.1.1.1 vlan100', 0

            elif cmd == ('ip', 'addr', 'show', 'dev',
                         'vlan100', 'scope', 'global'):
                return 'inet fake1 fake2 fake3', 0

            return 'fake', 0

        self.stubs.Set(linux_net, '_device_exists', stub_device_exists)
        self.stubs.Set(utils, 'execute', stub_utils_execute)

        rtn = linux_net.plug(networks[2], '00-00-00-00-00-00-00-E0')
        self.assertEquals(networks[2]['bridge'], rtn)
        self.assertEquals(15, self.stub_cnt)

    @attr(kind='small')
    def test_plug_parameter_mac_address_none(self):
        """ Ensure """
        self.flags(fake_network=False)
        self.stub_flag = False

        def stub_device_exists(device):
            return False

        def stub_utils_execute(*cmd, **kwargs):
            if cmd == ('vconfig', 'set_name_type', 'VLAN_PLUS_VID_NO_PAD'):
                self.stub_flag = True
            elif cmd[0] == 'ip' and cmd[1] == 'link'\
                and cmd[2] == 'set' and cmd[4] == 'address':
                self.stub_flag = False

            return 'fake', 0

        self.stubs.Set(linux_net, '_device_exists', stub_device_exists)
        self.stubs.Set(utils, 'execute', stub_utils_execute)

        rtn = linux_net.plug(networks[2], None)
        self.assertEquals(networks[2]['bridge'], rtn)
        self.assert_(self.stub_flag)

    @attr(kind='small')
    def test_plug_exception_command_return_error(self):
        """ Ensure raise exception when exec command return error"""
        self.flags(fake_network=False)

        def stub_device_exists(device):
            return False

        def stub_utils_execute(*cmd, **kwargs):
            if cmd == ('route', '-n'):
                return '0.0.0.0 1.1.1.1 vlan100', 0

            elif cmd == ('ip', 'addr', 'show', 'dev',
                         'vlan100', 'scope', 'global'):
                return 'inet fake1 fake2 fake3', 'Error!'

            return 'fake', 0

        self.stubs.Set(linux_net, '_device_exists', stub_device_exists)
        self.stubs.Set(utils, 'execute', stub_utils_execute)

        self.assertRaises(exception.Error,
                          linux_net.plug,
                          networks[2], '00-00-00-00-00-00-00-E0')

    @attr(kind='small')
    def test_plug_exception_command_failed(self):
        """ Ensure raise exception when command failed"""
        self.flags(fake_network=False)

        def stub_device_exists(device):
            return False

        def stub_utils_execute(*cmd, **kwargs):
            raise exception.ProcessExecutionError

        self.stubs.Set(linux_net, '_device_exists', stub_device_exists)
        self.stubs.Set(utils, 'execute', stub_utils_execute)

        self.assertRaises(exception.ProcessExecutionError,
                          linux_net.plug,
                          networks[2], '00-00-00-00-00-00-00-E0')

    @attr(kind='small')
    def test_unplug(self):
        """ Ensure destory Linux device, return device name"""
        rtn = linux_net.unplug(networks[0])
        self.assertEquals(networks[0]['bridge'], rtn)

    @attr(kind='small')
    def test_get_dev(self):
        """ Ensure get device name"""
        rtn = linux_net.get_dev(networks[0])
        self.assertEquals(networks[0]['bridge'], rtn)

    def test_ensure_bridge_parameter_interface_is_none(self):
        """ Ensure """
        self.flags(fake_network=False)
        self.stub_flag = False

        def stub_device_exists(device):
            return False

        def stub_utils_execute(*cmd, **kwargs):
            if cmd == ('brctl', 'addbr', 'fa0'):
                self.stub_flag = True
            elif cmd == ('brctl', 'addif', 'fa0', 'vlan100'):
                self.stub_flag = False

            return 'fake', 0

        self.stubs.Set(linux_net, '_device_exists', stub_device_exists)
        self.stubs.Set(utils, 'execute', stub_utils_execute)

        linux_net.LinuxBridgeInterfaceDriver().ensure_bridge('fa0', None)
        self.assert_(self.stub_flag)


class LinuxOVSInterfaceDriverTestcase(test.TestCase):

    def setUp(self):
        super(LinuxOVSInterfaceDriverTestcase, self).setUp()
        network_driver = FLAGS.network_driver
        self.driver = utils.import_object(network_driver)
        self.driver.db = db
        test_driver = 'nova.network.linux_net.LinuxOVSInterfaceDriver'
        linux_net.interface_driver = utils.import_object(test_driver)

    def tearDown(self):
        linux_net.interface_driver = \
            utils.import_object(FLAGS.linuxnet_interface_driver)
        super(LinuxOVSInterfaceDriverTestcase, self).tearDown()

    @attr(kind='small')
    def test_plug(self):
        """ Ensure create Linux device, return device name"""
        rtn = linux_net.plug(networks[0], '00-00-00-00-00-00-00-E0')
        self.assertEquals("gw-" + str(networks[0]['id']), rtn)

    @attr(kind='small')
    def test_plug_configuration_device_not_exists(self):
        """ Ensure exec command when device not exists"""
        self.flags(fake_network=False)
        self.stub_cnt = 0

        def stub_device_exists(device):
            return False

        def stub_utils_execute(*cmd, **kwargs):
            self.stub_cnt += 1
            return 'fake', 0

        self.stubs.Set(linux_net, '_device_exists', stub_device_exists)
        self.stubs.Set(utils, 'execute', stub_utils_execute)

        rtn = linux_net.plug(networks[0], '00-00-00-00-00-00-00-E0')
        self.assertEquals("gw-" + str(networks[0]['id']), rtn)
        self.assertEquals(3, self.stub_cnt)

    @attr(kind='small')
    def test_plug_exception_command_failed(self):
        """ Ensure raise exception when command failed"""
        self.flags(fake_network=False)

        def stub_device_exists(device):
            return False

        def stub_utils_execute(*cmd, **kwargs):
            raise exception.ProcessExecutionError

        self.stubs.Set(linux_net, '_device_exists', stub_device_exists)
        self.stubs.Set(utils, 'execute', stub_utils_execute)

        self.assertRaises(exception.ProcessExecutionError,
                          linux_net.plug,
                          networks[0], '00-00-00-00-00-00-00-E0')

    @attr(kind='small')
    def test_unplug(self):
        """ Ensure destory Linux device, return device name"""
        rtn = linux_net.unplug(networks[0])
        self.assertEquals("gw-" + str(networks[0]['id']), rtn)

    @attr(kind='small')
    def test_get_dev(self):
        """ Ensure get device name"""
        rtn = linux_net.get_dev(networks[0])
        self.assertEquals("gw-" + str(networks[0]['id']), rtn)
