# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
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

from nova import test
from nova import exception
from nova.exception import NovaException

from nose.plugins.skip import SkipTest
from nose.plugins.attrib import attr


class ApiErrorTestCase(test.TestCase):
    def test_return_valid_error(self):
        # without 'code' arg
        err = exception.ApiError('fake error')
        self.assertEqual(err.__str__(), 'fake error')
        self.assertEqual(err.code, None)
        self.assertEqual(err.msg, 'fake error')
        # with 'code' arg
        err = exception.ApiError('fake error', 'blah code')
        self.assertEqual(err.__str__(), 'blah code: fake error')
        self.assertEqual(err.code, 'blah code')
        self.assertEqual(err.msg, 'fake error')


class FakeNotifier(object):
    """Acts like the nova.notifier.api module."""
    ERROR = 88

    def __init__(self):
        self.provided_publisher = None
        self.provided_event = None
        self.provided_priority = None
        self.provided_payload = None

    def notify(self, publisher, event, priority, payload):
        self.provided_publisher = publisher
        self.provided_event = event
        self.provided_priority = priority
        self.provided_payload = payload


def good_function():
    return 99


def bad_function_error():
    raise exception.Error()


def bad_function_exception():
    raise Exception()


class WrapExceptionTestCase(test.TestCase):
    def test_wrap_exception_good_return(self):
        wrapped = exception.wrap_exception()
        self.assertEquals(99, wrapped(good_function)())

    def test_wrap_exception_throws_error(self):
        wrapped = exception.wrap_exception()
        self.assertRaises(exception.Error, wrapped(bad_function_error))

    def test_wrap_exception_throws_exception(self):
        wrapped = exception.wrap_exception()
        self.assertRaises(Exception, wrapped(bad_function_exception))

    def test_wrap_exception_with_notifier(self):
        notifier = FakeNotifier()
        wrapped = exception.wrap_exception(notifier, "publisher", "event",
                                           "level")
        self.assertRaises(Exception, wrapped(bad_function_exception))
        self.assertEquals(notifier.provided_publisher, "publisher")
        self.assertEquals(notifier.provided_event, "event")
        self.assertEquals(notifier.provided_priority, "level")
        for key in ['exception', 'args']:
            self.assertTrue(key in notifier.provided_payload.keys())

    def test_wrap_exception_with_notifier_defaults(self):
        notifier = FakeNotifier()
        wrapped = exception.wrap_exception(notifier)
        self.assertRaises(Exception, wrapped(bad_function_exception))
        self.assertEquals(notifier.provided_publisher, None)
        self.assertEquals(notifier.provided_event, "bad_function_exception")
        self.assertEquals(notifier.provided_priority, notifier.ERROR)


