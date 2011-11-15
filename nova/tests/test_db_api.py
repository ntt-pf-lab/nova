# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
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

"""Unit tests for the DB API"""

import datetime
import mox

from nova import test
from nova import context
from nova import db
from nova import exception
from nova import flags

from nova.compute import vm_states
from nose.plugins.attrib import attr
from nose.plugins.skip import SkipTest
from nova import ipv6

FLAGS = flags.FLAGS


def _setup_networking(instance_id, ip='1.2.3.4', flo_addr='1.2.1.2'):
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


class DbApiTestCase(test.TestCase):
    def setUp(self):
        super(DbApiTestCase, self).setUp()
        self.user_id = 'fake'
        self.project_id = 'fake'
        self.context = context.RequestContext(self.user_id, self.project_id,
                                              is_admin=True)
        self.db = db

    def test_instance_get_project_vpn(self):
        values = {'instance_type_id': FLAGS.default_instance_type,
                  'image_ref': FLAGS.vpn_image_id,
                  'project_id': self.project_id,
                 }
        instance = self.db.instance_create(self.context, values)
        result = self.db.instance_get_project_vpn(self.context.elevated(),
                                             self.project_id)
        self.assertEqual(instance['id'], result['id'])

    def test_instance_get_project_vpn_joins(self):
        values = {'instance_type_id': FLAGS.default_instance_type,
                  'image_ref': FLAGS.vpn_image_id,
                  'project_id': self.project_id,
                 }
        instance = self.db.instance_create(self.context, values)
        _setup_networking(instance['id'])
        result = self.db.instance_get_project_vpn(self.context.elevated(),
                                             self.project_id)
        self.assertEqual(instance['id'], result['id'])
        self.assertEqual(result['fixed_ips'][0]['floating_ips'][0].address,
                         '1.2.1.2')

    def test_instance_get_all_by_filters(self):
        args = {'reservation_id': 'a', 'image_ref': 1, 'host': 'host1'}
        inst1 = self.db.instance_create(self.context, args)
        inst2 = self.db.instance_create(self.context, args)
        result = self.db.instance_get_all_by_filters(self.context, {})
        self.assertTrue(2, len(result))

    def test_instance_get_all_by_filters_parameter_ipv6(self):
        def fake_to_global(prefix, mac, project_id):
            return prefix

        self.stubs.Set(ipv6.api.IMPL, 'to_global', fake_to_global)

        args1 = {'id': 1, 'image_ref': 1, 'host': 'host1'}
        args2 = {'id': 2, 'image_ref': 1, 'host': 'host2'}
        inst1 = self.db.instance_create(self.context, args1)
        inst2 = self.db.instance_create(self.context, args2)

        self.db.api.network_create_safe(self.context,
            {'id': 100, 'host': 'host1', 'cidr_v6': '2001:db8::/16'})
        self.db.api.virtual_interface_create(self.context,
            {'id': 1, 'instance_id': 1, 'network_id': 100})

        filter = {'ip6': '2001:db8::'}
        result = self.db.instance_get_all_by_filters(self.context, filter)
        self.assertEqual(1, len(result))

    def test_instance_get_all_by_filters_parameter_ip(self):
        def fake_to_global(prefix, mac, project_id):
            return prefix

        self.stubs.Set(ipv6.api.IMPL, 'to_global', fake_to_global)

        args1 = {'id': 1, 'image_ref': 1, 'host': 'host1'}
        args2 = {'id': 2, 'image_ref': 1, 'host': 'host2'}
        inst1 = self.db.instance_create(self.context, args1)
        inst2 = self.db.instance_create(self.context, args2)

        self.db.api.network_create_safe(self.context,
            {'id': 100, 'host': 'host1', 'cidr': '192.168.0.1'})
        self.db.api.virtual_interface_create(self.context,
            {'id': 1, 'instance_id': 1, 'network_id': 100,
             'address': '192.168.0.1'})
        self.db.api.fixed_ip_create(self.context,
            {'id': 200, 'instance_id': 1, 'virtual_interface_id': 1,
             'address': '192.168.0.1'})

        filter = {'ip': '192.168.0.1'}
        result = self.db.instance_get_all_by_filters(self.context, filter)

        self.assertEqual(1, len(result))

    def test_instance_get_all_by_filters_parameter_meta(self):
        args1 = {'id': 1, 'image_ref': 1, 'host': 'host1',
                    'metadata': {'key1': 'value1'}}
        args2 = {'id': 2, 'image_ref': 1, 'host': 'host2'}
        inst1 = self.db.instance_create(self.context, args1)
        inst2 = self.db.instance_create(self.context, args2)

        meta = [dict(key1='value1')]
        filter = {'metadata': meta}
        result = self.db.instance_get_all_by_filters(self.context, filter)

        self.assertEqual(1, len(result))

        meta = dict(key1='value1')
        filter = {'metadata': meta}
        result = self.db.instance_get_all_by_filters(self.context, filter)

        self.assertEqual(1, len(result))

    def test_instance_get_all_by_filters_parameter_column(self):
        args1 = {'id': 1, 'image_ref': 1, 'host': 'host1',
                    'metadata': {'key1': 'value1'}}
        args2 = {'id': 2, 'image_ref': 1, 'host': 'host2'}
        inst1 = self.db.instance_create(self.context, args1)
        inst2 = self.db.instance_create(self.context, args2)

        filter = {'host': 'host*'}
        result = self.db.instance_get_all_by_filters(self.context, filter)

        self.assertEqual(2, len(result))

        filter = {'host': 'host2'}
        result = self.db.instance_get_all_by_filters(self.context, filter)

        self.assertEqual(1, len(result))

    def test_instance_get_all_by_filters_deleted(self):
        args1 = {'reservation_id': 'a', 'image_ref': 1, 'host': 'host1'}
        inst1 = self.db.instance_create(self.context, args1)
        args2 = {'reservation_id': 'b', 'image_ref': 1, 'host': 'host1'}
        inst2 = self.db.instance_create(self.context, args2)
        self.db.instance_destroy(self.context, inst1.id)
        result = self.db.instance_get_all_by_filters(
                                    self.context.elevated(), {})
        self.assertEqual(2, len(result))
        self.assertEqual(result[0].id, inst2.id)
        self.assertEqual(result[1].id, inst1.id)
        self.assertTrue(result[1].deleted)

    @attr(kind='small')
    def test_service_destroy(self):
        """
        service_destroy
        """
        # setup
        self.db.api.service_create(self.context, {'id': 1})

        # test and assert
        result = self.db.api.service_destroy(self.context, 1)
        self.assertTrue(result is None)

        self.assertRaises(exception.ServiceNotFound,
                          self.db.api.service_get,
                          self.context, 1)

    @attr(kind='small')
    def test_service_destroy_db_not_found(self):
        # test and assert
        self.assertRaises(exception.ServiceNotFound,
                          self.db.api.service_destroy,
                          self.context, 1)

    @attr(kind='small')
    def test_service_get(self):
        """
        service_get
        """
        # setup
        self.db.api.service_create(self.context, {'id': 1})

        # test and assert
        result = self.db.api.service_get(self.context, 1)
        self.assertTrue(result)
        self.assertEqual(1, result.id)

    @attr(kind='small')
    def test_service_get_db_not_found(self):
        # test and assert
        self.assertRaises(exception.ServiceNotFound,
                          self.db.api.service_get,
                          self.context, 1)

    @attr(kind='small')
    def test_service_get_by_host_and_topic(self):
        """
        service_get_by_host_and_topic
        """
        # setup
        self.db.api.service_create(self.context,
                                   {'id': 1, 'host': 'host1',
                                    'topic': 'compute'})

        # test and assert
        result = self.db.api.service_get_by_host_and_topic(
                                    self.context, 'host1', 'compute')
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)
        self.assertEqual('host1', result.host)
        self.assertEqual('compute', result.topic)

    @attr(kind='small')
    def test_service_get_by_host_and_topic_db_not_found(self):
        # setup
        self.db.api.service_create(self.context,
                                   {'id': 1, 'host': 'host1',
                                    'topic': 'compute'})
        # test and assert
        result = self.db.api.service_get_by_host_and_topic(
                                            self.context, 'host2', 'compute')
        self.assertTrue(result is None)

    @attr(kind='small')
    def test_service_get_all(self):
        """
        service_get_all
        """
        # setup
        self.db.api.service_create(self.context, {'id': 1})

        # test and assert
        result = self.db.api.service_get_all(self.context)
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)

    @attr(kind='small')
    def test_service_get_all_db_not_found(self):
        # test and assert
        result = db.api.service_get_all(self.context)
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_service_get_all_by_topic(self):
        """
        service_get_all_by_topic
        """
        # setup
        self.db.api.service_create(self.context, {'id': 1, 'topic': 'compute'})

        # test and assert
        result = self.db.api.service_get_all_by_topic(self.context, 'compute')
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)
        self.assertEqual('compute', result[0].topic)

    @attr(kind='small')
    def test_service_get_all_by_topic_db_not_found(self):
        # test and assert
        result = self.db.api.service_get_all_by_topic(self.context, 'compute')
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_service_get_all_by_host(self):
        """
        service_get_all_by_host
        """
        # setup
        self.db.api.service_create(self.context, {'id': 1, 'host': 'host1'})

        # test and assert
        result = self.db.api.service_get_all_by_host(self.context, 'host1')
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)
        self.assertEqual('host1', result[0].host)

    @attr(kind='small')
    def test_service_get_all_by_host_db_not_found(self):
        # test and assert
        result = self.db.api.service_get_all_by_host(self.context, 'host1')
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_service_get_all_compute_by_host(self):
        """
        service_get_all_compute_by_host
        """
        # setup
        self.db.api.service_create(self.context,
                                   {'id': 1, 'host': 'host1',
                                    'topic': 'compute'})

        # test and assert
        result = self.db.api.service_get_all_compute_by_host(
                                            self.context, 'host1')
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)
        self.assertEqual('host1', result[0].host)
        self.assertEqual('compute', result[0].topic)

    @attr(kind='small')
    def test_service_get_all_compute_by_host_db_not_found(self):
        """
        should not be raise exception.
        """
        # test and assert
        self.assertRaises(exception.ComputeHostNotFound,
                          self.db.api.service_get_all_compute_by_host,
                          self.context, 'host1')

    @attr(kind='small')
    def test_service_get_all_compute_sorted(self):
        """
        service_get_all_compute_sorted
        """
        # setup
        self.db.api.service_create(self.context,
                                   {'id': 1, 'host': 'host1',
                                    'topic': 'compute'})
        self.db.api.instance_create(self.context,
                                    {'host': 'host1', 'vcpus': 1})
        self.db.api.instance_create(self.context,
                                    {'host': 'host1', 'vcpus': 2})

        # test and assert
        result = self.db.api.service_get_all_compute_sorted(self.context)
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertTrue(isinstance(result[0], tuple))
        self.assertTrue(1, result[0][0].id)
        self.assertTrue('host1', result[0][0].host)
        self.assertTrue('compute', result[0][0].topic)
        self.assertTrue(3, result[0][1])

    @attr(kind='small')
    def test_service_get_all_compute_sorted_db_not_found(self):
        # test and assert
        result = self.db.api.service_get_all_compute_sorted(self.context)
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_service_get_all_network_sorted(self):
        """
        service_get_all_network_sorted
        """
        # setup
        self.db.api.service_create(self.context,
                                   {'id': 1, 'host': 'host1',
                                    'topic': 'network'})
        self.db.api.network_create_safe(self.context, {'host': 'host1'})
        self.db.api.network_create_safe(self.context, {'host': 'host1'})

        # test and assert
        result = self.db.api.service_get_all_network_sorted(self.context)
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertTrue(isinstance(result[0], tuple))
        self.assertTrue(1, result[0][0].id)
        self.assertTrue('host1', result[0][0].host)
        self.assertTrue('network', result[0][0].topic)
        self.assertTrue(2, result[0][1])

    @attr(kind='small')
    def test_service_get_all_network_sorted_db_not_found(self):
        # test and assert
        result = db.api.service_get_all_network_sorted(self.context)
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_service_get_all_volume_sorted(self):
        """
        service_get_all_volume_sorted
        """
        # setup
        self.db.api.service_create(self.context,
                                   {'id': 1, 'host': 'host1',
                                    'topic': 'volume'})
        self.db.api.volume_create(self.context, {'host': 'host1', 'size': 1})
        self.db.api.volume_create(self.context, {'host': 'host1', 'size': 2})

        # test and assert
        result = self.db.api.service_get_all_volume_sorted(self.context)
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertTrue(isinstance(result[0], tuple))
        self.assertTrue(1, result[0][0].id)
        self.assertTrue('host1', result[0][0].host)
        self.assertTrue('network', result[0][0].topic)
        self.assertTrue(3, result[0][1])

    @attr(kind='small')
    def test_service_get_all_volume_sorted_db_not_found(self):
        # test and assert
        result = self.db.api.service_get_all_volume_sorted(self.context)
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_service_get_by_args(self):
        """
        service_get_by_args
        """
        # setup
        self.db.api.service_create(self.context,
                                   {'id': 1, 'host': 'host1',
                                    'binary': 'binary1'})

        # test and assert
        result = self.db.api.service_get_by_args(
                                            self.context, 'host1', 'binary1')
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)
        self.assertEqual('host1', result.host)
        self.assertEqual('binary1', result.binary)

    @attr(kind='small')
    def test_service_get_by_args_db_not_found(self):
        # test and assert
        self.assertRaises(exception.HostBinaryNotFound,
                          self.db.api.service_get_by_args,
                          self.context, 'host1', 'binary1')

    @attr(kind='small')
    def test_service_create(self):
        """
        service_create
        """
        # test and assert
        result = self.db.api.service_create(self.context, {'id': 1})
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)

        service = self.db.api.service_get(self.context, result.id)
        self.assertTrue(service is not None)

    @attr(kind='small')
    def test_service_create_db_duplicate(self):
        # setup
        self.db.api.service_create(self.context, {'id': 1})

        # test and assert
        self.assertRaises(exception.Duplicate,
                          self.db.api.service_create,
                          self.context, {'id': 1})

    @attr(kind='small')
    def test_service_update(self):
        """
        service_update
        """
        # setup
        self.db.api.service_create(self.context, {'id': 1})

        # test and assert
        self.db.api.service_update(self.context, 1, {'host': 'host1'})
        service = self.db.api.service_get(self.context, 1)
        self.assertTrue(service is not None)
        self.assertEqual(1, service.id)
        self.assertEqual('host1', service.host)

    @attr(kind='small')
    def test_service_update_db_not_found(self):
        # test and assert
        self.assertRaises(exception.ServiceNotFound,
                          self.db.api.service_update,
                          self.context, 1, {'host': 'host1'})

    @attr(kind='small')
    def test_compute_node_get(self):
        """
        compute_node_get
        """
        # setup
        self.db.api.service_create(self.context, {'id': 1})
        self.db.api.compute_node_create(self.context,
                                        {'id': 1,
                                         'service_id': 1,
                                         'vcpus': 1,
                                         'memory_mb': 1,
                                         'local_gb': 1,
                                         'vcpus_used': 1,
                                         'memory_mb_used': 1,
                                         'local_gb_used': 1,
                                         'hypervisor_type': 'kvm',
                                         'hypervisor_version': 1,
                                         'cpu_info': 'cpu_info1'})

        # test and assert
        result = self.db.api.compute_node_get(self.context, 1)
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)
        self.assertEqual(1, result.service_id)
        self.assertEqual(1, result.vcpus)
        self.assertEqual(1, result.memory_mb)
        self.assertEqual(1, result.local_gb)
        self.assertEqual(1, result.vcpus_used)
        self.assertEqual(1, result.memory_mb_used)
        self.assertEqual(1, result.local_gb_used)
        self.assertEqual("kvm", result.hypervisor_type)
        self.assertEqual(1, result.hypervisor_version)
        self.assertEqual("cpu_info1", result.cpu_info)

    @attr(kind='small')
    def test_compute_node_get_db_not_found(self):
        # test and assert
        self.assertRaises(exception.ComputeHostNotFound,
                          self.db.api.compute_node_get,
                          self.context, 1)

    @attr(kind='small')
    def test_compute_node_create(self):
        """
        compute_node_create
        """
        # setup
        self.db.api.service_create(self.context, {'id': 1})
        self.db.api.compute_node_create(self.context,
                                        {'id': 1,
                                         'service_id': 1,
                                         'vcpus': 1,
                                         'memory_mb': 1,
                                         'local_gb': 1,
                                         'vcpus_used': 1,
                                         'memory_mb_used': 1,
                                         'local_gb_used': 1,
                                         'hypervisor_type': 'kvm',
                                         'hypervisor_version': 1,
                                         'cpu_info': 'cpu_info1'})

        # test and assert
        result = self.db.api.compute_node_get(self.context, 1)
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)
        self.assertEqual(1, result.service_id)
        self.assertEqual(1, result.vcpus)
        self.assertEqual(1, result.memory_mb)
        self.assertEqual(1, result.local_gb)
        self.assertEqual(1, result.vcpus_used)
        self.assertEqual(1, result.memory_mb_used)
        self.assertEqual(1, result.local_gb_used)
        self.assertEqual("kvm", result.hypervisor_type)
        self.assertEqual(1, result.hypervisor_version)
        self.assertEqual("cpu_info1", result.cpu_info)

    @attr(kind='small')
    def test_compute_node_create_db_duplicate(self):
        # setup
        self.db.api.service_create(self.context, {'id': 1})
        self.db.api.compute_node_create(self.context,
                                        {'id': 1,
                                         'service_id': 1,
                                         'vcpus': 1,
                                         'memory_mb': 1,
                                         'local_gb': 1,
                                         'vcpus_used': 1,
                                         'memory_mb_used': 1,
                                         'local_gb_used': 1,
                                         'hypervisor_type': 'hypervisor_type1',
                                         'hypervisor_version': 1,
                                         'cpu_info': 'cpu_info1'})

        # test and assert
        self.assertRaises(exception.Duplicate,
                          self.db.api.compute_node_create,
                          self.context,
                          {'id': 1,
                           'service_id': 1,
                           'vcpus': 1,
                           'memory_mb': 1,
                           'local_gb': 1,
                           'vcpus_used': 1,
                           'memory_mb_used': 1,
                           'local_gb_used': 1,
                           'hypervisor_type': 'hypervisor_type1',
                           'hypervisor_version': 1,
                           'cpu_info': 'cpu_info1'})

    @attr(kind='small')
    def test_compute_node_update(self):
        """
        compute_node_update
        """
        # setup
        self.db.api.service_create(self.context, {'id': 1})
        self.db.api.compute_node_create(self.context,
                                        {'id': 1,
                                         'service_id': 1,
                                         'vcpus': 1,
                                         'memory_mb': 1,
                                         'local_gb': 1,
                                         'vcpus_used': 1,
                                         'memory_mb_used': 1,
                                         'local_gb_used': 1,
                                         'hypervisor_type': 'hypervisor_type1',
                                         'hypervisor_version': 1,
                                         'cpu_info': 'cpu_info1'})

        # test and assert
        self.db.api.compute_node_update(self.context, 1, {'vcpus': 2})

        compute_node = db.api.compute_node_get(self.context, 1)
        self.assertTrue(compute_node is not None)
        self.assertEqual(1, compute_node.id)
        self.assertEqual(2, compute_node.vcpus)

    @attr(kind='small')
    def test_compute_node_update_db_not_found(self):
        # test and assert
        self.assertRaises(exception.ComputeHostNotFound,
                          self.db.api.compute_node_update,
                          self.context, 1, {'vcpus': 2})

    @attr(kind='small')
    def test_certificate_create(self):
        """
        certificate_create
        """
        # setup
        certificate_list = self.db.api.certificate_get_all_by_project(
                                            self.context, 'project1')
        self.assertEqual(0, len(certificate_list))

        # test and assert
        result = self.db.api.certificate_create(
                        self.context, {'id': 1, 'project_id': 'project1'})
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)

        certificate_list = self.db.api.certificate_get_all_by_project(
                                            self.context, 'project1')
        self.assertEqual(1, len(certificate_list))

    @attr(kind='small')
    def test_certificate_create_db_duplicate(self):
        # setup
        self.db.api.certificate_create(self.context, {'id': 1})

        # test and assert
        self.assertRaises(exception.Duplicate,
                          self.db.api.certificate_create,
                          self.context, {'id': 1})

    @attr(kind='small')
    def test_certificate_destroy(self):
        """
        certificate_destroy
        """
        # setup
        self.db.api.certificate_create(self.context,
                                       {'id': 1, 'project_id': 'project1'})
        certificate_list = db.api.certificate_get_all_by_project(
                                            self.context, 'project1')
        self.assertEqual(1, len(certificate_list))

        # test and assert
        result = self.db.api.certificate_destroy(self.context, 1)
        self.assertTrue(result is None)

        certificate_list = db.api.certificate_get_all_by_project(
                                            self.context, 'project1')
        self.assertEqual(0, len(certificate_list))

    @attr(kind='small')
    def test_certificate_destroy_db_not_found(self):
        # test and assert
        self.assertRaises(exception.CertificateNotFound,
                          self.db.api.certificate_destroy,
                          self.context, 1)

    @attr(kind='small')
    def test_certificate_get_all_by_project(self):
        """
        certificate_get_all_by_project
        """
        # setup
        self.db.api.certificate_create(self.context,
                                       {'id': 1, 'project_id': 'project1'})

        # test and assert
        result = self.db.api.certificate_get_all_by_project(
                                            self.context, 'project1')
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)
        self.assertEqual('project1', result[0].project_id)

    @attr(kind='small')
    def test_certificate_get_all_by_project_db_not_found(self):
        # test and assert
        result = self.db.api.certificate_get_all_by_project(
                                        self.context, 'project1')
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_certificate_get_all_by_user(self):
        """
        certificate_get_all_by_user
        """
        # setup
        self.db.api.certificate_create(self.context,
                                       {'id': 1, 'user_id': 'user1'})

        # test and assert
        result = self.db.api.certificate_get_all_by_user(self.context, 'user1')
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)
        self.assertEqual('user1', result[0].user_id)

    @attr(kind='small')
    def test_certificate_get_all_by_user_db_not_found(self):
        # test and assert
        result = self.db.api.certificate_get_all_by_user(self.context, 'user1')
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_certificate_get_all_by_user_and_project(self):
        """
        certificate_get_all_by_user_and_project
        """
        # setup
        self.db.api.certificate_create(self.context,
                                       {'id': 1, 'user_id': 'user1',
                                        'project_id': 'project1'})

        # test and assert
        result = self.db.api.certificate_get_all_by_user_and_project(
                                            self.context, 'user1', 'project1')
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)
        self.assertEqual('user1', result[0].user_id)
        self.assertEqual('project1', result[0].project_id)

    @attr(kind='small')
    def test_certificate_get_all_by_user_and_project_db_not_found(self):
        # test and assert
        result = self.db.api.certificate_get_all_by_user_and_project(
                                            self.context, 'user1', 'project1')
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_certificate_update(self):
        """
        certificate_update
        """
        # setup
        self.db.api.certificate_create(self.context,
                                       {'id': 1, 'project_id': 'project1'})

        # test and assert
        self.db.api.certificate_update(self.context, 1, {'user_id': 'user1'})

        # certificate_get is not exist.
        certificate_list = db.api.certificate_get_all_by_project(
                                            self.context, 'project1')
        self.assertEqual(1, len(certificate_list))
        self.assertEqual(1, certificate_list[0].id)
        self.assertEqual('user1', certificate_list[0].user_id)

    @attr(kind='small')
    def test_certificate_update_db_not_found(self):
        # test and assert
        self.assertRaises(exception.CertificateNotFound,
                          self.db.api.certificate_update,
                          self.context, 1, {'user_id': 'user1'})

    @attr(kind='small')
    def test_floating_ip_get(self):
        """
        floating_ip_get
        """
        # setup
        self.db.api.floating_ip_create(self.context, {'id': 1})

        # test and assert
        result = self.db.api.floating_ip_get(self.context, 1)
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)

    @attr(kind='small')
    def test_floating_ip_get_db_not_found(self):
        # test and assert
        self.assertRaises(exception.FloatingIpNotFound,
                          self.db.api.floating_ip_get,
                          self.context, 1)

    @attr(kind='small')
    def test_floating_ip_allocate_address(self):
        """
        floating_ip_allocate_address
        """
        # setup
        self.db.api.floating_ip_create(self.context,
                                       {'id': 1, 'address': '1.0.0.0'})

        # test and assert
        result = self.db.api.floating_ip_allocate_address(
                                            self.context, 'project1')
        self.assertTrue(result is not None)
        self.assertEqual('1.0.0.0', result)

        floating_ip = db.api.floating_ip_get(self.context, 1)
        self.assertTrue(floating_ip is not None)
        self.assertEqual('project1', floating_ip.project_id)

    @attr(kind='small')
    def test_floating_ip_allocate_address_db_not_found(self):
        # test and assert
        self.assertRaises(exception.FloatingIpNotFound,
                          self.db.api.floating_ip_allocate_address,
                          self.context, 'project1')

    @attr(kind='small')
    def test_floating_ip_create(self):
        """
        floating_ip_create
        """
        # test and assert
        result = self.db.api.floating_ip_create(
                            self.context, {'id': 1, 'address': '1.0.0.0'})
        self.assertTrue(result is not None)
        self.assertEqual('1.0.0.0', result)

        floating_ip = db.api.floating_ip_get(self.context, 1)
        self.assertTrue(floating_ip is not None)

    @attr(kind='small')
    def test_floating_ip_create_db_duplicate(self):
        # setup
        self.db.api.floating_ip_create(self.context, {'id': 1})

        # test and assert
        self.assertRaises(exception.Duplicate,
                          self.db.api.floating_ip_create,
                          self.context, {'id': 1, 'address': '1.0.0.0'})

    @attr(kind='small')
    def test_floating_ip_count_by_project(self):
        """
        floating_ip_count_by_project
        """
        # setup
        self.db.api.floating_ip_create(self.context,
                                       {'id': 1, 'project_id': 'project1'})

        # test and assert
        result = self.db.api.floating_ip_count_by_project(
                                            self.context, 'project1')
        self.assertTrue(result is not None)
        self.assertEqual(1, result)

    @attr(kind='small')
    def test_floating_ip_deallocate(self):
        """
        floating_ip_deallocate
        """
        # setup
        self.db.api.floating_ip_create(self.context,
                                       {'id': 1, 'address': '1.0.0.0'})

        # test and assert
        self.db.api.floating_ip_deallocate(self.context, '1.0.0.0')

        floating_ip = self.db.api.floating_ip_get(self.context, 1)
        self.assertTrue(floating_ip is not None)
        self.assertEqual('1.0.0.0', floating_ip.address)
        self.assertEqual(None, floating_ip.project_id)
        self.assertEqual(None, floating_ip.host)
        self.assertEqual(False, floating_ip.auto_assigned)

    @attr(kind='small')
    def test_floating_ip_deallocate_db_not_found(self):
        # test and assert
        self.assertRaises(exception.FloatingIpNotFoundForAddress,
                          self.db.api.floating_ip_deallocate,
                          self.context, '1.0.0.0')

    @attr(kind='small')
    def test_floating_ip_destroy(self):
        """
        floating_ip_destroy
        """
        # setup
        self.db.api.floating_ip_create(self.context,
                                       {'id': 1, 'address': '1.0.0.0'})

        # test and assert
        result = self.db.api.floating_ip_destroy(self.context, '1.0.0.0')
        self.assertTrue(result is None)

        self.assertRaises(exception.FloatingIpNotFound,
                          self.db.api.floating_ip_get,
                          self.context, 1)

    @attr(kind='small')
    def test_floating_ip_destroy_db_not_found(self):
        # test and assert
        self.assertRaises(exception.FloatingIpNotFoundForAddress,
                          self.db.api.floating_ip_destroy,
                          self.context, '1.0.0.0')

    @attr(kind='small')
    def test_floating_ip_disassociate(self):
        """
        floating_ip_disassociate
        """
        # setup
        self.db.api.fixed_ip_create(self.context, {'address': '10.1.1.1'})
        fixed_ip = self.db.fixed_ip_get_by_address(self.context, "10.1.1.1")
        self.db.api.floating_ip_create(self.context,
                                       {'id': 1,
                                        'address': '1.0.0.0',
                                        'fixed_ip_id': fixed_ip.id})

        # test and assert
        result = self.db.api.floating_ip_disassociate(self.context, '1.0.0.0')
        self.assertTrue(result is not None)
        self.assertEqual('10.1.1.1', result)

        floating_ip = self.db.api.floating_ip_get(self.context, 1)
        self.assertTrue(floating_ip is not None)
        self.assertEqual('1.0.0.0', floating_ip.address)
        self.assertEqual(None, floating_ip.fixed_ip)

    @attr(kind='small')
    def test_floating_ip_disassociate_db_not_found(self):
        # test and assert
        self.assertRaises(exception.FloatingIpNotFoundForAddress,
                          self.db.api.floating_ip_disassociate,
                          self.context, '1.0.0.0')

    @attr(kind='small')
    def test_floating_ip_fixed_ip_associate(self):
        """
        floating_ip_fixed_ip_associate
        """
        # setup
        self.db.api.fixed_ip_create(self.context, {'address': '10.1.1.1'})
        self.db.api.floating_ip_create(self.context,
                                       {'id': 1, 'address': '1.0.0.0'})

        # test and assert
        result = self.db.api.floating_ip_fixed_ip_associate(
                                            self.context,
                                            '1.0.0.0', '10.1.1.1', 'localhost')
        self.assertTrue(result is None)

        floating_ip = db.api.floating_ip_get(self.context, 1)
        self.assertTrue(floating_ip is not None)
        self.assertEqual('1.0.0.0', floating_ip.address)
        self.assertEqual('10.1.1.1', floating_ip.fixed_ip.address)
        self.assertEqual('localhost', floating_ip.host)

    @attr(kind='small')
    def test_floating_ip_fixed_ip_associate_db_not_found(self):
        # test and assert
        self.assertRaises(exception.FloatingIpNotFoundForAddress,
                          self.db.api.floating_ip_fixed_ip_associate,
                          self.context, '1.0.0.0', '10.1.1.1', 'localhost')

    @attr(kind='small')
    def test_floating_ip_get_all(self):
        """
        floating_ip_get_all
        """
        # setup
        self.db.api.floating_ip_create(self.context, {'id': 1})

        # test and assert
        result = self.db.api.floating_ip_get_all(self.context)
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)

    @attr(kind='small')
    def test_floating_ip_get_all_db_not_found(self):
        # test and assert
        self.assertRaises(exception.NoFloatingIpsDefined,
                          db.api.floating_ip_get_all,
                          self.context)

    @attr(kind='small')
    def test_floating_ip_get_all_by_host(self):
        """
        floating_ip_get_all_by_host
        """
        # setup
        db.api.floating_ip_create(self.context, {'id': 1, 'host': 'host1'})

        # test and assert
        result = self.db.api.floating_ip_get_all_by_host(self.context, 'host1')
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)

    @attr(kind='small')
    def test_floating_ip_get_all_by_host_db_not_found(self):
        # test and assert
        self.assertRaises(exception.FloatingIpNotFoundForHost,
                          self.db.api.floating_ip_get_all_by_host,
                          self.context, 'project1')

    @attr(kind='small')
    def test_floating_ip_get_all_by_project(self):
        """
        floating_ip_get_all_by_project
        """
        # setup
        self.db.api.floating_ip_create(self.context,
                                       {'id': 1, 'project_id': 'project1'})

        # test and assert
        result = self.db.api.floating_ip_get_all_by_project(
                                            self.context, 'project1')
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)

    @attr(kind='small')
    def test_floating_ip_get_all_by_project_db_not_found(self):
        # test and assert
        self.assertRaises(exception.FloatingIpNotFoundForProject,
                          self.db.api.floating_ip_get_all_by_project,
                          self.context, 'project1')

    @attr(kind='small')
    def test_floating_ip_get_by_address(self):
        """
        floating_ip_get_by_address
        """
        # setup
        self.db.api.floating_ip_create(self.context,
                                       {'id': 1, 'address': '1.0.0.0'})

        # test and assert
        result = self.db.api.floating_ip_get_by_address(
                                            self.context, '1.0.0.0')
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)
        self.assertEqual('1.0.0.0', result.address)

    @attr(kind='small')
    def test_floating_ip_get_by_address_db_not_found(self):
        # test and assert
        self.assertRaises(exception.FloatingIpNotFoundForAddress,
                          db.api.floating_ip_get_by_address,
                          self.context, '1.0.0.0')

    @attr(kind='small')
    def test_floating_ip_update(self):
        """
        floating_ip_update
        """
        # setup
        self.db.api.floating_ip_create(self.context,
                                       {'id': 1, 'address': '1.0.0.0'})

        # test and assert
        self.db.api.floating_ip_update(self.context,
                                       '1.0.0.0', {'host': 'host1'})

        floating_ip = self.db.api.floating_ip_get(self.context, 1)
        self.assertTrue(floating_ip is not None)
        self.assertEqual('1.0.0.0', floating_ip.address)
        self.assertEqual('host1', floating_ip.host)

    @attr(kind='small')
    def test_floating_ip_update_db_not_found(self):
        # test and assert
        self.assertRaises(exception.FloatingIpNotFoundForAddress,
                          db.api.floating_ip_update,
                          self.context, '1.0.0.0', {'host': 'host1'})

    @attr(kind='small')
    def test_floating_ip_set_auto_assigned(self):
        """
        floating_ip_set_auto_assigned
        """
        # setup
        self.db.api.floating_ip_create(self.context,
                                       {'id': 1, 'address': '1.0.0.0'})

        # test and assert
        self.db.api.floating_ip_set_auto_assigned(self.context, '1.0.0.0')

        floating_ip = db.api.floating_ip_get(self.context, 1)
        self.assertTrue(floating_ip is not None)
        self.assertEqual(1, floating_ip.id)
        self.assertEqual('1.0.0.0', floating_ip.address)
        self.assertEqual(True, floating_ip.auto_assigned)

    @attr(kind='small')
    def test_floating_ip_set_auto_assigned_db_not_found(self):
        # test and assert
        self.assertRaises(exception.FloatingIpNotFoundForAddress,
                          db.api.floating_ip_set_auto_assigned,
                          self.context, '1.0.0.0')

    @attr(kind='small')
    def test_migration_update(self):
        """
        migration_update
        """
        # setup
        self.db.api.migration_create(self.context, {'id': 1})

        # test and assert
        result = self.db.api.migration_update(
                self.context, 1, {'source_compute': 'source_compute1'})
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)

        migration = db.api.migration_get(self.context, 1)
        self.assertTrue(migration is not None)
        self.assertEqual(1, migration.id)
        self.assertEqual('source_compute1', migration.source_compute)

    @attr(kind='small')
    def test_migration_update_db_not_found(self):
        # test and assert
        self.assertRaises(exception.MigrationNotFound,
                          self.db.api.migration_update,
                          self.context, 1,
                          {'source_compute': 'source_compute1'})

    @attr(kind='small')
    def test_migration_create(self):
        """
        migration_create
        """
        # test and assert
        result = self.db.api.migration_create(self.context, {'id': 1})
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)

        migration = self.db.api.migration_get(self.context, 1)
        self.assertTrue(migration is not None)
        self.assertEqual(1, migration.id)

    @attr(kind='small')
    def test_migration_create_db_duplicate(self):
        # setup
        self.db.api.migration_create(self.context, {'id': 1})

        # test and assert
        self.assertRaises(exception.Duplicate,
                          self.db.api.migration_create,
                          self.context, {'id': 1})

    @attr(kind='small')
    def test_migration_get(self):
        """
        migration_get
        """
        # setup
        db.api.migration_create(self.context, {'id': 1})

        # test and assert
        result = db.api.migration_get(self.context, 1)
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)

    @attr(kind='small')
    def test_migration_get_db_not_found(self):
        # test and assert
        self.assertRaises(exception.MigrationNotFound,
                          self.db.api.migration_get,
                          self.context, 1)

    @attr(kind='small')
    def test_migration_get_by_instance_and_status(self):
        """
        migration_get_by_instance_and_status
        """
        # setup
        self.db.api.migration_create(self.context,
                                     {'id': 1,
                                      'instance_uuid': 'instance_uuid1',
                                      'status': 'status1'})

        # test and assert
        result = self.db.api.migration_get_by_instance_and_status(
                                            self.context,
                                            'instance_uuid1', 'status1')
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)
        self.assertEqual("instance_uuid1", result.instance_uuid)
        self.assertEqual("status1", result.status)

    @attr(kind='small')
    def test_migration_get_by_instance_and_status_db_not_found(self):
        # test and assert
        self.assertRaises(exception.MigrationNotFoundByStatus,
                          self.db.api.migration_get_by_instance_and_status,
                          self.context, 'instance_uuid1', 'status1')

    @attr(kind='small')
    def test_fixed_ip_associate(self):
        """
        fixed_ip_associate
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.network_create_safe(self.context, {'id': 100})
        self.db.api.fixed_ip_create(self.context, {'address': '10.1.1.1'})

        # test and assert
        result = self.db.api.fixed_ip_associate(
                                            self.context, '10.1.1.1', 1, 100)
        self.assertTrue(result is not None)

        fixed_ip = self.db.api.fixed_ip_get_by_address(
                                            self.context, '10.1.1.1')
        self.assertTrue(result is not None)
        self.assertEqual('10.1.1.1', fixed_ip.address)
        self.assertEqual(1, fixed_ip.instance.id)
        self.assertEqual(100, fixed_ip.network.id)

    @attr(kind='small')
    def test_fixed_ip_associate_db_not_found(self):
        # test and assert
        self.assertRaises(exception.FixedIpNotFoundForNetwork,
                          db.api.fixed_ip_associate,
                          self.context, '2.0.0.0', 1)

    @attr(kind='small')
    def test_fixed_ip_associate_exception_ip_used(self):
        """fixed_ip_associate"""
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.network_create_safe(self.context, {'id': 100})
        self.db.api.fixed_ip_create(self.context, {'address': '10.1.1.1',
                                                   'instance_id': 1})

        # test and assert
        self.assertRaises(exception.FixedIpAlreadyInUse,
                    self.db.api.fixed_ip_associate,
                                    self.context, '10.1.1.1', 1, 100)

    @attr(kind='small')
    def test_fixed_ip_associate_pool(self):
        """
        fixed_ip_associate_pool
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.network_create_safe(self.context, {'id': 100})
        self.db.api.fixed_ip_create(self.context, {'address': '10.1.1.1'})

        # test and assert
        result = self.db.api.fixed_ip_associate_pool(
                                            self.context, 100, 1, 'host1')
        self.assertTrue(result is not None)
        self.assertEqual('10.1.1.1', result)

        fixed_ip = self.db.api.fixed_ip_get_by_address(
                                            self.context, '10.1.1.1')
        self.assertTrue(result is not None)
        self.assertEqual('10.1.1.1', fixed_ip.address)
        self.assertEqual(1, fixed_ip.instance.id)
        self.assertEqual(100, fixed_ip.network.id)
        self.assertEqual('host1', fixed_ip.host)

    @attr(kind='small')
    def test_fixed_ip_associate_pool_db_not_found(self):
        # test and assert
        self.assertRaises(exception.NoMoreFixedIps,
                          db.api.fixed_ip_associate_pool,
                          self.context,  100, 1, 'host1')

    @attr(kind='small')
    def test_fixed_ip_create(self):
        """
        fixed_ip_create
        """
        # test and assert
        self.db.api.fixed_ip_create(self.context, {'address': '10.1.1.1'})

        fixed_ip = self.db.api.fixed_ip_get_by_address(
                                            self.context, '10.1.1.1')
        self.assertTrue(fixed_ip is not None)
        self.assertEqual('10.1.1.1', fixed_ip.address)

    @attr(kind='small')
    def test_fixed_ip_create_db_duplicate(self):
        # setup
        self.db.api.fixed_ip_create(self.context,
                                    {'id': 100, 'address': '10.1.1.1'})
        # test and assert
        self.assertRaises(exception.Duplicate,
                          self.db.api.fixed_ip_create,
                          self.context,
                          {'id': 100, 'address': '10.1.1.1'})

    @attr(kind='small')
    def test_fixed_ip_disassociate(self):
        """
        fixed_ip_disassociate
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.1', 'instance_id': 1})

        # test and assert
        self.db.api.fixed_ip_disassociate(self.context, '10.1.1.1')

        fixed_ip = self.db.api.fixed_ip_get_by_address(
                                            self.context, '10.1.1.1')
        self.assertTrue(fixed_ip is not None)
        self.assertEqual('10.1.1.1', fixed_ip.address)
        self.assertEqual(None, fixed_ip.instance)

    @attr(kind='small')
    def test_fixed_ip_disassociate_db_not_found(self):
        # test and assert
        self.assertRaises(exception.FixedIpNotFoundForAddress,
                          db.api.fixed_ip_disassociate,
                          self.context, '2.0.0.0')

    @attr(kind='small')
    def test_fixed_ip_disassociate_all_by_timeout(self):
        """
        fixed_ip_disassociate_all_by_timeout
        """
        # setup
        self.db.api.network_create_safe(self.context,
                                        {'id': 100, 'host': 'host1'})
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.fixed_ip_create(
                self.context, {'address': '10.1.1.1',
                               'network_id': 100,
                               'instance_id': 1,
                               'updated_at': datetime.datetime(2010, 12, 31)})

        # test and assert
        self.db.api.fixed_ip_disassociate_all_by_timeout(
                self.context, 'host1', datetime.datetime(2011, 1, 1))

        fixed_ip = self.db.api.fixed_ip_get_by_address(
                                            self.context, '10.1.1.1')
        self.assertTrue(fixed_ip is not None)
        self.assertEqual('10.1.1.1', fixed_ip.address)
        self.assertEqual(None, fixed_ip.instance_id)
        self.assertEqual(False, fixed_ip.leased)

    @attr(kind='small')
    def test_fixed_ip_disassociate_all_by_timeout_db_not_found(self):
        """
        returned update count. "not found" means count zero.
        """
        # test and assert
        result = self.db.api.fixed_ip_disassociate_all_by_timeout(
                self.context, 'host1', datetime.datetime(2011, 1, 1))
        self.assertTrue(result is not None)
        self.assertEqual(0, result)

    @attr(kind='small')
    def test_fixed_ip_get_all(self):
        """
        fixed_ip_get_all
        """
        # setup
        self.db.api.fixed_ip_create(self.context, {'address': '10.1.1.1'})

        # test and assert
        result = self.db.api.fixed_ip_get_all(self.context)
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertTrue('10.1.1.1', result[0].address)

    @attr(kind='small')
    def test_fixed_ip_get_all_db_not_found(self):
        """
        fixed_ip already stored in test db.
        """
#        raise SkipTest("fixed_ip already stored in test db.")
        # test and assert
        result = self.db.api.fixed_ip_get_all(self.context)
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_fixed_ip_get_all_by_instance_host(self):
        """
        fixed_ip_get_all_by_instance_host
        """
#        raise SkipTest("Not implemented in sqlalchemy.api.")

    @attr(kind='small')
    def test_fixed_ip_get_all_by_instance_host_db_not_found(self):
#        raise SkipTest("Not implemented in sqlalchemy.api.")

    @attr(kind='small')
    def test_fixed_ip_get_by_address(self):
        """
        fixed_ip_get_by_address
        """
        # setup
        self.db.api.fixed_ip_create(self.context, {'address': '10.1.1.1'})

        # test and assert
        result = self.db.api.fixed_ip_get_by_address(self.context, '10.1.1.1')
        self.assertTrue(result is not None)
        self.assertEqual('10.1.1.1', result.address)

    @attr(kind='small')
    def test_fixed_ip_get_by_address_parameter_context(self):
        """
        fixed_ip_get_by_address
        """
        # setup
        normal_ctx = context.RequestContext(self.user_id, self.project_id,
                                              is_admin=False)
        self.db.api.instance_create(self.context, {'id': 1,
                                        'project_id': self.project_id})
        self.db.api.fixed_ip_create(self.context, {'address': '10.1.1.1',
                                                   'instance_id': 1})

        # test and assert
        result = self.db.api.fixed_ip_get_by_address(normal_ctx, '10.1.1.1')
        self.assertTrue(result is not None)
        self.assertEqual('10.1.1.1', result.address)

    @attr(kind='small')
    def test_fixed_ip_get_by_address_db_not_found(self):
        # test and assert
        self.assertRaises(exception.FixedIpNotFoundForAddress,
                          db.api.fixed_ip_get_by_address,
                          self.context, '2.0.0.0')

    @attr(kind='small')
    def test_fixed_ip_get_by_instance(self):
        """
        fixed_ip_get_by_instance
        """
        # setup
        self.db.api.fixed_ip_create(self.context, {'instance_id': 1})

        # test and assert
        result = self.db.api.fixed_ip_get_by_instance(self.context, 1)
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].instance_id)

    @attr(kind='small')
    def test_fixed_ip_get_by_instance_db_not_found(self):
        # test and assert
        self.assertRaises(exception.FixedIpNotFoundForInstance,
                          db.api.fixed_ip_get_by_instance,
                          self.context, 1)

    @attr(kind='small')
    def test_fixed_ip_get_by_network_host(self):
        """
        fixed_ip_get_by_network_host
        """
        # setup
        self.db.api.fixed_ip_create(self.context,
                                    {'network_id': 100, 'host': 'host1'})

        # test and assert
        result = self.db.api.fixed_ip_get_by_network_host(
                                    self.context, 100, 'host1')
        self.assertTrue(result is not None)
        self.assertEqual(100, result.network_id)
        self.assertEqual('host1', result.host)

    @attr(kind='small')
    def test_fixed_ip_get_by_network_host_db_not_found(self):
        # test and assert
        self.assertRaises(exception.FixedIpNotFoundForNetworkHost,
                          db.api.fixed_ip_get_by_network_host,
                          self.context, 100, 'host1')

    @attr(kind='small')
    def test_fixed_ip_get_by_virtual_interface(self):
        """
        fixed_ip_get_by_virtual_interface
        """
        # setup
        self.db.api.fixed_ip_create(self.context, {'virtual_interface_id': 1})

        # test and assert
        result = self.db.api.fixed_ip_get_by_virtual_interface(self.context, 1)
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].virtual_interface_id)

    @attr(kind='small')
    def test_fixed_ip_get_by_virtual_interface_db_not_found(self):
        # test and assert
        self.assertRaises(exception.FixedIpNotFoundForVirtualInterface,
                          db.api.fixed_ip_get_by_virtual_interface,
                          self.context, 1)

    @attr(kind='small')
    def test_fixed_ip_get_network(self):
        """
        fixed_ip_get_network
        It looks unmatch name of api. why it return network?
        """
        # setup
        self.db.api.network_create_safe(self.context, {'id': 100})
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.1', 'network_id': 100})

        # test and assert
        result = self.db.api.fixed_ip_get_network(self.context, '10.1.1.1')
        self.assertTrue(result is not None)
        self.assertEqual(100, result.id)

    @attr(kind='small')
    def test_fixed_ip_get_network_db_not_found(self):
        # test and assert
        self.assertRaises(exception.FixedIpNotFoundForAddress,
                          db.api.fixed_ip_get_network,
                          self.context, '2.0.0.0')

    @attr(kind='small')
    def test_fixed_ip_update(self):
        """
        fixed_ip_update
        """
        # setup
        self.db.api.fixed_ip_create(self.context, {'address': '10.1.1.1'})

        # test and assert
        self.db.api.fixed_ip_update(self.context,
                                    '10.1.1.1', {'host': 'host1'})

        fixed_ip = self.db.api.fixed_ip_get_by_address(
                                    self.context, '10.1.1.1')
        self.assertTrue(fixed_ip is not None)
        self.assertEqual('10.1.1.1', fixed_ip.address)
        self.assertEqual('host1', fixed_ip.host)

    @attr(kind='small')
    def test_fixed_ip_update_db_not_found(self):
        # test and assert
        self.assertRaises(exception.FixedIpNotFoundForAddress,
                          db.api.fixed_ip_update,
                          self.context, '2.0.0.0', {'host': 'host1'})

    @attr(kind='small')
    def test_virtual_interface_create(self):
        """
        virtual_interface_create
        """
        # test and assert
        result = self.db.api.virtual_interface_create(self.context,
                                                      {'id': 1,
                                                       'instance_id': 1})
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)

        virtual_interface = self.db.api.virtual_interface_get(self.context, 1)
        self.assertTrue(virtual_interface is not None)

    @attr(kind='small')
    def test_virtual_interface_create_db_duplicate(self):
        # setup
        self.db.api.virtual_interface_create(self.context,
                                             {'id': 1, 'instance_id': 1,
                                              'address': '10.1.1.1'})

        # test and assert
        self.assertRaises(exception.Duplicate,
                          self.db.api.virtual_interface_create,
                          self.context,
                          {'id': 1, 'instance_id': 1, 'address': '10.1.1.1'})

    @attr(kind='small')
    def test_virtual_interface_update(self):
        """
        virtual_interface_update
        """
        # setup
        self.db.api.virtual_interface_create(self.context,
                                             {'id': 1, 'instance_id': 1})

        # test and assert
        self.db.api.virtual_interface_update(self.context, 1,
                                             {'uuid': 'uuid1'})

        virtual_interface = self.db.api.virtual_interface_get(self.context, 1)
        self.assertTrue(virtual_interface is not None)
        self.assertEqual(1, virtual_interface.id)
        self.assertEqual('uuid1', virtual_interface.uuid)

    @attr(kind='small')
    def test_virtual_interface_update_db_not_found(self):
        # test and assert
        self.assertRaises(exception.NotFound,
                          self.db.api.virtual_interface_update,
                          self.context, 1, {'uuid': 'uuid1'})

    @attr(kind='small')
    def test_virtual_interface_get(self):
        """
        virtual_interface_get
        """
        # setup
        self.db.api.virtual_interface_create(self.context,
                                             {'id': 1, 'instance_id': 1})

        # test and assert
        result = self.db.api.virtual_interface_get(self.context, 1)
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)
        self.assertEqual(1, result.instance_id)

    @attr(kind='small')
    def test_virtual_interface_get_db_not_found(self):
        # test and assert
        self.assertRaises(exception.NotFound,
                          self.db.api.virtual_interface_get,
                          self.context,
                                                    1)

    @attr(kind='small')
    def test_virtual_interface_get_by_address(self):
        """
        virtual_interface_get_by_address
        """
        # setup
        self.db.api.virtual_interface_create(self.context,
                                             {'id': 1,
                                              'instance_id': 1,
                                              'address': '10.1.1.1'})

        # test and assert
        result = self.db.api.virtual_interface_get_by_address(
                                            self.context, '10.1.1.1')
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)
        self.assertEqual('10.1.1.1', result.address)

    @attr(kind='small')
    def test_virtual_interface_get_by_address_db_not_found(self):
        # test and assert
        result = self.db.api.virtual_interface_get_by_address(
                                            self.context, '10.1.1.1')
        self.assertTrue(result is None)

    @attr(kind='small')
    def test_virtual_interface_get_by_uuid(self):
        """
        virtual_interface_get_by_uuid
        """
        # setup
        self.db.api.virtual_interface_create(self.context,
                                             {'id': 1,
                                              'instance_id': 1,
                                              'uuid': 'uuid1'})

        # test and assert
        result = self.db.api.virtual_interface_get_by_uuid(
                                            self.context, 'uuid1')
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)
        self.assertEqual('uuid1', result.uuid)

    @attr(kind='small')
    def test_virtual_interface_get_by_uuid_db_not_found(self):
        """
        should be raise exception
        """
        # test and assert
        result = self.db.api.virtual_interface_get_by_uuid(
                                            self.context, 'uuid1')
        self.assertTrue(result is None)

    @attr(kind='small')
    def test_virtual_interface_get_by_fixed_ip(self):
        """
        virtual_interface_get_by_fixed_ip
        """
#        raise SkipTest("FIXME InvalidRequestError: \
#            Entity 'Mapper|VirtualInterface|virtual_interfaces' \
#            has no property 'fixed_ip_id'")
        # setup
        self.db.api.network_create_safe(self.context, {'id': 100})
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.1', 'network_id': 100})
        self.db.api.virtual_interface_create(self.context,
                                    {'id': 1, 'instance_id': 1,
                                     'network_id': 100})

        # test and assert
        result = self.db.api.virtual_interface_get_by_fixed_ip(
                                            self.context, '10.1.1.1')
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)
        self.assertEqual(100, result.network.id)

    @attr(kind='small')
    def test_virtual_interface_get_by_fixed_ip_db_not_found(self):
        """
        virtual_interface_get_by_fixed_ip
        """
#        raise SkipTest("FIXME InvalidRequestError: \
#            Entity 'Mapper|VirtualInterface|virtual_interfaces' \
#            has no property 'fixed_ip_id'")
        # test and assert
        # FIXME InvalidRequestError:
        # Entity 'Mapper|VirtualInterface|virtual_interfaces'
        # has no property 'fixed_ip_id'
        result = db.api.virtual_interface_get_by_fixed_ip(
                                            self.context, '2.0.0.0')
        self.assertTrue(result is None)

    @attr(kind='small')
    def test_virtual_interface_get_by_instance(self):
        """
        virtual_interface_get_by_instance
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.virtual_interface_create(self.context,
                                             {'id': 1,
                                              'instance_id': 1})

        # test and assert
        result = self.db.api.virtual_interface_get_by_instance(self.context, 1)
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)
        self.assertEqual(1, result[0].instance_id)

    @attr(kind='small')
    def test_virtual_interface_get_by_instance_db_not_found(self):
        # setup
        self.db.api.instance_create(self.context, {'id': 1})

        # test and assert
        result = self.db.api.virtual_interface_get_by_instance(self.context, 1)
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_virtual_interface_get_by_instance_and_network(self):
        """
        virtual_interface_get_by_instance_and_network
        """
        # setup
        self.db.api.virtual_interface_create(self.context,
                                             {'id': 1,
                                              'instance_id': 1,
                                              'network_id': 1})

        # test and assert
        result = self.db.api.virtual_interface_get_by_instance_and_network(
                                                            self.context, 1, 1)
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)
        self.assertEqual(1, result.instance_id)
        self.assertEqual(1, result.network_id)

    @attr(kind='small')
    def test_virtual_interface_get_by_instance_and_network_db_not_found(self):
        # test and assert
        result = self.db.api.virtual_interface_get_by_instance_and_network(
                                                            self.context, 1, 1)
        self.assertTrue(result is None)

    @attr(kind='small')
    def test_virtual_interface_get_by_network(self):
        """
        virtual_interface_get_by_network
        """
        # setup
        self.db.api.virtual_interface_create(self.context,
                                             {'id': 1, 'instance_id': 1,
                                              'network_id': 1})

        # test and assert
        result = self.db.api.virtual_interface_get_by_network(self.context, 1)
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)
        self.assertEqual(1, result[0].network_id)

    @attr(kind='small')
    def test_virtual_interface_get_by_network_db_not_found(self):
        # test and assert
        result = self.db.api.virtual_interface_get_by_network(self.context, 1)
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_virtual_interface_delete(self):
        """
        virtual_interface_delete
        """
        # setup
        self.db.api.virtual_interface_create(self.context,
                                             {'id': 1, 'instance_id': 1})

        # test and assert
        result = self.db.api.virtual_interface_delete(self.context, 1)
        self.assertTrue(result is None)

        self.assertRaises(exception.NotFound,
                          self.db.api.virtual_interface_get,
                          self.context,
                                                    1)

    @attr(kind='small')
    def test_virtual_interface_delete_db_not_found(self):
