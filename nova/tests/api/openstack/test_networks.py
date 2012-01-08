# Copyright 2012 NTT.
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

import webob
import json

from nova import test
from nova.tests.api.openstack import fakes
from nova.api.openstack import networks
from nova.network.api import API as api
from nova import exception


FAKE_LABEL = 'test001'
FAKE_UUID = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
FAKE_CIDR = '192.168.0.0/25'
FAKE_PID = 'fake'
FAKE_CIDR_V6 = 'fe80::/125'

NETWORKS = {
    "networks": [
        {
        "label": FAKE_LABEL,
        "uuid" : FAKE_UUID,
        "cidr" : FAKE_CIDR,
        "cidr_v6": FAKE_CIDR_V6,
        "priority": 0,
        },
        {
        "label": "test002",
        "uuid" : "fffffff-gggg-hhhh-iiii-jjjjjjjjjjjj",
        "cidr" : "192.168.0.128/25",
        "cidr_v6": "fe81::/125",
        "priority": 0,
        },
     ],
}

NETWORK_INFO = {
    "network": {
        "created_at": "2012-01-06-T12:34:56Z",
        "updated_at": "2012-01-06-T12:34:56Z",
        "id": "network001",
        "injected": "T",
        "cidr": FAKE_CIDR,
        "bridge": "br100",
        "gateway": "192.168.0.126",
        "dns1": "172.17.16.100",
        "vlan": 100,
        "vpn": 1000,
        "vpn_private_address": "10.11.12.0/25",
        "dhcp_start": "192.168.0.0",
        "project_id": FAKE_PID,
        "host": "host001",
        "cidr_v6": FAKE_CIDR_V6,
        "gateway_v6": "fe80::8/125",
        "label": FAKE_LABEL,
        "bridge_interface": "eth0",
        "multi_host": "T",
        "dns2": "172.18.10.1",
        "uuid": FAKE_UUID,
        "priority": 0,
        "dhcp_server": None,
        }
}

NETWORK_INFO_DEFAULT = {
    "network": {
        "created_at": "2012-01-06-T12:34:56Z",
        "updated_at": "2012-01-06-T12:34:56Z",
        "id": "network001",
        "injected": "T",
        "cidr": FAKE_CIDR,
        "bridge": "br100",
        "gateway": "192.168.0.126",
        "dns1": "172.17.16.100",
        "vlan": 100,
        "vpn": 1000,
        "vpn_private_address": "10.11.12.0/25",
        "dhcp_start": "192.168.0.0",
        "project_id": None,
        "host": "host001",
        "cidr_v6": FAKE_CIDR_V6,
        "gateway_v6": "fe80::8/125",
        "label": FAKE_LABEL,
        "bridge_interface": "eth0",
        "multi_host": "T",
        "dns2": "172.18.10.1",
        "uuid": FAKE_UUID,
        "priority": 0,
        "dhcp_server": None,
        }
}


def create_network_exc(self, context, project_id, network):
    raise exception.ApiError()


def delete_network_exc(self, context, uuid):
    raise exception.NetworkNotFoundForUUID()


def get_network_info_exc(self, context, uuid):
    raise exception.NetworkNotFoundForUUID()


def create_network(self, context, project_id, network):
    if project_id:
        return NETWORK_INFO['network']
    else:
        return NETWORK_INFO_DEFAULT['network']


def delete_network(self, context, uuid):
    pass


def get_networks(self, context, project_id, is_detail):
    if is_detail:
        if project_id:
            return [NETWORK_INFO['network']]
        else:
            return [NETWORK_INFO_DEFAULT['network']]
    else:
        return NETWORKS['networks']


def get_network_info(self, context, uuid):
    if context.project_id:
        return NETWORK_INFO['network']
    else:
        return NETWORK_INFO_DEFAULT['network']


