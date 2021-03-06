# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# Copyright (c) 2010 Citrix Systems, Inc.
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
A fake (in-memory) hypervisor+api.

Allows nova testing w/o a hypervisor.  This module also documents the
semantics of real hypervisor connections.

"""

from nova import db
from nova import exception
from nova import log as logging
from nova import utils
from nova.compute import power_state
from nova.virt import driver


LOG = logging.getLogger('nova.compute.disk')


def get_connection(_):
    # The read_only parameter is ignored.
    return FakeConnection.instance()


class FakeInstance(object):

    def __init__(self, name, state):
        self.name = name
        self.state = state


class FakeConnection(driver.ComputeDriver):
    """Fake hypervisor driver"""

    def __init__(self):
        self.instances = {}
        self.rescuing_instances = {}
        self.host_status = {
          'host_name-description': 'Fake Host',
          'host_hostname': 'fake-mini',
          'host_memory_total': 8000000000,
          'host_memory_overhead': 10000000,
          'host_memory_free': 7900000000,
          'host_memory_free_computed': 7900000000,
          'host_other_config': {},
          'host_ip_address': '192.168.1.109',
          'host_cpu_info': {},
          'disk_available': 500000000000,
          'disk_total': 600000000000,
          'disk_used': 100000000000,
          'host_uuid': 'cedb9b39-9388-41df-8891-c5c9a0c0fe5f',
          'host_name_label': 'fake-mini'}
        self._mounts = {}

    @classmethod
    def instance(cls):
        if not hasattr(cls, '_instance'):
            cls._instance = cls()
        return cls._instance

    def init_host(self, host):
        return

    def list_instances(self):
        return self.instances.keys() + self.rescuing_instances.keys()

    def _map_to_instance_info(self, instance):
        instance = utils.check_isinstance(instance, FakeInstance)
        info = driver.InstanceInfo(instance.name, instance.state)
        return info

    def list_instances_detail(self):
        info_list = []
        for instance in self.instances.values():
            info_list.append(self._map_to_instance_info(instance))
        return info_list

    def spawn(self, context, instance,
              network_info=None, block_device_info=None):
        name = instance.name
        state = power_state.RUNNING
        fake_instance = FakeInstance(name, state)
        self.instances[name] = fake_instance

    def snapshot(self, context, instance, name):
        if not instance['name'] in self.instances:
            raise exception.InstanceNotFound

    def reboot(self, instance, network_info):
        if instance['name'] in self.instances:
            pass
        else:
            raise exception.InstanceNotFound

    def get_host_ip_addr(self):
        return '192.168.0.1'

    def resize(self, instance, flavor):
        if instance['name'] in self.instances:
            pass
        else:
            raise exception.InstanceNotFound

    def set_admin_password(self, instance, new_pass):
        if instance['name'] in self.instances:
            pass
        else:
            raise exception.InstanceNotFound

    def inject_file(self, instance, b64_path, b64_contents):
        if instance['name'] in self.instances:
            pass
        else:
            raise exception.InstanceNotFound

    def inject_network_info(self, instance, network_info):
        if instance['name'] in self.instances:
            pass
        else:
            raise exception.InstanceNotFound

    def reset_network(self, instance):
        if instance['name'] in self.instances:
            pass
        else:
            raise exception.InstanceNotFound

    def agent_update(self, instance, url, md5hash):
        if instance['name'] in self.instances:
            pass
        else:
            raise exception.InstanceNotFound

    def rescue(self, context, instance, callback, network_info):
        name = instance['name']
        if name in self.instances:
            self.rescuing_instances[name] = self.instances[name]
            del self.instances[name]
        else:
            raise exception.InstanceNotFound

    def unrescue(self, instance, callback, network_info):
        name = instance['name']
        if name in self.rescuing_instances:
            self.instances[name] = self.rescuing_instances[name]
            del self.rescuing_instances[name]
        else:
            raise exception.InstanceNotInRescueMode(instance_id=name)

    def poll_rescued_instances(self, timeout):
        pass

    def poll_unconfirmed_resizes(self, resize_confirm_window):
        pass

    def migrate_disk_and_power_off(self, instance, dest):
        if instance['name'] in self.instances:
            del self.instances[instance['name']]
        else:
            raise exception.InstanceNotFound

    def pause(self, instance, callback):
        if instance['name'] in self.instances:
            pass
        else:
            raise exception.InstanceNotFound

    def unpause(self, instance, callback):
        if instance['name'] in self.instances:
            pass
        else:
            raise exception.InstanceNotFound

    def suspend(self, instance, callback):
        if instance['name'] in self.instances:
            pass
        else:
            raise exception.InstanceNotFound

    def resume(self, instance, callback):
        if instance['name'] in self.instances:
            pass
        else:
            raise exception.InstanceNotFound

    def destroy(self, instance, network_info, cleanup=True):
        key = instance['name']
        if key in self.instances:
            del self.instances[key]
        else:
            LOG.warning("Key '%s' not in instances '%s'" %
                        (key, self.instances))

    def attach_volume(self, instance_name, device_path, mountpoint):
        if instance_name not in self.instances:
            raise exception.InstanceNotFound(instance_id=instance_name)
        elif not instance_name in self._mounts:
            self._mounts[instance_name] = {}
        self._mounts[instance_name][mountpoint] = device_path
        return True

    def detach_volume(self, instance_name, mountpoint):
        if instance_name not in self.instances:
            raise exception.InstanceNotFound(instance_id=instance_name)
        try:
            del self._mounts[instance_name][mountpoint]
        except KeyError:
            pass
        return True

    def get_info(self, instance_name):
        if instance_name not in self.instances:
            raise exception.InstanceNotFound(instance_id=instance_name)
        i = self.instances[instance_name]
        return {'state': i.state,
                'max_mem': 0,
                'mem': 0,
                'num_cpu': 2,
                'cpu_time': 0}

    def get_diagnostics(self, instance_name):
        if instance_name in self.instances:
            return {}
        else:
            raise exception.InstanceNotFound

    def list_disks(self, instance_name):
        if instance_name in self.instances:
            return ['A_DISK']
        else:
            raise exception.InstanceNotFound

    def list_interfaces(self, instance_name):
        if instance_name in self.instances:
            return ['A_VIF']
        else:
            raise exception.InstanceNotFound

    def block_stats(self, instance_name, disk_id):
        if instance_name in self.instances:
            return [0L, 0L, 0L, 0L, None]
        else:
            raise exception.InstanceNotFound

    def interface_stats(self, instance_name, iface_id):
        if instance_name in self.instances:
            return [0L, 0L, 0L, 0L, 0L, 0L, 0L, 0L]
        else:
            raise exception.InstanceNotFound

    def get_console_output(self, instance):
        if instance['name'] in self.instances:
            return 'FAKE CONSOLE\xffOUTPUT'
        else:
            raise exception.InstanceNotFound

    def get_ajax_console(self, instance):
        if instance['name'] in self.instances:
            return {'token': 'FAKETOKEN',
                    'host': 'fakeajaxconsole.com',
                    'port': 6969}
        else:
            raise exception.InstanceNotFound

    def get_vnc_console(self, instance):
        if instance['name'] in self.instances:
            return {'token': 'FAKETOKEN',
                    'host': 'fakevncconsole.com',
                    'port': 6969}
        else:
            raise exception.InstanceNotFound

    def get_console_pool_info(self, console_type):
        return  {'address': '127.0.0.1',
                 'username': 'fakeuser',
                 'password': 'fakepassword'}

    def refresh_security_group_rules(self, security_group_id):
        return True

    def refresh_security_group_members(self, security_group_id):
        return True

    def refresh_provider_fw_rules(self):
        pass

    def update_available_resource(self, ctxt, host):
        """This method is supported only by libvirt."""
        result = db.service_get_all_by_topic(ctxt, 'compute')
        if len(result) == 0:
            raise exception.ComputeServiceUnavailable(host=host)

    def compare_cpu(self, xml):
        """This method is supported only by libvirt."""
        raise NotImplementedError('This method is supported only by libvirt.')

    def ensure_filtering_rules_for_instance(self, instance_ref, network_info):
        """This method is supported only by libvirt."""
        raise NotImplementedError('This method is supported only by libvirt.')

    def plug_vifs(self, instance, network_info):
        if instance['name'] in self.instances:
            pass
        else:
            raise exception.InstanceNotFound

    def finish_revert_migration(self, instance):
        if instance['name'] in self.instances:
            pass
        else:
            raise exception.InstanceNotFound

    def confirm_migration(self, migration, instance, network_info):
        if instance['name'] in self.instances:
            pass
        else:
            raise exception.InstanceNotFound

    def finish_migration(self, context, migration, instance, disk_info,
                         network_info, resize_instance):
        if instance['name'] in self.instances:
            pass
        else:
            raise exception.InstanceNotFound

    def live_migration(self, context, instance, dest,
                       post_method, recover_method, block_migration=False):
        if instance['name'] in self.instances:
            post_method(context, instance, dest, block_migration)
        else:
            recover_method(context, instance, dest, block_migration)

    def unfilter_instance(self, instance_ref, network_info):
        """This method is supported only by libvirt."""
        raise NotImplementedError('This method is supported only by libvirt.')

    def test_remove_vm(self, instance_name):
        """ Removes the named VM, as if it crashed. For testing"""
        self.instances.pop(instance_name)

    def update_host_status(self):
        """Return fake Host Status of ram, disk, network."""
        return self.host_status

    def get_host_stats(self, refresh=False):
        """Return fake Host Status of ram, disk, network."""
        return self.host_status

    def host_power_action(self, host, action):
        """Reboots, shuts down or powers up the host."""
        pass

    def set_host_enabled(self, host, enabled):
        """Sets the specified host's ability to accept new instances."""
        pass

    def get_instance_disk_info(self, ctxt, instance_ref):
        """This method is supported only by libvirt."""
        pass

    def post_live_migration_at_destination(self, ctxt,
                                           instance_ref,
                                           network_info,
                                           block_migration):
        """This method is supported only by libvirt."""
        pass

    def pre_block_migration(self, ctxt, instance_ref, disk_info_json):
        """This method is supported only by libvirt."""
        pass

    def revert_migration(self, instance_ref):
        pass
