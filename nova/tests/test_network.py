# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 Rackspace
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
"""
Tests For nova.network.manager
"""
import datetime
import mox

from eventlet import greenpool
from nose.plugins.attrib import attr
from nova import context
from nova import db
from nova import exception
from nova import flags
from nova import ipv6
from nova import log as logging
from nova import quota
from nova import rpc
from nova import test
from nova import utils
from nova.network import api as network_api
from nova.network import manager as network_manager

from nose.plugins.skip import SkipTest


LOG = logging.getLogger('nova.tests.network')


HOST = "testhost"


class FakeDriver(object):
    pass


class FakeModel(dict):
    """Represent a model from the db"""
    def __init__(self, *args, **kwargs):
        self.update(kwargs)

    def __getattr__(self, name):
        return self[name]


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
             'vlan': None,
             'host': HOST,
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
             'vlan': None,
             'host': HOST,
             'project_id': 'fake_project',
             'vpn_public_address': '192.168.1.2'}]


fixed_ips = [{'id': 0,
              'network_id': 0,
              'address': '192.168.0.100',
              'instance_id': 0,
              'allocated': False,
              'virtual_interface_id': 0,
              'floating_ips': []},
             {'id': 0,
              'network_id': 1,
              'address': '192.168.1.100',
              'instance_id': 0,
              'allocated': False,
              'virtual_interface_id': 0,
              'floating_ips': []}]


flavor = {'id': 0,
          'rxtx_cap': 3}


floating_ip_fields = {'id': 0,
                      'address': '192.168.10.100',
                      'fixed_ip_id': 0,
                      'project_id': None,
                      'auto_assigned': False}

vifs = [{'id': 0,
         'address': 'DE:AD:BE:EF:00:00',
         'uuid': '00000000-0000-0000-0000-0000000000000000',
         'network_id': 0,
         'network': FakeModel(**networks[0]),
         'instance_id': 0},
        {'id': 1,
         'address': 'DE:AD:BE:EF:00:01',
         'uuid': '00000000-0000-0000-0000-0000000000000001',
         'network_id': 1,
         'network': FakeModel(**networks[1]),
         'instance_id': 0},
        {'id': 2,
         'address': 'DE:AD:BE:EF:00:02',
         'uuid': '00000000-0000-0000-0000-0000000000000002',
         'network_id': 2,
         'network': None,
         'instance_id': 0}]


