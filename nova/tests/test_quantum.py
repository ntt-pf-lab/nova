# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 Nicira, Inc.
# All Rights Reserved.
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
from nova.db.sqlalchemy import models
from nova.db.sqlalchemy.session import get_session
from nova import exception
from nova import ipv6
from nova import log as logging
from nova.network.quantum import manager as quantum_manager
from nova import test
from nova import utils

from nose.plugins.attrib import attr
from nova.network import quantum
from nova.network.quantum import quantum_connection
from nova import flags
from nova.compute import instance_types

FLAGS = flags.FLAGS

LOG = logging.getLogger('nova.tests.quantum_network')


# this class can be used for unit functional/testing on nova,
# as it does not actually make remote calls to the Quantum service
class FakeQuantumClientConnection(object):

    def __init__(self):
        self.nets = {}

    def get_networks_for_tenant(self, tenant_id):
        net_ids = []
        for net_id, n in self.nets.items():
            if n['tenant-id'] == tenant_id:
                net_ids.append(net_id)
        return net_ids

    def create_network(self, tenant_id, network_name):

        uuid = str(utils.gen_uuid())
        self.nets[uuid] = {'net-name': network_name,
                           'tenant-id': tenant_id,
                           'ports': {}}
        return uuid

    def delete_network(self, tenant_id, net_id):
        if self.nets[net_id]['tenant-id'] == tenant_id:
            del self.nets[net_id]

    def network_exists(self, tenant_id, net_id):
        try:
            return self.nets[net_id]['tenant-id'] == tenant_id
        except KeyError:
            return False

    def _confirm_not_attached(self, interface_id):
        for n in self.nets.values():
            for p in n['ports'].values():
                if p['attachment-id'] == interface_id:
                    raise Exception(_("interface '%s' is already attached" %
                                          interface_id))

    def create_and_attach_port(self, tenant_id, net_id, interface_id):
        if not self.network_exists(tenant_id, net_id):
            raise Exception(
                _("network %(net_id)s does not exist for tenant %(tenant_id)"
                    % locals()))

        self._confirm_not_attached(interface_id)
        uuid = str(utils.gen_uuid())
        self.nets[net_id]['ports'][uuid] = \
                {"port-state": "ACTIVE",
                "attachment-id": interface_id}

    def detach_and_delete_port(self, tenant_id, net_id, port_id):
        if not self.network_exists(tenant_id, net_id):
            raise exception.NotFound(
                    _("network %(net_id)s does not exist "
                        "for tenant %(tenant_id)s" % locals()))
        del self.nets[net_id]['ports'][port_id]

    def get_port_by_attachment(self, tenant_id, attachment_id):
        for net_id, n in self.nets.items():
            if n['tenant-id'] == tenant_id:
                for port_id, p in n['ports'].items():
                    if p['attachment-id'] == attachment_id:
                        return (net_id, port_id)

        return (None, None)

networks = [{'label': 'project1-net1',
             'injected': False,
             'multi_host': False,
             'cidr': '192.168.0.0/24',
             'cidr_v6': '2001:1db8::/64',
             'gateway_v6': '2001:1db8::1',
             'netmask_v6': '64',
             'netmask': '255.255.255.0',
             'bridge': None,
             'bridge_interface': None,
             'gateway': '192.168.0.1',
             'broadcast': '192.168.0.255',
             'dns1': '192.168.0.1',
             'dns2': '192.168.0.2',
             'vlan': None,
             'host': None,
             'vpn_public_address': None,
             'project_id': 'fake_project1',
             'priority': 1},
            {'label': 'project2-net1',
             'injected': False,
             'multi_host': False,
             'cidr': '192.168.1.0/24',
             'cidr_v6': '2001:1db9::/64',
             'gateway_v6': '2001:1db9::1',
             'netmask_v6': '64',
             'netmask': '255.255.255.0',
             'bridge': None,
             'bridge_interface': None,
             'gateway': '192.168.1.1',
             'broadcast': '192.168.1.255',
             'dns1': '192.168.0.1',
             'dns2': '192.168.0.2',
             'vlan': None,
             'host': None,
             'project_id': 'fake_project2',
             'priority': 1},
             {'label': "public",
             'injected': False,
             'multi_host': False,
             'cidr': '10.0.0.0/24',
             'cidr_v6': '2001:1dba::/64',
             'gateway_v6': '2001:1dba::1',
             'netmask_v6': '64',
             'netmask': '255.255.255.0',
             'bridge': None,
             'bridge_interface': None,
             'gateway': '10.0.0.1',
             'broadcast': '10.0.0.255',
             'dns1': '10.0.0.1',
             'dns2': '10.0.0.2',
             'vlan': None,
             'host': None,
             'project_id': None,
             'priority': 0},
             {'label': "project2-net2",
             'injected': False,
             'multi_host': False,
             'cidr': '9.0.0.0/24',
             'cidr_v6': '2001:1dbb::/64',
             'gateway_v6': '2001:1dbb::1',
             'netmask_v6': '64',
             'netmask': '255.255.255.0',
             'bridge': None,
             'bridge_interface': None,
             'gateway': '9.0.0.1',
             'broadcast': '9.0.0.255',
             'dns1': '9.0.0.1',
             'dns2': '9.0.0.2',
             'vlan': None,
             'host': None,
             'project_id': "fake_project2",
             'priority': 2}]


