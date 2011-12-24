# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2010 OpenStack LLC
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

import copy
import eventlet
import mox
import os
import re
import shutil
import sys
import tempfile

from xml.etree.ElementTree import fromstring as xml_to_tree
from xml.dom.minidom import parseString as xml_to_dom

from nova import context
from nova import db
from nova import exception
from nova import flags
from nova import test
from nova import utils
from nova.api.ec2 import cloud
from nova.compute import power_state
from nova.compute import vm_states
from nova.virt.libvirt import connection
from nova.virt.libvirt import firewall

import shutil
import os
import multiprocessing
import sys

from eventlet import greenthread
from eventlet import event

from nose.plugins.attrib import attr
from nova.compute import instance_types
from nova.auth import manager
from nova import network
from nova import image
from nova import virt

libvirt = None
FLAGS = flags.FLAGS


def _concurrency(wait, done, target):
    wait.wait()
    done.send()


class FakeVirDomainSnapshot(object):

    def __init__(self, dom=None):
        self.dom = dom

    def delete(self, flags):
        pass


class FakeVirtDomain(object):

    def __init__(self, fake_xml=None):
        if fake_xml:
            self._fake_dom_xml = fake_xml
        else:
            self._fake_dom_xml = """
                <domain type='kvm'>
                    <devices>
                        <disk type='file'>
                            <source file='filename'/>
                        </disk>
                    </devices>
                </domain>
            """

    def snapshotCreateXML(self, *args):
        return FakeVirDomainSnapshot(self)

    def createWithFlags(self, launch_flags):
        pass

    def XMLDesc(self, *args):
        return self._fake_dom_xml


def _create_network_info(count=1, ipv6=None):
    if ipv6 is None:
        ipv6 = FLAGS.use_ipv6
    fake = 'fake'
    fake_ip = '10.11.12.13'
    fake_ip_2 = '0.0.0.1'
    fake_ip_3 = '0.0.0.1'
    fake_vlan = 100
    fake_bridge_interface = 'eth0'
    network = {'bridge': fake,
               'cidr': fake_ip,
               'cidr_v6': fake_ip,
               'gateway_v6': fake,
               'vlan': fake_vlan,
               'bridge_interface': fake_bridge_interface}
    mapping = {'mac': fake,
               'dhcp_server': '10.0.0.1',
               'gateway': fake,
               'gateway6': fake,
               'ips': [{'ip': fake_ip}, {'ip': fake_ip}]}
    if ipv6:
        mapping['ip6s'] = [{'ip': fake_ip},
                           {'ip': fake_ip_2},
                           {'ip': fake_ip_3}]
    return [(network, mapping) for x in xrange(0, count)]


def _setup_networking(instance_id, ip='1.2.3.4', mac='56:12:12:12:12:12'):
    ctxt = context.get_admin_context()
    network_ref = db.project_get_networks(ctxt,
                                           'fake',
                                           associate=True)[0]
    vif = {'address': mac,
           'network_id': network_ref['id'],
           'instance_id': instance_id}
    vif_ref = db.virtual_interface_create(ctxt, vif)

    fixed_ip = {'address': ip,
                'network_id': network_ref['id'],
                'virtual_interface_id': vif_ref['id']}
    db.fixed_ip_create(ctxt, fixed_ip)
    db.fixed_ip_update(ctxt, ip, {'allocated': True,
                                  'instance_id': instance_id})


class CacheConcurrencyTestCase(test.TestCase):
    def setUp(self):
        super(CacheConcurrencyTestCase, self).setUp()
        self.flags(instances_path='nova.compute.manager')

        def fake_exists(fname):
            basedir = os.path.join(FLAGS.instances_path, '_base')
            if fname == basedir:
                return True
            return False

        def fake_execute(*args, **kwargs):
            pass

        self.stubs.Set(os.path, 'exists', fake_exists)
        self.stubs.Set(utils, 'execute', fake_execute)

    def test_same_fname_concurrency(self):
        """Ensures that the same fname cache runs at a sequentially"""
        conn = connection.LibvirtConnection
        wait1 = eventlet.event.Event()
        done1 = eventlet.event.Event()
        eventlet.spawn(conn._cache_image, _concurrency,
                       'target', 'fname', False, wait1, done1)
        wait2 = eventlet.event.Event()
        done2 = eventlet.event.Event()
        eventlet.spawn(conn._cache_image, _concurrency,
                       'target', 'fname', False, wait2, done2)
        wait2.send()
        eventlet.sleep(0)
        try:
            self.assertFalse(done2.ready())
        finally:
            wait1.send()
        done1.wait()
        eventlet.sleep(0)
        self.assertTrue(done2.ready())

    def test_different_fname_concurrency(self):
        """Ensures that two different fname caches are concurrent"""
        conn = connection.LibvirtConnection
        wait1 = eventlet.event.Event()
        done1 = eventlet.event.Event()
        eventlet.spawn(conn._cache_image, _concurrency,
                       'target', 'fname2', False, wait1, done1)
        wait2 = eventlet.event.Event()
        done2 = eventlet.event.Event()
        eventlet.spawn(conn._cache_image, _concurrency,
                       'target', 'fname1', False, wait2, done2)
        wait2.send()
        eventlet.sleep(0)
        try:
            self.assertTrue(done2.ready())
        finally:
            wait1.send()
            eventlet.sleep(0)


class LibvirtConnTestCase(test.TestCase):

    def setUp(self):
        super(LibvirtConnTestCase, self).setUp()
        connection._late_load_cheetah()
        self.flags(fake_call=True)
        self.user_id = 'fake'
        self.project_id = 'fake'
        self.context = context.RequestContext(self.user_id, self.project_id)
        self.network = utils.import_object(FLAGS.network_manager)
        self.context = context.get_admin_context()
        self.flags(instances_path='')
        self.call_libvirt_dependant_setup = False
        self.test_ip = '10.11.12.13'

    test_instance = {'memory_kb': '1024000',
                     'basepath': '/some/path',
                     'bridge_name': 'br100',
                     'vcpus': 2,
                     'project_id': 'fake',
                     'bridge': 'br101',
                     'image_ref': '123456',
                     'local_gb': 20,
                     'instance_type_id': '5'}  # m1.small

    def lazy_load_library_exists(self):
        """check if libvirt is available."""
        # try to connect libvirt. if fail, skip test.
        try:
            import libvirt
            import libxml2
        except ImportError:
            return False
        global libvirt
        libvirt = __import__('libvirt')
        connection.libvirt = __import__('libvirt')
        connection.libxml2 = __import__('libxml2')
        return True

    def create_fake_libvirt_mock(self, **kwargs):
        """Defining mocks for LibvirtConnection(libvirt is not used)."""

        # A fake libvirt.virConnect
        class FakeLibvirtConnection(object):
            def defineXML(self, xml):
                return FakeVirtDomain()

        # A fake connection.IptablesFirewallDriver
        class FakeIptablesFirewallDriver(object):

            def __init__(self, **kwargs):
                pass

            def setattr(self, key, val):
                self.__setattr__(key, val)

        # A fake VIF driver
        class FakeVIFDriver(object):

            def __init__(self, **kwargs):
                pass

            def setattr(self, key, val):
                self.__setattr__(key, val)

            def plug(self, instance, network, mapping):
                return {
                    'id': 'fake',
                    'bridge_name': 'fake',
                    'mac_address': 'fake',
                    'ip_address': 'fake',
                    'dhcp_server': 'fake',
                    'extra_params': 'fake',
                }

        # Creating mocks
        fake = FakeLibvirtConnection()
        fakeip = FakeIptablesFirewallDriver
        fakevif = FakeVIFDriver()
        # Customizing above fake if necessary
        for key, val in kwargs.items():
            fake.__setattr__(key, val)

        # Inevitable mocks for connection.LibvirtConnection
        self.mox.StubOutWithMock(connection.utils, 'import_class')
        connection.utils.import_class(mox.IgnoreArg()).AndReturn(fakeip)
        self.mox.StubOutWithMock(connection.utils, 'import_object')
        connection.utils.import_object(mox.IgnoreArg()).AndReturn(fakevif)
        self.mox.StubOutWithMock(connection.LibvirtConnection, '_conn')
        connection.LibvirtConnection._conn = fake

    def fake_lookup(self, instance_name):
        return FakeVirtDomain()

    def fake_execute(self, *args):
        open(args[-1], "a").close()

    def create_service(self, **kwargs):
        service_ref = {'host': kwargs.get('host', 'dummy'),
                       'binary': 'nova-compute',
                       'topic': 'compute',
                       'report_count': 0,
                       'availability_zone': 'zone'}

        return db.service_create(context.get_admin_context(), service_ref)

    def test_preparing_xml_info(self):
        conn = connection.LibvirtConnection(True)
        instance_ref = db.instance_create(self.context, self.test_instance)

        result = conn._prepare_xml_info(instance_ref,
                                        _create_network_info(),
                                        False)
        self.assertTrue(len(result['nics']) == 1)

        result = conn._prepare_xml_info(instance_ref,
                                        _create_network_info(2),
                                        False)
        self.assertTrue(len(result['nics']) == 2)

    def test_xml_and_uri_no_ramdisk_no_kernel(self):
        instance_data = dict(self.test_instance)
        self._check_xml_and_uri(instance_data,
                                expect_kernel=False, expect_ramdisk=False)

    def test_xml_and_uri_no_ramdisk(self):
        instance_data = dict(self.test_instance)
        instance_data['kernel_id'] = 'aki-deadbeef'
        self._check_xml_and_uri(instance_data,
                                expect_kernel=True, expect_ramdisk=False)

    def test_xml_and_uri_no_kernel(self):
        instance_data = dict(self.test_instance)
        instance_data['ramdisk_id'] = 'ari-deadbeef'
        self._check_xml_and_uri(instance_data,
                                expect_kernel=False, expect_ramdisk=False)

    def test_xml_and_uri(self):
        instance_data = dict(self.test_instance)
        instance_data['ramdisk_id'] = 'ari-deadbeef'
        instance_data['kernel_id'] = 'aki-deadbeef'
        self._check_xml_and_uri(instance_data,
                                expect_kernel=True, expect_ramdisk=True)

    def test_xml_and_uri_rescue(self):
        instance_data = dict(self.test_instance)
        instance_data['ramdisk_id'] = 'ari-deadbeef'
        instance_data['kernel_id'] = 'aki-deadbeef'
        self._check_xml_and_uri(instance_data, expect_kernel=True,
                                expect_ramdisk=True, rescue=True)

    def test_xml_and_uri_single_local_disk(self):
        self.flags(libvirt_single_local_disk=True)
        instance_data = dict(self.test_instance)
        instance_data['ramdisk_id'] = 'ari-deadbeef'
        instance_data['kernel_id'] = 'aki-deadbeef'
        self._check_xml_and_uri(instance_data,
                                expect_kernel=True, expect_ramdisk=True,
                                single_local_disk=True)

    def test_lxc_container_and_uri(self):
        instance_data = dict(self.test_instance)
        self._check_xml_and_container(instance_data)

    def test_snapshot_in_ami_format(self):
        if not self.lazy_load_library_exists():
            return

        self.flags(image_service='nova.image.fake.FakeImageService')

        # Start test
        image_service = utils.import_object(FLAGS.image_service)

        # Assign image_ref = 3 from nova/images/fakes for testing
        # ami image
        test_instance = copy.deepcopy(self.test_instance)
        test_instance["image_ref"] = "3"

        # Assuming that base image already exists in image_service
        instance_ref = db.instance_create(self.context, test_instance)
        properties = {'instance_id': instance_ref['id'],
                      'user_id': str(self.context.user_id)}
        snapshot_name = 'test-snap'
        sent_meta = {'name': snapshot_name, 'is_public': False,
                     'status': 'creating', 'properties': properties}
        # Create new image. It will be updated in snapshot method
        # To work with it from snapshot, the single image_service is needed
        recv_meta = image_service.create(context, sent_meta)

        self.mox.StubOutWithMock(connection.LibvirtConnection, '_conn')
        connection.LibvirtConnection._conn.lookupByName = self.fake_lookup
        self.mox.StubOutWithMock(connection.utils, 'execute')
        connection.utils.execute = self.fake_execute

        self.mox.ReplayAll()

        conn = connection.LibvirtConnection(False)
        conn.snapshot(self.context, instance_ref, recv_meta['id'])

        snapshot = image_service.show(context, recv_meta['id'])
        self.assertEquals(snapshot['properties']['image_state'], 'available')
        self.assertEquals(snapshot['status'], 'active')
        # ami image treated as a raw disk.
        self.assertEquals(snapshot['disk_format'], 'raw')
        self.assertEquals(snapshot['name'], snapshot_name)

    def test_snapshot_in_raw_format(self):
        if not self.lazy_load_library_exists():
            return

        self.flags(image_service='nova.image.fake.FakeImageService')

        # Start test
        image_service = utils.import_object(FLAGS.image_service)

        # Assuming that base image already exists in image_service
        instance_ref = db.instance_create(self.context, self.test_instance)
        properties = {'instance_id': instance_ref['id'],
                      'user_id': str(self.context.user_id)}
        snapshot_name = 'test-snap'
        sent_meta = {'name': snapshot_name, 'is_public': False,
                     'status': 'creating', 'properties': properties}
        # Create new image. It will be updated in snapshot method
        # To work with it from snapshot, the single image_service is needed
        recv_meta = image_service.create(context, sent_meta)

        self.mox.StubOutWithMock(connection.LibvirtConnection, '_conn')
        connection.LibvirtConnection._conn.lookupByName = self.fake_lookup
        self.mox.StubOutWithMock(connection.utils, 'execute')
        connection.utils.execute = self.fake_execute

        self.mox.ReplayAll()

        conn = connection.LibvirtConnection(False)
        conn.snapshot(self.context, instance_ref, recv_meta['id'])

        snapshot = image_service.show(context, recv_meta['id'])
        self.assertEquals(snapshot['properties']['image_state'], 'available')
        self.assertEquals(snapshot['status'], 'active')
        self.assertEquals(snapshot['disk_format'], 'raw')
        self.assertEquals(snapshot['name'], snapshot_name)

    def test_snapshot_in_qcow2_format(self):
        if not self.lazy_load_library_exists():
            return

        self.flags(image_service='nova.image.fake.FakeImageService')
        self.flags(snapshot_image_format='qcow2')

        # Start test
        image_service = utils.import_object(FLAGS.image_service)

        # Assuming that base image already exists in image_service
        instance_ref = db.instance_create(self.context, self.test_instance)
        properties = {'instance_id': instance_ref['id'],
                      'user_id': str(self.context.user_id)}
        snapshot_name = 'test-snap'
        sent_meta = {'name': snapshot_name, 'is_public': False,
                     'status': 'creating', 'properties': properties}
        # Create new image. It will be updated in snapshot method
        # To work with it from snapshot, the single image_service is needed
        recv_meta = image_service.create(context, sent_meta)

        self.mox.StubOutWithMock(connection.LibvirtConnection, '_conn')
        connection.LibvirtConnection._conn.lookupByName = self.fake_lookup
        self.mox.StubOutWithMock(connection.utils, 'execute')
        connection.utils.execute = self.fake_execute

        self.mox.ReplayAll()

        conn = connection.LibvirtConnection(False)
        conn.snapshot(self.context, instance_ref, recv_meta['id'])

        snapshot = image_service.show(context, recv_meta['id'])
        self.assertEquals(snapshot['properties']['image_state'], 'available')
        self.assertEquals(snapshot['status'], 'active')
        self.assertEquals(snapshot['disk_format'], 'qcow2')
        self.assertEquals(snapshot['name'], snapshot_name)

    def test_snapshot_no_image_architecture(self):
        if not self.lazy_load_library_exists():
            return

        self.flags(image_service='nova.image.fake.FakeImageService')

        # Start test
        image_service = utils.import_object(FLAGS.image_service)

        # Assign image_ref = 2 from nova/images/fakes for testing different
        # base image
        test_instance = copy.deepcopy(self.test_instance)
        test_instance["image_ref"] = "2"

        # Assuming that base image already exists in image_service
        instance_ref = db.instance_create(self.context, test_instance)
        properties = {'instance_id': instance_ref['id'],
                      'user_id': str(self.context.user_id)}
        snapshot_name = 'test-snap'
        sent_meta = {'name': snapshot_name, 'is_public': False,
                     'status': 'creating', 'properties': properties}
        # Create new image. It will be updated in snapshot method
        # To work with it from snapshot, the single image_service is needed
        recv_meta = image_service.create(context, sent_meta)

        self.mox.StubOutWithMock(connection.LibvirtConnection, '_conn')
        connection.LibvirtConnection._conn.lookupByName = self.fake_lookup
        self.mox.StubOutWithMock(connection.utils, 'execute')
        connection.utils.execute = self.fake_execute

        self.mox.ReplayAll()

        conn = connection.LibvirtConnection(False)
        conn.snapshot(self.context, instance_ref, recv_meta['id'])

        snapshot = image_service.show(context, recv_meta['id'])
        self.assertEquals(snapshot['properties']['image_state'], 'available')
        self.assertEquals(snapshot['status'], 'active')
        self.assertEquals(snapshot['name'], snapshot_name)

    def test_attach_invalid_device(self):
        self.create_fake_libvirt_mock()
        connection.LibvirtConnection._conn.lookupByName = self.fake_lookup
        self.mox.ReplayAll()
        conn = connection.LibvirtConnection(False)
        self.assertRaises(exception.InvalidDevicePath,
                          conn.attach_volume,
                          "fake", "bad/device/path", "/dev/fake")

    def test_multi_nic(self):
        instance_data = dict(self.test_instance)
        network_info = _create_network_info(2)
        conn = connection.LibvirtConnection(True)
        instance_ref = db.instance_create(self.context, instance_data)
        xml = conn.to_xml(instance_ref, network_info, False)
        tree = xml_to_tree(xml)
        interfaces = tree.findall("./devices/interface")
        self.assertEquals(len(interfaces), 2)
        parameters = interfaces[0].findall('./filterref/parameter')
        self.assertEquals(interfaces[0].get('type'), 'bridge')
        self.assertEquals(parameters[0].get('name'), 'IP')
        self.assertEquals(parameters[0].get('value'), '10.11.12.13')
        self.assertEquals(parameters[1].get('name'), 'DHCPSERVER')
        self.assertEquals(parameters[1].get('value'), '10.0.0.1')

    def _check_xml_and_container(self, instance):
        user_context = context.RequestContext(self.user_id,
                                              self.project_id)
        instance_ref = db.instance_create(user_context, instance)
        _setup_networking(instance_ref['id'], self.test_ip)

        self.flags(libvirt_type='lxc')
        conn = connection.LibvirtConnection(True)

        uri = conn.get_uri()
        self.assertEquals(uri, 'lxc:///')

        network_info = _create_network_info()
        xml = conn.to_xml(instance_ref, network_info)
        tree = xml_to_tree(xml)

        check = [
        (lambda t: t.find('.').get('type'), 'lxc'),
        (lambda t: t.find('./os/type').text, 'exe'),
        (lambda t: t.find('./devices/filesystem/target').get('dir'), '/')]

        for i, (check, expected_result) in enumerate(check):
            self.assertEqual(check(tree),
                             expected_result,
                             '%s failed common check %d' % (xml, i))

        target = tree.find('./devices/filesystem/source').get('dir')
        self.assertTrue(len(target) > 0)

    def _check_xml_and_uri(self, instance, expect_ramdisk, expect_kernel,
                           rescue=False, single_local_disk=False):
        user_context = context.RequestContext(self.user_id, self.project_id)
        instance_ref = db.instance_create(user_context, instance)
        network_ref = db.project_get_networks(context.get_admin_context(),
                                             self.project_id)[0]

        _setup_networking(instance_ref['id'], self.test_ip)

        type_uri_map = {'qemu': ('qemu:///system',
                             [(lambda t: t.find('.').get('type'), 'qemu'),
                              (lambda t: t.find('./os/type').text, 'hvm'),
                              (lambda t: t.find('./devices/emulator'), None)]),
                        'kvm': ('qemu:///system',
                             [(lambda t: t.find('.').get('type'), 'kvm'),
                              (lambda t: t.find('./os/type').text, 'hvm'),
                              (lambda t: t.find('./devices/emulator'), None)]),
                        'uml': ('uml:///system',
                             [(lambda t: t.find('.').get('type'), 'uml'),
                              (lambda t: t.find('./os/type').text, 'uml')]),
                        'xen': ('xen:///',
                             [(lambda t: t.find('.').get('type'), 'xen'),
                              (lambda t: t.find('./os/type').text, 'linux')]),
                              }

        for hypervisor_type in ['qemu', 'kvm', 'xen']:
            check_list = type_uri_map[hypervisor_type][1]

            if rescue:
                check = (lambda t: t.find('./os/kernel').text.split('/')[1],
                         'kernel.rescue')
                check_list.append(check)
                check = (lambda t: t.find('./os/initrd').text.split('/')[1],
                         'ramdisk.rescue')
                check_list.append(check)
            else:
                if expect_kernel:
                    check = (lambda t: t.find('./os/kernel').text.split(
                        '/')[1], 'kernel')
                else:
                    check = (lambda t: t.find('./os/kernel'), None)
                check_list.append(check)

                if expect_ramdisk:
                    check = (lambda t: t.find('./os/initrd').text.split(
                        '/')[1], 'ramdisk')
                else:
                    check = (lambda t: t.find('./os/initrd'), None)
                check_list.append(check)

        parameter = './devices/interface/filterref/parameter'
        common_checks = [
            (lambda t: t.find('.').tag, 'domain'),
            (lambda t: t.find(parameter).get('name'), 'IP'),
            (lambda t: t.find(parameter).get('value'), '10.11.12.13'),
            (lambda t: t.findall(parameter)[1].get('name'), 'DHCPSERVER'),
            (lambda t: t.findall(parameter)[1].get('value'), '10.0.0.1'),
            (lambda t: t.find('./devices/serial/source').get(
                'path').split('/')[1], 'console.log'),
            (lambda t: t.find('./memory').text, '2097152')]
        if rescue:
            common_checks += [
                (lambda t: t.findall('./devices/disk/source')[0].get(
                    'file').split('/')[1], 'disk.rescue'),
                (lambda t: t.findall('./devices/disk/source')[1].get(
                    'file').split('/')[1], 'disk')]
        else:
            common_checks += [(lambda t: t.findall(
                './devices/disk/source')[0].get('file').split('/')[1],
                               'disk')]
            if single_local_disk:
                common_checks += [(lambda t: len(t.findall(
                    './devices/disk/source')), 1)]
            else:
                common_checks += [(lambda t: t.findall(
                    './devices/disk/source')[1].get('file').split('/')[1],
                               'disk.local')]

        for (libvirt_type, (expected_uri, checks)) in type_uri_map.iteritems():
            self.flags(libvirt_type=libvirt_type)
            conn = connection.LibvirtConnection(True)

            uri = conn.get_uri()
            self.assertEquals(uri, expected_uri)

            network_info = _create_network_info()
            xml = conn.to_xml(instance_ref, network_info, rescue)
            tree = xml_to_tree(xml)
            for i, (check, expected_result) in enumerate(checks):
                self.assertEqual(check(tree),
                                 expected_result,
                                 '%s != %s failed check %d' %
                                 (check(tree), expected_result, i))

            for i, (check, expected_result) in enumerate(common_checks):
                self.assertEqual(check(tree),
                                 expected_result,
                                 '%s != %s failed common check %d' %
                                 (check(tree), expected_result, i))

        # This test is supposed to make sure we don't
        # override a specifically set uri
        #
        # Deliberately not just assigning this string to FLAGS.libvirt_uri and
        # checking against that later on. This way we make sure the
        # implementation doesn't fiddle around with the FLAGS.
        testuri = 'something completely different'
        self.flags(libvirt_uri=testuri)
        for (libvirt_type, (expected_uri, checks)) in type_uri_map.iteritems():
            self.flags(libvirt_type=libvirt_type)
            conn = connection.LibvirtConnection(True)
            uri = conn.get_uri()
            self.assertEquals(uri, testuri)
        db.instance_destroy(user_context, instance_ref['id'])

    def test_update_available_resource_works_correctly(self):
        """Confirm compute_node table is updated successfully."""
        self.flags(instances_path='.')

        # Prepare mocks
        def getVersion():
            return 12003

        def getType():
            return 'qemu'

        def listDomainsID():
            return []

        service_ref = self.create_service(host='dummy')
        self.create_fake_libvirt_mock(getVersion=getVersion,
                                      getType=getType,
                                      listDomainsID=listDomainsID)
        self.mox.StubOutWithMock(connection.LibvirtConnection,
                                 'get_cpu_info')
        connection.LibvirtConnection.get_cpu_info().AndReturn('cpuinfo')

        # Start test
        self.mox.ReplayAll()
        conn = connection.LibvirtConnection(False)
        conn.update_available_resource(self.context, 'dummy')
        service_ref = db.service_get(self.context, service_ref['id'])
        compute_node = service_ref['compute_node'][0]

        if sys.platform.upper() == 'LINUX2':
            self.assertTrue(compute_node['vcpus'] >= 0)
            self.assertTrue(compute_node['memory_mb'] > 0)
            self.assertTrue(compute_node['local_gb'] > 0)
            self.assertTrue(compute_node['vcpus_used'] == 0)
            self.assertTrue(compute_node['memory_mb_used'] > 0)
            self.assertTrue(compute_node['local_gb_used'] > 0)
            self.assertTrue(len(compute_node['hypervisor_type']) > 0)
            self.assertTrue(compute_node['hypervisor_version'] > 0)
        else:
            self.assertTrue(compute_node['vcpus'] >= 0)
            self.assertTrue(compute_node['memory_mb'] == 0)
            self.assertTrue(compute_node['local_gb'] > 0)
            self.assertTrue(compute_node['vcpus_used'] == 0)
            self.assertTrue(compute_node['memory_mb_used'] == 0)
            self.assertTrue(compute_node['local_gb_used'] > 0)
            self.assertTrue(len(compute_node['hypervisor_type']) > 0)
            self.assertTrue(compute_node['hypervisor_version'] > 0)

        db.service_destroy(self.context, service_ref['id'])

    def test_update_resource_info_no_compute_record_found(self):
        """Raise exception if no recorde found on services table."""
        self.flags(instances_path='.')
        self.create_fake_libvirt_mock()

        self.mox.ReplayAll()
        conn = connection.LibvirtConnection(False)
        self.assertRaises(exception.ComputeServiceUnavailable,
                          conn.update_available_resource,
                          self.context, 'dummy')

    def test_ensure_filtering_rules_for_instance_timeout(self):
        """ensure_filtering_fules_for_instance() finishes with timeout."""
        # Skip if non-libvirt environment
        if not self.lazy_load_library_exists():
            return

        # Preparing mocks
        def fake_none(self, *args):
            return

        def fake_raise(self):
            raise libvirt.libvirtError('ERR')

        class FakeTime(object):
            def __init__(self):
                self.counter = 0

            def sleep(self, t):
                self.counter += t

        fake_timer = FakeTime()

        self.create_fake_libvirt_mock()
        instance_ref = db.instance_create(self.context, self.test_instance)
        network_info = _create_network_info()

        # Start test
        self.mox.ReplayAll()
        try:
            conn = connection.LibvirtConnection(False)
            conn.firewall_driver.setattr('setup_basic_filtering', fake_none)
            conn.firewall_driver.setattr('prepare_instance_filter', fake_none)
            conn.firewall_driver.setattr('instance_filter_exists', fake_none)
            conn.ensure_filtering_rules_for_instance(instance_ref,
                                                     network_info,
                                                     time=fake_timer)
        except exception.Error, e:
            c1 = (0 <= e.message.find('Timeout migrating for'))
        self.assertTrue(c1)

        self.assertEqual(29, fake_timer.counter, "Didn't wait the expected "
                                                 "amount of time")

        db.instance_destroy(self.context, instance_ref['id'])

    def test_live_migration_raises_exception(self):
        """Confirms recover method is called when exceptions are raised."""
        # Skip if non-libvirt environment
        if not self.lazy_load_library_exists():
            return

        # Preparing data
        self.compute = utils.import_object(FLAGS.compute_manager)
        instance_dict = {'host': 'fake',
                         'power_state': power_state.RUNNING,
                         'vm_state': vm_states.ACTIVE}
        instance_ref = db.instance_create(self.context, self.test_instance)
        instance_ref = db.instance_update(self.context, instance_ref['id'],
                                          instance_dict)
        vol_dict = {'status': 'migrating', 'size': 1}
        volume_ref = db.volume_create(self.context, vol_dict)
        db.volume_attached(self.context, volume_ref['id'], instance_ref['id'],
                           '/dev/fake')

        # Preparing mocks
        vdmock = self.mox.CreateMock(libvirt.virDomain)
        self.mox.StubOutWithMock(vdmock, "migrateToURI")
        vdmock.migrateToURI(FLAGS.live_migration_uri % 'dest',
                            mox.IgnoreArg(),
                            None, FLAGS.live_migration_bandwidth).\
                            AndRaise(libvirt.libvirtError('ERR'))

        def fake_lookup(instance_name):
            if instance_name == instance_ref.name:
                return vdmock

        self.create_fake_libvirt_mock(lookupByName=fake_lookup)
