# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
#    Copyright 2010 OpenStack LLC
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

import base64
from eventlet import greenthread
import netaddr
import sys
import traceback
import types

from nova import exception
from nova import flags
from nova import image
from nova import log as logging
from nova import test
from nova import utils
from nova.tests import utils as test_utils
from nova.virt import driver
from nova import db


libvirt = None
FLAGS = flags.FLAGS


LOG = logging.getLogger('nova.tests.test_virt_drivers')


class TestVirtDriver(test.TestCase):
    def test_block_device(self):
        swap = {'device_name': '/dev/sdb',
                'swap_size': 1}
        ephemerals = [{'num': 0,
                       'virtual_name': 'ephemeral0',
                       'device_name': '/dev/sdc1',
                       'size': 1}]
        block_device_mapping = [{'mount_device': '/dev/sde',
                                 'device_path': 'fake_device'}]
        block_device_info = {
                'root_device_name': '/dev/sda',
                'swap': swap,
                'ephemerals': ephemerals,
                'block_device_mapping': block_device_mapping}

        empty_block_device_info = {}

        self.assertEqual(
            driver.block_device_info_get_root(block_device_info), '/dev/sda')
        self.assertEqual(
            driver.block_device_info_get_root(empty_block_device_info), None)
        self.assertEqual(
            driver.block_device_info_get_root(None), None)

        self.assertEqual(
            driver.block_device_info_get_swap(block_device_info), swap)
        self.assertEqual(driver.block_device_info_get_swap(
            empty_block_device_info)['device_name'], None)
        self.assertEqual(driver.block_device_info_get_swap(
            empty_block_device_info)['swap_size'], 0)
        self.assertEqual(
            driver.block_device_info_get_swap({'swap': None})['device_name'],
            None)
        self.assertEqual(
            driver.block_device_info_get_swap({'swap': None})['swap_size'],
            0)
        self.assertEqual(
            driver.block_device_info_get_swap(None)['device_name'], None)
        self.assertEqual(
            driver.block_device_info_get_swap(None)['swap_size'], 0)

        self.assertEqual(
            driver.block_device_info_get_ephemerals(block_device_info),
            ephemerals)
        self.assertEqual(
            driver.block_device_info_get_ephemerals(empty_block_device_info),
            [])
        self.assertEqual(
            driver.block_device_info_get_ephemerals(None),
            [])

        self.assertEqual(
            driver.block_device_info_get_mapping(block_device_info),
            block_device_mapping)
        self.assertEqual(
            driver.block_device_info_get_mapping(empty_block_device_info),
            [])
        self.assertEqual(
            driver.block_device_info_get_mapping(None),
            [])

    def test_swap_is_usable(self):
        self.assertFalse(driver.swap_is_usable(None))
        self.assertFalse(driver.swap_is_usable({'device_name': None}))
        self.assertFalse(driver.swap_is_usable({'device_name': '/dev/sdb',
                                                'swap_size': 0}))
        self.assertTrue(driver.swap_is_usable({'device_name': '/dev/sdb',
                                                'swap_size': 1}))


def catch_notimplementederror(f):
    """Decorator to simplify catching drivers raising NotImplementedError

    If a particular call makes a driver raise NotImplementedError, we
    log it so that we can extract this information afterwards to
    automatically generate a hypervisor/feature support matrix."""
    def wrapped_func(self, *args, **kwargs):
        try:
            return f(self, *args, **kwargs)
        except NotImplementedError as e:
            frame = traceback.extract_tb(sys.exc_info()[2])[-1]
            message = '%(driver)s does not implement %(method)s' % {
               'driver': type(self.connection),
               'method': frame[2]}
            if getattr(e, 'message', ''):
                message += ': ' + e.message
            LOG.error(message)

    wrapped_func.__name__ = f.__name__
    wrapped_func.__doc__ = f.__doc__
    return wrapped_func


def fake_looping_call_start(self, interval, now=True):
    try:
        self.f(*self.args, **self.kw)
    except utils.LoopingCallDone:
        pass


