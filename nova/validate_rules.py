# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2011 NTT.
# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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

import webob

from nova import context
from nova import exception
from nova import flags
from nova import validation
from nova import db
from nova import image
from nova import utils
from nova.context import RequestContext
from nova.compute import power_state
import sys

FLAGS = flags


class BaseValidator(validation.Validator):
    """
    BaseValidator.

    Define a initialization to use database.
    All rule that use database, should be inherit this.
    """
    def __init__(self, target, *args, **kwargs):
        """
        Initialize object.
        ::target:: validate target method.
        ::args:: method parameters.
        ::kwargs:: keyword args, it contains webob.Request object as req.
        """
        self.target = target
        self.args = args
        self.kwargs = kwargs
        # context is special object
        self.context = None
        # for api validation
        if 'req' in kwargs and isinstance(kwargs['req'], webob.Request):
            self.request = kwargs['req']
            self.context = kwargs['req'].environ['nova.context']
        for arg in args:
            if isinstance(arg, RequestContext):
                self.context = arg
        if self.context is None:
            self.context = context.get_admin_context(False)


class ProjectRequire(BaseValidator):
    """
    ProjextRequire.

    Validate the project is exists.
    Require the 'project_id' parameter.
    This is unusable when using keystone, because by using
    auth_driver for check project existance.
    """
    def validate_project_id(self, project_id):
        driver = utils.import_class(FLAGS.auth_driver)
        if driver is not None:
            drv = driver()
            project = drv.get_project(project_id)
            if project is None:
                raise exception.ProjectNotFound(project_id=project_id)


class InstanceRequire(BaseValidator):
    """
    InstanceRequire.

    Validate the instance is exists.
    Require the 'instance_id' parameter.
    """
    def validate_instance_id(self, instance_id):
        print "hogehoge"
        if utils.is_uuid_like(instance_id):
            db.instance_get_by_uuid(self.context, instance_id)
        else:
            db.instance_get(self.context, instance_id)


class InstanceNameValid(BaseValidator):
    """
    InstanceNameValid.

    Validate the name is valid format.
    Require the 'instance_name' parameter.
    """
    def validate_instance_name(self, instance_name):
        if not instance_name:
            raise exception.InvalidParameterValue(
                              err="name parameter required.")
        if len(instance_name) > 255:
            raise exception.InvalidParameterValue(
                              err="name parameter over 255 length.")


class InstanceRunningRequire(BaseValidator):
    """
    InstanceRunningRequire.

    Validate the instance is running status.
    Require the 'instance_id' parameter.
    """
    def validate_instance_id(self, instance_id):
        instance = db.instance_get(self.context, instance_id)
        if instance["power_state"] != power_state.RUNNING:
            raise exception.InstanceNotRunning(instance_id=instance_id)


class ImageNameValid(BaseValidator):
    """
    ImageNameValid.

    Validate the image name is valid and unique.
    Require the 'image_name' parameter.
    """
    def validate_image_name(self, image_name):
        print image_name
        if not image_name:
            raise exception.InvalidParameterValue(
                              err="Image name should be specified.")
        if len(image_name) > 255:
            print len(image_name)
            raise exception.InvalidParameterValue(
                              err="Image name should less than 255.")

        service = image.get_default_image_service()
        try:
            service.show_by_name(self.context, image_name)
            raise exception.Duplicate()
        except exception.ImageNotFound:
            pass


class NetworkRequire(BaseValidator):
    """
    NetworkRequire.

    Validate the network is exists.
    Require the 'network_id' parameter.
    """
    def validate_network_id(self, network_id):
        db.network_get(self.context, network_id)


class NetworkUuidsExists(BaseValidator):
    """
    NetworkUuidsExists.

    Validate the all networks uuid are exists.
    Require the 'uuids' parameter.
    """
    def validate_uuids(self, uuids):
        db.network_get_all_by_uuids(self.context, uuids)