#        self.mox.StubOutWithMock(self.compute, "recover_live_migration")
        self.mox.StubOutWithMock(self.compute, "rollback_live_migration")
#        self.compute.recover_live_migration(self.context, instance_ref,
#                                             dest='dest')
        self.compute.rollback_live_migration(self.context, instance_ref,
                                            'dest', False)

        #start test
        self.mox.ReplayAll()
        conn = connection.LibvirtConnection(False)
        self.assertRaises(libvirt.libvirtError,
                      conn._live_migration,
                      self.context, instance_ref, 'dest', False,
                      self.compute.rollback_live_migration)

        instance_ref = db.instance_get(self.context, instance_ref['id'])
        self.assertTrue(instance_ref['vm_state'] == vm_states.ACTIVE)
        self.assertTrue(instance_ref['power_state'] == power_state.RUNNING)
        volume_ref = db.volume_get(self.context, volume_ref['id'])
        self.assertTrue(volume_ref['status'] == 'in-use')

        db.volume_destroy(self.context, volume_ref['id'])
        db.instance_destroy(self.context, instance_ref['id'])

    def test_pre_block_migration_works_correctly(self):
        """Confirms pre_block_migration works correctly."""

        # Skip if non-libvirt environment
        if not self.lazy_load_library_exists():
            return

        # Replace instances_path since this testcase creates tmpfile
        tmpdir = tempfile.mkdtemp()
        store = FLAGS.instances_path
        FLAGS.instances_path = tmpdir

        # Test data
        instance_ref = db.instance_create(self.context, self.test_instance)
        dummyjson = ('[{"path": "%s/disk", "local_gb": "10G",'
                     ' "type": "raw", "backing_file": ""}]')

        # Preparing mocks
        # qemu-img should be mockd since test environment might not have
        # large disk space.
        self.mox.StubOutWithMock(utils, "execute")
        utils.execute('qemu-img', 'create', '-f', 'raw',
                      '%s/%s/disk' % (tmpdir, instance_ref.name), '10G')

        self.mox.ReplayAll()
        conn = connection.LibvirtConnection(False)
        conn.pre_block_migration(self.context, instance_ref,
                                 dummyjson % tmpdir)

        self.assertTrue(os.path.exists('%s/%s/' %
                                       (tmpdir, instance_ref.name)))

        shutil.rmtree(tmpdir)
        db.instance_destroy(self.context, instance_ref['id'])
        # Restore FLAGS.instances_path
        FLAGS.instances_path = store

    def test_get_instance_disk_info_works_correctly(self):
        """Confirms pre_block_migration works correctly."""
        # Skip if non-libvirt environment
        if not self.lazy_load_library_exists():
            return

        # Test data
        instance_ref = db.instance_create(self.context, self.test_instance)
        dummyxml = ("<domain type='kvm'><name>instance-0000000a</name>"
                    "<devices>"
                    "<disk type='file'><driver name='qemu' type='raw'/>"
                    "<source file='/test/disk'/>"
                    "<target dev='vda' bus='virtio'/></disk>"
                    "<disk type='file'><driver name='qemu' type='qcow2'/>"
                    "<source file='/test/disk.local'/>"
                    "<target dev='vdb' bus='virtio'/></disk>"
                    "</devices></domain>")

        ret = ("image: /test/disk\nfile format: raw\n"
               "virtual size: 20G (21474836480 bytes)\ndisk size: 3.1G\n"
               "disk size: 102M\n"
               "cluster_size: 2097152\n"
               "backing file: /test/dummy (actual path: /backing/file)\n")

        # Preparing mocks
        vdmock = self.mox.CreateMock(libvirt.virDomain)
        self.mox.StubOutWithMock(vdmock, "XMLDesc")
        vdmock.XMLDesc(0).AndReturn(dummyxml)

        def fake_lookup(instance_name):
            if instance_name == instance_ref.name:
                return vdmock
        self.create_fake_libvirt_mock(lookupByName=fake_lookup)

        self.mox.StubOutWithMock(os.path, "getsize")
        # based on above testdata, one is raw image, so getsize is mocked.
        os.path.getsize("/test/disk").AndReturn(10 * 1024 * 1024 * 1024)
        # another is qcow image, so qemu-img should be mocked.
        self.mox.StubOutWithMock(utils, "execute")
        utils.execute('qemu-img', 'info', '/test/disk.local').\
            AndReturn((ret, ''))

        self.mox.ReplayAll()
        conn = connection.LibvirtConnection(False)
        info = conn.get_instance_disk_info(self.context, instance_ref)
        info = utils.loads(info)

        self.assertTrue(info[0]['type'] == 'raw' and
                        info[1]['type'] == 'qcow2' and
                        info[0]['path'] == '/test/disk' and
                        info[1]['path'] == '/test/disk.local' and
                        info[0]['local_gb'] == '10G' and
                        info[1]['local_gb'] == '20G' and
                        info[0]['backing_file'] == "" and
                        info[1]['backing_file'] == "file")

        db.instance_destroy(self.context, instance_ref['id'])

    def test_spawn_with_network_info(self):
        # Skip if non-libvirt environment
        if not self.lazy_load_library_exists():
            return

        # Preparing mocks
        def fake_none(self, instance):
            return

        self.create_fake_libvirt_mock()
        instance = db.instance_create(self.context, self.test_instance)

        # Start test
        self.mox.ReplayAll()
        conn = connection.LibvirtConnection(False)
        conn.firewall_driver.setattr('setup_basic_filtering', fake_none)
        conn.firewall_driver.setattr('prepare_instance_filter', fake_none)

        network_info = _create_network_info()

        try:
            conn.spawn(self.context, instance, network_info)
        except Exception, e:
            count = (0 <= str(e.message).find('Unexpected method call'))

        shutil.rmtree(os.path.join(FLAGS.instances_path, instance.name))
        shutil.rmtree(os.path.join(FLAGS.instances_path, '_base'))

        self.assertTrue(count)

    def test_get_host_ip_addr(self):
        conn = connection.LibvirtConnection(False)
        ip = conn.get_host_ip_addr()
        self.assertEquals(ip, FLAGS.my_ip)

    def test_volume_in_mapping(self):
        conn = connection.LibvirtConnection(False)
        swap = {'device_name': '/dev/sdb',
                'swap_size': 1}
        ephemerals = [{'num': 0,
                       'virtual_name': 'ephemeral0',
                       'device_name': '/dev/sdc1',
                       'size': 1},
                      {'num': 2,
                       'virtual_name': 'ephemeral2',
                       'device_name': '/dev/sdd',
                       'size': 1}]
        block_device_mapping = [{'mount_device': '/dev/sde',
                                 'device_path': 'fake_device'},
                                {'mount_device': '/dev/sdf',
                                 'device_path': 'fake_device'}]
        block_device_info = {
                'root_device_name': '/dev/sda',
                'swap': swap,
                'ephemerals': ephemerals,
                'block_device_mapping': block_device_mapping}

        def _assert_volume_in_mapping(device_name, true_or_false):
            self.assertEquals(conn._volume_in_mapping(device_name,
                                                      block_device_info),
                              true_or_false)

        _assert_volume_in_mapping('sda', False)
        _assert_volume_in_mapping('sdb', True)
        _assert_volume_in_mapping('sdc1', True)
        _assert_volume_in_mapping('sdd', True)
        _assert_volume_in_mapping('sde', True)
        _assert_volume_in_mapping('sdf', True)
        _assert_volume_in_mapping('sdg', False)
        _assert_volume_in_mapping('sdh1', False)


