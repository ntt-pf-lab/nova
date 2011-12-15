# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 Nicira Networks, Inc
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

import time

from netaddr import IPNetwork, IPAddress

from nova import db
from nova import context
from nova import exception
from nova import flags
from nova import log as logging
from nova import manager
from nova.network import manager
from nova.network.quantum import quantum_connection
from nova import utils

LOG = logging.getLogger("nova.network.quantum.manager")

FLAGS = flags.FLAGS

flags.DEFINE_string('quantum_ipam_lib',
                    'nova.network.quantum.nova_ipam_lib',
                    "Indicates underlying IP address management library")


flags.DEFINE_bool('quantum_use_dhcp', False,
                    'Whether or not to enable DHCP for networks')


class QuantumManager(manager.FlatManager):
    """NetworkManager class that communicates with a Quantum service
       via a web services API to provision VM network connectivity.

       For IP Address management, QuantumManager can be configured to
       use either Nova's local DB or the Melange IPAM service.

       Currently, the QuantumManager does NOT support any of the 'gateway'
       functionality implemented by the Nova VlanManager, including:
            * floating IPs
            * NAT gateway

       Support for these capabilities are targted for future releases.
    """

    def __init__(self, q_conn=None, ipam_lib=None, *args, **kwargs):
        """Initialize two key libraries, the connection to a
           Quantum service, and the library for implementing IPAM.

           Calls inherited FlatManager constructor.
        """

        if not q_conn:
            q_conn = quantum_connection.QuantumClientConnection()
        self.q_conn = q_conn

        if not ipam_lib:
            ipam_lib = FLAGS.quantum_ipam_lib
        self.ipam = utils.import_object(ipam_lib).get_ipam_lib(self)

        super(QuantumManager, self).__init__(*args, **kwargs)
        self.driver.init_host()
        # TODO(bgh): We'll need to enable these when we implement the full L3
        # functionalities
        # self.driver.ensure_metadata_ip()
        # self.driver.metadata_forward()

    def init_host(self):
        if FLAGS.quantum_use_dhcp:
            ctxt = context.get_admin_context()
            networks = db.network_get_all(ctxt) \
                         if db.network_count(ctxt) > 0 else []
            for net in networks:
                # set up dnsmasq for only used networks
                if self.get_dhcp_hosts_text(ctxt, net['uuid'], None) \
                    == "":
                    continue
                vif_rec = {'uuid': None}  # dummy
                self.enable_dhcp(ctxt, net['uuid'], net, vif_rec, None)

        # NOTE(oda): actually do nothing, so maybe OK not to call this.
        super(QuantumManager, self).init_host()
 
    def create_networks(self, context, label, cidr, multi_host, num_networks,
                        network_size, cidr_v6, gateway, gateway_v6, bridge,
                        bridge_interface, dns1=None, dns2=None, uuid=None,
                        **kwargs):
        """Unlike other NetworkManagers, with QuantumManager, each
           create_networks calls should create only a single network.

           Two scenarios exist:
                - no 'uuid' is specified, in which case we contact
                  Quantum and create a new network.
                - an existing 'uuid' is specified, corresponding to
                  a Quantum network created out of band.

           In both cases, we initialize a subnet using the IPAM lib.
        """
        if num_networks != 1:
            raise Exception(_("QuantumManager requires that only one"
                              " network is created per call"))
        q_tenant_id = kwargs["project_id"] or FLAGS.quantum_default_tenant_id
        quantum_net_id = uuid
        if quantum_net_id:
            if not self.q_conn.network_exists(q_tenant_id, quantum_net_id):
                    raise Exception(_("Unable to find existing quantum " \
                        " network for tenant '%(q_tenant_id)s' with "
                        "net-id '%(quantum_net_id)s'" % locals()))
        else:
            # otherwise, create network from default quantum pool
            quantum_net_id = self.q_conn.create_network(q_tenant_id, label)

        ipam_tenant_id = kwargs.get("project_id", None)
        priority = kwargs.get("priority", 0)
        self.ipam.create_subnet(context, label, ipam_tenant_id, quantum_net_id,
            priority, cidr, gateway, gateway_v6,
            cidr_v6, dns1, dns2)

        # reserve dhcp_server ip address
        # TODO(oda): dhcp_server ip address can be specified via 
        # the nova-manage network create.
        dhcp_server = str(IPAddress(IPNetwork(cidr).first + 2))
        self.ipam.reserve_fixed_ip(context, dhcp_server, quantum_net_id,
                  ipam_tenant_id)

        return [{'uuid': quantum_net_id}]

    def delete_network(self, context, fixed_range, uuid):
        """Lookup network by uuid, delete both the IPAM
           subnet and the corresponding Quantum network.

           The fixed_range parameter is kept here for interface compatibility
           but is not used.
        """
        # TODO(oda): should check whether the network is used or not
        # and go forward only if the network is not used.
        quantum_net_id = uuid
        project_id = context.project_id
        # TODO(bgh): The project_id isn't getting populated here for some
        # reason.. I'm not sure if it's an invalid assumption or just a bug.
        # In order to get the right quantum_net_id we'll have to query all the
        # project_ids for now.
        if project_id is None:
            projects = db.project_get_all(context)
            for p in projects:
                if self.q_conn.network_exists(p['id'], uuid):
                    project_id = p['id']
                    break
        LOG.debug("Deleting network for tenant: %s" % project_id)
        q_tenant_id = project_id or FLAGS.quantum_default_tenant_id
        if FLAGS.quantum_use_dhcp:
            # delete gw device for dhcp and delete the port from quantum
            # so that the network can be deleted.
            # do this while network_ref exists.
            admin_context = context.elevated()
            network = db.network_get_by_uuid(admin_context, quantum_net_id)
            self.driver.unplug(network)
            dev = self.driver.get_dev(network)
            port = self.q_conn.get_port_by_attachment(q_tenant_id,
                    quantum_net_id, dev)
            if port is not None:
                self.q_conn.detach_and_delete_port(q_tenant_id,
                        quantum_net_id, port)
            self.driver.kill_dhcp(dev)
        self.ipam.delete_subnets_by_net_id(context, quantum_net_id,
                project_id)
        self.q_conn.delete_network(q_tenant_id, quantum_net_id)

    def allocate_for_instance(self, context, **kwargs):
        """Called by compute when it is creating a new VM.

           There are three key tasks:
                - Determine the number and order of vNICs to create
                - Allocate IP addresses
                - Create ports on a Quantum network and attach vNICs.

           We support two approaches to determining vNICs:
                - By default, a VM gets a vNIC for any network belonging
                  to the VM's project, and a vNIC for any "global" network
                  that has a NULL project_id.  vNIC order is determined
                  by the network's 'priority' field.
                - If the 'os-create-server-ext' was used to create the VM,
                  only the networks in 'requested_networks' are used to
                  create vNICs, and the vNIC order is determiend by the
                  order in the requested_networks array.

           For each vNIC, use the FlatManager to create the entries
           in the virtual_interfaces table, contact Quantum to
           create a port and attachment the vNIC, and use the IPAM
           lib to allocate IP addresses.
        """
        instance_id = kwargs.pop('instance_id')
        instance_type_id = kwargs['instance_type_id']
        host = kwargs.pop('host')
        project_id = kwargs.pop('project_id')
        LOG.debug(_("network allocations for instance %s"), project_id)

        requested_networks = kwargs.get('requested_networks')

        if requested_networks:
            net_proj_pairs = [(net, project_id) for net in requested_networks]
        else:
            net_proj_pairs = [({'uuid': net_id, 'fixed_ip': None, 'gw': True},
                                 p_id) \
                   for (net_id, p_id) in \
                             self.ipam.get_project_and_global_net_ids(context,
                                                                project_id)]

        # Quantum may also know about networks that aren't in the networks
        # table so we need to query Quanutm for any tenant networks and add
        # them to net_proj_pairs.
        qnets = self.q_conn.get_networks(project_id)
        for qn in qnets['networks']:
            if qn['id'] not in (net['uuid'] for (net, _p) in net_proj_pairs):
                pair = ({'uuid': qn['id'], 'fixed_ip': None, 'gw': True},
                                                                project_id)
                net_proj_pairs.append(pair)

        # Create a port via quantum and attach the vif
        for (net, project_id) in net_proj_pairs:
            # FIXME(danwent): We'd like to have the manager be
            # completely decoupled from the nova networks table.
            # However, other parts of nova sometimes go behind our
            # back and access network data directly from the DB.  So
            # for now, the quantum manager knows that there is a nova
            # networks DB table and accesses it here.  updating the
            # virtual_interfaces table to use UUIDs would be one
            # solution, but this would require significant work
            # elsewhere.
            admin_context = context.elevated()

            # We may not be able to get a network_ref here if this network
            # isn't in the database (i.e. it came from Quantum).
            quantum_net_id = net['uuid']
            network_ref = db.network_get_by_uuid(admin_context,
                                                 quantum_net_id)
            if network_ref is None:
                network_ref = {}
                network_ref = {"uuid": quantum_net_id,
                    "project_id": project_id,
                    # NOTE(bgh): We need to document this somewhere but since
                    # we don't know the priority of any networks we get from
                    # quantum we just give them a priority of 0.  If its
                    # necessary to specify the order of the vifs and what
                    # network they map to then the user will have to use the
                    # OSCreateServer extension and specify them explicitly.
                    #
                    # In the future users will be able to tag quantum networks
                    # with a priority .. and at that point we can update the
                    # code here to reflect that.
                    "priority": 0,
                    "id": 'NULL',
                    "label": "quantum-net-%s" % quantum_net_id}

            vif_rec = manager.FlatManager.add_virtual_interface(self,
                                  context, instance_id, network_ref['id'])

            # talk to Quantum API to create and attach port.
            q_tenant_id = project_id or FLAGS.quantum_default_tenant_id
            self.q_conn.create_and_attach_port(q_tenant_id, quantum_net_id,
                                               vif_rec['uuid'])
            # Tell melange to allocate an IP
            ip = self.ipam.allocate_fixed_ip(context, net,
                     project_id, vif_rec)
            # Set up/start the dhcp server for this network if necessary
            if FLAGS.quantum_use_dhcp:
                self.enable_dhcp(context, quantum_net_id, network_ref,
                    vif_rec, project_id)
        return self.get_instance_nw_info(context, instance_id,
                                         instance_type_id, host)

    def enable_dhcp(self, context, quantum_net_id, network_ref, vif_rec,
            project_id):
        LOG.info("Using DHCP for network: %s" % network_ref['label'])
        # Figure out the ipam tenant id for this subnet:  We need to
        # query for the tenant_id since the network could be created
        # with the project_id as the tenant or the default tenant.
        ipam_tenant_id = self.ipam.get_tenant_id_by_net_id(context,
            quantum_net_id, vif_rec['uuid'], project_id)
        # Figure out what subnets correspond to this network
        v4_subnet, v6_subnet = self.ipam.get_subnets_by_net_id(context,
                    ipam_tenant_id, quantum_net_id, vif_rec['uuid'])
        # Set up (or find) the dhcp server for each of the subnets
        # returned above (both v4 and v6).
        for subnet in [v4_subnet, v6_subnet]:
            if subnet is None or subnet['cidr'] is None:
                continue
            # Fill in some of the network fields that we would have
            # previously gotten from the network table (they'll be
            # passed to the linux_net functions).
            network_ref['cidr'] = subnet['cidr']
            n = IPNetwork(subnet['cidr'])
            network_ref['dhcp_server'] = IPAddress(n.first + 2)
            # TODO(bgh): Melange should probably track dhcp_start
            if not 'dhcp_start' in network_ref or \
                    network_ref['dhcp_start'] is None:
                network_ref['dhcp_start'] = IPAddress(n.first + 1)
            network_ref['broadcast'] = IPAddress(n.broadcast)
            network_ref['gateway'] = subnet['gateway']
            # Construct the interface id that we'll use for the bridge
            interface_id = "gw-" + str(network_ref['uuid'][0:11])
            network_ref['bridge'] = interface_id
            # Query quantum to see if we've already created a port for
            # the gateway device and attached the device to the port.
            # If we haven't then we need to intiialize it and create
            # it.  This device will be the one serving dhcp via
            # dnsmasq.
            if not self.driver.device_exists(interface_id):
                mac_address = self.generate_mac_address()
                is_gw = (network_ref['gateway'] != network_ref['dhcp_server'])
                self.driver.plug(network_ref, mac_address,
                    gateway=is_gw)
                self.driver.initialize_gateway_device(interface_id, network_ref)
                LOG.debug("Intializing DHCP for network: %s" %
                    network_ref)
            q_tenant_id = project_id or FLAGS.quantum_default_tenant_id
            port = self.q_conn.get_port_by_attachment(q_tenant_id,
                    quantum_net_id, interface_id)
            if not port:
                self.q_conn.create_and_attach_port(q_tenant_id,
                        quantum_net_id, interface_id)

            hosts = self.get_dhcp_hosts_text(context,
                subnet['network_id'], project_id)
            self.driver.update_dhcp_hostfile_with_text(interface_id, hosts)
            self.driver.restart_dhcp(interface_id, network_ref)

    def get_instance_nw_info(self, context, instance_id,
                                instance_type_id, host):
        """This method is used by compute to fetch all network data
           that should be used when creating the VM.

           The method simply loops through all virtual interfaces
           stored in the nova DB and queries the IPAM lib to get
           the associated IP data.

           The format of returned data is 'defined' by the initial
           set of NetworkManagers found in nova/network/manager.py .
           Ideally this 'interface' will be more formally defined
           in the future.
        """
        network_info = []
        instance = db.instance_get(context, instance_id)
        project_id = instance.project_id

        admin_context = context.elevated()
        vifs = db.virtual_interface_get_by_instance(admin_context,
                                                    instance_id)
        for vif in vifs:
            net = db.network_get(admin_context, vif['network_id'])
            net_id = net['uuid']

            if not net_id:
                # TODO(bgh): We need to figure out a way to tell if we
                # should actually be raising this exception or not.
                # In the case that a VM spawn failed it may not have
                # attached the vif and raising the exception here
                # prevents deletion of the VM.  In that case we should
                # probably just log, continue, and move on.
                raise Exception(_("No network for for virtual interface %s") %
                                vif['uuid'])

            ipam_tenant_id = self.ipam.get_tenant_id_by_net_id(context,
                net_id, vif['uuid'], project_id)
            v4_subnet, v6_subnet = \
                    self.ipam.get_subnets_by_net_id(context,
                            ipam_tenant_id, net_id, vif['uuid'])

            v4_ips = self.ipam.get_v4_ips_by_interface(context,
                                        net_id, vif['uuid'],
                                        project_id=ipam_tenant_id)
            v6_ips = self.ipam.get_v6_ips_by_interface(context,
                                        net_id, vif['uuid'],
                                        project_id=ipam_tenant_id)

            def ip_dict(ip, subnet):
                return {
                    "ip": ip,
                    "netmask": subnet["netmask"],
                    "enabled": "1"}

            network_dict = {
                'cidr': v4_subnet['cidr'],
                'injected': False,
                'multi_host': False}

            info = {
                'gateway': v4_subnet['gateway'],
                'dhcp_server': v4_subnet['gateway'],
                'broadcast': v4_subnet['broadcast'],
                'mac': vif['address'],
                'vif_uuid': vif['uuid'],
                'dns': [],
                'ips': [ip_dict(ip, v4_subnet) for ip in v4_ips]}

            if v6_subnet:
                if v6_subnet['cidr']:
                    network_dict['cidr_v6'] = v6_subnet['cidr']
                    info['ip6s'] = [ip_dict(ip, v6_subnet) for ip in v6_ips]

                if v6_subnet['gateway']:
                    info['gateway6'] = v6_subnet['gateway']

            dns_dict = {}
            for s in [v4_subnet, v6_subnet]:
                for k in ['dns1', 'dns2']:
                    if s and s[k]:
                        dns_dict[s[k]] = None
            info['dns'] = [d for d in dns_dict.keys()]

            network_info.append((network_dict, info))
        return network_info

    def deallocate_for_instance(self, context, **kwargs):
        """Called when a VM is terminated.  Loop through each virtual
           interface in the Nova DB and remove the Quantum port and
           clear the IP allocation using the IPAM.  Finally, remove
           the virtual interfaces from the Nova DB.
        """
        instance_id = kwargs.get('instance_id')
        project_id = kwargs.pop('project_id', None)

        admin_context = context.elevated()
        vifs = db.virtual_interface_get_by_instance(admin_context,
                                                    instance_id)
        for vif_ref in vifs:
            interface_id = vif_ref['uuid']
            q_tenant_id = project_id

            network_ref = db.network_get(admin_context, vif_ref['network_id'])
            net_id = network_ref['uuid']

            port_id = self.q_conn.get_port_by_attachment(q_tenant_id,
                                                         net_id, interface_id)
            if not port_id:
                q_tenant_id = FLAGS.quantum_default_tenant_id
                port_id = self.q_conn.get_port_by_attachment(
                    q_tenant_id, net_id, interface_id)

            if not port_id:
                LOG.error("Unable to find port with attachment: %s" %
                          (interface_id))
            else:
                self.q_conn.detach_and_delete_port(q_tenant_id,
                                                   net_id, port_id)

            ipam_tenant_id = self.ipam.get_tenant_id_by_net_id(context,
                net_id, vif_ref['uuid'], project_id)

            self.ipam.deallocate_ips_by_vif(context, ipam_tenant_id,
                                            net_id, vif_ref)

            # If DHCP is enabled on this network then we need to update the
            # leases and restart the server.
            if FLAGS.quantum_use_dhcp:
                self.update_dhcp(context, ipam_tenant_id, network_ref, vif_ref,
                    project_id)
        try:
            db.virtual_interface_delete_by_instance(admin_context,
                                                    instance_id)
        except exception.InstanceNotFound:
            LOG.error(_("Attempted to deallocate non-existent instance: %s" %
                        (instance_id)))

    # TODO(bgh): At some point we should consider merging enable_dhcp() and
    # update_dhcp()
    def update_dhcp(self, context, ipam_tenant_id, network_ref, vif_ref,
            project_id):
        # Figure out what subnet corresponds to this network/vif
        v4_subnet, v6_subnet = self.ipam.get_subnets_by_net_id(context,
                        ipam_tenant_id, network_ref['uuid'], vif_ref['uuid'])
        for subnet in [v4_subnet, v6_subnet]:
            if subnet is None or subnet['cidr'] is None:
                continue
            # Fill in some of the network fields that we would have
            # previously gotten from the network table (they'll be
            # passed to the linux_net functions).
            network_ref['cidr'] = subnet['cidr']
            n = IPNetwork(subnet['cidr'])
            network_ref['dhcp_server'] = IPAddress(n.first + 2)
            network_ref['dhcp_start'] = IPAddress(n.first + 1)
            network_ref['broadcast'] = IPAddress(n.broadcast)
            network_ref['gateway'] = subnet['gateway']
            dev = "gw-" + str(network_ref['uuid'][0:11])
            # And remove the dhcp mappings for the subnet
            hosts = self.get_dhcp_hosts_text(context,
                subnet['network_id'], project_id)
            self.driver.update_dhcp_hostfile_with_text(dev, hosts)
            # Restart dnsmasq
            self.driver.kill_dhcp(dev)
            self.driver.restart_dhcp(dev, network_ref)

            # TODO(bgh): if this is the last instance for the network
            # then we should actually just kill the dhcp server.

    def validate_networks(self, context, networks):
        """Validates that this tenant has quantum networks with the associated
           UUIDs.  This is called by the 'os-create-server-ext' API extension
           code so that we can return an API error code to the caller if they
           request an invalid network.
        """
        if networks is None:
            return

        project_id = context.project_id
        for net in networks:
            # TODO(bgh): At some point we should figure out whether or
            # not we want the verify_subnet_exists call to be optional.
            net_id = net['uuid']
            if not self.ipam.verify_subnet_exists(context, project_id,
                                                  net_id):
                raise exception.NetworkNotFound(network_id=net_id)
            if not self.q_conn.network_exists(project_id, net_id):
                raise exception.NetworkNotFound(network_id=net_id)

    # NOTE(bgh): deallocate_for_instance will take care of this..  The reason
    # we're providing this is so that NetworkManager::release_fixed_ip() isn't
    # called.  It does some database operations that we don't want to happen
    # and since the majority of the stuff that it does is already taken care
    # of in our deallocate_for_instance call we don't need to do anything.
    def release_fixed_ip(self, context, address):
        pass

    def get_dhcp_hosts_text(self, context, subnet_id, project_id=None):
        ips = self.ipam.get_allocated_ips(context, subnet_id, project_id)
        hosts_text = ""
        admin_context = context.elevated()
        for ip in ips:
            address, vif_id, gw = ip
            vif = db.virtual_interface_get_by_uuid(admin_context, vif_id)
            mac_address = vif['address']
            set_gw = ",set:nor" if not gw else ""
            text = "%s,%s.%s,%s%s\n" % (mac_address, "host-" + address,
                    FLAGS.dhcp_domain, address, set_gw)
            hosts_text += text
        LOG.debug("DHCP hosts: %s" % hosts_text)
        return hosts_text

    def get_dhcp_leases(self, context, network_ref):
        """Return a network's hosts config in dnsmasq leasefile format."""
        subnet_id = network_ref['uuid']
        project_id = network_ref['project_id']
        ips = self.ipam.get_allocated_ips(context, subnet_id, project_id)
        leases_text = ""
        admin_context = context.elevated()
        for ip in ips:
            address, vif_id, gw = ip
            vif = db.virtual_interface_get_by_uuid(admin_context, vif_id)
            mac_address = vif['address']
            text = "%s %s %s %s *\n" % \
                (int(time.time()) - FLAGS.dhcp_lease_time,
                 mac_address, address, '*')
            leases_text += text
        LOG.debug("DHCP leases: %s" % leases_text)
        return leases_text

    # NOTE(oda): quick work around
    @property
    def _bottom_reserved_ips(self):
        return 1  # network