def fake_greenthread_spawn(func, *args):
    try:
        func(*args)
    except Exception:
        pass


class LiveMigrationCallbackHandler:
    def post_method(self, *args, **kwargs):
        self.state = 'SUCCESS'

    def recover_method(self, *args, **kwargs):
        self.state = 'FAILED'


class _VirtDriverConnectionTestCase(test.TestCase):
    def setUp(self):
        super(_VirtDriverConnectionTestCase, self).setUp()

        # Stubs
        self.stubs.Set(utils.LoopingCall, 'start', fake_looping_call_start)
        self.stubs.Set(greenthread, 'spawn', fake_greenthread_spawn)

        assert getattr(self, 'driver_module', None) is not None, \
            "Define the target driver module as an attribute 'driver_module'."
        assert getattr(self.driver_module,
                       'get_connection', None) is not None, \
            "All driver modules have an entry function " \
            "get_connection(readonly=boolean)."
        self.connection = self.driver_module.get_connection('')
        self.ctxt = test_utils.get_test_admin_context()
        self.image_service = image.get_default_image_service()

    def _ensure_test_instance_running(self):
        """ An utility function to ensure a test instance running. """
        self.instance_ref = test_utils.get_test_instance()
        self.network_info = test_utils.get_test_network_info()
        self.connection.spawn(self.ctxt, self.instance_ref, self.network_info)

    def _must_be_test_instance_running(self):
        self.assertIn(self.instance_ref['name'],
                      self.connection.list_instances())

    def _must_not_be_test_instance_running(self):
        self.assertNotIn(self.instance_ref['name'],
                         self.connection.list_instances())

    @catch_notimplementederror
    def test_init_host(self):
        """
        This just checks the definition of this method.
        Because its an hook, depends on the platform that
        driver's connection is made for.
        """
        self.connection.init_host('myhostname')

    @catch_notimplementederror
    def test_list_instances(self):
        self.assertEqual(self.connection.list_instances(), [],
                "Be empty before an instance running")
        self._ensure_test_instance_running()
        self.assertIn(self.instance_ref['name'],
                      self.connection.list_instances())

    @catch_notimplementederror
    def test_list_instances_detail(self):
        self.assertEqual(self.connection.list_instances_detail(), [],
                "Be empty before an instance running")
        self._ensure_test_instance_running()
        self.assertIn(self.instance_ref['name'],
                [instance.name for instance in \
                 self.connection.list_instances_detail()])

    @catch_notimplementederror
    def test_spawn(self):
        # do spawn within the utility function below.
        self._ensure_test_instance_running()
        self._must_be_test_instance_running()

    @catch_notimplementederror
    def test_snapshot_instance_not_running(self):
        instance_ref = test_utils.get_test_instance()
        img_ref = self.image_service.create(self.ctxt, {'name': 'snap-1'})
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.snapshot,
                          self.ctxt, instance_ref, img_ref['id'])

    @catch_notimplementederror
    def test_snapshot(self):
        self._ensure_test_instance_running()
        img_ref = self.image_service.create(self.ctxt, {'name': 'snap-1'})
        self.connection.snapshot(self.ctxt, self.instance_ref, img_ref['id'])

    @catch_notimplementederror
    def test_reboot_instance_not_running(self):
        instance_ref = test_utils.get_test_instance()
        network_info = test_utils.get_test_network_info()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.reboot,
                          instance_ref, network_info)

    @catch_notimplementederror
    def test_reboot(self):
        self._ensure_test_instance_running()
        self.connection.reboot(self.instance_ref, self.network_info)
        self._must_be_test_instance_running()

    @catch_notimplementederror
    def test_get_host_ip_addr(self):
        host_ip = self.connection.get_host_ip_addr()

        # Will raise an exception if it's not a valid IP at all
        ip = netaddr.IPAddress(host_ip)

        # For now, assume IPv4.
        self.assertEquals(ip.version, 4)

    @catch_notimplementederror
    def test_resize_instance_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.resize,
                          instance_ref, 7)

    @catch_notimplementederror
    def test_resize(self):
        self._ensure_test_instance_running()
        # XXX(yusuke): Hard coded flavor
        self.connection.resize(self.instance_ref, 7)
        self._must_be_test_instance_running()

    @catch_notimplementederror
    def test_set_admin_password_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.set_admin_password,
                          instance_ref, '')

    @catch_notimplementederror
    def test_set_admin_password(self):
        self._ensure_test_instance_running()
        self.connection.set_admin_password(self.instance_ref, 'p4ssw0rd')
        self._must_be_test_instance_running()

    @test.skip_test("for essex")
    @catch_notimplementederror
    def test_inject_network_info_not_running(self):
        instance_ref = test_utils.get_test_instance()
        network_info = test_utils.get_test_network_info()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.inject_network_info,
                          instance_ref, network_info)

    @catch_notimplementederror
    def test_inject_network_info(self):
        self._ensure_test_instance_running()
        self.connection.inject_network_info(self.instance_ref,
                                            self.network_info)
        self._must_be_test_instance_running()

    @catch_notimplementederror
    def test_plug_vifs(self):
        self._ensure_test_instance_running()
        self.connection.plug_vifs(self.instance_ref, self.network_info)
        self._must_be_test_instance_running()

    @catch_notimplementederror
    def test_inject_file_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.inject_file,
                          instance_ref, '', '')

    @catch_notimplementederror
    def test_inject_file(self):
        self._ensure_test_instance_running()
        self.connection.inject_file(self.instance_ref,
                                    base64.b64encode('/testfile'),
                                      base64.b64encode('testcontents'))
        self._must_be_test_instance_running()

    @test.skip_test("for essex")
    @catch_notimplementederror
    def test_reset_network_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.reset_network,
                          instance_ref)

    @catch_notimplementederror
    def test_reset_network(self):
        self._ensure_test_instance_running()
        self.connection.reset_network(self.instance_ref)
        self._must_be_test_instance_running()

    @catch_notimplementederror
    def test_agent_update_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.agent_update,
                          instance_ref, '', '')

    @catch_notimplementederror
    def test_agent_update(self):
        self._ensure_test_instance_running()
        self.connection.agent_update(self.instance_ref,
                                     'http://www.openstack.org/',
                                     'd41d8cd98f00b204e9800998ecf8427e')
        self._must_be_test_instance_running()

    @catch_notimplementederror
    def test_rescue_not_running(self):
        instance_ref = test_utils.get_test_instance()
        network_info = test_utils.get_test_network_info()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.rescue,
                          {}, instance_ref, lambda x: None, network_info)

    @catch_notimplementederror
    def test_rescue(self):
        self._ensure_test_instance_running()
        self.connection.rescue(self.ctxt, self.instance_ref,
                               lambda x: None, self.network_info)
        self._must_be_test_instance_running()

    @catch_notimplementederror
    def test_unrescue_unrescued_instance(self):
        instance_ref = test_utils.get_test_instance()
        network_info = test_utils.get_test_network_info()
        self.assertRaises(exception.InstanceNotInRescueMode,
                          self.connection.unrescue,
                          instance_ref, lambda x: None, network_info)

    @catch_notimplementederror
    def test_unrescue_rescued_instance(self):
        self._ensure_test_instance_running()
        self.connection.rescue(self.ctxt, self.instance_ref,
                               lambda x: None, self.network_info)
        self.connection.unrescue(self.instance_ref,
                                 lambda x: None, self.network_info)
        self._must_be_test_instance_running()

    @catch_notimplementederror
    def test_poll_rescued_instances(self):
        self.assertEqual(None, self.connection.poll_rescued_instances(10))

    @test.skip_test("for essex")
    @catch_notimplementederror
    def test_poll_unconfirmed_resizes(self):
        self.assertEqual(None, self.connection.poll_unconfirmed_resizes(10))

    @catch_notimplementederror
    def test_migrate_disk_and_power_off_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.migrate_disk_and_power_off,
                          instance_ref, 'dest_host')

    @catch_notimplementederror
    def test_migrate_disk_and_power_off(self):
        self._ensure_test_instance_running()
        self.connection.migrate_disk_and_power_off(self.instance_ref,
                                                   'dest_host')
        self._must_not_be_test_instance_running()

    @catch_notimplementederror
    def test_pause_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.pause,
                          instance_ref, None)

    @catch_notimplementederror
    def test_pause(self):
        self._ensure_test_instance_running()
        self.connection.pause(self.instance_ref, None)
        self._must_be_test_instance_running()

    @catch_notimplementederror
    def test_unpause_unpaused_instance(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.unpause,
                          instance_ref, None)

    @catch_notimplementederror
    def test_unpause_paused_instance(self):
        self._ensure_test_instance_running()
        self.connection.pause(self.instance_ref, None)
        self.connection.unpause(self.instance_ref, None)
        self._must_be_test_instance_running()

    @catch_notimplementederror
    def test_suspend_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.suspend,
                          instance_ref, None)

    @catch_notimplementederror
    def test_suspend(self):
        self._ensure_test_instance_running()
        self.connection.suspend(self.instance_ref, None)
        self._must_be_test_instance_running()

    @catch_notimplementederror
    def test_resume_unsuspended_instance(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.resume,
                          instance_ref, None)

    @catch_notimplementederror
    def test_resume_suspended_instance(self):
        self._ensure_test_instance_running()
        self.connection.suspend(self.instance_ref, None)
        self.connection.resume(self.instance_ref, None)
        self._must_be_test_instance_running()

    @catch_notimplementederror
    def test_destroy_instance_not_running(self):
        """
        A note for the method of the driver interface:

        If the instance is not found (for example if networking failed),
        this function should still succeed.
        """
        fake_instance = {'id': 42, 'name': 'I just made this up!'}
        network_info = test_utils.get_test_network_info()
        self.connection.destroy(fake_instance, network_info)

    @catch_notimplementederror
    def test_destroy_instance(self):
        self._ensure_test_instance_running()
        self.connection.destroy(self.instance_ref, self.network_info)
        self._must_not_be_test_instance_running()

    @catch_notimplementederror
    def test_attach_volume_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.attach_volume,
                          instance_ref['name'], '', '')

    @catch_notimplementederror
    def test_attach_volume(self):
        self._ensure_test_instance_running()
        self.connection.attach_volume(self.instance_ref['name'],
                                      '/dev/null', '/mnt/nova/something')

    @catch_notimplementederror
    def test_detach_volume_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.detach_volume,
                          instance_ref['name'], '')

    @catch_notimplementederror
    def test_detach_volume(self):
        self._ensure_test_instance_running()
        self.connection.attach_volume(self.instance_ref['name'],
                                      '/dev/null', '/mnt/nova/something')
        self.connection.detach_volume(self.instance_ref['name'],
                                      '/mnt/nova/something')

    @catch_notimplementederror
    def test_get_info_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.get_info,
                          instance_ref['name'])

    @catch_notimplementederror
    def test_get_info(self):
        self._ensure_test_instance_running()
        info = self.connection.get_info(self.instance_ref['name'])
        self.assertIn('state', info)
        self.assertIn('max_mem', info)
        self.assertIn('mem', info)
        self.assertIn('num_cpu', info)
        self.assertIn('cpu_time', info)

    @catch_notimplementederror
    def test_get_diagnostics_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.get_diagnostics,
                          instance_ref['name'])

    @catch_notimplementederror
    def test_get_diagnostics(self):
        self._ensure_test_instance_running()
        self.assertTrue(isinstance(
            self.connection.get_diagnostics(self.instance_ref['name']),
            types.DictType),
            "Must return the information as a dict.")

    @catch_notimplementederror
    def test_list_disks_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.list_disks,
                          instance_ref['name'])

    @catch_notimplementederror
    def test_list_disks(self):
        self._ensure_test_instance_running()
        self.assertTrue(isinstance(
            self.connection.list_disks(self.instance_ref['name']),
            types.ListType))

    @catch_notimplementederror
    def test_list_interfaces_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.list_interfaces,
                          instance_ref['name'])

    @catch_notimplementederror
    def test_list_interfaces(self):
        self._ensure_test_instance_running()
        self.assertTrue(isinstance(
            self.connection.list_interfaces(self.instance_ref['name']),
            types.ListType))

    @catch_notimplementederror
    def test_block_stats_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.block_stats,
                          instance_ref['name'], 'someid')

    @catch_notimplementederror
    def test_block_stats(self):
        self._ensure_test_instance_running()
        stats = self.connection.block_stats(self.instance_ref['name'],
                                            'someid')
        self.assertEquals(len(stats), 5)

    @catch_notimplementederror
    def test_interface_stats_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.interface_stats,
                          instance_ref['name'], 'someid')

    @catch_notimplementederror
    def test_interface_stats(self):
        self._ensure_test_instance_running()
        stats = self.connection.interface_stats(self.instance_ref['name'],
                                                'someid')
        self.assertEquals(len(stats), 8)

    @catch_notimplementederror
    def test_get_console_output_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.get_console_output,
                          instance_ref)

    @catch_notimplementederror
    def test_get_console_output(self):
        self._ensure_test_instance_running()
        console_output = self.connection.get_console_output(self.instance_ref)
        self.assertTrue(isinstance(console_output, basestring))

    @catch_notimplementederror
    def test_get_ajax_console_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.get_ajax_console,
                          instance_ref)

    @catch_notimplementederror
    def test_get_ajax_console(self):
        self._ensure_test_instance_running()
        ajax_console = self.connection.get_ajax_console(self.instance_ref)
        self.assertIn('token', ajax_console)
        self.assertIn('host', ajax_console)
        self.assertIn('port', ajax_console)

    @test.skip_test("for essex")
    @catch_notimplementederror
    def test_get_vnc_console_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.get_vnc_console,
                          instance_ref)

    @test.skip_test("for essex")
    @catch_notimplementederror
    def test_get_vnc_console(self):
        self._ensure_test_instance_running()
        vnc_console = self.connection.get_vnc_console(self.instance_ref)
        self.assertIn('token', vnc_console)
        self.assertIn('host', vnc_console)
        self.assertIn('port', vnc_console)

    @catch_notimplementederror
    def test_get_console_pool_info(self):
        self._ensure_test_instance_running()
        console_pool = self.connection.get_console_pool_info('')
        self.assertIn('address', console_pool)
        self.assertIn('username', console_pool)
        self.assertIn('password', console_pool)

    @catch_notimplementederror
    def test_refresh_security_group_rules(self):
        # FIXME: Create security group and add the instance to it
        self._ensure_test_instance_running()
        self.connection.refresh_security_group_rules(1)

    @catch_notimplementederror
    def test_refresh_security_group_members(self):
        # FIXME: Create security group and add the instance to it
        self._ensure_test_instance_running()
        self.connection.refresh_security_group_members(1)

    @test.skip_test("for essex")
    @catch_notimplementederror
    def test_refresh_provider_fw_rules(self):
        self._ensure_test_instance_running()
        # FIXME(yusuke): Check the rule modified.
        self.connection.refresh_provider_fw_rules()

    @catch_notimplementederror
    def test_update_available_resource_not_running(self):
        self.assertRaises(exception.ComputeServiceUnavailable,
                          self.connection.update_available_resource,
                          self.ctxt, 'dummy')

    @catch_notimplementederror
    def test_update_available_resource(self):
        self.compute = self.start_service('compute', host='dummy')
        self.connection.update_available_resource(self.ctxt, 'dummy')

    @catch_notimplementederror
    def test_compare_cpu(self):
        cpu_info = '''{ "topology": {
                               "sockets": 1,
                               "cores": 2,
                               "threads": 1 },
                        "features": [
                            "xtpr",
                            "tm2",
                            "est",
                            "vmx",
                            "ds_cpl",
                            "monitor",
                            "pbe",
                            "tm",
                            "ht",
                            "ss",
                            "acpi",
                            "ds",
                            "vme"],
                        "arch": "x86_64",
                        "model": "Penryn",
                        "vendor": "Intel" }'''
        self.assertEqual(self.connection.compare_cpu(cpu_info),
                         None,
                         "Returns None if migration is acceptable.")

    @catch_notimplementederror
    def test_ensure_filtering_for_instance(self):
        instance_ref = test_utils.get_test_instance()
        network_info = test_utils.get_test_network_info()
        # FIXME(yusuke): Can not add any assertions because of its interface.
        self.connection.ensure_filtering_rules_for_instance(instance_ref,
                                                            network_info)

    @catch_notimplementederror
    def test_unfilter_instance(self):
        instance_ref = test_utils.get_test_instance()
        network_info = test_utils.get_test_network_info()
        # FIXME(yusuke): Can not add any assertions because of its interface.
        self.connection.unfilter_instance(instance_ref, network_info)

    @test.skip_test("for essex")
    @catch_notimplementederror
    def test_finish_migration_not_running(self):
        instance_ref = test_utils.get_test_instance()
        disk_info = test_utils.get_test_disk_info()
        network_info = test_utils.get_test_network_info()
        migration = test_utils.get_test_migration()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.finish_migration,
                          self.ctxt, migration, instance_ref,
                          disk_info, network_info, None)

    @test.skip_test("for essex")
    @catch_notimplementederror
    def test_confirm_migration_not_running(self):
        instance_ref = test_utils.get_test_instance()
        network_info = test_utils.get_test_network_info()
        migration = test_utils.get_test_migration()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.confirm_migration,
                          migration, instance_ref, network_info)

    @test.skip_test("for essex")
    @catch_notimplementederror
    def test_revert_migration_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.InstanceNotFound,
                          self.connection.finish_revert_migration,
                          instance_ref)

    @test.skip_test("for essex")
    @catch_notimplementederror
    def test_finish_migration(self):
        disk_info = test_utils.get_test_disk_info()
        migration = test_utils.get_test_migration()
        self._ensure_test_instance_running()
        self.connection.finish_migration(self.ctxt, migration,
                                         self.instance_ref,
                                         disk_info, self.network_info, None)
        self.connection.confirm_migration(migration, self.instance_ref,
                                          self.network_info)
        self._must_be_test_instance_running()

    @catch_notimplementederror
    def test_revert_migration(self):
        self._ensure_test_instance_running()
        self.connection.finish_revert_migration(self.instance_ref)
        self._must_be_test_instance_running()

    @catch_notimplementederror
    def test_live_migration_not_running(self):
        handler = LiveMigrationCallbackHandler()
        instance_ref = test_utils.get_test_instance()
        self.connection.live_migration(self.ctxt, instance_ref, 'otherhost',
                                       handler.post_method,
                                       handler.recover_method)
        self.assertEqual(handler.state, 'FAILED')

    @catch_notimplementederror
    def test_live_migration(self):
        self._ensure_test_instance_running()
        handler = LiveMigrationCallbackHandler()
        self.connection.live_migration(self.ctxt, self.instance_ref,
                                       'otherhost', handler.post_method,
                                       handler.recover_method)
        self._must_be_test_instance_running()
        self.assertEqual(handler.state, 'SUCCESS')

    @catch_notimplementederror
    def _check_host_status_fields(self, host_status):
        self.assertIn('host_name-description', host_status)
        self.assertIn('host_hostname', host_status)
        self.assertIn('host_memory_total', host_status)
        self.assertIn('host_memory_overhead', host_status)
        self.assertIn('host_memory_free', host_status)
        self.assertIn('host_memory_free_computed', host_status)
        self.assertIn('host_other_config', host_status)
        self.assertIn('host_ip_address', host_status)
        self.assertIn('host_cpu_info', host_status)
        self.assertIn('disk_available', host_status)
        self.assertIn('disk_total', host_status)
        self.assertIn('disk_used', host_status)
        self.assertIn('host_uuid', host_status)
        self.assertIn('host_name_label', host_status)

    @catch_notimplementederror
    def test_update_host_status(self):
        host_status = self.connection.update_host_status()
        self._check_host_status_fields(host_status)

    @catch_notimplementederror
    def test_get_host_stats(self):
        host_status = self.connection.get_host_stats()
        self._check_host_status_fields(host_status)

    @catch_notimplementederror
    def test_set_host_enabled(self):
        # FIXME(yusuke): Can not add any assertions because of its interface.
        self.connection.set_host_enabled('a useless argument?', True)

    @test.skip_test("for essex")
    @catch_notimplementederror
    def test_power_off_not_running(self):
        instance_ref = test_utils.get_test_instance()
        self.assertRaises(exception.ApiError,
                          self.connection.power_off, instance_ref)

    @test.skip_test("for essex")
    @catch_notimplementederror
    def test_power_off(self):
        self._ensure_test_instance_running()
        self.connection.power_off(self.instance_ref)
        self._must_not_be_test_instance_running()

    @test.skip_test("for essex")
    @catch_notimplementederror
    def test_power_on_running(self):
        self._ensure_test_instance_running()
        self.assertRaises(exception.ApiError,
                          self.connection.power_on, self.instance_ref)

    @test.skip_test("for essex")
    @catch_notimplementederror
    def test_power_on(self):
        self._ensure_test_instance_running()
        self.connection.power_off(self.instance_ref)
        self.connection.power_on(self.instance_ref)
        self._must_be_test_instance_running()

    @catch_notimplementederror
    def test_host_power_action_reboot(self):
        # FIXME(yusuke): Can not add any assertions because of its interface.
        self.connection.host_power_action('a useless argument?', 'reboot')

    @catch_notimplementederror
    def test_host_power_action_shutdown(self):
        # FIXME(yusuke): Can not add any assertions because of its interface.
        self.connection.host_power_action('a useless argument?', 'shutdown')

    @catch_notimplementederror
    def test_host_power_action_startup(self):
        # FIXME(yusuke): Can not add any assertions because of its interface.
        self.connection.host_power_action('a useless argument?', 'startup')