class NWFilterFakes:
    def __init__(self):
        self.filters = {}

    def nwfilterLookupByName(self, name):
        if name in self.filters:
            return self.filters[name]
        raise libvirt.libvirtError('Filter Not Found')

    def filterDefineXMLMock(self, xml):
        class FakeNWFilterInternal:
            def __init__(self, parent, name):
                self.name = name
                self.parent = parent

            def undefine(self):
                del self.parent.filters[self.name]
                pass
        tree = xml_to_tree(xml)
        name = tree.get('name')
        if name not in self.filters:
            self.filters[name] = FakeNWFilterInternal(self, name)
        return True


class IptablesFirewallTestCase(test.TestCase):
    def setUp(self):
        super(IptablesFirewallTestCase, self).setUp()

        self.user_id = 'fake'
        self.project_id = 'fake'
        self.context = context.RequestContext(self.user_id, self.project_id)
        self.network = utils.import_object(FLAGS.network_manager)

        class FakeLibvirtConnection(object):
            def nwfilterDefineXML(*args, **kwargs):
                """setup_basic_rules in nwfilter calls this."""
                pass
        self.fake_libvirt_connection = FakeLibvirtConnection()
        self.test_ip = '10.11.12.13'
        self.fw = firewall.IptablesFirewallDriver(
                      get_connection=lambda: self.fake_libvirt_connection)

    def lazy_load_library_exists(self):
        """check if libvirt is available."""
        # try to connect libvirt. if fail, skip test.
        try:
            import libvirt
            import libxml2
        except ImportError:
            return False
        global libvirt
        libvirt = __import__('libvirt')
        connection.libvirt = __import__('libvirt')
        connection.libxml2 = __import__('libxml2')
        return True

    in_nat_rules = [
      '# Generated by iptables-save v1.4.10 on Sat Feb 19 00:03:19 2011',
      '*nat',
      ':PREROUTING ACCEPT [1170:189210]',
      ':INPUT ACCEPT [844:71028]',
      ':OUTPUT ACCEPT [5149:405186]',
      ':POSTROUTING ACCEPT [5063:386098]',
    ]

    in_filter_rules = [
      '# Generated by iptables-save v1.4.4 on Mon Dec  6 11:54:13 2010',
      '*filter',
      ':INPUT ACCEPT [969615:281627771]',
      ':FORWARD ACCEPT [0:0]',
      ':OUTPUT ACCEPT [915599:63811649]',
      ':nova-block-ipv4 - [0:0]',
      '-A INPUT -i virbr0 -p tcp -m tcp --dport 67 -j ACCEPT ',
      '-A FORWARD -d 192.168.122.0/24 -o virbr0 -m state --state RELATED'
      ',ESTABLISHED -j ACCEPT ',
      '-A FORWARD -s 192.168.122.0/24 -i virbr0 -j ACCEPT ',
      '-A FORWARD -i virbr0 -o virbr0 -j ACCEPT ',
      '-A FORWARD -o virbr0 -j REJECT --reject-with icmp-port-unreachable ',
      '-A FORWARD -i virbr0 -j REJECT --reject-with icmp-port-unreachable ',
      'COMMIT',
      '# Completed on Mon Dec  6 11:54:13 2010',
    ]

    in6_filter_rules = [
      '# Generated by ip6tables-save v1.4.4 on Tue Jan 18 23:47:56 2011',
      '*filter',
      ':INPUT ACCEPT [349155:75810423]',
      ':FORWARD ACCEPT [0:0]',
      ':OUTPUT ACCEPT [349256:75777230]',
      'COMMIT',
      '# Completed on Tue Jan 18 23:47:56 2011',
    ]

    def _create_instance_ref(self):
        return db.instance_create(self.context,
                                  {'user_id': 'fake',
                                   'project_id': 'fake',
                                   'instance_type_id': 1})

    def test_static_filters(self):
        instance_ref = self._create_instance_ref()
        src_instance_ref = self._create_instance_ref()
        src_ip = '10.11.12.14'
        src_mac = '56:12:12:12:12:13'
        _setup_networking(instance_ref['id'], self.test_ip, src_mac)
        _setup_networking(src_instance_ref['id'], src_ip)

        admin_ctxt = context.get_admin_context()
        secgroup = db.security_group_create(admin_ctxt,
                                            {'user_id': 'fake',
                                             'project_id': 'fake',
                                             'name': 'testgroup',
                                             'description': 'test group'})

        src_secgroup = db.security_group_create(admin_ctxt,
                                                {'user_id': 'fake',
                                                 'project_id': 'fake',
                                                 'name': 'testsourcegroup',
                                                 'description': 'src group'})

        db.security_group_rule_create(admin_ctxt,
                                      {'parent_group_id': secgroup['id'],
                                       'protocol': 'icmp',
                                       'from_port': -1,
                                       'to_port': -1,
                                       'cidr': '192.168.11.0/24'})

        db.security_group_rule_create(admin_ctxt,
                                      {'parent_group_id': secgroup['id'],
                                       'protocol': 'icmp',
                                       'from_port': 8,
                                       'to_port': -1,
                                       'cidr': '192.168.11.0/24'})

        db.security_group_rule_create(admin_ctxt,
                                      {'parent_group_id': secgroup['id'],
                                       'protocol': 'tcp',
                                       'from_port': 80,
                                       'to_port': 81,
                                       'cidr': '192.168.10.0/24'})

        db.security_group_rule_create(admin_ctxt,
                                      {'parent_group_id': secgroup['id'],
                                       'protocol': 'tcp',
                                       'from_port': 80,
                                       'to_port': 81,
                                       'group_id': src_secgroup['id']})

        db.instance_add_security_group(admin_ctxt, instance_ref['id'],
                                       secgroup['id'])
        db.instance_add_security_group(admin_ctxt, src_instance_ref['id'],
                                       src_secgroup['id'])
        instance_ref = db.instance_get(admin_ctxt, instance_ref['id'])
        src_instance_ref = db.instance_get(admin_ctxt, src_instance_ref['id'])

#        self.fw.add_instance(instance_ref)
        def fake_iptables_execute(*cmd, **kwargs):
            process_input = kwargs.get('process_input', None)
            if cmd == ('ip6tables-save', '-t', 'filter'):
                return '\n'.join(self.in6_filter_rules), None
            if cmd == ('iptables-save', '-t', 'filter'):
                return '\n'.join(self.in_filter_rules), None
            if cmd == ('iptables-save', '-t', 'nat'):
                return '\n'.join(self.in_nat_rules), None
            if cmd == ('iptables-restore',):
                lines = process_input.split('\n')
                if '*filter' in lines:
                    self.out_rules = lines
                return '', ''
            if cmd == ('ip6tables-restore',):
                lines = process_input.split('\n')
                if '*filter' in lines:
                    self.out6_rules = lines
                return '', ''
            print cmd, kwargs

        from nova.network import linux_net
        linux_net.iptables_manager.execute = fake_iptables_execute

        network_info = _create_network_info()
        self.fw.prepare_instance_filter(instance_ref, network_info)
        self.fw.apply_instance_filter(instance_ref, network_info)

        in_rules = filter(lambda l: not l.startswith('#'),
                          self.in_filter_rules)
        for rule in in_rules:
            if not 'nova' in rule:
                self.assertTrue(rule in self.out_rules,
                                'Rule went missing: %s' % rule)

        instance_chain = None
        for rule in self.out_rules:
            # This is pretty crude, but it'll do for now
            if '-d 10.11.12.13 -j' in rule:
                instance_chain = rule.split(' ')[-1]
                break
        self.assertTrue(instance_chain, "The instance chain wasn't added")

        security_group_chain = None
        for rule in self.out_rules:
            # This is pretty crude, but it'll do for now
            if '-A %s -j' % instance_chain in rule:
                security_group_chain = rule.split(' ')[-1]
                break
        self.assertTrue(security_group_chain,
                        "The security group chain wasn't added")

        regex = re.compile('-A .* -j ACCEPT -p icmp -s 192.168.11.0/24')
        self.assertTrue(len(filter(regex.match, self.out_rules)) > 0,
                        "ICMP acceptance rule wasn't added")

        regex = re.compile('-A .* -j ACCEPT -p icmp -m icmp --icmp-type 8'
                           ' -s 192.168.11.0/24')
        self.assertTrue(len(filter(regex.match, self.out_rules)) > 0,
                        "ICMP Echo Request acceptance rule wasn't added")

        regex = re.compile('-A .* -j ACCEPT -p tcp -m multiport '
                           '--dports 80:81 -s %s' % (src_ip,))
        self.assertTrue(len(filter(regex.match, self.out_rules)) > 0,
                        "TCP port 80/81 acceptance rule wasn't added")

        regex = re.compile('-A .* -j ACCEPT -p tcp '
                           '-m multiport --dports 80:81 -s 192.168.10.0/24')
        self.assertTrue(len(filter(regex.match, self.out_rules)) > 0,
                        "TCP port 80/81 acceptance rule wasn't added")
        db.instance_destroy(admin_ctxt, instance_ref['id'])

    def test_filters_for_instance_with_ip_v6(self):
        self.flags(use_ipv6=True)
        network_info = _create_network_info()
        rulesv4, rulesv6 = self.fw._filters_for_instance("fake", network_info)
        self.assertEquals(len(rulesv4), 2)
        self.assertEquals(len(rulesv6), 3)

    def test_filters_for_instance_without_ip_v6(self):
        self.flags(use_ipv6=False)
        network_info = _create_network_info()
        rulesv4, rulesv6 = self.fw._filters_for_instance("fake", network_info)
        self.assertEquals(len(rulesv4), 2)
        self.assertEquals(len(rulesv6), 0)

    def test_multinic_iptables(self):
        ipv4_rules_per_network = 2
        ipv6_rules_per_network = 3
        networks_count = 5
        instance_ref = self._create_instance_ref()
        network_info = _create_network_info(networks_count)
        ipv4_len = len(self.fw.iptables.ipv4['filter'].rules)
        ipv6_len = len(self.fw.iptables.ipv6['filter'].rules)
        inst_ipv4, inst_ipv6 = self.fw.instance_rules(instance_ref,
                                                      network_info)
        self.fw.prepare_instance_filter(instance_ref, network_info)
        ipv4 = self.fw.iptables.ipv4['filter'].rules
        ipv6 = self.fw.iptables.ipv6['filter'].rules
        ipv4_network_rules = len(ipv4) - len(inst_ipv4) - ipv4_len
        ipv6_network_rules = len(ipv6) - len(inst_ipv6) - ipv6_len
        self.assertEquals(ipv4_network_rules,
                          ipv4_rules_per_network * networks_count)
        self.assertEquals(ipv6_network_rules,
                          ipv6_rules_per_network * networks_count)

    def test_do_refresh_security_group_rules(self):
        instance_ref = self._create_instance_ref()
        self.mox.StubOutWithMock(self.fw,
                                 'add_filters_for_instance',
                                 use_mock_anything=True)
        self.fw.prepare_instance_filter(instance_ref, mox.IgnoreArg())
        self.fw.instances[instance_ref['id']] = instance_ref
        self.mox.ReplayAll()
        self.fw.do_refresh_security_group_rules("fake")

    def test_unfilter_instance_undefines_nwfilter(self):
        # Skip if non-libvirt environment
        if not self.lazy_load_library_exists():
            return

        admin_ctxt = context.get_admin_context()

        fakefilter = NWFilterFakes()
        self.fw.nwfilter._conn.nwfilterDefineXML =\
                               fakefilter.filterDefineXMLMock
        self.fw.nwfilter._conn.nwfilterLookupByName =\
                               fakefilter.nwfilterLookupByName
        instance_ref = self._create_instance_ref()

        _setup_networking(instance_ref['id'], self.test_ip)
        network_info = _create_network_info()
        self.fw.setup_basic_filtering(instance_ref, network_info)
        self.fw.prepare_instance_filter(instance_ref, network_info)
        self.fw.apply_instance_filter(instance_ref, network_info)
        original_filter_count = len(fakefilter.filters)
        self.fw.unfilter_instance(instance_ref, network_info)

        # should undefine just the instance filter
        self.assertEqual(original_filter_count - len(fakefilter.filters), 1)

        db.instance_destroy(admin_ctxt, instance_ref['id'])

    def test_provider_firewall_rules(self):
        # setup basic instance data
        instance_ref = self._create_instance_ref()
        _setup_networking(instance_ref['id'], self.test_ip)
        # FRAGILE: peeks at how the firewall names chains
        chain_name = 'inst-%s' % instance_ref['id']

        # create a firewall via setup_basic_filtering like libvirt_conn.spawn
        # should have a chain with 0 rules
        network_info = _create_network_info(1)
        self.fw.setup_basic_filtering(instance_ref, network_info)
        self.assertTrue('provider' in self.fw.iptables.ipv4['filter'].chains)
        rules = [rule for rule in self.fw.iptables.ipv4['filter'].rules
                      if rule.chain == 'provider']
        self.assertEqual(0, len(rules))

        admin_ctxt = context.get_admin_context()
        # add a rule and send the update message, check for 1 rule
        provider_fw0 = db.provider_fw_rule_create(admin_ctxt,
                                                  {'protocol': 'tcp',
                                                   'cidr': '10.99.99.99/32',
                                                   'from_port': 1,
                                                   'to_port': 65535})
        self.fw.refresh_provider_fw_rules()
        rules = [rule for rule in self.fw.iptables.ipv4['filter'].rules
                      if rule.chain == 'provider']
        self.assertEqual(1, len(rules))

        # Add another, refresh, and make sure number of rules goes to two
        provider_fw1 = db.provider_fw_rule_create(admin_ctxt,
                                                  {'protocol': 'udp',
                                                   'cidr': '10.99.99.99/32',
                                                   'from_port': 1,
                                                   'to_port': 65535})
        self.fw.refresh_provider_fw_rules()
        rules = [rule for rule in self.fw.iptables.ipv4['filter'].rules
                      if rule.chain == 'provider']
        self.assertEqual(2, len(rules))

        # create the instance filter and make sure it has a jump rule
        self.fw.prepare_instance_filter(instance_ref, network_info)
        self.fw.apply_instance_filter(instance_ref, network_info)
        inst_rules = [rule for rule in self.fw.iptables.ipv4['filter'].rules
                           if rule.chain == chain_name]
        jump_rules = [rule for rule in inst_rules if '-j' in rule.rule]
        provjump_rules = []
        # IptablesTable doesn't make rules unique internally
        for rule in jump_rules:
            if 'provider' in rule.rule and rule not in provjump_rules:
                provjump_rules.append(rule)
        self.assertEqual(1, len(provjump_rules))

        # remove a rule from the db, cast to compute to refresh rule
        db.provider_fw_rule_destroy(admin_ctxt, provider_fw1['id'])
        self.fw.refresh_provider_fw_rules()
        rules = [rule for rule in self.fw.iptables.ipv4['filter'].rules
                      if rule.chain == 'provider']
        self.assertEqual(1, len(rules))