class NetworksTest(test.TestCase):
    def setup(self):
        super(NeworksTest, self).setUp()

    def test_v10_invalid_request_create(self):
        body = dict(network = dict(label = FAKE_LABEL, cidr = FAKE_CIDR))
        req = webob.Request.blank('/v1.0/networks')
        req.method = 'POST'
        req.body = json.dumps(body)
        req.headers["content-type"] = "application/json"
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 404)

    def test_v10_invalid_request_delete(self):
        self.stubs.Set(api, 'delete_network', delete_network)
        req = webob.Request.blank('/v1.0/networks/%s' % FAKE_UUID)
        req.method = 'DELETE'
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 404)

    def test_v10_invalid_request_index(self):
        req = webob.Request.blank('/v1.0/networks')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 404)

    def test_v10_invalid_request_show(self):
        req = webob.Request.blank('/v1.0/networks/%s' % FAKE_UUID)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 404)

    def test_v10_invalid_request_detail(self):
        req = webob.Request.blank('/v1.0/networks/detail')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 404)

    def test_v11_create(self):
        self.stubs.Set(api, 'create_network', create_network)
        body = dict(network = dict(label = FAKE_LABEL, cidr = FAKE_CIDR))
        req = webob.Request.blank('/v1.1/%s/networks' % FAKE_PID)
        req.method = 'POST'
        req.body = json.dumps(body)
        req.headers["content-type"] = "application/json"
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_network = json.loads(res.body)
        self.assertEqual(res_network, NETWORK_INFO)

    def test_v11_delete(self):
        self.stubs.Set(api, 'delete_network', delete_network)
        req = webob.Request.blank('/v1.1/%s/networks/%s' % (FAKE_PID, FAKE_UUID))
        req.method = 'DELETE'
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)

    def test_v11_index(self):
        self.stubs.Set(api, 'get_networks', get_networks)
        req = webob.Request.blank('/v1.1/%s/networks' % FAKE_PID)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_networks = json.loads(res.body)
        self.assertEqual(res_networks, NETWORKS)

    def test_v11_detail(self):
        self.stubs.Set(api, 'get_networks', get_networks)
        req = webob.Request.blank('/v1.1/%s/networks/detail' % FAKE_PID)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_networks = json.loads(res.body)
        self.assertEqual(res_networks['networks'][0], NETWORK_INFO['network'])

    def test_v11_show(self):
        self.stubs.Set(api, 'get_network_info', get_network_info)
        req = webob.Request.blank('/v1.1/%s/networks/%s' % (FAKE_PID, FAKE_UUID))
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_network = json.loads(res.body)
        self.assertEqual(res_network, NETWORK_INFO)

    @test.skip_test('default tenant_id not support yet.')
    def test_v11_default_tenantid_create(self):
        self.stubs.Set(api, 'create_network', create_network)
        body = dict(network = dict(label = FAKE_LABEL, cidr = FAKE_CIDR))
        req = webob.Request.blank('/v1.1/default/networks')
        req.method = 'POST'
        req.body = json.dumps(body)
        req.headers["content-type"] = "application/json"
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_network = json.loads(res.body)
        self.assertEqual(res_network, NETWORK_INFO_DEFAULT)

    @test.skip_test('default tenant_id not support yet.')
    def test_v11_default_tenantid_index(self):
        self.stubs.Set(api, 'get_networks', get_networks)
        req = webob.Request.blank('/v1.1/default/networks')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_networks = json.loads(res.body)
        self.assertEqual(res_networks, NETWORKS)

    @test.skip_test('default tenant_id not support yet.')
    def test_v11_default_tenantid_show(self):
        self.stubs.Set(api, 'get_network_info', get_network_info)
        req = webob.Request.blank('/v1.1/default/networks/%s' % FAKE_UUID)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_network = json.loads(res.body)
        self.assertEqual(res_network, NETWORK_INFO_DEFAULT)

    @test.skip_test('default tenant_id not support yet.')
    def test_v11_default_tenantid_detail(self):
        self.stubs.Set(api, 'get_networks', get_networks)
        req = webob.Request.blank('/v1.1/default/networks/detail')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 200)
        res_networks = json.loads(res.body)
        self.assertEqual(res_networks['networks'][0],
                         NETWORK_INFO_DEFAULT['network'])

    def test_v11_except_create(self):
        self.stubs.Set(api, 'create_network', create_network_exc)
        body = dict(network = dict(label = FAKE_LABEL, cidr = FAKE_CIDR))
        req = webob.Request.blank('/v1.1/%s/networks' % FAKE_PID)
        req.method = 'POST'
        req.body = json.dumps(body)
        req.headers["content-type"] = "application/json"
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_v11_except_delete(self):
        self.stubs.Set(api, 'delete_network', delete_network_exc)
        req = webob.Request.blank('/v1.1/%s/networks/%s' % (FAKE_PID, FAKE_UUID))
        req.method = 'DELETE'
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 404)

    def test_v11_except_show(self):
        self.stubs.Set(api, 'get_network_info', get_network_info_exc)
        req = webob.Request.blank('/v1.1/%s/networks/%s' % (FAKE_PID, FAKE_UUID))
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 404)

    def test_v11_invalid_body_create(self):
        body = dict(notnetwork = dict(label = FAKE_LABEL, cidr = FAKE_CIDR))
        req = webob.Request.blank('/v1.1/%s/networks' % FAKE_PID)
        req.method = 'POST'
        req.body = json.dumps(body)
        req.headers["content-type"] = "application/json"
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)