class AbstractDriverConnectionTestCase(_VirtDriverConnectionTestCase):
    def setUp(self):
        import nova.virt.driver

        self.driver_module = nova.virt.driver

        def get_driver_connection(_):
            connection = nova.virt.driver.ComputeDriver()
            # For the tests which should be examined after spawning,
            # the spawn API must be replaced
            # to avoid raising NotImplementedError
            # at the ComputeDriver.spawn().
            # Because its an interface method,
            # and it have to be passed for sequential execution of those tests.
            # For example, to test the snapshot API,
            # the spawn API have to be passed before.
            connection.spawn = lambda context, instance, network_info=None, \
                                block_device_info=None: None
            return connection

        self.driver_module.get_connection = get_driver_connection
        super(AbstractDriverConnectionTestCase, self).setUp()

    @catch_notimplementederror
    def test_spawn(self):
        import nova.virt.driver

        # Override the connection for the purpose in
        # get_driver_connection of setUp.
        self.connection = nova.virt.driver.ComputeDriver()
        self._ensure_test_instance_running()


class FakeConnectionTestCase(_VirtDriverConnectionTestCase):
    def setUp(self):
        import nova.virt.fake
        self.driver_module = nova.virt.fake
        super(FakeConnectionTestCase, self).setUp()

# Before long, we'll add the real hypervisor drivers here as well
# with whatever instrumentation they need to work independently of
# their hypervisor. This way, we can verify that they all act the
# same.
