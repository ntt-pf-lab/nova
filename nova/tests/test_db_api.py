# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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
from nose.plugins.skip import SkipTest

from nova import test
from nova import context
from nova import db
from nova import flags
from nova import exception


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
        self.context = context.RequestContext(self.user_id, self.project_id)

    def test_instance_get_project_vpn(self):
        values = {'instance_type_id': FLAGS.default_instance_type,
                  'image_ref': FLAGS.vpn_image_id,
                  'project_id': self.project_id,
                 }
        instance = db.instance_create(self.context, values)
        result = db.instance_get_project_vpn(self.context.elevated(),
                                             self.project_id)
        self.assertEqual(instance['id'], result['id'])

    def test_instance_get_project_vpn_joins(self):
        values = {'instance_type_id': FLAGS.default_instance_type,
                  'image_ref': FLAGS.vpn_image_id,
                  'project_id': self.project_id,
                 }
        instance = db.instance_create(self.context, values)
        _setup_networking(instance['id'])
        result = db.instance_get_project_vpn(self.context.elevated(),
                                             self.project_id)
        self.assertEqual(instance['id'], result['id'])
        self.assertEqual(result['fixed_ips'][0]['floating_ips'][0].address,
                         '1.2.1.2')

    def test_instance_get_all_by_filters(self):
        args = {'reservation_id': 'a', 'image_ref': 1, 'host': 'host1'}
        inst1 = db.instance_create(self.context, args)
        inst2 = db.instance_create(self.context, args)
        result = db.instance_get_all_by_filters(self.context, {})
        self.assertTrue(2, len(result))

    def test_instance_get_all_by_filters_deleted(self):
        args1 = {'reservation_id': 'a', 'image_ref': 1, 'host': 'host1'}
        inst1 = db.instance_create(self.context, args1)
        args2 = {'reservation_id': 'b', 'image_ref': 1, 'host': 'host1'}
        inst2 = db.instance_create(self.context, args2)
        db.instance_destroy(self.context, inst1.id)
        result = db.instance_get_all_by_filters(self.context.elevated(), {})
        self.assertEqual(2, len(result))
        self.assertEqual(result[0].id, inst2.id)
        self.assertEqual(result[1].id, inst1.id)
        self.assertTrue(result[1].deleted)

    def test_eventlog_create(self):
        con = {}
        con['id'] = 1
        con['request_id'] = '1'
        con['message_id'] = '1'
        con['event_type'] = 'event_type'
        con['publisher_id'] = 'compute'
        con['priority'] = 'INFO'
        args1 = "{'args': {'instance_id': '1'},'method': 'run_instance'}"
        con['message'] = args1
        con['status'] = 'Success'
        con['user_id'] = 'fake'
        con['tenant_id'] = 'fake'

        db.api.eventlog_create(self.context, con)
        result = db.api.eventlog_get(self.context, '1', 1)

        self.assertEqual(1, result.id)
        self.assertEqual('1', result.request_id)
        self.assertEqual('1', result.message_id)
        self.assertEqual('event_type', result.event_type)
        self.assertEqual('compute', result.publisher_id)
        self.assertEqual('INFO', result.priority)
        self.assertEqual(args1, result.message)
        self.assertEqual('Success', result.status)
        self.assertEqual('fake', result.user_id)
        self.assertEqual('fake', result.tenant_id)

    def test_eventlog_create_duplicate(self):
        raise SkipTest("DBError occured")

        con = {}
        con['id'] = 1
        con['request_id'] = '1'
        con['message_id'] = '1'
        con['event_type'] = 'event_type'
        con['publisher_id'] = 'compute'
        con['priority'] = 'INFO'
        args1 = "{'args': {'instance_id': '1'},'method': 'run_instance'}"
        con['message'] = args1
        con['status'] = 'Success'
        con['user_id'] = 'fake'
        con['tenant_id'] = 'fake'

        db.api.eventlog_create(self.context, con)
        self.assertRaises(exception.Duplicate, db.api.eventlog_create,
                          self.context, con)

    def test_eventlog_update(self):
        con = {}
        con['id'] = 1
        con['request_id'] = '1'
        con['message_id'] = '1'
        con['event_type'] = 'event_type'
        con['publisher_id'] = 'compute'
        con['priority'] = 'INFO'
        args1 = "{'args': {'instance_id': '1'},'method': 'run_instance'}"
        con['message'] = args1
        con['status'] = 'Success'
        con['user_id'] = 'fake'
        con['tenant_id'] = 'fake'

        db.api.eventlog_create(self.context, con)
        db.api.eventlog_update(self.context, '1', {'status': 'Timeout'})
        result = db.api.eventlog_get(self.context, '1', 1)

        self.assertEqual('Timeout', result.status)

    def test_eventlog_update_not_found(self):
        con = {}
        con['id'] = 1
        con['request_id'] = '1'
        con['message_id'] = '1'
        con['event_type'] = 'event_type'
        con['publisher_id'] = 'compute'
        con['priority'] = 'INFO'
        args1 = "{'args': {'instance_id': '1'},'method': 'run_instance'}"
        con['message'] = args1
        con['status'] = 'Success'
        con['user_id'] = 'fake'
        con['tenant_id'] = 'fake'

        db.api.eventlog_create(self.context, con)
        self.assertRaises(exception.EventLogNotFound,
                          db.api.eventlog_update(self.context,
                                                 '2', {'status': 'Timeout'}))

    def test_eventlog_get(self):
        con = {}
        con['id'] = 1
        con['request_id'] = '1'
        con['message_id'] = '1'
        con['event_type'] = 'event_type'
        con['publisher_id'] = 'compute'
        con['priority'] = 'INFO'
        args1 = "{'args': {'instance_id': '1'},'method': 'run_instance'}"
        con['message'] = args1
        con['status'] = 'Success'
        con['user_id'] = 'fake'
        con['tenant_id'] = 'fake'

        db.api.eventlog_create(self.context, con)
        result = db.api.eventlog_get(self.context, '1', 1)

        self.assertEqual(1, result.id)
        self.assertEqual('1', result.request_id)
        self.assertEqual('1', result.message_id)
        self.assertEqual('event_type', result.event_type)
        self.assertEqual('compute', result.publisher_id)
        self.assertEqual('INFO', result.priority)
        self.assertEqual(args1, result.message)
        self.assertEqual('Success', result.status)
        self.assertEqual('fake', result.user_id)
        self.assertEqual('fake', result.tenant_id)

    def test_eventlog_get_not_found(self):
        con = {}
        con['id'] = 1
        con['request_id'] = '1'
        con['message_id'] = '1'
        con['event_type'] = 'event_type'
        con['publisher_id'] = 'compute'
        con['priority'] = 'INFO'
        con['message'] = "{'args': {'instance_id': '1'},\
                           'method': 'run_instance'}"
        con['status'] = 'Success'
        con['user_id'] = 'fake'
        con['tenant_id'] = 'fake'

        db.api.eventlog_create(self.context, con)
        self.assertRaises(exception.EventLogNotFound, db.api.eventlog_get,
                          self.context, '2', 1)

    def test_eventlog_get_all_by_request_id(self):
        con = {}
        con['id'] = 1
        con['request_id'] = '1'
        con['message_id'] = '1'
        con['event_type'] = 'event_type'
        con['publisher_id'] = 'compute'
        con['priority'] = 'INFO'
        args1 = "{'args': {'instance_id': '1'},'method': 'run_instance'}"
        con['message'] = args1
        con['status'] = 'Success'
        con['user_id'] = 'fake'
        con['tenant_id'] = 'fake'

        db.api.eventlog_create(self.context, con)

        con1 = {}
        con1['id'] = 2
        con1['request_id'] = '1'
        con1['message_id'] = '1'
        con1['event_type'] = 'event_type'
        con1['publisher_id'] = 'compute'
        con1['priority'] = 'INFO'
        con['message'] = args1
        con1['status'] = 'Success'
        con1['user_id'] = 'fake'
        con1['tenant_id'] = 'fake'

        db.api.eventlog_create(self.context, con1)

        result = []
        result = db.api.eventlog_get_all_by_request_id(self.context,
                                                       '1',
                                                       session=None)

        self.assertEqual(1, result[0].id)
        self.assertEqual('1', result[0].request_id)
        self.assertEqual('1', result[0].message_id)
        self.assertEqual('event_type', result[0].event_type)
        self.assertEqual('compute', result[0].publisher_id)
        self.assertEqual('INFO', result[0].priority)
        self.assertEqual(args1, result[0].message)
        self.assertEqual('Success', result[0].status)
        self.assertEqual('fake', result[0].user_id)
        self.assertEqual('fake', result[0].tenant_id)