class NWFilterTestCase(test.TestCase):
    def setUp(self):
        super(NWFilterTestCase, self).setUp()

        class Mock(object):
            pass

        self.user_id = 'fake'
        self.project_id = 'fake'
        self.context = context.RequestContext(self.user_id, self.project_id)

        self.fake_libvirt_connection = Mock()

        self.test_ip = '10.11.12.13'
        self.fw = firewall.NWFilterFirewall(
                                         lambda: self.fake_libvirt_connection)

    def test_cidr_rule_nwfilter_xml(self):
        cloud_controller = cloud.CloudController()
        cloud_controller.create_security_group(self.context,
                                               'testgroup',
                                               'test group description')
        cloud_controller.authorize_security_group_ingress(self.context,
                                                          'testgroup',
                                                          from_port='80',
                                                          to_port='81',
                                                          ip_protocol='tcp',
                                                          cidr_ip='0.0.0.0/0')

        security_group = db.security_group_get_by_name(self.context,
                                                       'fake',
                                                       'testgroup')

        xml = self.fw.security_group_to_nwfilter_xml(security_group.id)

        dom = xml_to_dom(xml)
        self.assertEqual(dom.firstChild.tagName, 'filter')

        rules = dom.getElementsByTagName('rule')
        self.assertEqual(len(rules), 1)

        # It's supposed to allow inbound traffic.
        self.assertEqual(rules[0].getAttribute('action'), 'accept')
        self.assertEqual(rules[0].getAttribute('direction'), 'in')

        # Must be lower priority than the base filter (which blocks everything)
        self.assertTrue(int(rules[0].getAttribute('priority')) < 1000)

        ip_conditions = rules[0].getElementsByTagName('tcp')
        self.assertEqual(len(ip_conditions), 1)
        self.assertEqual(ip_conditions[0].getAttribute('srcipaddr'), '0.0.0.0')
        self.assertEqual(ip_conditions[0].getAttribute('srcipmask'), '0.0.0.0')
        self.assertEqual(ip_conditions[0].getAttribute('dstportstart'), '80')
        self.assertEqual(ip_conditions[0].getAttribute('dstportend'), '81')
        self.teardown_security_group()

    def teardown_security_group(self):
        cloud_controller = cloud.CloudController()
        cloud_controller.delete_security_group(self.context, 'testgroup')

    def setup_and_return_security_group(self):
        cloud_controller = cloud.CloudController()
        cloud_controller.create_security_group(self.context,
                                               'testgroup',
                                               'test group description')
        cloud_controller.authorize_security_group_ingress(self.context,
                                                          'testgroup',
                                                          from_port='80',
                                                          to_port='81',
                                                          ip_protocol='tcp',
                                                          cidr_ip='0.0.0.0/0')

        return db.security_group_get_by_name(self.context, 'fake', 'testgroup')

    def _create_instance(self):
        return db.instance_create(self.context,
                                  {'user_id': 'fake',
                                   'project_id': 'fake',
                                   'instance_type_id': 1})

    def _create_instance_type(self, params=None):
        """Create a test instance"""
        if not params:
            params = {}

        context = self.context.elevated()
        inst = {}
        inst['name'] = 'm1.small'
        inst['memory_mb'] = '1024'
        inst['vcpus'] = '1'
        inst['local_gb'] = '20'
        inst['flavorid'] = '1'
        inst['swap'] = '2048'
        inst['rxtx_quota'] = 100
        inst['rxtx_cap'] = 200
        inst.update(params)
        return db.instance_type_create(context, inst)['id']

    def test_creates_base_rule_first(self):
        # These come pre-defined by libvirt
        self.defined_filters = ['no-mac-spoofing',
                                'no-ip-spoofing',
                                'no-arp-spoofing',
                                'allow-dhcp-server']

        self.recursive_depends = {}
        for f in self.defined_filters:
            self.recursive_depends[f] = []

        def _filterDefineXMLMock(xml):
            dom = xml_to_dom(xml)
            name = dom.firstChild.getAttribute('name')
            self.recursive_depends[name] = []
            for f in dom.getElementsByTagName('filterref'):
                ref = f.getAttribute('filter')
                self.assertTrue(ref in self.defined_filters,
                                ('%s referenced filter that does ' +
                                'not yet exist: %s') % (name, ref))
                dependencies = [ref] + self.recursive_depends[ref]
                self.recursive_depends[name] += dependencies

            self.defined_filters.append(name)
            return True

        self.fake_libvirt_connection.nwfilterDefineXML = _filterDefineXMLMock

        instance_ref = self._create_instance()
        inst_id = instance_ref['id']

        _setup_networking(instance_ref['id'], self.test_ip)

        def _ensure_all_called():
            instance_filter = 'nova-instance-%s-%s' % (instance_ref['name'],
                                                       'fake')
            secgroup_filter = 'nova-secgroup-%s' % self.security_group['id']
            for required in [secgroup_filter, 'allow-dhcp-server',
                             'no-arp-spoofing', 'no-ip-spoofing',
                             'no-mac-spoofing']:
                self.assertTrue(required in
                                self.recursive_depends[instance_filter],
                                "Instance's filter does not include %s" %
                                required)

        self.security_group = self.setup_and_return_security_group()

        db.instance_add_security_group(self.context, inst_id,
                                       self.security_group.id)
        instance = db.instance_get(self.context, inst_id)

        network_info = _create_network_info()
        self.fw.setup_basic_filtering(instance, network_info)
        self.fw.prepare_instance_filter(instance, network_info)
        self.fw.apply_instance_filter(instance, network_info)
        _ensure_all_called()
        self.teardown_security_group()
        db.instance_destroy(context.get_admin_context(), instance_ref['id'])

    def test_create_network_filters(self):
        instance_ref = self._create_instance()
        network_info = _create_network_info(3)
        result = self.fw._create_network_filters(instance_ref,
                                                 network_info,
                                                 "fake")
        self.assertEquals(len(result), 3)

    def test_unfilter_instance_undefines_nwfilters(self):
        admin_ctxt = context.get_admin_context()

        fakefilter = NWFilterFakes()
        self.fw._conn.nwfilterDefineXML = fakefilter.filterDefineXMLMock
        self.fw._conn.nwfilterLookupByName = fakefilter.nwfilterLookupByName

        instance_ref = self._create_instance()
        inst_id = instance_ref['id']

        self.security_group = self.setup_and_return_security_group()

        db.instance_add_security_group(self.context, inst_id,
                                       self.security_group.id)

        instance = db.instance_get(self.context, inst_id)

        _setup_networking(instance_ref['id'], self.test_ip)
        network_info = _create_network_info()
        self.fw.setup_basic_filtering(instance, network_info)
        self.fw.prepare_instance_filter(instance, network_info)
        self.fw.apply_instance_filter(instance, network_info)
        original_filter_count = len(fakefilter.filters)
        self.fw.unfilter_instance(instance, network_info)

        # should undefine 2 filters: instance and instance-secgroup
        self.assertEqual(original_filter_count - len(fakefilter.filters), 2)

        db.instance_destroy(admin_ctxt, instance_ref['id'])


class FakeLibxml2(object):

    def __init__(self, name=None):
        self.name = name
        self.counter = 0

    def parseDoc(self, xml):
        return FakeLibxml2()

    def xpathEval(self, p):
        return [FakeLibxml2(p)]

    def xpathNewContext(self):
        return self

    def xpathFreeContext(self):
        pass

    def freeDoc(self):
        pass

    children = []

    def prop(self, name):
        return 'test_device_name'

    def serialize(self):
        return 'abcd1234'

    def getContent(self):

        if not self.name:
            return 'test_contents'

        if self.name.find('arch') >= 0:
            return 'x86'
        elif self.name.find('model') >= 0:
            return 'amd1234'
        elif self.name.find('vendor') >= 0:
            return 'amd'
        elif self.name.find('topology') >= 0:
            return 'core2'
        elif self.name.find('model') >= 0:
            return 'amd'
        elif self.name.find('cores') >= 0:
            return '2'
        elif self.name.find('sockets') >= 0:
            return '9999'
        elif self.name.find('threads') >= 0:
            return '1024'
        elif self.name.find('disk/source') >= 0:
            return '/test_path'
        elif self.name.find('disk/driver') >= 0:
            return 'test_driver'
        elif self.name.find('devices/disk') >= 0:
            return 'file'
        else:
            return 'test_contents'

    def get_properties(self):
        return self

    def get_name(self):
        if self.counter == 0:
            self.name = 'cores'
            return self.name
        if self.counter == 1:
            self.name = 'sockets'
            return self.name
        if self.counter == 2:
            self.name = 'threads'
            return self.name
        return 'test_node_name'

    def get_next(self):
        if self.counter == 0:
            self.counter += 1
            self.name = 'cores'
            return self
        if self.counter == 1:
            self.counter += 1
            self.name = 'sockets'
            return self
        if self.counter == 2:
            self.counter += 1
            self.name = 'threads'
            return None


class FakeLibvirt(object):

    class libvirtError(Exception):
        def __init__(self, message=None):
            super(Exception, self).__init__(message)

        def get_error_code(self):
            return ''

        def get_error_domain(self):
            return ''

    VIR_CRED_AUTHNAME = None
    VIR_CRED_NOECHOPROMPT = None
    VIR_ERR_SYSTEM_ERROR = None
    VIR_FROM_REMOTE = None
    VIR_ERR_NO_DOMAIN = None
    VIR_ERR_OPERATION_INVALID = None
    nwfilterDefineXML = "<filter name='nova-project' chain='ipv4'>"
    VIR_MIGRATE_UNDEFINE_SOURCE = 1
    VIR_MIGRATE_PEER2PEER = 2
    VIR_MIGRATE_NON_SHARED_INC = 3

    def openReadOnly(self, uri):
        return FakeLibvirt()

    def openAuth(self, uri, auth, num):
        return FakeLibvirt()

    def getCapabilities(self):
        pass

    def listDomainsID(self):
        return [FakeDomain()]

    def lookupByID(self, id):
        return FakeDomain()

    def lookupByName(self, name):
        return FakeDomain()

    def defineXML(self, xml):
        return FakeDomain()

    def createXML(self, xml, launch_flags):
        return FakeDomain()

    def getType(self):
        return 'kvm'

    def getVersion(self):
        return 2

    def compareCPU(self, xml, index):
        return 1

    def listDefinedDomains(self):
        return ['instance_name']

    def nwfilterLookupByName(self, instance_filter_name):
        return FakeDomain()


class FakeDomain(object):

    def info(self):
        return ('state', '_max_mem', '_mem', '_num_cpu', '_cpu_time')

    def name(self):
        return 'test_inst_name'

    def destroy(self):
        pass

    def undefine(self):
        pass

    def attachDevice(self, xml):
        pass

    def XMLDesc(self, index):
        pass

    def detachDevice(self, xml):
        pass

    def snapshotCreateXML(self, xml, index):
        pass

    def delete(self, index):
        pass

    def createWithFlags(self, launch_flags):
        pass

    def suspend(self):
        pass

    def managedSave(self, index):
        pass

    def resume(self):
        pass

    def create(self):
        pass

    def vcpus(self):
        return (1, [1])

    def migrateToURI(self, uri, sum, name, bind):
        pass

    def interfaceStats(self, interface):
        return 'test_stats_up'

    def blockStats(self, disk):
        return 'test_stats_up'


class ConnectionTestCase(test.TestCase):
    """Test for nova.virt.libvirt.connection."""
    def setUp(self):
        super(ConnectionTestCase, self).setUp()
        self.connection = connection
        self.connection.libvirt = FakeLibvirt()
        self.connection.libxml2 = FakeLibxml2()

    @attr(kind='small')
    def test_get_connection(self):
        """Test for nova.virt.libvirt.connection.get_connection."""

        ref = self.connection.get_connection(read_only=True)

        self.assertEqual(True, isinstance(ref, connection.LibvirtConnection))
        self.assertNotEqual(None, self.connection.Template)

    @attr(kind='small')
    def test_get_connection_parameter(self):
        """Test for nova.virt.libvirt.connection.get_connection."""
        ref = self.connection.get_connection(read_only=False)
        self.assertEqual(False, ref.read_only)

    @attr(kind='small')
    def test_get_connection_parameter_import_libvirt(self):
        """Test for nova.virt.libvirt.connection.get_connection."""
        self.connection.libvirt = None
        # use try...exception because unittest environment
        # may be has not libvirt lib
        try:
            ref = self.connection.get_connection(read_only=False)
            self.assertNotEqual(None, ref)
            self.assertNotEqual(None, self.connection.libvirt)
            return
        except ImportError:
            self.assertEqual(None, self.connection.libvirt)
            return

        self.assertTrue(False, 'libvirt import error')

    @attr(kind='small')
    def test_get_connection_parameter_import_libxml2(self):
        """Test for nova.virt.libvirt.connection.get_connection."""
        self.connection.libxml2 = None
        # use try...exception because unittest environment
        # may be has not libxml2 lib
        try:
            ref = self.connection.get_connection(read_only=False)
            self.assertNotEqual(None, ref)
            self.assertNotEqual(None, self.connection.libxml2)
            return
        except ImportError:
            self.assertEqual(None, self.connection.libxml2)
            return

        self.assertTrue(False, 'libxml2 import error')

    @attr(kind='small')
    def test_late_load_cheetah(self):
        """Test for nova.virt.libvirt.connection._late_load_cheetah."""

        ref = self.connection._late_load_cheetah()

        self.assertNotEqual(None, self.connection.Template)
        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_get_eph_disk(self):
        """Test for nova.virt.libvirt.connection._get_eph_disk."""
        ephemeral = dict(num='1')
        ref = self.connection._get_eph_disk(ephemeral)

        self.assertEqual('disk.eph1', ref)