class NovaExceptionTestCase(test.TestCase):

    @attr(kind='small')
    def test_initialize_error(self):
        self.stubs.Set(NovaException, "message", "%s %id")
        ex = NovaException(test="test")
        self.assertEqual("%s %id", str(ex))

    @attr(kind='small')
    def test_ImagePaginationFailed(self):
        ex = exception.ImagePaginationFailed()
        self.assertEqual("Failed to paginate through images "
                         "from image service",
                          str(ex))

    @attr(kind='small')
    def test_VirtualInterfaceCreateException(self):
        ex = exception.VirtualInterfaceCreateException()
        self.assertEqual("Virtual Interface creation failed", str(ex))

    @attr(kind='small')
    def test_VirtualInterfaceMacAddressException(self):
        ex = exception.VirtualInterfaceMacAddressException()
        self.assertEqual("5 attempts to create virtual interface"
                "with unique mac address failed", str(ex))

    @attr(kind='small')
    def test_NotAuthorized(self):
        ex = exception.NotAuthorized()
        self.assertEqual("Not authorized.", str(ex))

    @attr(kind='small')
    def test_AdminRequired(self):
        ex = exception.AdminRequired()
        self.assertEqual("User does not have admin privileges", str(ex))

    @attr(kind='small')
    def test_Invalid(self):
        ex = exception.Invalid()
        self.assertEqual("Unacceptable parameters.", str(ex))

    @attr(kind='small')
    def test_InvalidSignature(self):
        ex = exception.InvalidSignature(signature="SIG", user="TEST")
        self.assertEqual("Invalid signature SIG for user TEST.", str(ex))

    @attr(kind='small')
    def test_InvalidInput(self):
        ex = exception.InvalidInput(reason="TEST")
        self.assertEqual("Invalid input received: TEST", str(ex))

    @attr(kind='small')
    def test_InvalidInstanceType(self):
        ex = exception.InvalidInstanceType(instance_type="TEST")
        self.assertEqual("Invalid instance type TEST.", str(ex))

    @attr(kind='small')
    def test_InvalidVolumeType(self):
        ex = exception.InvalidVolumeType(volume_type="TEST")
        self.assertEqual("Invalid volume type TEST.", str(ex))

    @attr(kind='small')
    def test_InvalidPortRange(self):
        ex = exception.InvalidPortRange(from_port=0, to_port=80)
        self.assertEqual("Invalid port range 0:80.", str(ex))

    @attr(kind='small')
    def test_InvalidIpProtocol(self):
        ex = exception.InvalidIpProtocol(protocol="http")
        self.assertEqual("Invalid IP protocol http.", str(ex))

    @attr(kind='small')
    def test_InvalidContentType(self):
        ex = exception.InvalidContentType(content_type="text")
        self.assertEqual("Invalid content type text.", str(ex))

    @attr(kind='small')
    def test_InvalidCidr(self):
        ex = exception.InvalidCidr(cidr="0.0.0.0")
        self.assertEqual("Invalid cidr 0.0.0.0.", str(ex))

    @attr(kind='small')
    def test_InvalidParameterValue(self):
        ex = exception.InvalidParameterValue(err="params")
        self.assertEqual("params", str(ex))

    @attr(kind='small')
    def test_InstanceNotRunning(self):
        ex = exception.InstanceNotRunning(instance_id="i-xxxxxxxx")
        self.assertEqual("Instance i-xxxxxxxx is not running.", str(ex))

    @attr(kind='small')
    def test_InstanceNotSuspended(self):
        ex = exception.InstanceNotSuspended(instance_id="i-xxxxxxxx")
        self.assertEqual("Instance i-xxxxxxxx is not suspended.", str(ex))

    @attr(kind='small')
    def test_InstanceNotInRescueMode(self):
        ex = exception.InstanceNotInRescueMode(instance_id="i-xxxxxxxx")
        self.assertEqual("Instance i-xxxxxxxx is not in rescue mode", str(ex))

    @attr(kind='small')
    def test_InstanceSuspendFailure(self):
        ex = exception.InstanceSuspendFailure(reason="TEST")
        self.assertEqual("Failed to suspend instance: TEST", str(ex))

    @attr(kind='small')
    def test_InstanceResumeFailure(self):
        ex = exception.InstanceResumeFailure(reason="TEST")
        self.assertEqual("Failed to resume server: TEST.", str(ex))

    @attr(kind='small')
    def test_InstanceRebootFailure(self):
        ex = exception.InstanceRebootFailure(reason="TEST")
        self.assertEqual("Failed to reboot instance: TEST", str(ex))

    @attr(kind='small')
    def test_ServiceUnavailable(self):
        ex = exception.ServiceUnavailable()
        self.assertEqual("Service is unavailable at this time.", str(ex))

    @attr(kind='small')
    def test_VolumeServiceUnavailable(self):
        ex = exception.VolumeServiceUnavailable()
        self.assertEqual("Volume service is unavailable at this time.",
                         str(ex))

    @attr(kind='small')
    def test_ComputeServiceUnavailable(self):
        ex = exception.ComputeServiceUnavailable()
        self.assertEqual("Compute service is unavailable at this time.",
                         str(ex))

    @attr(kind='small')
    def test_UnableToMigrateToSelf(self):
        ex = exception.UnableToMigrateToSelf(instance_id="i-xxxxxxxx",
                                             host="test")
        self.assertEqual("Unable to migrate instance (i-xxxxxxxx) "
                "to current host (test).", str(ex))

    @attr(kind='small')
    def test_SourceHostUnavailable(self):
        ex = exception.SourceHostUnavailable()
        self.assertEqual("Original compute host is unavailable at this time.",
                         str(ex))

    @attr(kind='small')
    def test_InvalidHypervisorType(self):
        ex = exception.InvalidHypervisorType()
        self.assertEqual("The supplied hypervisor type of is invalid.",
                         str(ex))

    @attr(kind='small')
    def test_DestinationHypervisorTooOld(self):
        ex = exception.DestinationHypervisorTooOld()
        self.assertEqual("The instance requires a newer hypervisor version "
                         "than has been provided.", str(ex))

    @attr(kind='small')
    def test_DestinationDiskExists(self):
        ex = exception.DestinationDiskExists(path="/var")
        self.assertEqual("The supplied disk path (/var) already exists, "
                "it is expected not to exist.", str(ex))

    @attr(kind='small')
    def test_InvalidDevicePath(self):
        ex = exception.InvalidDevicePath(path="/var")
        self.assertEqual("The supplied device path (/var) is invalid.",
                         str(ex))

    @attr(kind='small')
    def test_InvalidCPUInfo(self):
        ex = exception.InvalidCPUInfo(reason="TEST")
        self.assertEqual("Unacceptable CPU info: TEST", str(ex))

    @attr(kind='small')
    def test_InvalidVLANTag(self):
        ex = exception.InvalidVLANTag(bridge="br100",
                                      tag="100",
                                      pgroup="TEST")
        self.assertEqual("VLAN tag is not appropriate for the port group "
                "br100. Expected VLAN tag is 100, "
                "but the one associated with the port group is TEST.",
                str(ex))

    @attr(kind='small')
    def test_InvalidVLANPortGroup(self):
        ex = exception.InvalidVLANPortGroup(bridge="br100",
                                            expected="100",
                                            actual="10")
        self.assertEqual("vSwitch which contains the port group br100 is "
                "not associated with the desired physical adapter. "
                "Expected vSwitch is 100, but the one associated "
                "is 10.", str(ex))

    @attr(kind='small')
    def test_InvalidDiskFormat(self):
        ex = exception.InvalidDiskFormat(disk_format="TEST")
        self.assertEqual("Disk format TEST is not acceptable", str(ex))

    @attr(kind='small')
    def test_ImageUnacceptable(self):
        ex = exception.ImageUnacceptable(image_id="ami", reason="TEST")
        self.assertEqual("Image ami is unacceptable: TEST", str(ex))

    @attr(kind='small')
    def test_InstanceUnacceptable(self):
        ex = exception.InstanceUnacceptable(instance_id="i", reason="TEST")
        self.assertEqual("Instance i is unacceptable: TEST", str(ex))

    @attr(kind='small')
    def test_InvalidEc2Id(self):
        ex = exception.InvalidEc2Id(ec2_id="i")
        self.assertEqual("Ec2 id i is unacceptable.", str(ex))

    @attr(kind='small')
    def test_NotFound(self):
        ex = exception.NotFound()
        self.assertEqual("Resource could not be found.", str(ex))

    @attr(kind='small')
    def test_FlagNotSet(self):
        ex = exception.FlagNotSet(flag="test")
        self.assertEqual("Required flag test not set.", str(ex))

    @attr(kind='small')
    def test_InstanceNotFound(self):
        ex = exception.InstanceNotFound(instance_id="i")
        self.assertEqual("Instance i could not be found.", str(ex))

    @attr(kind='small')
    def test_VolumeNotFound(self):
        ex = exception.VolumeNotFound(volume_id="v")
        self.assertEqual("Volume v could not be found.", str(ex))

    @attr(kind='small')
    def test_VolumeNotFoundForInstance(self):
        ex = exception.VolumeNotFoundForInstance(instance_id="i")
        self.assertEqual("Volume not found for instance i.", str(ex))

    @attr(kind='small')
    def test_VolumeMetadataNotFound(self):
        ex = exception.VolumeMetadataNotFound(volume_id="v",
                                              metadata_key="key")
        self.assertEqual("Volume v has no metadata with "
                "key key.", str(ex))

    @attr(kind='small')
    def test_NoVolumeTypesFound(self):
        ex = exception.NoVolumeTypesFound()
        self.assertEqual("Zero volume types found.", str(ex))

    @attr(kind='small')
    def test_VolumeTypeNotFound(self):
        ex = exception.VolumeTypeNotFound(volume_type_id="type")
        self.assertEqual("Volume type type could not be found.", str(ex))

    @attr(kind='small')
    def test_VolumeTypeNotFoundByName(self):
        ex = exception.VolumeTypeNotFoundByName(volume_type_name="name")
        self.assertEqual("Volume type with name name "
                "could not be found.", str(ex))

    @attr(kind='small')
    def test_VolumeTypeExtraSpecsNotFound(self):
        ex = exception.VolumeTypeExtraSpecsNotFound(volume_type_id="v",
                                                    extra_specs_key="k")
        self.assertEqual("Volume Type v has no extra specs with "
                "key k.", str(ex))

    @attr(kind='small')
    def test_SnapshotNotFound(self):
        ex = exception.SnapshotNotFound(snapshot_id="s")
        self.assertEqual("Snapshot s could not be found.", str(ex))

    @attr(kind='small')
    def test_VolumeIsBusy(self):
        raise SkipTest
        ex = exception.VolumeIsBusy(volume_name="vol")
        self.assertEqual("deleting volume vol that has snapshot", str(ex))

    @attr(kind='small')
    def test_ExportDeviceNotFoundForVolume(self):
        ex = exception.ExportDeviceNotFoundForVolume(volume_id="vol")
        self.assertEqual("No export device found for volume vol.", str(ex))

    @attr(kind='small')
    def test_ISCSITargetNotFoundForVolume(self):
        ex = exception.ISCSITargetNotFoundForVolume(volume_id="vol")
        self.assertEqual("No target id found for volume vol.", str(ex))

    @attr(kind='small')
    def test_DiskNotFound(self):
        ex = exception.DiskNotFound(location="/")
        self.assertEqual("No disk at /", str(ex))

    @attr(kind='small')
    def test_InvalidImageRef(self):
        ex = exception.InvalidImageRef(image_href="ami")
        self.assertEqual("Invalid image href ami.", str(ex))

    @attr(kind='small')
    def test_ListingImageRefsNotSupported(self):
        ex = exception.ListingImageRefsNotSupported()
        self.assertEqual("Some images have been stored via hrefs."
        + " This version of the api does not support displaying image hrefs.",
        str(ex))

    @attr(kind='small')
    def test_ImageNotFound(self):
        ex = exception.ImageNotFound(image_id="ami")
        self.assertEqual("Image ami could not be found.", str(ex))

    @attr(kind='small')
    def test_KernelNotFoundForImage(self):
        ex = exception.KernelNotFoundForImage(image_id="ami")
        self.assertEqual("Kernel not found for image ami.", str(ex))

    @attr(kind='small')
    def test_UserNotFound(self):
        ex = exception.UserNotFound(user_id="test")
        self.assertEqual("User test could not be found.", str(ex))

    @attr(kind='small')
    def test_ProjectNotFound(self):
        ex = exception.ProjectNotFound(project_id="test")
        self.assertEqual("Project test could not be found.", str(ex))

    @attr(kind='small')
    def test_ProjectMembershipNotFound(self):
        ex = exception.ProjectMembershipNotFound(user_id="test",
                                                 project_id="test")
        self.assertEqual("User test is not a member of project test.",
                         str(ex))

    @attr(kind='small')
    def test_UserRoleNotFound(self):
        ex = exception.UserRoleNotFound(role_id="test")
        self.assertEqual("Role test could not be found.", str(ex))

    @attr(kind='small')
    def test_StorageRepositoryNotFound(self):
        ex = exception.StorageRepositoryNotFound()
        self.assertEqual("Cannot find SR to read/write VDI.", str(ex))

    @attr(kind='small')
    def test_NetworkNotCreated(self):
        ex = exception.NetworkNotCreated(req="vconfig")
        self.assertEqual("vconfig is required to create a network.", str(ex))

    @attr(kind='small')
    def test_NetworkNotFound(self):
        ex = exception.NetworkNotFound(network_id="default")
        self.assertEqual("Network default could not be found.", str(ex))

    @attr(kind='small')
    def test_NetworkNotFoundForBridge(self):
        ex = exception.NetworkNotFoundForBridge(bridge="default")
        self.assertEqual("Network could not be found for bridge default",
                         str(ex))

    @attr(kind='small')
    def test_NetworkNotFoundForUUID(self):
        ex = exception.NetworkNotFoundForUUID(
                            uuid="99999999-9999-9999-9999-999999999999")
        self.assertEqual("Network could not be found for uuid "
                         "99999999-9999-9999-9999-999999999999",
                         str(ex))

    @attr(kind='small')
    def test_NetworkNotFoundForCidr(self):
        ex = exception.NetworkNotFoundForCidr(cidr="0.0.0.0")
        self.assertEqual("Network could not be found with cidr 0.0.0.0.",
                         str(ex))

    @attr(kind='small')
    def test_NetworkNotFoundForInstance(self):
        ex = exception.NetworkNotFoundForInstance(instance_id="i")
        self.assertEqual("Network could not be found for instance i.",
                         str(ex))

    @attr(kind='small')
    def test_NoNetworksFound(self):
        ex = exception.NoNetworksFound()
        self.assertEqual("No networks defined.", str(ex))

    @attr(kind='small')
    def test_NetworkNotFoundForProject(self):
        ex = exception.NetworkNotFoundForProject(network_uuid="i",
                                                 project_id="test")
        self.assertEqual("Either Network uuid i is not present or "
                "is not assigned to the project test.", str(ex))

    @attr(kind='small')
    def test_NetworkHostNotSet(self):
        ex = exception.NetworkHostNotSet(network_id="i")
        self.assertEqual("Host is not set to the network (i).", str(ex))

    @attr(kind='small')
    def test_DatastoreNotFound(self):
        ex = exception.DatastoreNotFound()
        self.assertEqual("Could not find the datastore reference(s) "
                         "which the VM uses.", str(ex))

    @attr(kind='small')
    def test_FixedIpNotFound(self):
        ex = exception.FixedIpNotFound(id="0")
        self.assertEqual("No fixed IP associated with id 0.", str(ex))

    @attr(kind='small')
    def test_FixedIpNotFoundForAddress(self):
        ex = exception.FixedIpNotFoundForAddress(address="test")
        self.assertEqual("Fixed ip not found for address test.", str(ex))

    @attr(kind='small')
    def test_FixedIpNotFoundForInstance(self):
        ex = exception.FixedIpNotFoundForInstance(instance_id="i")
        self.assertEqual("Instance i has zero fixed ips.", str(ex))

    @attr(kind='small')
    def test_FixedIpNotFoundForNetworkHost(self):
        ex = exception.FixedIpNotFoundForNetworkHost(host="h", network_id="i")
        self.assertEqual("Network host h has zero fixed ips "
                "in network i.", str(ex))

    @attr(kind='small')
    def test_FixedIpNotFoundForSpecificInstance(self):
        ex = exception.FixedIpNotFoundForSpecificInstance(ip="h",
                                                          instance_id="i")
        self.assertEqual("Instance i doesn't have fixed ip 'h'.", str(ex))

    @attr(kind='small')
    def test_FixedIpNotFoundForVirtualInterface(self):
        ex = exception.FixedIpNotFoundForVirtualInterface(vif_id="h")
        self.assertEqual("Virtual interface h has zero associated fixed ips.",
                         str(ex))

    @attr(kind='small')
    def test_FixedIpNotFoundForHost(self):
        ex = exception.FixedIpNotFoundForHost(host="h")
        self.assertEqual("Host h has zero fixed ips.", str(ex))

    @attr(kind='small')
    def test_FixedIpNotFoundForNetwork(self):
        ex = exception.FixedIpNotFoundForNetwork(address="h",
                                                 network_uuid="i")
        self.assertEqual("Fixed IP address (h) does not exist in "
                "network (i).", str(ex))

    @attr(kind='small')
    def test_FixedIpAlreadyInUse(self):
        ex = exception.FixedIpAlreadyInUse(address="h")
        self.assertEqual("Fixed IP address h is already in use.", str(ex))

    @attr(kind='small')
    def test_FixedIpInvalid(self):
        ex = exception.FixedIpInvalid(address="h")
        self.assertEqual("Fixed IP address h is invalid.", str(ex))

    @attr(kind='small')
    def test_NoMoreFixedIps(self):
        ex = exception.NoMoreFixedIps()
        self.assertEqual("Zero fixed ips available.", str(ex))

    @attr(kind='small')
    def test_NoFixedIpsDefined(self):
        ex = exception.NoFixedIpsDefined()
        self.assertEqual("Zero fixed ips could be found.", str(ex))

    @attr(kind='small')
    def test_FloatingIpNotFound(self):
        ex = exception.FloatingIpNotFound(id="i")
        self.assertEqual("Floating ip not found for id i.", str(ex))

    @attr(kind='small')
    def test_FloatingIpNotFoundForAddress(self):
        ex = exception.FloatingIpNotFoundForAddress(address="a")
        self.assertEqual("Floating ip not found for address a.", str(ex))

    @attr(kind='small')
    def test_FloatingIpNotFoundForProject(self):
        ex = exception.FloatingIpNotFoundForProject(project_id="p")
        self.assertEqual("Floating ip not found for project p.", str(ex))

    @attr(kind='small')
    def test_FloatingIpNotFoundForHost(self):
        ex = exception.FloatingIpNotFoundForHost(host="h")
        self.assertEqual("Floating ip not found for host h.", str(ex))

    @attr(kind='small')
    def test_NoMoreFloatingIps(self):
        ex = exception.NoMoreFloatingIps()
        self.assertEqual("Zero floating ips available.", str(ex))

    @attr(kind='small')
    def test_FloatingIpAlreadyInUse(self):
        ex = exception.FloatingIpAlreadyInUse(address="h", fixed_ip="f")
        self.assertEqual("Floating ip h already in use by f.", str(ex))

    @attr(kind='small')
    def test_NoFloatingIpsDefined(self):
        ex = exception.NoFloatingIpsDefined()
        self.assertEqual("Zero floating ips exist.", str(ex))

    @attr(kind='small')
    def test_KeypairNotFound(self):
        ex = exception.KeypairNotFound(keypair_name="k", user_id="test")
        self.assertEqual("Keypair k not found for user test", str(ex))

    @attr(kind='small')
    def test_CertificateNotFound(self):
        ex = exception.CertificateNotFound(certificate_id="c")
        self.assertEqual("Certificate c not found.", str(ex))

    @attr(kind='small')
    def test_ServiceNotFound(self):
        ex = exception.ServiceNotFound(service_id="s")
        self.assertEqual("Service s could not be found.", str(ex))

    @attr(kind='small')
    def test_HostNotFound(self):
        ex = exception.HostNotFound(host="h")
        self.assertEqual("Host h could not be found.", str(ex))

    @attr(kind='small')
    def test_ComputeHostNotFound(self):
        ex = exception.ComputeHostNotFound(host="h")
        self.assertEqual("Compute host h could not be found.", str(ex))

    @attr(kind='small')
    def test_HostBinaryNotFound(self):
        ex = exception.HostBinaryNotFound(binary="b", host="h")
        self.assertEqual("Could not find binary b on host h.", str(ex))

    @attr(kind='small')
    def test_AuthTokenNotFound(self):
        ex = exception.AuthTokenNotFound(token="t")
        self.assertEqual("Auth token t could not be found.", str(ex))

    @attr(kind='small')
    def test_AccessKeyNotFound(self):
        ex = exception.AccessKeyNotFound(access_key="a")
        self.assertEqual("Access Key a could not be found.", str(ex))

    @attr(kind='small')
    def test_QuotaNotFound(self):
        ex = exception.QuotaNotFound()
        self.assertEqual("Quota could not be found", str(ex))

    @attr(kind='small')
    def test_ProjectQuotaNotFound(self):
        ex = exception.ProjectQuotaNotFound(project_id="p")
        self.assertEqual("Quota for project p could not be found.", str(ex))

    @attr(kind='small')
    def test_SecurityGroupNotFound(self):
        ex = exception.SecurityGroupNotFound(security_group_id="s")
        self.assertEqual("Security group s not found.", str(ex))

    @attr(kind='small')
    def test_SecurityGroupNotFoundForProject(self):
        ex = exception.SecurityGroupNotFoundForProject(security_group_id="s",
                                                       project_id="p")
        self.assertEqual("Security group s not found "
                "for project p.", str(ex))

    @attr(kind='small')
    def test_SecurityGroupNotFoundForRule(self):
        ex = exception.SecurityGroupNotFoundForRule(rule_id="r")
        self.assertEqual("Security group with rule r not found.", str(ex))

    @attr(kind='small')
    def test_SecurityGroupExistsForInstance(self):
        ex = exception.SecurityGroupExistsForInstance(security_group_id="s",
                                                      instance_id="i")
        self.assertEqual("Security group s is already associated"
                 " with the instance i", str(ex))

    @attr(kind='small')
    def test_SecurityGroupNotExistsForInstance(self):
        ex = exception.SecurityGroupNotExistsForInstance(
                                            security_group_id="s",
                                            instance_id="i")
        self.assertEqual("Security group s is not associated with"
                 " the instance i", str(ex))

    @attr(kind='small')
    def test_MigrationNotFound(self):
        ex = exception.MigrationNotFound(migration_id="m")
        self.assertEqual("Migration m could not be found.", str(ex))

    @attr(kind='small')
    def test_MigrationNotFoundByStatus(self):
        ex = exception.MigrationNotFoundByStatus(instance_id="i", status="s")
        self.assertEqual("Migration not found for instance i "
                "with status s.", str(ex))

    @attr(kind='small')
    def test_ConsolePoolNotFound(self):
        ex = exception.ConsolePoolNotFound(pool_id="p")
        self.assertEqual("Console pool p could not be found.", str(ex))

    @attr(kind='small')
    def test_ConsolePoolNotFoundForHostType(self):
        ex = exception.ConsolePoolNotFoundForHostType(console_type="type",
                                                      compute_host="h",
                                                      host="test")
        self.assertEqual("Console pool of type type "
                "for compute host h "
                "on proxy host test not found.", str(ex))

    @attr(kind='small')
    def test_ConsoleNotFound(self):
        ex = exception.ConsoleNotFound(console_id="p")
        self.assertEqual("Console p could not be found.", str(ex))

    @attr(kind='small')
    def test_ConsoleNotFoundForInstance(self):
        ex = exception.ConsoleNotFoundForInstance(instance_id="i")
        self.assertEqual("Console for instance i could not be found.",
                         str(ex))

    @attr(kind='small')
    def test_ConsoleNotFoundInPoolForInstance(self):
        ex = exception.ConsoleNotFoundInPoolForInstance(instance_id="i",
                                                        pool_id="p")
        self.assertEqual("Console for instance i "
                "in pool p could not be found.", str(ex))

    @attr(kind='small')
    def test_NoInstanceTypesFound(self):
        ex = exception.NoInstanceTypesFound()
        self.assertEqual("Zero instance types found.", str(ex))

    @attr(kind='small')
    def test_InstanceTypeNotFound(self):
        ex = exception.InstanceTypeNotFound(instance_type_id="i")
        self.assertEqual("Instance type i could not be found.", str(ex))

    @attr(kind='small')
    def test_InstanceTypeNotFoundByName(self):
        ex = exception.InstanceTypeNotFoundByName(instance_type_name="i")
        self.assertEqual("Instance type with name i "
                "could not be found.", str(ex))

    @attr(kind='small')
    def test_FlavorNotFound(self):
        ex = exception.FlavorNotFound(flavor_id="f")
        self.assertEqual("Flavor f could not be found.", str(ex))

    @attr(kind='small')
    def test_ZoneNotFound(self):
        ex = exception.ZoneNotFound(zone_id="z")
        self.assertEqual("Zone z could not be found.", str(ex))

    @attr(kind='small')
    def test_SchedulerHostFilterNotFound(self):
        ex = exception.SchedulerHostFilterNotFound(filter_name="f")
        self.assertEqual("Scheduler Host Filter f could not be found.",
                         str(ex))

    @attr(kind='small')
    def test_SchedulerCostFunctionNotFound(self):
        ex = exception.SchedulerCostFunctionNotFound(cost_fn_str="str")
        self.assertEqual("Scheduler cost function str could"
                " not be found.", str(ex))

    @attr(kind='small')
    def test_SchedulerWeightFlagNotFound(self):
        ex = exception.SchedulerWeightFlagNotFound(flag_name="ff")
        self.assertEqual("Scheduler weight flag not found: ff", str(ex))

    @attr(kind='small')
    def test_InstanceMetadataNotFound(self):
        ex = exception.InstanceMetadataNotFound(instance_id="i",
                                                metadata_key="k")
        self.assertEqual("Instance i has no metadata with "
                "key k.", str(ex))

    @attr(kind='small')
    def test_InstanceTypeExtraSpecsNotFound(self):
        ex = exception.InstanceTypeExtraSpecsNotFound(instance_type_id="i",
                                                      extra_specs_key="k")
        self.assertEqual("Instance Type i has no extra specs with "
                "key k.", str(ex))

    @attr(kind='small')
    def test_LDAPObjectNotFound(self):
        ex = exception.LDAPObjectNotFound()
        self.assertEqual("LDAP object could not be found", str(ex))

    @attr(kind='small')
    def test_LDAPUserNotFound(self):
        ex = exception.LDAPUserNotFound(user_id="u")
        self.assertEqual("LDAP user u could not be found.", str(ex))

    @attr(kind='small')
    def test_LDAPGroupNotFound(self):
        ex = exception.LDAPGroupNotFound(group_id="g")
        self.assertEqual("LDAP group g could not be found.", str(ex))

    @attr(kind='small')
    def test_LDAPGroupMembershipNotFound(self):
        ex = exception.LDAPGroupMembershipNotFound(user_id="u", group_id="g")
        self.assertEqual("LDAP user u is not a member of group g.", str(ex))

    @attr(kind='small')
    def test_FileNotFound(self):
        ex = exception.FileNotFound(file_path="path")
        self.assertEqual("File path could not be found.", str(ex))

    @attr(kind='small')
    def test_NoFilesFound(self):
        ex = exception.NoFilesFound()
        self.assertEqual("Zero files could be found.", str(ex))

    @attr(kind='small')
    def test_SwitchNotFoundForNetworkAdapter(self):
        ex = exception.SwitchNotFoundForNetworkAdapter(adapter="eth0")
        self.assertEqual("Virtual switch associated with the "
                "network adapter eth0 not found.", str(ex))

    @attr(kind='small')
    def test_NetworkAdapterNotFound(self):
        ex = exception.NetworkAdapterNotFound(adapter="eth0")
        self.assertEqual("Network adapter eth0 could not be found.", str(ex))

    @attr(kind='small')
    def test_ClassNotFound(self):
        ex = exception.ClassNotFound(class_name="clazz", exception="error")
        self.assertEqual("Class clazz could not be found: error",
                         str(ex))

    @attr(kind='small')
    def test_NotAllowed(self):
        ex = exception.NotAllowed()
        self.assertEqual("Action not allowed.", str(ex))

    @attr(kind='small')
    def test_GlobalRoleNotAllowed(self):
        ex = exception.GlobalRoleNotAllowed(role_id="admin")
        self.assertEqual("Unable to use global role admin", str(ex))

    @attr(kind='small')
    def test_ImageRotationNotAllowed(self):
        ex = exception.ImageRotationNotAllowed()
        self.assertEqual("Rotation is not allowed for snapshots", str(ex))

    @attr(kind='small')
    def test_RotationRequiredForBackup(self):
        ex = exception.RotationRequiredForBackup()
        self.assertEqual("Rotation param is required for backup image_type",
                         str(ex))

    @attr(kind='small')
    def test_Duplicate(self):
        ex = exception.Duplicate()
        self.assertEqual("An unknown exception occurred.", str(ex))

    @attr(kind='small')
    def test_KeyPairExists(self):
        ex = exception.KeyPairExists(key_name="k")
        self.assertEqual("Key pair k already exists.", str(ex))

    @attr(kind='small')
    def test_UserExists(self):
        ex = exception.UserExists(user="u")
        self.assertEqual("User u already exists.", str(ex))

    @attr(kind='small')
    def test_LDAPUserExists(self):
        ex = exception.LDAPUserExists(user="u")
        self.assertEqual("LDAP user u already exists.", str(ex))

    @attr(kind='small')
    def test_LDAPGroupExists(self):
        ex = exception.LDAPGroupExists(group="g")
        self.assertEqual("LDAP group g already exists.", str(ex))

    @attr(kind='small')
    def test_LDAPMembershipExists(self):
        ex = exception.LDAPMembershipExists(uid="u", group_dn="dn")
        self.assertEqual("User u is already a member of "
                "the group dn", str(ex))

    @attr(kind='small')
    def test_ProjectExists(self):
        ex = exception.ProjectExists(project="p")
        self.assertEqual("Project p already exists.", str(ex))

    @attr(kind='small')
    def test_InstanceExists(self):
        ex = exception.InstanceExists(name="n")
        self.assertEqual("Instance n already exists.", str(ex))

    @attr(kind='small')
    def test_InvalidSharedStorage(self):
        ex = exception.InvalidSharedStorage(path="/", reason="TEST")
        self.assertEqual("/ is on shared storage: TEST", str(ex))

    @attr(kind='small')
    def test_MigrationError(self):
        ex = exception.MigrationError(reason="TEST")
        self.assertEqual("Migration error: TEST", str(ex))

    @attr(kind='small')
    def test_MalformedRequestBody(self):
        ex = exception.MalformedRequestBody(reason="TEST")
        self.assertEqual("Malformed message body: TEST", str(ex))

    @attr(kind='small')
    def test_PasteConfigNotFound(self):
        ex = exception.PasteConfigNotFound(path="/")
        self.assertEqual("Could not find paste config at /", str(ex))

    @attr(kind='small')
    def test_PasteAppNotFound(self):
        ex = exception.PasteAppNotFound(name="app", path="/")
        self.assertEqual("Could not load paste app 'app' from /", str(ex))

    @attr(kind='small')
    def test_VSANovaAccessParamNotFound(self):
        ex = exception.VSANovaAccessParamNotFound()
        self.assertEqual("Nova access parameters were not specified.",
                         str(ex))

    @attr(kind='small')
    def test_VirtualStorageArrayNotFound(self):
        ex = exception.VirtualStorageArrayNotFound(id=0)
        self.assertEqual("Virtual Storage Array 0 could not be found.",
                         str(ex))

    @attr(kind='small')
    def test_VirtualStorageArrayNotFoundByName(self):
        ex = exception.VirtualStorageArrayNotFoundByName(name="i")
        self.assertEqual("Virtual Storage Array i could not be found.",
                         str(ex))

    @attr(kind='small')
    def test_CannotResizeToSameSize(self):
        ex = exception.CannotResizeToSameSize()
        self.assertEqual("When resizing, instances must change size!",
                         str(ex))

    @attr(kind='small')
    def test_CannotResizeToSmallerSize(self):
        ex = exception.CannotResizeToSmallerSize()
        self.assertEqual("Resizing to a smaller size is not supported.",
                         str(ex))

    @attr(kind='small')
    def test_ImageTooLarge(self):
        ex = exception.ImageTooLarge()
        self.assertEqual("Image is larger than instance type allows",
                         str(ex))

    @attr(kind='small')
    def test_ZoneRequestError(self):
        ex = exception.ZoneRequestError()
        self.assertEqual("1 or more Zones could not complete the request",
                         str(ex))
        ex = exception.ZoneRequestError("test")
        self.assertEqual("test", str(ex))


