# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
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
Tests For nova.virt.connection
"""

from nose.plugins.attrib import attr
from nova import exception
from nova import flags
from nova import log as logging
from nova import test
from nova import virt
from nova.virt import connection
from nova.virt.libvirt.connection import LibvirtConnection
from nova.virt import xenapi_conn
from nova.virt import hyperv
from nova.virt import vmwareapi_conn


class ConnectionTestCase(test.TestCase):
    """Test for nova.virt.connection"""
    def setUp(self):
        super(ConnectionTestCase, self).setUp()
        self.connection = connection

    @attr(kind='small')
    def test_get_connection(self):
        """Test for nova.virt.connection.get_connection"""
        ref = self.connection.get_connection(read_only=False)

        self.assertEqual(True, isinstance(ref, virt.fake.FakeConnection))

    @attr(kind='small')
    def test_get_connection_configuration_libvirt(self):
        """Test for nova.virt.connection.get_connection"""
        self.flags(connection_type='libvirt')

        virt.libvirt.connection.libvirt = 'FakeLibvirt'
        virt.libvirt.connection.libxml2 = 'FakeLibxml2'

        ref = self.connection.get_connection(read_only=False)

        self.assertEqual(True, isinstance(ref, LibvirtConnection))

    @attr(kind='small')
    def test_get_connection_configuration_xenapi(self):
        """Test for nova.virt.connection.get_connection"""
        self.flags(connection_type='xenapi')
        self.flags(xenapi_connection_url='fake_url')
        self.flags(xenapi_connection_password='fake_password')

        def fake_init(self, url, user, pw):
            pass

        self.stubs.Set(self.connection.xenapi_conn.XenAPISession,
                       '__init__', fake_init)

        def fake_vol_init(self, session):
            pass

        self.stubs.Set(self.connection.xenapi_conn.VolumeOps,
                       '__init__', fake_vol_init)

        def fake_vop_init(self, session):
            pass

        self.stubs.Set(self.connection.xenapi_conn.VMOps,
                       '__init__', fake_vop_init)

        ref = self.connection.get_connection(read_only=False)

        self.assertEqual(True, isinstance(ref, xenapi_conn.XenAPIConnection))

    @attr(kind='small')
    def test_get_connection_configuration_hyperv(self):
        """Test for nova.virt.connection.get_connection"""
        self.flags(connection_type='hyperv')

        def fake_init(self):
            pass

        self.stubs.Set(self.connection.hyperv.HyperVConnection,
                       '__init__', fake_init)

        hyperv.wmi = 'Fakewmi'

        ref = self.connection.get_connection(read_only=False)

        self.assertEqual(True, isinstance(ref, hyperv.HyperVConnection))

    @attr(kind='small')
    def test_get_connection_configuration_vmwareapi(self):
        """Test for nova.virt.connection.get_connection"""
        self.flags(connection_type='vmwareapi')
        self.flags(vmwareapi_host_ip='fakeip')
        self.flags(vmwareapi_host_username='fakeuser')
        self.flags(vmwareapi_host_password='fakepassword')

        def fake_init(self, host_ip, host_username, host_password,
                                        api_retry_count, scheme="https"):
            pass

        self.stubs.Set(self.connection.vmwareapi_conn.VMWareESXConnection,
                       '__init__', fake_init)

        ref = self.connection.get_connection(read_only=False)

        self.assertEqual(True,
                         isinstance(ref, vmwareapi_conn.VMWareESXConnection))

    @attr(kind='small')
    def test_get_connection_exception_none(self):
        """Test for nova.virt.connection.get_connection"""
        self.flags(connection_type='vmwareapi')
        self.flags(vmwareapi_host_ip='fakeip')
        self.flags(vmwareapi_host_username='fakeuser')
        self.flags(vmwareapi_host_password='fakepassword')

        def fake_get_connection(read_only):
            return None

        self.stubs.Set(self.connection.vmwareapi_conn,
                       'get_connection', fake_get_connection)

        self.assertRaises(SystemExit,
                          self.connection.get_connection, read_only=False)

    @attr(kind='small')
    def test_get_connection_exception(self):
        """Test for nova.virt.connection.get_connection"""
        self.flags(connection_type='not_exist')
        self.assertRaises(Exception,
            self.connection.get_connection, read_only=False)
