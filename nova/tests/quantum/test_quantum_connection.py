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
Tests For nova.network.quantum.quantum_connection
"""

from nova import exception
from nova import flags
from nova import log as logging
from nova import test
from nose.plugins.attrib import attr
from nova.network.quantum import quantum_connection
from nova.network.quantum import client


class QuantumClientConnectionTestCase(test.TestCase):
    """Test for quantum.quantum_connection.QuantumClientConnection. """
    def setUp(self):
        super(QuantumClientConnectionTestCase, self).setUp()
        self.quantumclientconnection =\
            quantum_connection.QuantumClientConnection()

    @attr(kind='small')
    def test_create_network(self):
        """Test for nova.network.quantum.quantum_connection.
        QuantumClientConnection.create_network. """
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):
            return dict(network={'id': 1})

        self.stubs.Set(self.quantumclientconnection.client,
                       'do_request', fake_do_request)

        ref = self.quantumclientconnection.create_network(tenant_id=1,
                                    network_name='test_network_name')

        self.assertEqual(1, ref)

    @attr(kind='small')
    def test_delete_network(self):
        """Test for nova.network.quantum.quantum_connection.
        QuantumClientConnection.delete_network. """
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):
            return '200 OK'

        self.stubs.Set(self.quantumclientconnection.client,
                       'do_request', fake_do_request)

        ref = self.quantumclientconnection.delete_network(tenant_id=1,
                                                    net_id='99.99.99.99')

        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_network_exists(self):
        """Test for nova.network.quantum.quantum_connection.
        QuantumClientConnection.network_exists. """
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):
            return True

        self.stubs.Set(self.quantumclientconnection.client,
                       'do_request', fake_do_request)

        ref = self.quantumclientconnection.network_exists(tenant_id=1,
                                                net_id='99.99.99.99')

        self.assertEqual(True, ref)

    @attr(kind='small')
    def test_network_exists_exception(self):
        """Test for nova.network.quantum.quantum_connection.
        QuantumClientConnection.network_exists. """
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):
            raise client.QuantumNotFoundException

        self.stubs.Set(self.quantumclientconnection.client,
                       'do_request', fake_do_request)

        ref = self.quantumclientconnection.network_exists(tenant_id=1,
                                                net_id='99.99.99.99')

        self.assertEqual(False, ref)

    @attr(kind='small')
    def test_create_and_attach_port(self):
        """Test for nova.network.quantum.quantum_connection.
        QuantumClientConnection.create_and_attach_port. """
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):
            return dict(port={'id': 1})

        self.stubs.Set(self.quantumclientconnection.client,
                       'do_request', fake_do_request)

        ref = self.quantumclientconnection.create_and_attach_port(
                                    tenant_id=1, net_id='127.0.0.1',
                                    interface_id=1)

        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_detach_and_delete_port(self):
        """Test for nova.network.quantum.quantum_connection.
        QuantumClientConnection.detach_and_delete_port. """
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):
            return dict(port={'id': 1})

        self.stubs.Set(self.quantumclientconnection.client,
                       'do_request', fake_do_request)

        ref = self.quantumclientconnection.detach_and_delete_port(
                                    tenant_id='1', net_id='1', port_id='1')

        self.assertEqual(None, ref)

    def test_get_port_by_attachment(self):
        """Test for nova.network.quantum.quantum_connection.
        QuantumClientConnection.get_port_by_attachment. """
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):

            if action.find('attachment') >= 0:
                return dict(attachment={'id': 2})
            elif action.find('port') >= 0:
                return dict(ports=[{'id': 'port_id'}])

            return dict(networks=[{'id': 'network_id'}])

        self.stubs.Set(self.quantumclientconnection.client,
                       'do_request', fake_do_request)

        ref = self.quantumclientconnection.get_port_by_attachment(
                                        tenant_id=1, attachment_id=2)

        self.assertEqual('network_id', ref[0])
        self.assertEqual('port_id', ref[1])

    def test_get_port_by_attachment_parameter(self):
        """Test for nova.network.quantum.quantum_connection.
        QuantumClientConnection.get_port_by_attachment. """
        def fake_do_request(method, action, body=None,
                   headers=None, params=None):

            if action.find('attachment') >= 0:
                return dict(attachment={'id': 2})
            elif action.find('port') >= 0:
                return dict(ports=[{'id': 'port_id'}])

            return dict(networks=[{'id': 'network_id'}])

        self.stubs.Set(self.quantumclientconnection.client,
                       'do_request', fake_do_request)

        ref = self.quantumclientconnection.get_port_by_attachment(
                                        tenant_id=1, attachment_id=99)

        self.assertEqual(None, ref[0])
        self.assertEqual(None, ref[1])