class FlatNetworkTestCase(test.TestCase):
    def setUp(self):
        super(FlatNetworkTestCase, self).setUp()
        self.network = network_manager.FlatManager(host=HOST)
        self.network.db = db
        self.context = context.RequestContext('testuser', 'testproject',
                                              is_admin=False)

    def test_get_instance_nw_info(self):
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')

        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn(fixed_ips)
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn(vifs)
        db.instance_type_get(mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn(flavor)
        self.mox.ReplayAll()

        nw_info = self.network.get_instance_nw_info(None, 0, 0, None)

        self.assertTrue(nw_info)

        for i, nw in enumerate(nw_info):
            i8 = i + 8
            check = {'bridge': 'fa%s' % i,
                     'cidr': '192.168.%s.0/24' % i,
                     'cidr_v6': '2001:db%s::/64' % i8,
                     'id': i,
                     'multi_host': False,
                     'injected': 'DONTCARE',
                     'bridge_interface': 'fake_fa%s' % i,
                     'vlan': None}

            self.assertDictMatch(nw[0], check)

            check = {'broadcast': '192.168.%s.255' % i,
                     'dhcp_server': '192.168.%s.1' % i,
                     'dns': 'DONTCARE',
                     'gateway': '192.168.%s.1' % i,
                     'gateway6': '2001:db%s::1' % i8,
                     'ip6s': 'DONTCARE',
                     'ips': 'DONTCARE',
                     'label': 'test%s' % i,
                     'mac': 'DE:AD:BE:EF:00:0%s' % i,
                     'vif_uuid': ('00000000-0000-0000-0000-000000000000000%s' %
                                  i),
                     'rxtx_cap': 'DONTCARE',
                     'should_create_vlan': False,
                     'should_create_bridge': False}
            self.assertDictMatch(nw[1], check)

            check = [{'enabled': 'DONTCARE',
                      'ip': '2001:db%s::dcad:beff:feef:%s' % (i8, i),
                      'netmask': '64'}]
            self.assertDictListMatch(nw[1]['ip6s'], check)

            check = [{'enabled': '1',
                      'ip': '192.168.%s.100' % i,
                      'netmask': '255.255.255.0'}]
            self.assertDictListMatch(nw[1]['ips'], check)

    @attr(kind='small')
    def test_validate_networks(self):
        """
        no exception is raised (db.fixed_ip_get_by_address is called)
        """
        self._context = None
        self._address = None
        fixed_ip = dict(fixed_ips[1])
        fixed_ip['network'] = FakeModel(**networks[1])
        fixed_ip['instance'] = None

        def stub_fixed_ip_get_by_address(context, address):
            self._context = context
            self._address = address
            return fixed_ip

        self.mox.StubOutWithMock(db, 'network_get_all_by_uuids')
        self.stubs.Set(db, 'fixed_ip_get_by_address',
                       stub_fixed_ip_get_by_address)

        requested_networks = [("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                               "192.168.1.100")]
        db.network_get_all_by_uuids(mox.IgnoreArg(),
                                mox.IgnoreArg()).AndReturn(networks)

        self.mox.ReplayAll()
        self.network.validate_networks(self.context, requested_networks)
        self.assertTrue(self._context)
        self.assertEqual(requested_networks[0][1], self._address)

    @attr(kind='small')
    def test_validate_networks_none_requested_networks(self):
        """
        none is returned
        """
        res = self.network.validate_networks(self.context, None)
        self.assertTrue(res is None)

    @attr(kind='small')
    def test_validate_networks_empty_requested_networks(self):
        """
        none is returned
        """
        requested_networks = []

        res = self.network.validate_networks(self.context, requested_networks)
        self.assertTrue(res is None)

    def test_validate_networks_invalid_fixed_ip(self):
        self.mox.StubOutWithMock(db, 'network_get_all_by_uuids')
        requested_networks = [(1, "192.168.0.100.1")]
        db.network_get_all_by_uuids(mox.IgnoreArg(),
                                mox.IgnoreArg()).AndReturn(networks)
        self.mox.ReplayAll()

        self.assertRaises(exception.FixedIpInvalid,
                          self.network.validate_networks, None,
                          requested_networks)

    def test_validate_networks_empty_fixed_ip(self):
        self.mox.StubOutWithMock(db, 'network_get_all_by_uuids')

        requested_networks = [(1, "")]
        db.network_get_all_by_uuids(mox.IgnoreArg(),
                                mox.IgnoreArg()).AndReturn(networks)
        self.mox.ReplayAll()

        self.assertRaises(exception.FixedIpInvalid,
                          self.network.validate_networks,
                          None, requested_networks)

    @attr(kind='small')
    def test_validate_networks_none_fixed_ip(self):
        """
        no exception is raised (db.network_get_all_by_uuids is called)
        """
        self._context = None
        self._network_uuids = None
        self._project_id = None
        requested_networks = [(1, None)]

        def stub_network_get_all_by_uuids(
                        context, network_uuids, project_id=None):
            self._context = context
            self._network_uuids = network_uuids
            self._project_id = project_id
            return requested_networks

        self.stubs.Set(db, 'network_get_all_by_uuids',
                       stub_network_get_all_by_uuids)

        self.network.validate_networks(None, requested_networks)
        self.assertEqual(None, self._context)
        self.assertEqual([1], self._network_uuids)
        self.assertTrue(self._project_id is None)

    @attr(kind='small')
    def test_validate_networks_db_fixed_ip_not_found_for_network(self):
        """
        FixedIpNotFoundForNetwork is raised
        """
        self.mox.StubOutWithMock(db, 'network_get_all_by_uuids')
        self.mox.StubOutWithMock(db, "fixed_ip_get_by_address")

        requested_networks = [("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                               "192.168.1.100")]
        db.network_get_all_by_uuids(mox.IgnoreArg(),
                                mox.IgnoreArg()).AndReturn(networks)

        network = dict(networks[1])
        network['uuid'] = 'dummyuuid'
        fixed_ip = dict(fixed_ips[1])
        fixed_ip['network'] = network
        db.fixed_ip_get_by_address(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn(fixed_ip)

        self.mox.ReplayAll()
        self.assertRaises(exception.FixedIpNotFoundForNetwork,
                          self.network.validate_networks,
                          self.context, requested_networks)

    @attr(kind='small')
    def test_validate_networks_db_fixed_ip_already_in_use(self):
        """
        FixedIpAlreadyInUse is raised
        """
        self.mox.StubOutWithMock(db, 'network_get_all_by_uuids')
        self.mox.StubOutWithMock(db, "fixed_ip_get_by_address")

        requested_networks = [("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                               "192.168.1.100")]
        db.network_get_all_by_uuids(mox.IgnoreArg(),
                                mox.IgnoreArg()).AndReturn(networks)

        fixed_ip = dict(fixed_ips[1])
        fixed_ip['network'] = dict(networks[1])
        fixed_ip['instance'] = {'id': 0}
        db.fixed_ip_get_by_address(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn(fixed_ip)

        self.mox.ReplayAll()
        self.assertRaises(exception.FixedIpAlreadyInUse,
                          self.network.validate_networks,
                          self.context, requested_networks)

    @attr(kind='small')
    def test_add_fixed_ip_instance_without_vpn_requested_networks(self):
        """
        address is not set and db.fixed_ip_associate_pool is called
        """
        self._context = None
        self._network_id = None
        self._instance_id = None
        self._host = None

        def stub_fixed_ip_associate_pool(
                        context, network_id, instance_id=None, host=None):
            self._context = context
            self._network_id = network_id
            self._instance_id = instance_id
            self._host = host
            return '192.168.0.101'

        self.mox.StubOutWithMock(db, 'network_get')
        self.mox.StubOutWithMock(db, 'network_update')
        self.stubs.Set(db, 'fixed_ip_associate_pool',
                       stub_fixed_ip_associate_pool)
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(db,
                              'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')

        db.fixed_ip_update(mox.IgnoreArg(),
                           mox.IgnoreArg(),
                           mox.IgnoreArg())
        db.virtual_interface_get_by_instance_and_network(mox.IgnoreArg(),
                mox.IgnoreArg(), mox.IgnoreArg()).AndReturn({'id': 0})

        db.instance_get(mox.IgnoreArg(),
                        mox.IgnoreArg()).AndReturn({'security_groups':
                                                             [{'id': 0}]})
        db.network_get(mox.IgnoreArg(),
                       mox.IgnoreArg()).AndReturn(networks[0])
        db.network_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()
        self.network.add_fixed_ip_to_instance(self.context, 1, HOST,
                                              networks[0]['id'])
        self.assertTrue(self._context)
        self.assertEqual(networks[0]['id'], self._network_id)
        self.assertEqual(1, self._instance_id)
        self.assertTrue(self._host is None)

    @attr(kind='small')
    def test_add_fixed_ip_instance_param_instance_does_not_exist(self):
        """
        InstanceNotFound is raised when instance does not exist
        """
#        raise SkipTest('Parameter check is not implemented yet')
        self.mox.StubOutWithMock(db, 'instance_get')
        db.instance_get(mox.IgnoreArg(),
                        mox.IgnoreArg()).AndRaise(exception.InstanceNotFound)
        self.mox.ReplayAll()

        instance_id = 99999  # not exist
        network_id = 1
        self.assertRaises(exception.InstanceNotFound,
                          self.network.add_fixed_ip_to_instance,
                          self.context, instance_id, HOST, network_id)

    @attr(kind='small')
    def test_add_fixed_ip_instance_param_network_does_not_exist(self):
        """
        NetworkNotFound is raised when network does not exist
        """
#        raise SkipTest('Parameter check is not implemented yet')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(db, 'network_get')
        db.instance_get(mox.IgnoreArg(),
                        mox.IgnoreArg()).AndReturn({'id': 0})
        db.network_get(mox.IgnoreArg(),
                        mox.IgnoreArg()).AndRaise(exception.NetworkNotFound)
        self.mox.ReplayAll()

        instance_id = 1
        network_id = 99999  # not exist
        self.assertRaises(exception.NetworkNotFound,
                          self.network.add_fixed_ip_to_instance,
                          self.context, instance_id, HOST, network_id)

    @attr(kind='small')
    def test_init_param_not_network_driver(self):
        """
        network_driver is not set to FLAGS.network_driver
        """
        manager = network_manager.FlatManager(
                        'nova.tests.test_network.FakeDriver')
        self.assertTrue(isinstance(manager.driver, FakeDriver))

    @attr(kind='small')
    def test_init_host(self):
        """
        db.network_update is called
        """
        self._context = None
        self._network_id = None
        self._values = None

        def stub_network_update(context, network_id, values):
            self._context = context
            self._network_id = network_id
            self._values = values

        self.mox.StubOutWithMock(db, 'network_get_all_by_host')
        self.stubs.Set(db, 'network_update', stub_network_update)
        network = networks[0]
        db.network_get_all_by_host(mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn([network])
        self.mox.ReplayAll()

        self.network.init_host()
        self.assertTrue(self._context)
        self.assertEqual(network['id'], self._network_id)
        self.assertEqual(flags.FLAGS.flat_injected, self._values['injected'])

    @attr(kind='small')
    def test_init_host_ex_setup_network(self):
        """
        all networks are initialized even
        when exception is raised in _setup_network
        """
#        raise SkipTest('AssertionError: 2 != 1')
        self._count = 0

        def stub_setup_network(context, network_ref):
            self._count += 1
            raise exception.DBError()

        self.mox.StubOutWithMock(db, 'network_get_all_by_host')
        self.stubs.Set(self.network, '_setup_network', stub_setup_network)
        db.network_get_all_by_host(mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn(networks)
        self.mox.ReplayAll()

        self.assertRaises(exception.DBError,
                          self.network.init_host)
        self.assertEqual(2, self._count)

    @attr(kind='small')
    def test_periodic_tasks_param_not_timeout_fixed_ips(self):
        """
        db.fixed_ip_disassociate_all_by_timeout is not called
        """
        self._is_called = False

        def stub_fixed_ip_disassociate_all_by_timeout(context, host, time):
            self._is_called = True

        self.stubs.Set(db, 'fixed_ip_disassociate_all_by_timeout',
                       stub_fixed_ip_disassociate_all_by_timeout)

        self.network.periodic_tasks(self.context)
        self.assertFalse(self._is_called)

    @attr(kind='small')
    def test_periodic_tasks_param_timeout_fixed_ips(self):
        """
        db.fixed_ip_disassociate_all_by_timeout is called
        """
        self._context = None
        self._host = None
        self._time = None

        def stub_fixed_ip_disassociate_all_by_timeout(context, host, time):
            self._context = context
            self._host = host
            self._time = time
            return 1

        self.mox.StubOutWithMock(utils, 'utcnow')
        self.stubs.Set(db,
                       'fixed_ip_disassociate_all_by_timeout',
                       stub_fixed_ip_disassociate_all_by_timeout)
        now = datetime.datetime.now()
        utils.utcnow().AndReturn(now)
        self.mox.ReplayAll()

        self.network.timeout_fixed_ips = True
        self.network.periodic_tasks(self.context)
        self.assertTrue(self._context)
        self.assertEqual(HOST, self._host)
        time = now - datetime.timedelta(
                        seconds=flags.FLAGS.fixed_ip_disassociate_timeout)
        self.assertEqual(time, self._time)

    @attr(kind='small')
    def test_set_network_host(self):
        """
        host is returned
        """
        self.mox.StubOutWithMock(db, 'network_set_host')
        db.network_set_host(mox.IgnoreArg(),
                            mox.IgnoreArg(),
                            mox.IgnoreArg()).AndReturn(HOST)
        self.mox.ReplayAll()

        res = self.network.set_network_host(self.context, networks[0])
        self.assertEqual(HOST, res)

    @attr(kind='small')
    def test_set_network_host_param_network_ref_is_none(self):
        """
        NetworkNotFound is raised when network_ref is none
        """
#        raise SkipTest('Parameter check is not implemented yet')
        network_ref = None
        self.assertRaises(exception.NetworkNotFound,
                          self.network.set_network_host,
                          self.context, network_ref)

    @attr(kind='small')
    def test_set_network_host_param_network_does_not_exist(self):
        """
        NetworkNotFound is raised when network does not exist
        """
#        raise SkipTest('Parameter check is not implemented yet')
        self.mox.StubOutWithMock(db, 'network_get')
        db.network_get(mox.IgnoreArg(),
                       mox.IgnoreArg()).AndRaise(exception.NetworkNotFound)
        self.mox.ReplayAll()

        network_ref = {'id': 99999}  # not exist
        self.assertRaises(exception.NetworkNotFound,
                          self.network.set_network_host,
                          self.context, network_ref)

    @attr(kind='small')
    def test_allocate_for_instance_param_instance_does_not_exist(self):
        """
        InstanceNotFound is raised when instance does not exist
        """
#        raise SkipTest('Parameter check is not implemented yet')
        self.mox.StubOutWithMock(db, 'instance_get')
        db.instance_get(mox.IgnoreArg(),
                        mox.IgnoreArg()).AndRaise(exception.InstanceNotFound)
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 99999  # not exist
        kwargs['host'] = HOST
        kwargs['project_id'] = 'fake_project'
        kwargs['instance_type_id'] = 1
        kwargs['requested_networks'] = [networks[0]]
        kwargs['vpn'] = False
        self.assertRaises(exception.InstanceNotFound,
                          self.network.allocate_for_instance,
                          self.context, **kwargs)

    @attr(kind='small')
    def test_allocate_for_instance_ex_networks_not_found(self):
        """
        [] is returned when NoNetworksFound is caught
        """
        self.mox.StubOutWithMock(db, 'network_get_all')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        db.network_get_all(mox.IgnoreArg()).AndRaise(exception.NoNetworksFound)
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([])
        db.instance_type_get(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        kwargs['host'] = HOST
        kwargs['project_id'] = 'fake_project'
        kwargs['instance_type_id'] = 1
        kwargs['requested_networks'] = None
        kwargs['vpn'] = False
        res = self.network.allocate_for_instance(self.context, **kwargs)
        self.assertEqual([], res)

    @attr(kind='small')
    def test_allocate_for_instance_ex_add_virtual_interface(self):
        """
        All networks are processed
        even when exception is raised in self.add_virtual_interface()
        """
        self._count = 0

        def stub_virtual_interface_delete_by_instance(context, instance_id):
            self._count += 1

        self.mox.StubOutWithMock(db, 'network_get_all')
        self.mox.StubOutWithMock(db, 'virtual_interface_create')
        db.network_get_all(mox.IgnoreArg()).AndReturn(networks)
        for _ in range(10):
            db.virtual_interface_create(
                        mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndRaise(exception.VirtualInterfaceCreateException)
        self.stubs.Set(db, 'virtual_interface_delete_by_instance',
                            stub_virtual_interface_delete_by_instance)
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        kwargs['host'] = HOST
        kwargs['project_id'] = 'fake_project'
        kwargs['instance_type_id'] = 1
        kwargs['requested_networks'] = None
        kwargs['vpn'] = False
        self.assertRaises(exception.NetworkAllocateException,
                          self.network.allocate_for_instance,
                          self.context, **kwargs)
        self.assertEqual(2, self._count)

    @attr(kind='small')
    def test_deallocate_for_instance(self):
        """
        db.virtual_interface_delete_by_instance is called
        """
        self._context = None
        self._instance_id = None

        def stub_virtual_interface_delete_by_instance(context, instance_id):
            self._context = context
            self._instance_id = instance_id

        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_address')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(db, 'fixed_ip_disassociate')
        self.stubs.Set(db, 'virtual_interface_delete_by_instance',
                       stub_virtual_interface_delete_by_instance)
        fixed_ip = FakeModel(**fixed_ips[0])
        fixed_ip.floating_ips = [{'address': '192.168.10.100',
                                  'auto_assigned': True}]
        db.fixed_ip_get_by_instance(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn([fixed_ip])
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        db.fixed_ip_get_by_address(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'instance': {'id': 0}})
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.fixed_ip_disassociate(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        self.network.deallocate_for_instance(self.context, **kwargs)
        self.assertTrue(self._context)
        self.assertEqual(kwargs.pop('instance_id'), self._instance_id)

    @attr(kind='small')
    def test_deallocate_for_instance_param_instance_does_not_exist(self):
        """
        InstanceNotFound is raised when instance does not exist
        """
#        raise SkipTest('Parameter check is not implemented yet')
        self.mox.StubOutWithMock(db, 'instance_get')
        db.instance_get(mox.IgnoreArg(),
                        mox.IgnoreArg()).AndRaise(exception.InstanceNotFound)
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 99999  # not exist
        self.assertRaises(exception.InstanceNotFound,
                          self.network.deallocate_for_instance,
                          self.context, **kwargs)

    @attr(kind='small')
    def test_deallocate_for_instance_ex_fixed_ip_not_found(self):
        """
        db.deallocate_fixed_ip() is skipped and LOG.warn is called
        """
        self._msg = None
        self._args = None
        self._kwargs = None

        def stub_warn(msg, *args, **kwargs):
            self._msg = msg
            self._args = args
            self._kwargs = kwargs

        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_delete_by_instance')
        fixed_ip = FakeModel(**fixed_ips[0])
        fixed_ip.floating_ips = [{'address': '192.168.10.100',
                                  'auto_assigned': True}]
        db.fixed_ip_get_by_instance(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndRaise(exception.FixedIpNotFoundForInstance)
        db.virtual_interface_delete_by_instance(
                                    mox.IgnoreArg(), mox.IgnoreArg())
        self.stubs.Set(logging.getLogger("nova.network.manager"),
                       'warn', stub_warn)
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        self.network.deallocate_for_instance(self.context, **kwargs)
        self.assertEqual(_("Skipping fixed ip address deallocation "
                           "for instance |%s|"), self._msg)
        self.assertEqual(kwargs['instance_id'], self._args[0])
        self.assertTrue(self._kwargs['context'] is not None)

    @attr(kind='small')
    def test_get_instance_nw_info_param_instance_does_not_exist(self):
        """
        InstanceNotFound is raised when instance does not exist
        """
#        raise SkipTest('Parameter check is not implemented yet')
        self.mox.StubOutWithMock(db, 'instance_get')
        db.instance_get(mox.IgnoreArg(),
                        mox.IgnoreArg()).AndRaise(exception.InstanceNotFound)
        self.mox.ReplayAll()

        instance_id = 99999  # not exist
        self.assertRaises(exception.InstanceNotFound,
                          self.network.get_instance_nw_info,
                          self.context, instance_id, 1, HOST)

    @attr(kind='small')
    def test_deallocate_for_instance_ex_deallocate_fixed_ip(self):
        """
        All FixedIps are deallocated
        even when exception is raised in self.deallocate_fixed_ip()
        """
        self._count = 0

        def stub_deallocate_fixed_ip(context, address, **kwargs):
            self._count += 1
            raise exception.ProcessExecutionError()

        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        _fixed_ips = list([FakeModel(**fixed_ips[0]),
                           FakeModel(**fixed_ips[1])])
        _fixed_ips[0].floating_ips = [
                        {'address': '192.168.0.1', 'auto_assigned': True}]
        _fixed_ips[1].floating_ips = [
                        {'address': '192.168.0.2', 'auto_assigned': True}]
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn(_fixed_ips)
        self.stubs.Set(self.network, 'deallocate_fixed_ip',
                       stub_deallocate_fixed_ip)
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        self.assertRaises(exception.NetworkDeallocateException,
                          self.network.deallocate_for_instance,
                          self.context, **kwargs)
        self.assertEqual(2, self._count)

    @attr(kind='small')
    def test_get_instance_nw_info_ex_fixed_ip_not_found(self):
        """
        fixed_ips is set to [] when FixedIpNotFoundForInstance is caught
        """
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        db.fixed_ip_get_by_instance(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndRaise(exception.FixedIpNotFoundForInstance)
        vif = dict(vifs[1])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([vif])
        db.instance_type_get(mox.IgnoreArg(),
                             mox.IgnoreArg()).AndReturn(flavor)
        self.mox.ReplayAll()

        res = self.network.get_instance_nw_info(self.context, 1, 1, HOST)
        self.assertEqual(1, len(res))
        self.assertEqual([], res[0][1].get('ips'))

    @attr(kind='small')
    def test_get_instance_nw_info_db_vif_network_is_none(self):
        """
        network_info is not appended
        """
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([])
        vif = {}
        vif['network'] = None
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([vif])
        db.instance_type_get(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        res = self.network.get_instance_nw_info(self.context, 1, 1, HOST)
        self.assertEqual([], res)

    @attr(kind='small')
    def test_get_instance_nw_info_db_fixed_ip_network_id_is_not_nw_id(self):
        """
        network_IPs is set to []
        """
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        self.mox.StubOutWithMock(ipv6, 'to_global')
        fixed_ip = dict(fixed_ips[0])
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([fixed_ip])
        vif = dict(vifs[1])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([vif])
        db.instance_type_get(mox.IgnoreArg(),
                             mox.IgnoreArg()).AndReturn(flavor)
        global_ipv6 = '2001:db9::dcad:beff:feef:1'
        ipv6.to_global(mox.IgnoreArg(),
                       mox.IgnoreArg(),
                       mox.IgnoreArg()).AndReturn(global_ipv6)
        self.mox.ReplayAll()

        res = self.network.get_instance_nw_info(self.context, 1, 1, HOST)
        self.assertEqual(1, len(res))
        network = vif['network']
        check = {'bridge': network['bridge'],
                 'id': network['id'],
                 'cidr': network['cidr'],
                 'cidr_v6': network['cidr_v6'],
                 'injected': network['injected'],
                 'vlan': network['vlan'],
                 'bridge_interface': network['bridge_interface'],
                 'multi_host': network['multi_host']}
        self.assertDictMatch(res[0][0], check)

        check = {'label': network['label'],
                 'gateway': network['gateway'],
                 'dhcp_server': network['gateway'],
                 'broadcast': network['broadcast'],
                 'mac': vif['address'],
                 'vif_uuid': vif['uuid'],
                 'rxtx_cap': flavor['rxtx_cap'],
                 'dns': [],
                 'ips': [],
                 'should_create_bridge': False,
                 'should_create_vlan': False,
                 'ip6s': [{'ip': global_ipv6,
                           'netmask': '64', 'enabled': '1'}],
                 'gateway6': network['gateway_v6'],
                 'dns': [network['dns1'], network['dns2']]}
        self.assertDictMatch(res[0][1], check)

    @attr(kind='small')
    def test_get_instance_nw_info_db_multi_host(self):
        """
        dhcp_server is set to fixed_ip['address']
        """
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_network_host')
        self.mox.StubOutWithMock(ipv6, 'to_global')
        fixed_ip = dict(fixed_ips[0])
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([fixed_ip])
        vif = dict(vifs[0])
        network = dict(networks[0])
        network['multi_host'] = True
        vif['network'] = network
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([vif])
        db.instance_type_get(mox.IgnoreArg(),
                             mox.IgnoreArg()).AndReturn(flavor)
        db.fixed_ip_get_by_network_host(mox.IgnoreArg(),
                                        mox.IgnoreArg(),
                                        mox.IgnoreArg()).AndReturn(fixed_ip)
        global_ipv6 = '2001:db9::dcad:beff:feef:1'
        ipv6.to_global(mox.IgnoreArg(),
                       mox.IgnoreArg(),
                       mox.IgnoreArg()).AndReturn(global_ipv6)
        self.mox.ReplayAll()

        res = self.network.get_instance_nw_info(self.context, 1, 1, HOST)
        self.assertEqual(1, len(res))
        check = {'bridge': network['bridge'],
                 'id': network['id'],
                 'cidr': network['cidr'],
                 'cidr_v6': network['cidr_v6'],
                 'injected': network['injected'],
                 'vlan': network['vlan'],
                 'bridge_interface': network['bridge_interface'],
                 'multi_host': network['multi_host']}
        self.assertDictMatch(res[0][0], check)

        check = {'label': network['label'],
                 'gateway': network['gateway'],
                 'dhcp_server': fixed_ip['address'],
                 'broadcast': network['broadcast'],
                 'mac': vif['address'],
                 'vif_uuid': vif['uuid'],
                 'rxtx_cap': flavor['rxtx_cap'],
                 'dns': [],
                 'ips': [{'ip': fixed_ip['address'],
                          'netmask': network['netmask'], 'enabled': '1'}],
                 'should_create_bridge': False,
                 'should_create_vlan': False,
                 'ip6s': [{'ip': global_ipv6,
                           'netmask': '64', 'enabled': '1'}],
                 'gateway6': network['gateway_v6'],
                 'dns': [network['dns1'], network['dns2']]}
        self.assertDictMatch(res[0][1], check)

    @attr(kind='small')
    def test_get_instance_nw_info_db_not_multi_host(self):
        """
        dhcp_server is set to vif['network']['gateway']
        """
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        self.mox.StubOutWithMock(ipv6, 'to_global')
        fixed_ip = dict(fixed_ips[0])
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([fixed_ip])
        vif = dict(vifs[0])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([vif])
        db.instance_type_get(mox.IgnoreArg(),
                             mox.IgnoreArg()).AndReturn(flavor)
        global_ipv6 = '2001:db9::dcad:beff:feef:1'
        ipv6.to_global(mox.IgnoreArg(),
                       mox.IgnoreArg(),
                       mox.IgnoreArg()).AndReturn(global_ipv6)
        self.mox.ReplayAll()

        res = self.network.get_instance_nw_info(self.context, 1, 1, HOST)
        self.assertEqual(1, len(res))
        network = vif['network']
        check = {'bridge': network['bridge'],
                 'id': network['id'],
                 'cidr': network['cidr'],
                 'cidr_v6': network['cidr_v6'],
                 'injected': network['injected'],
                 'vlan': network['vlan'],
                 'bridge_interface': network['bridge_interface'],
                 'multi_host': network['multi_host']}
        self.assertDictMatch(res[0][0], check)

        check = {'label': network['label'],
                 'gateway': network['gateway'],
                 'dhcp_server': network['gateway'],
                 'broadcast': network['broadcast'],
                 'mac': vif['address'],
                 'vif_uuid': vif['uuid'],
                 'rxtx_cap': flavor['rxtx_cap'],
                 'dns': [],
                 'ips': [{'ip': fixed_ip['address'],
                          'netmask': network['netmask'], 'enabled': '1'}],
                 'should_create_bridge': False,
                 'should_create_vlan': False,
                 'ip6s': [{'ip': global_ipv6,
                           'netmask': '64', 'enabled': '1'}],
                 'gateway6': network['gateway_v6'],
                 'dns': [network['dns1'], network['dns2']]}
        self.assertDictMatch(res[0][1], check)

    @attr(kind='small')
    def test_get_instance_nw_info_db_not_network_cidr_v6(self):
        """
        ip6s is set to none
        """
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        fixed_ip = dict(fixed_ips[0])
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([fixed_ip])
        vif = dict(vifs[0])
        network = dict(networks[0])
        network['cidr_v6'] = None
        vif['network'] = network
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([vif])
        db.instance_type_get(mox.IgnoreArg(),
                             mox.IgnoreArg()).AndReturn(flavor)
        self.mox.ReplayAll()

        res = self.network.get_instance_nw_info(self.context, 1, 1, HOST)
        self.assertEqual(1, len(res))
        self.assertEqual(None, res[0][1].get('ip6s'))

    @attr(kind='small')
    def test_get_instance_nw_info_db_not_network_gateway_v6(self):
        """
        gateway6 is set to none
        """
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        fixed_ip = dict(fixed_ips[0])
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([fixed_ip])
        vif = dict(vifs[0])
        network = dict(networks[0])
        network['gateway_v6'] = None
        vif['network'] = network
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([vif])
        db.instance_type_get(mox.IgnoreArg(),
                             mox.IgnoreArg()).AndReturn(flavor)
        self.mox.ReplayAll()

        res = self.network.get_instance_nw_info(self.context, 1, 1, HOST)
        self.assertEqual(1, len(res))
        self.assertEqual(None, res[0][1].get('gateway6'))

    @attr(kind='small')
    def test_get_instance_nw_info_db_not_network_dns1(self):
        """
        info['dns'] is not appended to network['dns1']
        """
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        fixed_ip = dict(fixed_ips[0])
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([fixed_ip])
        vif = dict(vifs[0])
        network = dict(networks[0])
        network['dns1'] = None
        vif['network'] = network
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([vif])
        db.instance_type_get(mox.IgnoreArg(),
                             mox.IgnoreArg()).AndReturn(flavor)
        self.mox.ReplayAll()

        res = self.network.get_instance_nw_info(self.context, 1, 1, HOST)
        self.assertEqual(1, len(res))
        self.assertEqual([network['dns2']], res[0][1].get('dns'))

    @attr(kind='small')
    def test_get_instance_nw_info_db_not_network_dns2(self):
        """
        info['dns'] is not appended to network['dns2']
        """
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        fixed_ip = dict(fixed_ips[0])
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([fixed_ip])
        vif = dict(vifs[0])
        network = dict(networks[0])
        network['dns2'] = None
        vif['network'] = network
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([vif])
        db.instance_type_get(mox.IgnoreArg(),
                             mox.IgnoreArg()).AndReturn(flavor)
        self.mox.ReplayAll()

        res = self.network.get_instance_nw_info(self.context, 1, 1, HOST)
        self.assertEqual(1, len(res))
        self.assertEqual([network['dns1']], res[0][1].get('dns'))

    @attr(kind='small')
    def test_get_instance_nw_info_param_get_dhcp_multi_host_and_not_host(self):
        """
        host is set to self.host
        """
        self._context = None
        self._network_id = None
        self._host = None

        def stub_fixed_ip_get_by_network_host(context, network_id, host):
            self._context = context
            self._network_id = network_id
            self._host = host
            return fixed_ips[0]

        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        self.stubs.Set(db, 'fixed_ip_get_by_network_host',
                       stub_fixed_ip_get_by_network_host)
        fixed_ip = dict(fixed_ips[0])
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([fixed_ip])
        vif = dict(vifs[0])
        network = dict(networks[0])
        network['multi_host'] = True
        vif['network'] = network
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([vif])
        db.instance_type_get(mox.IgnoreArg(),
                             mox.IgnoreArg()).AndReturn(flavor)
        self.mox.ReplayAll()

        res = self.network.get_instance_nw_info(self.context, 1, 1, None)
        self.assertEqual(1, len(res))
        self.assertTrue(self._context)
        self.assertEqual(network['id'], self._network_id)
        self.assertEqual(HOST, self._host)

    @attr(kind='small')
    def test_get_instance_nw_info_ex_get_dhcp_ip_fixed_ip_not_found(self):
        """
        db.fixed_ip_associate_pool is called
        when FixedIpNotFoundForNetworkHost is caught
        """
        dhcp_server = '10.0.0.1'
        self._context = None
        self._network_id = None
        self._instance_id = None
        self._host = None

        def stub_fixed_ip_associate_pool(
                        context, network_id, instance_id=None, host=None):
            self._context = context
            self._network_id = network_id
            self._instance_id = instance_id
            self._host = host
            return dhcp_server

        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_network_host')
        self.stubs.Set(db, 'fixed_ip_associate_pool',
                       stub_fixed_ip_associate_pool)
        fixed_ip = dict(fixed_ips[0])
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([fixed_ip])
        vif = dict(vifs[0])
        network = dict(networks[0])
        network['multi_host'] = True
        vif['network'] = network
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([vif])
        db.instance_type_get(mox.IgnoreArg(),
                             mox.IgnoreArg()).AndReturn(flavor)
        db.fixed_ip_get_by_network_host(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndRaise(exception.FixedIpNotFoundForNetworkHost)
        self.mox.ReplayAll()

        res = self.network.get_instance_nw_info(self.context, 1, 1, HOST)
        self.assertEqual(1, len(res))
        self.assertEqual(dhcp_server, res[0][1].get('dhcp_server'))
        self.assertTrue(self._context)
        self.assertEqual(network['id'], self._network_id)
        self.assertTrue(self._instance_id is None)
        self.assertEqual(HOST, self._host)

    @attr(kind='small')
    def test_get_instance_nw_info_ex_get_dhcp_ip(self):
        """
        All VirtualInterfaces are processed
        even when exception is raised in self._get_dhcp_ip()
        """
        self._count = 0

        def stub_get_dhcp_ip(caller, context, network_ref, host=None):
            self._count += 1
            raise exception.NoMoreFixedIps()

        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_network_host')
        self.stubs.Set(self.network, '_get_dhcp_ip', stub_get_dhcp_ip)
        fixed_ip = dict(fixed_ips[0])
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([fixed_ip])
        _vifs = list([vifs[0], vifs[1]])
        _vifs[0]['network']['multi_host'] = True
        _vifs[1]['network']['multi_host'] = True
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn(_vifs)
        db.instance_type_get(mox.IgnoreArg(),
                             mox.IgnoreArg()).AndReturn(flavor)
        self.mox.ReplayAll()

        self.assertRaises(exception.NetworkGetNwInfoException,
                          self.network.get_instance_nw_info,
                          self.context, 1, 1, HOST)
        self.assertEqual(2, self._count)

    @attr(kind='small')
    def test_add_virtual_interface(self):
        """
        VirtualInterfaceMacAddressException is not raised
        """
        self.mox.StubOutWithMock(db, 'virtual_interface_create')
        db.virtual_interface_create(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn(vifs[0])
        self.mox.ReplayAll()

        res = self.network.add_virtual_interface(self.context, 1, 1)
        self.assertEqual(vifs[0], res)

    @attr(kind='small')
    def test_add_virtual_interface_param_instance_does_not_exist(self):
        """
        InstanceNotFound is raised when instance does not exist
        """
#        raise SkipTest('Parameter check is not implemented yet')
        self.mox.StubOutWithMock(db, 'instance_get')
        db.instance_get(mox.IgnoreArg(),
                        mox.IgnoreArg()).AndRaise(exception.InstanceNotFound)
        self.mox.ReplayAll()

        instance_id = 99999  # not exist
        network_id = 1
        self.assertRaises(exception.InstanceNotFound,
                          self.network.add_virtual_interface,
                          self.context, instance_id, network_id)

    @attr(kind='small')
    def test_add_virtual_interface_param_network_does_not_exist(self):
        """
        NetworkNotFound is raised when network does not exist
        """
#        raise SkipTest('Parameter check is not implemented yet')
        self.mox.StubOutWithMock(db, 'network_get')
        db.network_get(mox.IgnoreArg(),
                       mox.IgnoreArg()).AndRaise(exception.NetworkNotFound)
        self.mox.ReplayAll()

        instance_id = 1
        network_id = 99999  # not exist
        self.assertRaises(exception.NetworkNotFound,
                          self.network.add_virtual_interface,
                          self.context, instance_id, network_id)

    @attr(kind='small')
    def test_add_virtual_interface_ex_virtual_interface_create(self):
        """
        VirtualInterfaceMacAddressException is raised
        """
        self.mox.StubOutWithMock(db, 'virtual_interface_create')
        self.mox.StubOutWithMock(db, 'virtual_interface_delete_by_instance')
        db.virtual_interface_create(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndRaise(exception.VirtualInterfaceCreateException)
        db.virtual_interface_create(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndRaise(exception.VirtualInterfaceCreateException)
        db.virtual_interface_create(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndRaise(exception.VirtualInterfaceCreateException)
        db.virtual_interface_create(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndRaise(exception.VirtualInterfaceCreateException)
        db.virtual_interface_create(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndRaise(exception.VirtualInterfaceCreateException)
        db.virtual_interface_delete_by_instance(
                                        mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        self.assertRaises(exception.VirtualInterfaceMacAddressException,
                          self.network.add_virtual_interface,
                          self.context, 1, 1)

    @attr(kind='small')
    def test_add_virtual_interface_cfg_mac_address_attempts_is_zero(self):
        """
        VirtualInterfaceMacAddressException is raised
        when FLAGS.create_unique_mac_address_attempts is zero
        """
        self.flags(create_unique_mac_address_attempts=0)

        self.mox.StubOutWithMock(db, 'virtual_interface_delete_by_instance')
        db.virtual_interface_delete_by_instance(
                                        mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        self.assertRaises(exception.VirtualInterfaceMacAddressException,
                          self.network.add_virtual_interface,
                          self.context, 1, 1)

    @attr(kind='small')
    def test_allocate_fixed_ip_param_instance_does_not_exist(self):
        """
        InstanceNotFound is raised when instance does not exist
        """
#        raise SkipTest('Parameter check is not implemented yet')
        self.mox.StubOutWithMock(db, 'instance_get')
        db.instance_get(mox.IgnoreArg(),
                        mox.IgnoreArg()).AndRaise(exception.InstanceNotFound)
        self.mox.ReplayAll()

        instance_id = 99999  # not exist
        network = dict(networks[0])
        network['cidr'] = None
        kwargs = {}
        self.assertRaises(exception.InstanceNotFound,
                          self.network.allocate_fixed_ip,
                          self.context, instance_id, network, **kwargs)

    @attr(kind='small')
    def test_allocate_fixed_ip_param_network_cidr_is_none(self):
        """
        none is returned
        """
        self.mox.StubOutWithMock(db, 'network_update')
        db.network_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        network = dict(networks[0])
        network['cidr'] = None
        kwargs = {}
        res = self.network.allocate_fixed_ip(
                        self.context, 1, network, **kwargs)
        self.assertEqual(None, res)

    @attr(kind='small')
    def test_allocate_fixed_ip_param_address_is_not_none(self):
        """
        db.fixed_ip_associate is called
        """
        fixed_ip_address = '192.168.0.101'
        self._context = None
        self._address = None
        self._instance_id = None
        self._network_id = None
        self._reserved = None

        def stub_fixed_ip_associate(
                        context, address, instance_id,
                        network_id=None, reserved=False):
            self._context = context
            self._address = address
            self._instance_id = instance_id
            self._network_id = network_id
            self._reserved = reserved
            return fixed_ip_address

        self.stubs.Set(db, 'fixed_ip_associate', stub_fixed_ip_associate)
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db, 'network_update')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        db.network_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['address'] = '10.0.0.0'
        res = self.network.allocate_fixed_ip(
                        self.context, 1, networks[0], **kwargs)
        self.assertEqual(fixed_ip_address, res)
        self.assertTrue(self._context)
        self.assertEqual(kwargs['address'], self._address)
        self.assertEqual(1, self._instance_id)
        self.assertEqual(networks[0]['id'], self._network_id)
        self.assertEqual(False, self._reserved)

    @attr(kind='small')
    def test_allocate_fixed_ip_param_address_is_none(self):
        """
        db.fixed_ip_associate_pool is called
        """
        self.mox.StubOutWithMock(db, 'fixed_ip_associate_pool')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db, 'network_update')
        fixed_ip_address = '192.168.0.101'
        db.fixed_ip_associate_pool(mox.IgnoreArg(),
                                   mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn(fixed_ip_address)
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        db.network_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        kwargs = {}
        res = self.network.allocate_fixed_ip(
                        self.context, 1, networks[0], **kwargs)
        self.assertEqual(fixed_ip_address, res)

    @attr(kind='small')
    def test_deallocate_fixed_ip_cfg_not_force_dhcp_release(self):
        """
        driver.release_dhcp is not called
        """
        self.flags(force_dhcp_release=False)

        self._is_called = False

        def stub_release_dhcp(dev, address, mac_address):
            self._is_called = True

        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_address')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(db, 'fixed_ip_disassociate')
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        db.fixed_ip_get_by_address(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'instance': {'id': 0}})
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.fixed_ip_disassociate(mox.IgnoreArg(), mox.IgnoreArg())
        self.stubs.Set(self.network.driver, 'release_dhcp', stub_release_dhcp)
        self.mox.ReplayAll()

        kwargs = {}
        self.network.deallocate_fixed_ip(
                        self.context, '192.168.0.100', **kwargs)
        self.assertFalse(self._is_called)

    @attr(kind='small')
    def test_deallocate_fixed_ip_cfg_force_dhcp_release(self):
        """
        driver.release_dhcp is called
        """
        self.flags(force_dhcp_release=True)

        self._dev = None
        self._address = None
        self._mac_address = None

        def stub_release_dhcp(dev, address, mac_address):
            self._dev = dev
            self._address = address
            self._mac_address = mac_address

        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_address')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(self.network.driver, 'get_dev')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.stubs.Set(self.network.driver, 'release_dhcp', stub_release_dhcp)
        self.mox.StubOutWithMock(db, 'fixed_ip_disassociate')
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        db.fixed_ip_get_by_address(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'instance': {'id': 0},
                                   'network': networks[0]})
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        dev = networks[0]['bridge']
        self.network.driver.get_dev(mox.IgnoreArg()).AndReturn(dev)
        vif = vifs[0]
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn(vif)
        db.fixed_ip_disassociate(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        kwargs = {}
        self.network.deallocate_fixed_ip(
                        self.context, '192.168.0.100', **kwargs)
        self.assertEqual(dev, self._dev)
        self.assertEqual('192.168.0.100', self._address)
        self.assertEqual(vif['address'], self._mac_address)

    @attr(kind='small')
    def test_deallocate_fixed_ip_ex_driver_get_dev(self):
        """
        ProcessExecutionError is raised
        """
        self.flags(force_dhcp_release=True)

        def stub_get_dev(network):
            raise exception.ProcessExecutionError()

        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_address')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.stubs.Set(self.network.driver, 'get_dev', stub_get_dev)
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        db.fixed_ip_get_by_address(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'instance': {'id': 0},
                                   'network': networks[0]})
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        self.mox.ReplayAll()

        kwargs = {}
        self.assertRaises(exception.ProcessExecutionError,
                          self.network.deallocate_fixed_ip,
                          self.context, '192.168.0.100', **kwargs)

    @attr(kind='small')
    def test_deallocate_fixed_ip_ex_driver_release_dhcp(self):
        """
        ProcessExecutionError is raised
        """
        self.flags(force_dhcp_release=True)

        def stub_release_dhcp(dev, address, mac_address):
            raise exception.ProcessExecutionError()

        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_address')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.stubs.Set(self.network.driver, 'release_dhcp', stub_release_dhcp)
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        db.fixed_ip_get_by_address(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'instance': {'id': 0},
                                   'network': networks[0]})
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        vif = vifs[0]
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn(vif)
        self.mox.ReplayAll()

        kwargs = {}
        self.assertRaises(exception.ProcessExecutionError,
                          self.network.deallocate_fixed_ip,
                          self.context, '192.168.0.100', **kwargs)

    @attr(kind='small')
    def test_lease_fixed_ip(self):
        """
        db.fixed_ip_update is called
        """
        self._context = None
        self._address = None
        self._leased = None
        self._updated_at = None

        def stub_fixed_ip_update(context, address, values):
            self._context = context
            self._address = address
            self._leased = values['leased']
            self._updated_at = values['updated_at']

        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_address')
        self.mox.StubOutWithMock(utils, 'utcnow')
        self.stubs.Set(db, 'fixed_ip_update', stub_fixed_ip_update)
        fixed_ip = dict(fixed_ips[0])
        fixed_ip['instance'] = {'id': 0}
        fixed_ip['allocated'] = True
        db.fixed_ip_get_by_address(mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn(fixed_ip)
        now = datetime.datetime.now()
        utils.utcnow().AndReturn(now)
        self.mox.ReplayAll()

        self.network.lease_fixed_ip(self.context, '192.168.0.100')
        self.assertTrue(self._context)
        self.assertEqual(fixed_ip['address'], self._address)
        self.assertEqual(True, self._leased)
        self.assertEqual(now, self._updated_at)

    @attr(kind='small')
    def test_lease_fixed_ip_db_fixed_ip_instance_not_found(self):
        """
        NotFound is raised
        """
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_address')
        fixed_ip = dict(fixed_ips[0])
        fixed_ip['instance'] = None
        db.fixed_ip_get_by_address(mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn(fixed_ip)
        self.mox.ReplayAll()

        self.assertRaises(exception.NotFound,
                          self.network.lease_fixed_ip,
                          self.context, '192.168.0.100')

    @attr(kind='small')
    def test_lease_fixed_ip_db_fixed_ip_not_allocated(self):
        """
        LOG.warn is called
        """
        self._msg = None
        self._args = None
        self._kwargs = None

        def stub_warn(msg, *args, **kwargs):
            self._msg = msg
            self._args = args
            self._kwargs = kwargs

        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_address')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        fixed_ip = dict(fixed_ips[0])
        fixed_ip['instance'] = {'id': 0}
        db.fixed_ip_get_by_address(mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn(fixed_ip)
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.stubs.Set(logging.getLogger("nova.network.manager"),
                       'warn', stub_warn)
        self.mox.ReplayAll()

        self.network.lease_fixed_ip(self.context, '192.168.0.100')
        self.assertEqual(_('IP |%s| leased that isn\'t allocated'), self._msg)
        self.assertEqual('192.168.0.100', self._args[0])
        self.assertTrue(self._kwargs['context'] is not None)

    @attr(kind='small')
    def test_release_fixed_ip(self):
        """
        db.fixed_ip_update is called
        """
        self._context = None
        self._address = None
        self._leased = None

        def stub_fixed_ip_update(context, address, values):
            self._context = context
            self._address = address
            self._leased = values['leased']

        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_address')
        self.stubs.Set(db, 'fixed_ip_update', stub_fixed_ip_update)
        fixed_ip = dict(fixed_ips[0])
        fixed_ip['instance'] = {'id': 0}
        fixed_ip['leased'] = True
        fixed_ip['allocated'] = True
        db.fixed_ip_get_by_address(mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn(fixed_ip)
        self.mox.ReplayAll()

        self.network.release_fixed_ip(self.context, '192.168.0.100')
        self.assertTrue(self._context)
        self.assertEqual(fixed_ip['address'], self._address)
        self.assertEqual(False, self._leased)

    @attr(kind='small')
    def test_release_fixed_ip_db_fixed_ip_instance_not_found(self):
        """
        NotFound is raised
        """
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_address')
        fixed_ip = dict(fixed_ips[0])
        fixed_ip['instance'] = None
        db.fixed_ip_get_by_address(mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn(fixed_ip)
        self.mox.ReplayAll()

        self.assertRaises(exception.NotFound,
                          self.network.release_fixed_ip,
                          self.context, '192.168.0.100')

    @attr(kind='small')
    def test_release_fixed_ip_db_fixed_ip_not_leased(self):
        """
        LOG.warn is called
        """
        self._msg = None
        self._args = None
        self._kwargs = None

        def stub_warn(msg, *args, **kwargs):
            self._msg = msg
            self._args = args
            self._kwargs = kwargs

        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_address')
        self.stubs.Set(logging.getLogger("nova.network.manager"),
                       'warn', stub_warn)
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        fixed_ip = dict(fixed_ips[0])
        fixed_ip['instance'] = {'id': 0}
        fixed_ip['leased'] = False
        fixed_ip['allocated'] = True
        db.fixed_ip_get_by_address(mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn(fixed_ip)
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        self.network.release_fixed_ip(self.context, '192.168.0.100')
        self.assertEqual(_('IP %s released that was not leased'), self._msg)
        self.assertEqual('192.168.0.100', self._args[0])
        self.assertTrue(self._kwargs['context'] is not None)

    @attr(kind='small')
    def test_release_fixed_ip_db_fixed_ip_not_allocated(self):
        """
        db.fixed_ip_disassociate is called
        """
        self.flags(update_dhcp_on_disassociate=False)

        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_address')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db, 'fixed_ip_disassociate')
        fixed_ip = dict(fixed_ips[0])
        fixed_ip['instance'] = {'id': 0}
        fixed_ip['leased'] = True
        fixed_ip['allocated'] = False
        db.fixed_ip_get_by_address(mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn(fixed_ip)
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        db.fixed_ip_disassociate(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        self.network.release_fixed_ip(self.context, '192.168.0.100')

    @attr(kind='small')
    def test_release_fixed_ip_cfg_update_dhcp_on_disassociate(self):
        """
        db.fixed_ip_get_network is called
        """
        self.flags(update_dhcp_on_disassociate=True)

        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_address')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db, 'fixed_ip_disassociate')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_network')
        self.mox.StubOutWithMock(db, 'network_update')
        fixed_ip = dict(fixed_ips[0])
        fixed_ip['instance'] = {'id': 0}
        fixed_ip['leased'] = True
        fixed_ip['allocated'] = False
        db.fixed_ip_get_by_address(mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn(fixed_ip)
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        db.fixed_ip_disassociate(mox.IgnoreArg(), mox.IgnoreArg())
        db.fixed_ip_get_network(mox.IgnoreArg(),
                                mox.IgnoreArg()).AndReturn(networks[0])
        db.network_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        self.network.release_fixed_ip(self.context, '192.168.0.100')

    @attr(kind='small')
    def test_create_networks_db_network_already_exists(self):
        """
        following process continues even when network creation failed
        """
        def stub_fixed_ip_create(context, values):
            pass

        self._network_create_count = 0

        def stub_network_create_safe(context, values):
            self._network_create_count += 1
            if self._network_create_count == 1:
                return None
            if self._network_create_count == 2:
                return networks[0]

        self.mox.StubOutWithMock(db, 'network_get_all')
        self.mox.StubOutWithMock(db, 'network_get')
        self.stubs.Set(db, 'network_create_safe', stub_network_create_safe)
        self.stubs.Set(db, 'fixed_ip_create', stub_fixed_ip_create)
        db.network_get_all(mox.IgnoreArg()).AndReturn([])
        db.network_get(mox.IgnoreArg(),
                       mox.IgnoreArg()).AndReturn(networks[0])
        self.mox.ReplayAll()

        cidr = '192.168.0.0/16'
        args = [None, 'fake', cidr, False, 2, 256, None, None, None, None]
        res = self.network.create_networks(*args)
        self.assertEqual([networks[0]], res)
        self.assertEqual(2, self._network_create_count)

    @attr(kind='small')
    def test_create_networks_ex_db_fixed_ip_create(self):
        """
        NetworkCreateException is raised
        when DBError occurred in db.fixed_ip_create()
        """
        self._fixed_ip_create_count = 0

        def stub_fixed_ip_create(context, values):
            self._fixed_ip_create_count += 1
            if self._fixed_ip_create_count == 1:
                raise exception.DBError('DBError occurred')

        self.mox.StubOutWithMock(db, 'network_get_all')
        self.mox.StubOutWithMock(db, 'network_create_safe')
        self.mox.StubOutWithMock(db, 'network_get')
        self.stubs.Set(db, 'fixed_ip_create', stub_fixed_ip_create)
        db.network_get_all(mox.IgnoreArg()).AndReturn([])
        db.network_create_safe(mox.IgnoreArg(),
                               mox.IgnoreArg()).AndReturn(networks[0])
        db.network_get(mox.IgnoreArg(),
                       mox.IgnoreArg()).AndReturn(networks[0])
        self.mox.ReplayAll()

        cidr = '192.168.0.0/24'
        args = [None, 'fake', cidr, False, 1, 256, None, None, None, None]
        self.assertRaises(exception.NetworkCreateException,
                          self.network.create_networks,
                          *args)
        self.assertEqual(256, self._fixed_ip_create_count)

    @attr(kind='small')
    def test_delete_network_db_network_is_disassociated(self):
        """
        db.network_delete_safe is called
        """
        self._context = None
        self._network_id = None

        def stub_network_delete_safe(context, network_id):
            self._context = context
            self._network_id = network_id

        self.mox.StubOutWithMock(db, 'network_get_by_cidr')
        network = FakeModel(**networks[0])
        network.project_id = None
        db.network_get_by_cidr(mox.IgnoreArg(),
                               mox.IgnoreArg()).AndReturn(network)
        self.stubs.Set(db, 'network_delete_safe', stub_network_delete_safe)
        self.mox.ReplayAll()

        self.network.delete_network(self.context, '10.0.0.0/29', True)
        self.assertTrue(self._context)
        self.assertEqual(network.id, self._network_id)

    @attr(kind='small')
    def test_delete_network_db_network_is_associated(self):
        """
        ValueError is raised
        """
        self.mox.StubOutWithMock(db, 'network_get_by_cidr')
        network = FakeModel(**networks[0])
        db.network_get_by_cidr(mox.IgnoreArg(),
                               mox.IgnoreArg()).AndReturn(network)
        self.mox.ReplayAll()

        self.assertRaises(ValueError,
                          self.network.delete_network,
                          self.context, '10.0.0.0/29', True)

    @attr(kind='small')
    def test_allocate_for_instance_param_requested_networks_is_none(self):
        """
        address is not set
        """
        self._context = None
        self._instance_id = None
        self._network = None
        self._kwargs = None

        def stub_allocate_fixed_ip(context, instance_id, network, **kwargs):
            self._context = context
            self._instance_id = instance_id
            self._network = network
            self._kwargs = kwargs

        self.mox.StubOutWithMock(db, 'network_get_all')
        self.mox.StubOutWithMock(db, 'virtual_interface_create')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        network = networks[0]
        db.network_get_all(mox.IgnoreArg()).AndReturn([network])
        db.virtual_interface_create(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn(vifs[0])
        self.stubs.Set(self.network, 'allocate_fixed_ip',
                       stub_allocate_fixed_ip)
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([])
        db.instance_type_get(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        kwargs['host'] = HOST
        kwargs['project_id'] = 'fake_project'
        kwargs['instance_type_id'] = 1
        kwargs['requested_networks'] = None
        kwargs['vpn'] = False
        res = self.network.allocate_for_instance(self.context, **kwargs)
        self.assertEqual([], res)
        self.assertTrue(self._context)
        self.assertEqual(kwargs['instance_id'], self._instance_id)
        self.assertEqual(network, self._network)
        self.assertTrue(self._kwargs['address'] is None)

    @attr(kind='small')
    def test_allocate_for_instance_param_network_uuid_equal_to_uuid(self):
        """
        address is set to fixed_ip
        """
        self._context = None
        self._instance_id = None
        self._network = None
        self._kwargs = None

        def stub_allocate_fixed_ip(context, instance_id, network, **kwargs):
            self._context = context
            self._instance_id = instance_id
            self._network = network
            self._kwargs = kwargs

        self.mox.StubOutWithMock(db, 'network_get_all_by_uuids')
        self.mox.StubOutWithMock(db, 'virtual_interface_create')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        network = networks[0]
        db.network_get_all_by_uuids(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([network])
        db.virtual_interface_create(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn(vifs[0])
        self.stubs.Set(self.network, 'allocate_fixed_ip',
                       stub_allocate_fixed_ip)
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([])
        db.instance_type_get(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        kwargs['host'] = HOST
        kwargs['project_id'] = 'fake_project'
        kwargs['instance_type_id'] = 1
        kwargs['requested_networks'] = [
                        ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
                         '192.168.0.100')]
        kwargs['vpn'] = False
        res = self.network.allocate_for_instance(self.context, **kwargs)
        self.assertEqual([], res)
        self.assertTrue(self._context)
        self.assertEqual(kwargs['instance_id'], self._instance_id)
        self.assertEqual(network, self._network)
        self.assertEqual(kwargs['requested_networks'][0][1],
                         self._kwargs['address'])

    @attr(kind='small')
    def test_allocate_for_instance_param_network_uuid_not_equal_to_uuid(self):
        """
        address is not set
        """
        self._context = None
        self._instance_id = None
        self._network = None
        self._kwargs = None

        def stub_allocate_fixed_ip(context, instance_id, network, **kwargs):
            self._context = context
            self._instance_id = instance_id
            self._network = network
            self._kwargs = kwargs

        self.mox.StubOutWithMock(db, 'network_get_all_by_uuids')
        self.mox.StubOutWithMock(db, 'virtual_interface_create')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        network = networks[0]
        db.network_get_all_by_uuids(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([network])
        db.virtual_interface_create(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn(vifs[0])
        self.stubs.Set(self.network, 'allocate_fixed_ip',
                       stub_allocate_fixed_ip)
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([])
        db.instance_type_get(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        kwargs['host'] = HOST
        kwargs['project_id'] = 'fake_project'
        kwargs['instance_type_id'] = 1
        kwargs['requested_networks'] = [
                        ('cccccccc-cccc-cccc-cccc-cccccccccccc',
                         '192.168.0.100')]
        kwargs['vpn'] = False
        res = self.network.allocate_for_instance(self.context, **kwargs)
        self.assertEqual([], res)
        self.assertTrue(self._context)
        self.assertEqual(kwargs['instance_id'], self._instance_id)
        self.assertEqual(network, self._network)
        self.assertTrue(self._kwargs['address'] is None)

    @attr(kind='small')
    def test_deallocate_fixed_ip(self):
        """
        db.fixed_ip_disassociate is called
        """
        self._context = None
        self._address = None

        def stub_fixed_ip_disassociate(context, address):
            self._context = context
            self._address = address

        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_address')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.stubs.Set(db, 'fixed_ip_disassociate', stub_fixed_ip_disassociate)
        db.fixed_ip_update(mox.IgnoreArg(),
                           mox.IgnoreArg(),
                           mox.IgnoreArg())
        fixed_ip = dict(fixed_ips[0])
        fixed_ip['instance'] = {'id': 0}
        db.fixed_ip_get_by_address(mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn(fixed_ip)
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        self.mox.ReplayAll()

        address = '192.168.0.100'
        kwargs = {}
        self.network.deallocate_fixed_ip(self.context, address, **kwargs)
        self.assertTrue(self._context)
        self.assertEqual(address, self._address)


class VlanNetworkTestCase(test.TestCase):
    def setUp(self):
        super(VlanNetworkTestCase, self).setUp()
        self.network = network_manager.VlanManager(host=HOST)
        self.network.db = db
        self.context = context.RequestContext('testuser', 'testproject',
                                              is_admin=False)

    @attr(kind='small')
    def test_vpn_allocate_fixed_ip(self):
        self.mox.StubOutWithMock(db, 'fixed_ip_associate')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db,
                              'virtual_interface_get_by_instance_and_network')

        db.fixed_ip_associate(mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              reserved=True).AndReturn('192.168.0.1')
        db.fixed_ip_update(mox.IgnoreArg(),
                           mox.IgnoreArg(),
                           mox.IgnoreArg())
        db.virtual_interface_get_by_instance_and_network(mox.IgnoreArg(),
                mox.IgnoreArg(), mox.IgnoreArg()).AndReturn({'id': 0})
        self.mox.ReplayAll()

        network = dict(networks[0])
        network['vpn_private_address'] = '192.168.0.2'
        res = self.network.allocate_fixed_ip(None, 0, network, vpn=True)
        self.assertEqual(network['vpn_private_address'], res)

    @attr(kind='small')
    def test_allocate_fixed_ip(self):
        self.mox.StubOutWithMock(db, 'fixed_ip_associate_pool')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db,
                              'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'instance_get')

        db.instance_get(mox.IgnoreArg(),
                        mox.IgnoreArg()).AndReturn({'security_groups':
                                                             [{'id': 0}]})
        db.fixed_ip_associate_pool(mox.IgnoreArg(),
                                   mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn('192.168.0.1')
        db.fixed_ip_update(mox.IgnoreArg(),
                           mox.IgnoreArg(),
                           mox.IgnoreArg())
        db.virtual_interface_get_by_instance_and_network(mox.IgnoreArg(),
                mox.IgnoreArg(), mox.IgnoreArg()).AndReturn({'id': 0})
        self.mox.ReplayAll()

        network = dict(networks[0])
        network['vpn_private_address'] = '192.168.0.2'
        res = self.network.allocate_fixed_ip(self.context, 0, network)
        self.assertEqual('192.168.0.1', res)

    @attr(kind='small')
    def test_create_networks(self):
        """
        Test for nova.network.manager.VlanManager.create_networks.
        """
        self._count = 0

        def stub_network_create_safe(context, values):
            self._count += 1
            return networks[0]

        self.mox.StubOutWithMock(db, 'network_get_all')
        self.stubs.Set(db, 'network_create_safe', stub_network_create_safe)
        self.mox.StubOutWithMock(db, 'network_get')
        db.network_get_all(mox.IgnoreArg()).AndReturn(networks)
        db.network_get(mox.IgnoreArg(),
                       mox.IgnoreArg()).AndReturn(networks[0])
        db.network_get(mox.IgnoreArg(),
                       mox.IgnoreArg()).AndReturn(networks[1])
        self.mox.ReplayAll()

        self.network.create_networks(
                        self.context,
                        label='test',
                        cidr=flags.FLAGS.fixed_range,
                        multi_host=flags.FLAGS.multi_host,
                        num_networks=flags.FLAGS.num_networks,
                        network_size=flags.FLAGS.network_size,
                        cidr_v6=flags.FLAGS.fixed_range_v6,
                        gateway_v6=flags.FLAGS.gateway_v6,
                        bridge=flags.FLAGS.flat_network_bridge,
                        bridge_interface=flags.FLAGS.vlan_interface,
                        vpn_start=flags.FLAGS.vpn_start,
                        vlan_start=flags.FLAGS.vlan_start,
                        dns1=flags.FLAGS.flat_network_dns)
        self.assertTrue(flags.FLAGS.network_size, self._count)

    def test_create_networks_too_big(self):
        self.assertRaises(ValueError, self.network.create_networks, None,
                          num_networks=4094, vlan_start=1)

    def test_create_networks_too_many(self):
        self.assertRaises(ValueError, self.network.create_networks, None,
                          num_networks=100, vlan_start=1,
                          cidr='192.168.0.1/24', network_size=100)

    def test_validate_networks(self):
        self.mox.StubOutWithMock(db, 'network_get_all_by_uuids')
        self.mox.StubOutWithMock(db, "fixed_ip_get_by_address")

        requested_networks = [("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                               "192.168.1.100")]
        db.network_get_all_by_uuids(mox.IgnoreArg(),
                                mox.IgnoreArg(),
                                mox.IgnoreArg()).AndReturn(networks)

        fixed_ips[1]['network'] = FakeModel(**networks[1])
        fixed_ips[1]['instance'] = None
        db.fixed_ip_get_by_address(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn(fixed_ips[1])

        self.mox.ReplayAll()
        self.network.validate_networks(self.context, requested_networks)

    def test_validate_networks_none_requested_networks(self):
        self.network.validate_networks(self.context, None)

    def test_validate_networks_empty_requested_networks(self):
        requested_networks = []
        self.mox.ReplayAll()

        self.network.validate_networks(self.context, requested_networks)

    def test_validate_networks_invalid_fixed_ip(self):
        self.mox.StubOutWithMock(db, 'network_get_all_by_uuids')
        requested_networks = [(1, "192.168.0.100.1")]
        db.network_get_all_by_uuids(mox.IgnoreArg(),
                                mox.IgnoreArg(),
                                mox.IgnoreArg()).AndReturn(networks)
        self.mox.ReplayAll()

        self.assertRaises(exception.FixedIpInvalid,
                          self.network.validate_networks, self.context,
                          requested_networks)

    def test_validate_networks_empty_fixed_ip(self):
        self.mox.StubOutWithMock(db, 'network_get_all_by_uuids')

        requested_networks = [(1, "")]
        db.network_get_all_by_uuids(mox.IgnoreArg(),
                                mox.IgnoreArg(),
                                mox.IgnoreArg()).AndReturn(networks)
        self.mox.ReplayAll()

        self.assertRaises(exception.FixedIpInvalid,
                          self.network.validate_networks,
                          self.context, requested_networks)

    def test_validate_networks_none_fixed_ip(self):
        self.mox.StubOutWithMock(db, 'network_get_all_by_uuids')

        requested_networks = [(1, None)]
        db.network_get_all_by_uuids(mox.IgnoreArg(),
                                mox.IgnoreArg(),
                                mox.IgnoreArg()).AndReturn(networks)
        self.mox.ReplayAll()
        self.network.validate_networks(self.context, requested_networks)

    def test_cant_associate_associated_floating_ip(self):
        ctxt = context.RequestContext('testuser', 'testproject',
                                      is_admin=False)

        def fake_floating_ip_get_by_address(context, address):
            return {'address': '10.10.10.10',
                    'fixed_ip': {'address': '10.0.0.1'}}
        self.stubs.Set(self.network.db, 'floating_ip_get_by_address',
                                fake_floating_ip_get_by_address)

        self.assertRaises(exception.FloatingIpAlreadyInUse,
                          self.network.associate_floating_ip,
                          ctxt,
                          mox.IgnoreArg(),
                          mox.IgnoreArg())

    @attr(kind='small')
    def test_add_fixed_ip_instance_without_vpn_requested_networks(self):
        """
        driver.initialize_gateway_device is called
        """
        self._is_called = False

        def stub_initialize_gateway_device(dev, network_ref):
            self._is_called = True

        self.mox.StubOutWithMock(db, 'network_get')
        self.mox.StubOutWithMock(db, 'fixed_ip_associate_pool')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(db,
                              'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.stubs.Set(self.network.driver, 'initialize_gateway_device',
                       stub_initialize_gateway_device)

        db.fixed_ip_update(mox.IgnoreArg(),
                           mox.IgnoreArg(),
                           mox.IgnoreArg())
        db.virtual_interface_get_by_instance_and_network(mox.IgnoreArg(),
                mox.IgnoreArg(), mox.IgnoreArg()).AndReturn({'id': 0})

        db.instance_get(mox.IgnoreArg(),
                        mox.IgnoreArg()).AndReturn({'security_groups':
                                                             [{'id': 0}]})
        db.fixed_ip_associate_pool(mox.IgnoreArg(),
                                   mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.network_get(mox.IgnoreArg(),
                       mox.IgnoreArg()).AndReturn(networks[0])
        self.mox.ReplayAll()
        self.network.add_fixed_ip_to_instance(self.context, 1, HOST,
                                              networks[0]['id'])
        self.assertTrue(self._is_called)

    def test_ip_association_and_allocation_of_other_project(self):
        """Makes sure that we cannot deallocaate or disassociate
        a public ip of other project"""

        context1 = context.RequestContext('user', 'project1')
        context2 = context.RequestContext('user', 'project2')

        address = '1.2.3.4'
        float_addr = db.floating_ip_create(context1.elevated(),
                {'address': address,
                 'project_id': context1.project_id})

        instance = db.instance_create(context1,
                {'project_id': 'project1'})

        fix_addr = db.fixed_ip_associate_pool(context1.elevated(),
                1, instance['id'])

        # Associate the IP with non-admin user context
        self.assertRaises(exception.NotAuthorized,
                          self.network.associate_floating_ip,
                          context2,
                          float_addr,
                          fix_addr)

        # Deallocate address from other project
        self.assertRaises(exception.NotAuthorized,
                          self.network.deallocate_floating_ip,
                          context2,
                          float_addr)

        # Now Associates the address to the actual project
        self.network.associate_floating_ip(context1, float_addr, fix_addr)

        # Now try dis-associating from other project
        self.assertRaises(exception.NotAuthorized,
                          self.network.disassociate_floating_ip,
                          context2,
                          float_addr)

        # Clean up the ip addresses
        self.network.deallocate_floating_ip(context1, float_addr)
        self.network.deallocate_fixed_ip(context1, fix_addr)
        db.floating_ip_destroy(context1.elevated(), float_addr)
        db.fixed_ip_disassociate(context1.elevated(), fix_addr)

    @attr(kind='small')
    def test_allocate_for_instance_param_requested_networks_is_not_none(self):
        """
        address is set to the value of requested_networks's fixed_ip
        """
        self._function = None
        self._context = None
        self._topic = None
        self._method = None
        self._args = None

        def stub_spawn_n(caller, function, *args, **kwargs):
            self._function = function
            self._context = args[0]
            self._topic = args[1]
            self._method = args[2]['method']
            self._args = args[2]['args']

        self.mox.StubOutWithMock(db, 'network_get_all_by_uuids')
        self.mox.StubOutWithMock(db, 'virtual_interface_create')
        self.mox.StubOutWithMock(db, 'queue_get_for')
        self.stubs.Set(greenpool.GreenPool, 'spawn_n', stub_spawn_n)
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        network = dict(networks[0])
        network['host'] = 'dummyhost'
        db.network_get_all_by_uuids(mox.IgnoreArg(),
                                    mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([network])
        db.virtual_interface_create(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn(vifs[0])
        db.queue_get_for(mox.IgnoreArg(),
                         mox.IgnoreArg(),
                         mox.IgnoreArg()).AndReturn('network')
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([])
        db.instance_type_get(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        kwargs['host'] = HOST
        kwargs['project_id'] = 'fake_project'
        kwargs['instance_type_id'] = 1
        kwargs['requested_networks'] = [
                        ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
                         '192.168.0.100')]
        kwargs['vpn'] = False
        res = self.network.allocate_for_instance(self.context, **kwargs)
        self.assertEqual([], res)
        self.assertEqual(rpc.call, self._function)
        self.assertTrue(self._context)
        self.assertEqual('network', self._topic)
        self.assertEqual('_rpc_allocate_fixed_ip', self._method)
        self.assertEqual(kwargs['instance_id'], self._args['instance_id'])
        self.assertEqual(network['id'], self._args['network_id'])
        self.assertEqual(kwargs['requested_networks'][0][1],
                         self._args['address'])
        self.assertEqual(kwargs['vpn'], self._args['vpn'])

    @attr(kind='small')
    def test_allocate_for_instance_param_network_multi_host_is_true(self):
        """
        host is set to network['host']
        """
        self._context = None
        self._topic = None
        self._physical_node_id = None

        def stub_queue_get_for(context, topic, physical_node_id):
            self._context = context
            self._topic = topic
            self._physical_node_id = physical_node_id
            return 'network'

        self.mox.StubOutWithMock(db, 'project_get_networks')
        self.mox.StubOutWithMock(db, 'virtual_interface_create')
        self.stubs.Set(db, 'queue_get_for', stub_queue_get_for)
        self.mox.StubOutWithMock(greenpool.GreenPool, 'spawn_n')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        network = dict(networks[0])
        network['multi_host'] = True
        db.project_get_networks(mox.IgnoreArg(),
                                mox.IgnoreArg()).AndReturn([network])
        db.virtual_interface_create(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn(vifs[0])
        greenpool.GreenPool().spawn_n(mox.IgnoreArg(), mox.IgnoreArg(),
                                      mox.IgnoreArg(), mox.IgnoreArg())
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([])
        db.instance_type_get(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        kwargs['host'] = 'dummyhost'
        kwargs['project_id'] = 'fake_project'
        kwargs['instance_type_id'] = 1
        kwargs['requested_networks'] = None
        kwargs['vpn'] = False
        res = self.network.allocate_for_instance(self.context, **kwargs)
        self.assertEqual([], res)
        self.assertTrue(self._context)
        self.assertEqual(flags.FLAGS.network_topic, self._topic)
        self.assertEqual(kwargs['host'], self._physical_node_id)

    @attr(kind='small')
    def test_allocate_for_instance_param_host_is_none(self):
        """
        rpc.call is called
        """
        self._context = None
        self._topic = None
        self._method = None
        self._args = None

        def stub_call(context, topic, msg):
            self._context = context
            self._topic = topic
            self._method = msg['method']
            self._args = msg['args']
            return HOST

        self.mox.StubOutWithMock(db, 'project_get_networks')
        self.mox.StubOutWithMock(db, 'virtual_interface_create')
        self.stubs.Set(rpc, 'call', stub_call)
        self.mox.StubOutWithMock(db, 'fixed_ip_associate_pool')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_network_host')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        network = dict(networks[0])
        network['multi_host'] = True
        db.project_get_networks(mox.IgnoreArg(),
                                mox.IgnoreArg()).AndReturn([network])
        db.virtual_interface_create(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn(vifs[0])
        db.fixed_ip_associate_pool(mox.IgnoreArg(),
                                   mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        db.fixed_ip_get_by_network_host(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn(fixed_ips[0])
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([])
        db.instance_type_get(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        kwargs['host'] = None
        kwargs['project_id'] = 'fake_project'
        kwargs['instance_type_id'] = 1
        kwargs['requested_networks'] = None
        kwargs['vpn'] = False
        res = self.network.allocate_for_instance(self.context, **kwargs)
        self.assertEqual([], res)
        self.assertTrue(self._context)
        self.assertEqual(flags.FLAGS.network_topic, self._topic)
        self.assertEqual('set_network_host', self._method)
        self.assertEqual({'network_ref': network}, self._args)

    @attr(kind='small')
    def test_allocate_for_instance_param_host_is_not_equal_to_self_host(self):
        """
        green_pool.spawn_n is called
        """
        self._function = None
        self._context = None
        self._topic = None
        self._method = None
        self._args = None

        def stub_spawn_n(caller, function, *args, **kwargs):
            self._function = function
            self._context = args[0]
            self._topic = args[1]
            self._method = args[2]['method']
            self._args = args[2]['args']

        self.mox.StubOutWithMock(db, 'project_get_networks')
        self.mox.StubOutWithMock(db, 'virtual_interface_create')
        self.mox.StubOutWithMock(rpc, 'call')
        self.mox.StubOutWithMock(db, 'queue_get_for')
        self.stubs.Set(greenpool.GreenPool, 'spawn_n', stub_spawn_n)
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        network = dict(networks[0])
        network['multi_host'] = True
        db.project_get_networks(mox.IgnoreArg(),
                                mox.IgnoreArg()).AndReturn([network])
        db.virtual_interface_create(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn(vifs[0])
        rpc.call(mox.IgnoreArg(),
                 mox.IgnoreArg(),
                 mox.IgnoreArg()).AndReturn('dummyhost')
        db.queue_get_for(mox.IgnoreArg(),
                         mox.IgnoreArg(),
                         mox.IgnoreArg()).AndReturn('network')
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([])
        db.instance_type_get(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        kwargs['host'] = None
        kwargs['project_id'] = 'fake_project'
        kwargs['instance_type_id'] = 1
        kwargs['requested_networks'] = None
        kwargs['vpn'] = False
        res = self.network.allocate_for_instance(self.context, **kwargs)
        self.assertEqual([], res)
        self.assertEqual(rpc.call, self._function)
        self.assertTrue(self._context)
        self.assertEqual('network', self._topic)
        self.assertEqual('_rpc_allocate_fixed_ip', self._method)
        self.assertEqual(kwargs['instance_id'], self._args['instance_id'])
        self.assertEqual(network['id'], self._args['network_id'])
        self.assertTrue(self._args['address'] is None)
        self.assertEqual(kwargs['vpn'], self._args['vpn'])

    @attr(kind='small')
    def test_init_host_floating_ips_db_fixed_ip_is_none(self):
        """
        driver.ensure_floating_forward is not called
        """
        self._is_called = False

        def stub_ensure_floating_forward(floating_ip, fixed_ip):
            self._is_called = True

        self.mox.StubOutWithMock(db, 'floating_ip_get_all_by_host')
        self.stubs.Set(self.network.driver, 'ensure_floating_forward',
                       stub_ensure_floating_forward)
        floating_ip = dict(floating_ip_fields)
        db.floating_ip_get_all_by_host(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn([floating_ip])
        self.mox.ReplayAll()

        self.network.init_host_floating_ips()
        self.assertFalse(self._is_called)

    @attr(kind='small')
    def test_init_host_floating_ips_db_fixed_ip_is_not_none(self):
        """
        driver.ensure_floating_forward is called
        """
        self._floating_ip = None
        self._fixed_ip = None

        def stub_ensure_floating_forward(floating_ip, fixed_ip):
            self._floating_ip = floating_ip
            self._fixed_ip = fixed_ip

        self.mox.StubOutWithMock(db, 'floating_ip_get_all_by_host')
        self.stubs.Set(self.network.driver, 'ensure_floating_forward',
                       stub_ensure_floating_forward)
        floating_ip = dict(floating_ip_fields)
        floating_ip['fixed_ip'] = {'address': '192.168.0.100'}
        db.floating_ip_get_all_by_host(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn([floating_ip])
        self.mox.ReplayAll()

        self.network.init_host_floating_ips()
        self.assertEqual(floating_ip['address'], self._floating_ip)
        self.assertEqual(floating_ip['fixed_ip']['address'], self._fixed_ip)

    @attr(kind='small')
    def test_init_host_floating_ips_ex_floating_ips_not_found(self):
        """
        none is returned
        """
        self.mox.StubOutWithMock(db, 'floating_ip_get_all_by_host')
        db.floating_ip_get_all_by_host(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndRaise(exception.FloatingIpNotFoundForHost())
        self.mox.ReplayAll()

        res = self.network.init_host_floating_ips()
        self.assertTrue(res is None)

    @attr(kind='small')
    def test_init_host_floating_ips_ex_driver_bind_floating_ip(self):
        """
        ProcessExecutionError is raised
        """
#        raise SkipTest('AssertionError: 2 != 1')
        self._count = 0

        def stub_bind_floating_ip(floating_ip, check_exit_code=True):
            self._count += 1
            raise exception.ProcessExecutionError()

        self.mox.StubOutWithMock(db, 'floating_ip_get_all_by_host')
        self.stubs.Set(self.network.driver, 'bind_floating_ip',
                       stub_bind_floating_ip)
        floating_ips = [floating_ip_fields, floating_ip_fields]
        floating_ips[0]['fixed_ip'] = {'address': '192.168.0.100'}
        floating_ips[1]['fixed_ip'] = {'address': '192.168.0.200'}
        db.floating_ip_get_all_by_host(mox.IgnoreArg(),
                                       mox.IgnoreArg()).AndReturn(floating_ips)
        self.mox.ReplayAll()

        self.assertRaises(exception.ProcessExecutionError,
                          self.network.init_host_floating_ips)
        self.assertEqual(2, self._count)

    @attr(kind='small')
    def test_init_host_floating_ips_ex_driver_ensure_floating_forward(self):
        """
        driver.unbind_floating_ip() is called
        when exception occurred in driver.ensure_floating_forward()
        """
        self._ensure_count = 0
        self._unbind_count = 0
        self._floating_ip = []

        def stub_ensure_floating_forward(floating_ip, fixed_ip):
            self._ensure_count += 1
            if self._ensure_count == 1:
                raise exception.ProcessExecutionError()
            if self._ensure_count == 2:
                return

        def stub_unbind_floating_ip(floating_ip):
            self._unbind_count += 1
            self._floating_ip.append(floating_ip)

        self.mox.StubOutWithMock(db, 'floating_ip_get_all_by_host')
        self.stubs.Set(self.network.driver, 'ensure_floating_forward',
                       stub_ensure_floating_forward)
        self.stubs.Set(self.network.driver, 'unbind_floating_ip',
                       stub_unbind_floating_ip)
        floating_ips = [floating_ip_fields, floating_ip_fields]
        floating_ips[0]['fixed_ip'] = {'address': '192.168.0.100'}
        floating_ips[1]['fixed_ip'] = {'address': '192.168.0.200'}
        db.floating_ip_get_all_by_host(mox.IgnoreArg(),
                                       mox.IgnoreArg()).AndReturn(floating_ips)
        self.mox.ReplayAll()

        self.assertRaises(exception.NetworkInitHostException,
                          self.network.init_host_floating_ips)
        self.assertEqual(2, self._ensure_count)
        self.assertEqual(1, self._unbind_count)
        self.assertEqual('192.168.0.100', self._floating_ip[0])

    @attr(kind='small')
    def test_allocate_for_instance(self):
        """
        network_api.associate_floating_ip is not called
        """
        self._is_called = False

        def stub_associate_floating_ip(self, context, floating_ip, fixed_ip,
                                       affect_auto_assigned=False):
            self._is_called = True

        self.mox.StubOutWithMock(db, 'project_get_networks')
        self.mox.StubOutWithMock(db, 'virtual_interface_create')
        self.mox.StubOutWithMock(db, 'fixed_ip_associate_pool')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        self.stubs.Set(network_api.API, 'associate_floating_ip',
                       stub_associate_floating_ip)
        db.project_get_networks(mox.IgnoreArg(),
                                mox.IgnoreArg()).AndReturn([networks[0]])
        db.virtual_interface_create(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn(vifs[0])
        db.fixed_ip_associate_pool(mox.IgnoreArg(),
                                   mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([])
        db.instance_type_get(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        kwargs['host'] = HOST
        kwargs['project_id'] = 'fake_project'
        kwargs['instance_type_id'] = 1
        kwargs['requested_networks'] = None
        kwargs['vpn'] = False
        res = self.network.allocate_for_instance(self.context, **kwargs)
        self.assertEqual([], res)
        self.assertFalse(self._is_called)

    @attr(kind='small')
    def test_allocate_for_instance_param_instance_does_not_exist(self):
        """
        InstanceNotFound is raised when instance does not exist
        """
#        raise SkipTest('Parameter check is not implemented yet')
        self.mox.StubOutWithMock(db, 'instance_get')
        db.instance_get(mox.IgnoreArg(),
                        mox.IgnoreArg()).AndRaise(exception.InstanceNotFound)
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 99999  # not exist
        kwargs['host'] = HOST
        kwargs['project_id'] = 'fake_project'
        kwargs['instance_type_id'] = 1
        kwargs['requested_networks'] = None
        kwargs['vpn'] = False
        self.assertRaises(exception.InstanceNotFound,
                          self.network.allocate_for_instance,
                          self.context, **kwargs)

    @attr(kind='small')
    def test_allocate_for_instance_cfg_auto_assign_floating_ip(self):
        """
        network_api.associate_floating_ip is called
        """
        self.flags(auto_assign_floating_ip=True)

        self._context = None
        self._floating_ip = None
        self._fixed_ip = None
        self._affect_auto_assigned = None

        def stub_associate_floating_ip(caller, context, floating_ip, fixed_ip,
                                       affect_auto_assigned=False):
            self._context = context
            self._floating_ip = floating_ip
            self._fixed_ip = fixed_ip
            self._affect_auto_assigned = affect_auto_assigned

        self.mox.StubOutWithMock(db, 'project_get_networks')
        self.mox.StubOutWithMock(db, 'virtual_interface_create')
        self.mox.StubOutWithMock(db, 'fixed_ip_associate_pool')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        self.mox.StubOutWithMock(db, 'floating_ip_count_by_project')
        self.mox.StubOutWithMock(db, 'quota_get_all_by_project')
        self.mox.StubOutWithMock(db, 'floating_ip_allocate_address')
        self.mox.StubOutWithMock(db, 'floating_ip_set_auto_assigned')
        self.mox.StubOutWithMock(db, 'floating_ip_get_by_address')
        self.stubs.Set(network_api.API, 'associate_floating_ip',
                       stub_associate_floating_ip)
        db.project_get_networks(mox.IgnoreArg(),
                                mox.IgnoreArg()).AndReturn([networks[0]])
        db.virtual_interface_create(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn(vifs[0])
        db.fixed_ip_associate_pool(mox.IgnoreArg(),
                                   mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([])
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([])
        db.instance_type_get(mox.IgnoreArg(), mox.IgnoreArg())
        db.floating_ip_count_by_project(mox.IgnoreArg(),
                                        mox.IgnoreArg()).AndReturn(0)
        db.floating_ip_count_by_project(mox.IgnoreArg(),
                                        mox.IgnoreArg()).AndReturn(0)
        db.quota_get_all_by_project(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn({})
        db.quota_get_all_by_project(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn({})
        db.floating_ip_allocate_address(mox.IgnoreArg(), mox.IgnoreArg())
        db.floating_ip_set_auto_assigned(mox.IgnoreArg(), mox.IgnoreArg())
        floating_ip = dict(floating_ip_fields)
        db.floating_ip_get_by_address(mox.IgnoreArg(),
                                      mox.IgnoreArg()).AndReturn(floating_ip)
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        kwargs['host'] = HOST
        kwargs['project_id'] = 'fake_project'
        kwargs['instance_type_id'] = 1
        kwargs['requested_networks'] = None
        kwargs['vpn'] = False
        res = self.network.allocate_for_instance(self.context, **kwargs)
        self.assertEqual([], res)
        self.assertTrue(self._context)
        self.assertEqual(floating_ip, self._floating_ip)
        self.assertTrue(self._fixed_ip is None)
        self.assertTrue(self._affect_auto_assigned)

    @attr(kind='small')
    def test_deallocate_for_instance_param_instance_does_not_exist(self):
        """
        InstanceNotFound is raised when instance does not exist
        """
#        raise SkipTest('Parameter check is not implemented yet')
        self.mox.StubOutWithMock(db, 'instance_get')
        db.instance_get(mox.IgnoreArg(),
                        mox.IgnoreArg()).AndRaise(exception.InstanceNotFound)
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 99999  # not exist
        self.assertRaises(exception.InstanceNotFound,
                          self.network.deallocate_for_instance,
                          self.context, **kwargs)

    @attr(kind='small')
    def test_deallocate_for_instance_db_floating_ip_auto_assigned(self):
        """
        network_api.release_floating_ip is called
        """
        self._context = None
        self._address = None
        self._affect_auto_assigned = None

        def stub_release_floating_ip(
                        caller, context, address, affect_auto_assigned=False):
            self._context = context
            self._address = address
            self._affect_auto_assigned = affect_auto_assigned

        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_delete_by_instance')
        self.mox.StubOutWithMock(network_api.API, 'disassociate_floating_ip')
        self.stubs.Set(network_api.API, 'release_floating_ip',
                       stub_release_floating_ip)
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_address')
        self.mox.StubOutWithMock(db, 'instance_get')
        fixed_ip = FakeModel(**fixed_ips[0])
        fixed_ip.floating_ips = [{'address': '192.168.10.100',
                                  'auto_assigned': True}]
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([fixed_ip])
        db.virtual_interface_delete_by_instance(
                                            mox.IgnoreArg(), mox.IgnoreArg())
        network_api.API().disassociate_floating_ip(
                                            mox.IgnoreArg(), mox.IgnoreArg())
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        db.fixed_ip_get_by_address(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'instance': {'id': 0}})
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        self.network.deallocate_for_instance(self.context, **kwargs)
        self.assertTrue(self._context)
        self.assertEqual(fixed_ip.floating_ips[0]['address'], self._address)
        self.assertTrue(self._affect_auto_assigned)

    @attr(kind='small')
    def test_deallocate_for_instance_db_floating_ip_not_auto_assigned(self):
        """
        network_api.release_floating_ip is not called
        """
        self._is_called = False

        def stub_release_floating_ip(
                        caller, context, address, affect_auto_assigned=False):
            self._is_called = True

        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_delete_by_instance')
        self.mox.StubOutWithMock(network_api.API, 'disassociate_floating_ip')
        self.stubs.Set(network_api.API, 'release_floating_ip',
                       stub_release_floating_ip)
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_address')
        self.mox.StubOutWithMock(db, 'instance_get')
        fixed_ip = FakeModel(**fixed_ips[0])
        fixed_ip.floating_ips = [{'address': '192.168.10.100',
                                  'auto_assigned': False}]
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([fixed_ip])
        db.virtual_interface_delete_by_instance(
                        mox.IgnoreArg(), mox.IgnoreArg())
        network_api.API().disassociate_floating_ip(
                                            mox.IgnoreArg(), mox.IgnoreArg())
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        db.fixed_ip_get_by_address(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'instance': {'id': 0}})
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        self.network.deallocate_for_instance(self.context, **kwargs)
        self.assertFalse(self._is_called)

    @attr(kind='small')
    def test_deallocate_for_instance_ex_network_api_disassoc_floating_ip(self):
        """
        All FloatingIps are disassociated and deallocated
        even when exception is raised in network_api.disassociate_floating_ip()
        """
        self._disassociate_floating_ip_count = 0
        self._release_floating_ip_count = 0

        def stub_disassociate_floating_ip(caller, context, address,
                                          affect_auto_assigned=False):
            self._disassociate_floating_ip_count += 1
            raise exception.ApiError('ApiError occurred')

        def stub_release_floating_ip(
                        caller, context, address, affect_auto_assigned=False):
            self._release_floating_ip_count += 1

        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.stubs.Set(network_api.API, 'disassociate_floating_ip',
                       stub_disassociate_floating_ip)
        self.stubs.Set(network_api.API, 'release_floating_ip',
                       stub_release_floating_ip)
        _fixed_ips = list([FakeModel(**fixed_ips[0]),
                           FakeModel(**fixed_ips[1])])
        _fixed_ips[0].floating_ips = [
                        {'address': '192.168.0.1', 'auto_assigned': True}]
        _fixed_ips[1].floating_ips = [
                        {'address': '192.168.0.2', 'auto_assigned': True}]
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn(_fixed_ips)
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        self.assertRaises(exception.NetworkDeallocateException,
                          self.network.deallocate_for_instance,
                          self.context, **kwargs)
        self.assertEqual(2, self._disassociate_floating_ip_count)
        self.assertEqual(2, self._release_floating_ip_count)

    @attr(kind='small')
    def test_deallocate_for_instance_ex_network_api_release_floating_ip(self):
        """
        All FloatingIps are disassociated and deallocated
        even when exception is raised in network_api.release_floating_ip()
        """
        self._disassociate_floating_ip_count = 0
        self._release_floating_ip_count = 0

        def stub_disassociate_floating_ip(caller, context, address,
                                          affect_auto_assigned=False):
            self._disassociate_floating_ip_count += 1

        def stub_release_floating_ip(
                        caller, context, address, affect_auto_assigned=False):
            self._release_floating_ip_count += 1
            raise exception.ApiError('ApiError occurred')

        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.stubs.Set(network_api.API, 'disassociate_floating_ip',
                       stub_disassociate_floating_ip)
        self.stubs.Set(network_api.API, 'release_floating_ip',
                       stub_release_floating_ip)
        _fixed_ips = list([FakeModel(**fixed_ips[0]),
                           FakeModel(**fixed_ips[1])])
        _fixed_ips[0].floating_ips = [
                        {'address': '192.168.0.1', 'auto_assigned': True}]
        _fixed_ips[1].floating_ips = [
                        {'address': '192.168.0.2', 'auto_assigned': True}]
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn(_fixed_ips)
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        self.assertRaises(exception.NetworkDeallocateException,
                          self.network.deallocate_for_instance,
                          self.context, **kwargs)
        self.assertEqual(2, self._disassociate_floating_ip_count)
        self.assertEqual(2, self._release_floating_ip_count)

    @attr(kind='small')
    def test_allocate_floating_ip_db_address_quota_not_exceeded(self):
        """
        db.floating_ip_allocate_address is called
        """
        self._is_called = False

        def stub_floating_ip_allocate_address(context, project_id):
            self._is_called = True
            return '192.168.10.100'

        self.mox.StubOutWithMock(db, 'floating_ip_count_by_project')
        self.mox.StubOutWithMock(db, 'quota_get_all_by_project')
        db.floating_ip_count_by_project(mox.IgnoreArg(),
                                        mox.IgnoreArg()).AndReturn(0)
        db.floating_ip_count_by_project(mox.IgnoreArg(),
                                        mox.IgnoreArg()).AndReturn(0)
        db.quota_get_all_by_project(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'floating_ips': 1})
        db.quota_get_all_by_project(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'floating_ips': 1})
        self.stubs.Set(db, 'floating_ip_allocate_address',
                       stub_floating_ip_allocate_address)
        self.mox.ReplayAll()

        res = self.network.allocate_floating_ip(self.context, 'fake_project')
        self.assertEqual('192.168.10.100', res)
        self.assertTrue(self._is_called)

    @attr(kind='small')
    def test_allocate_floating_ip_db_address_quota_exceeded(self):
        """
        QuotaError is raised
        """
        self.mox.StubOutWithMock(db, 'floating_ip_count_by_project')
        self.mox.StubOutWithMock(db, 'quota_get_all_by_project')
        db.floating_ip_count_by_project(mox.IgnoreArg(),
                                        mox.IgnoreArg()).AndReturn(1)
        db.floating_ip_count_by_project(mox.IgnoreArg(),
                                        mox.IgnoreArg()).AndReturn(1)
        db.quota_get_all_by_project(
                        mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'floating_ips': 1})
        db.quota_get_all_by_project(
                        mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'floating_ips': 1})
        self.mox.ReplayAll()

        self.assertRaises(quota.QuotaError,
                          self.network.allocate_floating_ip,
                          self.context, 'fake_project')

    @attr(kind='small')
    def test_associate_floating_ip_db_floating_ip_fixed_ip_is_none(self):
        """
        driver.ensure_floating_forward is called
        """
        self._floating_ip = None
        self._fixed_ip = None

        def stub_ensure_floating_forward(floating_ip, fixed_ip):
            self._floating_ip = floating_ip
            self._fixed_ip = fixed_ip

        self.mox.StubOutWithMock(db, 'floating_ip_get_by_address')
        self.mox.StubOutWithMock(db, 'floating_ip_fixed_ip_associate')
        self.mox.StubOutWithMock(self.network.driver, 'bind_floating_ip')
        self.stubs.Set(self.network.driver, 'ensure_floating_forward',
                       stub_ensure_floating_forward)
        floating_ip = {'address': '10.10.10.10',
                       'fixed_ip': None}
        db.floating_ip_get_by_address(mox.IgnoreArg(),
                                      mox.IgnoreArg()).AndReturn(floating_ip)
        db.floating_ip_fixed_ip_associate(mox.IgnoreArg(),
                                          mox.IgnoreArg(),
                                          mox.IgnoreArg(),
                                          mox.IgnoreArg())
        self.network.driver.bind_floating_ip(mox.IgnoreArg())
        self.mox.ReplayAll()

        floating_ip_address = '192.168.0.100'
        fixed_ip_address = '10.0.0.0'
        self.network.associate_floating_ip(
                        self.context, floating_ip_address, fixed_ip_address)
        self.assertEqual(floating_ip_address, self._floating_ip)
        self.assertEqual(fixed_ip_address, self._fixed_ip)

    @attr(kind='small')
    def test_associate_floating_ip_ex_driver_bind_floating_ip(self):
        """
        ProcessExecutionError is raised
        """
        def stub_bind_floating_ip(floating_ip, check_exit_code=True):
            raise exception.ProcessExecutionError()

        self.mox.StubOutWithMock(db, 'floating_ip_get_by_address')
        self.mox.StubOutWithMock(db, 'floating_ip_fixed_ip_associate')
        self.stubs.Set(self.network.driver, 'bind_floating_ip',
                       stub_bind_floating_ip)
        floating_ip = {'address': '10.10.10.10',
                       'fixed_ip': None}
        db.floating_ip_get_by_address(mox.IgnoreArg(),
                                      mox.IgnoreArg()).AndReturn(floating_ip)
        db.floating_ip_fixed_ip_associate(mox.IgnoreArg(),
                                          mox.IgnoreArg(),
                                          mox.IgnoreArg(),
                                          mox.IgnoreArg())
        self.mox.ReplayAll()

        floating_ip_address = '192.168.0.100'
        fixed_ip_address = '10.0.0.0'
        self.assertRaises(exception.ProcessExecutionError,
                          self.network.associate_floating_ip,
                          self.context, floating_ip_address, fixed_ip_address)

    @attr(kind='small')
    def test_associate_floating_ip_ex_driver_ensure_floating_forward(self):
        """
        driver.unbind_floating_ip() is called
        when exception occurred in driver.ensure_floating_forward()
        """
        self._floating_ip = None

        def stub_ensure_floating_forward(floating_ip, fixed_ip):
            raise exception.ProcessExecutionError()

        def stub_unbind_floating_ip(floating_ip):
            self._floating_ip = floating_ip

        self.mox.StubOutWithMock(db, 'floating_ip_get_by_address')
        self.mox.StubOutWithMock(db, 'floating_ip_fixed_ip_associate')
        self.stubs.Set(self.network.driver, 'ensure_floating_forward',
                       stub_ensure_floating_forward)
        self.stubs.Set(self.network.driver, 'unbind_floating_ip',
                       stub_unbind_floating_ip)
        floating_ip = {'address': '10.10.10.10',
                       'fixed_ip': None}
        db.floating_ip_get_by_address(mox.IgnoreArg(),
                                      mox.IgnoreArg()).AndReturn(floating_ip)
        db.floating_ip_fixed_ip_associate(mox.IgnoreArg(),
                                          mox.IgnoreArg(),
                                          mox.IgnoreArg(),
                                          mox.IgnoreArg())
        self.mox.ReplayAll()

        floating_ip_address = '192.168.0.100'
        fixed_ip_address = '10.0.0.0'
        self.assertRaises(exception.ProcessExecutionError,
                          self.network.associate_floating_ip,
                          self.context, floating_ip_address, fixed_ip_address)
        self.assertEqual(floating_ip_address, self._floating_ip)

    @attr(kind='small')
    def test_disassociate_floating_ip(self):
        """
        driver.remove_floating_forward is called
        """
        self._floating_ip = None
        self._fixed_ip = None

        def stub_remove_floating_forward(floating_ip, fixed_ip):
            self._floating_ip = floating_ip
            self._fixed_ip = fixed_ip

        self.mox.StubOutWithMock(db, 'floating_ip_disassociate')
        self.mox.StubOutWithMock(self.network.driver, 'unbind_floating_ip')
        self.stubs.Set(self.network.driver, 'remove_floating_forward',
                       stub_remove_floating_forward)
        fixed_ip_address = '10.0.0.0'
        db.floating_ip_disassociate(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn(fixed_ip_address)
        self.network.driver.unbind_floating_ip(mox.IgnoreArg())
        self.mox.ReplayAll()

        floating_ip_address = '192.168.0.100'
        self.network.disassociate_floating_ip(
                        self.context, floating_ip_address)
        self.assertEqual(floating_ip_address, self._floating_ip)
        self.assertEqual(fixed_ip_address, self._fixed_ip)

    @attr(kind='small')
    def test_disassociate_floating_ip_ex_driver_unbind_floating_ip(self):
        """
        ProcessExecutionError is raised
        """
        def stub_unbind_floating_ip(floating_ip):
            raise exception.ProcessExecutionError()

        self.mox.StubOutWithMock(db, 'floating_ip_disassociate')
        self.stubs.Set(self.network.driver, 'unbind_floating_ip',
                       stub_unbind_floating_ip)
        fixed_ip_address = '10.0.0.0'
        db.floating_ip_disassociate(
                        mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn(fixed_ip_address)
        self.mox.ReplayAll()

        floating_ip_address = '192.168.0.100'
        self.assertRaises(exception.ProcessExecutionError,
                          self.network.disassociate_floating_ip,
                          self.context, floating_ip_address)

    @attr(kind='small')
    def test_disassociate_floating_ip_ex_driver_remove_floating_forward(self):
        """
        ProcessExecutionError is raised
        """
        def stub_remove_floating_forward(floating_ip, fixed_ip):
            raise exception.ProcessExecutionError()

        self.mox.StubOutWithMock(db, 'floating_ip_disassociate')
        self.stubs.Set(self.network.driver, 'remove_floating_forward',
                       stub_remove_floating_forward)
        fixed_ip_address = '10.0.0.0'
        db.floating_ip_disassociate(
                        mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn(fixed_ip_address)
        self.mox.ReplayAll()

        floating_ip_address = '192.168.0.100'
        self.assertRaises(exception.ProcessExecutionError,
                          self.network.disassociate_floating_ip,
                          self.context, floating_ip_address)

    @attr(kind='small')
    def test_deallocate_floating_ip(self):
        """
        db.floating_ip_deallocate is called
        """
        self._context = None
        self._address = None

        def stub_floating_ip_deallocate(context, address):
            self._context = context
            self._address = address

        self.stubs.Set(db, 'floating_ip_deallocate',
                       stub_floating_ip_deallocate)

        floating_ip_address = '192.168.0.100'
        self.network.deallocate_floating_ip(self.context, floating_ip_address)
        self.assertTrue(self._context)
        self.assertEqual(floating_ip_address, self._address)

    @attr(kind='small')
    def test_init_host(self):
        """
        driver.metadata_forward is called
        """
        self._is_called = False

        def stub_metadata_forward():
            self._is_called = True

        self.stubs.Set(self.network.driver, 'metadata_forward',
                       stub_metadata_forward)

        self.network.init_host()
        self.assertTrue(self._is_called)

    @attr(kind='small')
    def test_init_host_ex_driver_init_host(self):
        """
        ProcessExecutionError is raised
        """
        def stub_init_host():
            raise exception.ProcessExecutionError()

        self.stubs.Set(self.network.driver, 'init_host', stub_init_host)

        self.assertRaises(exception.ProcessExecutionError,
                          self.network.init_host)

    @attr(kind='small')
    def test_allocate_fixed_ip_param_instance_does_not_exist(self):
        """
        InstanceNotFound is raised when instance does not exist
        """
#        raise SkipTest('Parameter check is not implemented yet')
        self.mox.StubOutWithMock(db, 'instance_get')
        db.instance_get(mox.IgnoreArg(),
                        mox.IgnoreArg()).AndRaise(exception.InstanceNotFound)
        self.mox.ReplayAll()

        instance_id = 99999  # not exist
        kwargs = {}
        kwargs['address'] = '10.0.0.0'
        self.assertRaises(exception.InstanceNotFound,
                          self.network.allocate_fixed_ip,
                          self.context, instance_id, networks[0], **kwargs)

    @attr(kind='small')
    def test_allocate_fixed_ip_param_address_is_not_none(self):
        """
        db.fixed_ip_associate is called
        """
        fixed_ip_address = '192.168.0.101'
        self._context = None
        self._address = None
        self._instance_id = None
        self._network_id = None
        self._reserved = None

        def stub_fixed_ip_associate(
                        context, address, instance_id,
                        network_id=None, reserved=False):
            self._context = context
            self._address = address
            self._instance_id = instance_id
            self._network_id = network_id
            self._reserved = reserved
            return fixed_ip_address

        self.stubs.Set(db, 'fixed_ip_associate', stub_fixed_ip_associate)
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['address'] = '10.0.0.0'
        res = self.network.allocate_fixed_ip(
                        self.context, 1, networks[0], **kwargs)
        self.assertEqual(fixed_ip_address, res)
        self.assertTrue(self._context)
        self.assertEqual(kwargs['address'], self._address)
        self.assertEqual(1, self._instance_id)
        self.assertEqual(networks[0]['id'], self._network_id)
        self.assertEqual(False, self._reserved)

    @attr(kind='small')
    def test_allocate_fixed_ip_param_not_vpn_pub_address_and_vpn_forward(self):
        """
        driver.ensure_vpn_forward is called
        """
        self._public_ip = None
        self._port = None
        self._private_ip = None

        def stub_ensure_vpn_forward(public_ip, port, private_ip):
            self._public_ip = public_ip
            self._port = port
            self._private_ip = private_ip

        self.mox.StubOutWithMock(db, 'fixed_ip_associate')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db, 'network_update')
        self.stubs.Set(self.network.driver, 'ensure_vpn_forward',
                       stub_ensure_vpn_forward)
        db.fixed_ip_associate(mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        network = dict(networks[0])
        network['vpn_public_address'] = None
        network['vpn_public_port'] = None
        network['vpn_private_address'] = None
        db.network_update(mox.IgnoreArg(),
                          mox.IgnoreArg(),
                          mox.IgnoreArg()).AndReturn(network)
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['address'] = '192.168.0.101'
        res = self.network.allocate_fixed_ip(
                        self.context, 1, network, **kwargs)
        self.assertEqual('192.168.0.101', res)
        self.assertEqual(flags.FLAGS.vpn_ip, self._public_ip)
        self.assertEqual(network['vpn_public_port'], self._port)
        self.assertEqual(network['vpn_private_address'], self._private_ip)

    @attr(kind='small')
    def test_allocate_fixed_ip_cfg_not_fake_network_and_not_use_ipv6(self):
        """
        db.network_update is called
        """
        self.flags(fake_network=False)
        self.flags(use_ipv6=False)

        self.flags(fake_network=False)
        self.flags(use_ipv6=False)

        self._context = None
        self._dev = None
        self._network_ref = None

        def stub_update_dhcp(context, dev, network_ref):
            self._context = context
            self._dev = dev
            self._network_ref = network_ref

        self.mox.StubOutWithMock(db, 'fixed_ip_associate')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(self.network.driver, 'plug')
        self.mox.StubOutWithMock(self.network.driver,
                                 'initialize_gateway_device')
        self.stubs.Set(self.network.driver, 'update_dhcp', stub_update_dhcp)
        db.fixed_ip_associate(mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        dev = networks[0]['bridge']
        self.network.driver.plug(mox.IgnoreArg(),
                                 mox.IgnoreArg()).AndReturn(dev)
        self.network.driver.initialize_gateway_device(
                                    mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        network = networks[0]
        kwargs = {}
        kwargs['address'] = '192.168.0.101'
        res = self.network.allocate_fixed_ip(
                        self.context, 1, network, **kwargs)
        self.assertEqual('192.168.0.101', res)
        self.assertTrue(self._context)
        self.assertEqual(dev, self._dev)
        self.assertEqual(network, self._network_ref)

    @attr(kind='small')
    def test_allocate_fixed_ip_cfg_not_fake_network_and_use_ipv6(self):
        """
        db.network_update is called
        """
        self.flags(fake_network=False)
        self.flags(use_ipv6=True)

        self._context = None
        self._network_id = None
        self._values = None

        def stub_network_update(context, network_id, values):
            self._context = context
            self._network_id = network_id
            self._values = values

        self.mox.StubOutWithMock(db, 'fixed_ip_associate')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(self.network.driver, 'plug')
        self.mox.StubOutWithMock(self.network.driver,
                                 'initialize_gateway_device')
        self.mox.StubOutWithMock(self.network.driver, 'update_dhcp')
        self.mox.StubOutWithMock(self.network.driver, 'update_ra')
        self.mox.StubOutWithMock(utils, 'get_my_linklocal')
        self.stubs.Set(db, 'network_update', stub_network_update)
        db.fixed_ip_associate(mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.network.driver.plug(mox.IgnoreArg(), mox.IgnoreArg())
        self.network.driver.initialize_gateway_device(
                                        mox.IgnoreArg(), mox.IgnoreArg())
        self.network.driver.update_dhcp(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.network.driver.update_ra(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        gateway = 'gatewayv6'
        utils.get_my_linklocal(mox.IgnoreArg()).AndReturn(gateway)
        self.mox.ReplayAll()

        network = networks[0]
        kwargs = {}
        kwargs['address'] = '192.168.0.101'
        res = self.network.allocate_fixed_ip(
                        self.context, 1, network, **kwargs)
        self.assertEqual('192.168.0.101', res)
        self.assertTrue(self._context)
        self.assertEqual(network['id'], self._network_id)
        self.assertEqual(gateway, self._values['gateway_v6'])

    @attr(kind='small')
    def test_allocate_fixed_ip_ex_driver_plug(self):
        """
        ProcessExecutionError is raised
        """
        self.flags(fake_network=False)
        self.flags(use_ipv6=True)

        def stub_plug(network, mac_address):
            raise exception.ProcessExecutionError()

        self.mox.StubOutWithMock(db, 'fixed_ip_associate')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.stubs.Set(self.network.driver, 'plug', stub_plug)
        db.fixed_ip_associate(mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        network = networks[0]
        kwargs = {}
        kwargs['address'] = '192.168.0.101'
        self.assertRaises(exception.ProcessExecutionError,
                          self.network.allocate_fixed_ip,
                          self.context, 1, network, **kwargs)

    @attr(kind='small')
    def test_allocate_fixed_ip_ex_driver_initialize_gateway_device(self):
        """
        driver.unbind_floating_ip() is called for cleanup
        """
        self.flags(fake_network=False)
        self.flags(use_ipv6=True)

        self._network = None

        def stub_initialize_gateway_device(dev, network_ref):
            raise exception.ProcessExecutionError()

        def stub_unplug(network):
            self._network = network

        self.mox.StubOutWithMock(db, 'fixed_ip_associate')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(self.network.driver, 'plug')
        self.stubs.Set(self.network.driver, 'initialize_gateway_device',
                       stub_initialize_gateway_device)
        self.stubs.Set(self.network.driver, 'unplug', stub_unplug)
        db.fixed_ip_associate(mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.network.driver.plug(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        network = networks[0]
        kwargs = {}
        kwargs['address'] = '192.168.0.101'
        self.assertRaises(exception.ProcessExecutionError,
                          self.network.allocate_fixed_ip,
                          self.context, 1, network, **kwargs)
        self.assertEqual(network, self._network)

    @attr(kind='small')
    def test_allocate_fixed_ip_ex_driver_ensure_vpn_forward(self):
        """
        driver.unbind_floating_ip() is called for cleanup
        """
        self._network = None

        def stub_ensure_vpn_forward(public_ip, port, private_ip):
            raise exception.ProcessExecutionError()

        def stub_unplug(network):
            self._network = network

        self.mox.StubOutWithMock(db, 'fixed_ip_associate')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db, 'network_update')
        self.stubs.Set(self.network.driver, 'ensure_vpn_forward',
                       stub_ensure_vpn_forward)
        self.stubs.Set(self.network.driver, 'unplug', stub_unplug)
        db.fixed_ip_associate(mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        network = dict(networks[0])
        network['vpn_public_address'] = None
        network['vpn_public_port'] = None
        network['vpn_private_address'] = None
        db.network_update(mox.IgnoreArg(),
                          mox.IgnoreArg(),
                          mox.IgnoreArg()).AndReturn(network)
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['address'] = '192.168.0.101'
        self.assertRaises(exception.ProcessExecutionError,
                          self.network.allocate_fixed_ip,
                          self.context, 1, network, **kwargs)
        self.assertEqual(network, self._network)

    @attr(kind='small')
    def test_allocate_fixed_ip_ex_driver_update_dhcp(self):
        """
        driver.unbind_floating_ip() is called for cleanup
        """
        self.flags(fake_network=False)
        self.flags(use_ipv6=True)

        self._network = None

        def stub_update_dhcp(context, dev, network_ref):
            raise exception.ProcessExecutionError()

        def stub_unplug(network):
            self._network = network

        self.mox.StubOutWithMock(db, 'fixed_ip_associate')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(self.network.driver, 'plug')
        self.mox.StubOutWithMock(self.network.driver,
                                 'initialize_gateway_device')
        self.stubs.Set(self.network.driver, 'update_dhcp', stub_update_dhcp)
        self.stubs.Set(self.network.driver, 'unplug', stub_unplug)
        db.fixed_ip_associate(mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.network.driver.plug(mox.IgnoreArg(), mox.IgnoreArg())
        self.network.driver.initialize_gateway_device(
                                    mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        network = networks[0]
        kwargs = {}
        kwargs['address'] = '192.168.0.101'
        self.assertRaises(exception.ProcessExecutionError,
                          self.network.allocate_fixed_ip,
                          self.context, 1, network, **kwargs)
        self.assertEqual(network, self._network)

    @attr(kind='small')
    def test_allocate_fixed_ip_ex_driver_update_ra(self):
        """
        driver.release_dhcp() and
        driver.unbind_floating_ip() are called for cleanup
        """
        self.flags(fake_network=False)
        self.flags(use_ipv6=True)

        self._network = None
        self._dev = None
        self._address = None
        self._mac_address = None

        def stub_update_ra(context, dev, network_ref):
            raise exception.ProcessExecutionError()

        def stub_release_dhcp(dev, address, mac_address):
            self._dev = dev
            self._address = address
            self._mac_address = mac_address

        def stub_unplug(network):
            self._network = network

        self.mox.StubOutWithMock(db, 'fixed_ip_associate')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(self.network, 'generate_mac_address')
        self.mox.StubOutWithMock(self.network.driver, 'plug')
        self.mox.StubOutWithMock(self.network.driver,
                                 'initialize_gateway_device')
        self.mox.StubOutWithMock(self.network.driver, 'update_dhcp')
        self.stubs.Set(self.network.driver, 'update_ra', stub_update_ra)
        self.stubs.Set(self.network.driver, 'release_dhcp', stub_release_dhcp)
        self.stubs.Set(self.network.driver, 'unplug', stub_unplug)
        db.fixed_ip_associate(mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        mac_address = '00-00-00-00-00-00-00-00'
        self.network.generate_mac_address().AndReturn(mac_address)
        dev = 'dev'
        self.network.driver.plug(mox.IgnoreArg(),
                                 mox.IgnoreArg()).AndReturn(dev)
        self.network.driver.initialize_gateway_device(
                                        mox.IgnoreArg(), mox.IgnoreArg())
        self.network.driver.update_dhcp(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        network = networks[0]
        kwargs = {}
        kwargs['address'] = '192.168.0.101'
        self.assertRaises(exception.ProcessExecutionError,
                          self.network.allocate_fixed_ip,
                          self.context, 1, network, **kwargs)
        self.assertEqual(dev, self._dev)
        self.assertEqual(network['dhcp_server'], self._address)
        self.assertEqual(mac_address, self._mac_address)
        self.assertEqual(network, self._network)

    @attr(kind='small')
    def test_add_network_to_project(self):
        """
        db.network_associate is called
        """
        self._context = None
        self._project_id = None
        self._force = None

        def stub_network_associate(context, project_id, force=False):
            self._context = context
            self._project_id = project_id
            self._force = force

        self.stubs.Set(db, 'network_associate', stub_network_associate)

        project_id = 'fake_project'
        self.network.add_network_to_project(self.context, project_id)
        self.assertTrue(self._context)
        self.assertEqual(project_id, self._project_id)
        self.assertEqual(True, self._force)

    @attr(kind='small')
    def test_allocate_for_instance_param_requested_networks_exist(self):
        """
        db.network_get_all_by_uuids is called
        """
        network = networks[0]
        self._context = None
        self._network_uuids = None
        self._project_id = None

        def stub_network_get_all_by_uuids(context,
                                          network_uuids, project_id=None):
            self._context = context
            self._network_uuids = network_uuids
            self._project_id = project_id
            return [network]

        self.stubs.Set(db, 'network_get_all_by_uuids',
                       stub_network_get_all_by_uuids)
        self.mox.StubOutWithMock(db, 'virtual_interface_create')
        self.mox.StubOutWithMock(db, 'fixed_ip_associate')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        db.virtual_interface_create(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn(vifs[0])
        db.fixed_ip_associate(mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([])
        db.instance_type_get(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        kwargs['host'] = HOST
        kwargs['project_id'] = 'fake_project'
        kwargs['instance_type_id'] = 1
        kwargs['requested_networks'] = [
                        ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
                         '192.168.0.100')]
        kwargs['vpn'] = False
        res = self.network.allocate_for_instance(self.context, **kwargs)
        self.assertEqual([], res)
        self.assertTrue(self._context)
        self.assertEqual([kwargs['requested_networks'][0][0]],
                         self._network_uuids)
        self.assertEqual(kwargs['project_id'], self._project_id)

    @attr(kind='small')
    def test_allocate_for_instance_param_requested_networks_do_not_exist(self):
        """
        db.project_get_networks is called
        """
        network = networks[0]
        self._context = None
        self._project_id = None
        self._associate = None

        def stub_project_get_networks(context, project_id, associate=True):
            self._context = context
            self._project_id = project_id
            self._associate = associate
            return [network]

        self.stubs.Set(db, 'project_get_networks', stub_project_get_networks)
        self.mox.StubOutWithMock(db, 'virtual_interface_create')
        self.mox.StubOutWithMock(db, 'fixed_ip_associate_pool')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(db, 'fixed_ip_get_by_instance')
        self.mox.StubOutWithMock(db, 'virtual_interface_get_by_instance')
        self.mox.StubOutWithMock(db, 'instance_type_get')
        db.virtual_interface_create(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn(vifs[0])
        db.fixed_ip_associate_pool(mox.IgnoreArg(),
                                   mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        db.fixed_ip_get_by_instance(mox.IgnoreArg(),
                                    mox.IgnoreArg()).AndReturn([])
        db.virtual_interface_get_by_instance(mox.IgnoreArg(),
                                             mox.IgnoreArg()).AndReturn([])
        db.instance_type_get(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        kwargs = {}
        kwargs['instance_id'] = 1
        kwargs['host'] = HOST
        kwargs['project_id'] = 'fake_project'
        kwargs['instance_type_id'] = 1
        kwargs['requested_networks'] = None
        kwargs['vpn'] = False
        res = self.network.allocate_for_instance(self.context, **kwargs)
        self.assertEqual([], res)
        self.assertTrue(self._context)
        self.assertEqual(kwargs['project_id'], self._project_id)
        self.assertEqual(True, self._associate)


class CommonNetworkTestCase(test.TestCase):

    class FakeNetworkManager(network_manager.NetworkManager):
        """This NetworkManager doesn't call the base class so we can bypass all
        inherited service cruft and just perform unit tests.
        """

        class FakeDB:
            def fixed_ip_get_by_instance(self, context, instance_id):
                return [dict(address='10.0.0.0'), dict(address='10.0.0.1'),
                        dict(address='10.0.0.2')]

            def network_get_by_cidr(self, context, cidr):
                raise exception.NetworkNotFoundForCidr()

            def network_create_safe(self, context, net):
                fakenet = dict(net)
                fakenet['id'] = 999
                return fakenet

            def network_get_all(self, context):
                raise exception.NoNetworksFound()

        def __init__(self):
            self.db = self.FakeDB()
            self.deallocate_called = None

        def deallocate_fixed_ip(self, context, address):
            self.deallocate_called = address

        def _create_fixed_ips(self, context, network_id):
            pass

    def fake_network_create_safe(self, context, net):
        return None

    def fake_create_fixed_ips(self, context, network_id):
        return None

    def test_remove_fixed_ip_from_instance(self):
        manager = self.FakeNetworkManager()
        manager.remove_fixed_ip_from_instance(None, 99, '10.0.0.1')

        self.assertEquals(manager.deallocate_called, '10.0.0.1')

    def test_remove_fixed_ip_from_instance_bad_input(self):
        manager = self.FakeNetworkManager()
        self.assertRaises(exception.FixedIpNotFoundForSpecificInstance,
                          manager.remove_fixed_ip_from_instance,
                          None, 99, 'bad input')

    @attr(kind='small')
    def test_remove_fixed_ip_from_instance_param_instance_does_not_exist(self):
        """
        InstanceNotFound is raised when instance does not exist
        """
#        raise SkipTest('Parameter check is not implemented yet')
        self.mox.StubOutWithMock(db, 'instance_get')
        db.instance_get(mox.IgnoreArg(),
                        mox.IgnoreArg()).AndRaise(exception.InstanceNotFound)
        self.mox.ReplayAll()

        manager = self.FakeNetworkManager()
        instance_id = 99999  # not exist
        self.assertRaises(exception.InstanceNotFound,
                          manager.remove_fixed_ip_from_instance,
                          None, instance_id, '10.0.0.1')

    def test_validate_cidrs(self):
        manager = self.FakeNetworkManager()
        nets = manager.create_networks(None, 'fake', '192.168.0.0/24',
                                       False, 1, 256, None, None, None,
                                       None)
        self.assertEqual(1, len(nets))
        cidrs = [str(net['cidr']) for net in nets]
        self.assertTrue('192.168.0.0/24' in cidrs)

    def test_validate_cidrs_split_exact_in_half(self):
        manager = self.FakeNetworkManager()
        nets = manager.create_networks(None, 'fake', '192.168.0.0/24',
                                       False, 2, 128, None, None, None,
                                       None)
        self.assertEqual(2, len(nets))
        cidrs = [str(net['cidr']) for net in nets]
        self.assertTrue('192.168.0.0/25' in cidrs)
        self.assertTrue('192.168.0.128/25' in cidrs)

    def test_validate_cidrs_split_cidr_in_use_middle_of_range(self):
        manager = self.FakeNetworkManager()
        self.mox.StubOutWithMock(manager.db, 'network_get_all')
        ctxt = mox.IgnoreArg()
        manager.db.network_get_all(ctxt).AndReturn([{'id': 1,
                                     'cidr': '192.168.2.0/24'}])
        self.mox.ReplayAll()
        nets = manager.create_networks(None, 'fake', '192.168.0.0/16',
                                       False, 4, 256, None, None, None,
                                       None)
        self.assertEqual(4, len(nets))
        cidrs = [str(net['cidr']) for net in nets]
        exp_cidrs = ['192.168.0.0/24', '192.168.1.0/24', '192.168.3.0/24',
                     '192.168.4.0/24']
        for exp_cidr in exp_cidrs:
            self.assertTrue(exp_cidr in cidrs)
        self.assertFalse('192.168.2.0/24' in cidrs)

    def test_validate_cidrs_smaller_subnet_in_use(self):
        manager = self.FakeNetworkManager()
        self.mox.StubOutWithMock(manager.db, 'network_get_all')
        ctxt = mox.IgnoreArg()
        manager.db.network_get_all(ctxt).AndReturn([{'id': 1,
                                     'cidr': '192.168.2.9/25'}])
        self.mox.ReplayAll()
        # ValueError: requested cidr (192.168.2.0/24) conflicts with
        #             existing smaller cidr
        args = (None, 'fake', '192.168.2.0/24', False, 1, 256, None, None,
                None, None)
        self.assertRaises(ValueError, manager.create_networks, *args)

    def test_validate_cidrs_split_smaller_cidr_in_use(self):
        manager = self.FakeNetworkManager()
        self.mox.StubOutWithMock(manager.db, 'network_get_all')
        ctxt = mox.IgnoreArg()
        manager.db.network_get_all(ctxt).AndReturn([{'id': 1,
                                     'cidr': '192.168.2.0/25'}])
        self.mox.ReplayAll()
        nets = manager.create_networks(None, 'fake', '192.168.0.0/16',
                                       False, 4, 256, None, None, None, None)
        self.assertEqual(4, len(nets))
        cidrs = [str(net['cidr']) for net in nets]
        exp_cidrs = ['192.168.0.0/24', '192.168.1.0/24', '192.168.3.0/24',
                     '192.168.4.0/24']
        for exp_cidr in exp_cidrs:
            self.assertTrue(exp_cidr in cidrs)
        self.assertFalse('192.168.2.0/24' in cidrs)

    def test_validate_cidrs_split_smaller_cidr_in_use2(self):
        manager = self.FakeNetworkManager()
        self.mox.StubOutWithMock(manager.db, 'network_get_all')
        ctxt = mox.IgnoreArg()
        manager.db.network_get_all(ctxt).AndReturn([{'id': 1,
                                     'cidr': '192.168.2.9/29'}])
        self.mox.ReplayAll()
        nets = manager.create_networks(None, 'fake', '192.168.2.0/24',
                                       False, 3, 32, None, None, None, None)
        self.assertEqual(3, len(nets))
        cidrs = [str(net['cidr']) for net in nets]
        exp_cidrs = ['192.168.2.32/27', '192.168.2.64/27', '192.168.2.96/27']
        for exp_cidr in exp_cidrs:
            self.assertTrue(exp_cidr in cidrs)
        self.assertFalse('192.168.2.0/27' in cidrs)

    def test_validate_cidrs_split_all_in_use(self):
        manager = self.FakeNetworkManager()
        self.mox.StubOutWithMock(manager.db, 'network_get_all')
        ctxt = mox.IgnoreArg()
        in_use = [{'id': 1, 'cidr': '192.168.2.9/29'},
                  {'id': 2, 'cidr': '192.168.2.64/26'},
                  {'id': 3, 'cidr': '192.168.2.128/26'}]
        manager.db.network_get_all(ctxt).AndReturn(in_use)
        self.mox.ReplayAll()
        args = (None, 'fake', '192.168.2.0/24', False, 3, 64, None, None,
                None, None)
        # ValueError: Not enough subnets avail to satisfy requested num_
        #             networks - some subnets in requested range already
        #             in use
        self.assertRaises(ValueError, manager.create_networks, *args)

    def test_validate_cidrs_one_in_use(self):
        manager = self.FakeNetworkManager()
        args = (None, 'fake', '192.168.0.0/24', False, 2, 256, None, None,
                None, None)
        # ValueError: network_size * num_networks exceeds cidr size
        self.assertRaises(ValueError, manager.create_networks, *args)

    def test_validate_cidrs_already_used(self):
        manager = self.FakeNetworkManager()
        self.mox.StubOutWithMock(manager.db, 'network_get_all')
        ctxt = mox.IgnoreArg()
        manager.db.network_get_all(ctxt).AndReturn([{'id': 1,
                                     'cidr': '192.168.0.0/24'}])
        self.mox.ReplayAll()
        # ValueError: cidr already in use
        args = (None, 'fake', '192.168.0.0/24', False, 1, 256, None, None,
                None, None)
        self.assertRaises(ValueError, manager.create_networks, *args)

    def test_validate_cidrs_too_many(self):
        manager = self.FakeNetworkManager()
        args = (None, 'fake', '192.168.0.0/24', False, 200, 256, None, None,
                None, None)
        # ValueError: Not enough subnets avail to satisfy requested
        #             num_networks
        self.assertRaises(ValueError, manager.create_networks, *args)

    def test_validate_cidrs_split_partial(self):
        manager = self.FakeNetworkManager()
        nets = manager.create_networks(None, 'fake', '192.168.0.0/16',
                                       False, 2, 256, None, None, None, None)
        returned_cidrs = [str(net['cidr']) for net in nets]
        self.assertTrue('192.168.0.0/24' in returned_cidrs)
        self.assertTrue('192.168.1.0/24' in returned_cidrs)

    def test_validate_cidrs_conflict_existing_supernet(self):
        manager = self.FakeNetworkManager()
        self.mox.StubOutWithMock(manager.db, 'network_get_all')
        ctxt = mox.IgnoreArg()
        fakecidr = [{'id': 1, 'cidr': '192.168.0.0/8'}]
        manager.db.network_get_all(ctxt).AndReturn(fakecidr)
        self.mox.ReplayAll()
        args = (None, 'fake', '192.168.0.0/24', False, 1, 256, None, None,
                None, None)
        # ValueError: requested cidr (192.168.0.0/24) conflicts
        #             with existing supernet
        self.assertRaises(ValueError, manager.create_networks, *args)

    def test_create_networks(self):
        cidr = '192.168.0.0/24'
        manager = self.FakeNetworkManager()
        self.stubs.Set(manager, '_create_fixed_ips',
                                self.fake_create_fixed_ips)
        args = [None, 'foo', cidr, None, 1, 256, 'fd00::/48', None, None,
                None]
        self.assertTrue(manager.create_networks(*args))

    def test_create_networks_cidr_already_used(self):
        manager = self.FakeNetworkManager()
        self.mox.StubOutWithMock(manager.db, 'network_get_all')
        ctxt = mox.IgnoreArg()
        fakecidr = [{'id': 1, 'cidr': '192.168.0.0/24'}]
        manager.db.network_get_all(ctxt).AndReturn(fakecidr)
        self.mox.ReplayAll()
        args = [None, 'foo', '192.168.0.0/24', None, 1, 256,
                 'fd00::/48', None, None, None]
        self.assertRaises(ValueError, manager.create_networks, *args)

    def test_create_networks_many(self):
        cidr = '192.168.0.0/16'
        manager = self.FakeNetworkManager()
        self.stubs.Set(manager, '_create_fixed_ips',
                                self.fake_create_fixed_ips)
        args = [None, 'foo', cidr, None, 10, 256, 'fd00::/48', None, None,
                None]
        self.assertTrue(manager.create_networks(*args))

    @attr(kind='small')
    def test_create_networks_param_not_cidr_and_not_subnet_v4(self):
        """
        net['cidr'], net['netmask'], net['gateway'], net['broadcast']
        and net['dhcp_start'] are not set
        """
        self._context = None
        self._values = None

        def fake_network_create_safe(context, values):
            self._context = context
            self._values = values
            fakenet = dict(values)
            fakenet['id'] = 999
            return fakenet

        manager = self.FakeNetworkManager()
        self.stubs.Set(manager.db, 'network_create_safe',
                                fake_network_create_safe)
        self.stubs.Set(manager, '_create_fixed_ips',
                                self.fake_create_fixed_ips)
        args = [None, 'foo', None, None, 1, 256, 'fd00::/48', None, None,
                None]
        self.assertTrue(manager.create_networks(*args))
        self.assertTrue(self._values.get('cidr') is None)
        self.assertTrue(self._values.get('netmask') is None)
        self.assertTrue(self._values.get('gateway') is None)
        self.assertTrue(self._values.get('broadcast') is None)
        self.assertTrue(self._values.get('dhcp_start') is None)

    @attr(kind='small')
    def test_create_networks_param_cidr_v6_and_subnet_v6_and_gateway_v6(self):
        """
        net['gateway_v6'] is set to gateway_v6
        """
        self._context = None
        self._values = None

        def fake_network_create_safe(context, values):
            self._context = context
            self._values = values
            fakenet = dict(values)
            fakenet['id'] = 999
            return fakenet

        cidr = '192.168.0.0/24'
        gateway_v6 = 'gatewayv6'
        manager = self.FakeNetworkManager()
        self.stubs.Set(manager.db, 'network_create_safe',
                                fake_network_create_safe)
        self.stubs.Set(manager, '_create_fixed_ips',
                                self.fake_create_fixed_ips)
        args = [None, 'foo', cidr, None, 1, 256, 'fd00::/48', gateway_v6, None,
                None]
        self.assertTrue(manager.create_networks(*args))
        self.assertEqual(gateway_v6, self._values['gateway_v6'])


class FlatDHCPNetworkTestCase(test.TestCase):
    def setUp(self):
        super(FlatDHCPNetworkTestCase, self).setUp()
        self.network = network_manager.FlatDHCPManager(host=HOST)
        self.network.db = db
        self.context = context.RequestContext('testuser', 'testproject',
                                              is_admin=False)

    @attr(kind='small')
    def test_init_host(self):
        """
        driver.metadata_forward is called
        """
        self._is_called = False

        def stub_metadata_forward():
            self._is_called = True

        self.stubs.Set(self.network.driver, 'metadata_forward',
                       stub_metadata_forward)

        self.network.init_host()
        self.assertTrue(self._is_called)

    @attr(kind='small')
    def test_init_host_ex_driver_init_host(self):
        """
        ProcessExecutionError is raised
        """
        def stub_init_host():
            raise exception.ProcessExecutionError()

        self.stubs.Set(self.network.driver, 'init_host', stub_init_host)

        self.assertRaises(exception.ProcessExecutionError,
                          self.network.init_host)

    @attr(kind='small')
    def test_init_host_ex_driver_ensure_metadata_ip(self):
        """
        ProcessExecutionError is raised
        """
        def stub_ensure_metadata_ip():
            raise exception.ProcessExecutionError()

        self.stubs.Set(self.network.driver, 'ensure_metadata_ip',
                       stub_ensure_metadata_ip)

        self.assertRaises(exception.ProcessExecutionError,
                          self.network.init_host)

    @attr(kind='small')
    def test_init_host_ex_driver_metadata_forward(self):
        """
        ProcessExecutionError is raised
        """
        def stub_metadata_forward():
            raise exception.ProcessExecutionError()

        self.stubs.Set(self.network.driver, 'metadata_forward',
                       stub_metadata_forward)

        self.assertRaises(exception.ProcessExecutionError,
                          self.network.init_host)

    @attr(kind='small')
    def test_allocate_fixed_ip_cfg_fake_network(self):
        """
        driver.update_dhcp is not called
        """
        self._is_called = False

        def stub_update_dhcp(context, dev, network_ref):
            self._is_called = True

        self.mox.StubOutWithMock(db, 'fixed_ip_associate_pool')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.stubs.Set(self.network.driver, 'update_dhcp', stub_update_dhcp)
        db.fixed_ip_associate_pool(mox.IgnoreArg(),
                                   mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        kwargs = {}
        res = self.network.allocate_fixed_ip(
                        self.context, 1, networks[0], **kwargs)
        self.assertEqual('192.168.0.101', res)
        self.assertFalse(self._is_called)

    @attr(kind='small')
    def test_allocate_fixed_ip_cfg_not_fake_network_and_not_use_ipv6(self):
        """
        driver.update_dhcp is called
        """
        self.flags(fake_network=False)
        self.flags(use_ipv6=False)

        self._context = None
        self._dev = None
        self._network_ref = None

        def stub_update_dhcp(context, dev, network_ref):
            self._context = context
            self._dev = dev
            self._network_ref = network_ref

        self.mox.StubOutWithMock(db, 'fixed_ip_associate_pool')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(self.network.driver, 'plug')
        self.mox.StubOutWithMock(self.network.driver,
                                 'initialize_gateway_device')
        self.stubs.Set(self.network.driver, 'update_dhcp', stub_update_dhcp)
        db.fixed_ip_associate_pool(mox.IgnoreArg(),
                                   mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        dev = networks[0]['bridge']
        self.network.driver.plug(mox.IgnoreArg(),
                                 mox.IgnoreArg()).AndReturn(dev)
        self.network.driver.initialize_gateway_device(
                                    mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        network = networks[0]
        kwargs = {}
        res = self.network.allocate_fixed_ip(
                        self.context, 1, network, **kwargs)
        self.assertEqual('192.168.0.101', res)
        self.assertTrue(self._context)
        self.assertEqual(dev, self._dev)
        self.assertEqual(network, self._network_ref)

    @attr(kind='small')
    def test_allocate_fixed_ip_cfg_not_fake_network_and_use_ipv6(self):
        """
        db.network_update is called
        """
        self.flags(fake_network=False)
        self.flags(use_ipv6=True)

        self._context = None
        self._network_id = None
        self._values = None

        def stub_network_update(context, network_id, values):
            self._context = context
            self._network_id = network_id
            self._values = values

        self.mox.StubOutWithMock(db, 'fixed_ip_associate_pool')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(self.network.driver, 'plug')
        self.mox.StubOutWithMock(self.network.driver,
                                 'initialize_gateway_device')
        self.mox.StubOutWithMock(self.network.driver, 'update_dhcp')
        self.mox.StubOutWithMock(self.network.driver, 'update_ra')
        self.mox.StubOutWithMock(utils, 'get_my_linklocal')
        self.stubs.Set(db, 'network_update', stub_network_update)
        db.fixed_ip_associate_pool(mox.IgnoreArg(),
                                   mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.network.driver.plug(mox.IgnoreArg(), mox.IgnoreArg())
        self.network.driver.initialize_gateway_device(
                        mox.IgnoreArg(), mox.IgnoreArg())
        self.network.driver.update_dhcp(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.network.driver.update_ra(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        gateway = 'gatewayv6'
        utils.get_my_linklocal(mox.IgnoreArg()).AndReturn(gateway)
        self.mox.ReplayAll()

        network = networks[0]
        kwargs = {}
        res = self.network.allocate_fixed_ip(
                        self.context, 1, network, **kwargs)
        self.assertEqual('192.168.0.101', res)
        self.assertTrue(self._context)
        self.assertEqual(network['id'], self._network_id)
        self.assertEqual(gateway, self._values['gateway_v6'])

    @attr(kind='small')
    def test_allocate_fixed_ip_ex_driver_plug(self):
        """
        ProcessExecutionError is raised
        """
        self.flags(fake_network=False)
        self.flags(use_ipv6=True)

        def stub_plug(network, mac_address):
            raise exception.ProcessExecutionError()

        self.mox.StubOutWithMock(db, 'fixed_ip_associate_pool')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.stubs.Set(self.network.driver, 'plug', stub_plug)
        db.fixed_ip_associate_pool(mox.IgnoreArg(),
                                   mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        network = networks[0]
        kwargs = {}
        self.assertRaises(exception.ProcessExecutionError,
                          self.network.allocate_fixed_ip,
                          self.context, 1, network, **kwargs)

    @attr(kind='small')
    def test_allocate_fixed_ip_ex_driver_initialize_gateway_device(self):
        """
        driver.unbind_floating_ip() is called for cleanup
        """
        self.flags(fake_network=False)
        self.flags(use_ipv6=True)

        self._network = None

        def stub_initialize_gateway_device(dev, network_ref):
            raise exception.ProcessExecutionError()

        def stub_unplug(network):
            self._network = network

        self.mox.StubOutWithMock(db, 'fixed_ip_associate_pool')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(self.network.driver, 'plug')
        self.stubs.Set(self.network.driver,
                       'initialize_gateway_device',
                       stub_initialize_gateway_device)
        self.stubs.Set(self.network.driver, 'unplug', stub_unplug)
        db.fixed_ip_associate_pool(mox.IgnoreArg(),
                                   mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.network.driver.plug(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        network = networks[0]
        kwargs = {}
        self.assertRaises(exception.ProcessExecutionError,
                          self.network.allocate_fixed_ip,
                          self.context, 1, network, **kwargs)
        self.assertEqual(network, self._network)

    @attr(kind='small')
    def test_allocate_fixed_ip_ex_driver_update_dhcp(self):
        """
        driver.unbind_floating_ip() is called for cleanup
        """
        self.flags(fake_network=False)
        self.flags(use_ipv6=True)

        self._network = None

        def stub_update_dhcp(context, dev, network_ref):
            raise exception.ProcessExecutionError()

        def stub_unplug(network):
            self._network = network

        self.mox.StubOutWithMock(db, 'fixed_ip_associate_pool')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(self.network.driver, 'plug')
        self.mox.StubOutWithMock(self.network.driver,
                                 'initialize_gateway_device')
        self.stubs.Set(self.network.driver, 'update_dhcp', stub_update_dhcp)
        self.stubs.Set(self.network.driver, 'unplug', stub_unplug)
        db.fixed_ip_associate_pool(mox.IgnoreArg(),
                                   mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.network.driver.plug(mox.IgnoreArg(), mox.IgnoreArg())
        self.network.driver.initialize_gateway_device(
                                        mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        network = networks[0]
        kwargs = {}
        self.assertRaises(exception.ProcessExecutionError,
                          self.network.allocate_fixed_ip,
                          self.context, 1, network, **kwargs)
        self.assertEqual(network, self._network)

    @attr(kind='small')
    def test_allocate_fixed_ip_ex_driver_update_ra(self):
        """
        driver.release_dhcp() and
        driver.unbind_floating_ip() are called for cleanup
        """
        self.flags(fake_network=False)
        self.flags(use_ipv6=True)

        self._network = None
        self._dev = None
        self._address = None
        self._mac_address = None

        def stub_update_ra(context, dev, network_ref):
            raise exception.ProcessExecutionError()

        def stub_release_dhcp(dev, address, mac_address):
            self._dev = dev
            self._address = address
            self._mac_address = mac_address

        def stub_unplug(network):
            self._network = network

        self.mox.StubOutWithMock(db, 'fixed_ip_associate_pool')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(self.network, 'generate_mac_address')
        self.mox.StubOutWithMock(self.network.driver, 'plug')
        self.mox.StubOutWithMock(self.network.driver,
                                 'initialize_gateway_device')
        self.mox.StubOutWithMock(self.network.driver, 'update_dhcp')
        self.stubs.Set(self.network.driver, 'update_ra', stub_update_ra)
        self.stubs.Set(self.network.driver, 'release_dhcp', stub_release_dhcp)
        self.stubs.Set(self.network.driver, 'unplug', stub_unplug)
        db.fixed_ip_associate_pool(mox.IgnoreArg(),
                                   mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        mac_address = '00-00-00-00-00-00-00-00'
        self.network.generate_mac_address().AndReturn(mac_address)
        dev = 'dev'
        self.network.driver.plug(mox.IgnoreArg(),
                                 mox.IgnoreArg()).AndReturn(dev)
        self.network.driver.initialize_gateway_device(
                                        mox.IgnoreArg(), mox.IgnoreArg())
        self.network.driver.update_dhcp(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        network = networks[0]
        kwargs = {}
        self.assertRaises(exception.ProcessExecutionError,
                          self.network.allocate_fixed_ip,
                          self.context, 1, network, **kwargs)
        self.assertEqual(dev, self._dev)
        self.assertEqual(network['dhcp_server'], self._address)
        self.assertEqual(mac_address, self._mac_address)
        self.assertEqual(network, self._network)

    @attr(kind='small')
    def test_allocate_fixed_ip_ex_utils_get_my_linklocal(self):
        """
        driver.release_dhcp() and
        driver.unbind_floating_ip() are called for cleanup
        """
        self.flags(fake_network=False)
        self.flags(use_ipv6=True)

        self._network = None
        self._dev = None
        self._address = None
        self._mac_address = None

        def stub_get_my_linklocal(interface):
            raise exception.ProcessExecutionError()

        def stub_release_dhcp(dev, address, mac_address):
            self._dev = dev
            self._address = address
            self._mac_address = mac_address

        def stub_unplug(network):
            self._network = network

        self.mox.StubOutWithMock(db, 'fixed_ip_associate_pool')
        self.mox.StubOutWithMock(db, 'instance_get')
        self.mox.StubOutWithMock(
                        db, 'virtual_interface_get_by_instance_and_network')
        self.mox.StubOutWithMock(db, 'fixed_ip_update')
        self.mox.StubOutWithMock(self.network, 'generate_mac_address')
        self.mox.StubOutWithMock(self.network.driver, 'plug')
        self.mox.StubOutWithMock(self.network.driver,
                                 'initialize_gateway_device')
        self.mox.StubOutWithMock(self.network.driver, 'update_dhcp')
        self.mox.StubOutWithMock(self.network.driver, 'update_ra')
        self.stubs.Set(utils, 'get_my_linklocal', stub_get_my_linklocal)
        self.stubs.Set(self.network.driver, 'release_dhcp', stub_release_dhcp)
        self.stubs.Set(self.network.driver, 'unplug', stub_unplug)
        db.fixed_ip_associate_pool(mox.IgnoreArg(),
                                   mox.IgnoreArg(),
                                   mox.IgnoreArg()).AndReturn('192.168.0.101')
        db.instance_get(mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'security_groups': [{'id': 0}]})
        db.virtual_interface_get_by_instance_and_network(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                        AndReturn({'id': 0})
        db.fixed_ip_update(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        mac_address = '00-00-00-00-00-00-00-00'
        self.network.generate_mac_address().AndReturn(mac_address)
        dev = 'dev'
        self.network.driver.plug(mox.IgnoreArg(),
                                 mox.IgnoreArg()).AndReturn(dev)
        self.network.driver.initialize_gateway_device(
                                        mox.IgnoreArg(), mox.IgnoreArg())
        self.network.driver.update_dhcp(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.network.driver.update_ra(
                        mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        network = networks[0]
        kwargs = {}
        self.assertRaises(exception.ProcessExecutionError,
                          self.network.allocate_fixed_ip,
                          self.context, 1, network, **kwargs)
        self.assertEqual(dev, self._dev)
        self.assertEqual(network['dhcp_server'], self._address)
        self.assertEqual(mac_address, self._mac_address)
        self.assertEqual(network, self._network)
