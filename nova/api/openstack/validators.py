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
from nova import exception
from nova import log as logging
from nova import wsgi
from nova import validate_rules as rules
from nova import validation
from nova import utils

LOG = logging.getLogger('nova.api.openstack')


class InstanceCreationResolver(validation.Resolver):
    """
    InstanceCreationResolver.
    """
    def resolve_parameter(self, params):
        try:
            body = params['body']
            params['instance_name'] = body['server']['name']
            params['image_id'] = body['server'].get('imageRef')
            params['flavor_id'] = body['server'].get('flavorRef')
            params['zone_name'] = body['server'].get('availability_zone')
            params['metadata'] = body['server'].get('metadata')
        except KeyError:
            pass
        return params


class InstanceUpdateResolver(validation.Resolver):
    """
    InstanceUpdateResolver.
    """
    def resolve_parameter(self, params):
        try:
            body = params['body']
            params['instance_name'] = body['server']['name']
        except KeyError:
            pass
        return params


class CreateImageResolver(validation.Resolver):
    """
    CreateImageResolver.
    params before: input_dict, req, instance_id
    params after: input_dict, req, instance_id, image_name
    """
    def resolve_parameter(self, params):
        try:
            input_dict = params['input_dict']
            entity = input_dict.get("createImage", {})
            params['image_name'] = entity.get('name')
            params['metadata'] = entity.get('metadata')
        except KeyError:
            pass
        return params


class KeypairCreationResolver(validation.Resolver):
    """
    KeypairCreationResolver.
    """
    def resolve_parameter(self, params):
        try:
            body = params['body']
            params['keypair_name'] = body['keypair']['name']
            params['public_key'] = body['keypair'].get('public_key')
        except KeyError:
            pass
        return params


MAPPING = []


def handle_web_exception(self, e):
    if isinstance(e, exception.NotFound):
        raise webob.exc.HTTPNotFound(explanation=str(e))
    elif isinstance(e, exception.Invalid):
        # TODO add some except pattern.
        if isinstance(e, exception.InstanceRebootFailure):
            raise webob.exc.HTTPForbidden(explanation=str(e))
        if isinstance(e, exception.InstanceSnapshotFailure):
            raise webob.exc.HTTPForbidden(explanation=str(e))
        raise webob.exc.HTTPBadRequest(explanation=str(e))
    elif isinstance(e, exception.Duplicate):
        raise webob.exc.HTTPBadRequest(explanation=str(e))
    elif isinstance(e, exception.InstanceBusy):
        raise webob.exc.HTTPConflict(explanation=str(e))


class ValidatorMiddleware(wsgi.Middleware):

    @classmethod
    def factory(cls, global_config, **local_config):
        """Paste factory."""
        def _factory(app):
            return cls(app, **local_config)
        return _factory

    def __init__(self, application):
        mapper = APIValidateMapper()
        mapper.map()
        validation.apply()
        super(ValidatorMiddleware, self).__init__(application)


class APIValidateMapper(object):

    base = "nova.api.openstack."

    def _get_config(self):
        return MAPPING

    def map(self):
        configs = self._get_config()
        for config in configs:
            cls = utils.import_class(self.base + config["cls"])
            func = getattr(cls, config["method"])
            for v in config["validators"]:
                v.handle_exception = handle_web_exception
            # weave
            func = validation.method(*config["validators"],
                                alias=config.get("alias", None),
                                resolver=config.get("resolver", None))(func)
            setattr(cls, config["method"], func)
