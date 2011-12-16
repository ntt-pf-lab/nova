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
Tests For nova.network.quantum.client
"""

import httplib
from nova import compute
from nova import context
from nova import db
from nova import exception
from nova import flags
from nova import log as logging
from nova import rpc
from nova import test
from nova import utils
from nose.plugins.attrib import attr
from nova.network import quantum
from nova.network.quantum import client


class JSONSerializerTestCase(test.TestCase):
    """Test for nova.network.quantum.client.JSONSerializer"""
    def setUp(self):
        super(JSONSerializerTestCase, self).setUp()
        self.jsonserializer = client.JSONSerializer()

    @attr(kind='small')
    def test_serialize(self):
        """Test for nova.network.quantum.client.JSONSerializer.serialize"""
        ref = self.jsonserializer.serialize(data='test-string',
                                            content_type=None)

        self.assertEqual('"test-string"', ref)

    @attr(kind='small')
    def test_serialize_parameter_int(self):
        """Test for nova.network.quantum.client.JSONSerializer.serialize"""
        ref = self.jsonserializer.serialize(data=1234,
                                            content_type=None)

        self.assertEqual('1234', ref)

    @attr(kind='small')
    def test_serialize_parameter_dict(self):
        """Test for nova.network.quantum.client.JSONSerializer.serialize"""
        data = dict(key1='abc')
        ref = self.jsonserializer.serialize(data=data,
                                            content_type=None)

        self.assertEqual('{"key1": "abc"}', ref)

    @attr(kind='small')
    def test_serialize_parameter_list(self):
        """Test for nova.network.quantum.client.JSONSerializer.serialize"""
        data = ['abc']
        ref = self.jsonserializer.serialize(data=data,
                                            content_type=None)

        self.assertEqual('["abc"]', ref)

    @attr(kind='small')
    def test_serialize_parameter_none(self):
        """Test for nova.network.quantum.client.JSONSerializer.serialize"""
        data = None
        ref = self.jsonserializer.serialize(data=data,
                                            content_type=None)

        self.assertEqual('null', ref)

    @attr(kind='small')
    def test_deserialize(self):
        """Test for nova.network.quantum.client.JSONSerializer.deserialize"""
        data = '"test-string"'
        ref = self.jsonserializer.deserialize(data=data, content_type=None)

        self.assertEqual('test-string', ref)

    @attr(kind='small')
    def test_deserialize_parameter_dict(self):
        """Test for nova.network.quantum.client.JSONSerializer.deserialize"""
        data = '{"key1": "abc"}'
        ref = self.jsonserializer.deserialize(data=data, content_type=None)

        self.assertEqual(dict(key1='abc'), ref)

    @attr(kind='small')
    def test_deserialize_parameter_list(self):
        """Test for nova.network.quantum.client.JSONSerializer.deserialize"""
        data = '["abc"]'
        ref = self.jsonserializer.deserialize(data=data, content_type=None)

        self.assertEqual(['abc'], ref)

    @attr(kind='small')
    def test_deserialize_parameter_none(self):
        """Test for nova.network.quantum.client.JSONSerializer.deserialize"""
        data = 'null'
        ref = self.jsonserializer.deserialize(data=data, content_type=None)

        self.assertEqual(None, ref)


class ClientTestCase(test.TestCase):
    """Test for nova.network.quantum.client.Client"""
    def setUp(self):
        super(ClientTestCase, self).setUp()
        try:
            if getattr(httplib.HTTPConnection,'wrapped'):
                httplib.HTTPConnection = getattr(httplib.HTTPConnection,'wrapped')
        except Exception:
            pass

        self.client = client.Client()

    @attr(kind='small')
    def test_quantumnotfoundexception(self):
        """Test for nova.network.quantum.client.QuantumNotFoundException"""
        ref = client.QuantumNotFoundException('test-message')

        self.assertEqual(True, isinstance(ref, Exception))

    @attr(kind='small')
    def test_quantumserverexception(self):
        """Test for nova.network.quantum.client.QuantumServerException"""
        ref = client.QuantumServerException('test-message')

        self.assertEqual(True, isinstance(ref, Exception))

    @attr(kind='small')
    def test_quantumioexception(self):
        """Test for nova.network.quantum.client.QuantumIOException"""
        ref = client.QuantumIOException('test-message')

        self.assertEqual(True, isinstance(ref, Exception))

    @attr(kind='small')
    def test_get_connection_type(self):
        """Test for nova.network.quantum.client.Client.get_connection_type"""
        self.client = client.Client()
        ref = self.client.get_connection_type()

        self.assertEqual('HTTPConnection', ref.__name__)

    @attr(kind='small')
    def test_get_connection_type_parameter(self):
        """Test for nova.network.quantum.client.Client.get_connection_type"""
        self.client = client.Client(use_ssl=True)
        ref = self.client.get_connection_type()

        self.assertEqual('HTTPSConnection', ref.__name__)

    @attr(kind='small')
    def test_get_connection_type_parameter_stub(self):
        """Test for nova.network.quantum.client.Client.get_connection_type"""
        class DumyCls(object):
            pass

        self.client = client.Client(testing_stub=DumyCls)
        ref = self.client.get_connection_type()

        self.assertEqual('DumyCls', ref.__name__)

    @attr(kind='small')
    def test_do_request(self):
        """Test for nova.network.quantum.client.Client.do_request"""
        self.client = client.Client(tenant='1')

        def fake_request(self, method, url, body=None, headers={}):
            pass

        self.stubs.Set(httplib.HTTPConnection, 'request', fake_request)

        class DumyResponse(object):
            def __init__(self):
                self.status = 200

            def read(self):
                return '"test-result"'

        def fake_getresponse(con):
            return DumyResponse()

        self.stubs.Set(httplib.HTTPConnection, 'getresponse', fake_getresponse)

        ref = self.client.do_request(method='GET', action='www.com',
                                     body=None, headers=None, params=None)

        self.assertEquals('test-result', ref)

    @attr(kind='small')
    def test_do_request_parameter(self):
        """Test for nova.network.quantum.client.Client.do_request"""
        class DumyLog(object):
            def debug(self, msg):
                pass
        self.client = client.Client(tenant='1', use_ssl=True, key_file='/f1',
                                    logger=DumyLog())

        def fake_request(self, method, url, body=None, headers={}):
            pass

        self.stubs.Set(httplib.HTTPSConnection, 'request', fake_request)

        class DumyResponse(object):
            def __init__(self):
                self.status = 200

            def read(self):
                return '"test-result"'

        def fake_getresponse(con):
            return DumyResponse()

        self.stubs.Set(httplib.HTTPSConnection, 'getresponse',
                        fake_getresponse)

        ref = self.client.do_request(method='POST', action='www.com',
                                     body='body1', headers=None,
                                     params=dict(param1='abc'))

        self.assertEquals('test-result', ref)

    @attr(kind='small')
    def test_do_request_exception_notenant(self):
        """Test for nova.network.quantum.client.Client.do_request"""
        def fake_request(self, method, url, body=None, headers={}):
            pass

        self.stubs.Set(httplib.HTTPConnection, 'request', fake_request)

        self.assertRaises(Exception,
                self.client.do_request, method='GET', action='www.com',
                                     body=None, headers=None, params=None)

    @attr(kind='small')
    def test_do_request_exception_status(self):
        """Test for nova.network.quantum.client.Client.do_request"""
        self.client = client.Client(tenant='1')

        def fake_request(self, method, url, body=None, headers={}):
            pass

        self.stubs.Set(httplib.HTTPConnection, 'request', fake_request)

        class DumyResponse(object):
            def __init__(self):
                self.status = 500

            def read(self):
                pass

        def fake_getresponse(con):
            return DumyResponse()

        self.stubs.Set(httplib.HTTPConnection, 'getresponse', fake_getresponse)

        self.assertRaises(client.QuantumServerException,
                self.client.do_request, method='GET', action='www.com',
                                     body=None, headers=None, params=None)

    @attr(kind='small')
    def test_do_request_exception_notfound(self):
        """Test for nova.network.quantum.client.Client.do_request"""
        self.client = client.Client(tenant='1')

        def fake_request(self, method, url, body=None, headers={}):
            pass

        self.stubs.Set(httplib.HTTPConnection, 'request', fake_request)

        class DumyResponse(object):
            def __init__(self):
                self.status = 404

            def read(self):
                pass

        def fake_getresponse(con):
            return DumyResponse()

        self.stubs.Set(httplib.HTTPConnection, 'getresponse', fake_getresponse)

        self.assertRaises(client.QuantumNotFoundException,
                self.client.do_request, method='GET', action='www.com',
                                     body=None, headers=None, params=None)

    @attr(kind='small')
    def test_do_request_exception_io(self):
        """Test for nova.network.quantum.client.Client.do_request"""
        self.client = client.Client(tenant='1')

        def fake_request(self, method, url, body=None, headers={}):
            raise IOError

        self.stubs.Set(httplib.HTTPConnection, 'request', fake_request)

        self.assertRaises(client.QuantumIOException,
                self.client.do_request, method='GET', action='www.com',
                                     body=None, headers=None, params=None)

    @attr(kind='small')
    def test_get_status_code_parameter(self):
        """Test for nova.network.quantum.client.Client.get_status_code"""

        class DumyResponse(object):
            def __init__(self):
                self.status = 404
                self.status_int = 200

        ref = self.client.get_status_code(response=DumyResponse())
        self.assertEqual(200, ref)

    @attr(kind='small')
    def test_serialize(self):
        """Test for nova.network.quantum.client.Client.serialize"""
        ref = self.client.serialize(data=dict(key1='abc'))
        self.assertEqual('{"key1": "abc"}', ref)

    @attr(kind='small')
    def test_serialize_parameter(self):
        """Test for nova.network.quantum.client.Client.serialize"""
        ref = self.client.serialize(data=None)
        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_serialize_exception(self):
        """Test for nova.network.quantum.client.Client.serialize"""
        self.assertRaises(Exception,
            self.client.serialize, data='test-string')

    @attr(kind='small')
    def test_deserialize(self):
        """Test for nova.network.quantum.client.Client.deserialize"""
        ref = self.client.deserialize(data='{"key1": "abc"}',
                                      status_code=None)
        self.assertEqual(dict(key1='abc'), ref)

    @test.skip_test('has no status_code parameter checking in this release')
    @attr(kind='small')
    def test_deserialize_parameter(self):
        """Test for nova.network.quantum.client.Client.deserialize"""
        ref = self.client.deserialize(data='test-string', status_code=202)
        self.assertEqual('test-string', ref)

    @attr(kind='small')
    def test_content_type(self):
        """Test for nova.network.quantum.client.Client.content_type"""
        ref = self.client.content_type(format=None)
        self.assertEqual('application/xml', ref)

    @attr(kind='small')
    def test_content_type_parameter(self):
        """Test for nova.network.quantum.client.Client.content_type"""
        ref = self.client.content_type(format='stream')
        self.assertEqual('application/stream', ref)

    @attr(kind='small')
    def test_list_networks(self):
        """Test for nova.network.quantum.client.Client.list_networks"""
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):
            return 'SUCCESS'

        self.stubs.Set(self.client, 'do_request', fake_do_request)

        ref = self.client.list_networks()
        self.assertEqual('SUCCESS', ref)

    @attr(kind='small')
    def test_show_network_details(self):
        """Test for nova.network.quantum.client.Client.show_network_details"""
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):
            return 'SUCCESS'

        self.stubs.Set(self.client, 'do_request', fake_do_request)

        ref = self.client.show_network_details('1.1.1.1', tenant='1')
        self.assertEqual('SUCCESS', ref)

    @attr(kind='small')
    def test_create_network(self):
        """Test for nova.network.quantum.client.Client.create_network"""
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):
            return 'SUCCESS'

        self.stubs.Set(self.client, 'do_request', fake_do_request)

        ref = self.client.create_network(body='test-string')
        self.assertEqual('SUCCESS', ref)

    @attr(kind='small')
    def test_update_network(self):
        """Test for nova.network.quantum.client.Client.update_network"""
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):
            return 'SUCCESS'

        self.stubs.Set(self.client, 'do_request', fake_do_request)

        ref = self.client.update_network('1.1.1.1', body=None)
        self.assertEqual('SUCCESS', ref)

    @attr(kind='small')
    def test_delete_network(self):
        """Test for nova.network.quantum.client.Client.delete_network"""
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):
            return 'SUCCESS'

        self.stubs.Set(self.client, 'do_request', fake_do_request)

        kwargs = dict(format='test-format')
        ref = self.client.delete_network('1.1.1.1', **kwargs)
        self.assertEqual('SUCCESS', ref)

    @attr(kind='small')
    def test_list_ports(self):
        """Test for nova.network.quantum.client.Client.list_ports"""
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):
            return 'SUCCESS'

        self.stubs.Set(self.client, 'do_request', fake_do_request)

        ref = self.client.list_ports('1.1.1.1')
        self.assertEqual('SUCCESS', ref)

    @attr(kind='small')
    def test_show_port_details(self):
        """Test for nova.network.quantum.client.Client.show_port_details"""
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):
            return 'SUCCESS'

        self.stubs.Set(self.client, 'do_request', fake_do_request)

        ref = self.client.show_port_details('1.1.1.1', 9898)
        self.assertEqual('SUCCESS', ref)

    @attr(kind='small')
    def test_create_port(self):
        """Test for nova.network.quantum.client.Client.create_port"""
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):
            return 'SUCCESS'

        self.stubs.Set(self.client, 'do_request', fake_do_request)

        ref = self.client.create_port('1.1.1.1')
        self.assertEqual('SUCCESS', ref)

    @attr(kind='small')
    def test_delete_port(self):
        """Test for nova.network.quantum.client.Client.delete_port"""
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):
            return 'SUCCESS'

        self.stubs.Set(self.client, 'do_request', fake_do_request)

        ref = self.client.delete_port('1.1.1.1', '9898')
        self.assertEqual('SUCCESS', ref)

    @attr(kind='small')
    def test_set_port_state(self):
        """Test for nova.network.quantum.client.Client.set_port_state"""
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):
            return 'SUCCESS'

        self.stubs.Set(self.client, 'do_request', fake_do_request)

        ref = self.client.set_port_state('1.1.1.1', '9898')
        self.assertEqual('SUCCESS', ref)

    @attr(kind='small')
    def test_show_port_attachment(self):
        """Test for nova.network.quantum.client.Client.show_port_attachment"""
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):
            return 'SUCCESS'

        self.stubs.Set(self.client, 'do_request', fake_do_request)

        ref = self.client.show_port_attachment('1.1.1.1', 9898)
        self.assertEqual('SUCCESS', ref)

    @attr(kind='small')
    def test_attach_resource(self):
        """Test for nova.network.quantum.client.Client.attach_resource"""
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):
            return 'SUCCESS'

        self.stubs.Set(self.client, 'do_request', fake_do_request)

        ref = self.client.attach_resource('1.1.1.1', 9898)
        self.assertEqual('SUCCESS', ref)

    @attr(kind='small')
    def test_detach_resource(self):
        """Test for nova.network.quantum.client.Client.detach_resource"""
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):
            return 'SUCCESS'

        self.stubs.Set(self.client, 'do_request', fake_do_request)

        ref = self.client.detach_resource('1.1.1.1', 9898)
        self.assertEqual('SUCCESS', ref)