#        raise SkipTest("UnmappedInstanceError:\
#            Class '__builtin__.NoneType' is not mapped")
        # test and assert
        # FIXME VirtualInterfaceNotFound does not exist.
        self.assertRaises(exception.NotFound,
                          self.db.api.virtual_interface_delete,
                          self.context, 1)

    @attr(kind='small')
    def test_virtual_interface_delete_by_instance(self):
        """
        virtual_interface_delete_by_instance
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.virtual_interface_create(self.context,
                                             {'id': 1, 'instance_id': 1})

        # test and assert
        result = self.db.api.virtual_interface_delete_by_instance(
                                                    self.context, 1)
        self.assertTrue(result is None)

        self.assertRaises(exception.NotFound,
                          self.db.api.virtual_interface_get,
                          self.context,
                                                    1)

    @attr(kind='small')
    def test_virtual_interface_delete_by_instance_db_not_found(self):
        # setup
        self.db.api.instance_create(self.context, {'id': 1})

        # test and assert
        result = self.db.api.virtual_interface_delete_by_instance(
                                                    self.context, 1)
        self.assertTrue(result is None)

    @attr(kind='small')
    def test_instance_create(self):
        """
        instance_create
        """
        # test and assert
        result = self.db.api.instance_create(self.context, {'id': 1})
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)

        instance = db.api.instance_get(self.context, result.id)
        self.assertTrue(instance is not None)
        self.assertEqual(1, instance.id)

    @attr(kind='small')
    def test_instance_create_parameter_meta(self):
        """
        instance_create
        """
        # test and assert
        meta = dict(key1='value1', key2='value2')
        result = self.db.api.instance_create(self.context, {'id': 1,
                                                            'metadata': meta})
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)

        instance = db.api.instance_get(self.context, result.id)
        self.assertTrue(instance is not None)
        self.assertEqual(1, instance.id)

        self.assertEqual(True, instance['metadata'][0].key in ('key1', 'key2'))
        self.assertEqual(True, instance['metadata'][1].key in ('key1', 'key2'))

    @attr(kind='small')
    def test_instance_create_db_duplicate(self):
        # setup
        self.db.api.instance_create(self.context, {'id': 1})

        # test and assert
        self.assertRaises(exception.Duplicate,
                          self.db.api.instance_create,
                          self.context, {'id': 1})

    @attr(kind='small')
    def test_instance_data_get_for_project(self):
        """
        instance_data_get_for_project
        instance_data is sum of instance, sum of vcpus, sum of memory_mb
        """
        # setup
        self.db.api.instance_create(self.context,
                                    {'id': 1,
                                     'project_id': 'project1',
                                     'vcpus': 2,
                                     'memory_mb': 3})

        # test and assert
        result = self.db.api.instance_data_get_for_project(
                                            self.context, 'project1')
        self.assertTrue(result is not None)
        self.assertEqual((1, 2, 3), result)

    @attr(kind='small')
    def test_instance_data_get_for_project_db_not_found(self):
        # test and assert
        result = self.db.api.instance_data_get_for_project(
                                            self.context, 'project1')
        self.assertTrue(result is not None)
        self.assertEqual((0, 0, 0), result)

    @attr(kind='small')
    def test_instance_destroy(self):
        """
        instance_destroy
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1})

        # test and assert
        result = self.db.api.instance_destroy(self.context, 1)
        self.assertTrue(result is None)

        self.assertRaises(exception.InstanceNotFound,
                          self.db.api.instance_get,
                          self.context, 1)

    @attr(kind='small')
    def test_instance_destroy_db_not_found(self):
        # test and assert
        # setup
        self.db.api.instance_create(self.context, {'id': 1})

        # test and assert
        self.db.api.instance_destroy(self.context, 2)
        result = self.db.api.instance_get(self.context, 1)
        self.assertTrue(result is not None)

    @attr(kind='small')
    def test_instance_stop(self):
        """
        instance_stop
        """
        # setup
        self.db.api.instance_create(self.context,
                                    {'id': 1,
                                     'host': 'host1',
                                     'task_state': 'task_state1'})

        # test and assert
        result = self.db.api.instance_stop(self.context, 1)
        self.assertTrue(result is None)

        instance = self.db.api.instance_get(self.context, 1)
        self.assertTrue(instance is not None)
        self.assertEqual(None, instance.host)
        self.assertEqual(vm_states.STOPPED, instance.vm_state)
        self.assertEqual(None, instance.task_state)
        self.assertEqual(None, instance.updated_at)

    @attr(kind='small')
    def test_instance_stop_db_not_found(self):
        # setup
        self.db.api.instance_create(self.context,
                                    {'id': 1,
                                     'host': 'host1',
                                     'task_state': 'task_state1'})

        # test and assert
        self.db.api.instance_stop(self.context, 2)

        instance = self.db.api.instance_get(self.context, 1)
        self.assertTrue(instance is not None)
        self.assertEqual('host1', instance.host)
        self.assertNotEqual(vm_states.STOPPED, instance.vm_state)
        self.assertEqual('task_state1', instance.task_state)

    @attr(kind='small')
    def test_instance_get_by_uuid(self):
        """
        instance_get_by_uuid
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1, 'uuid': 'uuid1'})

        # test and assert
        result = self.db.api.instance_get_by_uuid(self.context, 'uuid1')
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)
        self.assertEqual('uuid1', result.uuid)

    @attr(kind='small')
    def test_instance_get_by_uuid_db_not_found(self):
        # test and assert
        self.assertRaises(exception.InstanceNotFound,
                          self.db.api.instance_get_by_uuid,
                          self.context, 'uuid1')

    @attr(kind='small')
    def test_instance_get(self):
        """
        instance_get
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1})

        # test and assert
        result = self.db.api.instance_get(self.context, 1)
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)

    @attr(kind='small')
    def test_instance_get_parameter_context(self):
        """
        instance_get
        """
        # setup
        normal_ctx = context.RequestContext(self.user_id, self.project_id,
                                              is_admin=False)
        self.db.api.instance_create(self.context, {'id': 1,
                                            'project_id': self.project_id})

        # test and assert
        result = self.db.api.instance_get(normal_ctx, 1)
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)

    @attr(kind='small')
    def test_instance_get_db_not_found(self):
        # test and assert
        self.assertRaises(exception.InstanceNotFound,
                          self.db.api.instance_get,
                          self.context, 1)

    @attr(kind='small')
    def test_instance_get_all(self):
        """
        instance_get_all
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1})

        # test and assert
        result = self.db.api.instance_get_all(self.context)
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)

    @attr(kind='small')
    def test_instance_get_all_db_not_found(self):
        # test and assert
        result = self.db.api.instance_get_all(self.context)
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_instance_get_all_by_filters_db_not_found(self):
        # test and assert
        result = self.db.api.instance_get_all_by_filters(self.context, {})
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_instance_get_active_by_window(self):
        """
        instance_get_active_by_window
        """
        # setup
        self.db.api.instance_create(
                            self.context,
                            {'id': 1,
                             'launched_at': datetime.datetime(2011, 1, 1),
                             'terminated_at': datetime.datetime(2011, 1, 4),
                             'project_id': 'project1'})

        # test and assert
        result = self.db.api.instance_get_active_by_window(
                                    self.context,
                                    datetime.datetime(2011, 1, 2),
                                    datetime.datetime(2011, 1, 3),
                                    'project1')
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)

    @attr(kind='small')
    def test_instance_get_active_by_window_parameter_end(self):
        """
        instance_get_active_by_window
        """
        # setup
        self.db.api.instance_create(
                            self.context,
                            {'id': 1,
                             'launched_at': datetime.datetime(2011, 1, 1)})

        # test and assert
        result = self.db.api.instance_get_active_by_window(
                                    self.context,
                                    datetime.datetime(2011, 1, 2),
                                    None,
                                    None)
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)

    @attr(kind='small')
    def test_instance_get_active_by_window_db_not_found(self):
        # setup
        self.db.api.instance_create(
                            self.context,
                            {'id': 1,
                             'launched_at': datetime.datetime(2010, 1, 1),
                             'terminated_at': datetime.datetime(2010, 1, 4),
                             'project_id': 'project1'})

        # test and assert
        result = self.db.api.instance_get_active_by_window(
                                    self.context,
                                    datetime.datetime(2011, 1, 2),
                                    datetime.datetime(2011, 1, 3),
                                    'project1')
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_instance_get_active_by_window_joined(self):
        """
        instance_get_active_by_window_joined
        """
        # setup
        self.db.api.instance_create(
                            self.context,
                            {'id': 1,
                             'launched_at': datetime.datetime(2011, 1, 1),
                             'terminated_at': datetime.datetime(2011, 1, 4),
                             'project_id': 'project1'})

        # test and assert
        result = self.db.api.instance_get_active_by_window_joined(
                                    self.context,
                                    datetime.datetime(2011, 1, 2),
                                    datetime.datetime(2011, 1, 3),
                                    'project1')
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)

    @attr(kind='small')
    def test_instance_get_active_by_window_joined_parameter_end(self):
        """
        instance_get_active_by_window_joined
        """
        # setup
        self.db.api.instance_create(
                            self.context,
                            {'id': 1,
                             'launched_at': datetime.datetime(2011, 1, 1)})

        # test and assert
        result = self.db.api.instance_get_active_by_window_joined(
                                    self.context,
                                    datetime.datetime(2011, 1, 2),
                                    None,
                                    None)
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)

    @attr(kind='small')
    def test_instance_get_active_by_window_joined_db_not_found(self):
        # mock
        # setup
        self.db.api.instance_create(
                            self.context,
                            {'id': 1,
                             'launched_at': datetime.datetime(2010, 1, 1),
                             'terminated_at': datetime.datetime(2010, 1, 4),
                             'project_id': 'project1'})

        # test and assert
        result = self.db.api.instance_get_active_by_window_joined(
                                    self.context,
                                    datetime.datetime(2011, 1, 2),
                                    datetime.datetime(2011, 1, 3),
                                    'project1')
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_instance_get_all_by_user(self):
        """
        instance_get_all_by_user
        """
        # setup
        self.db.api.instance_create(self.context,
                                    {'id': 1, 'user_id': 'user1'})

        # test and assert
        result = self.db.api.instance_get_all_by_user(self.context, 'user1')
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)
        self.assertEqual('user1', result[0].user_id)

    @attr(kind='small')
    def test_instance_get_all_by_user_db_not_found(self):
        # setup
        self.db.api.instance_create(self.context,
                                    {'id': 1, 'user_id': 'user1'})

        # test and assert
        result = db.api.instance_get_all_by_user(self.context, 'user2')
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_instance_get_all_by_project(self):
        """
        instance_get_all_by_project
        """
        # setup
        self.db.api.instance_create(self.context,
                                    {'id': 1, 'project_id': 'project1'})

        # test and assert
        result = self.db.api.instance_get_all_by_project(
                                    self.context, 'project1')
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)
        self.assertEqual('project1', result[0].project_id)

    @attr(kind='small')
    def test_instance_get_all_by_project_db_not_found(self):
        # setup
        self.db.api.instance_create(self.context,
                                    {'id': 1, 'project_id': 'project1'})

        # test and assert
        result = db.api.instance_get_all_by_project(self.context, 'project2')
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_instance_get_all_by_host(self):
        """
        instance_get_all_by_host
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1, 'host': 'host1'})

        # test and assert
        result = db.api.instance_get_all_by_host(self.context, 'host1')
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)
        self.assertEqual('host1', result[0].host)

    @attr(kind='small')
    def test_instance_get_all_by_host_db_not_found(self):
        # setup
        self.db.api.instance_create(self.context, {'id': 1, 'host': 'host1'})

        # test and assert
        result = self.db.api.instance_get_all_by_host(self.context, 'host2')
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_instance_get_all_by_reservation(self):
        """
        instance_get_all_by_reservation
        """
        # setup
        self.db.api.instance_create(self.context,
                                    {'id': 1,
                                     'reservation_id': 'reservation1'})

        # test and assert
        result = db.api.instance_get_all_by_reservation(
                                    self.context, 'reservation1')
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)
        self.assertEqual('reservation1', result[0].reservation_id)

    @attr(kind='small')
    def test_instance_get_all_by_reservation_parameter_context(self):
        """
        instance_get_all_by_reservation
        """
        # setup
        normal_ctx = context.RequestContext(self.user_id, self.project_id,
                                              is_admin=False)
        self.db.api.instance_create(self.context,
                                    {'id': 1,
                                     'reservation_id': 'reservation1',
                                     'project_id': self.project_id})

        # test and assert
        result = db.api.instance_get_all_by_reservation(
                                    normal_ctx, 'reservation1')
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)
        self.assertEqual('reservation1', result[0].reservation_id)

    @attr(kind='small')
    def test_instance_get_all_by_reservation_db_not_found(self):
        # setup
        self.db.api.instance_create(self.context,
                                    {'id': 1,
                                     'reservation_id': 'reservation1'})
        # test and assert
        result = self.db.api.instance_get_all_by_reservation(
                                    self.context, 'reservation2')
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_instance_get_by_fixed_ip(self):
        """
        instance_get_by_fixed_ip
        """
        # setup
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.1', 'instance_id': 1})
        self.db.api.instance_create(self.context, {'id': 1})

        # test and assert
        result = self.db.api.instance_get_by_fixed_ip(self.context, '10.1.1.1')
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)

    @attr(kind='small')
    def test_instance_get_by_fixed_ip_db_not_found(self):
        # mock
        self.mox.StubOutWithMock(db.api.IMPL, 'instance_get_by_fixed_ip')
        db.api.IMPL.instance_get_by_fixed_ip(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        # test and assert
        result = db.api.instance_get_by_fixed_ip(self.context, '2.0.0.0')
        self.assertTrue(result is None)

    @attr(kind='small')
    def test_instance_get_by_fixed_ipv6(self):
        """
        instance_get_by_fixed_ipv6
        """
        # mock
        self.mox.StubOutWithMock(db.api.IMPL, 'instance_create')
        db.api.IMPL.instance_create(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.StubOutWithMock(db.api.IMPL, 'virtual_interface_create')
        db.api.IMPL.virtual_interface_create(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.StubOutWithMock(db.api.IMPL, 'instance_get_by_fixed_ipv6')
        db.api.IMPL.instance_get_by_fixed_ipv6(mox.IgnoreArg(),
                                               mox.IgnoreArg()).\
                AndReturn({'id': 1})
        self.mox.ReplayAll()

        # setup
        db.api.instance_create(self.context, {'id': 1})
        db.api.virtual_interface_create(
                self.context, {'id': 1,
                               'instance_id': 1,
                               'address': '02:00:00:00:00:00'})
        # test and assert
        result = db.api.instance_get_by_fixed_ipv6(
                                    self.context, '3:0:0:0:0:0:0:0')
        self.assertTrue(result is not None)
        self.assertEqual(1, result['id'])

    @attr(kind='small')
    def test_instance_get_by_fixed_ipv6_db_not_found(self):
        # mock
        self.mox.StubOutWithMock(db.api.IMPL, 'instance_get_by_fixed_ipv6')
        db.api.IMPL.instance_get_by_fixed_ipv6(
                                    mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        # test and assert
        result = db.api.instance_get_by_fixed_ipv6(
                                self.context, '3:0:0:0:0:0:0:0')
        self.assertTrue(result is None)

    @attr(kind='small')
    def test_instance_get_fixed_addresses(self):
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.1', 'instance_id': 1})

        # test and assert
        result = self.db.api.instance_get_fixed_addresses(self.context, 1)
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual('10.1.1.1', result[0])

    @attr(kind='small')
    def test_instance_get_fixed_addresses_db_not_found(self):
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.1', 'instance_id': 1})

        # test and assert
        self.assertRaises(exception.InstanceNotFound,
                          db.api.instance_get_fixed_addresses,
                          self.context, 2)

    @attr(kind='small')
    def test_instance_get_fixed_addresses_db_not_found_ip(self):
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.1', 'instance_id': 2})

        # test and assert
        ref = db.api.instance_get_fixed_addresses(self.context, 1)
        self.assertEqual([], ref)

    @attr(kind='small')
    def test_instance_get_floating_address(self):
        """
        instance_get_floating_address
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.fixed_ip_create(self.context,
                                    {'id': 100,
                                     'instance_id': 1})
        self.db.api.floating_ip_create(self.context,
                                       {'id': 1,
                                        'fixed_ip_id': 100,
                                        'address': '1.0.0.0'})

        # test and assert
        result = self.db.api.instance_get_floating_address(self.context, 1)
        self.assertTrue(result is not None)
        self.assertEqual('1.0.0.0', result)

    @attr(kind='small')
    def test_instance_get_floating_address_db_not_found(self):
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.fixed_ip_create(self.context,
                                    {'id': 100, 'instance_id': 1})
        self.db.api.floating_ip_create(self.context,
                                       {'id': 1,
                                        'fixed_ip_id': 100,
                                        'address': '1.0.0.0'})

        # test and assert
        self.assertRaises(exception.FixedIpNotFoundForInstance,
                          db.api.instance_get_floating_address,
                          self.context, 2)

    @attr(kind='small')
    def test_instance_get_floating_address_db_not_found_ip(self):
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.fixed_ip_create(self.context,
                                    {'id': 100, 'instance_id': 1})
        self.db.api.floating_ip_create(self.context,
                                       {'id': 1,
                                        'fixed_ip_id': 200,
                                        'address': '1.0.0.0'})

        # test and assert
        ref = db.api.instance_get_floating_address(self.context, 1)
        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_instance_get_project_vpn_db_not_found(self):
        # mock
        self.mox.StubOutWithMock(db.api.IMPL, 'instance_get_project_vpn')
        db.api.IMPL.instance_get_project_vpn(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        # test and assert
        result = db.api.instance_get_project_vpn(self.context, 'project1')
        self.assertTrue(result is None)

    @attr(kind='small')
    def test_instance_set_state(self):
        """
        instance_set_state
        """
#        raise SkipTest("Not implemented in sqlalchemy.api.")

    @attr(kind='small')
    def test_instance_set_state_db_not_found(self):
#        raise SkipTest("Not implemented in sqlalchemy.api.")

    @attr(kind='small')
    def test_instance_update(self):
        """
        instance_update
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1})

        # test and assert
        result = self.db.api.instance_update(self.context, 1,
                                             {'host': 'host1'})
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)

        instance = self.db.api.instance_get(self.context, 1)
        self.assertTrue(instance is not None)
        self.assertEqual('host1', instance.host)

    @attr(kind='small')
    def test_instance_update_meta(self):
        """
        instance_update
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1})

        # test and assert
        meta = dict(key1='value1')
        result = self.db.api.instance_update(self.context, 1,
                                        {'host': 'host1', 'metadata': meta})
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)

        instance = self.db.api.instance_get(self.context, 1)
        self.assertTrue(instance is not None)
        self.assertEqual('host1', instance.host)
        self.assertEqual('key1', instance['metadata'][0].key)

    @attr(kind='small')
    def test_instance_update_parameter_uuid(self):
        """
        instance_update
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        instance = self.db.api.instance_get(self.context, 1)

        # test and assert
        result = self.db.api.instance_update(self.context, instance['uuid'],
                                             {'host': 'host1'})
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)

        instance = self.db.api.instance_get(self.context, 1)
        self.assertTrue(instance is not None)
        self.assertEqual('host1', instance.host)

    @attr(kind='small')
    def test_instance_update_parameter_uuid_meta(self):
        """
        instance_update
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        instance = self.db.api.instance_get(self.context, 1)

        # test and assert
        meta = dict(key1='value1')
        result = self.db.api.instance_update(self.context, instance['uuid'],
                                        {'host': 'host1', 'metadata': meta})
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)

        instance = self.db.api.instance_get(self.context, 1)
        self.assertTrue(instance is not None)
        self.assertEqual('host1', instance.host)

    @attr(kind='small')
    def test_instance_update_db_not_found(self):
        # test and assert
        self.assertRaises(exception.InstanceNotFound,
                          self.db.api.instance_update,
                          self.context, 1, {'host': 'host1'})

    @attr(kind='small')
    def test_instance_add_security_group(self):
        """
        instance_add_security_group
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.security_group_create(self.context, {'id': 1})

        # test and assert
        result = self.db.api.instance_add_security_group(self.context, 1, 1)
        self.assertTrue(result is None)

        security_group_list = db.api.security_group_get_by_instance(
                                                        self.context, 1)
        self.assertEqual(1, len(security_group_list))
        self.assertEqual(1, security_group_list[0].id)
        self.assertEqual(1, security_group_list[0].instances[0].id)

    @attr(kind='small')
    def test_instance_add_security_group_db_not_found(self):
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.security_group_create(self.context, {'id': 1})
        # test and assert
        self.assertRaises(exception.InstanceNotFound,
                          db.api.instance_add_security_group,
                          self.context, 2, 1)

    @attr(kind='small')
    def test_instance_remove_security_group(self):
        """
        instance_remove_security_group
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.security_group_create(self.context, {'id': 1})
        self.db.api.instance_add_security_group(self.context, 1, 1)

        # test and assert
        result = self.db.api.instance_remove_security_group(
                                            self.context, 1, 1)
        self.assertTrue(result is None)

        security_group_list = self.db.api.security_group_get_by_instance(
                                            self.context, 1)
        self.assertEqual(0, len(security_group_list))

    @attr(kind='small')
    def test_instance_remove_security_group_db_not_found(self):
        """
        should be raise exception.
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.security_group_create(self.context, {'id': 1})
        self.db.api.instance_add_security_group(self.context, 1, 1)

        # test and assert
        result = self.db.api.instance_remove_security_group(
                                            self.context, 1, 2)
        self.assertTrue(result is None)

    @attr(kind='small')
    def test_instance_remove_security_group_db_not_found_ins(self):
        """
        should be raise exception.
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.security_group_create(self.context, {'id': 1})
        self.db.api.instance_add_security_group(self.context, 1, 1)

        # test and assert
        result = self.db.api.instance_remove_security_group(
                                            self.context, 2, 1)
        self.assertTrue(result is None)

    @attr(kind='small')
    def test_instance_action_create(self):
        """
        instance_action_create
        """
        # test and assert
        result = self.db.api.instance_action_create(self.context,
                                                    {'id': 1,
                                                     'instance_id': 1})
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)

        instance_action_list = self.db.api.instance_get_actions(
                                            self.context, result.id)
        self.assertTrue(instance_action_list is not None)
        self.assertEqual(1, len(instance_action_list))
        self.assertEqual(1, instance_action_list[0].id)
        self.assertEqual(1, instance_action_list[0].instance_id)

    @attr(kind='small')
    def test_instance_action_create_db_duplicate(self):
        # setup
        self.db.api.instance_action_create(self.context, {'id': 1})

        # test and assert
        self.assertRaises(exception.Duplicate,
                          self.db.api.instance_action_create,
                          self.context, {'id': 1})

    @attr(kind='small')
    def test_instance_get_actions(self):
        """
        instance_get_actions
        """
        # setup
        self.db.api.instance_action_create(self.context,
                                           {'id': 1, 'instance_id': 1})

        # test and assert
        result = self.db.api.instance_get_actions(self.context, 1)
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)
        self.assertEqual(1, result[0].instance_id)

    @attr(kind='small')
    def test_instance_get_actions_parameter_uuid(self):
        """
        instance_get_actions
        """
        # setup
        self.db.api.instance_create(self.context, {'id': 1})
        ref = self.db.api.instance_action_create(self.context,
                                           {'id': 1, 'instance_id': 1})

        instance = self.db.api.instance_get(self.context, ref['instance_id'])
        # test and assert
        result = self.db.api.instance_get_actions(self.context,
                                                  instance['uuid'])
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)
        self.assertEqual(1, result[0].instance_id)

    @attr(kind='small')
    def test_instance_get_actions_db_not_found(self):
        # setup
        self.db.api.instance_action_create(self.context,
                                           {'id': 1, 'instance_id': 1})

        # test and assert
        result = db.api.instance_get_actions(self.context, 2)
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_key_pair_create(self):
        """
        key_pair_create
        """
        # test and assert
        result = self.db.api.key_pair_create(self.context,
                                             {'id': 1,
                                              'user_id': 'user1',
                                              'name': 'name1'})
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)

        key_pair = self.db.api.key_pair_get(self.context, 'user1', 'name1')
        self.assertTrue(key_pair is not None)

    @attr(kind='small')
    def test_key_pair_create_db_duplicate(self):
        # setup
        self.db.api.key_pair_create(self.context, {'id': 1})

        # test and assert
        self.assertRaises(exception.Duplicate,
                          self.db.api.key_pair_create,
                          self.context, {'id': 1})

    @attr(kind='small')
    def test_key_pair_destroy(self):
        """
        key_pair_destroy
        """
        # setup
        self.db.api.key_pair_create(self.context,
                                    {'id': 1,
                                     'user_id': 'user1',
                                     'name': 'name1'})

        # test and assert
        result = self.db.api.key_pair_destroy(self.context, 'user1', 'name1')
        self.assertTrue(result is None)

        self.assertRaises(exception.KeypairNotFound,
                          self.db.api.key_pair_get,
                          self.context, 'user1', 'name1')

    @attr(kind='small')
    def test_key_pair_destroy_db_not_found(self):
        # setup
        self.db.api.key_pair_create(self.context,
                                    {'id': 1,
                                     'user_id': 'user1',
                                     'name': 'name1'})
        # test and assert
        self.assertRaises(exception.KeypairNotFound,
                          self.db.api.key_pair_destroy,
                          self.context, 'user2', 'name2')

    @attr(kind='small')
    def test_key_pair_destroy_all_by_user(self):
        """
        key_pair_destroy_all_by_user
        """
        # setup
        self.db.api.key_pair_create(self.context,
                                    {'id': 1,
                                     'user_id': 'user1',
                                     'name': 'name1'})

        # test and assert
        result = self.db.api.key_pair_destroy_all_by_user(
                                            self.context, 'user1')
        self.assertTrue(result is None)

        # test and assert
        self.assertRaises(exception.KeypairNotFound,
                          self.db.api.key_pair_get,
                          self.context, 'user1', 'name1')

    @attr(kind='small')
    def test_key_pair_destroy_all_by_user_db_not_found(self):
        # setup
        self.db.api.key_pair_create(self.context,
                                    {'id': 1,
                                     'user_id': 'user1',
                                     'name': 'name1'})

        # test and assert
        result = db.api.key_pair_destroy_all_by_user(self.context, 'user2')
        self.assertTrue(result is None)

        key_pair = self, db.api.key_pair_get(self.context, 'user1', 'name1')
        self.assertTrue(key_pair is not None)

    @attr(kind='small')
    def test_key_pair_get(self):
        """
        key_pair_get
        """
        # setup
        self.db.api.key_pair_create(self.context,
                                    {'id': 1,
                                     'user_id': 'user1',
                                     'name': 'name1'})

        # test and assert
        result = self.db.api.key_pair_get(self.context, 'user1', 'name1')
        self.assertTrue(result is not None)
        self.assertEqual(1, result.id)
        self.assertEqual('user1', result.user_id)
        self.assertEqual('name1', result.name)

    @attr(kind='small')
    def test_key_pair_get_db_not_found(self):
        # setup
        self.db.api.key_pair_create(self.context,
                                    {'id': 1,
                                     'user_id': 'user1',
                                     'name': 'name1'})

        # test and assert
        self.assertRaises(exception.KeypairNotFound,
                          self.db.api.key_pair_get,
                          self.context, 'user2', 'name1')

    @attr(kind='small')
    def test_key_pair_get_all_by_user(self):
        """
        key_pair_get_all_by_user
        """
        # setup
        self.db.api.key_pair_create(self.context,
                                    {'id': 1,
                                     'user_id': 'user1'})

        # test and assert
        result = self.db.api.key_pair_get_all_by_user(self.context, 'user1')
        self.assertTrue(result is not None)
        self.assertTrue(isinstance(result, list))
        self.assertEqual(1, len(result))
        self.assertEqual(1, result[0].id)
        self.assertEqual('user1', result[0].user_id)

    @attr(kind='small')
    def test_key_pair_get_all_by_user_db_not_found(self):
        # setup
        self.db.api.key_pair_create(self.context,
                                    {'id': 1,
                                     'user_id': 'user1'})

        # test and assert
        result = db.api.key_pair_get_all_by_user(self.context, 'user2')
        self.assertTrue(result is not None)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_network_associate(self):
        # setup
        # 'id' == 1 and 'project' == None is already exist
        # test and assert
        result = self.db.api.network_associate(self.context, 'project1', False)
        self.assertEqual('project1', result.project_id)
        network = self.db.api.network_get(self.context, 1)
        self.assertEqual('project1', network.project_id)

    @attr(kind='small')
    def test_network_associate_with_force(self):
#        raise SkipTest("network record should be store when associate called")
        # setup
        self.db.api.network_create_safe(self.context,
                                        {'id': 100,
                                         'project_id': 'other_project'})

        # test and assert
        result = self.db.api.network_associate(
                                    self.context, 'project1', True)
        self.assertEqual('project1', result.project_id)
        network = self.db.api.network_get(self.context, 100)
        self.assertEqual('project1', network.project_id)

    @attr(kind='small')
    def test_network_associate_with_no_more_networks(self):
        # setup
        networks = self.db.api.network_get_all(self.context)
        for nw in networks:
            self.db.api.network_update(self.context, nw.id,
                                       {'project_id': 'project'})
        # test and assert
        self.assertRaises(db.NoMoreNetworks,
                         self.db.api.network_associate,
                         self.context, 'project1', False)

    @attr(kind='small')
    def test_network_count(self):
        """
        some networks already registered, when using sqlite mock.
        """
        result = self.db.api.network_count(self.context)
        self.assertTrue(result is not None)

    @attr(kind='small')
    def test_network_count_allocated_ips(self):
        """
        resolved count from FixedIp table. (not networks)
        """
        # setup
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.1',
                                     'network_id': 100,
                                     'allocated': True})
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.2',
                                     'network_id': 100,
                                     'allocated': False})

        # test and assert
        result = self.db.api.network_count_allocated_ips(self.context, 100)
        self.assertEqual(1, result)

    @attr(kind='small')
    def test_network_count_allocated_ips_db_not_found(self):
        # setup
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.1',
                                     'network_id': 100,
                                     'allocated': True})
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.2',
                                     'network_id': 100,
                                     'allocated': False})

        # test and assert
        result = self.db.api.network_count_allocated_ips(self.context, 99)
        self.assertEqual(0, result)

    @attr(kind='small')
    def test_network_count_available_ips(self):
        """
        resolved count from FixedIp table. (not networks)
        """
        # setup
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.1',
                                     'network_id': 100,
                                     'allocated': True})
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.2',
                                     'network_id': 100,
                                     'allocated': False})
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.3',
                                     'network_id': 100,
                                     'allocated': False})

        # test and assert
        result = self.db.api.network_count_available_ips(self.context, 100)
        self.assertEqual(2, result)

    @attr(kind='small')
    def test_network_count_available_ips_db_not_found(self):
        """
        all network ips are allocated.
        """
        # setup
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.1',
                                     'network_id': 100,
                                     'allocated': True})
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.2',
                                     'network_id': 100,
                                     'allocated': True})
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.3',
                                     'network_id': 100,
                                     'allocated': True})

        # test and assert
        result = self.db.api.network_count_available_ips(self.context, 100)
        self.assertEqual(0, result)

    @attr(kind='small')
    def test_network_count_reserved_ips(self):
        """
        resolved count from FixedIp table. (not networks)
        """
        # setup
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.1',
                                     'network_id': 100,
                                     'reserved': True})
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.2',
                                     'network_id': 100,
                                     'reserved': False})
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.3',
                                     'network_id': 100,
                                     'reserved': False})

        # test and assert
        result = self.db.api.network_count_reserved_ips(self.context, 100)
        self.assertEqual(1, result)

    @attr(kind='small')
    def test_network_count_reserved_ips_db_not_found(self):
        """
        resolved count from FixedIp table. (not networks)
        """
        # setup
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.1',
                                     'network_id': 100,
                                     'reserved': True})
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.2',
                                     'network_id': 100,
                                     'reserved': True})
        self.db.api.fixed_ip_create(self.context,
                                    {'address': '10.1.1.3',
                                     'network_id': 100,
                                     'reserved': True})

        # test and assert
        result = self.db.api.network_count_reserved_ips(self.context, 101)
        self.assertEqual(0, result)

    @attr(kind='small')
    def test_network_create_safe(self):
        """
        safe means no error occurs when primary key is duplicate.
        """
        nw = {}
        nw['id'] = 100
        nw['label'] = "network1"
        nw['cidr'] = "10.1.1.0"
        nw['netmask'] = "255.255.255.0"
        nw['bridge'] = "br100"
        nw['bridge_interface'] = "eth1"
        nw['gateway'] = "10.1.1.254"
        nw['broadcast'] = "10.1.1.255"
        nw['dns1'] = "10.1.1.1"
        nw['dns2'] = "10.1.1.2"
        nw['vlan'] = 100
        nw['vpn_public_address'] = "68.52.102.104"
        nw['vpn_public_port'] = 8080
        nw['vpn_private_address'] = "10.1.1.3"
        nw['dhcp_start'] = "10.1.1.4"
        nw['project_id'] = "project1"
        nw['priority'] = 1
        nw['host'] = "host1"
        nw['uuid'] = "11:22:33:44"

        self.db.api.network_create_safe(self.context, nw)

        nw = self.db.api.network_get(self.context, 100)

        self.assertEqual(100, nw.id)
        self.assertEqual('network1', nw.label)
        self.assertEqual(False, nw.injected)
        self.assertEqual('10.1.1.0', nw.cidr)
        self.assertEqual(False, nw.multi_host)
        self.assertEqual('255.255.255.0', nw.netmask)
        self.assertEqual('br100', nw.bridge)
        self.assertEqual('eth1', nw.bridge_interface)
        self.assertEqual('10.1.1.254', nw.gateway)
        self.assertEqual('10.1.1.255', nw.broadcast)
        self.assertEqual('10.1.1.1', nw.dns1)
        self.assertEqual('10.1.1.2', nw.dns2)
        self.assertEqual(100, nw.vlan)
        self.assertEqual('68.52.102.104', nw.vpn_public_address)
        self.assertEqual(8080, nw.vpn_public_port)
        self.assertEqual('10.1.1.3', nw.vpn_private_address)
        self.assertEqual('10.1.1.4', nw.dhcp_start)
        self.assertEqual('project1', nw.project_id)
        self.assertEqual(1, nw.priority)
        self.assertEqual('host1', nw.host)
        self.assertEqual('11:22:33:44', nw.uuid)

    @attr(kind='small')
    def test_network_create_safe_db_duplicate(self):
        """
        safe means no error occurs when primary key is duplicate.
        """
#        raise SkipTest("DBError: (IntegrityError) PRIMARY KEY must be unique")
        # setup
        self.db.api.network_create_safe(self.context,
                                        {'id': 100, 'label': 'nw1'})
        # test and assert
        self.db.api.network_create_safe(self.context,
                                        {'id': 100, 'label': 'nw2'})
        nw = self.db.api.network_get(self.context, 100)
        self.assertEqual('nw1', nw.label)

    @attr(kind='small')
    def test_network_delete_safe(self):
        # setup
        self.db.api.network_create_safe(self.context,
                                        {'id': 100, 'label': 'nw1'})
        # test and assert
        self.db.api.network_delete_safe(self.context, 100)
        self.assertRaises(exception.NetworkNotFound,
                          self.db.api.network_get,
                          self.context, 100)

    @attr(kind='small')
    def test_network_delete_safe_db_not_found(self):
        """
        safe means no exception occures when network is not found
        """
#        raise SkipTest("Safe delete occured exception")
        # test and assert
        self.db.api.network_delete_safe(self.context, 100)
        self.assertRaises(exception.NetworkNotFound,
                          self.db.api.network_get,
                          self.context, 100)

    @attr(kind='small')
    def test_network_create_fixed_ips(self):
        """
        network_create_fixed_ips
        """
#        raise SkipTest("Not implemented in sqlalchemy.api.")

    @attr(kind='small')
    def test_network_create_fixed_ips_db_duplicate(self):
#        raise SkipTest("Not implemented in sqlalchemy.api.")

    @attr(kind='small')
    def test_network_disassociate(self):
        """
        unset project_id and host
        """
        # setup
        self.db.api.network_create_safe(self.context,
                                        {'id': 100,
                                         'project_id': 'project1',
                                         'host': 'host1'})
        # test and assert
        self.db.api.network_disassociate(self.context, 100)
        nw = self.db.api.network_get(self.context, 100)
        self.assertEqual(None, nw.project_id)
        self.assertEqual(None, nw.host)

    @attr(kind='small')
    def test_network_disassociate_db_not_found(self):
        self.assertRaises(exception.NetworkNotFound,
                          self.db.api.network_disassociate,
                          self.context, 100)

    @attr(kind='small')
    def test_network_disassociate_all(self):
        """
        unset project_id and host
        """
        # setup
        self.db.api.network_create_safe(self.context,
                                        {'id': 100,
                                         'project_id': 'project1',
                                         'host': 'host1'})
        self.db.api.network_create_safe(self.context,
                                        {'id': 101,
                                         'project_id': 'project1',
                                         'host': 'host1'})
        # test and assert
        self.db.api.network_disassociate_all(self.context)
        nw = self.db.api.network_get(self.context, 100)
        self.assertEqual(None, nw.project_id)
        nw = self.db.api.network_get(self.context, 101)
        self.assertEqual(None, nw.project_id)

    @attr(kind='small')
    def test_network_get(self):
        # setup
        self.db.api.network_create_safe(self.context,
                                        {'id': 100,
                                         'project_id': 'project1',
                                         'host': 'host1'})
        # test and assert
        nw = self.db.api.network_get(self.context, 100)
        self.assertEqual(100, nw.id)

    @attr(kind='small')
    def test_network_get_as_user(self):
        # setup
        self.db.api.network_create_safe(self.context,
                                        {'id': 100,
                                         'project_id': 'project1',
                                         'host': 'host1'})
        self.context.is_admin = False
        self.context.user_id = 'user1'
        self.context.project_id = 'project1'

        # test and assert
        nw = self.db.api.network_get(self.context, 100)
        self.assertEqual(100, nw.id)
        self.assertEqual('project1', nw.project_id)

    @attr(kind='small')
    def test_network_get_db_not_found(self):
        self.assertRaises(exception.NetworkNotFound,
                          self.db.api.network_get,
                          self.context, 100)

    @attr(kind='small')
    def test_network_get_all(self):
        # setup
        self.db.api.network_create_safe(self.context,
                                        {'id': 100,
                                         'project_id': 'project1',
                                         'host': 'host1'})
        # test and assert
        nw = self.db.api.network_get_all(self.context)
        self.assertIn(100, [n.id for n in nw])

    @attr(kind='small')
    def test_network_get_all_db_not_found(self):
        """
        looks violation for policy. should not raise exception
        """
        # setup
        nws = self.db.api.network_get_all(self.context)
        for nw in nws:
            self.db.api.network_update(self.context,
                                       nw.id, {'deleted': True})
        # test and assert
        self.assertRaises(exception.NoNetworksFound,
                          self.db.api.network_get_all,
                          self.context)

    @attr(kind='small')
    def test_network_get_all_by_uuids(self):
        # setup
        self.db.api.network_create_safe(self.context,
                                        {'id': 100,
                                         'project_id': None,
                                         'host': 'host1',
                                         'uuid': 'uuid'})
        # test and assert
        nw = self.db.api.network_get_all_by_uuids(self.context, ['uuid'])
        self.assertEqual(100, nw[0].id)

    @attr(kind='small')
    def test_network_get_all_by_uuids_with_project_id(self):
        # setup
        self.db.api.network_create_safe(self.context,
                                        {'id': 100,
                                         'project_id': 'project1',
                                         'host': 'host1',
                                         'uuid': 'uuid'})
        # test and assert
        nw = self.db.api.network_get_all_by_uuids(
                                    self.context, ['uuid'], 'project1')
        self.assertEqual(100, nw[0].id)

    @attr(kind='small')
    def test_network_get_all_by_uuids_no_network(self):
        # setup
        self.db.api.network_create_safe(self.context,
                                        {'id': 100,
                                         'project_id': 'project1',
                                         'host': 'host1',
                                         'uuid': 'uuid'})
        # test and assert
        self.assertRaises(exception.NoNetworksFound,
                          self.db.api.network_get_all_by_uuids,
                          self.context, ['uuid'], 'project2')

    @attr(kind='small')
    def test_network_get_all_by_uuids_no_network_host(self):
        # setup
        self.db.api.network_create_safe(self.context,
                                        {'id': 100,
                                         'project_id': 'project1',
                                         'host': None,
                                         'uuid': 'uuid'})
        # test and assert
        self.assertRaises(exception.NetworkHostNotSet,
                          self.db.api.network_get_all_by_uuids,
                          self.context, ['uuid'], 'project1')

    @attr(kind='small')
    def test_network_get_all_by_uuids_no_network_for_project(self):
        # setup
        self.db.api.network_create_safe(self.context,
                                        {'id': 100,
                                         'project_id': None,
                                         'host': 'host1',
                                         'uuid': 'uuid'})
        # test and assert
        self.assertRaises(exception.NoNetworksFound,
                          self.db.api.network_get_all_by_uuids,
                          self.context, ['uuid2'], 'project1')

    @attr(kind='small')
    def test_network_get_associated_fixed_ips(self):
        # setup
        self.db.fixed_ip_create(self.context,
                                {'address': '10.1.1.1',
                                 'network_id': 100,
                                 'instance_id': 1,
                                 'virtual_interface_id': 1})
        self.db.fixed_ip_create(self.context,
                                {'address': '10.1.1.2',
                                 'network_id': 100,
                                 'instance_id': 2,
                                 'virtual_interface_id': 2})
        # test and assert
        ips = self.db.api.network_get_associated_fixed_ips(self.context, 100)
        self.assertEqual("10.1.1.1", ips[0].address)
        self.assertEqual("10.1.1.2", ips[1].address)

    @attr(kind='small')
    def test_network_get_associated_fixed_ips_db_not_found(self):
        # setup
        self.db.fixed_ip_create(self.context,
                                {'address': '10.1.1.1',
                                 'network_id': 100,
                                 'instance_id': 1})
        self.db.fixed_ip_create(self.context,
                                {'address': '10.1.1.2',
                                 'network_id': 100,
                                 'virtual_interface_id': 2})
        # test and assert
        ips = self.db.api.network_get_associated_fixed_ips(self.context, 100)
        self.assertEqual([], ips)

    @attr(kind='small')
    def test_network_get_by_bridge(self):
        # setup
        self.db.network_create_safe(self.context,
                                    {'id': 100, 'bridge': 'br100'})
        self.db.network_create_safe(self.context,
                                    {'id': 101, 'bridge': 'br101'})
        # test and assert
        nw = self.db.api.network_get_by_bridge(self.context, 'br100')
        self.assertEqual("br100", nw.bridge)

    @attr(kind='small')
    def test_network_get_by_bridge_db_not_found(self):
        # setup
        self.db.network_create_safe(self.context,
                                    {'id': 100, 'bridge': 'br100'})
        self.db.network_create_safe(self.context,
                                    {'id': 101, 'bridge': 'br101'})
        # test and assert
        self.assertRaises(exception.NetworkNotFoundForBridge,
                          self.db.api.network_get_by_bridge,
                          self.context, 'br102')

    @attr(kind='small')
    def test_network_get_by_uuid(self):
        # setup
        self.db.network_create_safe(self.context,
                                    {'id': 100, 'uuid': 'uuid1'})
        self.db.network_create_safe(self.context,
                                    {'id': 101, 'uuid': 'uuid2'})
        # test and assert
        nw = self.db.api.network_get_by_uuid(self.context, 'uuid1')
        self.assertEqual("uuid1", nw.uuid)

    @attr(kind='small')
    def test_network_get_by_uuid_db_not_found(self):
        # setup
        self.db.network_create_safe(self.context,
                                    {'id': 100, 'uuid': 'uuid1'})
        self.db.network_create_safe(self.context,
                                    {'id': 101, 'uuid': 'uuid2'})
        # test and assert
        self.assertRaises(exception.NetworkNotFoundForUUID,
                          self.db.api.network_get_by_uuid,
                          self.context, 'uuid3')

    @attr(kind='small')
    def test_network_get_by_cidr(self):
        # setup
        self.db.network_create_safe(self.context,
                                    {'id': 100, 'cidr': '10.1.0.0'})
        self.db.network_create_safe(self.context,
                                    {'id': 101, 'cidr': '10.2.0.0'})
        # test and assert
        nw = self.db.api.network_get_by_cidr(self.context, '10.1.0.0')
        self.assertEqual("10.1.0.0", nw.cidr)

    @attr(kind='small')
    def test_network_get_by_cidr_db_not_found(self):
        # setup
        self.db.network_create_safe(self.context,
                                    {'id': 100, 'cidr': '10.1.0.0'})
        self.db.network_create_safe(self.context,
                                    {'id': 101, 'cidr': '10.2.0.0'})
        # test and assert
        self.assertRaises(exception.NetworkNotFoundForCidr,
                          self.db.api.network_get_by_cidr,
                          self.context, '10.3.0.0')

    @attr(kind='small')
    def test_network_get_by_instance(self):
        # setup
        self.db.network_create_safe(self.context, {'id': 100})
        self.db.fixed_ip_create(self.context,
                                {'network_id': 100, 'instance_id': 1})
        # test and assert
        nw = self.db.api.network_get_by_instance(self.context, 1)
        self.assertEqual(100, nw.id)

    @attr(kind='small')
    def test_network_get_by_instance_db_not_found(self):
        # setup
        self.db.network_create_safe(self.context, {'id': 100})
        self.db.fixed_ip_create(self.context,
                                {'network_id': 100, 'instance_id': 1})
        # test and assert
        self.assertRaises(exception.NetworkNotFoundForInstance,
                          self.db.api.network_get_by_instance,
                          self.context, 2)

    @attr(kind='small')
    def test_network_get_all_by_instance(self):
        # setup
        self.db.network_create_safe(self.context, {'id': 100})
        self.db.fixed_ip_create(self.context,
                                {'network_id': 100, 'instance_id': 1})
        # test and assert
        nw = self.db.api.network_get_all_by_instance(self.context, 1)
        self.assertEqual(100, nw[0].id)

    @attr(kind='small')
    def test_network_get_all_by_instance_db_not_found(self):
        # setup
        self.db.network_create_safe(self.context, {'id': 100})
        self.db.fixed_ip_create(self.context,
                                {'network_id': 100, 'instance_id': 1})
        # test and assert
        self.assertRaises(exception.NetworkNotFoundForInstance,
                          self.db.api.network_get_all_by_instance,
                          self.context, 2)

    @attr(kind='small')
    def test_network_get_all_by_host(self):
        # setup
        self.db.network_create_safe(self.context,
                                    {'id': 100, 'host': 'host'})
        self.db.fixed_ip_create(self.context,
                                {'network_id': 100,
                                 'instance_id': 1,
                                 'host': 'host'})
        # test and assert
        nw = self.db.api.network_get_all_by_host(self.context, 'host')
        self.assertEqual('host', nw[0].host)

    @attr(kind='small')
    def test_network_get_all_by_host_db_not_found(self):
        # setup
        self.db.network_create_safe(self.context,
                                    {'id': 100, 'host': 'host'})
        self.db.fixed_ip_create(self.context,
                                {'network_id': 100,
                                 'instance_id': 1,
                                 'host': 'host'})
        # test and assert
        nw = self.db.api.network_get_all_by_host(self.context, 'host2')
        self.assertEqual([], nw)

    @attr(kind='small')
    def test_network_get_index(self):
        """
        network_get_index
        """
#        raise SkipTest("Not implemented in sqlalchemy.api.")

    @attr(kind='small')
    def test_network_get_index_db_not_found(self):
#        raise SkipTest("Not implemented in sqlalchemy.api.")

    @attr(kind='small')
    def test_network_get_vpn_ip(self):
        """
        network_get_vpn_ip
        """
#        raise SkipTest("Not implemented in sqlalchemy.api.")

    @attr(kind='small')
    def test_network_get_vpn_ip_db_not_found(self):
#        raise SkipTest("Not implemented in sqlalchemy.api.")

    @attr(kind='small')
    def test_network_set_cidr(self):
        """
        network_set_cidr
        """
#        raise SkipTest("Not implemented in sqlalchemy.api.")

    @attr(kind='small')
    def test_network_set_cidr_db_not_found(self):
#        raise SkipTest("Not implemented in sqlalchemy.api.")

    @attr(kind='small')
    def test_network_set_host(self):
        # setup
        self.db.network_create_safe(self.context, {'id': 100})
        # test and assert
        host = self.db.api.network_set_host(self.context, 100, 'host2')
        self.assertEqual('host2', host)
        nw = self.db.api.network_get(self.context, 100)
        self.assertEqual('host2', nw.host)

    @attr(kind='small')
    def test_network_set_host_parameter_host(self):

        # setup
        self.db.network_create_safe(self.context, {'id': 100})
        # test and assert
        host = self.db.api.network_set_host(self.context, 100, 'host2')
        self.assertEqual('host2', host)
        nw = self.db.api.network_get(self.context, 100)
        self.assertEqual('host2', nw.host)

    @attr(kind='small')
    def test_network_set_host_db_not_found(self):
        # setup
        self.db.network_create_safe(self.context, {'id': 100, 'host': 'host'})
        # test and assert
        self.assertRaises(exception.NetworkNotFound,
                          self.db.api.network_set_host,
                          self.context, 99, 'host2')

    @attr(kind='small')
    def test_network_update(self):
        # setup
        self.db.network_create_safe(self.context, {'id': 100, 'host': 'host'})
        # test and assert
        self.db.api.network_update(self.context, 100, {'host': 'host2'})
        nw = self.db.api.network_get(self.context, 100)
        self.assertEqual('host2', nw.host)

    @attr(kind='small')
    def test_network_update_db_not_found(self):
        # setup
        self.db.network_create_safe(self.context, {'id': 100, 'host': 'host'})
        # test and assert
        self.assertRaises(exception.NetworkNotFound,
                          self.db.api.network_update,
                          self.context, 99, {'host': 'host2'})

    @attr(kind='small')
    def test_network_update_db_duplicate(self):
#        raise SkipTest("No error happened when update record\
#            and duplicate unique column.")
        # setup
        self.db.network_create_safe(self.context,
                                    {'id': 100, 'cidr': '10.1.1.0'})
        self.db.network_create_safe(self.context,
                                    {'id': 101, 'cidr': '10.2.1.0'})
        # test and assert
        self.assertRaises(exception.Duplicate,
                          self.db.api.network_update,
                          self.context, 100, {'cidr': '10.2.1.0'})

    @attr(kind='small')
    def test_queue_get_for(self):
        # test and assert
        result = self.db.api.queue_get_for(self.context, "compute", "compute1")
        self.assertEqual("compute.compute1", result)

    @attr(kind='small')
    def test_export_device_count(self):
        # setup
        self.db.api.export_device_create_safe(self.context, {'id': 1})
        # test and assert
        result = self.db.api.export_device_count(self.context)
        self.assertEqual(1, result)

    @attr(kind='small')
    def test_export_device_count_db_not_found(self):
        # test and assert
        result = self.db.api.export_device_count(self.context)
        self.assertEqual(0, result)

    @attr(kind='small')
    def test_export_device_create_safe(self):
        # setup
        self.db.volume_create(self.context, {'id': 1, 'size': '1g'})
        device = {}
        device['id'] = 1
        device['shelf_id'] = 1
        device['blade_id'] = 1
        device['volume_id'] = 1
        # test and assert
        result = self.db.api.export_device_create_safe(self.context, device)
        self.assertTrue(result is not None)

    @attr(kind='small')
    def test_export_device_create_safe_db_duplicate(self):
#        raise SkipTest("DBError: (IntegrityError) PRIMARY KEY must be unique")
        # setup
        self.db.volume_create(self.context, {'id': 1, 'size': '1g'})
        device = {}
        device['id'] = 1
        device['shelf_id'] = 1
        device['blade_id'] = 1
        device['volume_id'] = 1
        # test and assert
        self.db.api.export_device_create_safe(self.context, device)
        result = self.db.api.export_device_create_safe(self.context, device)
        self.assertTrue(result is None)

    @attr(kind='small')
    def test_iscsi_target_count_by_host(self):
        # setup
        self.db.api.iscsi_target_create_safe(self.context,
                                             {'id': 1, 'host': 'host'})
        # test and assert
        result = self.db.api.iscsi_target_count_by_host(self.context, 'host')
        self.assertEqual(1, result)

    @attr(kind='small')
    def test_iscsi_target_count_by_host_db_not_found(self):
        # setup
        self.db.api.iscsi_target_create_safe(self.context,
                                             {'id': 1, 'host': 'host'})
        # test and assert
        result = self.db.api.iscsi_target_count_by_host(self.context, 'host2')
        self.assertEqual(0, result)

    @attr(kind='small')
    def test_iscsi_target_create_safe(self):
        # setup
        self.db.volume_create(self.context, {'id': 1, 'size': '1g'})
        target = {}
        target['id'] = 1
        target['target_num'] = 1
        target['host'] = 'host'
        target['volume_id'] = 1
        # test and assert
        result = self.db.api.iscsi_target_create_safe(self.context, target)
        self.assertTrue(result is not None)

    @attr(kind='small')
    def test_iscsi_target_create_safe_db_duplicate(self):
#        raise SkipTest("DBError: (IntegrityError) PRIMARY KEY must be unique")
        # setup
        # setup
        self.db.volume_create(self.context, {'id': 1, 'size': '1g'})
        target = {}
        target['id'] = 1
        target['target_num'] = 1
        target['host'] = 'host'
        target['volume_id'] = 1
        # test and assert
        self.db.api.iscsi_target_create_safe(self.context, target)
        result = self.db.api.iscsi_target_create_safe(self.context, target)
        self.assertTrue(result is None)

    @attr(kind='small')
    def test_auth_token_destroy(self):
        # setup
        self.db.api.auth_token_create(self.context,
                                      {'token_hash': 'hash',
                                       'user_id': 'user1'})
        # test and assert
        self.db.api.auth_token_destroy(self.context, 'hash')
        self.assertRaises(exception.AuthTokenNotFound,
                          self.db.api.auth_token_get,
                          self.context, 'hash')

    @attr(kind='small')
    def test_auth_token_destroy_db_not_found(self):
        # setup
        self.db.api.auth_token_create(self.context,
                                      {'token_hash': 'hash',
                                       'user_id': 'user1'})
        # test and assert
        self.assertRaises(exception.AuthTokenNotFound,
                          self.db.api.auth_token_destroy,
                          self.context, 'hash1')

    @attr(kind='small')
    def test_auth_token_update(self):
        # setup
        self.db.api.auth_token_create(self.context,
                                      {'token_hash': 'hash',
                                       'user_id': 'user1'})
        # test and assert
        self.db.api.auth_token_update(self.context, 'hash',
                                      {'user_id': 'user2'})
        token = self.db.api.auth_token_get(self.context, 'hash')
        self.assertEqual('user2', token.user_id)

    @attr(kind='small')
    def test_auth_token_update_db_not_found(self):
        # setup
        self.db.api.auth_token_create(self.context,
                                      {'token_hash': 'hash',
                                       'user_id': 'user1'})
        # test and assert
        self.assertRaises(exception.AuthTokenNotFound,
                          self.db.api.auth_token_update,
                          self.context, 'not_found', {'user_id': 'user2'})

    @attr(kind='small')
    def test_auth_token_create(self):
        # setup
        token = {}
        token['token_hash'] = 'hash'
        token['user_id'] = 'user'
        token['server_management_url'] = 'http://server'
        token['storage_url'] = 'http://storage'
        token['cdn_management_url'] = 'http://cdn'
        # test and assert
        self.db.api.auth_token_create(self.context, token)
        result = self.db.auth_token_get(self.context, 'hash')
        self.assertEqual('hash', result.token_hash)
        self.assertEqual('user', result.user_id)
        self.assertEqual('http://server', result.server_management_url)
        self.assertEqual('http://storage', result.storage_url)
        self.assertEqual('http://cdn', result.cdn_management_url)

    @attr(kind='small')
    def test_auth_token_create_db_duplicate(self):
        # setup
        token = {}
        token['token_hash'] = 'hash'
        token['user_id'] = 'user'
        token['server_management_url'] = 'http://server'
        token['storage_url'] = 'http://storage'
        token['cdn_management_url'] = 'http://cdn'
        # test and assert
        self.db.api.auth_token_create(self.context, token)
        self.assertRaises(exception.Duplicate,
                          self.db.api.auth_token_create,
                          self.context, token)

    @attr(kind='small')
    def test_quota_get(self):
        # setup
        self.db.api.quota_create(self.context, 'project1', 'vcpus', 1)
        self.db.api.quota_create(self.context, 'project1', 'memory_mb', 10)
        self.db.api.quota_create(self.context, 'project1', 'disk_gb', 5)
        # test and assert
        quota = self.db.api.quota_get(self.context, 'project1', 'vcpus')
        self.assertEqual(1, quota.hard_limit)

    @attr(kind='small')
    def test_quota_get_user(self):
        # setup
        self.db.api.quota_create(self.context, 'project1', 'vcpus', 1)
        self.db.api.quota_create(self.context, 'project1', 'memory_mb', 10)
        self.db.api.quota_create(self.context, 'project1', 'disk_gb', 5)
        # test and assert
        self.context.is_admin = False
        self.context.user_id = "user1"
        self.context.project_id = "project1"
        quota = self.db.api.quota_get(self.context, 'project1', 'vcpus')
        self.assertEqual(1, quota.hard_limit)

    @attr(kind='small')
    def test_quota_get_db_not_found(self):
        # setup
        self.db.api.quota_create(self.context, 'project1', 'vcpus', 1)
        self.db.api.quota_create(self.context, 'project1', 'memory_mb', 10)
        self.db.api.quota_create(self.context, 'project1', 'disk_gb', 5)
        # test and assert
        self.assertRaises(exception.ProjectQuotaNotFound,
                          self.db.api.quota_get,
                          self.context, 'project2', 'vcpus')

    @attr(kind='small')
    def test_quota_get_all_by_project(self):
        # setup
        self.db.api.quota_create(self.context, 'project1', 'vcpus', 1)
        self.db.api.quota_create(self.context, 'project1', 'memory_mb', 10)
        self.db.api.quota_create(self.context, 'project1', 'disk_gb', 5)
        # test and assert
        quota = self.db.api.quota_get_all_by_project(self.context, 'project1')
        self.assertEqual(1, quota['vcpus'])
        self.assertEqual(10, quota['memory_mb'])
        self.assertEqual(5, quota['disk_gb'])

    @attr(kind='small')
    def test_quota_get_all_by_project_db_not_found(self):
        # setup
        self.db.api.quota_create(self.context, 'project1', 'vcpus', 1)
        self.db.api.quota_create(self.context, 'project1', 'memory_mb', 10)
        self.db.api.quota_create(self.context, 'project1', 'disk_gb', 5)
        # test and assert
        quota = self.db.api.quota_get_all_by_project(self.context, 'project2')
        self.assertEqual('project2', quota['project_id'])

    @attr(kind='small')
    def test_quota_create(self):
        # setup
        self.db.api.quota_create(self.context, 'project1', 'vcpus', 1)
        self.db.api.quota_create(self.context, 'project1', 'memory_mb', 10)
        self.db.api.quota_create(self.context, 'project1', 'disk_gb', 5)
        # assert
        quota = self.db.api.quota_get_all_by_project(self.context, 'project1')
        self.assertEqual(1, quota['vcpus'])
        self.assertEqual(10, quota['memory_mb'])
        self.assertEqual(5, quota['disk_gb'])

    @attr(kind='small')
    def test_quota_create_db_duplicate(self):
        """
        when same project, same resource specified,
            it will be update quota value.
        """
        # setup
        self.db.api.quota_create(self.context, 'project1', 'vcpus', 1)
        self.db.api.quota_create(self.context, 'project1', 'vcpus', 10)
        self.db.api.quota_create(self.context, 'project1', 'vcpus', 5)
        # assert
        quota = self.db.api.quota_get_all_by_project(self.context, 'project1')
        self.assertEqual(5, quota['vcpus'])

    @attr(kind='small')
    def test_quota_update(self):
        # setup
        self.db.api.quota_create(self.context, 'project1', 'vcpus', 1)
        self.db.api.quota_create(self.context, 'project1', 'memory_mb', 10)
        self.db.api.quota_create(self.context, 'project1', 'disk_gb', 5)
        # assert
        self.db.api.quota_update(self.context, 'project1', 'vcpus', 10)
        quota = self.db.api.quota_get_all_by_project(self.context, 'project1')
        self.assertEqual(10, quota['vcpus'])
        self.assertEqual(10, quota['memory_mb'])
        self.assertEqual(5, quota['disk_gb'])

    @attr(kind='small')
    def test_quota_update_db_not_found(self):
        # setup
        self.db.api.quota_create(self.context, 'project1', 'vcpus', 1)
        self.db.api.quota_create(self.context, 'project1', 'memory_mb', 10)
        self.db.api.quota_create(self.context, 'project1', 'disk_gb', 5)
        # test and assert
        self.assertRaises(exception.ProjectQuotaNotFound,
                          self.db.api.quota_update,
                          self.context, 'project2', 'vcpus', 10)

    @attr(kind='small')
    def test_quota_destroy(self):
        # setup
        self.db.api.quota_create(self.context, 'project1', 'vcpus', 1)
        self.db.api.quota_create(self.context, 'project1', 'memory_mb', 10)
        self.db.api.quota_create(self.context, 'project1', 'disk_gb', 5)
        # assert
        self.db.api.quota_destroy(self.context, 'project1', 'vcpus')
        quota = self.db.api.quota_get_all_by_project(self.context, 'project1')
        self.assertFalse('vcpus' in quota)
        self.assertEqual(10, quota['memory_mb'])
        self.assertEqual(5, quota['disk_gb'])

    @attr(kind='small')
    def test_quota_destroy_db_not_found(self):
        # setup
        self.db.api.quota_create(self.context, 'project1', 'vcpus', 1)
        self.db.api.quota_create(self.context, 'project1', 'memory_mb', 10)
        self.db.api.quota_create(self.context, 'project1', 'disk_gb', 5)
        # test and assert
        self.assertRaises(exception.ProjectQuotaNotFound,
                          self.db.api.quota_destroy,
                          self.context, 'project2', 'vcpus')

    @attr(kind='small')
    def test_quota_destroy_all_by_project(self):
        # setup
        self.db.api.quota_create(self.context, 'project1', 'vcpus', 1)
        self.db.api.quota_create(self.context, 'project1', 'memory_mb', 10)
        self.db.api.quota_create(self.context, 'project1', 'disk_gb', 5)
        # assert
        self.db.api.quota_destroy_all_by_project(self.context, 'project1')
        quota = self.db.api.quota_get_all_by_project(self.context, 'project1')
        self.assertFalse('vcpus' in quota)
        self.assertFalse('memory_mb' in quota)
        self.assertFalse('disk_gb' in quota)

    @attr(kind='small')
    def test_quota_destroy_all_by_project_db_not_found(self):
        # setup
        self.db.api.quota_create(self.context, 'project1', 'vcpus', 1)
        self.db.api.quota_create(self.context, 'project1', 'memory_mb', 10)
        self.db.api.quota_create(self.context, 'project1', 'disk_gb', 5)
        # assert
        self.db.api.quota_destroy_all_by_project(self.context, 'project2')
        quota = self.db.api.quota_get_all_by_project(self.context, 'project1')
        self.assertEqual(1, quota['vcpus'])
        self.assertEqual(10, quota['memory_mb'])
        self.assertEqual(5, quota['disk_gb'])

    @attr(kind='small')
    def test_volume_allocate_shelf_and_blade(self):
        # setup
        self.db.api.export_device_create_safe(self.context,
                                              {'shelf_id': 1, 'blade_id': 1})
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        # test and assert
        shelf_id, blade_id = self.db.volume_allocate_shelf_and_blade(
                                                        self.context, 1)
        self.assertEqual(1, shelf_id)
        self.assertEqual(1, blade_id)

    @attr(kind='small')
    def test_volume_allocate_shelf_and_blade_no_more_blades(self):
        # test and assert
        self.assertRaises(db.NoMoreBlades,
                          self.db.volume_allocate_shelf_and_blade,
                          self.context, 1)

    @attr(kind='small')
    def test_volume_allocate_iscsi_target(self):
        # setup
        self.db.api.iscsi_target_create_safe(self.context,
                                             {'target_num': 1, 'host': 'host'})
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        # test and assert
        target_num = self.db.volume_allocate_iscsi_target(
                                            self.context, 1, 'host')
        self.assertEqual(1, target_num)

    @attr(kind='small')
    def test_volume_allocate_iscsi_target_no_more_target(self):
        # test and assert
        self.assertRaises(db.NoMoreTargets,
                          self.db.volume_allocate_iscsi_target,
                          self.context, 1, 'host')

    @attr(kind='small')
    def test_volume_attached(self):
        # setup
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        self.db.api.instance_create(self.context, {'id': 1})
        # test and assert
        self.db.api.volume_attached(self.context, 1, 1, '/dev/sdb')
        volume = self.db.api.volume_get(self.context, 1)
        self.assertEqual('in-use', volume.status)
        self.assertEqual('/dev/sdb', volume.mountpoint)
        self.assertEqual('attached', volume.attach_status)
        self.assertEqual(1, volume.instance.id)

    @attr(kind='small')
    def test_volume_attached_volume_db_not_found(self):
        # setup
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        self.db.api.instance_create(self.context, {'id': 1})
        # test and assert
        self.assertRaises(exception.VolumeNotFound,
                          self.db.api.volume_attached,
                          self.context, 2, 1, '/dev/sdb')

    @attr(kind='small')
    def test_volume_attached_instance_db_not_found(self):
        # setup
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        self.db.api.instance_create(self.context, {'id': 1})
        # test and assert
        self.assertRaises(exception.InstanceNotFound,
                          self.db.api.volume_attached,
                          self.context, 1, 2, '/dev/sdb')

    @attr(kind='small')
    def test_volume_create(self):
        # setup
        vol = {}
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        # test and assert
        result = self.db.api.volume_create(self.context, vol)
        volume = self.db.api.volume_get(self.context, result.id)
        self.assertEqual('1g', volume.size)
        self.assertEqual(None, volume.snapshot_id)
        self.assertEqual('fake', volume.user_id)
        self.assertEqual('fake', volume.project_id)
        self.assertEqual(FLAGS.storage_availability_zone,
                         volume.availability_zone)
        self.assertEqual('creating', volume.status)
        self.assertEqual('detached', volume.attach_status)

    @attr(kind='small')
    def test_volume_create_with_metadata(self):
        # setup
        vol = {}
        vol['size'] = '1'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['metadata'] = {'type': 'test'}
        # test and assert
        result = self.db.api.volume_create(self.context, vol)
        metadata = self.db.api.volume_metadata_get(self.context, result.id)
        self.assertEqual('test', metadata['type'])

    @attr(kind='small')
    def test_volume_create_db_duplicate(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        # test and assert
        self.db.api.volume_create(self.context, vol)
        self.assertRaises(exception.Duplicate,
                          self.db.api.volume_create,
                          self.context, vol)

    @attr(kind='small')
    def test_volume_data_get_for_project(self):
        # setup
        self.db.api.volume_create(self.context,
                                  {'size': '1g', 'project_id': 'project1'})
        self.db.api.volume_create(self.context,
                                  {'size': '2g', 'project_id': 'project1'})
        self.db.api.volume_create(self.context,
                                  {'size': '3g', 'project_id': 'project1'})
        # test and assert
        count, sum = self.db.api.volume_data_get_for_project(
                                            self.context, 'project1')
        self.assertEqual(3, count)
        self.assertEqual(6, sum)

    @attr(kind='small')
    def test_volume_data_get_for_project_db_not_found(self):
        # test and assert
        count, sum = self.db.api.volume_data_get_for_project(
                                            self.context, 'project1')
        self.assertEqual(0, count)
        self.assertEqual(0, sum)

    @attr(kind='small')
    def test_volume_destroy(self):
        """
        destroy means remove all volume related records.
        metadata and iscsi/aoe. looks very dangerous.is vsa? zadara?
        if command failed?
        """
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)

        target = {}
        target['id'] = 1
        target['target_num'] = 1
        target['host'] = 'host'
        target['volume_id'] = 1  # already associated.
        # test and assert
        self.db.api.iscsi_target_create_safe(self.context, target)

        # test and assert
        self.db.api.volume_destroy(self.context, 1)
        self.assertRaises(exception.VolumeNotFound,
                          self.db.volume_metadata_get,
                          self.context, 1)
        self.assertRaises(exception.VolumeNotFound,
                          self.db.volume_get,
                          self.context, 1)

    @attr(kind='small')
    def test_volume_destroy_db_not_found(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)

        target = {}
        target['id'] = 1
        target['target_num'] = 1
        target['host'] = 'host'
        target['volume_id'] = 1  # already associated.
        # test and assert
        self.db.api.iscsi_target_create_safe(self.context, target)
        self.db.api.volume_destroy(self.context, 2)
        # no effect
        volume = self.db.api.volume_get(self.context, 1)
        self.assertEqual('1g', volume.size)
        self.assertEqual(None, volume.snapshot_id)
        self.assertEqual('fake', volume.user_id)
        self.assertEqual('fake', volume.project_id)
        self.assertEqual(FLAGS.storage_availability_zone,
                         volume.availability_zone)
        self.assertEqual('creating', volume.status)
        self.assertEqual('detached', volume.attach_status)

    @attr(kind='small')
    def test_volume_detached(self):
        # setup
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        self.db.api.instance_create(self.context, {'id': 1})
        # test and assert
        self.db.api.volume_detached(self.context, 1)
        volume = self.db.api.volume_get(self.context, 1)
        self.assertEqual('available', volume.status)
        self.assertEqual(None, volume.mountpoint)
        self.assertEqual('detached', volume.attach_status)
        self.assertEqual(None, volume.instance)

    @attr(kind='small')
    def test_volume_detached_volume_db_not_found(self):
        # setup
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        self.db.api.instance_create(self.context, {'id': 1})
        # test and assert
        self.assertRaises(exception.VolumeNotFound,
                          self.db.api.volume_detached,
                          self.context, 2)

    @attr(kind='small')
    def test_volume_get(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)

        # test and assert
        volume = self.db.api.volume_get(self.context, 1)
        self.assertEqual('1g', volume.size)
        self.assertEqual(None, volume.snapshot_id)
        self.assertEqual('fake', volume.user_id)
        self.assertEqual('fake', volume.project_id)
        self.assertEqual(FLAGS.storage_availability_zone,
                         volume.availability_zone)
        self.assertEqual('creating', volume.status)
        self.assertEqual('detached', volume.attach_status)

    @attr(kind='small')
    def test_volume_get_user(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)
        self.context.is_admin = False
        self.context.user_id = 'fake'
        self.context.project_id = 'fake'
        # test and assert
        volume = self.db.api.volume_get(self.context, 1)
        self.assertEqual('1g', volume.size)
        self.assertEqual(None, volume.snapshot_id)
        self.assertEqual('fake', volume.user_id)
        self.assertEqual('fake', volume.project_id)
        self.assertEqual(FLAGS.storage_availability_zone,
                         volume.availability_zone)
        self.assertEqual('creating', volume.status)
        self.assertEqual('detached', volume.attach_status)

    @attr(kind='small')
    def test_volume_get_db_not_found(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)

        self.assertRaises(exception.VolumeNotFound,
                          self.db.api.volume_get,
                          self.context, 2)

    @attr(kind='small')
    def test_volume_get_all(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)

        volumes = self.db.api.volume_get_all(self.context)
        volume = volumes[0]
        self.assertEqual('1g', volume.size)
        self.assertEqual(None, volume.snapshot_id)
        self.assertEqual('fake', volume.user_id)
        self.assertEqual('fake', volume.project_id)
        self.assertEqual(FLAGS.storage_availability_zone,
                         volume.availability_zone)
        self.assertEqual('creating', volume.status)
        self.assertEqual('detached', volume.attach_status)

    @attr(kind='small')
    def test_volume_get_all_db_not_found(self):
        result = self.db.api.volume_get_all(self.context)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_volume_get_all_by_host(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['host'] = 'host1'
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)

        volumes = self.db.api.volume_get_all_by_host(self.context, 'host1')
        volume = volumes[0]
        self.assertEqual('1g', volume.size)
        self.assertEqual(None, volume.snapshot_id)
        self.assertEqual('fake', volume.user_id)
        self.assertEqual('fake', volume.project_id)
        self.assertEqual(FLAGS.storage_availability_zone,
                         volume.availability_zone)
        self.assertEqual('creating', volume.status)
        self.assertEqual('detached', volume.attach_status)

    @attr(kind='small')
    def test_volume_get_all_by_host_db_not_found(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['host'] = 'host1'
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)

        volumes = self.db.api.volume_get_all_by_host(self.context, 'host2')
        self.assertEqual([], volumes)

    @attr(kind='small')
    def test_volume_get_all_by_instance(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['instance_id'] = 1
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)

        volumes = self.db.api.volume_get_all_by_instance(self.context, 1)
        volume = volumes[0]
        self.assertEqual('1g', volume.size)
        self.assertEqual(None, volume.snapshot_id)
        self.assertEqual('fake', volume.user_id)
        self.assertEqual('fake', volume.project_id)
        self.assertEqual(FLAGS.storage_availability_zone,
                         volume.availability_zone)
        self.assertEqual('creating', volume.status)
        self.assertEqual('detached', volume.attach_status)

    @attr(kind='small')
    def test_volume_get_all_by_instance_db_not_found(self):
        """
        should not be raise.
        """
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['instance_id'] = 1
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)

        self.assertRaises(exception.VolumeNotFoundForInstance,
                          self.db.api.volume_get_all_by_instance,
                          self.context, 2)

    @attr(kind='small')
    def test_volume_get_all_by_project(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)

        volumes = self.db.api.volume_get_all_by_project(
                                            self.context, 'fake')
        volume = volumes[0]
        self.assertEqual('1g', volume.size)
        self.assertEqual(None, volume.snapshot_id)
        self.assertEqual('fake', volume.user_id)
        self.assertEqual('fake', volume.project_id)
        self.assertEqual(FLAGS.storage_availability_zone,
                         volume.availability_zone)
        self.assertEqual('creating', volume.status)
        self.assertEqual('detached', volume.attach_status)

    @attr(kind='small')
    def test_volume_get_all_by_project_db_not_found(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)

        volumes = self.db.api.volume_get_all_by_project(
                                            self.context, 'fake2')
        self.assertEqual([], volumes)

    @attr(kind='small')
    def test_volume_get_by_ec2_id(self):
        """
        volume_get_by_ec2_id
        """
#        raise SkipTest("Not implemented in sqlalchemy.api.")

    @attr(kind='small')
    def test_volume_get_by_ec2_id_db_not_found(self):
#        raise SkipTest("Not implemented in sqlalchemy.api.")

    @attr(kind='small')
    def test_volume_get_instance(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['instance_id'] = 1
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)
        self.db.api.instance_create(self.context, {'id': 1})

        instance = self.db.api.volume_get_instance(self.context, 1)
        self.assertEqual(1, instance.id)

    @attr(kind='small')
    def test_volume_get_instance_db_not_found(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['instance_id'] = 1
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)
        self.db.api.instance_create(self.context, {'id': 1})

        self.assertRaises(exception.VolumeNotFound,
                          self.db.api.volume_get_instance,
                          self.context, 2)

    @attr(kind='small')
    def test_volume_get_shelf_and_blade(self):
        # setup
        self.db.api.export_device_create_safe(
                            self.context, {'volume_id': 1,
                                           'shelf_id': 1,
                                           'blade_id': 1})
        # test and assert
        shelf_id, blade_id = self.db.api.volume_get_shelf_and_blade(
                                                        self.context, 1)
        self.assertEqual(1, shelf_id)
        self.assertEqual(1, blade_id)

    @attr(kind='small')
    def test_volume_get_shelf_and_blade_db_not_found(self):
        # setup
        self.db.api.export_device_create_safe(
                            self.context, {'volume_id': 1,
                                           'shelf_id': 1,
                                           'blade_id': 1})
        # test and assert
        self.assertRaises(exception.ExportDeviceNotFoundForVolume,
                          self.db.api.volume_get_shelf_and_blade,
                          self.context, 2)

    @attr(kind='small')
    def test_volume_get_iscsi_target_num(self):
        # setup
        self.db.api.iscsi_target_create_safe(self.context,
                                             {'volume_id': 1, 'target_num': 1})
        # test and assert
        target_num = self.db.api.volume_get_iscsi_target_num(self.context, 1)
        self.assertEqual(1, target_num)

    @attr(kind='small')
    def test_volume_get_iscsi_target_num_db_not_found(self):
        # setup
        self.db.api.iscsi_target_create_safe(self.context,
                                             {'volume_id': 1, 'target_num': 1})
        # test and assert
        self.assertRaises(exception.ISCSITargetNotFoundForVolume,
                          self.db.api.volume_get_iscsi_target_num,
                          self.context, 2)

    @attr(kind='small')
    def test_volume_update(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['instance_id'] = 1
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)
        update = {}
        update['size'] = '10g'
        update['metadata'] = {'type': 'test2'}

        self.db.api.volume_update(self.context, 1, update)
        volume = self.db.api.volume_get(self.context, 1)
        self.assertEqual('10g', volume.size)
        metadata = self.db.api.volume_metadata_get(self.context, 1)
        self.assertEqual('test2', metadata['type'])

    @attr(kind='small')
    def test_volume_update_db_not_found(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['instance_id'] = 1
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)

        self.assertRaises(exception.VolumeNotFound,
                          self.db.volume_update,
                          self.context, 2, {'size': '10g'})

    @attr(kind='small')
    def test_volume_metadata_get(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['instance_id'] = 1
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)

        meta = self.db.api.volume_metadata_get(self.context, 1)
        self.assertEqual('test', meta['type'])

    @attr(kind='small')
    def test_volume_metadata_get_db_not_found(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['instance_id'] = 1
        self.db.api.volume_create(self.context, vol)

        meta = self.db.api.volume_metadata_get(self.context, 1)
        self.assertEqual({}, meta)

    @attr(kind='small')
    def test_volume_metadata_delete(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['instance_id'] = 1
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)
        self.db.api.volume_metadata_delete(self.context, 1, 'type')
        meta = self.db.api.volume_metadata_get(self.context, 1)
        self.assertEqual({}, meta)

    @attr(kind='small')
    def test_volume_metadata_delete_db_not_found(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['instance_id'] = 1
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)
        self.db.api.volume_metadata_delete(self.context, 1, 'not_found')
        result = self.db.volume_metadata_get(self.context, 1)
        self.assertEqual('test', result['type'])

    @attr(kind='small')
    def test_volume_metadata_get_item(self):
#        raise SkipTest("No method found in db.api")
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['instance_id'] = 1
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)
        meta = self.db.api.volume_metadata_get_item(
                                    self.context, 1, 'type')
        self.assertEqual('type', meta.key)
        self.assertEqual('test', meta.value)

    @attr(kind='small')
    def test_volume_metadata_get_item_db_not_found(self):
#        raise SkipTest("No method found in db.api")
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['instance_id'] = 1
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)
        self.assertRaises(exception.VolumeMetadataNotFound,
                          self.db.api.volume_metadata_get_item,
                          self.context, 1, 'not_exist')

    @attr(kind='small')
    def test_volume_metadata_update(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['instance_id'] = 1
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)
        self.db.api.volume_metadata_update(self.context, 1,
                                           {'type': 'test2'}, False)
        meta = self.db.api.volume_metadata_get(self.context, 1)
        self.assertEqual('test2', meta['type'])

    @attr(kind='small')
    def test_volume_metadata_update_with_delete(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['instance_id'] = 1
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)
        self.db.api.volume_metadata_update(self.context, 1,
                                           {'type': 'test2'}, True)
        meta = self.db.api.volume_metadata_get(self.context, 1)
        self.assertEqual('test2', meta['type'])

    @attr(kind='small')
    def test_volume_metadata_update_with_delete_multi(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['instance_id'] = 1
        vol['metadata'] = {'type': 'test', 'key1': 'value1'}
        self.db.api.volume_create(self.context, vol)
        self.db.api.volume_metadata_update(self.context, 1,
                                           {'type': 'test2'}, True)
        meta = self.db.api.volume_metadata_get(self.context, 1)
        self.assertEqual('test2', meta['type'])
        self.assertTrue('key1' not in meta)

    @attr(kind='small')
    def test_volume_metadata_update_new_item(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['instance_id'] = 1
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)
        self.db.api.volume_metadata_update(self.context, 1,
                                           {'type2': 'test2'}, False)
        meta = self.db.api.volume_metadata_get(self.context, 1)
        self.assertEqual('test', meta['type'])
        self.assertEqual('test2', meta['type2'])

    @attr(kind='small')
    def test_volume_metadata_update_db_not_found(self):
        # setup
        vol = {}
        vol['id'] = 1
        vol['size'] = '1g'
        vol['snapshot_id'] = None
        vol['user_id'] = 'fake'
        vol['project_id'] = 'fake'
        vol['availability_zone'] = FLAGS.storage_availability_zone
        vol['status'] = "creating"
        vol['attach_status'] = "detached"
        vol['instance_id'] = 1
        vol['metadata'] = {'type': 'test'}
        self.db.api.volume_create(self.context, vol)
        self.assertRaises(exception.VolumeNotFound,
                          self.db.api.volume_metadata_update,
                          self.context, 2, {'type2': 'test2'}, False)

    @attr(kind='small')
    def test_snapshot_create(self):
        snap = {}
        snap['id'] = 1
        snap['user_id'] = 'fake'
        snap['project_id'] = 'fake'
        snap['volume_id'] = 1
        snap['status'] = 'creating'
        snap['progress'] = '10%'
        snap['volume_size'] = None
        snap['display_name'] = 'test'
        snap['display_description'] = 'test'

        self.db.api.snapshot_create(self.context, snap)
        result = self.db.api.snapshot_get(self.context, 1)
        self.assertEqual('fake', result.user_id)
        self.assertEqual('fake', result.project_id)
        self.assertEqual(1, result.volume_id)
        self.assertEqual('creating', result.status)
        self.assertEqual('10%', result.progress)
        self.assertEqual(None, result.volume_size)
        self.assertEqual('test', result.display_name)
        self.assertEqual('test', result.display_description)

    @attr(kind='small')
    def test_snapshot_create_db_duplicate(self):
        snap = {}
        snap['id'] = 1
        snap['user_id'] = 'fake'
        snap['project_id'] = 'fake'
        snap['volume_id'] = 1
        snap['status'] = 'creating'
        snap['progress'] = '10%'
        snap['volume_size'] = None
        snap['display_name'] = 'test'
        snap['display_description'] = 'test'

        self.db.api.snapshot_create(self.context, snap)
        self.assertRaises(exception.Duplicate,
                          self.db.api.snapshot_create,
                          self.context, snap)

    @attr(kind='small')
    def test_snapshot_destroy(self):
        snap = {}
        snap['id'] = 1
        snap['user_id'] = 'fake'
        snap['project_id'] = 'fake'
        snap['volume_id'] = 1
        snap['status'] = 'creating'
        snap['progress'] = '10%'
        snap['volume_size'] = None
        snap['display_name'] = 'test'
        snap['display_description'] = 'test'

        self.db.api.snapshot_create(self.context, snap)
        self.db.api.snapshot_destroy(self.context, 1)
        self.assertRaises(exception.SnapshotNotFound,
                          self.db.api.snapshot_get,
                          self.context, 1)

    @attr(kind='small')
    def test_snapshot_destroy_db_not_found(self):
        """
        should be raise error.
        """
        snap = {}
        snap['id'] = 1
        snap['user_id'] = 'fake'
        snap['project_id'] = 'fake'
        snap['volume_id'] = 1
        snap['status'] = 'creating'
        snap['progress'] = '10%'
        snap['volume_size'] = None
        snap['display_name'] = 'test'
        snap['display_description'] = 'test'

        self.db.api.snapshot_create(self.context, snap)
        self.db.api.snapshot_destroy(self.context, 2)
        result = self.db.api.snapshot_get(self.context, 1)
        self.assertTrue(result is not None)

    @attr(kind='small')
    def test_snapshot_get(self):
        snap = {}
        snap['id'] = 1
        snap['user_id'] = 'fake'
        snap['project_id'] = 'fake'
        snap['volume_id'] = 1
        snap['status'] = 'creating'
        snap['progress'] = '10%'
        snap['volume_size'] = None
        snap['display_name'] = 'test'
        snap['display_description'] = 'test'

        self.db.api.snapshot_create(self.context, snap)
        result = self.db.api.snapshot_get(self.context, 1)
        self.assertTrue(result is not None)

    @attr(kind='small')
    def test_snapshot_get_user(self):
        snap = {}
        snap['id'] = 1
        snap['user_id'] = 'fake'
        snap['project_id'] = 'fake'
        snap['volume_id'] = 1
        snap['status'] = 'creating'
        snap['progress'] = '10%'
        snap['volume_size'] = None
        snap['display_name'] = 'test'
        snap['display_description'] = 'test'

        self.db.api.snapshot_create(self.context, snap)

        self.context.is_admin = False
        self.context.user_id = 'fake'
        self.context.project_id = 'fake'
        result = self.db.api.snapshot_get(self.context, 1)
        self.assertTrue(result is not None)

    @attr(kind='small')
    def test_snapshot_get_db_not_found(self):
        snap = {}
        snap['id'] = 1
        snap['user_id'] = 'fake'
        snap['project_id'] = 'fake'
        snap['volume_id'] = 1
        snap['status'] = 'creating'
        snap['progress'] = '10%'
        snap['volume_size'] = None
        snap['display_name'] = 'test'
        snap['display_description'] = 'test'

        self.db.api.snapshot_create(self.context, snap)
        self.db.api.snapshot_destroy(self.context, 1)
        self.assertRaises(exception.SnapshotNotFound,
                          self.db.api.snapshot_get,
                          self.context, 1)

    @attr(kind='small')
    def test_snapshot_get_all(self):
        snap = {}
        snap['id'] = 1
        snap['user_id'] = 'fake'
        snap['project_id'] = 'fake'
        snap['volume_id'] = 1
        snap['status'] = 'creating'
        snap['progress'] = '10%'
        snap['volume_size'] = None
        snap['display_name'] = 'test'
        snap['display_description'] = 'test'

        self.db.api.snapshot_create(self.context, snap)
        snaps = self.db.api.snapshot_get_all(self.context)
        self.assertEqual(1, snaps[0].id)

    @attr(kind='small')
    def test_snapshot_get_all_db_not_found(self):
        snaps = self.db.api.snapshot_get_all(self.context)
        self.assertEqual([], snaps)

    @attr(kind='small')
    def test_snapshot_get_all_by_project(self):
        snap = {}
        snap['id'] = 1
        snap['user_id'] = 'fake'
        snap['project_id'] = 'fake'
        snap['volume_id'] = 1
        snap['status'] = 'creating'
        snap['progress'] = '10%'
        snap['volume_size'] = None
        snap['display_name'] = 'test'
        snap['display_description'] = 'test'

        self.db.api.snapshot_create(self.context, snap)
        snaps = self.db.api.snapshot_get_all_by_project(self.context, 'fake')
        self.assertEqual(1, snaps[0].id)

    @attr(kind='small')
    def test_snapshot_get_all_by_project_db_not_found(self):
        snap = {}
        snap['id'] = 1
        snap['user_id'] = 'fake'
        snap['project_id'] = 'fake'
        snap['volume_id'] = 1
        snap['status'] = 'creating'
        snap['progress'] = '10%'
        snap['volume_size'] = None
        snap['display_name'] = 'test'
        snap['display_description'] = 'test'

        self.db.api.snapshot_create(self.context, snap)
        snaps = self.db.api.snapshot_get_all_by_project(self.context, 'fake2')
        self.assertEqual([], snaps)

    @attr(kind='small')
    def test_snapshot_update(self):
        snap = {}
        snap['id'] = 1
        snap['user_id'] = 'fake'
        snap['project_id'] = 'fake'
        snap['volume_id'] = 1
        snap['status'] = 'creating'
        snap['progress'] = '10%'
        snap['volume_size'] = None
        snap['display_name'] = 'test'
        snap['display_description'] = 'test'

        self.db.api.snapshot_create(self.context, snap)
        self.db.api.snapshot_update(self.context, 1,
                                    {'status': 'available',
                                     'progress': '100%'})
        result = self.db.api.snapshot_get(self.context, 1)
        self.assertEqual('available', result.status)
        self.assertEqual('100%', result.progress)

    @attr(kind='small')
    def test_snapshot_update_db_not_found(self):
        snap = {}
        snap['id'] = 1
        snap['user_id'] = 'fake'
        snap['project_id'] = 'fake'
        snap['volume_id'] = 1
        snap['status'] = 'creating'
        snap['progress'] = '10%'
        snap['volume_size'] = None
        snap['display_name'] = 'test'
        snap['display_description'] = 'test'

        self.db.api.snapshot_create(self.context, snap)
        self.assertRaises(exception.SnapshotNotFound,
                          self.db.api.snapshot_update,
                          self.context, 2,
                          {'status': 'available', 'progress': '100%'})

    @attr(kind='small')
    def test_block_device_mapping_create(self):
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        self.db.api.snapshot_create(self.context, {'id': 1, 'volume_id': 1})

        bdm = {}
        bdm['id'] = 1
        bdm['instance_id'] = 1
        bdm['device_name'] = '/dev/sdh'
        bdm['virtual_name'] = '/dev/sdb'
        bdm['volume_id'] = 1
        bdm['no_device'] = False

        self.db.api.block_device_mapping_create(self.context, bdm)
        results = self.db.api.block_device_mapping_get_all_by_instance(
                                                            self.context, 1)
        result = results[0]
        self.assertEqual(1, result.instance.id)
        self.assertEqual(False, result.delete_on_termination)
        self.assertEqual('/dev/sdh', result.device_name)
        self.assertEqual('/dev/sdb', result.virtual_name)
        self.assertEqual(1, result.volume.id)
        self.assertEqual('1g', result.volume.size)
        self.assertEqual(False, result.no_device)

    @attr(kind='small')
    def test_block_device_mapping_create_db_duplicate(self):
        """
        looks never duplicate occur, but it is right?
        """
#        raise SkipTest("Block device never duplicate.")
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        self.db.api.snapshot_create(self.context, {'id': 1, 'volume_id': 1})

        bdm = {}
        bdm['id'] = 1
        bdm['instance_id'] = 1
        bdm['device_name'] = '/dev/sdh'
        bdm['virtual_name'] = '/dev/sdb'
        bdm['volume_id'] = 1
        bdm['no_device'] = False

        self.db.api.block_device_mapping_create(self.context, bdm)
        self.db.api.block_device_mapping_create(self.context, bdm)

    @attr(kind='small')
    def test_block_device_mapping_update(self):
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        self.db.api.snapshot_create(self.context, {'id': 1, 'volume_id': 1})

        bdm = {}
        bdm['id'] = 1
        bdm['instance_id'] = 1
        bdm['device_name'] = '/dev/sdh'
        bdm['virtual_name'] = '/dev/sdb'
        bdm['volume_id'] = 1
        bdm['no_device'] = False

        self.db.api.block_device_mapping_create(self.context, bdm)
        self.db.api.block_device_mapping_update(
                                    self.context, 1,
                                    {'device_name': '/dev/sdg'})
        results = self.db.api.block_device_mapping_get_all_by_instance(
                                                            self.context, 1)
        result = results[0]
        self.assertEqual(1, result.instance.id)
        self.assertEqual(False, result.delete_on_termination)
        self.assertEqual('/dev/sdg', result.device_name)
        self.assertEqual('/dev/sdb', result.virtual_name)
        self.assertEqual(1, result.volume.id)
        self.assertEqual('1g', result.volume.size)
        self.assertEqual(False, result.no_device)

    @attr(kind='small')
    def test_block_device_mapping_update_db_not_found(self):
        """
        should be raise error.
        """
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        self.db.api.snapshot_create(self.context, {'id': 1, 'volume_id': 1})

        bdm = {}
        bdm['id'] = 1
        bdm['instance_id'] = 1
        bdm['device_name'] = '/dev/sdh'
        bdm['virtual_name'] = '/dev/sdb'
        bdm['volume_id'] = 1
        bdm['no_device'] = False

        self.db.api.block_device_mapping_create(self.context, bdm)
        self.db.api.block_device_mapping_update(
                                    self.context, 2,
                                    {'instance_id': 2,
                                     'device_name': '/dev/sdg'})
        results = self.db.api.block_device_mapping_get_all_by_instance(
                                                            self.context, 1)
        result = results[0]
        self.assertEqual('/dev/sdh', result.device_name)

    @attr(kind='small')
    def test_block_device_mapping_update_or_create(self):
        """
        when update or create, If the virtual_name not specified
            then raise KeyError.
        """
#        raise SkipTest("If the virtual_name not specified\
#            then raise KeyError.")
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        self.db.api.snapshot_create(self.context, {'id': 1, 'volume_id': 1})

        bdm = {}
        bdm['id'] = 1
        bdm['instance_id'] = 1
        bdm['device_name'] = '/dev/sdh'
        bdm['virtual_name'] = '/dev/sdb'
        bdm['volume_id'] = 1
        bdm['no_device'] = False

        self.db.api.block_device_mapping_create(self.context, bdm)
        self.db.api.block_device_mapping_update_or_create(
                                    self.context, {'instance_id': 1,
                                                   'device_name': '/dev/sdg'})
        results = self.db.api.block_device_mapping_get_all_by_instance(
                                                            self.context, 2)
        result = results[0]
        self.assertEqual('/dev/sdg', result.device_name)

    @attr(kind='small')
    def test_block_device_mapping_update_or_create_update(self):
        """
        when update or create, If the virtual_name not specified
            then raise KeyError.
        """
#        raise SkipTest("If the virtual_name not specified\
#            then raise KeyError.")
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        self.db.api.snapshot_create(self.context, {'id': 1, 'volume_id': 1})

        bdm = {}
        bdm['id'] = 1
        bdm['instance_id'] = 1
        bdm['device_name'] = '/dev/sdh'
        bdm['virtual_name'] = '/dev/sdb'
        bdm['volume_id'] = 1
        bdm['no_device'] = False

        self.db.api.block_device_mapping_create(self.context, bdm)
        self.db.api.block_device_mapping_update_or_create(
                                    self.context, {'instance_id': 1,
                                                   'no_device': True,
                                                   'device_name': '/dev/sdh'})
        results = self.db.api.block_device_mapping_get_all_by_instance(
                                                            self.context, 1)
        result = results[0]
        self.assertEqual('/dev/sdh', result.device_name)
        self.assertEqual(True, result.no_device)

    @attr(kind='small')
    def test_block_device_mapping_update_or_create_virtual(self):
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        self.db.api.snapshot_create(self.context, {'id': 1, 'volume_id': 1})

        bdm = {}
        bdm['id'] = 1
        bdm['instance_id'] = 1
        bdm['device_name'] = '/dev/sdh'
        bdm['virtual_name'] = 'swap'
        bdm['volume_id'] = 1
        bdm['no_device'] = False
        self.db.api.block_device_mapping_create(self.context, bdm)
        self.db.api.block_device_mapping_update_or_create(
                                    self.context, {'instance_id': 1,
                                                   'virtual_name': 'swap',
                                                   'device_name': '/dev/sdg'})
        results = self.db.api.block_device_mapping_get_all_by_instance(
                                                            self.context, 1)
        result = results[0]
        self.assertEqual('/dev/sdg', result.device_name)
        self.assertNotEqual(1, result.id)

    @attr(kind='small')
    def test_block_device_mapping_get_all_by_instance(self):
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        self.db.api.snapshot_create(self.context, {'id': 1, 'volume_id': 1})

        bdm = {}
        bdm['id'] = 1
        bdm['instance_id'] = 1
        bdm['device_name'] = '/dev/sdh'
        bdm['virtual_name'] = '/dev/sdb'
        bdm['volume_id'] = 1
        bdm['no_device'] = False

        self.db.api.block_device_mapping_create(self.context, bdm)
        results = self.db.api.block_device_mapping_get_all_by_instance(
                                                            self.context, 1)
        result = results[0]
        self.assertEqual(1, result.instance.id)

    @attr(kind='small')
    def test_block_device_mapping_get_all_by_instance_db_not_found(self):
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        self.db.api.snapshot_create(self.context, {'id': 1, 'volume_id': 1})

        bdm = {}
        bdm['id'] = 1
        bdm['instance_id'] = 1
        bdm['device_name'] = '/dev/sdh'
        bdm['virtual_name'] = '/dev/sdb'
        bdm['volume_id'] = 1
        bdm['no_device'] = False

        self.db.api.block_device_mapping_create(self.context, bdm)
        results = self.db.api.block_device_mapping_get_all_by_instance(
                                                            self.context, 2)
        self.assertEqual([], results)

    @attr(kind='small')
    def test_block_device_mapping_destroy(self):
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        self.db.api.snapshot_create(self.context, {'id': 1, 'volume_id': 1})

        bdm = {}
        bdm['id'] = 1
        bdm['instance_id'] = 1
        bdm['device_name'] = '/dev/sdh'
        bdm['virtual_name'] = '/dev/sdb'
        bdm['volume_id'] = 1
        bdm['no_device'] = False

        self.db.api.block_device_mapping_create(self.context, bdm)
        self.db.api.block_device_mapping_destroy(self.context, 1)
        results = self.db.api.block_device_mapping_get_all_by_instance(
                                                            self.context, 1)
        self.assertEqual([], results)

    @attr(kind='small')
    def test_block_device_mapping_destroy_db_not_found(self):
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        self.db.api.snapshot_create(self.context, {'id': 1, 'volume_id': 1})

        bdm = {}
        bdm['id'] = 1
        bdm['instance_id'] = 1
        bdm['device_name'] = '/dev/sdh'
        bdm['virtual_name'] = '/dev/sdb'
        bdm['volume_id'] = 1
        bdm['no_device'] = False

        self.db.api.block_device_mapping_create(self.context, bdm)
        self.db.api.block_device_mapping_destroy(self.context, 2)
        results = self.db.api.block_device_mapping_get_all_by_instance(
                                                            self.context, 1)
        self.assertTrue(len(results) > 0)

    @attr(kind='small')
    def test_block_device_mapping_destroy_by_instance_and_volume(self):
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        self.db.api.snapshot_create(self.context, {'id': 1, 'volume_id': 1})

        bdm = {}
        bdm['id'] = 1
        bdm['instance_id'] = 1
        bdm['device_name'] = '/dev/sdh'
        bdm['virtual_name'] = '/dev/sdb'
        bdm['volume_id'] = 1
        bdm['no_device'] = False

        self.db.api.block_device_mapping_create(self.context, bdm)
        self.db.api.block_device_mapping_destroy_by_instance_and_volume(
                                                            self.context, 1, 1)
        results = self.db.api.block_device_mapping_get_all_by_instance(
                                                            self.context, 1)
        self.assertEqual([], results)

    @attr(kind='small')
    def test_block_device_mapping_destroy_by_inst_and_vol_db_not_found(self):
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.volume_create(self.context, {'id': 1, 'size': '1g'})
        self.db.api.snapshot_create(self.context, {'id': 1, 'volume_id': 1})

        bdm = {}
        bdm['id'] = 1
        bdm['instance_id'] = 1
        bdm['device_name'] = '/dev/sdh'
        bdm['virtual_name'] = '/dev/sdb'
        bdm['volume_id'] = 1
        bdm['no_device'] = False

        self.db.api.block_device_mapping_create(self.context, bdm)
        self.db.api.block_device_mapping_destroy_by_instance_and_volume(
                                                            self.context, 2, 2)
        results = self.db.api.block_device_mapping_get_all_by_instance(
                                                            self.context, 1)
        self.assertTrue(len(results) > 0)

    @attr(kind='small')
    def test_security_group_create(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'

        self.db.api.security_group_create(self.context, group)
        result = self.db.api.security_group_get(self.context, 1)
        self.assertEqual('default', result.name)
        self.assertEqual('test', result.description)
        self.assertEqual('fake', result.user_id)
        self.assertEqual('fake', result.project_id)

    @attr(kind='small')
    def test_security_group_create_db_duplicate(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'

        self.db.api.security_group_create(self.context, group)
        self.assertRaises(exception.Duplicate,
                          self.db.api.security_group_create,
                          self.context, group)

    @attr(kind='small')
    def test_security_group_get_all(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'

        self.db.api.security_group_create(self.context, group)
        results = self.db.api.security_group_get_all(self.context)
        result = results[0]
        self.assertEqual('default', result.name)
        self.assertEqual('test', result.description)
        self.assertEqual('fake', result.user_id)
        self.assertEqual('fake', result.project_id)

    @attr(kind='small')
    def test_security_group_get_all_db_not_found(self):
        results = self.db.api.security_group_get_all(self.context)
        self.assertEqual([], results)

    @attr(kind='small')
    def test_security_group_get(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'

        self.db.api.security_group_create(self.context, group)
        result = self.db.api.security_group_get(self.context, 1)
        self.assertEqual('default', result.name)
        self.assertEqual('test', result.description)
        self.assertEqual('fake', result.user_id)
        self.assertEqual('fake', result.project_id)

    @attr(kind='small')
    def test_security_group_get_user(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'

        self.db.api.security_group_create(self.context, group)
        self.context.is_admin = False
        self.context.user_id = 'fake'
        self.context.project_id = 'fake'
        result = self.db.api.security_group_get(self.context, 1)
        self.assertEqual('default', result.name)
        self.assertEqual('test', result.description)
        self.assertEqual('fake', result.user_id)
        self.assertEqual('fake', result.project_id)

    @attr(kind='small')
    def test_security_group_get_db_not_found(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'

        self.db.api.security_group_create(self.context, group)
        self.context.is_admin = False
        self.context.user_id = 'fake2'
        self.context.project_id = 'fake2'
        self.assertRaises(exception.SecurityGroupNotFound,
                          self.db.api.security_group_get,
                          self.context, 1)

    @attr(kind='small')
    def test_security_group_get_by_name(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'

        self.db.api.security_group_create(self.context, group)
        result = self.db.api.security_group_get_by_name(
                                            self.context, 'fake', 'default')
        self.assertEqual('default', result.name)
        self.assertEqual('test', result.description)
        self.assertEqual('fake', result.user_id)
        self.assertEqual('fake', result.project_id)

    @attr(kind='small')
    def test_security_group_get_by_name_db_not_found(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'

        self.db.api.security_group_create(self.context, group)
        self.assertRaises(exception.SecurityGroupNotFoundForProject,
                          self.db.api.security_group_get_by_name,
                          self.context, 'fake', 'fake')

    @attr(kind='small')
    def test_security_group_get_by_project(self):
        """
        not good method name.
        """
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'

        self.db.api.security_group_create(self.context, group)
        results = self.db.api.security_group_get_by_project(
                                            self.context, 'fake')
        result = results[0]
        self.assertEqual('default', result.name)
        self.assertEqual('test', result.description)
        self.assertEqual('fake', result.user_id)
        self.assertEqual('fake', result.project_id)

    @attr(kind='small')
    def test_security_group_get_by_project_db_not_found(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'

        self.db.api.security_group_create(self.context, group)
        result = self.db.api.security_group_get_by_project(
                                            self.context, 'fake2')
        self.assertEqual([], result)

    @attr(kind='small')
    def test_security_group_get_by_instance(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'

        self.db.api.security_group_create(self.context, group)
        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.instance_add_security_group(self.context, 1, 1)
        results = self.db.api.security_group_get_by_instance(self.context, 1)
        result = results[0]
        self.assertEqual('default', result.name)
        self.assertEqual('test', result.description)
        self.assertEqual('fake', result.user_id)
        self.assertEqual('fake', result.project_id)

    @attr(kind='small')
    def test_security_group_get_by_instance_db_not_found(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'

        self.db.api.security_group_create(self.context, group)
        self.db.api.instance_create(self.context, {'id': 1})
        results = self.db.api.security_group_get_by_instance(self.context, 1)
        self.assertEqual([], results)

    @attr(kind='small')
    def test_security_group_exists(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'

        self.db.api.security_group_create(self.context, group)
        result = self.db.api.security_group_exists(
                                    self.context, 'fake', 'default')
        self.assertTrue(result)

    @attr(kind='small')
    def test_security_group_exists_db_not_found(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'

        self.db.api.security_group_create(self.context, group)
        result = self.db.api.security_group_exists(
                                    self.context, 'fake', 'default2')
        self.assertFalse(result)

    @attr(kind='small')
    def test_security_group_destroy(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'
        self.db.api.security_group_create(self.context, group)

        rule = {}
        rule['id'] = 1
        rule['parent_group_id'] = 1
        rule['group_id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 8080
        rule['cidr'] = '0.0.0.0'
        self.db.api.security_group_rule_create(self.context, rule)

        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.instance_add_security_group(self.context, 1, 1)
        self.db.api.security_group_destroy(self.context, 1)

        self.assertRaises(exception.SecurityGroupNotFound,
                          self.db.api.security_group_get,
                          self.context, 1)
        self.assertRaises(exception.SecurityGroupNotFoundForRule,
                          self.db.api.security_group_rule_get,
                          self.context, 1)

    @attr(kind='small')
    def test_security_group_destroy_db_not_found(self):
#        raise SkipTest("NotFound exception not raise")
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'
        self.db.api.security_group_create(self.context, group)

        rule = {}
        rule['id'] = 1
        rule['parent_group_id'] = 1
        rule['group_id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 8080
        rule['cidr'] = '0.0.0.0'
        self.db.api.security_group_rule_create(self.context, rule)

        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.instance_add_security_group(self.context, 1, 1)

        self.assertRaises(exception.SecurityGroupNotFound,
                          self.db.api.security_group_destroy,
                          self.context, 2)

    @attr(kind='small')
    def test_security_group_destroy_all(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'
        self.db.api.security_group_create(self.context, group)

        rule = {}
        rule['id'] = 1
        rule['parent_group_id'] = 1
        rule['group_id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 8080
        rule['cidr'] = '0.0.0.0'
        self.db.api.security_group_rule_create(self.context, rule)

        self.db.api.instance_create(self.context, {'id': 1})
        self.db.api.instance_add_security_group(self.context, 1, 1)
        self.db.api.security_group_destroy_all(self.context)

        self.assertRaises(exception.SecurityGroupNotFound,
                          self.db.api.security_group_get,
                          self.context, 1)
        self.assertRaises(exception.SecurityGroupNotFoundForRule,
                          self.db.api.security_group_rule_get,
                          self.context, 1)

    @attr(kind='small')
    def test_security_group_destroy_all_db_not_found(self):
        self.db.api.security_group_destroy_all(self.context)

        self.assertRaises(exception.SecurityGroupNotFound,
                          self.db.api.security_group_get,
                          self.context, 1)
        self.assertRaises(exception.SecurityGroupNotFoundForRule,
                          self.db.api.security_group_rule_get,
                          self.context, 1)

    @attr(kind='small')
    def test_security_group_rule_create(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'
        self.db.api.security_group_create(self.context, group)

        rule = {}
        rule['id'] = 1
        rule['parent_group_id'] = 1
        rule['group_id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 8080
        rule['cidr'] = '0.0.0.0'
        self.db.api.security_group_rule_create(self.context, rule)

        result = self.db.api.security_group_rule_get(self.context, 1)
        self.assertEqual('tcp', result.protocol)
        self.assertEqual(0, result.from_port)
        self.assertEqual(8080, result.to_port)
        self.assertEqual('0.0.0.0', result.cidr)

    @attr(kind='small')
    def test_security_group_rule_create_db_duplicate(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'
        self.db.api.security_group_create(self.context, group)

        rule = {}
        rule['id'] = 1
        rule['parent_group_id'] = 1
        rule['group_id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 8080
        rule['cidr'] = '0.0.0.0'
        self.db.api.security_group_rule_create(self.context, rule)
        self.assertRaises(exception.Duplicate,
                          self.db.api.security_group_rule_create,
                          self.context, rule)

    @attr(kind='small')
    def test_security_group_rule_get(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'
        self.db.api.security_group_create(self.context, group)

        rule = {}
        rule['id'] = 1
        rule['parent_group_id'] = 1
        rule['group_id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 8080
        rule['cidr'] = '0.0.0.0'
        self.db.api.security_group_rule_create(self.context, rule)

        result = self.db.api.security_group_rule_get(self.context, 1)
        self.assertEqual('tcp', result.protocol)
        self.assertEqual(0, result.from_port)
        self.assertEqual(8080, result.to_port)
        self.assertEqual('0.0.0.0', result.cidr)

    @attr(kind='small')
    def test_security_group_rule_get_parameter_context(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'
        self.db.api.security_group_create(self.context, group)

        rule = {}
        rule['id'] = 1
        rule['parent_group_id'] = 1
        rule['group_id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 8080
        rule['cidr'] = '0.0.0.0'
        self.db.api.security_group_rule_create(self.context, rule)
        normal_ctx = context.RequestContext(self.user_id, self.project_id,
                                              is_admin=False)

        result = self.db.api.security_group_rule_get(normal_ctx, 1)
        self.assertEqual('tcp', result.protocol)
        self.assertEqual(0, result.from_port)
        self.assertEqual(8080, result.to_port)
        self.assertEqual('0.0.0.0', result.cidr)

    @attr(kind='small')
    def test_security_group_rule_get_db_not_found(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'
        self.db.api.security_group_create(self.context, group)

        rule = {}
        rule['id'] = 1
        rule['parent_group_id'] = 1
        rule['group_id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 8080
        rule['cidr'] = '0.0.0.0'
        self.db.api.security_group_rule_create(self.context, rule)

        self.assertRaises(exception.SecurityGroupNotFoundForRule,
                          self.db.api.security_group_rule_get,
                          self.context, 2)

    @attr(kind='small')
    def test_security_group_rule_get_by_security_group(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'
        self.db.api.security_group_create(self.context, group)

        rule = {}
        rule['id'] = 1
        rule['parent_group_id'] = 1
        rule['group_id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 8080
        rule['cidr'] = '0.0.0.0'
        self.db.api.security_group_rule_create(self.context, rule)

        result = self.db.api.security_group_rule_get_by_security_group(
                                                            self.context, 1)
        self.assertEqual('tcp', result[0].protocol)
        self.assertEqual(0, result[0].from_port)
        self.assertEqual(8080, result[0].to_port)
        self.assertEqual('0.0.0.0', result[0].cidr)

    @attr(kind='small')
    def test_security_group_rule_get_by_security_group_user(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'
        self.db.api.security_group_create(self.context, group)

        rule = {}
        rule['id'] = 1
        rule['parent_group_id'] = 1
        rule['group_id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 8080
        rule['cidr'] = '0.0.0.0'
        self.db.api.security_group_rule_create(self.context, rule)
        self.context.is_admin = False
        self.context.user_id = 'fake'
        self.context.project_id = 'fake'

        result = self.db.api.security_group_rule_get_by_security_group(
                                                            self.context, 1)
        self.assertEqual('tcp', result[0].protocol)
        self.assertEqual(0, result[0].from_port)
        self.assertEqual(8080, result[0].to_port)
        self.assertEqual('0.0.0.0', result[0].cidr)

    @attr(kind='small')
    def test_security_group_rule_get_by_security_group_db_not_found(self):
        """
        should be raise error.
        """
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'
        self.db.api.security_group_create(self.context, group)

        rule = {}
        rule['id'] = 1
        rule['parent_group_id'] = 2
        rule['group_id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 8080
        rule['cidr'] = '0.0.0.0'
        self.db.api.security_group_rule_create(self.context, rule)

        result = self.db.api.security_group_rule_get_by_security_group(
                                                            self.context, 1)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_security_group_rule_get_by_security_group_grantee(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'
        self.db.api.security_group_create(self.context, group)

        rule = {}
        rule['id'] = 1
        rule['parent_group_id'] = 1
        rule['group_id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 8080
        rule['cidr'] = '0.0.0.0'
        self.db.api.security_group_rule_create(self.context, rule)

        result = self.db.api.security_group_rule_get_by_security_group_grantee(
                                                            self.context, 1)
        self.assertEqual('tcp', result[0].protocol)
        self.assertEqual(0, result[0].from_port)
        self.assertEqual(8080, result[0].to_port)
        self.assertEqual('0.0.0.0', result[0].cidr)

    @attr(kind='small')
    def test_security_group_rule_get_by_security_group_grantee_user(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'
        self.db.api.security_group_create(self.context, group)

        rule = {}
        rule['id'] = 1
        rule['parent_group_id'] = 1
        rule['group_id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 8080
        rule['cidr'] = '0.0.0.0'
        self.db.api.security_group_rule_create(self.context, rule)
        self.context.is_admin = False
        self.context.user_id = 'fake'
        self.context.project_id = 'fake'

        result = self.db.api.security_group_rule_get_by_security_group_grantee(
                                                            self.context, 1)
        self.assertEqual('tcp', result[0].protocol)
        self.assertEqual(0, result[0].from_port)
        self.assertEqual(8080, result[0].to_port)
        self.assertEqual('0.0.0.0', result[0].cidr)

    @attr(kind='small')
    def test_security_group_rule_get_by_security_gp_grantee_db_not_found(self):
        """
        should be raise error.
        """
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'
        self.db.api.security_group_create(self.context, group)

        rule = {}
        rule['id'] = 1
        rule['parent_group_id'] = 1
        rule['group_id'] = 2
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 8080
        rule['cidr'] = '0.0.0.0'
        self.db.api.security_group_rule_create(self.context, rule)

        result = self.db.api.security_group_rule_get_by_security_group_grantee(
                                                            self.context, 1)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_security_group_rule_destroy(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'
        self.db.api.security_group_create(self.context, group)

        rule = {}
        rule['id'] = 1
        rule['parent_group_id'] = 1
        rule['group_id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 8080
        rule['cidr'] = '0.0.0.0'
        self.db.api.security_group_rule_create(self.context, rule)

        self.db.api.security_group_rule_destroy(self.context, 1)
        self.assertRaises(exception.SecurityGroupNotFoundForRule,
                          self.db.api.security_group_rule_get,
                          self.context, 1)

    @attr(kind='small')
    def test_security_group_rule_destroy_db_not_found(self):
        group = {}
        group['id'] = 1
        group['name'] = 'default'
        group['description'] = 'test'
        group['user_id'] = 'fake'
        group['project_id'] = 'fake'
        self.db.api.security_group_create(self.context, group)

        rule = {}
        rule['id'] = 1
        rule['parent_group_id'] = 1
        rule['group_id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 8080
        rule['cidr'] = '0.0.0.0'
        self.db.api.security_group_rule_create(self.context, rule)

        self.assertRaises(exception.SecurityGroupNotFoundForRule,
                          self.db.api.security_group_rule_destroy,
                          self.context, 2)

    @attr(kind='small')
    def test_provider_fw_rule_create(self):
        # setup
        rule = {}
        rule['id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 80
        rule['cidr'] = '0.0.0.0'
        # test and assert
        self.db.api.provider_fw_rule_create(self.context, rule)
        results = self.db.api.provider_fw_rule_get_all(self.context)
        self.assertEqual('tcp', results[0].protocol)
        self.assertEqual(0, results[0].from_port)
        self.assertEqual(80, results[0].to_port)
        self.assertEqual('0.0.0.0', results[0].cidr)

    @attr(kind='small')
    def test_provider_fw_rule_create_db_duplicate(self):
        # setup
        rule = {}
        rule['id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 80
        rule['cidr'] = '0.0.0.0'
        # test and assert
        self.db.api.provider_fw_rule_create(self.context, rule)
        self.assertRaises(exception.Duplicate,
                          self.db.api.provider_fw_rule_create,
                          self.context, rule)

    @attr(kind='small')
    def test_provider_fw_rule_get_all(self):
        # setup
        rule = {}
        rule['id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 80
        rule['cidr'] = '0.0.0.0'
        # test and assert
        self.db.api.provider_fw_rule_create(self.context, rule)
        results = self.db.api.provider_fw_rule_get_all(self.context)
        self.assertEqual('tcp', results[0].protocol)
        self.assertEqual(0, results[0].from_port)
        self.assertEqual(80, results[0].to_port)
        self.assertEqual('0.0.0.0', results[0].cidr)

    @attr(kind='small')
    def test_provider_fw_rule_get_all_db_not_found(self):
        # test and assert
        results = self.db.api.provider_fw_rule_get_all(self.context)
        self.assertEqual([], results)

    @attr(kind='small')
    def test_provider_fw_rule_get_all_by_cidr(self):
        # setup
        rule = {}
        rule['id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 80
        rule['cidr'] = '0.0.0.0'
        # test and assert
        self.db.api.provider_fw_rule_create(self.context, rule)
        results = self.db.api.provider_fw_rule_get_all_by_cidr(
                                            self.context, '0.0.0.0')
        self.assertEqual('tcp', results[0].protocol)
        self.assertEqual(0, results[0].from_port)
        self.assertEqual(80, results[0].to_port)
        self.assertEqual('0.0.0.0', results[0].cidr)

    @attr(kind='small')
    def test_provider_fw_rule_get_all_by_cidr_db_not_found(self):
        # setup
        rule = {}
        rule['id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 80
        rule['cidr'] = '0.0.0.0'
        # test and assert
        self.db.api.provider_fw_rule_create(self.context, rule)
        results = self.db.api.provider_fw_rule_get_all_by_cidr(
                                            self.context, '10.1.0.0')
        self.assertEqual([], results)

    @attr(kind='small')
    def test_provider_fw_rule_destroy(self):
        # setup
        rule = {}
        rule['id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 80
        rule['cidr'] = '0.0.0.0'
        # test and assert
        self.db.api.provider_fw_rule_create(self.context, rule)
        self.db.api.provider_fw_rule_destroy(self.context, 1)
        results = self.db.api.provider_fw_rule_get_all(self.context)
        self.assertEqual([], results)

    @attr(kind='small')
    def test_provider_fw_rule_destroy_db_not_found(self):
        """
        shuld be raise error.
        """
        # setup
        rule = {}
        rule['id'] = 1
        rule['protocol'] = 'tcp'
        rule['from_port'] = 0
        rule['to_port'] = 80
        rule['cidr'] = '0.0.0.0'
        # test and assert
        self.db.api.provider_fw_rule_create(self.context, rule)
        self.db.api.provider_fw_rule_destroy(self.context, 2)
        results = self.db.api.provider_fw_rule_get_all(self.context)
        self.assertEqual('tcp', results[0].protocol)
        self.assertEqual(0, results[0].from_port)
        self.assertEqual(80, results[0].to_port)
        self.assertEqual('0.0.0.0', results[0].cidr)

    @attr(kind='small')
    def test_user_create(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        # test and assert
        self.db.api.user_create(self.context, user)
        result = self.db.api.user_get(self.context, 1)
        self.assertEqual('fake', result.name)
        self.assertEqual('access', result.access_key)
        self.assertEqual('secret', result.secret_key)
        self.assertEqual(True, result.is_admin)

    @attr(kind='small')
    def test_user_create_db_duplicate(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        # test and assert
        self.db.api.user_create(self.context, user)
        self.assertRaises(exception.Duplicate,
                          self.db.api.user_create,
                          self.context, user)

    @attr(kind='small')
    def test_user_get(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        # test and assert
        self.db.api.user_create(self.context, user)
        result = self.db.api.user_get(self.context, 1)
        self.assertEqual('fake', result.name)
        self.assertEqual('access', result.access_key)
        self.assertEqual('secret', result.secret_key)
        self.assertEqual(True, result.is_admin)

    @attr(kind='small')
    def test_user_get_db_not_found(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        # test and assert
        self.db.api.user_create(self.context, user)
        self.assertRaises(exception.UserNotFound,
                          self.db.api.user_get,
                          self.context, 2)

    @attr(kind='small')
    def test_user_get_by_uid(self):
        """
        user_get_by_uid
        """
#        raise SkipTest("Not implemented in sqlalchemy.api.")

    @attr(kind='small')
    def test_user_get_by_uid_db_not_found(self):
#        raise SkipTest("Not implemented in sqlalchemy.api.")

    @attr(kind='small')
    def test_user_get_by_access_key(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        # test and assert
        self.db.api.user_create(self.context, user)
        result = self.db.api.user_get_by_access_key(self.context, "access")
        self.assertEqual('fake', result.name)
        self.assertEqual('access', result.access_key)
        self.assertEqual('secret', result.secret_key)
        self.assertEqual(True, result.is_admin)

    @attr(kind='small')
    def test_user_get_by_access_key_db_not_found(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        # test and assert
        self.db.api.user_create(self.context, user)
        self.assertRaises(exception.AccessKeyNotFound,
                          self.db.api.user_get_by_access_key,
                          self.context, "notfound")

    @attr(kind='small')
    def test_user_delete(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        self.db.project_add_member(self.context, 1, 1)
        self.db.user_add_project_role(self.context, 1, 1, 'admin')
        self.db.user_add_role(self.context, 1, 'admin')

        # test and assert
        self.db.api.user_delete(self.context, 1)
        self.assertRaises(exception.UserNotFound,
                          self.db.api.user_get,
                          self.context, 1)

    @attr(kind='small')
    def test_user_delete_db_not_found(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        self.db.project_add_member(self.context, 1, 1)
        self.db.user_add_project_role(self.context, 1, 1, 'admin')
        self.db.user_add_role(self.context, 1, 'admin')

        # test and assert
        self.assertRaises(exception.UserNotFound,
                          self.db.api.user_delete,
                          self.context, 2)

    @attr(kind='small')
    def test_user_get_all(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        # test and assert
        self.db.api.user_create(self.context, user)
        results = self.db.api.user_get_all(self.context)
        self.assertEqual('fake', results[0].name)
        self.assertEqual('access', results[0].access_key)
        self.assertEqual('secret', results[0].secret_key)
        self.assertEqual(True, results[0].is_admin)

    @attr(kind='small')
    def test_user_get_all_db_not_found(self):
        results = self.db.api.user_get_all(self.context)
        self.assertEqual([], results)

    @attr(kind='small')
    def test_user_get_roles(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        # test and assert
        self.db.api.user_create(self.context, user)
        self.db.user_add_role(self.context, 1, 'roleA')
        self.db.user_add_role(self.context, 1, 'roleB')
        self.db.user_add_role(self.context, 1, 'roleC')
        roles = self.db.api.user_get_roles(self.context, 1)
        self.assertIn('roleA', roles)
        self.assertIn('roleB', roles)
        self.assertIn('roleC', roles)

    @attr(kind='small')
    def test_user_get_roles_db_not_found(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        # test and assert
        self.db.api.user_create(self.context, user)
        roles = self.db.api.user_get_roles(self.context, 1)
        self.assertEqual([], roles)

    @attr(kind='small')
    def test_user_get_roles_for_project(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        self.db.project_add_member(self.context, 1, 1)
        self.db.user_add_project_role(self.context, 1, 1, 'admin')
        self.db.user_add_project_role(self.context, 1, 1, 'user')
        self.db.user_add_role(self.context, 1, 'admin')

        # test and assert
        roles = self.db.api.user_get_roles_for_project(self.context, 1, 1)
        self.assertIn('admin', roles)
        self.assertIn('user', roles)

    @attr(kind='small')
    def test_user_get_roles_for_project_db_not_found(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        self.db.project_add_member(self.context, 1, 1)
        self.db.user_add_role(self.context, 1, 'admin')

        # test and assert
        roles = self.db.api.user_get_roles_for_project(self.context, 1, 1)
        self.assertEqual([], roles)

    @attr(kind='small')
    def test_user_remove_project_role(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        self.db.project_add_member(self.context, 1, 1)
        self.db.user_add_project_role(self.context, 1, 1, 'admin')
        self.db.user_add_project_role(self.context, 1, 1, 'user')
        self.db.user_add_role(self.context, 1, 'admin')

        # test and assert
        self.db.user_remove_project_role(self.context, 1, 1, 'admin')
        roles = self.db.api.user_get_roles_for_project(self.context, 1, 1)
        self.assertNotIn('admin', roles)
        self.assertIn('user', roles)

    @attr(kind='small')
    def test_user_remove_project_role_db_not_found(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        self.db.project_add_member(self.context, 1, 1)
        self.db.user_add_project_role(self.context, 1, 1, 'admin')
        self.db.user_add_project_role(self.context, 1, 1, 'user')
        self.db.user_add_role(self.context, 1, 'admin')

        # test and assert
        self.db.user_remove_project_role(self.context, 1, 1, 'not_found')
        roles = self.db.api.user_get_roles_for_project(self.context, 1, 1)
        self.assertIn('admin', roles)
        self.assertIn('user', roles)

    @attr(kind='small')
    def test_user_add_role(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        self.db.project_add_member(self.context, 1, 1)
        self.db.user_add_role(self.context, 1, 'admin')

        # test and assert
        roles = self.db.api.user_get_roles(self.context, 1)
        self.assertIn('admin', roles)

    @attr(kind='small')
    def test_user_add_role_db_duplicate(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        self.db.project_add_member(self.context, 1, 1)
        self.db.user_add_role(self.context, 1, 'admin')

        # test and assert
        self.assertRaises(exception.Duplicate,
                          self.db.user_add_role,
                          self.context, 1, 'admin')

    @attr(kind='small')
    def test_user_add_role_duplicate_other_user(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        user = {}
        user['id'] = 2
        user['name'] = 'fake2'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        self.db.project_add_member(self.context, 1, 1)
        # test and assert
        self.db.user_add_role(self.context, 1, 'admin')
        self.db.user_add_role(self.context, 2, 'admin')
        roles = self.db.api.user_get_roles(self.context, 1)
        self.assertIn('admin', roles)
        roles = self.db.api.user_get_roles(self.context, 2)
        self.assertIn('admin', roles)

    @attr(kind='small')
    def test_user_remove_role(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        self.db.project_add_member(self.context, 1, 1)
        self.db.user_add_role(self.context, 1, 'admin')

        # test and assert
        self.db.api.user_remove_role(self.context, 1, 'admin')
        roles = self.db.api.user_get_roles(self.context, 1)
        self.assertNotIn('admin', roles)

    @attr(kind='small')
    def test_user_remove_role_db_not_found(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        self.db.project_add_member(self.context, 1, 1)
        self.db.user_add_role(self.context, 1, 'admin')

        # test and assert
        self.db.api.user_remove_role(self.context, 1, 'not_found')
        roles = self.db.api.user_get_roles(self.context, 1)
        self.assertIn('admin', roles)

    @attr(kind='small')
    def test_user_add_project_role(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        self.db.project_add_member(self.context, 1, 1)
        self.db.user_add_project_role(self.context, 1, 1, 'admin')
        self.db.user_add_project_role(self.context, 1, 1, 'user')
        self.db.user_add_role(self.context, 1, 'admin')

        # test and assert
        roles = self.db.api.user_get_roles_for_project(self.context, 1, 1)
        self.assertIn('admin', roles)
        self.assertIn('user', roles)

    @attr(kind='small')
    def test_user_add_project_role_db_duplicate(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        self.db.project_add_member(self.context, 1, 1)
        self.db.user_add_project_role(self.context, 1, 1, 'admin')
        self.db.user_add_project_role(self.context, 1, 1, 'user')
        self.db.user_add_role(self.context, 1, 'admin')

        # test and assert
        self.assertRaises(exception.Duplicate,
                          self.db.user_add_project_role,
                          self.context, 1, 1, 'admin')

    @attr(kind='small')
    def test_user_update(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        # test and assert
        self.db.api.user_create(self.context, user)
        self.db.api.user_update(self.context, 1, {'name': 'new_name'})
        result = self.db.api.user_get(self.context, 1)
        self.assertEqual('new_name', result.name)
        self.assertEqual('access', result.access_key)
        self.assertEqual('secret', result.secret_key)
        self.assertEqual(True, result.is_admin)

    @attr(kind='small')
    def test_user_update_db_not_found(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        # test and assert
        self.db.api.user_create(self.context, user)
        self.assertRaises(exception.UserNotFound,
                          self.db.api.user_update,
                          self.context, 2, {'name': 'new_name'})

    @attr(kind='small')
    def test_project_create(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        # test and assert
        result = self.db.api.project_get(self.context, 1)
        self.assertEqual('project', result.name)
        self.assertEqual('test', result.description)

    @attr(kind='small')
    def test_project_create_db_duplicate(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        # test and assert
        self.assertRaises(exception.Duplicate,
                          self.db.api.project_create,
                          self.context, project)

    @attr(kind='small')
    def test_project_add_member(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        # test and assert
        self.db.api.project_add_member(self.context, 1, 1)
        result = self.db.api.project_get(self.context, 1)
        self.assertEqual('fake', result.members[0].name)

    @attr(kind='small')
    def test_project_add_member_user_db_not_found(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        # test and assert
        self.assertRaises(exception.UserNotFound,
                          self.db.api.project_add_member,
                          self.context, 1, 2)

    @attr(kind='small')
    def test_project_add_member_project_db_not_found(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        # test and assert
        self.assertRaises(exception.ProjectNotFound,
                          self.db.api.project_add_member,
                          self.context, 2, 1)

    @attr(kind='small')
    def test_project_get(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        # test and assert
        result = self.db.api.project_get(self.context, 1)
        self.assertEqual('project', result.name)
        self.assertEqual('test', result.description)

    @attr(kind='small')
    def test_project_get_db_not_found(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        # test and assert
        self.assertRaises(exception.ProjectNotFound,
                          self.db.api.project_get,
                          self.context, 2)

    @attr(kind='small')
    def test_project_get_all(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        # test and assert
        result = self.db.api.project_get_all(self.context)
        self.assertEqual('project', result[0].name)
        self.assertEqual('test', result[0].description)

    @attr(kind='small')
    def test_project_get_all_db_not_found(self):
        # test and assert
        result = self.db.api.project_get_all(self.context)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_project_get_by_user(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        self.db.api.project_add_member(self.context, 1, 1)
        # test and assert
        result = self.db.api.project_get_by_user(self.context, 1)
        self.assertEqual('project', result[0].name)
        self.assertEqual('test', result[0].description)

    @attr(kind='small')
    def test_project_get_by_user_db_not_found(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        # test and assert
        result = self.db.api.project_get_by_user(self.context, 1)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_project_get_by_user_user_db_not_found(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        # test and assert
        self.assertRaises(exception.UserNotFound,
                          self.db.api.project_get_by_user,
                          self.context, 2)

    @attr(kind='small')
    def test_project_remove_member(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)
        self.db.api.project_add_member(self.context, 1, 1)

        # test and assert
        self.db.project_remove_member(self.context, 1, 1)
        result = self.db.api.project_get(self.context, 1)
        self.assertEqual([], result.members)

    @attr(kind='small')
    def test_project_remove_member_user_db_not_found(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        # test and assert
        self.assertRaises(exception.UserNotFound,
                          self.db.api.project_remove_member,
                          self.context, 1, 2)

    @attr(kind='small')
    def test_project_remove_member_project_db_not_found(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        # test and assert
        self.assertRaises(exception.ProjectNotFound,
                          self.db.api.project_remove_member,
                          self.context, 2, 1)

    @attr(kind='small')
    def test_project_update(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        # test and assert
        self.db.project_update(self.context, 1, {'name': 'new_name'})
        result = self.db.api.project_get(self.context, 1)
        self.assertEqual('new_name', result.name)
        self.assertEqual('test', result.description)

    @attr(kind='small')
    def test_project_update_db_not_found(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        # test and assert
        self.assertRaises(exception.ProjectNotFound,
                          self.db.api.project_update,
                          self.context, 2, {'name': 'new_project'})

    @attr(kind='small')
    def test_project_delete(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)
        self.db.api.project_add_member(self.context, 1, 1)
        self.db.api.user_add_project_role(self.context, 1, 1, 'admin')
        # test and assert
        self.db.project_delete(self.context, 1)
        self.assertRaises(exception.ProjectNotFound,
                          self.db.api.project_get,
                          self.context, 1)

    @attr(kind='small')
    def test_project_delete_db_not_found(self):
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)
        self.db.api.project_add_member(self.context, 1, 1)
        self.db.api.user_add_project_role(self.context, 1, 1, 'admin')
        # test and assert
        self.assertRaises(exception.ProjectNotFound,
                          self.db.api.project_delete,
                          self.context, 2)

    @attr(kind='small')
    def test_project_get_networks(self):
        """
        network associate not work fine, if sqlite used.
        can't update network association table.
        """
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        nw = {}
        nw['id'] = 100
        nw['label'] = "network1"
        nw['cidr'] = "10.1.1.0"
        nw['netmask'] = "255.255.255.0"
        nw['bridge'] = "br100"
        nw['bridge_interface'] = "eth1"
        nw['gateway'] = "10.1.1.254"
        nw['broadcast'] = "10.1.1.255"
        nw['dns1'] = "10.1.1.1"
        nw['dns2'] = "10.1.1.2"
        nw['vlan'] = 100
        nw['vpn_public_address'] = "68.52.102.104"
        nw['vpn_public_port'] = 8080
        nw['vpn_private_address'] = "10.1.1.3"
        nw['dhcp_start'] = "10.1.1.4"
        nw['priority'] = 1
        nw['project_id'] = '1'
        nw['host'] = "host1"
        nw['uuid'] = "11:22:33:44"

        self.db.api.network_create_safe(self.context, nw)

        # test and assert
        result = self.db.project_get_networks(self.context, 1, False)
        self.assertEqual(100, result[0].id)
        self.assertEqual('1', result[0].project_id)

    @attr(kind='small')
    def test_project_get_networks_with_associate(self):
        """
        network recored is already stored in test db.
        """
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        nw = {}
        nw['id'] = 100
        nw['label'] = "network1"
        nw['cidr'] = "10.1.1.0"
        nw['netmask'] = "255.255.255.0"
        nw['bridge'] = "br100"
        nw['bridge_interface'] = "eth1"
        nw['gateway'] = "10.1.1.254"
        nw['broadcast'] = "10.1.1.255"
        nw['dns1'] = "10.1.1.1"
        nw['dns2'] = "10.1.1.2"
        nw['vlan'] = 100
        nw['vpn_public_address'] = "68.52.102.104"
        nw['vpn_public_port'] = 8080
        nw['vpn_private_address'] = "10.1.1.3"
        nw['dhcp_start'] = "10.1.1.4"
        nw['priority'] = 1
        nw['host'] = "host1"
        nw['uuid'] = "11:22:33:44"

        self.db.api.network_create_safe(self.context, nw)

        # test and assert
        result = self.db.project_get_networks(self.context, 1, True)
        self.assertNotEqual([], result)

    @attr(kind='small')
    def test_project_get_networks_db_not_found(self):
        """
        network recored is already stored in test db.
        """
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        nw = {}
        nw['id'] = 100
        nw['label'] = "network1"
        nw['cidr'] = "10.1.1.0"
        nw['netmask'] = "255.255.255.0"
        nw['bridge'] = "br100"
        nw['bridge_interface'] = "eth1"
        nw['gateway'] = "10.1.1.254"
        nw['broadcast'] = "10.1.1.255"
        nw['dns1'] = "10.1.1.1"
        nw['dns2'] = "10.1.1.2"
        nw['vlan'] = 100
        nw['vpn_public_address'] = "68.52.102.104"
        nw['vpn_public_port'] = 8080
        nw['vpn_private_address'] = "10.1.1.3"
        nw['dhcp_start'] = "10.1.1.4"
        nw['priority'] = 1
        nw['host'] = "host1"
        nw['uuid'] = "11:22:33:44"

        self.db.api.network_create_safe(self.context, nw)

        # test and assert
        result = self.db.project_get_networks(self.context, 1, False)
        self.assertEqual([], result)

    @attr(kind='small')
    def test_project_get_networks_v6(self):
        """
        network associate not work fine, if sqlite used.
        can't update network association table.
        """
        # setup
        user = {}
        user['id'] = 1
        user['name'] = 'fake'
        user['access_key'] = 'access'
        user['secret_key'] = 'secret'
        user['is_admin'] = True
        self.db.api.user_create(self.context, user)

        project = {}
        project['id'] = 1
        project['name'] = 'project'
        project['description'] = 'test'
        project['project_manager'] = 1
        self.db.api.project_create(self.context, project)

        nw = {}
        nw['id'] = 100
        nw['label'] = "network1"
        nw['cidr'] = "10.1.1.0"
        nw['netmask'] = "255.255.255.0"
        nw['bridge'] = "br100"
        nw['bridge_interface'] = "eth1"
        nw['gateway'] = "10.1.1.254"
        nw['broadcast'] = "10.1.1.255"
        nw['dns1'] = "10.1.1.1"
        nw['dns2'] = "10.1.1.2"
        nw['vlan'] = 100
        nw['vpn_public_address'] = "68.52.102.104"
        nw['vpn_public_port'] = 8080
        nw['vpn_private_address'] = "10.1.1.3"
        nw['dhcp_start'] = "10.1.1.4"
        nw['priority'] = 1
        nw['project_id'] = '1'
        nw['host'] = "host1"
        nw['uuid'] = "11:22:33:44"

        self.db.api.network_create_safe(self.context, nw)

        # test and assert
        result = self.db.project_get_networks_v6(self.context, 1)
        self.assertEqual(100, result[0].id)
        self.assertEqual('1', result[0].project_id)

    @attr(kind='small')
    def test_console_pool_create(self):
        con = {}
        con['id'] = 1
        con['address'] = 'localhost'
        con['username'] = 'fake'
        con['password'] = 'fake'
        con['console_type'] = 'vnc'
        con['public_hostname'] = 'console'
        con['host'] = 'localhost'
        con['compute_host'] = 'compute'

        self.db.api.console_pool_create(self.context, con)
        pool = self.db.api.console_pool_get(self.context, 1)
        self.assertEqual('localhost', pool.address)
        self.assertEqual('fake', pool.username)
        self.assertEqual('fake', pool.password)
        self.assertEqual('vnc', pool.console_type)
        self.assertEqual('console', pool.public_hostname)
        self.assertEqual('localhost', pool.host)
        self.assertEqual('compute', pool.compute_host)

    @attr(kind='small')
    def test_console_pool_create_db_duplicate(self):
        con = {}
        con['id'] = 1
        con['address'] = 'localhost'
        con['username'] = 'fake'
        con['password'] = 'fake'
        con['console_type'] = 'vnc'
        con['public_hostname'] = 'console'
        con['host'] = 'localhost'
        con['compute_host'] = 'compute'

        self.db.api.console_pool_create(self.context, con)
        self.assertRaises(exception.Duplicate,
                          self.db.api.console_pool_create,
                          self.context, con)

    @attr(kind='small')
    def test_console_pool_get(self):
        con = {}
        con['id'] = 1
        con['address'] = 'localhost'
        con['username'] = 'fake'
        con['password'] = 'fake'
        con['console_type'] = 'vnc'
        con['public_hostname'] = 'console'
        con['host'] = 'localhost'
        con['compute_host'] = 'compute'

        self.db.api.console_pool_create(self.context, con)
        pool = self.db.api.console_pool_get(self.context, 1)
        self.assertEqual('localhost', pool.address)
        self.assertEqual('fake', pool.username)
        self.assertEqual('fake', pool.password)
        self.assertEqual('vnc', pool.console_type)
        self.assertEqual('console', pool.public_hostname)
        self.assertEqual('localhost', pool.host)
        self.assertEqual('compute', pool.compute_host)

    @attr(kind='small')
    def test_console_pool_get_db_not_found(self):
#        raise SkipTest("DBError occured")
        con = {}
        con['id'] = 1
        con['address'] = 'localhost'
        con['username'] = 'fake'
        con['password'] = 'fake'
        con['console_type'] = 'vnc'
        con['public_hostname'] = 'console'
        con['host'] = 'localhost'
        con['compute_host'] = 'compute'

        self.db.api.console_pool_create(self.context, con)
        self.assertRaises(exception.ConsolePoolNotFound,
                          self.db.api.console_pool_get,
                          self.context, 2)

    @attr(kind='small')
    def test_console_pool_get_by_host_type(self):
        con = {}
        con['id'] = 1
        con['address'] = 'localhost'
        con['username'] = 'fake'
        con['password'] = 'fake'
        con['console_type'] = 'vnc'
        con['public_hostname'] = 'console'
        con['host'] = 'localhost'
        con['compute_host'] = 'compute'

        self.db.api.console_pool_create(self.context, con)
        pool = self.db.api.console_pool_get_by_host_type(
                                    self.context, 'compute',
                                    'localhost', 'vnc')
        self.assertEqual('localhost', pool.address)
        self.assertEqual('fake', pool.username)
        self.assertEqual('fake', pool.password)
        self.assertEqual('vnc', pool.console_type)
        self.assertEqual('console', pool.public_hostname)
        self.assertEqual('localhost', pool.host)
        self.assertEqual('compute', pool.compute_host)

    @attr(kind='small')
    def test_console_pool_get_by_host_type_db_not_found(self):
        con = {}
        con['id'] = 1
        con['address'] = 'localhost'
        con['username'] = 'fake'
        con['password'] = 'fake'
        con['console_type'] = 'vnc'
        con['public_hostname'] = 'console'
        con['host'] = 'localhost'
        con['compute_host'] = 'compute'

        self.db.api.console_pool_create(self.context, con)
        self.assertRaises(exception.ConsolePoolNotFoundForHostType,
                          self.db.api.console_pool_get_by_host_type,
                          self.context, 'compute', 'localhost', 'xcp')

    @attr(kind='small')
    def test_console_pool_get_all_by_host_type(self):
        con = {}
        con['id'] = 1
        con['address'] = 'localhost'
        con['username'] = 'fake'
        con['password'] = 'fake'
        con['console_type'] = 'vnc'
        con['public_hostname'] = 'console'
        con['host'] = 'localhost'
        con['compute_host'] = 'compute'

        self.db.api.console_pool_create(self.context, con)
        pools = self.db.api.console_pool_get_all_by_host_type(
                                    self.context, 'localhost', 'vnc')
        pool = pools[0]
        self.assertEqual('localhost', pool.address)
        self.assertEqual('fake', pool.username)
        self.assertEqual('fake', pool.password)
        self.assertEqual('vnc', pool.console_type)
        self.assertEqual('console', pool.public_hostname)
        self.assertEqual('localhost', pool.host)
        self.assertEqual('compute', pool.compute_host)

    @attr(kind='small')
    def test_console_pool_get_all_by_host_type_db_not_found(self):
        con = {}
        con['id'] = 1
        con['address'] = 'localhost'
        con['username'] = 'fake'
        con['password'] = 'fake'
        con['console_type'] = 'vnc'
        con['public_hostname'] = 'console'
        con['host'] = 'localhost'
        con['compute_host'] = 'compute'

        self.db.api.console_pool_create(self.context, con)
        pools = self.db.api.console_pool_get_all_by_host_type(
                                    self.context, 'localhost', 'xcp')
        self.assertEqual([], pools)

    @attr(kind='small')
    def test_console_create(self):
        con = {}
        con['id'] = 1
        con['instance_name'] = 'test'
        con['instance_id'] = 1
        con['password'] = 'fake'
        con['port'] = 8080
        con['pool_id'] = 1

        self.db.api.console_create(self.context, con)
        result = self.db.api.console_get(self.context, 1, 1)
        self.assertEqual('test', result.instance_name)
        self.assertEqual('fake', result.password)
        self.assertEqual(8080, result.port)
        self.assertEqual(1, result.pool_id)

    @attr(kind='small')
    def test_console_create_db_duplicate(self):
        con = {}
        con['id'] = 1
        con['instance_name'] = 'test'
        con['instance_id'] = 1
        con['password'] = 'fake'
        con['port'] = 8080
        con['pool_id'] = 1

        self.db.api.console_create(self.context, con)
        self.assertRaises(exception.Duplicate,
                          self.db.api.console_create,
                          self.context, con)

    @attr(kind='small')
    def test_console_delete(self):
        con = {}
        con['id'] = 1
        con['instance_name'] = 'test'
        con['instance_id'] = 1
        con['password'] = 'fake'
        con['port'] = 8080
        con['pool_id'] = 1

        self.db.api.console_create(self.context, con)
        self.db.api.console_delete(self.context, 1)
        self.assertRaises(exception.ConsoleNotFound,
                          self.db.api.console_get,
                          self.context, 1)

    @attr(kind='small')
    def test_console_delete_db_not_found(self):
        """
        should be raise error.
        """
        con = {}
        con['id'] = 1
        con['instance_name'] = 'test'
        con['instance_id'] = 1
        con['password'] = 'fake'
        con['port'] = 8080
        con['pool_id'] = 1

        self.db.api.console_create(self.context, con)
        self.db.api.console_delete(self.context, 2)
        result = self.db.api.console_get(self.context, 1, 1)
        self.assertEqual('test', result.instance_name)
        self.assertEqual('fake', result.password)
        self.assertEqual(8080, result.port)
        self.assertEqual(1, result.pool_id)

    @attr(kind='small')
    def test_console_get_by_pool_instance(self):
        con = {}
        con['id'] = 1
        con['instance_name'] = 'test'
        con['instance_id'] = 1
        con['password'] = 'fake'
        con['port'] = 8080
        con['pool_id'] = 1

        self.db.api.console_create(self.context, con)
        result = self.db.api.console_get_by_pool_instance(self.context, 1, 1)
        self.assertEqual('test', result.instance_name)
        self.assertEqual('fake', result.password)
        self.assertEqual(8080, result.port)
        self.assertEqual(1, result.pool_id)

    @attr(kind='small')
    def test_console_get_by_pool_instance_db_not_found(self):
        con = {}
        con['id'] = 1
        con['instance_name'] = 'test'
        con['instance_id'] = 1
        con['password'] = 'fake'
        con['port'] = 8080
        con['pool_id'] = 1

        self.db.api.console_create(self.context, con)
        self.assertRaises(exception.ConsoleNotFoundInPoolForInstance,
                          self.db.api.console_get_by_pool_instance,
                          self.context, 2, 1)

    @attr(kind='small')
    def test_console_get_all_by_pool_instance(self):
        con = {}
        con['id'] = 1
        con['instance_name'] = 'test'
        con['instance_id'] = 1
        con['password'] = 'fake'
        con['port'] = 8080
        con['pool_id'] = 1

        self.db.api.console_create(self.context, con)
        results = self.db.api.console_get_all_by_instance(self.context, 1)
        result = results[0]
        self.assertEqual('test', result.instance_name)
        self.assertEqual('fake', result.password)
        self.assertEqual(8080, result.port)
        self.assertEqual(1, result.pool_id)

    @attr(kind='small')
    def test_console_get_all_by_pool_instance_db_not_found(self):
        con = {}
        con['id'] = 1
        con['instance_name'] = 'test'
        con['instance_id'] = 1
        con['password'] = 'fake'
        con['port'] = 8080
        con['pool_id'] = 1

        self.db.api.console_create(self.context, con)
        results = self.db.api.console_get_all_by_instance(self.context, 2)
        self.assertEqual([], results)

    @attr(kind='small')
    def test_console_get(self):
        pool = {}
        pool['id'] = 1
        pool['address'] = 'localhost'
        pool['username'] = 'fake'
        pool['password'] = 'fake'
        pool['console_type'] = 'vnc'
        pool['public_hostname'] = 'console'
        pool['host'] = 'localhost'
        pool['compute_host'] = 'compute'
        self.db.api.console_pool_create(self.context, pool)

        con = {}
        con['id'] = 1
        con['instance_name'] = 'test'
        con['instance_id'] = 1
        con['password'] = 'fake'
        con['port'] = 8080
        con['pool_id'] = 1

        self.db.api.console_create(self.context, con)
        result = self.db.api.console_get(self.context, 1, 1)
        self.assertEqual('test', result.instance_name)
        self.assertEqual('fake', result.password)
        self.assertEqual(8080, result.port)
        self.assertEqual(1, result.pool_id)
        self.assertEqual('localhost', result.pool.address)

    @attr(kind='small')
    def test_console_get_instance_db_not_found(self):
        pool = {}
        pool['id'] = 1
        pool['address'] = 'localhost'
        pool['username'] = 'fake'
        pool['password'] = 'fake'
        pool['console_type'] = 'vnc'
        pool['public_hostname'] = 'console'
        pool['host'] = 'localhost'
        pool['compute_host'] = 'compute'
        self.db.api.console_pool_create(self.context, pool)

        con = {}
        con['id'] = 1
        con['instance_name'] = 'test'
        con['instance_id'] = 1
        con['password'] = 'fake'
        con['port'] = 8080
        con['pool_id'] = 1

        self.db.api.console_create(self.context, con)
        self.assertRaises(exception.ConsoleNotFoundForInstance,
                          self.db.api.console_get,
                          self.context, 1, 2)

    @attr(kind='small')
    def test_console_get_db_not_found(self):
        pool = {}
        pool['id'] = 1
        pool['address'] = 'localhost'
        pool['username'] = 'fake'
        pool['password'] = 'fake'
        pool['console_type'] = 'vnc'
        pool['public_hostname'] = 'console'
        pool['host'] = 'localhost'
        pool['compute_host'] = 'compute'
        self.db.api.console_pool_create(self.context, pool)

        con = {}
        con['id'] = 1
        con['instance_name'] = 'test'
        con['instance_id'] = 1
        con['password'] = 'fake'
        con['port'] = 8080
        con['pool_id'] = 1

        self.db.api.console_create(self.context, con)
        self.assertRaises(exception.ConsoleNotFound,
                          self.db.api.console_get,
                          self.context, 2, 1)

    @attr(kind='small')
    def test_instance_type_create(self):
        """
        Why returned dict??
        """
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100

        # test and assert
        self.db.api.instance_type_create(self.context, values)
        result = self.db.api.instance_type_get(self.context, 100)
        self.assertEqual('test', result['name'])
        self.assertEqual(100, result['memory_mb'])
        self.assertEqual(2, result['vcpus'])
        self.assertEqual(10, result['local_gb'])
        self.assertEqual(100, result['flavorid'])

    @attr(kind='small')
    def test_instance_type_create_db_duplicate(self):
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100

        # test and assert
        self.db.api.instance_type_create(self.context, values)
        self.assertRaises(exception.Duplicate,
                          self.db.api.instance_type_create,
                          self.context, values)

    @attr(kind='small')
    def test_instance_type_get_all(self):
        """
        default instance type already stored in database.
        """
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100

        # test and assert
        self.db.api.instance_type_create(self.context, values)
        results = self.db.api.instance_type_get_all(self.context)
        self.assertNotEqual([], results)

    @attr(kind='small')
    def test_instance_type_get_all_parameter_notfound(self):
        """
        return {} if instance type not exist
        """
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100

        # test and assert
        self.db.api.instance_type_destroy(self.context, 'm1.medium')
        self.db.api.instance_type_destroy(self.context, 'm1.xlarge')
        self.db.api.instance_type_destroy(self.context, 'm1.tiny')
        self.db.api.instance_type_destroy(self.context, 'm1.large')
        self.db.api.instance_type_destroy(self.context, 'm1.small')

        results = self.db.api.instance_type_get_all(self.context)

        self.assertEqual({}, results)

    @attr(kind='small')
    def test_instance_type_get_all_with_inactive(self):
        """
        default instance type avaluesdy stored in database.
        """
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 10000
        values['vcpus'] = 2
        values['local_gb'] = 10000
        values['flavorid'] = 100
        self.db.api.instance_type_create(self.context, values)
        self.db.api.instance_type_destroy(self.context, 'test')

        extra_specs = {}
        extra_specs['key'] = 'kkk'
        extra_specs['value'] = 'vvv'
        self.db.api.instance_type_extra_specs_update_or_create(
                                    self.context, 100, extra_specs)

        # test and assert
        result = self.db.api.instance_type_get_all(self.context, True)
        self.assertTrue(isinstance(result, dict))
        self.assertEqual(100, result['test']['id'])
        self.assertEqual(extra_specs, result['test']['extra_specs'])

    @attr(kind='small')
    def test_instance_type_get(self):
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100

        # test and assert
        self.db.api.instance_type_create(self.context, values)
        result = self.db.api.instance_type_get(self.context, 100)
        self.assertEqual('test', result['name'])
        self.assertEqual(100, result['memory_mb'])
        self.assertEqual(2, result['vcpus'])
        self.assertEqual(10, result['local_gb'])
        self.assertEqual(100, result['flavorid'])

    @attr(kind='small')
    def test_instance_type_get_db_not_found(self):
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100

        # test and assert
        self.db.api.instance_type_create(self.context, values)
        self.assertRaises(exception.InstanceTypeNotFound,
                          self.db.api.instance_type_get,
                          self.context, 101)

    @attr(kind='small')
    def test_instance_type_get_by_name(self):
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100

        # test and assert
        self.db.api.instance_type_create(self.context, values)
        result = self.db.api.instance_type_get_by_name(self.context, 'test')
        self.assertEqual('test', result['name'])
        self.assertEqual(100, result['memory_mb'])
        self.assertEqual(2, result['vcpus'])
        self.assertEqual(10, result['local_gb'])
        self.assertEqual(100, result['flavorid'])

    @attr(kind='small')
    def test_instance_type_get_by_name_db_not_found(self):
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100

        # test and assert
        self.db.api.instance_type_create(self.context, values)
        self.assertRaises(exception.InstanceTypeNotFound,
                          self.db.api.instance_type_get_by_name,
                          self.context, 'not_found')

    @attr(kind='small')
    def test_instance_type_get_by_flavor_id(self):
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100

        # test and assert
        self.db.api.instance_type_create(self.context, values)
        result = self.db.api.instance_type_get_by_flavor_id(self.context, 100)
        self.assertEqual('test', result['name'])
        self.assertEqual(100, result['memory_mb'])
        self.assertEqual(2, result['vcpus'])
        self.assertEqual(10, result['local_gb'])
        self.assertEqual(100, result['flavorid'])

    @attr(kind='small')
    def test_instance_type_get_by_flavor_id_db_not_found(self):
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100

        # test and assert
        self.db.api.instance_type_create(self.context, values)
        self.assertRaises(exception.FlavorNotFound,
                          self.db.api.instance_type_get_by_flavor_id,
                          self.context, 101)

    @attr(kind='small')
    def test_instance_type_get_by_flavor_id_illigal_args(self):
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100

        # test and assert
        self.db.api.instance_type_create(self.context, values)
        self.assertRaises(exception.FlavorNotFound,
                          self.db.api.instance_type_get_by_flavor_id,
                          self.context, 'test')

    @attr(kind='small')
    def test_instance_type_destroy(self):
        """
        Returned deleted instance_type.
        """
#        raise SkipTest("Returned deleted instance_type")
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100

        # test and assert
        self.db.api.instance_type_create(self.context, values)
        self.db.api.instance_type_destroy(self.context, 'test')
        self.assertRaises(exception.InstanceTypeNotFound,
                          self.db.api.instance_type_get,
                          self.context, 100)

    @attr(kind='small')
    def test_instance_type_destroy_db_not_found(self):
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100

        # test and assert
        self.db.api.instance_type_create(self.context, values)
        self.assertRaises(exception.InstanceTypeNotFoundByName,
                          self.db.api.instance_type_destroy,
                          self.context, 'not_found')

    @attr(kind='small')
    def test_instance_type_purge(self):
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100

        # test and assert
        self.db.api.instance_type_create(self.context, values)
        self.db.api.instance_type_purge(self.context, 'test')
        self.assertRaises(exception.InstanceTypeNotFound,
                          self.db.api.instance_type_get,
                          self.context, 100)

    @attr(kind='small')
    def test_instance_type_purge_db_not_found(self):
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100

        # test and assert
        self.db.api.instance_type_create(self.context, values)
        self.assertRaises(exception.InstanceTypeNotFoundByName,
                          self.db.api.instance_type_purge,
                          self.context, 'not_found')

    @attr(kind='small')
    def test_zone_create(self):
        # setup
        zone = {}
        zone['id'] = 1
        zone['api_url'] = 'http://localhost'
        zone['username'] = 'fake'
        zone['password'] = 'fake'
        # test and assert
        self.db.api.zone_create(self.context, zone)
        result = self.db.api.zone_get(self.context, 1)
        self.assertEqual('http://localhost', result.api_url)
        self.assertEqual('fake', result.username)
        self.assertEqual('fake', result.password)

    @attr(kind='small')
    def test_zone_create_db_duplicate(self):
        # setup
        zone = {}
        zone['id'] = 1
        zone['name'] = 'test'
        zone['api_url'] = 'http://localhost'
        zone['username'] = 'fake'
        zone['password'] = 'fake'
        # test and assert
        self.db.api.zone_create(self.context, zone)
        self.assertRaises(exception.Duplicate,
                          self.db.api.zone_create,
                          self.context, zone)

    @attr(kind='small')
    def test_zone_update(self):
        # setup
        zone = {}
        zone['id'] = 1
        zone['api_url'] = 'http://localhost'
        zone['username'] = 'fake'
        zone['password'] = 'fake'
        # test and assert
        self.db.api.zone_create(self.context, zone)
        self.db.api.zone_update(self.context, 1, {'username': 'new_username'})
        result = self.db.api.zone_get(self.context, 1)
        self.assertEqual('new_username', result.username)

    @attr(kind='small')
    def test_zone_update_db_not_found(self):
        # setup
        zone = {}
        zone['id'] = 1
        zone['name'] = 'test'
        zone['api_url'] = 'http://localhost'
        zone['username'] = 'fake'
        zone['password'] = 'fake'
        # test and assert
        self.db.api.zone_create(self.context, zone)
        self.assertRaises(exception.ZoneNotFound,
                          self.db.api.zone_update,
                          self.context, 2, {'name': 'new_name'})

    @attr(kind='small')
    def test_zone_delete(self):
        # setup
        zone = {}
        zone['id'] = 1
        zone['name'] = 'test'
        zone['api_url'] = 'http://localhost'
        zone['username'] = 'fake'
        zone['password'] = 'fake'
        # test and assert
        self.db.api.zone_create(self.context, zone)
        self.db.api.zone_delete(self.context, 1)
        self.assertRaises(exception.ZoneNotFound,
                          self.db.api.zone_get,
                          self.context, 1)

    @attr(kind='small')
    def test_zone_delete_db_not_found(self):
        """
        should be raise error.
        """
        # setup
        zone = {}
        zone['id'] = 1
        zone['api_url'] = 'http://localhost'
        zone['username'] = 'fake'
        zone['password'] = 'fake'
        # test and assert
        self.db.api.zone_create(self.context, zone)
        self.db.api.zone_delete(self.context, 2)
        result = self.db.api.zone_get(self.context, 1)
        self.assertEqual('http://localhost', result.api_url)
        self.assertEqual('fake', result.username)
        self.assertEqual('fake', result.password)

    @attr(kind='small')
    def test_zone_get(self):
        # setup
        zone = {}
        zone['id'] = 1
        zone['api_url'] = 'http://localhost'
        zone['username'] = 'fake'
        zone['password'] = 'fake'
        # test and assert
        self.db.api.zone_create(self.context, zone)
        result = self.db.api.zone_get(self.context, 1)
        self.assertEqual('http://localhost', result.api_url)
        self.assertEqual('fake', result.username)
        self.assertEqual('fake', result.password)

    @attr(kind='small')
    def test_zone_get_db_not_found(self):
        # setup
        zone = {}
        zone['id'] = 1
        zone['name'] = 'test'
        zone['api_url'] = 'http://localhost'
        zone['username'] = 'fake'
        zone['password'] = 'fake'
        # test and assert
        self.db.api.zone_create(self.context, zone)
        self.assertRaises(exception.ZoneNotFound,
                          self.db.api.zone_get,
                          self.context, 2)

    @attr(kind='small')
    def test_zone_get_all(self):
        # setup
        zone = {}
        zone['id'] = 1
        zone['api_url'] = 'http://localhost'
        zone['username'] = 'fake'
        zone['password'] = 'fake'
        # test and assert
        self.db.api.zone_create(self.context, zone)
        results = self.db.api.zone_get_all(self.context)
        result = results[0]
        self.assertEqual('http://localhost', result.api_url)
        self.assertEqual('fake', result.username)
        self.assertEqual('fake', result.password)

    @attr(kind='small')
    def test_zone_get_all_db_not_found(self):
        # test and assert
        results = self.db.api.zone_get_all(self.context)
        self.assertEqual([], results)

    @attr(kind='small')
    def test_instance_metadata_get(self):
        # setup
        i = {}
        i['id'] = 1
        i['metadata'] = {'type': 'test'}

        self.db.api.instance_create(self.context, i)
        # test and assert
        metadata = self.db.api.instance_metadata_get(self.context, 1)
        self.assertEqual('test', metadata['type'])

    @attr(kind='small')
    def test_instance_metadata_get_db_not_found(self):
        # setup
        i = {}
        i['id'] = 1
        i['metadata'] = {'type': 'test'}

        self.db.api.instance_create(self.context, i)
        # test and assert
        self.assertRaises(exception.InstanceNotFound,
                          self.db.api.instance_metadata_get,
                          self.context, 2)

    @attr(kind='small')
    def test_instance_metadata_delete(self):
        # setup
        i = {}
        i['id'] = 1
        i['metadata'] = {'type': 'test'}

        self.db.api.instance_create(self.context, i)
        # test and assert
        self.db.api.instance_metadata_delete(self.context, 1, 'type')
        metadata = self.db.api.instance_metadata_get(self.context, 1)
        self.assertEqual({}, metadata)

    @attr(kind='small')
    def test_instance_metadata_delete_db_not_found(self):
        # setup
        i = {}
        i['id'] = 1
        i['metadata'] = {'type': 'test'}

        self.db.api.instance_create(self.context, i)
        # test and assert
        self.assertRaises(exception.InstanceNotFound,
                          self.db.api.instance_metadata_delete,
                          self.context, 2, 'type')

    @attr(kind='small')
    def test_instance_metadata_get_item(self):
        """
        Not found in db.api.
        """
#        raise SkipTest("Not found in API")
        # setup
        i = {}
        i['id'] = 1
        i['metadata'] = {'type': 'test'}

        self.db.api.instance_create(self.context, i)
        # test and assert
        metadata = self.db.api.instance_metadata_get_item(
                                    self.context, 1, 'type')
        self.assertEqual('test', metadata.value)

    @attr(kind='small')
    def test_instance_metadata_get_item_exception_notfound(self):
        """
        Not found in db.api.
        """
#        raise SkipTest("Not found in API")
        # setup
        i = {}
        i['id'] = 1
        i['metadata'] = {'type': 'test'}

        self.db.api.instance_create(self.context, i)
        # test and assert
        self.assertRaises(exception.InstanceMetadataNotFound,
                    self.db.api.instance_metadata_get_item,
                                    self.context, 1, 'type1')

    @attr(kind='small')
    def test_instance_metadata_update(self):
        # setup
        i = {}
        i['id'] = 1
        i['metadata'] = {'type': 'test'}

        self.db.api.instance_create(self.context, i)
        # test and assert
        self.db.api.instance_metadata_update(
                                    self.context, 1,
                                    {'type': 'new_type'}, False)
        metadata = self.db.api.instance_metadata_get(self.context, 1)
        self.assertEqual('new_type', metadata['type'])

    @attr(kind='small')
    def test_instance_metadata_update_with_delete(self):
        # setup
        i = {}
        i['id'] = 1
        i['metadata'] = {'type': 'test'}

        self.db.api.instance_create(self.context, i)
        # test and assert
        self.db.api.instance_metadata_update(
                                    self.context, 1,
                                    {'type': 'new_type'}, True)
        metadata = self.db.api.instance_metadata_get(self.context, 1)
        self.assertEqual('new_type', metadata['type'])

    @attr(kind='small')
    def test_instance_metadata_update_with_delete_otherkey(self):
        # setup
        i = {}
        i['id'] = 1
        i['metadata'] = {'type': 'test', 'key1': 'value1'}

        self.db.api.instance_create(self.context, i)
        # test and assert
        self.db.api.instance_metadata_update(
                                    self.context, 1,
                                    {'type': 'new_type'}, True)
        metadata = self.db.api.instance_metadata_get(self.context, 1)
        self.assertEqual('new_type', metadata['type'])
        self.assertTrue('key1' not in metadata)

    @attr(kind='small')
    def test_instance_metadata_update_with_new_value(self):
        # setup
        i = {}
        i['id'] = 1
        i['metadata'] = {'type': 'test'}

        self.db.api.instance_create(self.context, i)
        # test and assert
        self.db.api.instance_metadata_update(
                                    self.context, 1,
                                    {'spec': 'new_spec'}, False)
        metadata = self.db.api.instance_metadata_get(self.context, 1)
        self.assertEqual('test', metadata['type'])
        self.assertEqual('new_spec', metadata['spec'])

    @attr(kind='small')
    def test_instance_metadata_update_db_not_found(self):
        # setup
        i = {}
        i['id'] = 1
        i['metadata'] = {'type': 'test'}

        self.db.api.instance_create(self.context, i)
        # test and assert
        self.assertRaises(exception.InstanceNotFound,
                          self.db.api.instance_metadata_update,
                          self.context, 2, {'test': 'test'}, False)

    @attr(kind='small')
    def test_agent_build_create(self):
        # setup
        ab = {}
        ab['id'] = 1
        ab['hypervisor'] = 'kvm'
        ab['os'] = 'linux'
        ab['architecture'] = 'x86_64'
        ab['version'] = '1.0'
        ab['url'] = 'http://localhost'
        ab['md5hash'] = 'hash'

        self.db.api.agent_build_create(self.context, ab)
        result = self.db.api.agent_build_get_by_triple(
                                    self.context, 'kvm', 'linux', 'x86_64')
        self.assertEqual('http://localhost', result.url)
        self.assertEqual('1.0', result.version)
        self.assertEqual('hash', result.md5hash)

    @attr(kind='small')
    def test_agent_build_create_db_duplicate(self):
        # setup
        ab = {}
        ab['id'] = 1
        ab['hypervisor'] = 'kvm'
        ab['os'] = 'linux'
        ab['architecture'] = 'x86_64'
        ab['version'] = '1.0'
        ab['url'] = 'http://localhost'
        ab['md5hash'] = 'hash'

        self.db.api.agent_build_create(self.context, ab)
        self.assertRaises(exception.Duplicate,
                          self.db.api.agent_build_create,
                          self.context, ab)

    @attr(kind='small')
    def test_agent_build_get_by_triple(self):
        # setup
        ab = {}
        ab['id'] = 1
        ab['hypervisor'] = 'kvm'
        ab['os'] = 'linux'
        ab['architecture'] = 'x86_64'
        ab['version'] = '1.0'
        ab['url'] = 'http://localhost'
        ab['md5hash'] = 'hash'

        self.db.api.agent_build_create(self.context, ab)
        result = self.db.api.agent_build_get_by_triple(
                                    self.context, 'kvm', 'linux', 'x86_64')
        self.assertEqual('http://localhost', result.url)
        self.assertEqual('1.0', result.version)
        self.assertEqual('hash', result.md5hash)

    @attr(kind='small')
    def test_agent_build_get_by_triple_db_not_found(self):
        # setup
        ab = {}
        ab['id'] = 1
        ab['hypervisor'] = 'kvm'
        ab['os'] = 'linux'
        ab['architecture'] = 'x86_64'
        ab['version'] = '1.0'
        ab['url'] = 'http://localhost'
        ab['md5hash'] = 'hash'

        self.db.api.agent_build_create(self.context, ab)
        result = self.db.api.agent_build_get_by_triple(
                                    self.context, 'kvm', 'windows', 'x86_64')
        self.assertEqual(None, result)

    @attr(kind='small')
    def test_agent_build_get_all(self):
        # setup
        ab = {}
        ab['id'] = 1
        ab['hypervisor'] = 'kvm'
        ab['os'] = 'linux'
        ab['architecture'] = 'x86_64'
        ab['version'] = '1.0'
        ab['url'] = 'http://localhost'
        ab['md5hash'] = 'hash'

        self.db.api.agent_build_create(self.context, ab)
        results = self.db.api.agent_build_get_all(self.context)
        result = results[0]
        self.assertEqual('http://localhost', result.url)
        self.assertEqual('1.0', result.version)
        self.assertEqual('hash', result.md5hash)

    @attr(kind='small')
    def test_agent_build_get_all_db_not_found(self):
        # setup
        results = self.db.api.agent_build_get_all(self.context)
        self.assertEqual([], results)

    @attr(kind='small')
    def test_agent_build_destroy(self):
        # setup
        ab = {}
        ab['id'] = 1
        ab['hypervisor'] = 'kvm'
        ab['os'] = 'linux'
        ab['architecture'] = 'x86_64'
        ab['version'] = '1.0'
        ab['url'] = 'http://localhost'
        ab['md5hash'] = 'hash'

        self.db.api.agent_build_create(self.context, ab)
        self.db.api.agent_build_destroy(self.context, 1)
        results = self.db.api.agent_build_get_all(self.context)
        self.assertEqual([], results)

    @attr(kind='small')
    def test_agent_build_destroy_db_not_found(self):
        """
        should be raise error
        """
        # setup
        ab = {}
        ab['id'] = 1
        ab['hypervisor'] = 'kvm'
        ab['os'] = 'linux'
        ab['architecture'] = 'x86_64'
        ab['version'] = '1.0'
        ab['url'] = 'http://localhost'
        ab['md5hash'] = 'hash'

        self.db.api.agent_build_create(self.context, ab)
        self.db.api.agent_build_destroy(self.context, 2)
        results = self.db.api.agent_build_get_all(self.context)
        self.assertNotEqual([], results)

    @attr(kind='small')
    def test_agent_build_update(self):
        # setup
        ab = {}
        ab['id'] = 1
        ab['hypervisor'] = 'kvm'
        ab['os'] = 'linux'
        ab['architecture'] = 'x86_64'
        ab['version'] = '1.0'
        ab['url'] = 'http://localhost'
        ab['md5hash'] = 'hash'

        self.db.api.agent_build_create(self.context, ab)
        self.db.agent_build_update(self.context, 1, {'os': 'windows'})
        results = self.db.api.agent_build_get_all(self.context)
        result = results[0]
        self.assertEqual('http://localhost', result.url)
        self.assertEqual('1.0', result.version)
        self.assertEqual('hash', result.md5hash)
        self.assertEqual('windows', result.os)

    @attr(kind='small')
    def test_agent_build_update_db_not_found(self):
        """
        should be raise error
        """
#        raise SkipTest("No exception occured in invalid id specified,\
#            so raise AttributeError.")
        # setup
        ab = {}
        ab['id'] = 1
        ab['hypervisor'] = 'kvm'
        ab['os'] = 'linux'
        ab['architecture'] = 'x86_64'
        ab['version'] = '1.0'
        ab['url'] = 'http://localhost'
        ab['md5hash'] = 'hash'

        self.db.api.agent_build_create(self.context, ab)
        self.db.agent_build_update(self.context, 2, {'os': 'windows'})
        results = self.db.api.agent_build_get_all(self.context)
        result = results[0]
        self.assertEqual('http://localhost', result.url)
        self.assertEqual('1.0', result.version)
        self.assertEqual('hash', result.md5hash)
        self.assertEqual('linux', result.os)

    @attr(kind='small')
    def test_instance_type_extra_specs_get(self):
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100
        values['extra_specs'] = {'key1': 'value1'}

        self.db.api.instance_type_create(self.context, values)
        result = self.db.api.instance_type_extra_specs_get(self.context, 100)
        self.assertEqual('value1', result['key1'])

    @attr(kind='small')
    def test_instance_type_extra_specs_get_no_spec(self):
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100

        self.db.api.instance_type_create(self.context, values)
        result = self.db.api.instance_type_extra_specs_get(self.context, 100)
        self.assertEqual({}, result)

    @attr(kind='small')
    def test_instance_type_extra_specs_get_no_instance_type(self):
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100

        self.db.api.instance_type_create(self.context, values)
        result = self.db.api.instance_type_extra_specs_get(self.context, 101)
        self.assertEqual({}, result)

    @attr(kind='small')
    def test_instance_type_extra_specs_delete(self):
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100
        values['extra_specs'] = {'key1': 'value1'}

        self.db.api.instance_type_create(self.context, values)
        self.db.api.instance_type_extra_specs_delete(self.context, 100, 'key1')
        result = self.db.api.instance_type_extra_specs_get(self.context, 100)
        self.assertEqual({}, result)

    @attr(kind='small')
    def test_instance_type_extra_specs_delete_db_not_found(self):
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100
        values['extra_specs'] = {'key1': 'value1'}

        self.db.api.instance_type_create(self.context, values)
        self.db.api.instance_type_extra_specs_delete(
                                    self.context, 100, 'unknow_key')
        result = self.db.api.instance_type_extra_specs_get(self.context, 100)
        self.assertEqual('value1', result['key1'])

    @attr(kind='small')
    def test_instance_type_extra_specs_get_item(self):
        """
        No method found in db.api
        """
#        raise SkipTest("No method found in db.api")
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100
        values['extra_specs'] = {'key1': 'value1'}

        self.db.api.instance_type_create(self.context, values)
        result = self.db.api.instance_type_extra_specs_get_item(
                                    self.context, 100, 'key1')
        self.assertEqual('key1', result.key)
        self.assertEqual('value1', result.value)

    @attr(kind='small')
    def test_instance_type_extra_specs_update_or_create(self):
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100
        values['extra_specs'] = {'key1': 'value1'}

        self.db.api.instance_type_create(self.context, values)
        self.db.api.instance_type_extra_specs_update_or_create(
                                    self.context, 100, {'key1': 'value2'})
        result = self.db.api.instance_type_extra_specs_get(self.context, 100)
        self.assertEqual('value2', result['key1'])

    @attr(kind='small')
    def test_instance_type_extra_specs_update_or_create_append(self):
        # setup
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100
        values['extra_specs'] = {'key1': 'value1'}

        self.db.api.instance_type_create(self.context, values)
        self.db.api.instance_type_extra_specs_update_or_create(
                                    self.context, 100, {'key2': 'value2'})
        result = self.db.api.instance_type_extra_specs_get(self.context, 100)
        self.assertEqual('value1', result['key1'])
        self.assertEqual('value2', result['key2'])

    @attr(kind='small')
    def test_volume_type_create(self):
        """
        Why returns dict?
        """
        values = {}
        values['id'] = 1
        values['name'] = 'test'

        self.db.api.volume_type_create(self.context, values)
        result = self.db.api.volume_type_get(self.context, 1)
        self.assertEqual('test', result['name'])

    @attr(kind='small')
    def test_volume_type_create_db_duplicate(self):
        """
        Only this method return DBError.
        """
        values = {}
        values['id'] = 1
        values['name'] = 'test'

        self.db.api.volume_type_create(self.context, values)
        self.assertRaises(exception.DBError,
                          self.db.api.volume_type_create,
                          self.context, values)

    @attr(kind='small')
    def test_volume_type_get_all(self):
        """
        Why returns dict in dict?
        """
        values = {}
        values['id'] = 1
        values['name'] = 'test'

        self.db.api.volume_type_create(self.context, values)
        results = self.db.api.volume_type_get_all(self.context)
        self.assertEqual('test', results['test']['name'])

    @attr(kind='small')
    def test_volume_type_get_all_db_not_found(self):
        results = self.db.api.volume_type_get_all(self.context)
        self.assertEqual({}, results)

    @attr(kind='small')
    def test_volume_type_get_all_inactive(self):
        values = {}
        values['id'] = 1
        values['name'] = 'test'

        self.db.api.volume_type_create(self.context, values)
        self.db.api.volume_type_destroy(self.context, 'test')
        results = self.db.api.volume_type_get_all(self.context, True)
        self.assertEqual('test', results['test']['name'])

    @attr(kind='small')
    def test_volume_type_get(self):
        values = {}
        values['id'] = 1
        values['name'] = 'test'

        self.db.api.volume_type_create(self.context, values)
        result = self.db.api.volume_type_get(self.context, 1)
        self.assertEqual('test', result['name'])

    @attr(kind='small')
    def test_volume_type_get_db_not_found(self):
        values = {}
        values['id'] = 1
        values['name'] = 'test'

        self.db.api.volume_type_create(self.context, values)
        self.assertRaises(exception.VolumeTypeNotFound,
                          self.db.api.volume_type_get,
                          self.context, 2)

    @attr(kind='small')
    def test_volume_type_get_by_name(self):
        values = {}
        values['id'] = 1
        values['name'] = 'test'

        self.db.api.volume_type_create(self.context, values)
        result = self.db.api.volume_type_get_by_name(self.context, 'test')
        self.assertEqual('test', result['name'])

    @attr(kind='small')
    def test_volume_type_get_by_name_db_not_found(self):
        values = {}
        values['id'] = 1
        values['name'] = 'test'

        self.db.api.volume_type_create(self.context, values)
        self.assertRaises(exception.VolumeTypeNotFoundByName,
                          self.db.api.volume_type_get_by_name,
                          self.context, 'not_found')

    @attr(kind='small')
    def test_volume_type_destroy(self):
        """
        Returns deleted type. is that right?
        """
#        raise SkipTest("Returned deleted volume_type.")
        values = {}
        values['id'] = 1
        values['name'] = 'test'

        self.db.api.volume_type_create(self.context, values)
        self.db.api.volume_type_destroy(self.context, 'test')
        self.assertRaises(exception.VolumeTypeNotFoundByName,
                          self.db.api.volume_type_get_by_name,
                          self.context, 'test')

    @attr(kind='small')
    def test_volume_type_destroy_db_not_found(self):
        values = {}
        values['id'] = 1
        values['name'] = 'test'

        self.db.api.volume_type_create(self.context, values)
        self.assertRaises(exception.VolumeTypeNotFoundByName,
                          self.db.api.volume_type_destroy,
                          self.context, 'not_found')

    @attr(kind='small')
    def test_volume_type_purge(self):
        values = {}
        values['id'] = 1
        values['name'] = 'test'

        self.db.api.volume_type_create(self.context, values)
        self.db.api.volume_type_purge(self.context, 'test')
        results = self.db.api.volume_type_get_all(self.context, True)
        self.assertEqual({}, results)

    @attr(kind='small')
    def test_volume_type_purge_db_not_found(self):
        values = {}
        values['id'] = 1
        values['name'] = 'test'

        self.db.api.volume_type_create(self.context, values)
        self.assertRaises(exception.VolumeTypeNotFoundByName,
                          self.db.api.volume_type_purge,
                          self.context, 'not_found')

    @attr(kind='small')
    def test_volume_type_extra_specs_get(self):
        values = {}
        values['id'] = 1
        values['name'] = 'test'
        values['extra_specs'] = {'key1': 'value1'}

        self.db.api.volume_type_create(self.context, values)
        result = self.db.api.volume_type_extra_specs_get(self.context, 1)
        self.assertEqual('value1', result['key1'])

    @attr(kind='small')
    def test_volume_type_extra_specs_get_db_not_found(self):
        values = {}
        values['id'] = 1
        values['name'] = 'test'
        values['extra_specs'] = {'key1': 'value1'}

        self.db.api.volume_type_create(self.context, values)
        result = self.db.api.volume_type_extra_specs_get(self.context, 2)
        self.assertEqual({}, result)

    @attr(kind='small')
    def test_volume_type_extra_specs_delete(self):
        values = {}
        values['id'] = 1
        values['name'] = 'test'
        values['extra_specs'] = {'key1': 'value1'}

        self.db.api.volume_type_create(self.context, values)
        self.db.api.volume_type_extra_specs_delete(self.context, 1, 'key1')
        result = self.db.api.volume_type_extra_specs_get(self.context, 1)
        self.assertEqual({}, result)

    @attr(kind='small')
    def test_volume_type_extra_specs_delete_db_not_found(self):
        values = {}
        values['id'] = 1
        values['name'] = 'test'
        values['extra_specs'] = {'key1': 'value1'}

        self.db.api.volume_type_create(self.context, values)
        self.db.api.volume_type_extra_specs_delete(self.context, 1, 'key2')
        result = self.db.api.volume_type_extra_specs_get(self.context, 1)
        self.assertEqual('value1', result['key1'])

    @attr(kind='small')
    def test_volume_type_extra_specs_updaye_or_create(self):
        values = {}
        values['id'] = 1
        values['name'] = 'test'
        values['extra_specs'] = {'key1': 'value1'}

        self.db.api.volume_type_create(self.context, values)
        self.db.api.volume_type_extra_specs_update_or_create(
                                    self.context, 1, {'key1': 'new_value'})
        result = self.db.api.volume_type_extra_specs_get(self.context, 1)
        self.assertEqual('new_value', result['key1'])

    @attr(kind='small')
    def test_volume_type_extra_specs_updaye_or_create_append(self):
        values = {}
        values['id'] = 1
        values['name'] = 'test'
        values['extra_specs'] = {'key1': 'value1'}

        self.db.api.volume_type_create(self.context, values)
        self.db.api.volume_type_extra_specs_update_or_create(
                                    self.context, 1, {'key2': 'new_value'})
        result = self.db.api.volume_type_extra_specs_get(self.context, 1)
        self.assertEqual('value1', result['key1'])
        self.assertEqual('new_value', result['key2'])

    @attr(kind='small')
    def test_volume_type_extra_specs_get_item(self):
#        raise SkipTest("not defined in api interface")
        values = {}
        values['id'] = 1
        values['name'] = 'test'
        values['extra_specs'] = {'key1': 'value1'}

        self.db.api.volume_type_create(self.context, values)
        self.db.api.volume_type_extra_specs_update_or_create(
                                    self.context, 1, {'key1': 'new_value'})
        result = self.db.api.volume_type_extra_specs_get(self.context, 1)
        self.assertEqual('new_value', result['key1'])

        result = self.db.api.volume_type_extra_specs_get_item(self.context,
                                        volume_type_id=1, key='key1')
        self.assertEqual('new_value', result['key1'])

    @attr(kind='small')
    def test_volume_type_extra_specs_get_item_exception(self):
#        raise SkipTest("not defined in api interface")
        values = {}
        values['id'] = 1
        values['name'] = 'test'
        values['extra_specs'] = {'key1': 'value1'}

        self.db.api.volume_type_create(self.context, values)
        self.db.api.volume_type_extra_specs_update_or_create(
                                    self.context, 1, {'key1': 'new_value'})
        result = self.db.api.volume_type_extra_specs_get(self.context, 1)
        self.assertEqual('new_value', result['key1'])

        self.assertRaises(exception.VolumeTypeExtraSpecsNotFound,
                self.db.api.volume_type_extra_specs_get_item,
                        self.context, volume_type_id=1, key='key2')

    @attr(kind='small')
    def test_vsa_create(self):
        FLAGS.vsa_name_template = "vsa %s"
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100
        self.db.api.instance_type_create(self.context, values)

        vsa = {}
        vsa['id'] = 1
        vsa['display_name'] = 'test'
        vsa['display_description'] = 'test'
        vsa['project_id'] = 'fake'
        vsa['availability_zone'] = 'nova'
        vsa['instance_type_id'] = 100
        vsa['image_ref'] = 'http://s3url'
        vsa['status'] = 'available'

        self.db.api.vsa_create(self.context, vsa)
        result = self.db.api.vsa_get(self.context, 1)
        self.assertEqual('vsa 1', result.name)
        self.assertEqual('test', result.display_name)
        self.assertEqual('test', result.display_description)
        self.assertEqual('fake', result.project_id)
        self.assertEqual('nova', result.availability_zone)
        self.assertEqual(100, result.instance_type_id)
        self.assertEqual('http://s3url', result.image_ref)
        self.assertEqual(0, result.vc_count)
        self.assertEqual(0, result.vol_count)
        self.assertEqual('available', result.status)

    @attr(kind='small')
    def test_vsa_create_db_duplicate(self):
        vsa = {}
        vsa['id'] = 1
        vsa['display_name'] = 'test'
        vsa['display_description'] = 'test'
        vsa['project_id'] = 'fake'
        vsa['availability_zone'] = 'nova'
        vsa['instance_type_id'] = 100
        vsa['image_ref'] = 'http://s3url'
        vsa['status'] = 'available'

        self.db.api.vsa_create(self.context, vsa)
        self.assertRaises(exception.DBError,
                          self.db.api.vsa_create,
                          self.context, vsa)

    @attr(kind='small')
    def test_vsa_update(self):
        FLAGS.vsa_name_template = "vsa %s"
        vsa = {}
        vsa['id'] = 1
        vsa['display_name'] = 'test'
        vsa['display_description'] = 'test'
        vsa['project_id'] = 'fake'
        vsa['availability_zone'] = 'nova'
        vsa['instance_type_id'] = 100
        vsa['image_ref'] = 'http://s3url'
        vsa['status'] = 'available'

        self.db.api.vsa_create(self.context, vsa)
        self.db.api.vsa_update(self.context, 1, {'display_name': 'new_name'})
        result = self.db.api.vsa_get(self.context, 1)
        self.assertEqual('vsa 1', result.name)
        self.assertEqual('new_name', result.display_name)

    @attr(kind='small')
    def test_vsa_update_db_not_found(self):
        vsa = {}
        vsa['id'] = 1
        vsa['display_name'] = 'test'
        vsa['display_description'] = 'test'
        vsa['project_id'] = 'fake'
        vsa['availability_zone'] = 'nova'
        vsa['instance_type_id'] = 100
        vsa['image_ref'] = 'http://s3url'
        vsa['status'] = 'available'

        self.db.api.vsa_create(self.context, vsa)
        self.assertRaises(exception.VirtualStorageArrayNotFound,
                          self.db.api.vsa_update,
                          self.context, 2,  {'display_name': 'new_name'})

    @attr(kind='small')
    def test_vsa_destroy(self):
        vsa = {}
        vsa['id'] = 1
        vsa['display_name'] = 'test'
        vsa['display_description'] = 'test'
        vsa['project_id'] = 'fake'
        vsa['availability_zone'] = 'nova'
        vsa['instance_type_id'] = 100
        vsa['image_ref'] = 'http://s3url'
        vsa['status'] = 'available'

        self.db.api.vsa_create(self.context, vsa)
        self.db.api.vsa_destroy(self.context, 1)
        self.assertRaises(exception.VirtualStorageArrayNotFound,
                          self.db.api.vsa_get,
                          self.context, 1)

    @attr(kind='small')
    def test_vsa_destroy_db_not_found(self):
        """
        should be raise error.
        """
        FLAGS.vsa_name_template = "vsa %s"
        vsa = {}
        vsa['id'] = 1
        vsa['display_name'] = 'test'
        vsa['display_description'] = 'test'
        vsa['project_id'] = 'fake'
        vsa['availability_zone'] = 'nova'
        vsa['instance_type_id'] = 100
        vsa['image_ref'] = 'http://s3url'
        vsa['status'] = 'available'

        self.db.api.vsa_create(self.context, vsa)
        self.db.api.vsa_destroy(self.context, 2)
        result = self.db.api.vsa_get(self.context, 1)
        self.assertEqual('vsa 1', result.name)

    @attr(kind='small')
    def test_vsa_get(self):
        FLAGS.vsa_name_template = "vsa %s"
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100
        self.db.api.instance_type_create(self.context, values)

        vsa = {}
        vsa['id'] = 1
        vsa['display_name'] = 'test'
        vsa['display_description'] = 'test'
        vsa['project_id'] = 'fake'
        vsa['availability_zone'] = 'nova'
        vsa['instance_type_id'] = 100
        vsa['image_ref'] = 'http://s3url'
        vsa['status'] = 'available'

        self.db.api.vsa_create(self.context, vsa)
        result = self.db.api.vsa_get(self.context, 1)
        self.assertEqual('vsa 1', result.name)

    @attr(kind='small')
    def test_vsa_get_user(self):
        FLAGS.vsa_name_template = "vsa %s"
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100
        self.db.api.instance_type_create(self.context, values)

        vsa = {}
        vsa['id'] = 1
        vsa['display_name'] = 'test'
        vsa['display_description'] = 'test'
        vsa['project_id'] = 'fake'
        vsa['availability_zone'] = 'nova'
        vsa['instance_type_id'] = 100
        vsa['image_ref'] = 'http://s3url'
        vsa['status'] = 'available'

        self.db.api.vsa_create(self.context, vsa)

        self.context.is_admin = False
        self.context.user_id = 'fake'
        self.context.project_id = 'fake'
        result = self.db.api.vsa_get(self.context, 1)
        self.assertEqual('vsa 1', result.name)

    @attr(kind='small')
    def test_vsa_get_db_not_found(self):
        vsa = {}
        vsa['id'] = 1
        vsa['display_name'] = 'test'
        vsa['display_description'] = 'test'
        vsa['project_id'] = 'fake'
        vsa['availability_zone'] = 'nova'
        vsa['instance_type_id'] = 100
        vsa['image_ref'] = 'http://s3url'
        vsa['status'] = 'available'

        self.db.api.vsa_create(self.context, vsa)
        self.assertRaises(exception.VirtualStorageArrayNotFound,
                          self.db.api.vsa_get,
                          self.context, 2)

    @attr(kind='small')
    def test_vsa_get_all(self):
        FLAGS.vsa_name_template = "vsa %s"
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100
        self.db.api.instance_type_create(self.context, values)

        vsa = {}
        vsa['id'] = 1
        vsa['display_name'] = 'test'
        vsa['display_description'] = 'test'
        vsa['project_id'] = 'fake'
        vsa['availability_zone'] = 'nova'
        vsa['instance_type_id'] = 100
        vsa['image_ref'] = 'http://s3url'
        vsa['status'] = 'available'

        self.db.api.vsa_create(self.context, vsa)
        results = self.db.api.vsa_get_all(self.context)
        result = results[0]
        self.assertEqual('vsa 1', result.name)

    @attr(kind='small')
    def test_vsa_get_all_db_not_found(self):
        results = self.db.api.vsa_get_all(self.context)
        self.assertEqual([], results)

    @attr(kind='small')
    def test_vsa_get_all_by_project(self):
        FLAGS.vsa_name_template = "vsa %s"
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100
        self.db.api.instance_type_create(self.context, values)

        vsa = {}
        vsa['id'] = 1
        vsa['display_name'] = 'test'
        vsa['display_description'] = 'test'
        vsa['project_id'] = 'fake'
        vsa['availability_zone'] = 'nova'
        vsa['instance_type_id'] = 100
        vsa['image_ref'] = 'http://s3url'
        vsa['status'] = 'available'

        self.db.api.vsa_create(self.context, vsa)
        results = self.db.api.vsa_get_all_by_project(self.context, 'fake')
        result = results[0]
        self.assertEqual('vsa 1', result.name)

    @attr(kind='small')
    def test_vsa_get_all_by_project_db_not_found(self):
        FLAGS.vsa_name_template = "vsa %s"
        values = {}
        values['id'] = 100
        values['name'] = 'test'
        values['memory_mb'] = 100
        values['vcpus'] = 2
        values['local_gb'] = 10
        values['flavorid'] = 100
        self.db.api.instance_type_create(self.context, values)

        vsa = {}
        vsa['id'] = 1
        vsa['display_name'] = 'test'
        vsa['display_description'] = 'test'
        vsa['project_id'] = 'fake'
        vsa['availability_zone'] = 'nova'
        vsa['instance_type_id'] = 100
        vsa['image_ref'] = 'http://s3url'
        vsa['status'] = 'available'

        self.db.api.vsa_create(self.context, vsa)
        results = self.db.api.vsa_get_all_by_project(self.context, 'not_found')
        self.assertEqual([], results)
