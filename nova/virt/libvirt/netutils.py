# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# Copyright (c) 2010 Citrix Systems, Inc.
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


"""Network-releated utilities for supporting libvirt connection code."""


import netaddr
from netaddr.core import AddrFormatError

from nova import flags
from nova import exception


FLAGS = flags.FLAGS


def get_net_and_mask(cidr):
    try:
        net = netaddr.IPNetwork(cidr)
    except (UnboundLocalError, AddrFormatError):
        raise exception.InvalidCidr(cidr=cidr)
    return str(net.ip), str(net.netmask)


def get_net_and_prefixlen(cidr):
    try:
        net = netaddr.IPNetwork(cidr)
    except (UnboundLocalError, AddrFormatError):
        raise exception.InvalidCidr(cidr=cidr)
    return str(net.ip), str(net._prefixlen)


def get_ip_version(cidr):
    try:
        net = netaddr.IPNetwork(cidr)
    except (UnboundLocalError, AddrFormatError):
        raise exception.InvalidCidr(cidr=cidr)
    return int(net.version)