# this is a base class to be used by all other Quantum Test classes
class QuantumTestCaseBase(object):

    def test_create_and_delete_nets(self):
        self._create_nets()
        self._delete_nets()

    def _create_nets(self):
        for n in networks:
            ctx = context.RequestContext('user1', n['project_id'])
            self.net_man.create_networks(ctx,
                    label=n['label'], cidr=n['cidr'],
                    multi_host=n['multi_host'],
                    num_networks=1, network_size=256, cidr_v6=n['cidr_v6'],
                    gateway_v6=n['gateway_v6'], bridge=None,
                    bridge_interface=None, dns1=n['dns1'],
                    dns2=n['dns2'], project_id=n['project_id'],
                    priority=n['priority'])

    def _delete_nets(self):
        for n in networks:
            ctx = context.RequestContext('user1', n['project_id'])
            self.net_man.delete_network(ctx, n['cidr'])

    def test_allocate_and_deallocate_instance_static(self):
        self._create_nets()

        project_id = "fake_project1"
        ctx = context.RequestContext('user1', project_id)

        instance_ref = db.api.instance_create(ctx,
                                    {"project_id": project_id})
        nw_info = self.net_man.allocate_for_instance(ctx,
                        instance_id=instance_ref['id'], host="",
                        instance_type_id=instance_ref['instance_type_id'],
                        project_id=project_id)

        self.assertEquals(len(nw_info), 2)

        # we don't know which order the NICs will be in until we
        # introduce the notion of priority
        # v4 cidr
        self.assertTrue(nw_info[0][0]['cidr'].startswith("10."))
        self.assertTrue(nw_info[1][0]['cidr'].startswith("192."))

        # v4 address
        self.assertTrue(nw_info[0][1]['ips'][0]['ip'].startswith("10."))
        self.assertTrue(nw_info[1][1]['ips'][0]['ip'].startswith("192."))

        # v6 cidr
        self.assertTrue(nw_info[0][0]['cidr_v6'].startswith("2001:1dba:"))
        self.assertTrue(nw_info[1][0]['cidr_v6'].startswith("2001:1db8:"))

        # v6 address
        self.assertTrue(
            nw_info[0][1]['ip6s'][0]['ip'].startswith("2001:1dba:"))
        self.assertTrue(
            nw_info[1][1]['ip6s'][0]['ip'].startswith("2001:1db8:"))

        self.net_man.deallocate_for_instance(ctx,
                    instance_id=instance_ref['id'],
                    project_id=project_id)

        self._delete_nets()

    def test_allocate_and_deallocate_instance_dynamic(self):
        self._create_nets()
        project_id = "fake_project2"
        ctx = context.RequestContext('user1', project_id)

        net_ids = self.net_man.q_conn.get_networks_for_tenant(project_id)
        requested_networks = [(net_id, None) for net_id in net_ids]

        self.net_man.validate_networks(ctx, requested_networks)

        instance_ref = db.api.instance_create(ctx,
                                    {"project_id": project_id})
        nw_info = self.net_man.allocate_for_instance(ctx,
                        instance_id=instance_ref['id'], host="",
                        instance_type_id=instance_ref['instance_type_id'],
                        project_id=project_id,
                        requested_networks=requested_networks)

        self.assertEquals(len(nw_info), 2)

        # we don't know which order the NICs will be in until we
        # introduce the notion of priority
        # v4 cidr
        self.assertTrue(nw_info[0][0]['cidr'].startswith("9.") or
                        nw_info[1][0]['cidr'].startswith("9."))
        self.assertTrue(nw_info[0][0]['cidr'].startswith("192.") or
                        nw_info[1][0]['cidr'].startswith("192."))

        # v4 address
        self.assertTrue(nw_info[0][1]['ips'][0]['ip'].startswith("9.") or
                        nw_info[1][1]['ips'][0]['ip'].startswith("9."))
        self.assertTrue(nw_info[0][1]['ips'][0]['ip'].startswith("192.") or
                        nw_info[1][1]['ips'][0]['ip'].startswith("192."))

        # v6 cidr
        self.assertTrue(nw_info[0][0]['cidr_v6'].startswith("2001:1dbb:") or
                        nw_info[1][0]['cidr_v6'].startswith("2001:1dbb:"))
        self.assertTrue(nw_info[0][0]['cidr_v6'].startswith("2001:1db9:") or
                        nw_info[1][0]['cidr_v6'].startswith("2001:1db9:"))

        # v6 address
        self.assertTrue(
            nw_info[0][1]['ip6s'][0]['ip'].startswith("2001:1dbb:") or
            nw_info[1][1]['ip6s'][0]['ip'].startswith("2001:1dbb:"))
        self.assertTrue(
            nw_info[0][1]['ip6s'][0]['ip'].startswith("2001:1db9:") or
            nw_info[1][1]['ip6s'][0]['ip'].startswith("2001:1db9:"))

        self.net_man.deallocate_for_instance(ctx,
                    instance_id=instance_ref['id'],
                    project_id=project_id)

        self._delete_nets()

    def test_validate_bad_network(self):
        ctx = context.RequestContext('user1', 'fake_project1')
        self.assertRaises(exception.NetworkNotFound,
                        self.net_man.validate_networks, ctx, [("", None)])

    @attr(kind='small')
    def test_create_subnet_except_index(self):
        param = dict(context=context.get_admin_context(), label='label-1',
                     tenant_id='1', quantum_net_id=None, priority=2,
                     cidr='10.0.0.1',cidr_v6='::10:10',
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.assertRaises(IndexError,
                          self.net_man.ipam.create_subnet, **param)

    @attr(kind='small')
    def test_create_subnet_except_net0(self):
        param = dict(context=context.get_admin_context(), label='label-1',
                     tenant_id='1', quantum_net_id=None, priority=2,
                     cidr='10.0.0.1',cidr_v6='::10:10',
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.counter = 0
        def fake_create_networks(man, context, label, cidr, multi_host,
                        num_networks,
                        network_size, cidr_v6, gateway, gateway_v6, bridge,
                        bridge_interface, dns1=None, dns2=None, **kwargs):
            self.counter += 1
            return []

        self.stubs.Set(manager.FlatManager, 'create_networks',
                       fake_create_networks)

        self.assertRaises(Exception,
                          self.net_man.ipam.create_subnet, **param)
        self.assertEqual(1, self.counter)

    @attr(kind='small')
    def test_create_subnet_except_net2(self):
        param = dict(context=context.get_admin_context(), label='label-1',
                     tenant_id='1', quantum_net_id=None, priority=2,
                     cidr='10.0.0.1',cidr_v6='::10:10',
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.counter = 0
        def fake_create_networks(man, context, label, cidr, multi_host,
                        num_networks,
                        network_size, cidr_v6, gateway, gateway_v6, bridge,
                        bridge_interface, dns1=None, dns2=None, **kwargs):
            self.counter += 1
            return [1, 2]

        self.stubs.Set(manager.FlatManager, 'create_networks',
                       fake_create_networks)

        self.assertRaises(Exception,
                          self.net_man.ipam.create_subnet, **param)
        self.assertEqual(1, self.counter)

    @attr(kind='small')
    def test_create_subnet(self):
        param = dict(context=context.get_admin_context(), label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.0.1/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        ret = db.network_get_all(
                context.get_admin_context())
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True

        self.assertTrue(flag)

    @attr(kind='small')
    def test_get_network_id_by_cidr(self):
        param = dict(context=context.get_admin_context(), label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.20.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        uuid = self.net_man.ipam.get_network_id_by_cidr(
                    context.get_admin_context(), cidr=param['cidr'],
                    project_id=context.get_admin_context().project_id)

        self.assertEquals(param['quantum_net_id'], uuid)

    @attr(kind='small')
    def test_get_network_id_by_cidr_except(self):
        param = dict(context=context.get_admin_context(), label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.20.99/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        self.assertRaises(Exception,
            self.net_man.ipam.get_network_id_by_cidr,
                    context.get_admin_context(), cidr=param['cidr'],
                    project_id=context.get_admin_context().project_id)

    @attr(kind='small')
    def test_delete_subnets_by_net_id(self):
        param = dict(context=context.get_admin_context(), label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.30.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        ret = db.network_get_all(
                context.get_admin_context())
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
        self.assertTrue(flag)

        self.net_man.ipam.delete_subnets_by_net_id(
                    context.get_admin_context(),
                    net_id=param['quantum_net_id'],
                    project_id=context.get_admin_context().project_id)

        self.assertRaises(exception.NoNetworksFound,
                          db.network_get_all, context.get_admin_context())

    @attr(kind='small')
    def test_delete_subnets_by_net_id_except(self):
        param = dict(context=context.get_admin_context(), label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.30.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.assertRaises(Exception,
            self.net_man.ipam.delete_subnets_by_net_id,
                    context.get_admin_context(),
                    net_id=param['quantum_net_id'],
                    project_id=context.get_admin_context().project_id)

    @attr(kind='small')
    def test_get_project_and_global_net_ids(self):
        param = dict(context=context.get_admin_context(), label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.40.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        ret = db.network_get_all(
                context.get_admin_context())
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
        self.assertTrue(flag)

        ret = self.net_man.ipam.get_project_and_global_net_ids(
                    context.get_admin_context(),
                    project_id=1)
        self.assertEqual([(param['quantum_net_id'], '1')], ret)

    @attr(kind='small')
    def test_get_project_and_global_net_ids_size0(self):

        ret = self.net_man.ipam.get_project_and_global_net_ids(
                    context.get_admin_context(),
                    project_id=1)
        self.assertEqual([], ret)

    @attr(kind='small')
    def test_get_project_and_global_net_ids_size3_and_sort(self):
        param = dict(context=context.get_admin_context(), label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.50.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        param2 = dict(context=context.get_admin_context(), label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-cccc', priority=1,
                     cidr='100.100.60.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param2)

        param3 = dict(context=context.get_admin_context(), label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-dddd', priority=3,
                     cidr='100.100.70.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param3)

        ret = db.network_get_all(
                context.get_admin_context())
        count = 0
        for net_info in ret:
            uuid = net_info.uuid
            if uuid in (param['quantum_net_id'], param2['quantum_net_id'],
                        param3['quantum_net_id']):
                count += 1
        self.assertEqual(3, count)

        ret = self.net_man.ipam.get_project_and_global_net_ids(
                    context.get_admin_context(),
                    project_id=1)

        self.assertEqual([(param2['quantum_net_id'], '1'),
                          (param['quantum_net_id'], '1'),
                          (param3['quantum_net_id'], '1')], ret)

    def _create_instance(self, params=None):
        """Create a test instance"""
        if not params:
            params = {}

        inst = {}
        inst['image_ref'] = '1'
        inst['reservation_id'] = 'r-fakeres'
        inst['launch_time'] = '10'
        inst['user_id'] = 'fake'
        inst['project_id'] = 'fake'
        type_id = instance_types.get_instance_type_by_name('m1.tiny')['id']
        inst['instance_type_id'] = type_id
        inst['ami_launch_index'] = 0
        inst['host'] = 'host1'
        inst['local_gb'] = 10
        inst['config_drive'] = 1
        inst['kernel_id'] = 2
        inst['ramdisk_id'] = 3
        inst['config_drive_id'] = 1
        inst['key_data'] = 'ABCDEFG'

        inst.update(params)
        return db.instance_create(context.get_admin_context(), inst)

    def _setup_networking(self,
                          instance_id, ip='1.2.3.4', flo_addr='1.2.1.2'):
        ctxt = context.get_admin_context()

        network_ref = db.project_get_networks(ctxt,
                                              'fake',
                                              associate=True)[0]
        vif = {'address': '56:12:12:12:12:12',
               'network_id': network_ref['id'],
               'instance_id': instance_id}
        vif_ref = db.virtual_interface_create(ctxt, vif)

        fixed_ip = {'address': ip,
                    'network_id': network_ref['id'],
                    'virtual_interface_id': vif_ref['id'],
                    'allocated': True,
                    'instance_id': instance_id}
        db.fixed_ip_create(ctxt, fixed_ip)
        fix_ref = db.fixed_ip_get_by_address(ctxt, ip)
        db.floating_ip_create(ctxt, {'address': flo_addr,
                                 'fixed_ip_id': fix_ref['id']})
        return network_ref

    @attr(kind='small')
    def test_allocate_fixed_ip(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.70.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)

        ins_ref = self._create_instance()
        vif = {'address': '56:12:12:12:12:12',
               'network_id': net_info['id'],
               'instance_id': ins_ref['id']}

        vif_ref = db.virtual_interface_create(ctxt, vif)

        ip = '10.10.10.10'
        fixed_ip = {'address': ip,
#                    'network_id': net_info['id'],
#                    'virtual_interface_id': vif_ref['id'],
                    'allocated': False,
#                    'instance_id': ins_ref['id']
                    }
        db.fixed_ip_create(ctxt, fixed_ip)
#        fix_ref = db.fixed_ip_get_by_address(ctxt, ip)

        net_dict = dict(uuid=net_info['uuid'], fixed_ip=ip, gw=False)
        ret = self.net_man.ipam.allocate_fixed_ip(
                    ctxt,
                    net=net_dict, tenant_id=None,
                    vif_rec=vif_ref)

        self.assertEqual(ip, ret)

    @attr(kind='small')
    def test_allocate_fixed_ip_cidr_empty(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.70.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)
        net_info['cidr'] = None

        ins_ref = self._create_instance()
        vif = {'address': '56:12:12:12:12:12',
               'network_id': net_info['id'],
               'instance_id': ins_ref['id']}

        vif_ref = db.virtual_interface_create(ctxt, vif)

        ip = '10.10.10.10'
        fixed_ip = {'address': ip,
#                    'network_id': net_info['id'],
#                    'virtual_interface_id': vif_ref['id'],
                    'allocated': False,
#                    'instance_id': ins_ref['id']
                    }
        db.fixed_ip_create(ctxt, fixed_ip)
#        fix_ref = db.fixed_ip_get_by_address(ctxt, ip)

        net_dict = dict(uuid=net_info['uuid'], fixed_ip=ip, gw=False)
        ret = self.net_man.ipam.allocate_fixed_ip(
                    ctxt,
                    net=net_dict, tenant_id=None,
                    vif_rec=vif_ref)

        self.assertEqual(ip, ret)

    @attr(kind='small')
    def test_allocate_fixed_ip_fixedip_empty(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.70.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)

        ins_ref = self._create_instance()
        vif = {'address': '56:12:12:12:12:12',
               'network_id': net_info['id'],
               'instance_id': ins_ref['id']}

        vif_ref = db.virtual_interface_create(ctxt, vif)

        ip = '10.10.10.10'
        fixed_ip = {'address': ip,
#                    'network_id': net_info['id'],
#                    'virtual_interface_id': vif_ref['id'],
                    'allocated': False,
#                    'instance_id': ins_ref['id']
                    }
        db.fixed_ip_create(ctxt, fixed_ip)
#        fix_ref = db.fixed_ip_get_by_address(ctxt, ip)

        # has no fixed_ip field in net
        net_dict = dict(uuid=net_info['uuid'], gw=False)
        ret = self.net_man.ipam.allocate_fixed_ip(
                    ctxt,
                    net=net_dict, tenant_id=None,
                    vif_rec=vif_ref)

        self.assertEqual(ip, ret)

    @attr(kind='small')
    def test_allocate_fixed_ip_except(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.70.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)

        ins_ref = self._create_instance()
        vif = {'address': '56:12:12:12:12:12',
               'network_id': net_info['id'],
               'instance_id': ins_ref['id']}

        vif_ref = db.virtual_interface_create(ctxt, vif)

        ip = '10.10.10.10'
        fixed_ip = {'address': ip,
#                    'network_id': net_info['id'],
#                    'virtual_interface_id': vif_ref['id'],
                    'allocated': False,
                    'instance_id': ins_ref['id']
                    }
        db.fixed_ip_create(ctxt, fixed_ip)
#        fix_ref = db.fixed_ip_get_by_address(ctxt, ip)

        net_dict = dict(uuid=net_info['uuid'], fixed_ip=ip, gw=False)
        self.assertRaises(exception.FixedIpAlreadyInUse,
            self.net_man.ipam.allocate_fixed_ip,
                    ctxt,
                    net=net_dict, tenant_id=None,
                    vif_rec=vif_ref)

    @attr(kind='small')
    def test_reserve_fixed_ip(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.70.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)

        ins_ref = self._create_instance()

        ip = '10.10.10.20'
        fixed_ip = {'address': ip,
                    'network_id': net_info['id'],
#                    'virtual_interface_id': vif_ref['id'],
                    'allocated': False,
#                    'instance_id': ins_ref['id']
                    }
        db.fixed_ip_create(ctxt, fixed_ip)

        ret = self.net_man.ipam.reserve_fixed_ip(
                    ctxt,
                    address=ip, quantum_net_id=net_info['uuid'],tenant_id=None)

        fixed_ip = db.fixed_ip_get_by_address(ctxt, ip)
        self.assertEqual(True, fixed_ip['reserved'])

    @attr(kind='small')
    def test_reserve_fixed_ip_except_notfound_ip(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.70.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)

        ins_ref = self._create_instance()

        ip = '10.10.10.20'
        fixed_ip = {'address': ip,
                    'network_id': net_info['id'],
#                    'virtual_interface_id': vif_ref['id'],
                    'allocated': False,
#                    'instance_id': ins_ref['id']
                    }
        db.fixed_ip_create(ctxt, fixed_ip)

        self.assertRaises(exception.FixedIpNotFoundForAddress,
            self.net_man.ipam.reserve_fixed_ip,
                    ctxt,
                    address='20.10.10.20',
                    quantum_net_id=net_info['uuid'],tenant_id=None)

    @attr(kind='small')
    def test_reserve_fixed_ip_except_notfound_net(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.70.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)

        ins_ref = self._create_instance()

        ip = '10.10.10.20'
        fixed_ip = {'address': ip,
                    'network_id': net_info['id'],
#                    'virtual_interface_id': vif_ref['id'],
                    'allocated': False,
#                    'instance_id': ins_ref['id']
                    }
        db.fixed_ip_create(ctxt, fixed_ip)

        self.assertRaises(exception.FixedIpNotFoundForNetwork,
            self.net_man.ipam.reserve_fixed_ip,
                    ctxt,
                    address=ip,
                    quantum_net_id=net_info['id'],tenant_id=None)

    @attr(kind='small')
    def test_reserve_fixed_ip_except_used_ip(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.70.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)

        ins_ref = self._create_instance()

        ip = '10.10.10.20'
        fixed_ip = {'address': ip,
                    'network_id': net_info['id'],
#                    'virtual_interface_id': vif_ref['id'],
                    'allocated': True,
#                    'instance_id': ins_ref['id']
                    }
        db.fixed_ip_create(ctxt, fixed_ip)

        self.assertRaises(exception.FixedIpAlreadyInUse,
            self.net_man.ipam.reserve_fixed_ip,
                    ctxt,
                    address=ip,
                    quantum_net_id=net_info['uuid'],tenant_id=None)

    @attr(kind='small')
    def test_get_tenant_id_by_net_id(self):
        ctxt = context.get_admin_context()

        ret = self.net_man.ipam.get_tenant_id_by_net_id(ctxt,
                    net_id='1', vif_id='2', project_id='3')
        self.assertEqual('3', ret)

    @attr(kind='small')
    def test_get_subnets_by_net_id(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.80.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)

        ret = self.net_man.ipam.get_subnets_by_net_id(ctxt,
                    tenant_id=1, net_id=net_info['uuid'], _vif_id=None)

        v4 = {
            'network_id': net_info['uuid'],
            'cidr': net_info['cidr'],
            'gateway': net_info['gateway'],
            'broadcast': net_info['broadcast'],
            'netmask': net_info['netmask'],
            'dns1': net_info['dns1'],
            'dns2': net_info['dns2']}
        v6 = {
            'network_id': net_info['uuid'],
            'cidr': net_info['cidr_v6'],
            'gateway': net_info['gateway_v6'],
            'broadcast': None,
            'netmask': None,
            'dns1': None,
            'dns2': None}

        self.assertEqual((v4, v6), ret)

    @attr(kind='small')
    def test_get_v6_ips_by_interface(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='192.168.100.0/24',cidr_v6='2001:db8:0:f::/64',
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)

        ins_ref = self._create_instance()
#        vif = {'address': '192.168.100.100',
        vif = {'address': '02:16:3e:33:77:55',
               'network_id': net_info['id'],
               'instance_id': ins_ref['id'],
               'uuid': 'bcde-fghj'}

        vif_ref = db.virtual_interface_create(ctxt, vif)

#        ip = '10.10.10.10'
#        fixed_ip = {'address': ip,
##                    'network_id': net_info['id'],
##                    'virtual_interface_id': vif_ref['id'],
#                    'allocated': False,
#                    'instance_id': ins_ref['id']
#                    }
#        db.fixed_ip_create(ctxt, fixed_ip)

        ret = self.net_man.ipam.get_v6_ips_by_interface(
                    ctxt,
                    net_id=net_info['uuid'], vif_id=vif_ref['uuid'],
                    project_id='1')

        self.assertEqual(['2001:db8:0:f:16:3eff:fe33:7755'], ret)

    @attr(kind='small')
    def test_get_v6_ips_by_interface_cidr_v6_empty(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.70.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)

        ins_ref = self._create_instance()
        vif = {'address': '56:12:12:12:12:12',
               'network_id': net_info['id'],
               'instance_id': ins_ref['id']}

        vif_ref = db.virtual_interface_create(ctxt, vif)

        ret = self.net_man.ipam.get_v6_ips_by_interface(
                    ctxt,
                    net_id=net_info['uuid'], vif_id=vif_ref['id'],
                    project_id='1')
        self.assertEqual([], ret)

    @attr(kind='small')
    def test_verify_subnet_exists(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.70.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)

        ret = self.net_man.ipam.verify_subnet_exists(ctxt,
                    tenant_id=None, quantum_net_id=net_info['uuid'])
        self.assertEqual(True, ret)

    @attr(kind='small')
    def test_verify_subnet_exists_except(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.70.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)

        self.assertRaises(exception.NetworkNotFoundForUUID,
            self.net_man.ipam.verify_subnet_exists, ctxt,
                    tenant_id=None, quantum_net_id=net_info['id'])

    @attr(kind='small')
    def test_deallocate_ips_by_vif(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.70.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)

        ins_ref = self._create_instance()

        vif = {'address': '56:12:12:12:12:12',
               'network_id': net_info['id'],
               'instance_id': ins_ref['id']}

        vif_ref = db.virtual_interface_create(ctxt, vif)

        ip = '10.10.10.30'
        fixed_ip = {'address': ip,
                    'network_id': net_info['id'],
                    'virtual_interface_id': vif_ref['id'],
                    'allocated': True,
                    'instance_id': ins_ref['id']
                    }
        db.fixed_ip_create(ctxt, fixed_ip)

        ret = self.net_man.ipam.deallocate_ips_by_vif(ctxt,
                    tenant_id=None, 
                    net_id=net_info['uuid'],
                    vif_ref=vif_ref)

        fip = db.fixed_ip_get_by_address(ctxt, ip)
        self.assertEqual(False, fip.allocated)
        self.assertEqual(None, fip.virtual_interface_id)
        self.assertEqual(None, fip.virtual_interface_id)

    @attr(kind='small')
    def test_deallocate_ips_by_vif_multi(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.70.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)

        ins_ref = self._create_instance()

        vif = {'address': '56:12:12:12:12:12',
               'network_id': net_info['id'],
               'instance_id': ins_ref['id']}

        vif_ref = db.virtual_interface_create(ctxt, vif)

        ip = '10.10.10.30'
        fixed_ip = {'address': ip,
                    'network_id': net_info['id'],
                    'virtual_interface_id': vif_ref['id'],
                    'allocated': True,
                    'instance_id': ins_ref['id']
                    }
        db.fixed_ip_create(ctxt, fixed_ip)

        # second
        ip2 = '10.10.10.40'
        fixed_ip2 = {'address': ip2,
                    'network_id': net_info['id'],
                    'virtual_interface_id': vif_ref['id'],
                    'allocated': True,
                    'instance_id': ins_ref['id']
                    }
        db.fixed_ip_create(ctxt, fixed_ip2)

        ret = self.net_man.ipam.deallocate_ips_by_vif(ctxt,
                    tenant_id=None, 
                    net_id=net_info['uuid'],
                    vif_ref=vif_ref)

        fip = db.fixed_ip_get_by_address(ctxt, ip)
        self.assertEqual(False, fip.allocated)
        self.assertEqual(None, fip.virtual_interface_id)
        self.assertEqual(None, fip.virtual_interface_id)

        fip = db.fixed_ip_get_by_address(ctxt, ip2)
        self.assertEqual(False, fip.allocated)
        self.assertEqual(None, fip.virtual_interface_id)
        self.assertEqual(None, fip.virtual_interface_id)

    @attr(kind='small')
    def test_deallocate_ips_by_vif_except(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.70.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)

        ins_ref = self._create_instance()

        vif = {'address': '56:12:12:12:12:12',
               'network_id': net_info['id'],
               'instance_id': ins_ref['id']}

        vif_ref = db.virtual_interface_create(ctxt, vif)

        ip = '10.10.10.30'
        fixed_ip = {'address': ip,
                    'network_id': net_info['id'],
                    'virtual_interface_id': vif_ref['id'],
                    'allocated': True,
                    'instance_id': ins_ref['id']
                    }
        db.fixed_ip_create(ctxt, fixed_ip)

        vif_ref['id'] = 'not_exist_id'
        ret = self.net_man.ipam.deallocate_ips_by_vif(ctxt,
                    tenant_id=None, 
                    net_id=net_info['uuid'],
                    vif_ref=vif_ref)

        fip = db.fixed_ip_get_by_address(ctxt, ip)
        self.assertEqual(True, fip.allocated)
        self.assertEqual(ins_ref['id'], fip.virtual_interface_id)

    @attr(kind='small')
    def test_deallocate_ips_by_vif_except_multi(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.70.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)

        ins_ref = self._create_instance()

        vif = {'address': '56:12:12:12:12:12',
               'network_id': net_info['id'],
               'instance_id': ins_ref['id']}

        vif_ref = db.virtual_interface_create(ctxt, vif)

        ip = '10.10.10.50'
        fixed_ip = {'address': ip,
                    'network_id': net_info['id'],
                    'virtual_interface_id': vif_ref['id'],
                    'allocated': True,
                    'instance_id': ins_ref['id']
                    }
        db.fixed_ip_create(ctxt, fixed_ip)

        ip2 = '10.10.10.60'
        fixed_ip2 = {'address': ip2,
                    'network_id': net_info['id'],
                    'virtual_interface_id': vif_ref['id'],
                    'allocated': True,
                    'instance_id': ins_ref['id']
                    }
        db.fixed_ip_create(ctxt, fixed_ip2)

        self.counter = 0
        def fake_update(context, address, values):
            self.counter += 1
            if self.counter == 2:
                raise exception.FixedIpNotFoundForAddress

        self.stubs.Set(db, 'fixed_ip_update', fake_update)

        self.assertRaises(exception.FixedIpNotFoundForAddress,
            self.net_man.ipam.deallocate_ips_by_vif, ctxt,
                    tenant_id=None, 
                    net_id=net_info['uuid'],
                    vif_ref=vif_ref)


    @attr(kind='small')
    def test_get_allocated_ips_0(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.70.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)

        ins_ref = self._create_instance()

        vif = {'address': '56:12:12:12:12:12',
               'network_id': net_info['id'],
               'instance_id': ins_ref['id'],
               'uuid': 'aaaa-bbbb-cccc-dddd'}

        vif_ref = db.virtual_interface_create(ctxt, vif)

        ret = self.net_man.ipam.get_allocated_ips(ctxt,
                    subnet_id=net_info['uuid'],
                    project_id='1')

        self.assertEqual([], ret)

    @attr(kind='small')
    def test_get_allocated_ips_unmatch(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.70.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)

        ins_ref = self._create_instance()

        vif = {'address': '56:12:12:12:12:12',
               'network_id': net_info['id'],
               'instance_id': ins_ref['id'],
               'uuid': 'aaaa-bbbb-cccc-dddd'}

        vif_ref = db.virtual_interface_create(ctxt, vif)

        ip = '10.10.10.80'
        fixed_ip = {'address': ip,
                    'network_id': '999999',
                    'virtual_interface_id': vif_ref['id'],
                    'allocated': True,
                    'instance_id': ins_ref['id']
                    }
        db.fixed_ip_create(ctxt, fixed_ip)

        # second
        ip2 = '10.10.10.90'
        fixed_ip2 = {'address': ip2,
                    'network_id': '999999',
                    'virtual_interface_id': vif_ref['id'],
                    'allocated': True,
                    'instance_id': ins_ref['id']
                    }
        db.fixed_ip_create(ctxt, fixed_ip2)

        ret = self.net_man.ipam.get_allocated_ips(ctxt,
                    subnet_id=net_info['uuid'],
                    project_id='1')

        self.assertEqual([], ret)

    @attr(kind='small')
    def test_get_allocated_ips_multi(self):
        ctxt = context.get_admin_context()
        param = dict(context=ctxt, label='label-1',
                     tenant_id='1', quantum_net_id='aaaa-bbbb', priority=2,
                     cidr='100.100.70.0/24',cidr_v6=None,
                     gateway=None, gateway_v6=None,
                     dns1='102.168.10.1',
                     dns2='102.168.10.2', dhcp_server=None)

        self.net_man.ipam.create_subnet(**param)

        net_info = None
        ret = db.network_get_all(ctxt)
        flag = False
        for net_info in ret:
            uuid = net_info.uuid
            if uuid == param['quantum_net_id']:
                flag = True
                break
        self.assertTrue(flag)

        ins_ref = self._create_instance()

        vif = {'address': '56:12:12:12:12:12',
               'network_id': net_info['id'],
               'instance_id': ins_ref['id'],
               'uuid': 'aaaa-bbbb-cccc-dddd'}

        vif_ref = db.virtual_interface_create(ctxt, vif)

        ip = '10.10.10.80'
        fixed_ip = {'address': ip,
                    'network_id': net_info['id'],
                    'virtual_interface_id': vif_ref['id'],
                    'allocated': True,
                    'instance_id': ins_ref['id']
                    }
        db.fixed_ip_create(ctxt, fixed_ip)

        # second
        ip2 = '10.10.10.90'
        fixed_ip2 = {'address': ip2,
                    'network_id': net_info['id'],
                    'virtual_interface_id': vif_ref['id'],
                    'allocated': True,
                    'instance_id': ins_ref['id']
                    }
        db.fixed_ip_create(ctxt, fixed_ip2)

        ret = self.net_man.ipam.get_allocated_ips(ctxt,
                    subnet_id=net_info['uuid'],
                    project_id='1')

        self.assertEqual((ip, vif['uuid'], True), ret[0])
        self.assertEqual((ip2, vif['uuid'], True), ret[1])


class QuantumNovaIPAMTestCase(QuantumTestCaseBase, test.TestCase):

    def setUp(self):
        super(QuantumNovaIPAMTestCase, self).setUp()

        self.net_man = quantum_manager.QuantumManager(
                ipam_lib="nova.network.quantum.nova_ipam_lib",
                q_conn=FakeQuantumClientConnection())

        # Tests seem to create some networks by default, which
        # we don't want.  So we delete them.

        ctx = context.RequestContext('user1', 'fake_project1').elevated()
        for n in db.network_get_all(ctx):
            db.network_delete_safe(ctx, n['id'])

        # Other unit tests (e.g., test_compute.py) have a nasty
        # habit of of creating fixed IPs and not cleaning up, which
        # can confuse these tests, so we remove all existing fixed
        # ips before starting.
        session = get_session()
        result = session.query(models.FixedIp).all()
        with session.begin():
            for fip_ref in result:
                session.delete(fip_ref)


class QuantumManagerTestCase(test.TestCase):
    """Test for nova.network.quantum.manager.QuantumManager. """
    def setUp(self):
        super(QuantumManagerTestCase, self).setUp()
        self.quantummanager = quantum_manager.QuantumManager(
                                            q_conn=None, ipam_lib=None)

    def _setup_networking(self,
                          instance_id, ip='1.2.3.4', flo_addr='1.2.1.2'):
        ctxt = context.get_admin_context()

        network_ref = db.project_get_networks(ctxt,
                                              'fake',
                                              associate=True)[0]
        vif = {'address': '56:12:12:12:12:12',
               'network_id': network_ref['id'],
               'instance_id': instance_id}
        vif_ref = db.virtual_interface_create(ctxt, vif)

        fixed_ip = {'address': ip,
                    'network_id': network_ref['id'],
                    'virtual_interface_id': vif_ref['id'],
                    'allocated': True,
                    'instance_id': instance_id}
        db.fixed_ip_create(ctxt, fixed_ip)
        fix_ref = db.fixed_ip_get_by_address(ctxt, ip)
        db.floating_ip_create(ctxt, {'address': flo_addr,
                                 'fixed_ip_id': fix_ref['id']})
        return network_ref

    def _create_instance(self, params=None):
        """Create a test instance"""
        if not params:
            params = {}

        inst = {}
        inst['image_ref'] = '1'
        inst['reservation_id'] = 'r-fakeres'
        inst['launch_time'] = '10'
        inst['user_id'] = 'fake'
        inst['project_id'] = 'fake'
        type_id = instance_types.get_instance_type_by_name('m1.tiny')['id']
        inst['instance_type_id'] = type_id
        inst['ami_launch_index'] = 0
        inst['host'] = 'host1'
        inst['local_gb'] = 10
        inst['config_drive'] = 1
        inst['kernel_id'] = 2
        inst['ramdisk_id'] = 3
        inst['config_drive_id'] = 1
        inst['key_data'] = 'ABCDEFG'

        inst.update(params)
        return db.instance_create(context.get_admin_context(), inst)

    @attr(kind='small')
    def test_init(self):
        """Test for nova.network.quantum.manager.QuantumManager.init. """

        self.assertNotEqual(None, self.quantummanager.q_conn)
        self.assertEqual(True, isinstance(self.quantummanager.q_conn,
                                quantum_connection.QuantumClientConnection))
        self.assertEqual(True, isinstance(self.quantummanager.ipam,
                                quantum.nova_ipam_lib.QuantumNovaIPAMLib))

    @attr(kind='small')
    def test_create_networks_exception_num(self):
        """Test for quantum.manager.QuantumManager.create_networks. """
        param = dict(context=None, label=None, cidr=None, multi_host=None,
                     num_networks=2,
                     network_size=None, cidr_v6=None, gateway_v6=None,
                     bridge=None, bridge_interface=None, dns1=None,
                     dns2=None, uuid=None)

        self.assertRaises(Exception,
            self.quantummanager.create_networks, **param)

    @attr(kind='small')
    def test_create_networks_exception_notexist(self):
        """Test for quantum.manager.QuantumManager.create_networks. """
        param = dict(context=None, label=None, cidr=None, multi_host=None,
                     num_networks=1,
                     network_size=None, cidr_v6=None, gateway_v6=None,
                     bridge=None, bridge_interface=None, dns1=None,
                     dns2=None,
                     uuid='not_exist_net_id',
                     project_id='')

        def fake_network_exists(self, tenant_id, net_id):
            return False

        self.stubs.Set(quantum_connection.QuantumClientConnection,
                       'network_exists', fake_network_exists)

        self.assertRaises(Exception,
                          self.quantummanager.create_networks, **param)

    @attr(kind='small')
    def test_get_instance_nw_info_exception(self):
        """Test for quantum.manager.QuantumManager.get_instance_nw_info. """
        def fake_get_port_by_attachment(self, tenant_id, attachment_id):
            return (None, None)

        self.stubs.Set(quantum_connection.QuantumClientConnection,
                       'get_port_by_attachment', fake_get_port_by_attachment)

        ins_ref = self._create_instance()
        self._setup_networking(instance_id=ins_ref['id'])

        param = dict(context=context.get_admin_context(),
                     instance_id=ins_ref['id'],
                     instance_type_id=ins_ref['instance_type_id'],
                     host='127.0.0.1')
        self.assertRaises(Exception,
            self.quantummanager.get_instance_nw_info, **param)

    @attr(kind='small')
    def test_deallocate_for_instance_exception_net_not_found(self):
        """Test for quantum.manager.QuantumManager.deallocate_for_instance"""
        def fake_get_port_by_attachment(self, tenant_id, attachment_id):
            return (None, None)

        self.stubs.Set(quantum_connection.QuantumClientConnection,
                       'get_port_by_attachment', fake_get_port_by_attachment)

        def fake_error(msg):
            self.assertTrue(
                msg.startswith('Unable to find port with attachment'))

        self.stubs.Set(quantum_manager.LOG, 'error', fake_error)

        ins_ref = self._create_instance()
        self._setup_networking(instance_id=ins_ref['id'])

        param = dict(instance_id=ins_ref['id'])

        self.quantummanager.deallocate_for_instance(
                context=context.get_admin_context(), **param)

    @attr(kind='small')
    def test_deallocate_for_instance_exception_no_instance(self):
        """Test for quantum.manager.QuantumManager.deallocate_for_instance"""
        def fake_get_port_by_attachment(self, tenant_id, attachment_id):
            return (1, 999)

        self.stubs.Set(quantum_connection.QuantumClientConnection,
                       'get_port_by_attachment', fake_get_port_by_attachment)

        def fake_detach_and_delete_port(self, q_tenant_id,
                                        net_id, port_id):
            pass

        self.stubs.Set(quantum_connection.QuantumClientConnection,
                       'detach_and_delete_port', fake_detach_and_delete_port)

        def fake_virtual_interface_delete_by_instance(
                                                context, instance_id):
            raise exception.InstanceNotFound

        self.stubs.Set(quantum_manager.db,
                       'virtual_interface_delete_by_instance',
                       fake_virtual_interface_delete_by_instance)

        def fake_error(msg):
            self.assertTrue(
                msg.startswith('Attempted to deallocate non-existent'))

        self.stubs.Set(quantum_manager.LOG, 'error', fake_error)

        ins_ref = self._create_instance()
        self._setup_networking(instance_id=ins_ref['id'])

        param = dict(instance_id=ins_ref['id'])

        self.quantummanager.deallocate_for_instance(
                context=context.get_admin_context(), **param)

    @attr(kind='small')
    def test_validate_networks_parameter(self):
        """Test for quantum.manager.QuantumManager.validate_networks. """
        ref = self.quantummanager.validate_networks(context=None,
                                                    networks=None)
        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_validate_networks_exception(self):
        """Test for quantum.manager.QuantumManager.validate_networks. """

        def fake_network_exists(self, tenant_id, net_id):
            return False

        self.stubs.Set(quantum_connection.QuantumClientConnection,
                       'network_exists', fake_network_exists)

        def fake_verify_subnet_exists(context, project_id, net_id):
            return False

        self.stubs.Set(self.quantummanager.ipam,
                       'verify_subnet_exists', fake_verify_subnet_exists)

        na = [('127.0.0.1', 1)]
        self.assertRaises(exception.NetworkNotFound,
            self.quantummanager.validate_networks,
                context=context.get_admin_context(), networks=na)
