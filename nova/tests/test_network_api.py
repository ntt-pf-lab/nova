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
Tests For nova.network.api
"""

from nova import context
from nova import exception
from nova import flags
from nova import rpc
from nova import test
from nova.network import api
from nose.plugins.attrib import attr
from nose.plugins.skip import SkipTest

FLAGS = flags.FLAGS

instances = [{'id': 1,
              'project_id': 'fake',
              'host': 'testhost',
              'instance_type_id': 1}]

networks = [{'id': 1,
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
             'host': 'testhost',
             'project_id': 'fake_project',
             'vpn_public_address': '192.168.0.2'}]

fixed_ips = [{'id': 1,
              'network_id': 1,
              'address': '192.168.0.100',
              'instance_id': 1,
              'allocated': False,
              'virtual_interface_id': 1,
              'floating_ips': []},
             {'id': 2,
              'network_id': 2,
              'address': '192.168.1.100',
              'instance_id': 2,
              'allocated': False,
              'virtual_interface_id': 2,
              'floating_ips': []}]

floating_ips = [{'id': 1,
                 'address': '192.168.0.1',
                 'fixed_ip_id': 1,
                 'project_id': 'fake',
                 'auto_assigned': False}]

virtual_interfaces = [{'id': 1,
                       'address': 'DE:AD:BE:EF:00:00',
                       'uuid': '00000000-0000-0000-0000-0000000000000000',
                       'network_id': 1,
                       'instance_id': 1}]


class APITestCase(test.TestCase):
    """Test for nova.network.api.API. """
    cast = None
    call = None

    def setUp(self):
        super(APITestCase, self).setUp()
        self.api = api.API()
        #self.db = db
        self.context = context.get_admin_context()

        def fake_cast(context, topic, content):
            if self.cast:
                return self.cast(topic, content)

        def fake_call(context, topic, content):
            if self.call:
                return self.call(topic, content)

        self.stubs.Set(rpc, 'cast', fake_cast)
        self.stubs.Set(rpc, 'call', fake_call)

    @attr(kind='small')
    def test_get_floating_ip(self):
        """Test for nova.network.api.API.get_floating_ip. """
        def fake_floating_ip_get(context, floating_ip_id):
            return floating_ips[0]

        self.stubs.Set(self.api.db, "floating_ip_get",
                                    fake_floating_ip_get)

        floating_ip_id = 1
        ref = self.api.get_floating_ip(self.context, floating_ip_id)
        self.assertTrue(isinstance(ref, dict))
        self.assertEqual(floating_ips[0]['id'], ref['id'])

    @attr(kind='small')
    def test_get_floating_ip_param_floating_ip_not_found(self):
        raise SkipTest("Parameter check is not implemented.")
        """
        ApiError is raised
        """
        def fake_floating_ip_get(context, floating_ip_id):
            return exception.FloatingIpNotFound(id=floating_ip_id)

        self.stubs.Set(self.api.db, "floating_ip_get",
                                    fake_floating_ip_get)

        floating_ip_id = 99999
        self.assertRaises(exception.ApiError,
                          self.api.get_floating_ip,
                          self.context, floating_ip_id)

    @attr(kind='small')
    def test_get_floating_ip_by_ip(self):
        """Test for nova.network.api.API.get_floating_ip_by_ip. """
        def fake_floating_ip_get_by_address(context, address):
            return floating_ips[0]

        self.stubs.Set(self.api.db, "floating_ip_get_by_address",
                                    fake_floating_ip_get_by_address)

        address = '192.168.0.1'
        ref = self.api.get_floating_ip_by_ip(self.context, address)
        self.assertTrue(isinstance(ref, dict))
        self.assertEqual(floating_ips[0]['id'], ref['id'])

    @attr(kind='small')
    def test_list_floating_ips(self):
        """Test for nova.network.api.API.list_floating_ips. """
        def fake_floating_ip_get_all_by_project(context, project_id):
            return floating_ips

        self.stubs.Set(self.api.db, "floating_ip_get_all_by_project",
                                    fake_floating_ip_get_all_by_project)

        ref = self.api.list_floating_ips(self.context)
        self.assertEqual(floating_ips, ref)

    @attr(kind='small')
    def test_get_vifs_by_instance(self):
        """Test for nova.network.api.API.get_vifs_by_instance. """
        def fake_virtual_interface_get_by_instance(context, instance_id):
            return virtual_interfaces

        self.stubs.Set(self.api.db, "virtual_interface_get_by_instance",
                                    fake_virtual_interface_get_by_instance)

        instance_id = 1
        ref = self.api.get_vifs_by_instance(self.context, instance_id)
        self.assertEqual(virtual_interfaces, ref)

    @attr(kind='small')
    def test_get_vifs_by_instance_param_instance_not_found(self):
        raise SkipTest("Parameter check is not implemented.")
        """
        ApiError is raised
        """
        def fake_instance_get(context, instance_id):
            return exception.InstanceNotFound(instance_id=instance_id)

        self.stubs.Set(self.api.db, "instance_get",
                                    fake_instance_get)

        instance_id = 99999
        self.assertRaises(exception.ApiError,
                          self.api.get_vifs_by_instance,
                          self.context, instance_id)

    @attr(kind='small')
    def test_allocate_floating_ip(self):
        """Test for nova.network.api.API.allocate_floating_ip. """
        def call(topic, content):
            self.assertEqual(FLAGS.network_topic, topic)
            self.assertEqual('allocate_floating_ip', content['method'])
            self.assertEqual(None, content['args']['project_id'])
            return '192.168.0.1'

        self.call = call

        ref = self.api.allocate_floating_ip(self.context)
        self.assertEqual('192.168.0.1', ref)

    @attr(kind='small')
    def test_release_floating_ip(self):
        """Test for nova.network.api.API.release_floating_ip. """
        floating_ip_ref = dict(floating_ips[0])
        floating_ip_ref['fixed_ip'] = None

        def fake_floating_ip_get_by_address(context, address):
            return floating_ip_ref

        self.stubs.Set(self.api.db, "floating_ip_get_by_address",
                                    fake_floating_ip_get_by_address)

        def cast(topic, content):
            self.assertEqual(FLAGS.network_topic, topic)
            self.assertEqual('deallocate_floating_ip', content['method'])
            self.assertEqual(floating_ip_ref['address'],
                             content['args']['floating_address'])

        self.cast = cast

        address = '192.168.0.1'
        affect_auto_assigned = True
        self.api.release_floating_ip(self.context,
                                     address,
                                     affect_auto_assigned=affect_auto_assigned)

    @attr(kind='small')
    def test_release_floating_ip_param_fixed_ip_is_not_none(self):
        """
        ApiError is raised when floating_ip['fixed_ip'] is not None.
        """
        floating_ip_ref = dict(floating_ips[0])
        floating_ip_ref['fixed_ip'] = fixed_ips[0]

        def fake_floating_ip_get_by_address(context, address):
            return floating_ip_ref

        self.stubs.Set(self.api.db, "floating_ip_get_by_address",
                                    fake_floating_ip_get_by_address)

        address = '192.168.0.1'
        affect_auto_assigned = True
        self.assertRaises(exception.ApiError,
                          self.api.release_floating_ip,
                          self.context, address,
                          affect_auto_assigned=affect_auto_assigned)

    @attr(kind='small')
    def test_release_floating_ip_param_not_affect_and_auto_assigned(self):
        floating_ip_ref = dict(floating_ips[0])
        floating_ip_ref['fixed_ip'] = None
        floating_ip_ref['auto_assigned'] = True

        def fake_floating_ip_get_by_address(context, address):
            return floating_ip_ref

        self.stubs.Set(self.api.db, "floating_ip_get_by_address",
                                    fake_floating_ip_get_by_address)

        address = '192.168.0.1'
        affect_auto_assigned = False
        ref = self.api.release_floating_ip(
                            self.context, address,
                            affect_auto_assigned=affect_auto_assigned)
        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_associate_floating_ip(self):
        """Test for nova.network.api.API.associate_floating_ip. """
        floating_ip_ref = dict(floating_ips[0])
        floating_ip_ref['fixed_ip'] = None

        def fake_floating_ip_get_by_address(context, address):
            return floating_ip_ref

        def fake_queue_get_for(context, topic, physical_node_id):
            return FLAGS.network_topic

        self.stubs.Set(self.api.db, "floating_ip_get_by_address",
                                    fake_floating_ip_get_by_address)
        self.stubs.Set(self.api.db, "queue_get_for", fake_queue_get_for)

        def cast(topic, content):
            self.assertEqual(FLAGS.network_topic, topic)
            self.assertEqual('associate_floating_ip', content['method'])
            self.assertEqual(floating_ip_ref['address'],
                             content['args']['floating_address'])
            self.assertEqual(fixed_ip['address'],
                             content['args']['fixed_address'])

        self.cast = cast

        self.context.project_id = 'fake'
        floating_ip = '192.168.0.1'
        fixed_ip = dict(fixed_ips[0])
        fixed_ip['network'] = networks[0]
        affect_auto_assigned = True
        self.api.associate_floating_ip(
                    self.context, floating_ip, fixed_ip,
                    affect_auto_assigned=affect_auto_assigned)

    @attr(kind='small')
    def test_associate_floating_ip_param_fixed_ip_isinstance_basestring(self):
        """Test for nova.network.api.API.associate_floating_ip. """
        fixed_ip_ref = dict(fixed_ips[0])
        fixed_ip_ref['network'] = networks[0]

        def fake_fixed_ip_get_by_address(context, address):
            return fixed_ip_ref
        floating_ip_ref = dict(floating_ips[0])
        floating_ip_ref['fixed_ip'] = None

        def fake_floating_ip_get_by_address(context, address):
            return floating_ip_ref

        def fake_queue_get_for(context, topic, physical_node_id):
            return FLAGS.network_topic

        self.stubs.Set(self.api.db, "fixed_ip_get_by_address",
                                    fake_fixed_ip_get_by_address)
        self.stubs.Set(self.api.db, "floating_ip_get_by_address",
                                    fake_floating_ip_get_by_address)
        self.stubs.Set(self.api.db, "queue_get_for", fake_queue_get_for)

        def cast(topic, content):
            self.assertEqual(FLAGS.network_topic, topic)
            self.assertEqual('associate_floating_ip', content['method'])
            self.assertEqual(floating_ip_ref['address'],
                             content['args']['floating_address'])
            self.assertEqual(fixed_ip_ref['address'],
                             content['args']['fixed_address'])

        self.cast = cast

        self.context.project_id = 'fake'
        floating_ip = '192.168.0.1'
        fixed_ip = '10.0.0.1'
        affect_auto_assigned = True
        self.api.associate_floating_ip(
                        self.context, floating_ip, fixed_ip,
                        affect_auto_assigned=affect_auto_assigned)

    @attr(kind='small')
    def test_associate_floating_ip_param_not_affect_and_auto_assigned(self):
        """Test for nova.network.api.API.associate_floating_ip. """
        floating_ip_ref = dict(floating_ips[0])
        floating_ip_ref['auto_assigned'] = True

        def fake_floating_ip_get_by_address(context, address):
            return floating_ip_ref

        self.stubs.Set(self.api.db, "floating_ip_get_by_address",
                                    fake_floating_ip_get_by_address)
        floating_ip = '192.168.0.1'
        fixed_ip = dict(fixed_ips[0])
        affect_auto_assigned = False
        ref = self.api.associate_floating_ip(
                        self.context, floating_ip, fixed_ip,
                        affect_auto_assigned=affect_auto_assigned)
        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_associate_floating_ip_db_floating_ip_project_id_is_none(self):
        """Test for nova.network.api.API.associate_floating_ip. """
        floating_ip_ref = dict(floating_ips[0])
        floating_ip_ref['project_id'] = None

        def fake_floating_ip_get_by_address(context, address):
            return floating_ip_ref

        self.stubs.Set(self.api.db, "floating_ip_get_by_address",
                                    fake_floating_ip_get_by_address)

        floating_ip = '192.168.0.1'
        fixed_ip = dict(fixed_ips[0])
        affect_auto_assigned = True
        self.assertRaises(exception.ApiError,
                          self.api.associate_floating_ip,
                          self.context, floating_ip, fixed_ip,
                          affect_auto_assigned=affect_auto_assigned)

    @attr(kind='small')
    def test_associate_floating_ip_db_proj_id_not_equal_to_ctx_proj_id(self):
        """Test for nova.network.api.API.associate_floating_ip. """
        floating_ip_ref = dict(floating_ips[0])
        floating_ip_ref['fixed_ip'] = None

        def fake_floating_ip_get_by_address(context, address):
            return floating_ip_ref

        self.stubs.Set(self.api.db, "floating_ip_get_by_address",
                                    fake_floating_ip_get_by_address)

        floating_ip = '192.168.0.1'
        fixed_ip = dict(fixed_ips[0])
        affect_auto_assigned = True
        self.assertRaises(exception.ApiError,
                          self.api.associate_floating_ip,
                          self.context, floating_ip, fixed_ip,
                          affect_auto_assigned=affect_auto_assigned)

    @attr(kind='small')
    def test_associate_floating_ip_db_float_ip_fixed_ip_is_not_fixed_ip(self):
        """Test for nova.network.api.API.associate_floating_ip. """
        floating_ip_ref = dict(floating_ips[0])
        floating_ip_ref['fixed_ip'] = fixed_ips[1]

        def fake_floating_ip_get_by_address(context, address):
            return floating_ip_ref

        def fake_disassociate_floating_ip(context, address,
                                          affect_auto_assigned=False):
            self.assertEqual(self.context, context)
            self.assertEqual(floating_ip_ref['address'], address)
            self.assertEqual(False, affect_auto_assigned)

        def fake_queue_get_for(context, topic, physical_node_id):
            return FLAGS.network_topic

        self.stubs.Set(self.api.db, "floating_ip_get_by_address",
                                    fake_floating_ip_get_by_address)
        self.stubs.Set(self.api, "disassociate_floating_ip",
                                    fake_disassociate_floating_ip)
        self.stubs.Set(self.api.db, "queue_get_for", fake_queue_get_for)

        def cast(topic, content):
            self.assertEqual(FLAGS.network_topic, topic)
            self.assertEqual('associate_floating_ip', content['method'])
            self.assertEqual(floating_ip_ref['address'],
                             content['args']['floating_address'])
            self.assertEqual(fixed_ip['address'],
                             content['args']['fixed_address'])

        self.cast = cast

        self.context.project_id = 'fake'
        floating_ip = '192.168.0.1'
        fixed_ip = dict(fixed_ips[0])
        fixed_ip['network'] = networks[0]
        affect_auto_assigned = True
        self.api.associate_floating_ip(
                            self.context, floating_ip, fixed_ip,
                            affect_auto_assigned=affect_auto_assigned)

    @attr(kind='small')
    def test_associate_floating_ip_db_fixed_ip_network_multi_host(self):
        """Test for nova.network.api.API.associate_floating_ip. """
        floating_ip_ref = dict(floating_ips[0])
        floating_ip_ref['fixed_ip'] = None

        def fake_floating_ip_get_by_address(context, address):
            return floating_ip_ref

        def fake_queue_get_for(context, topic, physical_node_id):
            self.assertEqual(fixed_ip['instance']['host'], physical_node_id)
            return FLAGS.network_topic

        self.stubs.Set(self.api.db, "floating_ip_get_by_address",
                                    fake_floating_ip_get_by_address)
        self.stubs.Set(self.api.db, "queue_get_for", fake_queue_get_for)

        def cast(topic, content):
            self.assertEqual(FLAGS.network_topic, topic)
            self.assertEqual('associate_floating_ip', content['method'])
            self.assertEqual(floating_ip_ref['address'],
                             content['args']['floating_address'])
            self.assertEqual(fixed_ip['address'],
                             content['args']['fixed_address'])

        self.cast = cast

        self.context.project_id = 'fake'
        floating_ip = '192.168.0.1'
        fixed_ip = dict(fixed_ips[0])
        network = dict(networks[0])
        network['multi_host'] = True
        fixed_ip['network'] = network
        fixed_ip['instance'] = instances[0]
        affect_auto_assigned = True
        self.api.associate_floating_ip(
                            self.context, floating_ip, fixed_ip,
                            affect_auto_assigned=affect_auto_assigned)

    @attr(kind='small')
    def test_disassociate_floating_ip(self):
        """Test for nova.network.api.API.disassociate_floating_ip. """
        floating_ip_ref = dict(floating_ips[0])
        floating_ip_ref['fixed_ip'] = dict(fixed_ips[0])
        floating_ip_ref['fixed_ip']['network'] = networks[0]

        def fake_floating_ip_get_by_address(context, address):
            return floating_ip_ref

        def fake_queue_get_for(context, topic, physical_node_id):
            return FLAGS.network_topic

        self.stubs.Set(self.api.db, "floating_ip_get_by_address",
                                    fake_floating_ip_get_by_address)
        self.stubs.Set(self.api.db, "queue_get_for", fake_queue_get_for)

        def cast(topic, content):
            self.assertEqual(FLAGS.network_topic, topic)
            self.assertEqual('disassociate_floating_ip', content['method'])
            self.assertEqual(floating_ip_ref['address'],
                             content['args']['floating_address'])

        self.cast = cast

        address = '192.168.0.1'
        affect_auto_assigned = True
        self.api.disassociate_floating_ip(
                            self.context, address,
                            affect_auto_assigned=affect_auto_assigned)

    @attr(kind='small')
    def test_disassociate_floating_ip_param_not_affect_and_auto_assigned(self):
        """Test for nova.network.api.API.disassociate_floating_ip. """
        floating_ip_ref = dict(floating_ips[0])
        floating_ip_ref['auto_assigned'] = True

        def fake_floating_ip_get_by_address(context, address):
            return floating_ip_ref

        self.stubs.Set(self.api.db, "floating_ip_get_by_address",
                                    fake_floating_ip_get_by_address)

        address = '192.168.0.1'
        affect_auto_assigned = False
        self.api.disassociate_floating_ip(
                            self.context, address,
                            affect_auto_assigned=affect_auto_assigned)

    @attr(kind='small')
    def test_disassociate_floating_ip_db_floating_ip_fixed_ip_is_none(self):
        """Test for nova.network.api.API.disassociate_floating_ip. """
        floating_ip_ref = dict(floating_ips[0])
        floating_ip_ref['fixed_ip'] = None

        def fake_floating_ip_get_by_address(context, address):
            return floating_ip_ref

        self.stubs.Set(self.api.db, "floating_ip_get_by_address",
                                    fake_floating_ip_get_by_address)

        address = '192.168.0.1'
        affect_auto_assigned = True
        self.assertRaises(exception.ApiError,
                          self.api.disassociate_floating_ip,
                          self.context, address,
                          affect_auto_assigned=affect_auto_assigned)

    @attr(kind='small')
    def test_disassociate_floating_ip_db_floating_ip_fixed_ip_multi_host(self):
        """Test for nova.network.api.API.disassociate_floating_ip. """
        floating_ip_ref = dict(floating_ips[0])
        floating_ip_ref['fixed_ip'] = dict(fixed_ips[0])
        floating_ip_ref['fixed_ip']['network'] = dict(networks[0])
        floating_ip_ref['fixed_ip']['network']['multi_host'] = True
        floating_ip_ref['fixed_ip']['instance'] = instances[0]

        def fake_floating_ip_get_by_address(context, address):
            return floating_ip_ref

        def fake_queue_get_for(context, topic, physical_node_id):
            self.assertEqual(floating_ip_ref['fixed_ip']['instance']['host'],
                             physical_node_id)
            return FLAGS.network_topic

        self.stubs.Set(self.api.db, "floating_ip_get_by_address",
                                    fake_floating_ip_get_by_address)
        self.stubs.Set(self.api.db, "queue_get_for", fake_queue_get_for)

        def cast(topic, content):
            self.assertEqual(FLAGS.network_topic, topic)
            self.assertEqual('disassociate_floating_ip', content['method'])
            self.assertEqual(floating_ip_ref['address'],
                             content['args']['floating_address'])

        self.cast = cast

        address = '192.168.0.1'
        affect_auto_assigned = True
        self.api.disassociate_floating_ip(
                            self.context, address,
                            affect_auto_assigned=affect_auto_assigned)

    @attr(kind='small')
    def test_allocate_for_instance(self):
        """Test for nova.network.api.API.allocate_for_instance. """
        network_info = []

        def call(topic, content):
            self.assertEqual(FLAGS.network_topic, topic)
            self.assertEqual('allocate_for_instance', content['method'])
            args = content['args']
            self.assertEqual(instance['id'], args['instance_id'])
            self.assertEqual(instance['project_id'], args['project_id'])
            self.assertEqual(instance['host'], args['host'])
            self.assertEqual(instance['instance_type_id'],
                             args['instance_type_id'])
            return network_info

        self.call = call

        instance = instances[0]
        kwargs = {}
        kwargs['instance_id'] = 1
        kwargs['project_id'] = 'fake'
        kwargs['requested_networks'] = networks
        ref = self.api.allocate_for_instance(self.context, instance, **kwargs)
        self.assertEqual(network_info, ref)

    @attr(kind='small')
    def test_allocate_for_instance_param_instance_is_none(self):
        raise SkipTest("Parameter check is not implemented.")
        """
        ApiError is raised
        """
        instance = None
        kwargs = {}
        kwargs['instance_id'] = 1
        kwargs['project_id'] = 'fake'
        kwargs['requested_networks'] = networks
        self.assertRaises(exception.ApiError,
                          self.api.allocate_for_instance,
                          self.context, instance, **kwargs)

    @attr(kind='small')
    def test_allocate_for_instance_param_instance_not_found(self):
        raise SkipTest("Parameter check is not implemented.")
        """
        ApiError is raised
        """
        def fake_instance_get(context, instance_id):
            return exception.InstanceNotFound(instance_id=instance_id)

        self.stubs.Set(self.api.db, "instance_get",
                                    fake_instance_get)

        instance = {'id': 99999}
        kwargs = {}
        kwargs['instance_id'] = 1
        kwargs['project_id'] = 'fake'
        kwargs['requested_networks'] = networks
        self.assertRaises(exception.ApiError,
                          self.api.allocate_for_instance,
                          self.context, instance, **kwargs)

    @attr(kind='small')
    def test_deallocate_for_instance(self):
        """Test for nova.network.api.API.deallocate_for_instance. """
        def cast(topic, content):
            self.assertEqual(FLAGS.network_topic, topic)
            self.assertEqual('deallocate_for_instance', content['method'])
            args = content['args']
            self.assertEqual(instance['id'], args['instance_id'])
            self.assertEqual(instance['project_id'], args['project_id'])

        self.cast = cast

        instance = instances[0]
        kwargs = {}
        kwargs['instance_id'] = 1
        kwargs['fixed_ips'] = fixed_ips
        self.api.deallocate_for_instance(self.context, instance, **kwargs)

    @attr(kind='small')
    def test_deallocate_for_instance_param_instance_is_none(self):
        raise SkipTest("Parameter check is not implemented.")
        """
        ApiError is raised
        """
        instance = None
        kwargs = {}
        kwargs['instance_id'] = 1
        kwargs['fixed_ips'] = fixed_ips
        self.assertRaises(exception.ApiError,
                          self.api.deallocate_for_instance,
                          self.context, instance, **kwargs)

    @attr(kind='small')
    def test_deallocate_for_instance_param_instance_not_found(self):
        raise SkipTest("Parameter check is not implemented.")
        """
        ApiError is raised
        """
        def fake_instance_get(context, instance_id):
            return exception.InstanceNotFound(instance_id=instance_id)

        self.stubs.Set(self.api.db, "instance_get",
                                    fake_instance_get)

        instance = {'id': 99999}
        kwargs = {}
        kwargs['instance_id'] = 1
        kwargs['fixed_ips'] = fixed_ips
        self.assertRaises(exception.ApiError,
                          self.api.deallocate_for_instance,
                          self.context, instance, **kwargs)

    @attr(kind='small')
    def test_add_fixed_ip_to_instance(self):
        """Test for nova.network.api.API.add_fixed_ip_to_instance. """
        def cast(topic, content):
            self.assertEqual(FLAGS.network_topic, topic)
            self.assertEqual('add_fixed_ip_to_instance', content['method'])
            args = content['args']
            self.assertEqual(instance_id, args['instance_id'])
            self.assertEqual(host, args['host'])
            self.assertEqual(network_id, args['network_id'])

        self.cast = cast

        instance_id = 1
        host = 'testhost'
        network_id = 1
        self.api.add_fixed_ip_to_instance(
                            self.context, instance_id, host, network_id)

    @attr(kind='small')
    def test_remove_fixed_ip_from_instance(self):
        """Test for nova.network.api.API.remove_fixed_ip_from_instance. """
        def cast(topic, content):
            self.assertEqual(FLAGS.network_topic, topic)
            self.assertEqual('remove_fixed_ip_from_instance',
                             content['method'])
            args = content['args']
            self.assertEqual(instance_id, args['instance_id'])
            self.assertEqual(address, args['address'])

        self.cast = cast

        instance_id = 1
        address = '10.0.0.1'
        self.api.remove_fixed_ip_from_instance(
                            self.context, instance_id, address)

    @attr(kind='small')
    def test_remove_fixed_ip_from_instance_param_instance_not_found(self):
        raise SkipTest("Parameter check is not implemented.")
        """
        ApiError is raised
        """
        def fake_instance_get(context, instance_id):
            return exception.InstanceNotFound(instance_id=instance_id)

        self.stubs.Set(self.api.db, "instance_get",
                                    fake_instance_get)

        instance_id = 99999
        address = '10.0.0.1'
        self.assertRaises(exception.ApiError,
                          self.api.remove_fixed_ip_from_instance,
                          self.context, instance_id, address)

    @attr(kind='small')
    def test_add_network_to_project(self):
        """Test for nova.network.api.API.add_network_to_project. """
        def cast(topic, content):
            self.assertEqual(FLAGS.network_topic, topic)
            self.assertEqual('add_network_to_project', content['method'])
            self.assertEqual(project_id, content['args']['project_id'])

        self.cast = cast

        project_id = 'fake'
        self.api.add_network_to_project(self.context, project_id)

    @attr(kind='small')
    def test_get_instance_nw_info(self):
        """Test for nova.network.api.API.get_instance_nw_info. """
        network_info = []

        def call(topic, content):
            self.assertEqual(FLAGS.network_topic, topic)
            self.assertEqual('get_instance_nw_info', content['method'])
            args = content['args']
            self.assertEqual(instance['id'], args['instance_id'])
            self.assertEqual(instance['instance_type_id'],
                             args['instance_type_id'])
            self.assertEqual(instance['host'], args['host'])
            return network_info

        self.call = call

        instance = instances[0]
        ref = self.api.get_instance_nw_info(self.context, instance)
        self.assertEqual(network_info, ref)

    @attr(kind='small')
    def test_get_instance_nw_info_param_instance_is_none(self):
        raise SkipTest("Parameter check is not implemented.")
        """
        ApiError is raised
        """
        instance = None
        self.assertRaises(exception.ApiError,
                          self.api.get_instance_nw_info,
                          self.context, instance)

    @attr(kind='small')
    def test_get_instance_nw_info_param_instance_not_found(self):
        raise SkipTest("Parameter check is not implemented.")
        """
        ApiError is raised
        """
        def fake_instance_get(context, instance_id):
            return exception.InstanceNotFound(instance_id=instance_id)

        self.stubs.Set(self.api.db, "instance_get",
                                    fake_instance_get)

        instance = {'id': 99999}
        self.assertRaises(exception.ApiError,
                          self.api.get_instance_nw_info,
                          self.context, instance)

    @attr(kind='small')
    def test_validate_networks(self):
        """Test for nova.network.api.API.validate_networks. """
        def call(topic, content):
            self.assertEqual(FLAGS.network_topic, topic)
            self.assertEqual('validate_networks', content['method'])
            self.assertEqual(requested_networks, content['args']['networks'])

        self.call = call

        requested_networks = networks
        ref = self.api.validate_networks(self.context, requested_networks)
        self.assertEqual(None, ref)
