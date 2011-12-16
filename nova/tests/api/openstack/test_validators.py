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

import nova.db
import webob

from nova import context, db
from nova import flags
from nova import test
from nova import validate_rules as rules
from nova import validation
from nova import exception
from nova.api.openstack.validators import APIValidateMapper


class FakeController(object):

    def fake(self, id):
        return id


class FakeController2(object):

    def fake(self, id, name):
        return id


@test.skip_test('side effect to validation rules.')
class APIValidateMapperTest(test.TestCase):

    def setUp(self):
        super(APIValidateMapperTest, self).setUp()
        self.flags(verbose=True, allow_admin_api=True)
        self.mapper = APIValidateMapper()
        self.mapper.base = "nova.tests.api.openstack.test_validators."
        self.context = context.get_admin_context()

    def test_map(self):
        # setup
        def fake_get_config():
            return [{"cls": "FakeController",
                     "method": "fake",
                    "validators": [rules.FlavorRequire],
                    "alias": {"id": "flavor_id"}}
                    ]

        self.stubs.Set(self.mapper, "_get_config", fake_get_config)
        self.mapper.map()

        controller = FakeController()
        self.assertEqual(999, controller.fake(999))
        validation.apply()
        self.assertRaises(webob.exc.HTTPNotFound, controller.fake, 999)

    def test_map_multi(self):
        # setup
        def fake_get_config():
            return [
                    {"cls": "FakeController",
                     "method": "fake",
                     "validators": [rules.FlavorRequire],
                     "alias": {"id": "flavor_id"}},
                    {"cls": "FakeController2",
                     "method": "fake",
                     "validators": [rules.FlavorRequire, rules.NetworkRequire],
                     "alias": {"id": "flavor_id", "name": "network_id"}}
                    ]

        self.stubs.Set(self.mapper, "_get_config", fake_get_config)
        self.mapper.map()
        db.network_create_safe(self.context, {"id": 100})

        controller = FakeController2()

        self.assertEqual(1, controller.fake(1, 101))
        validation.apply()
        self.assertRaises(webob.exc.HTTPNotFound, controller.fake, 999, 100)
        self.assertRaises(webob.exc.HTTPNotFound, controller.fake, 1, 101)