class LibvirtConnectionTestCase(test.TestCase):
    """Test for nova.virt.libvirt.connection.LibvirtConnection."""
    def setUp(self):
        super(LibvirtConnectionTestCase, self).setUp()
        connection.libvirt = FakeLibvirt()
        connection.libxml2 = FakeLibxml2()

        self.libvirtconnection = connection.LibvirtConnection(read_only=True)
        self.platform = sys.platform
        self.exe_flag = False
        FakeLibxml2.children = []

        self.temp_path = os.path.join(flags.FLAGS.instances_path,
                                 'instance-00000001/', '')
        try:
            os.makedirs(self.temp_path)
        except Exception:
            print 'testcase init error'
            pass

    def tearDown(self):
        super(LibvirtConnectionTestCase, self).tearDown()
        sys.platform = self.platform

        try:
            shutil.rmtree(flags.FLAGS.instances_path)
        except Exception:
            pass

    def _setup_networking(self,
                          instance_id, ip='1.2.3.4', flo_addr='1.2.1.2'):
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
        return network_ref

    def _create_instance(self, params=None):
        """Create a test instance"""
        if not params:
            params = {}

        inst = {}
        inst['image_ref'] = '1'
        inst['reservation_id'] = 'r-fakeres'
        inst['launch_time'] = '10'
        inst['user_id'] = 'fake'
        inst['project_id'] = 'fake'
        type_id = instance_types.get_instance_type_by_name('m1.tiny')['id']
        inst['instance_type_id'] = type_id
        inst['ami_launch_index'] = 0
        inst['host'] = 'host1'
        inst['local_gb'] = 10
        inst['config_drive'] = 1
        inst['kernel_id'] = 2
        inst['ramdisk_id'] = 3
        inst['config_drive_id'] = 1
        inst['key_data'] = 'ABCDEFG'

        inst.update(params)
        return db.instance_create(context.get_admin_context(), inst)

    @attr(kind='small')
    def test_init(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.init."""

        ref = connection.LibvirtConnection(read_only=True)
        self.assertEqual(None, ref._wrapped_conn)

    @attr(kind='small')
    def test_init_host(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .init_host. no need assert becuase it is pass implements"""

        self.libvirtconnection.init_host(host='host1')

    @attr(kind='small')
    def test_init_parameter(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.init."""
        def fake_openAuth(self, uri, auth, num):
            return 'a fake connection'

        self.stubs.Set(FakeLibvirt, 'openAuth', fake_openAuth)

        ref = connection.LibvirtConnection(read_only=False)
        ref._conn

        self.assertEqual('a fake connection', ref._wrapped_conn)

    @attr(kind='small')
    def test_get_connection_exception(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._get_connection."""
        def fake_getCapabilities(self):
            raise FakeLibvirt.libvirtError('a fake libvirtError')

        self.stubs.Set(FakeLibvirt, 'getCapabilities', fake_getCapabilities)

        ref = connection.LibvirtConnection(read_only=False)
        # first take a connection
        ref._conn

        # raise exception if test_connection failed
        try:
            ref._conn
            self.assertTrue(False, 'a fake libvirtError not raised')
        except FakeLibvirt.libvirtError, e:
            self.assertEqual('a fake libvirtError', str(e))

    @attr(kind='small')
    def test_get_connection_exception_reconnect(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._get_connection."""
        def fake_getCapabilities(self):
            raise FakeLibvirt.libvirtError('a fake libvirtError')

        self.stubs.Set(FakeLibvirt, 'getCapabilities', fake_getCapabilities)

        ref = connection.LibvirtConnection(read_only=False)
        # first take a connection
        ref._conn
        conn1 = ref._wrapped_conn

        # re make a connection if is remote error
        FakeLibvirt.VIR_ERR_SYSTEM_ERROR = ''
        FakeLibvirt.VIR_FROM_REMOTE = ''
        ref._conn
        self.assertNotEqual(conn1, ref._wrapped_conn)

    @attr(kind='small')
    def test_get_uri(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.get_uri."""
        ref = self.libvirtconnection.get_uri()

        self.assertEqual('qemu:///system', ref)

    @attr(kind='small')
    def test_get_uri_configuration(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.get_uri."""
        self.flags(libvirt_type='xen', libvirt_uri='test_uri')
        ref = self.libvirtconnection.get_uri()
        self.assertEqual('test_uri', ref)

        self.flags(libvirt_type='uml', libvirt_uri='test_uri')
        ref = self.libvirtconnection.get_uri()
        self.assertEqual('test_uri', ref)

        self.flags(libvirt_type='lxc', libvirt_uri='test_uri')
        ref = self.libvirtconnection.get_uri()
        self.assertEqual('test_uri', ref)

        self.flags(libvirt_type='other', libvirt_uri='test_uri')
        ref = self.libvirtconnection.get_uri()
        self.assertEqual('test_uri', ref)

    @attr(kind='small')
    def test_list_instances(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .list_instances."""
        ref = self.libvirtconnection.list_instances()

        self.assertEqual(['test_inst_name'], ref)

    @attr(kind='small')
    def test_list_instances_detail(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .list_instances_detail."""

        def fake_info(self):
            return (0x09, '_max_mem', '_mem', '_num_cpu', '_cpu_time')

        self.stubs.Set(FakeDomain, 'info', fake_info)

        ref = self.libvirtconnection.list_instances_detail()

        self.assertEqual('test_inst_name', ref[0].name)

    @attr(kind='small')
    def test_list_instances_detail_exception(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .list_instances_detail."""
        self.assertRaises(AssertionError,
                          self.libvirtconnection.list_instances_detail)

    @attr(kind='small')
    def test_plug_vifs(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .plug_vifs."""

        def fake_execute(network, mapping):
            self.assertEqual('1.2.3.4', mapping['ips'][0]['ip'])
            self.assertEqual('56:12:12:12:12:12', mapping['mac'])

        self.stubs.Set(self.libvirtconnection.vif_driver,
                       '_get_configurations', fake_execute)

        ins_ref = self._create_instance()
        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')
        ref = self.libvirtconnection.plug_vifs(ins_ref, ni)
        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_destroy(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.destroy."""

        ins_ref = self._create_instance()
        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        ref = self.libvirtconnection.destroy(ins_ref, ni, cleanup=True)
        self.assertEqual(True, ref)

    @attr(kind='small')
    def test_destroy_parameter_wait(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.destroy."""

        ins_ref = self._create_instance()
        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        ref = self.libvirtconnection.destroy(ins_ref, ni, cleanup=True)
        self.assertEqual(True, ref)

    @attr(kind='small')
    def test_destroy_exception_instance_not_found(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.destroy."""

        def fake_lookupByName(self, instance_name):
            raise FakeLibvirt.libvirtError('a fake libvirtError')

        self.stubs.Set(FakeLibvirt, 'lookupByName', fake_lookupByName)

        ins_ref = self._create_instance()
        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        FakeLibvirt.VIR_ERR_NO_DOMAIN = ''
        ref = self.libvirtconnection.destroy(ins_ref, ni, cleanup=True)
        self.assertEqual(True, ref)

    @attr(kind='small')
    def test_destroy_exception_had_shutdown(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.destroy."""

        def fake_destroy(self):
            raise FakeLibvirt.libvirtError('a fake libvirtError')

        self.stubs.Set(FakeDomain, 'destroy', fake_destroy)

        def fake_info(self):
            return (power_state.SHUTOFF, '', '', '', '')

        self.stubs.Set(FakeDomain, 'info', fake_info)

        ins_ref = self._create_instance()
        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        FakeLibvirt.VIR_ERR_OPERATION_INVALID = ''
        ref = self.libvirtconnection.destroy(ins_ref, ni, cleanup=True)
        self.assertEqual(True, ref)

    @attr(kind='small')
    def test_destroy_exception_state(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.destroy."""

        def fake_destroy(self):
            raise FakeLibvirt.libvirtError('a fake libvirtError')

        self.stubs.Set(FakeDomain, 'destroy', fake_destroy)

        def fake_info(self):
            return ('', '', '', '', '')

        self.stubs.Set(FakeDomain, 'info', fake_info)

        ins_ref = self._create_instance()
        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        FakeLibvirt.VIR_ERR_OPERATION_INVALID = ''
#        self.assertRaises(FakeLibvirt.libvirtError,
#                    self.libvirtconnection.destroy, ins_ref, ni, cleanup=True)
        self.libvirtconnection.destroy(ins_ref, ni, cleanup=True)
        # no error happend

    @attr(kind='small')
    def test_destroy_exception_undefine(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.destroy."""

        def fake_undefine(self):
            raise FakeLibvirt.libvirtError('a fake libvirtError')

        self.stubs.Set(FakeDomain, 'undefine', fake_undefine)

        ins_ref = self._create_instance()
        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

#        self.assertRaises(FakeLibvirt.libvirtError,
#                    self.libvirtconnection.destroy, ins_ref, ni, cleanup=True)
        self.libvirtconnection.destroy(ins_ref, ni, cleanup=True)
        # no error happend.

    @attr(kind='small')
    def test_destroy_confirm_resize(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.destroy
           and nova.virt.libvirt.connection.LibvirtConnection._cleanup.
           confirm_resize=True case """

        ins_ref = self._create_instance()
        target = os.path.join(flags.FLAGS.instances_path, ins_ref['name'])
        target += "_resize"
        utils.execute('mkdir', '-p', target)

        ref = self.libvirtconnection.destroy(ins_ref, None, cleanup=True,
                confirm_resize=True)
        self.assertEqual(True, ref)
        self.assertTrue(not os.path.exists(target))

    @attr(kind='small')
    def test_cleanup(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection._cleanup."""

        def fake_rmtree(path, ignore_errors=False, onerror=None):
            self.assertTrue(path.find('instance-0000000'))

        self.stubs.Set(shutil, 'rmtree', fake_rmtree)

        def fake_exists(path):
            return True

        self.stubs.Set(os.path, 'exists', fake_exists)

        ins_ref = self._create_instance()

        ref = self.libvirtconnection._cleanup(ins_ref)
        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_cleanup_configuration(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection._cleanup."""

        self.flags(libvirt_type='lxc')

        def fake_execute(cmd, *arg, **kwargs):
            self.assertTrue(cmd in ('mount', 'unmount'))
            return ('unmountok', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        def fake_rmtree(path, ignore_errors=False, onerror=None):
            self.assertTrue(path.find('instance-0000000'))

        self.stubs.Set(shutil, 'rmtree', fake_rmtree)

        def fake_exists(path):
            return True

        self.stubs.Set(os.path, 'exists', fake_exists)

        ins_ref = self._create_instance()

        ref = self.libvirtconnection._cleanup(ins_ref)
        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_attach_volume(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .attach_volume."""

        def fake_attachDevice(con, xml):
            self.assertTrue(xml.find('test_device_name'))
            self.assertTrue(xml.find('block'))

        self.stubs.Set(FakeDomain, 'attachDevice', fake_attachDevice)

        ins_ref = self._create_instance()

        device_path = '/dev/test_device'
        mountpoint = '/mnt/volume/test_device_name'
        ref = self.libvirtconnection.attach_volume(ins_ref['name'],
                                                   device_path, mountpoint)
        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_attach_volume_parameter_network_device(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .attach_volume."""
        def fake_attachDevice(con, xml):
            self.assertTrue(xml.find('test_device_name'))
            self.assertTrue(xml.find('network'))

        self.stubs.Set(FakeDomain, 'attachDevice', fake_attachDevice)

        ins_ref = self._create_instance()

        device_path = 'test_protocol://host/test_device'
        mountpoint = '/mnt/volume/test_device_name'
        ref = self.libvirtconnection.attach_volume(ins_ref['name'],
                                                   device_path, mountpoint)
        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_attach_volume_exception_invalid_device(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .attach_volume."""
        def fake_attachDevice(con, xml):
            self.assertTrue(xml.find('test_device_name'))
            self.assertTrue(xml.find('block'))

        self.stubs.Set(FakeDomain, 'attachDevice', fake_attachDevice)

        ins_ref = self._create_instance()

        # without /dev/ or ://
        device_path = '/host/test_device'
        mountpoint = '/mnt/volume/test_device_name'
        self.assertRaises(exception.InvalidDevicePath,
                self.libvirtconnection.attach_volume, ins_ref['name'],
                                                   device_path, mountpoint)

    @attr(kind='small')
    def test_get_disk_xml(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._get_disk_xml."""

        xml = """<disk><target dev='test_device_name'/></disk>"""
        device = 'test_device_name'

        ref = self.libvirtconnection._get_disk_xml(xml, device)

        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_get_disk_xml_parameter(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._get_disk_xml."""

        xml = """<disk><target dev='test_device_name'/></disk>"""
        device = 'test_device_name'

        FakeLibxml2.children = [FakeLibxml2('target')]

        ref = self.libvirtconnection._get_disk_xml(xml, device)

        self.assertTrue(ref.find('FakeLibxml2') > 0)

    @attr(kind='small')
    def test_get_disk_xml_exception(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._get_disk_xml."""

        def fake_parseDoc(self, xml):
            raise FakeLibvirt.libvirtError

        self.stubs.Set(FakeLibxml2, 'parseDoc', fake_parseDoc)

        xml = """<disk><target dev='test_device_name'/></disk>"""
        device = 'test_device_name'

        ref = self.libvirtconnection._get_disk_xml(xml, device)

        self.assertEquals(None, ref)

    @attr(kind='small')
    def test_detach_volume(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .detach_volume."""
        def fake_get_disk_xml(xml, device):
            return '<disk><target dev=\'test_device_name\'/></disk>'

        self.stubs.Set(self.libvirtconnection, '_get_disk_xml',
                       fake_get_disk_xml)

        def fake_detachDevice(con, xml):
            self.assertTrue(xml.find('test_device_name'))

        self.stubs.Set(FakeDomain, 'detachDevice', fake_detachDevice)

        ins_ref = self._create_instance()
        mountpoint = '/mnt/volume/test_device_name'
        ref = self.libvirtconnection.detach_volume(ins_ref['name'], mountpoint)
        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_detach_volume_exception(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .detach_volume."""
        def fake_get_disk_xml(xml, device):
            return ''

        self.stubs.Set(self.libvirtconnection, '_get_disk_xml',
                       fake_get_disk_xml)

        ins_ref = self._create_instance()
        mountpoint = '/mnt/volume/test_device_name'
        self.assertRaises(exception.DiskNotFound,
            self.libvirtconnection.detach_volume, ins_ref['name'], mountpoint)

    @attr(kind='small')
    def test_snapshot(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.snapshot."""

        def fake_get_image_service(context, image_href):
            return (image.glance.GlanceImageService(), 1)

        self.stubs.Set(image, 'get_image_service', fake_get_image_service)

        def fake_show(self, context, image_id):
            image = {
                'id': 1,
                'name': 'test image',
                'is_public': False,
                'size': None,
                'location': None,
                'disk_format': None,
                'container_format': None,
                'checksum': None,
                'created_at': utils.utcnow(),
                'updated_at': utils.utcnow(),
                'deleted_at': None,
                'deleted': None,
                'status': None,
                'properties': {'instance_id': '1', 'user_id': 'fake'},
            }
            return image

        self.stubs.Set(image.glance.GlanceImageService, 'show', fake_show)

        def fake_update(img, context, image_href, metadata, image_file):
            self.exe_flag = True

        self.stubs.Set(image.glance.GlanceImageService, 'update', fake_update)

        def fake_XMLDesc(con, index):
            return """
                <domain type='kvm'>
                    <devices>
                        <disk type='file'>
                            <source file='filename'/>
                        </disk>
                    </devices>
                </domain>
            """

        self.stubs.Set(FakeDomain, 'XMLDesc', fake_XMLDesc)

        def fake_execute(cmd, *arg, **kwargs):
            self.assertTrue(cmd in ('qemu-img'))
            f = open(arg[-1], 'w')
            f.close()
            return ('qemu-imged', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        def fake_snapshotCreateXML(con, xml, index):
            return FakeDomain()

        self.stubs.Set(FakeDomain, 'snapshotCreateXML', fake_snapshotCreateXML)

        ins_ref = self._create_instance()

        image_href = '/host/image/1'
        ref = self.libvirtconnection.snapshot(context.get_admin_context(),
                                              ins_ref, image_href)

        self.assertEqual(None, ref)
        self.assertEqual(True, self.exe_flag)

    @attr(kind='small')
    def test_snapshot_parameter(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.snapshot."""

        def fake_get_image_service(context, image_href):
            return (image.glance.GlanceImageService(), 1)

        self.stubs.Set(image, 'get_image_service', fake_get_image_service)

        def fake_show(self, context, image_id):
            image = {
                'id': 1,
                'name': 'test image',
                'is_public': False,
                'size': None,
                'location': None,
                'disk_format': 'ami',
                'container_format': None,
                'checksum': None,
                'created_at': utils.utcnow(),
                'updated_at': utils.utcnow(),
                'deleted_at': None,
                'deleted': None,
                'status': None,
                'properties': {'instance_id': '1', 'user_id': 'fake',
                               'architecture': 'arch'},
            }
            return image

        self.stubs.Set(image.glance.GlanceImageService, 'show', fake_show)

        def fake_update(img, context, image_href, metadata, image_file):
            self.exe_flag = True

        self.stubs.Set(image.glance.GlanceImageService, 'update', fake_update)

        def fake_XMLDesc(con, index):
            return """
                <domain type='kvm'>
                    <devices>
                        <disk type='file'>
                            <source file='filename'/>
                        </disk>
                    </devices>
                </domain>
            """

        self.stubs.Set(FakeDomain, 'XMLDesc', fake_XMLDesc)

        def fake_execute(cmd, *arg, **kwargs):
            self.assertTrue(cmd in ('qemu-img'))
            f = open(arg[-1], 'w')
            f.close()
            return ('qemu-imged', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        def fake_snapshotCreateXML(con, xml, index):
            return FakeDomain()

        self.stubs.Set(FakeDomain, 'snapshotCreateXML', fake_snapshotCreateXML)

        ins_ref = self._create_instance()

        image_href = '/host/image/1'
        ref = self.libvirtconnection.snapshot(context.get_admin_context(),
                                              ins_ref, image_href)

        self.assertEqual(None, ref)
        self.assertEqual(True, self.exe_flag)

    @attr(kind='small')
    def test_reboot(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.reboot."""

        def fake_setup_basic_filtering(instance, network_info):
            pass

        self.stubs.Set(self.libvirtconnection.firewall_driver,
                       'setup_basic_filtering', fake_setup_basic_filtering)

        def fake_info(self):
            return (power_state.RUNNING, '', '', '', '')

        self.stubs.Set(FakeDomain, 'info', fake_info)

        ins_ref = self._create_instance()
        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        ref = self.libvirtconnection.reboot(ins_ref, ni, xml=None)

        self.assertTrue(isinstance(ref, event.Event))
        greenthread.sleep(0)

    @attr(kind='small')
    def test_reboot_exception_notfound(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.reboot."""

        def fake_setup_basic_filtering(instance, network_info):
            pass

        self.stubs.Set(self.libvirtconnection.firewall_driver,
                       'setup_basic_filtering', fake_setup_basic_filtering)

        def fake_info(self):
            raise exception.NotFound

        self.stubs.Set(FakeDomain, 'info', fake_info)

        ins_ref = self._create_instance()
        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        ref = self.libvirtconnection.reboot(ins_ref, ni, xml=None)

        self.assertTrue(isinstance(ref, event.Event))
        greenthread.sleep(0)

    @attr(kind='small')
    def test_reboot_exception(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.reboot.
        wrap libvirt api exception to exception.Error if failed"""
        def fake_setup_basic_filtering(instance, network_info):
            pass

        self.stubs.Set(self.libvirtconnection.firewall_driver,
                       'setup_basic_filtering', fake_setup_basic_filtering)

        def fake_destroy(self):
            raise FakeLibvirt.libvirtError('a fake libvirtError')

        self.stubs.Set(FakeDomain, 'destroy', fake_destroy)

        ins_ref = self._create_instance()
        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

#        self.assertRaises(exception.Error,
#                self.libvirtconnection.reboot, ins_ref, ni, xml=None)
        self.libvirtconnection.reboot(ins_ref, ni, xml=None)
        # not occured any exception.


    @attr(kind='small')
    def test_pause(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.pause."""
        self.counter = 0

        def fake_suspend(dom):
            self.counter += 1

        self.stubs.Set(FakeDomain, 'suspend', fake_suspend)

        ins_ref = self._create_instance()

        self.libvirtconnection.pause(ins_ref, callback=None)

        self.assertEqual(1, self.counter)

    @attr(kind='small')
    def test_unpause(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.unpause."""
        self.counter = 0

        def fake_resume(dom):
            self.counter += 1

        self.stubs.Set(FakeDomain, 'resume', fake_resume)

        ins_ref = self._create_instance()

        self.libvirtconnection.unpause(ins_ref, callback=None)

        self.assertEqual(1, self.counter)

    @attr(kind='small')
    def test_suspend(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.suspend."""
        self.counter = 0

        def fake_managedSave(dom, index):
            self.counter += 1

        self.stubs.Set(FakeDomain, 'managedSave', fake_managedSave)

        ins_ref = self._create_instance()

        self.libvirtconnection.suspend(ins_ref, callback=None)

        self.assertEqual(1, self.counter)

    @attr(kind='small')
    def test_resume(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.resume."""
        self.counter = 0

        def fake_create(dom):
            self.counter += 1

        self.stubs.Set(FakeDomain, 'create', fake_create)

        ins_ref = self._create_instance()

        self.libvirtconnection.resume(ins_ref, callback=None)

        self.assertEqual(1, self.counter)

    @attr(kind='small')
    def test_rescue(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.rescue."""
        self.libvirtconnection = connection.get_connection(read_only=True)

        def fake_XMLDesc(con, index):
            return """
                <domain type='kvm'>
                    <devices>
                        <serial type='pty'>
                            <source path='filename'/>
                        </serial>
                    </devices>
                </domain>
            """

        self.stubs.Set(FakeDomain, 'XMLDesc', fake_XMLDesc)

        def fake_fetch_image(context, target, image_id, user_id, project_id,
                     size=None):
            pass

        self.stubs.Set(self.libvirtconnection,
                       '_fetch_image', fake_fetch_image)

        def fake_reboot(instance, network_info, xml=None):
            self.exe_flag = True

        self.stubs.Set(self.libvirtconnection,
                       'reboot', fake_reboot)

        def fake_execute(cmd, *arg, **kwargs):
            return ('cmdok', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        ins_ref = self._create_instance()

        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        ref = self.libvirtconnection.rescue(context.get_admin_context(),
                        instance=ins_ref, callback=None, network_info=ni)
        greenthread.sleep(0)

        self.assertEqual(None, ref)
        self.assertEqual(True, self.exe_flag)

    @attr(kind='small')
    def test_unrescue(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.unrescue."""
        self.libvirtconnection = connection.get_connection(read_only=True)

        def fake_reboot(instance, network_info, xml=None):
            self.exe_flag = True

        self.stubs.Set(self.libvirtconnection,
                       'reboot', fake_reboot)

        ins_ref = self._create_instance()

        unrescue_xml_path = os.path.join(flags.FLAGS.instances_path,
                                         ins_ref['name'], 'unrescue.xml')
        f = open(unrescue_xml_path, 'w')
        f.close()

        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        ref = self.libvirtconnection.unrescue(
                        instance=ins_ref, callback=None, network_info=ni)
        greenthread.sleep(0)

        self.assertEqual(None, ref)
        self.assertEqual(True, self.exe_flag)

    @attr(kind='small')
    def test_poll_rescued_instances(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .poll_rescued_instances.
        no need assert becuase it is pass implements"""

        self.libvirtconnection.poll_rescued_instances(None)

    @attr(kind='small')
    def test_spawn(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.spawn."""

        def fake_setup_basic_filtering(instance, network_info):
            pass

        self.stubs.Set(self.libvirtconnection.firewall_driver,
                       'setup_basic_filtering', fake_setup_basic_filtering)

        def fake_to_xml(self, instance, network_info, rescue=False,
               block_device_info=None):
            return """
                <domain type='kvm'>
                    <devices>
                        <disk type='file'>
                            <source file='filename'/>
                        </disk>
                    </devices>
                </domain>
            """

        self.stubs.Set(self.libvirtconnection, 'to_xml', fake_to_xml)

        def fake_info(con):
            self.exe_flag = True
            return (power_state.RUNNING, '', '', '', '')

        self.stubs.Set(FakeDomain, 'info', fake_info)

        def fake_fetch_image(context, target, image_id, user_id, project_id,
                     size=None):
            pass

        self.stubs.Set(self.libvirtconnection,
                       '_fetch_image', fake_fetch_image)

        def fake_execute(cmd, *arg, **kwargs):
            return ('cmdok', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        ins_ref = self._create_instance()

        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        ref = self.libvirtconnection.spawn(context.get_admin_context(),
                instance=ins_ref, network_info=ni, block_device_info=None)

        greenthread.sleep(0.5)
        self.assertTrue(isinstance(ref, event.Event))
        self.assertTrue(self.exe_flag)

    @attr(kind='small')
    def test_flush_xen_console(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._flush_xen_console."""

        def fake_execute(cmd, *arg, **kwargs):
            self.assertTrue(cmd in ('dd'))
            return ('ddok', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        virsh_output = ['/dev/']
        ref = self.libvirtconnection._flush_xen_console(virsh_output)
        self.assertEqual('ddok', ref)

    @attr(kind='small')
    def test_flush_xen_console_parameter(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._flush_xen_console."""

        virsh_output = ['/notdev/']
        ref = self.libvirtconnection._flush_xen_console(virsh_output)
        self.assertEqual('', ref)

    @attr(kind='small')
    def test_get_console_output(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_console_output."""

        def fake_dump_file(filepath):
            return 'file contents'

        self.stubs.Set(self.libvirtconnection,
                       '_dump_file', fake_dump_file)

        def fake_flush_xen_console(virsh_output):
            return 'file data'

        self.stubs.Set(self.libvirtconnection,
                       '_flush_xen_console', fake_flush_xen_console)

        def fake_append_to_file(data, fpath):
            return 'fpath'

        self.stubs.Set(self.libvirtconnection,
                       '_append_to_file', fake_append_to_file)

        def fake_execute(cmd, *arg, **kwargs):
            self.assertTrue(cmd in ('chown', 'virsh'))
            return ('ddok', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        ins_ref = self._create_instance()

        self.flags(libvirt_type='xen')
        ref = self.libvirtconnection.get_console_output(ins_ref)

        self.assertEqual('file contents', ref)

    @test.skip_test('because get_console_output not implement for lxc ')
    @attr(kind='small')
    def test_get_console_output_configuration_lxc(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_console_output."""

        def fake_dump_file(filepath):
            return 'file contents'

        self.stubs.Set(self.libvirtconnection,
                       '_dump_file', fake_dump_file)

        def fake_flush_xen_console(virsh_output):
            return 'file data'

        self.stubs.Set(self.libvirtconnection,
                       '_flush_xen_console', fake_flush_xen_console)

        def fake_append_to_file(data, fpath):
            return 'fpath'

        self.stubs.Set(self.libvirtconnection,
                       '_append_to_file', fake_append_to_file)

        def fake_execute(cmd, *arg, **kwargs):
            self.assertTrue(cmd in ('chown', 'virsh'))
            return ('ddok', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        ins_ref = self._create_instance()

        self.flags(libvirt_type='lxc')
        ref = self.libvirtconnection.get_console_output(ins_ref)

        self.assertEqual('', ref)

    @attr(kind='small')
    def test_get_console_output_configuration_other(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_console_output."""

        def fake_dump_file(filepath):
            return 'file contents'

        self.stubs.Set(self.libvirtconnection,
                       '_dump_file', fake_dump_file)

        def fake_flush_xen_console(virsh_output):
            return 'file data'

        self.stubs.Set(self.libvirtconnection,
                       '_flush_xen_console', fake_flush_xen_console)

        def fake_append_to_file(data, fpath):
            return 'fpath'

        self.stubs.Set(self.libvirtconnection,
                       '_append_to_file', fake_append_to_file)

        def fake_execute(cmd, *arg, **kwargs):
            self.assertTrue(cmd in ('chown', 'virsh'))
            return ('ddok', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        ins_ref = self._create_instance()

        self.flags(libvirt_type='')
        ref = self.libvirtconnection.get_console_output(ins_ref)

        self.assertEqual('file contents', ref)

    @attr(kind='small')
    def test_append_to_file(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._append_to_file."""

        test_contents = 'test_contents'
        tmp = os.path.join(self.temp_path, '', 'test.txt')
        f = open(tmp, 'w')
        f.write(test_contents)
        f.close()

        ref = self.libvirtconnection._append_to_file(test_contents, tmp)

        self.assertEqual(tmp, ref)

    @attr(kind='small')
    def test_dump_file(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._dump_file."""

        test_contents = 'test_contents'
        tmp = os.path.join(self.temp_path, '', 'test.txt')
        f = open(tmp, 'w')
        f.write(test_contents)
        f.close()

        ref = self.libvirtconnection._dump_file(tmp)

        self.assertEqual(test_contents, ref)

    @attr(kind='small')
    def test_get_ajax_console(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_ajax_console."""

        def fake_execute(cmd, *arg, **kwargs):
            if cmd == 'netcat':
                raise exception.ProcessExecutionError
            return ('cmdok', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        def fake_XMLDesc(con, index):
            return """
                <domain type='kvm'>
                    <devices>
                        <serial type='pty'>
                            <source path='filename'/>
                        </serial>
                    </devices>
                </domain>
            """

        self.stubs.Set(FakeDomain, 'XMLDesc', fake_XMLDesc)

        ins_ref = self._create_instance()

        ref = self.libvirtconnection.get_ajax_console(ins_ref)

        self.assertEqual('host1', ref['host'])
        self.assertTrue(ref['token'])
        self.assertTrue(ref['port'])

    @attr(kind='small')
    def test_get_ajax_console_exception(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_ajax_console."""

        def fake_execute(cmd, *arg, **kwargs):
            return ('cmdok', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        ins_ref = self._create_instance()

        self.assertRaises(Exception,
                        self.libvirtconnection.get_ajax_console, ins_ref)

    @attr(kind='small')
    def test_get_host_ip_addr_configuration(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_host_ip_addr."""
        ip = '99.99.99.99'
        self.flags(my_ip=ip)
        ref = self.libvirtconnection.get_host_ip_addr()

        self.assertEqual(ip, ref)

    @attr(kind='small')
    def test_get_vnc_console(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_vnc_console."""

        def fake_XMLDesc(con, index):
            return """
                <domain type='kvm'>
                    <devices>
                        <graphics type='vnc' port='9876'>
                        </graphics>
                    </devices>
                </domain>
            """

        self.stubs.Set(FakeDomain, 'XMLDesc', fake_XMLDesc)

        ins_ref = self._create_instance()

        ref = self.libvirtconnection.get_vnc_console(ins_ref)

        self.assertEqual('host1', ref['host'])
        self.assertTrue(ref['token'])
        self.assertTrue('9876', ref['port'])

    @attr(kind='small')
    def test_cache_image(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._cache_image."""

        def fake_execute(cmd, *arg, **kwargs):
            return ('cmdok', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        def fake_exists(path):
            return False

        self.stubs.Set(os.path, 'exists', fake_exists)

        def fake_mkdir(path):
            pass

        self.stubs.Set(os, 'mkdir', fake_mkdir)

        def dummy(target):
            self.assertTrue(target.find('test_fname'))

        target = 'test_target'
        fname = 'test_fname'
        ref = self.libvirtconnection._cache_image(dummy, target, fname)

        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_fetch_image(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._fetch_image."""

        def fake_fetch_to_raw(context, image_href, path, user_id,
                              project_id):
            self.exe_flag = True

        self.stubs.Set(virt.images, 'fetch_to_raw',
                       fake_fetch_to_raw)

        target = 'test_target'
        ref = self.libvirtconnection._fetch_image(context.get_admin_context(),
                            target=target, image_id=1, user_id='fake',
                            project_id='fake', size=None)

        self.assertEqual(None, ref)
        self.assertEqual(True, self.exe_flag)

    @attr(kind='small')
    def test_create_local(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._create_local."""

        def fake_execute(cmd, *arg, **kwargs):
            return ('cmdok', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        target = 'test_target'
        ref = self.libvirtconnection._create_local(target=target,
                                 local_size=10, unit='G', fs_format=None)

        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_create_image(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._create_image."""

        self.libvirtconnection = connection.get_connection(read_only=True)

        def fake_fetch_image(context, target, image_id, user_id, project_id,
                     size=None):
            self.exe_flag = True

        self.stubs.Set(self.libvirtconnection,
                       '_fetch_image', fake_fetch_image)

        def fake_execute(cmd, *arg, **kwargs):
            return ('cmdok', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        ins_ref = self._create_instance()

        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        xml = self.libvirtconnection.to_xml(instance=ins_ref, network_info=ni,
                                            rescue=True)
        ref = self.libvirtconnection._create_image(context.get_admin_context(),
                inst=ins_ref, libvirt_xml=xml, suffix='',
                      disk_images=None, network_info=ni,
                      block_device_info=None)

        self.assertEqual(None, ref)
        self.assertEqual(True, self.exe_flag)

    @attr(kind='small')
    def test_create_image_parameter(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._create_image."""

        self.flags(libvirt_type='lxc')
        self.libvirtconnection = connection.get_connection(read_only=True)

        def fake_fetch_to_raw(context, image_href, path, user_id,
                              project_id):
            self.exe_flag = True

        self.stubs.Set(virt.images, 'fetch_to_raw',
                       fake_fetch_to_raw)

        def fake_execute(cmd, *arg, **kwargs):
            return ('cmdok', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        def fake_setup_container(image, container_dir=None, nbd=False):
            pass

        self.stubs.Set(virt.disk,
                       'setup_container', fake_setup_container)

        params = dict(config_drive='', config_drive_id='')
        ins_ref = self._create_instance(params)

        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        ni[0][0]['injected'] = True
        xml = self.libvirtconnection.to_xml(instance=ins_ref, network_info=ni,
                                            rescue=True)
        block_info = dict(ephemerals=[dict(num=1, size=6, device_name='ep1')],
                          root_device_name='/rootpath',
                          swap={'device_name': 'device1', 'swap_size': 10})

        ref = self.libvirtconnection._create_image(context.get_admin_context(),
                inst=ins_ref, libvirt_xml=xml, suffix='',
                      disk_images=None, network_info=ni,
                      block_device_info=block_info)

        self.assertEqual(None, ref)
        self.assertEqual(True, self.exe_flag)

    @attr(kind='small')
    def test_create_image_single_local_disk(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._create_image."""

        self.flags(libvirt_single_local_disk=True)
        self.libvirtconnection = connection.get_connection(read_only=True)

        def fake_fetch_image(context, target, image_id, user_id, project_id,
                     size=None):
            self.exe_flag = True

        self.stubs.Set(self.libvirtconnection,
                       '_fetch_image', fake_fetch_image)

        def fake_execute(cmd, *arg, **kwargs):
            return ('cmdok', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        ins_ref = self._create_instance()

        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        xml = self.libvirtconnection.to_xml(instance=ins_ref, network_info=ni,
                                            rescue=True)
        ref = self.libvirtconnection._create_image(context.get_admin_context(),
                inst=ins_ref, libvirt_xml=xml, suffix='',
                      disk_images=None, network_info=ni,
                      block_device_info=None)

        self.assertEqual(None, ref)
        self.assertEqual(True, self.exe_flag)

    @attr(kind='small')
    def test_prepare_xml_info(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._prepare_xml_info."""

        ins_ref = self._create_instance()
        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        ref = self.libvirtconnection._prepare_xml_info(instance=ins_ref,
                network_info=ni, rescue=False, block_device_info=None)

        self.assertEqual('1.2.3.4', ref['nics'][0]['ip_address'])
        self.assertTrue(ref['ramdisk'].find('00000001/ramdisk'))
        self.assertEqual([], ref['volumes'])
        self.assertTrue(ref['local_device'])

    @attr(kind='small')
    def test_prepare_xml_info_parameter(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._prepare_xml_info."""

        self.flags(use_cow_images=False)

        ins_ref = self._create_instance()
        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        block_info = dict(block_device_mapping=[dict(mount_device='/volume1',
                                type='type1', protocol=None,
                                name='volume1', device_path='/dev/test/')],
                          root_device_name='/rootpath',
                          swap={'device_name': 'device1', 'swap_size': 10})
        ref = self.libvirtconnection._prepare_xml_info(instance=ins_ref,
                network_info=ni, rescue=False, block_device_info=block_info)

        result = {'protocol': None, 'device_path': '/dev/test/',
                  'type': 'block', 'name': None, 'mount_device': '/volume1'}

        self.assertEqual(result, ref['volumes'][0])

    @attr(kind='small')
    def test_prepare_xml_info_parameter_swap(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._prepare_xml_info."""

        def fake_swap_is_usable(swap):
            return False

        self.stubs.Set(virt.driver, 'swap_is_usable', fake_swap_is_usable)
        self.flags(use_cow_images=False)

        instance_types.create(name='test_type', memory=10,
                vcpus=1, local_gb=5, flavorid=10, swap=20,
                rxtx_quota=0, rxtx_cap=0)
        ins_type = instance_types.get_instance_type_by_name('test_type')
        params = dict(instance_type_id=ins_type['id'])
        ins_ref = self._create_instance(params)

        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        block_info = dict(block_device_mapping=[dict(mount_device='/volume1',
                                type='type1', protocol=None,
                                name='volume1', device_path='/dev/test/')],
                          root_device_name='/rootpath',
                          swap={'device_name': 'device1', 'swap_size': 10})
        ref = self.libvirtconnection._prepare_xml_info(instance=ins_ref,
                network_info=ni, rescue=False, block_device_info=block_info)

        result = {'protocol': None, 'device_path': '/dev/test/',
                  'type': 'block', 'name': None, 'mount_device': '/volume1'}

        self.assertEqual(result, ref['volumes'][0])

    @attr(kind='small')
    def test_prepare_xml_info_single_local_disk(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._prepare_xml_info."""

        self.flags(libvirt_single_local_disk=True)
        ins_ref = self._create_instance()
        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        ref = self.libvirtconnection._prepare_xml_info(instance=ins_ref,
                network_info=ni, rescue=False, block_device_info=None)

        self.assertEqual('1.2.3.4', ref['nics'][0]['ip_address'])
        self.assertTrue(ref['ramdisk'].find('00000001/ramdisk'))
        self.assertEqual([], ref['volumes'])
        self.assertTrue(not ref['local_device'])

    @attr(kind='small')
    def test_to_xml(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection.to_xml."""

        self.libvirtconnection = connection.get_connection(read_only=True)
        ins_ref = self._create_instance()
        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        block_info = dict(block_device_mapping=[dict(mount_device='/volume1',
                                type='type1', protocol=None,
                                name='volume1', device_path='/dev/test/')],
                          root_device_name='/rootpath',
                          swap={'device_name': 'device1', 'swap_size': 10})

        ref = self.libvirtconnection.to_xml(instance=ins_ref,
                network_info=ni, rescue=False, block_device_info=block_info)

        self.assertTrue(ref.find("domain type='kvm'>"))
        self.assertTrue(ref.find("<name>instance-00000001</name>"))
        self.assertTrue(ref.find("<target dev='/volume1' bus='virtio'/>"))
        self.assertTrue(ref.find("<mac address='56:12:12:12:12:12'/>"))

    @attr(kind='small')
    def test_lookup_by_name_exception(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._lookup_by_name."""

        def fake_lookupByName(conn, instance_name):
            raise FakeLibvirt.libvirtError('a fake libvirtError')

        self.stubs.Set(FakeLibvirt, 'lookupByName', fake_lookupByName)

        FakeLibvirt.VIR_ERR_NO_DOMAIN = None

        ins_ref = self._create_instance()

        self.assertRaises(exception.Error,
                    self.libvirtconnection._lookup_by_name, ins_ref['name'])

    @attr(kind='small')
    def test_create_new_domain(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        ._create_new_domain."""

        def fake_createXML(con, xml, launch_flags):
            return 'a fake domain'

        self.stubs.Set(FakeLibvirt, 'createXML', fake_createXML)

        xml = '<test xml/>'
        ref = self.libvirtconnection._create_new_domain(xml=xml,
                                        persistent=False, launch_flags=0)

        self.assertEqual('a fake domain', ref)

    @attr(kind='small')
    def test_get_diagnostics(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_diagnostics."""

        ins_ref = self._create_instance()
        self.assertRaises(exception.ApiError,
                    self.libvirtconnection.get_diagnostics, ins_ref['name'])

    @attr(kind='small')
    def test_get_disks(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_disks."""

        ins_ref = self._create_instance()
        ref = self.libvirtconnection.get_disks(ins_ref['name'])
        self.assertEqual([], ref)

    @attr(kind='small')
    def test_get_disks_parameter(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_disks."""

        FakeLibxml2.children = [FakeLibxml2('target')]
        ins_ref = self._create_instance()

        ref = self.libvirtconnection.get_disks(ins_ref['name'])
        self.assertEqual('test_device_name', ref[0])

    @attr(kind='small')
    def test_get_disks_exception(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_disks."""

        def fake_parseDoc(self, xml):
            raise FakeLibvirt.libvirtError

        self.stubs.Set(FakeLibxml2, 'parseDoc', fake_parseDoc)

        ins_ref = self._create_instance()
        ref = self.libvirtconnection.get_disks(ins_ref['name'])
        self.assertEqual([], ref)

    @attr(kind='small')
    def test_get_interfaces(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_interfaces."""

        ins_ref = self._create_instance()
        ref = self.libvirtconnection.get_interfaces(ins_ref['name'])
        self.assertEqual([], ref)

    @attr(kind='small')
    def test_get_interfaces_parameter(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_interfaces."""

        FakeLibxml2.children = [FakeLibxml2('target')]

        ins_ref = self._create_instance()
        ref = self.libvirtconnection.get_interfaces(ins_ref['name'])
        self.assertEqual('test_device_name', ref[0])

    @attr(kind='small')
    def test_get_interfaces_exception(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_interfaces."""

        def fake_parseDoc(self, xml):
            raise FakeLibvirt.libvirtError

        self.stubs.Set(FakeLibxml2, 'parseDoc', fake_parseDoc)

        ins_ref = self._create_instance()
        ref = self.libvirtconnection.get_interfaces(ins_ref['name'])
        self.assertEqual([], ref)

    @attr(kind='small')
    def test_get_vcpu_total(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_vcpu_total."""
        ref = self.libvirtconnection.get_vcpu_total()

        self.assertEqual(True, ref > 0)

    @attr(kind='small')
    def test_get_vcpu_total_exception(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_vcpu_total."""

        def fake_cpu_count():
            raise NotImplementedError

        self.stubs.Set(multiprocessing, 'cpu_count', fake_cpu_count)

        ref = self.libvirtconnection.get_vcpu_total()

        self.assertEqual(0, ref)

    @attr(kind='small')
    def test_get_memory_mb_total(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_memory_mb_total."""
        ref = self.libvirtconnection.get_memory_mb_total()
        self.assertEqual(True, ref > 0)

    @attr(kind='small')
    def test_get_memory_mb_used(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_memory_mb_used."""

        sys.platform = 'win32'

        ref = self.libvirtconnection.get_memory_mb_used()

        self.assertEqual(0, ref)

    @attr(kind='small')
    def test_get_hypervisor_type(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_hypervisor_type."""
        ref = self.libvirtconnection.get_hypervisor_type()
        self.assertEqual('kvm', ref)

    @attr(kind='small')
    def test_get_hypervisor_version(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_hypervisor_version."""
        ref = self.libvirtconnection.get_hypervisor_version()
        self.assertEqual(2, ref)

    @attr(kind='small')
    def test_get_hypervisor_version_exception(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_hypervisor_version."""

        setattr(self.libvirtconnection._conn, 'getVersion', None)

        self.assertRaises(exception.Error,
                          self.libvirtconnection.get_hypervisor_version)

    @attr(kind='small')
    def test_get_cpu_info(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_cpu_info."""
        def fake_getCapabilities(con):
            return """
                <domain type='kvm'>
                    <devices>
                        <disk type='file'>
                            <source file='filename'/>
                        </disk>
                    </devices>
                </domain>
            """

        self.stubs.Set(FakeLibvirt, 'getCapabilities', fake_getCapabilities)

        ref = self.libvirtconnection.get_cpu_info()

        self.assertTrue(ref.find('model'))
        self.assertTrue(ref.find('vendor'))
        self.assertTrue(ref.find('1024'))
        self.assertTrue(ref.find('9999'))

    @attr(kind='small')
    def test_get_cpu_info_exception_count(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_cpu_info."""
        def fake_getCapabilities(con):
            return """
                <domain type='kvm'>
                    <devices>
                        <disk type='file'>
                            <source file='filename'/>
                        </disk>
                    </devices>
                </domain>
            """

        self.stubs.Set(FakeLibvirt, 'getCapabilities', fake_getCapabilities)

        def fake_xpathEval(self, path):
            return []

        self.stubs.Set(FakeLibxml2, 'xpathEval', fake_xpathEval)

        self.assertRaises(exception.InvalidCPUInfo,
                          self.libvirtconnection.get_cpu_info)

    @attr(kind='small')
    def test_get_cpu_info_exception_topology(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_cpu_info."""
        def fake_getCapabilities(con):
            return """
                <domain type='kvm'>
                    <devices>
                        <disk type='file'>
                            <source file='filename'/>
                        </disk>
                    </devices>
                </domain>
            """

        self.stubs.Set(FakeLibvirt, 'getCapabilities', fake_getCapabilities)

        def fake_get_next(self):
            if self.counter == 0:
                self.counter += 1
                self.name = 'cores'
                return self
            return None

        self.stubs.Set(FakeLibxml2, 'get_next', fake_get_next)

        self.assertRaises(exception.InvalidCPUInfo,
                          self.libvirtconnection.get_cpu_info)

    @attr(kind='small')
    def test_block_stats(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .block_stats."""

        ref = self.libvirtconnection.block_stats(
                                    instance_name='test', disk='test')

        self.assertEqual('test_stats_up', ref)

    @attr(kind='small')
    def test_interface_stats(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .interface_stats."""

        ref = self.libvirtconnection.interface_stats(
                                    instance_name='test', interface='test')

        self.assertEqual('test_stats_up', ref)

    @attr(kind='small')
    def test_get_console_pool_info(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_console_pool_info. no need assert becuase it is pass implements"""

        self.libvirtconnection.get_console_pool_info(console_type=None)

    @attr(kind='small')
    def test_refresh_security_group_rules(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .refresh_security_group_rules."""

        def fake_refresh_security_group_rules(security_group_id):
            self.exe_flag = True

        self.stubs.Set(self.libvirtconnection.firewall_driver,
                        'refresh_security_group_rules',
                        fake_refresh_security_group_rules)

        ref = self.libvirtconnection.refresh_security_group_rules(
                                               security_group_id='1')

        self.assertEqual(None, ref)
        self.assertEqual(True, self.exe_flag)

    @attr(kind='small')
    def test_refresh_security_group_members(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .refresh_security_group_members."""

        def fake_refresh_security_group_members(security_group_id):
            self.exe_flag = True

        self.stubs.Set(self.libvirtconnection.firewall_driver,
                        'refresh_security_group_members',
                        fake_refresh_security_group_members)

        ref = self.libvirtconnection.refresh_security_group_members(
                                               security_group_id='1')

        self.assertEqual(None, ref)
        self.assertEqual(True, self.exe_flag)

    @attr(kind='small')
    def test_refresh_provider_fw_rules(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .refresh_provider_fw_rules."""

        def fake_refresh_provider_fw_rules():
            self.exe_flag = True

        self.stubs.Set(self.libvirtconnection.firewall_driver,
                        'refresh_provider_fw_rules',
                        fake_refresh_provider_fw_rules)

        ref = self.libvirtconnection.refresh_provider_fw_rules()

        self.assertEqual(None, ref)
        self.assertEqual(True, self.exe_flag)

    @attr(kind='small')
    def test_update_available_resource(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .update_available_resource."""

        topic = 'compute'
        host = 'host1'
        sv = dict(host=host, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        nd = dict(service_id=sv_ref['id'], vcpus='12', memory_mb='10',
            local_gb='20', vcpus_used='3', memory_mb_used='4', cpu_info='s',
            local_gb_used='5', hypervisor_type='hdest', hypervisor_version='1')
        compute_ref = db.compute_node_create(context.get_admin_context(),
                                             values=nd)

        ref = self.libvirtconnection.update_available_resource(
                                        context.get_admin_context(), host)

        self.assertEqual(None, ref)

        compute_ref = db.compute_node_get(context.get_admin_context(),
                                             compute_id=compute_ref['id'])

        self.assertEqual('kvm', compute_ref['hypervisor_type'])
        self.assertEqual(2, compute_ref['hypervisor_version'])

    @attr(kind='small')
    def test_update_available_resource_parameter(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .update_available_resource."""

        topic = 'compute'
        host = 'host1'
        sv = dict(host=host, topic=topic)
        sv_ref = db.service_create(context.get_admin_context(), values=sv)

        ref = self.libvirtconnection.update_available_resource(
                                        context.get_admin_context(), host)

        self.assertEqual(None, ref)

        compute_ref = db.compute_node_get(context.get_admin_context(),
                                             compute_id=1)

        self.assertEqual('kvm', compute_ref['hypervisor_type'])
        self.assertEqual(2, compute_ref['hypervisor_version'])

    @attr(kind='small')
    def test_update_available_resource_exception(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .update_available_resource."""

        host = 'host1'
        self.assertRaises(exception.ComputeServiceUnavailable,
                    self.libvirtconnection.update_available_resource,
                                        context.get_admin_context(), host)

    @attr(kind='small')
    def test_compare_cpu(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .compare_cpu."""

        self.libvirtconnection = connection.get_connection(read_only=True)

        def fake_compareCPU(con, xml, index):
            self.assertTrue(xml.find(
                    '<topology sockets="9999" cores="2" threads="1024"/>'))
            return 1

        self.stubs.Set(FakeLibvirt, 'compareCPU', fake_compareCPU)

        cpu = {"vendor": "amd", "model": "amd1234", "arch": "x86",
               "features": ["test_contents"], "topology":
                    {"cores": "2", "threads": "1024", "sockets": "9999"}}

        ref = self.libvirtconnection.compare_cpu(cpu_info=utils.dumps(cpu))
        self.assertEqual(None, ref)

    @test.skip_test('fixes next')
    @attr(kind='small')
    def test_compare_cpu_exception(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .compare_cpu."""

        self.libvirtconnection = connection.get_connection(read_only=True)

        def fake_compareCPU(con, xml, index):
            self.assertTrue(xml.find(
                    '<topology sockets="9999" cores="2" threads="1024"/>'))
            raise FakeLibvirt.libvirtError('a fake libvirt exception')

        self.stubs.Set(FakeLibvirt, 'compareCPU', fake_compareCPU)

        cpu = {"vendor": "amd", "model": "amd1234", "arch": "x86",
               "features": ["test_contents"], "topology":
                    {"cores": "2", "threads": "1024", "sockets": "9999"}}

        self.assertRaises(exception.Error,
                self.libvirtconnection.compare_cpu, cpu_info=utils.dumps(cpu))

    @attr(kind='small')
    def test_compare_cpu_exception_invalid_cpu(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .compare_cpu."""

        self.libvirtconnection = connection.get_connection(read_only=True)

        def fake_compareCPU(con, xml, index):
            self.assertTrue(xml.find(
                    '<topology sockets="9999" cores="2" threads="1024"/>'))
            return 0

        self.stubs.Set(FakeLibvirt, 'compareCPU', fake_compareCPU)

        cpu = {"vendor": "amd", "model": "amd1234", "arch": "x86",
               "features": ["test_contents"], "topology":
                    {"cores": "2", "threads": "1024", "sockets": "9999"}}

        self.assertRaises(exception.InvalidCPUInfo,
                self.libvirtconnection.compare_cpu, cpu_info=utils.dumps(cpu))

    @attr(kind='small')
    def test_ensure_filtering_rules_for_instance(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .ensure_filtering_rules_for_instance."""

        self.flags(live_migration_retry_count=1)
        self.libvirtconnection = connection.get_connection(read_only=True)

        def fake_setup_basic_filtering(instance, network_info):
            pass

        self.stubs.Set(self.libvirtconnection.firewall_driver,
                       'setup_basic_filtering', fake_setup_basic_filtering)

        def fake_instance_filter_exists(instance, network_info):
            return True

        self.stubs.Set(self.libvirtconnection.firewall_driver,
                       'instance_filter_exists', fake_instance_filter_exists)

        ins_ref = self._create_instance()
        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        ref = self.libvirtconnection.ensure_filtering_rules_for_instance(
                            instance_ref=ins_ref, network_info=ni, time=None)

        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_ensure_filtering_rules_for_instance_exception(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .ensure_filtering_rules_for_instance."""

        self.flags(live_migration_retry_count=2)
        self.libvirtconnection = connection.get_connection(read_only=True)

        def fake_setup_basic_filtering(instance, network_info):
            pass

        self.stubs.Set(self.libvirtconnection.firewall_driver,
                       'setup_basic_filtering', fake_setup_basic_filtering)

        def fake_instance_filter_exists(instance, network_info):
            return False

        self.stubs.Set(self.libvirtconnection.firewall_driver,
                       'instance_filter_exists', fake_instance_filter_exists)

        ins_ref = self._create_instance()
        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        self.assertRaises(exception.Error,
            self.libvirtconnection.ensure_filtering_rules_for_instance,
                            instance_ref=ins_ref, network_info=ni, time=None)

    @attr(kind='small')
    def test_live_migration(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .live_migration."""

        def dummy_post(con, ctxt, instance_ref, dest,
                       block_migration=False):
            pass

        def dummy_recover(con, ctxt, instance_ref, dest,
                       block_migration=False):
            pass

        def fake_migrateToURI(con, uri, sum, name, bind):
            self.exe_flag = True

        self.stubs.Set(FakeDomain, 'migrateToURI', fake_migrateToURI)

        def fake_info(self):
            raise exception.NotFound

        self.stubs.Set(FakeDomain, 'info', fake_info)

        ins_ref = self._create_instance()

        ref = self.libvirtconnection.live_migration(
                context.get_admin_context(),
                instance_ref=ins_ref, dest='host2', post_method=dummy_post,
                recover_method=dummy_recover, block_migration=False)
        greenthread.sleep(0)

        self.assertEqual(None, ref)
        self.assertEqual(True, self.exe_flag)

    @attr(kind='small')
    def test_live_migration_parameter(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .live_migration."""

        def dummy_post(con, ctxt, instance_ref, dest,
                       block_migration=False):
            pass

        def dummy_recover(con, ctxt, instance_ref, dest,
                       block_migration=False):
            pass

        def fake_migrateToURI(con, uri, sum, name, bind):
            self.exe_flag = True

        self.stubs.Set(FakeDomain, 'migrateToURI', fake_migrateToURI)

        def fake_info(self):
            raise exception.NotFound

        self.stubs.Set(FakeDomain, 'info', fake_info)

        ins_ref = self._create_instance()

        ref = self.libvirtconnection.live_migration(
                context.get_admin_context(),
                instance_ref=ins_ref, dest='host2', post_method=dummy_post,
                recover_method=dummy_recover, block_migration=True)
        greenthread.sleep(0)

        self.assertEqual(None, ref)
        self.assertEqual(True, self.exe_flag)

    @attr(kind='small')
    def test_live_migration_exception_migrate(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .live_migration."""

        def dummy_post(con, ctxt, instance_ref, dest,
                       block_migration=False):
            pass

        def dummy_recover(con, ctxt, instance_ref, dest,
                       block_migration=False):
            self.exe_flag = True

        def fake_migrateToURI(con, uri, sum, name, bind):
            raise FakeLibvirt.libvirtError('a fake libvirt exception')

        self.stubs.Set(FakeDomain, 'migrateToURI', fake_migrateToURI)

        ins_ref = self._create_instance()

        try:
            self.libvirtconnection.live_migration(context.get_admin_context(),
                instance_ref=ins_ref, dest='host2', post_method=dummy_post,
                recover_method=dummy_recover, block_migration=True)
            greenthread.sleep(0)
        except FakeLibvirt.libvirtError:
            pass

        self.assertEqual(True, self.exe_flag)

    @test.skip_test("because that multi thread is difficult to test")
    @attr(kind='small')
    def test_live_migration_exception_post(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .live_migration."""

        def dummy_post(con, ctxt, instance_ref, dest,
                       block_migration=False):
            self.exe_flag = True

        def dummy_recover(con, ctxt, instance_ref, dest,
                       block_migration=False):
            pass

        def fake_migrateToURI(con, uri, sum, name, bind):
            pass

        self.stubs.Set(FakeDomain, 'migrateToURI', fake_migrateToURI)

        ins_ref = self._create_instance()

        self.libvirtconnection.live_migration(context.get_admin_context(),
            instance_ref=ins_ref, dest='host2', post_method=dummy_post,
            recover_method=dummy_recover, block_migration=True)
        greenthread.sleep(0)

        self.assertEqual(True, self.exe_flag, 'post method was not invoke')

    @attr(kind='small')
    def test_pre_block_migration(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .pre_block_migration."""

        def fake_execute(cmd, *arg, **kwargs):
            return ('cmdok', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        def fake_exists(path):
            return False

        self.stubs.Set(os.path, 'exists', fake_exists)

        def fake_basename(path):
            return path

        self.stubs.Set(os.path, 'basename', fake_basename)

        def fake_mkdir(path):
            pass

        self.stubs.Set(os, 'mkdir', fake_mkdir)

        def fake_cache_image(fn, target, fname, cow=False, *args, **kwargs):
            pass

        self.stubs.Set(self.libvirtconnection,
                       '_cache_image', fake_cache_image)

        def fake_fetch_image(context, target, image_id, user_id,
                             project_id, size=None):
            self.exe_flag = True

        self.stubs.Set(self.libvirtconnection,
                       '_fetch_image', fake_fetch_image)

        def fake_get_user(self, user_id):
            return 'fake'

        self.stubs.Set(manager.AuthManager, 'get_user', fake_get_user)

        def fake_get_project(self, project_id):
            return 'fake'

        self.stubs.Set(manager.AuthManager, 'get_project', fake_get_project)

        ins_ref = self._create_instance()

        disk = [{'path': '/dev/test_path', 'type': 'vda', 'local_gb': 8,
                'backing_file': '/dev/backup/test_path'}]
        ref = self.libvirtconnection.pre_block_migration(
                context.get_admin_context(),
                instance_ref=ins_ref, disk_info_json=utils.dumps(disk))

        self.assertEqual(None, ref)
        self.assertEqual(True, self.exe_flag)

    @attr(kind='small')
    def test_pre_block_migration_parameter_without_backing_file(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .pre_block_migration."""

        def fake_execute(cmd, *arg, **kwargs):
            self.assertTrue('backing_file' not in arg)
            return ('cmdok', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        def fake_exists(path):
            return False

        self.stubs.Set(os.path, 'exists', fake_exists)

        def fake_basename(path):
            return path

        self.stubs.Set(os.path, 'basename', fake_basename)

        def fake_mkdir(path):
            pass

        self.stubs.Set(os, 'mkdir', fake_mkdir)

        def fake_cache_image(fn, target, fname, cow=False, *args, **kwargs):
            pass

        self.stubs.Set(self.libvirtconnection,
                       '_cache_image', fake_cache_image)

        def fake_fetch_image(context, target, image_id, user_id,
                             project_id, size=None):
            self.exe_flag = True

        self.stubs.Set(self.libvirtconnection,
                       '_fetch_image', fake_fetch_image)

        def fake_get_user(self, user_id):
            return 'fake'

        self.stubs.Set(manager.AuthManager, 'get_user', fake_get_user)

        def fake_get_project(self, project_id):
            return 'fake'

        self.stubs.Set(manager.AuthManager, 'get_project', fake_get_project)

        ins_ref = self._create_instance()

        disk = [{'path': '/dev/test_path', 'type': 'vda', 'local_gb': 8,
                'backing_file': ''}]
        ref = self.libvirtconnection.pre_block_migration(
                context.get_admin_context(),
                instance_ref=ins_ref, disk_info_json=utils.dumps(disk))

        self.assertEqual(None, ref)
        self.assertEqual(True, self.exe_flag)

    @attr(kind='small')
    def test_pre_block_migration_exception(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .pre_block_migration."""

        def fake_execute(cmd, *arg, **kwargs):
            return ('cmdok', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        def fake_exists(path):
            return True

        self.stubs.Set(os.path, 'exists', fake_exists)

        ins_ref = self._create_instance()

        disk = [{'path': '/dev/test_path', 'type': 'vda', 'local_gb': 8,
                'backing_file': '/dev/backup/test_path'}]

        self.assertRaises(exception.DestinationDiskExists,
                self.libvirtconnection.pre_block_migration,
                    context.get_admin_context(),
                    instance_ref=ins_ref, disk_info_json=utils.dumps(disk))

    @attr(kind='small')
    def test_post_live_migration_at_destination(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .post_live_migration_at_destination."""

        self.libvirtconnection = connection.get_connection(read_only=True)

        def fake_isfile(path):
            self.exe_flag = True
            return True

        self.stubs.Set(os.path, 'isfile', fake_isfile)

        ins_ref = self._create_instance()
        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        ref = self.libvirtconnection.post_live_migration_at_destination(
                context.get_admin_context(), instance_ref=ins_ref,
                network_info=ni, block_migration=False)

        self.assertEqual(None, ref)
        self.assertEqual(True, self.exe_flag)

    @attr(kind='small')
    def test_post_live_migration_at_destination_configuration_noxml(
                                                                    self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .post_live_migration_at_destination."""

        self.libvirtconnection = connection.get_connection(read_only=True)

        def fake_isfile(path):
            self.exe_flag = True
            return False

        self.stubs.Set(os.path, 'isfile', fake_isfile)

        ins_ref = self._create_instance()
        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')

        ref = self.libvirtconnection.post_live_migration_at_destination(
                context.get_admin_context(), instance_ref=ins_ref,
                network_info=ni, block_migration=False)

        self.assertEqual(None, ref)
        self.assertEqual(True, self.exe_flag)

    @attr(kind='small')
    def test_get_instance_disk_info(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_instance_disk_info."""

        def fake_execute(cmd, *arg, **kwargs):
            return ('virtual size(10\nbacking file actual path:/dev/', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        ins_ref = self._create_instance()

        ref = self.libvirtconnection.get_instance_disk_info(
                        context.get_admin_context(), instance_ref=ins_ref)

        result = {"path": "/test_path", "local_gb": "10", "type": "2",
                  "backing_file": "dev"}

        self.assertEquals(True, ref.find('/test_path') > 0)
        self.assertEquals(True, ref.find('dev') > 0)
        self.assertEquals(True, ref.find('10') > 0)
        self.assertEquals(True, ref.find('2') > 0)

    @attr(kind='small')
    def test_get_instance_disk_info_parameter_disk_type(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_instance_disk_info."""

        def fake_getContent(con):
            if not con.name:
                return 'test_contents'

            if con.name.find('disk/source') >= 0:
                return '/test_path'
            elif con.name.find('disk/driver') >= 0:
                return 'raw'
            elif con.name.find('devices/disk') >= 0:
                return 'file'
            else:
                return 'test_contents'

        self.stubs.Set(FakeLibxml2, 'getContent', fake_getContent)

        def fake_get_next(self):
            if self.counter == 0:
                self.counter += 1
                return self
            if self.counter == 1:
                return None

        self.stubs.Set(FakeLibxml2, 'get_next', fake_get_next)

        def fake_getsize(path):
            return 1024 ** 2 + 1

        self.stubs.Set(os.path, 'getsize', fake_getsize)

        ins_ref = self._create_instance()

        ref = self.libvirtconnection.get_instance_disk_info(
                        context.get_admin_context(), instance_ref=ins_ref)

        result = {"path": "/test_path", "local_gb": "3M", "type": "raw",
                  "backing_file": ""}

        self.assertEquals(True, ref.find('/test_path') > 0)
        self.assertEquals(True, ref.find('raw') > 0)
        self.assertEquals(True, ref.find('2M') > 0)

    @attr(kind='small')
    def test_get_instance_disk_info_parameter_disk_type_notfile(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_instance_disk_info."""

        def fake_getContent(con):
            if not con.name:
                return 'test_contents'

            if con.name.find('disk/source') >= 0:
                return '/test_path'
            elif con.name.find('disk/driver') >= 0:
                return 'raw'
            elif con.name.find('devices/disk') >= 0:
                return 'not be file'
            else:
                return 'test_contents'

        self.stubs.Set(FakeLibxml2, 'getContent', fake_getContent)

        def fake_get_next(self):
            if self.counter == 0:
                self.counter += 1
                return self
            if self.counter == 1:
                return None

        self.stubs.Set(FakeLibxml2, 'get_next', fake_get_next)

        def fake_getsize(path):
            return 1024 ** 2 + 1

        self.stubs.Set(os.path, 'getsize', fake_getsize)

        ins_ref = self._create_instance()

        ref = self.libvirtconnection.get_instance_disk_info(
                        context.get_admin_context(), instance_ref=ins_ref)

        self.assertEquals('[]', ref)

    @attr(kind='small')
    def test_get_instance_disk_info_parameter_disk_size(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_instance_disk_info."""

        def fake_execute(cmd, *arg, **kwargs):
            return ('virtual size(1025\nbacking file actual path:/dev/', '')

        self.stubs.Set(utils, 'execute', fake_execute)

        ins_ref = self._create_instance()

        ref = self.libvirtconnection.get_instance_disk_info(
                        context.get_admin_context(), instance_ref=ins_ref)

        result = {"path": "/test_path", "local_gb": "2K", "type": "2",
                  "backing_file": "dev"}

        self.assertEquals(True, ref.find('/test_path') > 0)
        self.assertEquals(True, ref.find('dev') > 0)
        self.assertEquals(True, ref.find('2K') > 0)

    @attr(kind='small')
    def test_unfilter_instance(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .unfilter_instance."""

        ins_ref = self._create_instance()
        self._setup_networking(ins_ref['id'])
        manager = network.manager.NetworkManager()
        manager.SHOULD_CREATE_BRIDGE = True
        ni = manager.get_instance_nw_info(
                                    context.get_admin_context(),
                                    ins_ref['id'],
                                    ins_ref['instance_type_id'],
                                    'host1')
        self.libvirtconnection.firewall_driver.prepare_instance_filter(
                                    instance=ins_ref, network_info=ni)

        ref = self.libvirtconnection.unfilter_instance(instance_ref=ins_ref,
                                               network_info=ni)

        self.assertEqual(None, ref)
        self.assertEqual({}, self.libvirtconnection.firewall_driver.instances)

    @attr(kind='small')
    def test_update_host_status(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .update_host_status. no need assert becuase it is pass implements"""

        self.libvirtconnection.update_host_status()

    @attr(kind='small')
    def test_get_host_stats(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .get_host_stats. no need assert becuase it is pass implements"""

        self.libvirtconnection.get_host_stats(refresh=True)

    @attr(kind='small')
    def test_host_power_action(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .host_power_action. no need assert becuase it is pass implements"""

        self.libvirtconnection.host_power_action(host=None, action=None)

    @attr(kind='small')
    def test_set_host_enabled(self):
        """Test for nova.virt.libvirt.connection.LibvirtConnection
        .set_host_enabled. no need assert becuase it is pass implements"""

        self.libvirtconnection.set_host_enabled(host=None, enabled=True)

    @attr(kind='small')
    def test_migrate_disk_and_power_off(self):
        """Test for nova.virt.libvirt.connection.LivirtConnection
        .migrate_disk_and_power_off. """

        disk_info = [{'type': 'qcow2', 'path': '/test/disk',
                      'local_gb': 10, 'backing_file': '/base/disk'},
                     {'type': 'raw', 'path': '/test/disk.local',
                      'local_gb': 10, 'backing_file': '/base/disk.local'}]
        disk_info_text = utils.dumps(disk_info)

        def fake_get_instance_disk_info(instance):
            return disk_info
        def fake_destroy(instance, network_info, cleanup=True,
                         confirm_resize=False):
            pass
        def fake_get_host_ip_addr():
            return '10.0.0.1'

        def fake_execute(*args, **kwargs):
            pass

        self.stubs.Set(self.libvirtconnection, '_get_instance_disk_info',
                       fake_get_instance_disk_info)
        self.stubs.Set(self.libvirtconnection, 'destroy', fake_destroy)
        self.stubs.Set(self.libvirtconnection, 'get_host_ip_addr',
                       fake_get_host_ip_addr)
        self.stubs.Set(utils, 'execute', fake_execute)

        ins_ref = self._create_instance()
        """ dest is different host case """
        out = self.libvirtconnection.migrate_disk_and_power_off( \
               ins_ref, '10.0.0.2')
        self.assertEquals(out, disk_info_text)

        """ dest is same host case """
        out = self.libvirtconnection.migrate_disk_and_power_off( \
               ins_ref, '10.0.0.1')
        self.assertEquals(out, disk_info_text)

    @attr(kind='small')
    def test_wait_for_running(self):
        """Test for nova.virt.libvirt.connection.LivirtConnection
        ._wait_for_running. """

        def fake_get_info(instance_name):
            if instance_name == "not_found":
                raise exception.NotFound
            elif instance_name == "running":
                return {'state': power_state.RUNNING}
            else:
                return {'state': power_state.SHUTOFF}

        self.stubs.Set(self.libvirtconnection, 'get_info',
                       fake_get_info)

        """ instance not found case """
        self.assertRaises(utils.LoopingCallDone,
                self.libvirtconnection._wait_for_running,
                    "not_found")

        """ instance is running case """
        self.assertRaises(utils.LoopingCallDone,
                self.libvirtconnection._wait_for_running,
                    "running")

        """ else case """
        self.libvirtconnection._wait_for_running("else")

    @attr(kind='small')
    def test_finish_migration(self):
        """Test for nova.virt.libvirt.connection.LivirtConnection
        .finish_migration. """

        disk_info = [{'type': 'qcow2', 'path': '/test/disk',
                      'local_gb': 10, 'backing_file': '/base/disk'},
                     {'type': 'raw', 'path': '/test/disk.local',
                      'local_gb': 10, 'backing_file': '/base/disk.local'}]
        disk_info_text = utils.dumps(disk_info)

        def fake_extend(path, size):
            pass
        def fake_to_xml(instance, network_info):
            return ""
        def fake_plug_vifs(instance, network_info):
            pass
        def fake_create_image(context, inst, libvirt_xml, suffix='',
                      disk_images=None, network_info=None,
                      block_device_info=None):
            pass
        def fake_create_new_domain(xml):
            return None
        def fake_execute(*args, **kwargs):
            pass

        self.flags(use_cow_images=True)
        self.stubs.Set(virt.disk, 'extend', fake_extend)
        self.stubs.Set(self.libvirtconnection, 'to_xml', fake_to_xml)
        self.stubs.Set(self.libvirtconnection, 'plug_vifs', fake_plug_vifs)
        self.stubs.Set(self.libvirtconnection, '_create_image',
                       fake_create_image)
        self.stubs.Set(self.libvirtconnection, '_create_new_domain',
                       fake_create_new_domain)
        self.stubs.Set(utils, 'execute', fake_execute)
        fw = virt.libvirt.firewall.NullFirewallDriver(None)
        self.stubs.Set(self.libvirtconnection, 'firewall_driver', fw)

        ins_ref = self._create_instance()

        """ FLAGS.libvirt_single_local_disk == False case """
        self.flags(libvirt_single_local_disk=False)
        ref = self.libvirtconnection.finish_migration(
                      context.get_admin_context(), ins_ref,
                      disk_info_text, None, None)
        self.assertTrue(isinstance(ref, event.Event))

        """ FLAGS.libvirt_single_local_disk == True case """
        self.flags(libvirt_single_local_disk=True)
        ref = self.libvirtconnection.finish_migration(
                      context.get_admin_context(), ins_ref,
                      disk_info_text, None, None)
        self.assertTrue(isinstance(ref, event.Event))

    @attr(kind='small')
    def test_revert_migration(self):
        """Test for nova.virt.libvirt.connection.LivirtConnection
        .revert_migration. """

        def fake_execute(*args, **kwargs):
            pass
        def fake_plug_vifs(instance, network_info):
            pass
        def fake_create_new_domain(xml):
            return None

        self.stubs.Set(self.libvirtconnection, 'plug_vifs', fake_plug_vifs)
        self.stubs.Set(utils, 'execute', fake_execute)
        fw = virt.libvirt.firewall.NullFirewallDriver(None)
        self.stubs.Set(self.libvirtconnection, 'firewall_driver', fw)
        self.stubs.Set(self.libvirtconnection, '_create_new_domain',
                       fake_create_new_domain)

        ins_ref = self._create_instance()
        libvirt_xml_path = os.path.join(flags.FLAGS.instances_path,
                                         ins_ref['name'], 'libvirt.xml')
        f = open(libvirt_xml_path, 'w')
        f.close()

        ref = self.libvirtconnection.revert_migration(ins_ref, None)
        self.assertTrue(isinstance(ref, event.Event))
