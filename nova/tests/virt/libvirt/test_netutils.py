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
Tests For nova.virt.libvirt.netutils
"""

from nova import test
from nova import exception
from nose.plugins.attrib import attr
from nova.virt.libvirt import netutils


class NetutilsTestCase(test.TestCase):
    """Test for nova.virt.libvirt.netutils. """
    def setUp(self):
        super(NetutilsTestCase, self).setUp()

    @attr(kind='small')
    def test_get_net_and_mask(self):
        """Test for nova.virt.libvirt.netutils.get_net_and_mask.
        Make sure return address and mask"""

        cidr = '192.168.0.0/32'
        ref = netutils.get_net_and_mask(cidr)

        self.assertEqual('192.168.0.0', ref[0])
        self.assertEqual('255.255.255.255', ref[1])

    @attr(kind='small')
    def test_get_net_and_mask_parameter(self):
        """Test for nova.virt.libvirt.netutils.get_net_and_mask.
        Verify input of ip/mask type """

        cidr = '192.168.0.0/255.255.255.0'
        ref = netutils.get_net_and_mask(cidr)

        self.assertEqual('192.168.0.0', ref[0])
        self.assertEqual('255.255.255.0', ref[1])

    def test_get_net_and_mask_parameter_without_prefix(self):
        """Test for nova.virt.libvirt.netutils.get_net_and_mask.
        Return 255.255.255.255 without prefix inputed"""

        cidr = '192.168.0.0'
        ref = netutils.get_net_and_mask(cidr)

        self.assertEqual('192.168.0.0', ref[0])
        self.assertEqual('255.255.255.255', ref[1])

    def test_get_net_and_mask_exception_without_ip(self):
        """Test for nova.virt.libvirt.netutils.get_net_and_mask.
        Raise InvalidCidr without ip inputed"""

        cidr = '/32'
        self.assertRaises(exception.InvalidCidr,
            netutils.get_net_and_mask, cidr)

    @attr(kind='small')
    def test_get_net_and_mask_exception_prefix(self):
        """Test for nova.virt.libvirt.netutils.get_net_and_mask.
        Raise InvalidCidr if prefix is over 32 for ipv4"""

        cidr = '192.168.0.0/33'
        self.assertRaises(exception.InvalidCidr,
            netutils.get_net_and_mask, cidr)

    @attr(kind='small')
    def test_get_net_and_prefixlen(self):
        """Test for nova.virt.libvirt.netutils.get_net_and_prefixlen.
        Make sure return address and prefix length"""

        cidr = '192.168.0.0/11'
        ref = netutils.get_net_and_prefixlen(cidr)

        self.assertEqual('192.168.0.0', ref[0])
        self.assertEqual('11', ref[1])

    @attr(kind='small')
    def test_get_net_and_prefixlen_parameter(self):
        """Test for nova.virt.libvirt.netutils.get_net_and_prefixlen.
        Prefix is 32 if no inputed"""

        cidr = '192.168.0.0'
        ref = netutils.get_net_and_prefixlen(cidr)

        self.assertEqual('192.168.0.0', ref[0])
        self.assertEqual('32', ref[1])

    @attr(kind='small')
    def test_get_net_and_prefixlen_parameter_mask(self):
        """Test for nova.virt.libvirt.netutils.get_net_and_prefixlen.
        Verify mask input type"""

        cidr = '192.168.0.0/255.255.0.0'
        ref = netutils.get_net_and_prefixlen(cidr)

        self.assertEqual('192.168.0.0', ref[0])
        self.assertEqual('16', ref[1])

    @attr(kind='small')
    def test_get_net_and_prefixlen_exception(self):
        """Test for nova.virt.libvirt.netutils.get_net_and_prefixlen.
        Raise InvalidCidr if prefix is over 32 for ipv4"""

        cidr = '192.168.0.0/33'
        self.assertRaises(exception.InvalidCidr,
            netutils.get_net_and_prefixlen, cidr)

    @attr(kind='small')
    def test_get_net_and_prefixlen_exception_invalid(self):
        """Test for nova.virt.libvirt.netutils.get_net_and_prefixlen.
        Raise InvalidCidr for invalid input"""

        cidr = 'aaa'
        self.assertRaises(exception.InvalidCidr,
            netutils.get_net_and_prefixlen, cidr)

    @attr(kind='small')
    def test_get_ip_version(self):
        """Test for nova.virt.libvirt.netutils.get_ip_version.
        Make sure return version of protocol"""

        cidr = '192.168.0.0/8'
        ref = netutils.get_ip_version(cidr)

        self.assertEqual(4, ref)

    @attr(kind='small')
    def test_get_ip_version_parameter(self):
        """Test for nova.virt.libvirt.netutils.get_ip_version.
        Verify return ipv6 version"""

        cidr = '192:168::/64'
        ref = netutils.get_ip_version(cidr)

        self.assertEqual(6, ref)

    @attr(kind='small')
    def test_get_ip_version_exception(self):
        """Test for nova.virt.libvirt.netutils.get_ip_version.
        Raise InvalidCidr for invalid input"""

        cidr = '192:168:0:0/64'
        self.assertRaises(exception.InvalidCidr,
            netutils.get_ip_version, cidr)
