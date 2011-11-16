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

from nova import exception
from nova import flags
from nova import log as logging
from nova import wsgi
from nova import validate_rules as rules
from nova import validation
from nova import utils

MAPPING = [
{"cls": "flavors.Controller",
 "method": "show",
 "validators": [rules.FlavorRequire],
 "alias": {"id": "flavor_id"}}
]


class ValidatorMiddleware(wsgi.Middleware):

    @classmethod
    def factory(cls, global_config, **local_config):
        """Paste factory."""
        def _factory(app):
            return cls(app, **local_config)
        return _factory

    def __init__(self, applicateion):
        mapper = APIValidateMapper()
        mapper.map()
        validation.apply()


class APIValidateMapper(object):

    base = "nova.api.openstack."

    def _get_config(self):
        return MAPPING

    def map(self):
        configs = self._get_config(self)
        for config in configs:
            cls = utils.import_class(self.base + config["cls"])
            func = getattr(cls, config["method"])
            # weave
            func = validation.method(*config["validators"],
                                alias=config.get("alias", None),
                                resolver=config.get("resolver", None))(func)
            setattr(cls, config["method"], func)