class NetworkFixedIpsValid(BaseValidator):
    """
    NetworkFixedIpsExists.

    Validate the all networks ips are valid format.
    Require the 'fixed_ips' parameter.
    """
    def validate_fixed_ips(self, fixed_ips):
        for ip in fixed_ips:
            if not utils.is_valid_ipv4(ip):
                raise exception.FixedIpInvalid(address=ip)
            else:
                db.fixed_ip_get_by_address(self.context, ip)


class ConsoleRequire(BaseValidator):
    """
    ConsoleRequire.

    Validate the console is exists.
    Require the 'console_id' and 'instance_id' parameter.
    """
    def validate_console_id(self, console_id):
        instance_id = self.params["instance_id"]
        db.console_get(self.context, console_id, instance_id)


class FlavorRequire(BaseValidator):
    """
    FlavorRequire.

    Validate the flavor is exists.
    Require the 'flavor_id' parameter.
    """
    def validate_flavor_id(self, flavor_id):
        db.api.instance_type_get_by_flavor_id(self.context, flavor_id)


class ImageRequire(BaseValidator):
    """
    ImageRequire.

    Validate the image is exists.
    Require the 'image_id' parameter.
    """
    def validate_image_id(self, image_id):
        try:
            num = int(image_id)
            if num < 1:
                raise exception.InvalidParameterValue("Specified image id is not positive value.")
            elif num > sys.maxint:
                raise exception.InvalidParameterValue("Specified image id is too large.")
        except TypeError:
            raise exception.InvalidParameterValue("Specified image id is not digit.")
        service = image.get_default_image_service()
        result = service.show(self.context, image_id)
        if result is None:
            raise exception.ImageNotFound(image_id=image_id)


class ImageMetadataRequire(BaseValidator):
    """
    ImageMetadataRequire.

    Validate the image_metadata exists.
    Require the 'image_id' and 'metadata_id' parameter.
    """
    def validate_metadata_id(self, metadata_id):
        service = image.get_default_image_service()
        img = service.show(self.context, self.params["image_id"])
        try:
            meta = img["properties"]
            if metadata_id not in meta:
                raise exception.NotFound(
                            "specified metadata %s not found in image %s"
                                    % metadata_id, self.params["image_id"])
        except (TypeError, KeyError):
            raise exception.NotFound("%s not have any metadata"
                                     % self.params["image_id"])


class InstanceMetadataRequire(BaseValidator):
    """
    InstanceMetadataRequire.

    Validate the instance_metadata is exists.
    Require the 'instance_id' and 'metadata_id' parameters.
    """
    def validate_metadata_id(self, metadata_id):
        instance_id = self.params["instance_id"]
        meta = db.instance_metadata_get(self.context, instance_id)
        if metadata_id not in meta:
            raise exception.InstanceMetadataNotFound(
                            instance_id=instance_id, metadata_key=metadata_id)


class UserRequire(BaseValidator):
    """
    UserRequire.

    Validate the user is exists.
    Require the 'user_id' parameter.
    This is unusable when using keystone, because by using
    auth_driver for check user existance.
    """
    def validate_user_id(self, user_id):
        driver = utils.import_class(FLAGS.auth_driver)
        if driver is not None:
            drv = driver()
            user = drv.get_user(user_id)
            if user is None:
                raise exception.UserNotFound(user_id=user_id)


class ZoneRequire(BaseValidator):
    """
    ZoneRequire.

    Validate the zone is exists.
    Require the 'zone_id' parameter.
    """
    def validate_zone_id(self, zone_id):
        db.zone_get(self.context, zone_id)


class KeypairRequire(BaseValidator):
    """
    keypairRequire.

    Validate the keypair is exists.
    Require the 'keypair_name' parameter.
    """
    def validate_keypair_name(self, keypair_name):
        db.key_pair_get(self.context, self.context.user_id, keypair_name)


class KeypairNameValid(BaseValidator):
    """
    keypairNameRequire.

    Validate the keypair is not duplicate.
    Require the 'keypair_name' parameter.
    """
    def validate_keypair_name(self, keypair_name):
        try:
            db.key_pair_get(self.context, self.context.user_id, keypair_name)
            raise exception.KeyPairExists(key_name=keypair_name)
        except exception.KeypairNotFound:
            pass
