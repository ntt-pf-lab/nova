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
Tests For nova.network.quantum.melange_connection
"""

from nova import exception
from nova import flags
from nova import log as logging
from nova import test
from nova import utils
from nose.plugins.attrib import attr
from nova.network import quantum
from nova.network.quantum import melange_connection
import httplib


class MelangeConnectionTestCase(test.TestCase):
    """Test for nova.network.quantum.melange_connection.MelangeConnection"""
    def setUp(self):
        super(MelangeConnectionTestCase, self).setUp()
        self.melangeconnection = melange_connection.MelangeConnection()

    @attr(kind='small')
    def test_get(self):
        """Test for nova.network.quantum.melange_connection.
        MelangeConnection.get"""
        def fake_do_request(method, path, body=None,
                            headers=None, params=None):
            self.assertEqual('GET', method)
            return '200'

        self.stubs.Set(self.melangeconnection, 'do_request', fake_do_request)

        ref = self.melangeconnection.get(path='www.com',
                                         params=None, headers=None)

        self.assertEqual('200', ref)

    @attr(kind='small')
    def test_post(self):
        """Test for nova.network.quantum.melange_connection.
        MelangeConnection.post"""
        def fake_do_request(method, path, body=None,
                            headers=None, params=None):
            self.assertEqual('POST', method)
            return '200'

        self.stubs.Set(self.melangeconnection, 'do_request', fake_do_request)

        ref = self.melangeconnection.post(path='www.com',
                                          body=None, headers=None)
        self.assertEqual('200', ref)

    @attr(kind='small')
    def test_delete(self):
        """Test for nova.network.quantum.melange_connection.
        MelangeConnection.delete"""
        def fake_do_request(method, path, body=None,
                            headers=None, params=None):
            self.assertEqual('DELETE', method)
            return '200'

        self.stubs.Set(self.melangeconnection, 'do_request', fake_do_request)

        ref = self.melangeconnection.delete(path='www.com', headers=None)
        self.assertEqual('200', ref)

    @attr(kind='small')
    def test_get_connection(self):
        """Test for nova.network.quantum.melange_connection.
        MelangeConnection._get_connection."""

        ref = self.melangeconnection._get_connection()
        self.assertEqual(True, isinstance(ref, httplib.HTTPConnection))

        self.melangeconnection.use_ssl = True
        ref = self.melangeconnection._get_connection()
        self.assertEqual(True, isinstance(ref, httplib.HTTPSConnection))

    @attr(kind='small')
    def test_do_request(self):
        """Test for nova.network.quantum.melange_connection.
        MelangeConnection.do_request"""
        def fake_request(con, method, path, body=None,
                            headers=None, params=None):
            self.assertEqual('TEST_METHOD', method)

        self.stubs.Set(httplib.HTTPConnection, 'request', fake_request)

        class fake_httpresponse(object):
            def __init__(self):
                self.status = 200

            def read(self):
                return 'SUCCESS'

        def fake_getresponse(self):
            return  fake_httpresponse()

        self.stubs.Set(httplib.HTTPConnection, 'getresponse', fake_getresponse)

        ref = self.melangeconnection.do_request(
                method='TEST_METHOD', path='www.com',
                body=None, headers=None, params=None)

        self.assertEqual('SUCCESS', ref)

    @attr(kind='small')
    def test_do_request_parameter(self):
        """Test for nova.network.quantum.melange_connection.
        MelangeConnection.do_request"""
        def fake_request(con, method, path, body=None,
                            headers=None, params=None):
            self.assertEqual('TEST_METHOD', method)
            self.assertEqual(True, path.find('parameter1=1') > 0)

        self.stubs.Set(httplib.HTTPConnection, 'request', fake_request)

        class fake_httpresponse(object):
            def __init__(self):
                self.status = 200

            def read(self):
                return 'SUCCESS'

        def fake_getresponse(self):
            return  fake_httpresponse()

        self.stubs.Set(httplib.HTTPConnection, 'getresponse', fake_getresponse)

        ref = self.melangeconnection.do_request(
                method='TEST_METHOD', path='www.com',
                body=None, headers=None, params={'parameter1': 1})

        self.assertEqual('SUCCESS', ref)

    @attr(kind='small')
    def test_do_request_exception_status(self):
        """Test for nova.network.quantum.melange_connection.
        MelangeConnection.do_request"""
        def fake_request(con, method, path, body=None,
                            headers=None, params=None):
            self.assertEqual('TEST_METHOD', method)
            self.assertEqual(True, path.find('parameter1=1') > 0)

        self.stubs.Set(httplib.HTTPConnection, 'request', fake_request)

        class fake_httpresponse(object):
            def __init__(self):
                self.status = 500

            def read(self):
                return 'SUCCESS'

        def fake_getresponse(self):
            return  fake_httpresponse()

        self.stubs.Set(httplib.HTTPConnection, 'getresponse', fake_getresponse)

        self.assertRaises(Exception,
            self.melangeconnection.do_request,
                method='TEST_METHOD', path='www.com',
                body=None, headers=None, params={'parameter1': 1})

    @attr(kind='small')
    def test_do_request_exception_io(self):
        """Test for nova.network.quantum.melange_connection.
        MelangeConnection.do_request"""
        def fake_request(con, method, path, body=None,
                            headers=None, params=None):
            self.assertEqual('TEST_METHOD', method)
            self.assertEqual(True, path.find('parameter1=1') > 0)

        self.stubs.Set(httplib.HTTPConnection, 'request', fake_request)

        class fake_httpresponse(object):
            def __init__(self):
                self.status = 500

            def read(self):
                raise IOError

        def fake_getresponse(self):
            return  fake_httpresponse()

        self.stubs.Set(httplib.HTTPConnection, 'getresponse', fake_getresponse)

        self.assertRaises(Exception,
            self.melangeconnection.do_request,
                method='TEST_METHOD', path='www.com',
                body=None, headers=None, params={'parameter1': 1})

    @attr(kind='small')
    def test_allocate_ip(self):
        """Test for nova.network.quantum.melange_connection.
        MelangeConnection.allocate_ip"""
        def fake_do_request(method, path, body=None,
                            headers=None, params=None):
            self.assertEqual('POST', method)
            return utils.dumps(dict(ip_addresses='1.1.1.1'))

        self.stubs.Set(self.melangeconnection, 'do_request', fake_do_request)

        ref = self.melangeconnection.allocate_ip(
                network_id=1, vif_id=2, project_id=None, mac_address=None)

        self.assertEqual('1.1.1.1', ref)

    @attr(kind='small')
    def test_create_block(self):
        """Test for nova.network.quantum.melange_connection.
        MelangeConnection.create_block"""
        def fake_do_request(method, path, body=None,
                            headers=None, params=None):
            self.assertEqual('POST', method)
            return utils.dumps(dict(ip_addresses='1.1.1.1'))

        self.stubs.Set(self.melangeconnection, 'do_request', fake_do_request)

        ref = self.melangeconnection.create_block(
                network_id=1, cidr=2, project_id=None, dns1=None, dns2=None)

        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_delete_block(self):
        """Test for nova.network.quantum.melange_connection.
        MelangeConnection.delete_block"""
        def fake_do_request(method, path, body=None,
                            headers=None, params=None):
            self.assertEqual('DELETE', method)

        self.stubs.Set(self.melangeconnection, 'do_request', fake_do_request)

        ref = self.melangeconnection.delete_block(
                                        block_id=1, project_id=None)
        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_get_blocks(self):
        """Test for nova.network.quantum.melange_connection.
        MelangeConnection.get_blocks"""
        def fake_do_request(method, path, body=None,
                            headers=None, params=None):
            self.assertEqual('GET', method)
            return utils.dumps(dict(ip_addresses='1.1.1.1'))

        self.stubs.Set(self.melangeconnection, 'do_request', fake_do_request)

        ref = self.melangeconnection.get_blocks(project_id=None)
        self.assertEqual(dict(ip_addresses='1.1.1.1'), ref)

    @attr(kind='small')
    def test_get_allocated_ips(self):
        """Test for nova.network.quantum.melange_connection.
        MelangeConnection.get_allocated_ips"""
        def fake_do_request(method, path, body=None,
                            headers=None, params=None):
            self.assertEqual('GET', method)
            return utils.dumps(dict(ip_addresses='1.1.1.1'))

        self.stubs.Set(self.melangeconnection, 'do_request', fake_do_request)

        ref = self.melangeconnection.get_allocated_ips(
                            network_id=1, vif_id=1, project_id=None)
        self.assertEqual('1.1.1.1', ref)

    @attr(kind='small')
    def test_deallocate_ips(self):
        """Test for nova.network.quantum.melange_connection.
        MelangeConnection.deallocate_ips"""
        def fake_do_request(method, path, body=None,
                            headers=None, params=None):
            self.assertEqual('DELETE', method)
            return utils.dumps(dict(ip_addresses='1.1.1.1'))

        self.stubs.Set(self.melangeconnection, 'do_request', fake_do_request)

        ref = self.melangeconnection.deallocate_ips(
                        network_id=1, vif_id=1, project_id=None)
        self.assertEqual(None, ref)