class ProcessExecutionErrorTestCase(test.TestCase):

    @attr(kind='small')
    def test_init(self):
        """ Ensure message is default"""

        description = _('Unexpected error while running command.')
        cmd = None
        exit_code = '-'
        stdout = None
        stderr = None
        message = _('%(description)s\nCommand: %(cmd)s\n'
                    'Exit code: %(exit_code)s\nStdout: %(stdout)r\n'
                    'Stderr: %(stderr)r') % locals()

        err = exception.ProcessExecutionError()
        msg = IOError.__str__(err)
        self.assertEqual(message, msg)

    @attr(kind='small')
    def test_init_parameter(self):
        """ Ensure message is orignal"""

        description = _('Test error while running command.')
        cmd = 'fake'
        exit_code = '99'
        stdout = None
        stderr = None
        message = _('%(description)s\nCommand: %(cmd)s\n'
                    'Exit code: %(exit_code)s\nStdout: %(stdout)r\n'
                    'Stderr: %(stderr)r') % locals()

        err = exception.ProcessExecutionError(exit_code=exit_code,
                                              cmd=cmd,
                                              description=description)
        msg = IOError.__str__(err)
        self.assertEqual(message, msg)


class DBErrorTestCase(test.TestCase):
    @attr(kind='small')
    def test_init(self):
        err = exception.DBError()
        self.assertEqual(None, err.inner_exception)

        err2 = exception.DBError(inner_exception=err)
        self.assertEqual(err, err2.inner_exception)


class ExceptionTestCase(test.TestCase):
    @attr(kind='small')
    def test_wrap_db_error(self):

        def fake():
            return True

        wrap = exception.wrap_db_error(fake)()
        self.assert_(wrap)

    @attr(kind='small')
    def test_wrap_db_error_exception(self):

        from nova.virt import driver
        cls = driver.ComputeDriver()

        try:
            err_flag = False
            wrap = exception.wrap_db_error(cls.init_host)('fake')
        except exception.DBError:
            err_flag = True
        finally:
            self.assert_(err_flag)
