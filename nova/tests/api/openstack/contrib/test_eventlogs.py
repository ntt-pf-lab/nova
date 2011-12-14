# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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

import json
import webob

from nova import context
from nova import db
from nova import test
from nova.api.openstack.contrib.eventlogs import EventLogsController
from nova.tests.api.openstack import fakes


def fake_log(id, request_id, priority='INFO'):
    return {'request_id': request_id,
            'priority': priority,
            'message': 'FAKE message',
            'status': 'Success',
            'event_type': 'FAKE event',
            'user_id': 'abc',
            'id': id}


def get_single_requestid_logs():
    return [fake_log(1, 'cf5685ea-2611-4f2e-9036-b10dc9bdf4dc'),
            fake_log(2, 'cf5685ea-2611-4f2e-9036-b10dc9bdf4dc'),
            fake_log(3, 'cf5685ea-2611-4f2e-9036-b10dc9bdf4dc')]


def get_all_logs():
    return [fake_log(1, 'cf5685ea-2611-4f2e-9036-b10dc9bdf4da'),
            fake_log(2, 'cf5685ea-2611-4f2e-9036-b10dc9bdf4db'),
            fake_log(3, 'cf5685ea-2611-4f2e-9036-b10dc9bdf4dc'),
            fake_log(4, 'cf5685ea-2611-4f2e-9036-b10dc9bdf4dd'),
            fake_log(5, 'cf5685ea-2611-4f2e-9036-b10dc9bdf4de'),
            fake_log(6, 'cf5685ea-2611-4f2e-9036-b10dc9bdf4df'),
            fake_log(7, 'cf5685ea-2611-4f2e-9036-b10dc9bdf4e0'),
            fake_log(8, 'cf5685ea-2611-4f2e-9036-b10dc9bdf4e1'),
            fake_log(9, 'cf5685ea-2611-4f2e-9036-b10dc9bdf4e2'),
            fake_log(10, 'cf5685ea-2611-4f2e-9036-b10dc9bdf4e3'),
            fake_log(11, 'cf5685ea-2611-4f2e-9036-b10dc9bdf4e4')]


def db_eventlog_get_all_by_request_id(context, request_id, session=None):
    return get_single_requestid_logs()


def db_eventlog_get_all(context, filters=None):
    return get_all_logs()


class EventlogsTest(test.TestCase):

    def setUp(self):
        super(EventlogsTest, self).setUp()
        self.controller = EventLogsController()
        fakes.stub_out_networking(self.stubs)
        fakes.stub_out_rate_limiting(self.stubs)
        self.stubs.Set(db.api, "eventlog_get_all",
                       db_eventlog_get_all)
        self.stubs.Set(db.api, "eventlog_get_all_by_request_id",
                       db_eventlog_get_all_by_request_id)
        self.context = context.get_admin_context()

    def test_logs_list(self):
        req = webob.Request.blank('/v1.1/admin/logs')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)

        response = {'eventlogs': get_all_logs()}
        self.assertEqual(res_dict, response)

    def test_logs_request_id(self):
        req_url = '/v1.1/admin/logs/cf5685ea-2611-4f2e-9036-b10dc9bdf4dc'
        req = webob.Request.blank(req_url)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)

        response = {'eventlogs': get_single_requestid_logs()}
        self.assertEqual(res_dict, response)

    def test_logs_list_type_input(self):
        req = webob.Request.blank('/v1.1/admin/logs?type=INFO')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)

        response = {'eventlogs': get_all_logs()}
        self.assertEqual(res_dict, response)

    def test_logs_list_limit(self):
        req = webob.Request.blank('/v1.1/admin/logs?limit=5')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)
        expected_logs = get_all_logs()
        response = {'eventlogs': expected_logs[:5]}
        self.assertEqual(res_dict, response)

    def test_logs_list_offset(self):
        req = webob.Request.blank('/v1.1/admin/logs?offset=1')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)
        expected_logs = get_all_logs()
        response = {'eventlogs': expected_logs[1:]}
        self.assertEqual(res_dict, response)

    def test_logs_list_limit_with_offset(self):
        req = webob.Request.blank('/v1.1/admin/logs?offset=2&limit=10')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)
        expected_logs = get_all_logs()
        response = {'eventlogs': expected_logs[2:]}
        self.assertEqual(res_dict, response)

    def test_logs_list_marker(self):
        req = webob.Request.blank('/v1.1/admin/logs?marker=5')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_dict = json.loads(res.body)
        expected_logs = get_all_logs()
        response = {'eventlogs': expected_logs[5:]}
        self.assertEqual(res_dict, response)

    def test_logs_list_invalid_marker(self):
        req = webob.Request.blank('/v1.1/admin/logs?marker=555')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)
        self.assertNotEqual(res.body.find('marker [555] not found'), -1)