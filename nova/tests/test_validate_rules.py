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
from nova import test
from nova import context
from nova import exception
from nova import db
from nova import flags
from nova import validation
from nova import validate_rules as rules
from nova.auth import manager
from nova.compute import power_state

FLAGS = flags


class InstanceCreationResolver(validation.Resolver):

    def resolve_parameter(self, params):
        body = params['body']
        params['image_id'] = body['server']['imageId']
        params['flavor_id'] = body['server']['flavorId']
        return params


class ValidateRulesTestCase(test.TestCase):

    def setUp(self):
        super(ValidateRulesTestCase, self).setUp()
        self.context = context.get_admin_context()

    """Test Case for the validate rules."""
    def test_instance_require(self):
        # setup validation
        class TargetClass1(object):
            @validation.method(rules.InstanceRequire)
            def meth(self, instance_id):
                return "meth"

        validation.apply()
        # setup data
        values = {'id': 1,
                  'image_ref': 'ami-00000001',
                  'project_id': 'fake',
                 }
        db.instance_create(self.context, values)
        # do test
        target = TargetClass1()
        actual = target.meth(1)

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.InstanceNotFound, target.meth, 999)

    def test_instance_require_with_context(self):
        # setup validation
        class TargetClass1(object):
            @validation.method(rules.InstanceRequire)
            def meth(self, context, instance_id):
                return "meth"

        validation.apply()
        # setup data
        values = {'id': 1,
                  'image_ref': 'ami-00000001',
                  'project_id': 'fake',
                 }
        db.instance_create(self.context, values)
        # do test
        target = TargetClass1()
        actual = target.meth(self.context, 1)

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.InstanceNotFound,
                          target.meth, self.context, 999)

    def test_instance_require_alias(self):
        # setup validation
        class TargetClass1(object):
            @validation.method(rules.InstanceRequire,
                               alias={'id': 'instance_id'})
            def meth(self, context, id):
                return "meth"

        validation.apply()
        # setup data
        values = {'id': 1,
                  'image_ref': 'ami-00000001',
                  'project_id': 'fake',
                 }
        db.instance_create(self.context, values)
        # do test
        target = TargetClass1()
        actual = target.meth(self.context, 1)

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.InstanceNotFound,
                          target.meth, self.context, 999)

    def test_instance_network_require(self):
        # setup validation
        class TargetClass1(object):
            @validation.method(rules.InstanceRequire, rules.NetworkRequire)
            def meth(self, context, instance_id, network_id):
                return "meth"

        validation.apply()
        # setup data
        values = {'id': 1,
                  'image_ref': 'ami-00000001',
                  'project_id': 'fake',
                 }
        db.instance_create(self.context, values)

        values = {'id': 100}
        db.network_create_safe(self.context, values)

        # do test
        target = TargetClass1()
        actual = target.meth(self.context, 1, 100)

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.InstanceNotFound,
                          target.meth, self.context, 999, 100)
        self.assertRaises(exception.NetworkNotFound,
                          target.meth, self.context, 1, 999)

    def test_instance_metadata_require(self):
        # setup validation
        class TargetClass1(object):
            @validation.method(rules.InstanceMetadataRequire)
            def meth(self, context, instance_id, metadata_id):
                return "meth"

        validation.apply()
        # setup data
        values = {'id': 1,
                  'image_ref': 'ami-00000001',
                  'project_id': 'fake',
                  'metadata': {'key1': 'value1'}
                 }
        db.instance_create(self.context, values)

        # do test
        target = TargetClass1()
        actual = target.meth(self.context, 1, 'key1')

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.InstanceNotFound,
                          target.meth, self.context, 999, 'key1')
        self.assertRaises(exception.InstanceMetadataNotFound,
                          target.meth, self.context, 1, 'NoKey')

    def test_instance_create(self):
        # setup validation.
        class TargetClass1(object):
            @validation.method(rules.FlavorRequire,
                        rules.ImageRequire, resolver=InstanceCreationResolver)
            def meth(self, body):
                return "meth"
        validation.apply()

        body = dict(server=dict(
            name='server_test', imageId=1, flavorId=1,
            metadata={'hello': 'world', 'open': 'stack'},
            personality={}))
        # fake image service not have image that id is 999.
        invalid_image = dict(server=dict(
            name='server_test', imageId=999, flavorId=1,
            metadata={'hello': 'world', 'open': 'stack'},
            personality={}))

        invalid_flavor = dict(server=dict(
            name='server_test', imageId=1, flavorId=999,
            metadata={'hello': 'world', 'open': 'stack'},
            personality={}))

        # do test
        target = TargetClass1()
        actual = target.meth(body)

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.ImageNotFound, target.meth, invalid_image)
        self.assertRaises(exception.FlavorNotFound,
                          target.meth, invalid_flavor)

    def test_instance_metadata_require_with_alias(self):
        # setup validation
        class TargetClass1(object):
            @validation.method(rules.InstanceMetadataRequire,
                    alias={'server_id': 'instance_id', 'id': 'metadata_id'})
            def meth(self, context, server_id, id):
                return "meth"

        validation.apply()
        # setup data
        values = {'id': 1,
                  'image_ref': 'ami-00000001',
                  'project_id': 'fake',
                  'metadata': {'key1': 'value1'}
                 }
        db.instance_create(self.context, values)

        # do test
        target = TargetClass1()
        actual = target.meth(self.context, 1, 'key1')

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.InstanceNotFound,
                          target.meth, self.context, 999, 'key1')
        self.assertRaises(exception.InstanceMetadataNotFound,
                          target.meth, self.context, 1, 'NoKey')

    def test_instance_name_valid(self):
        # setup validation
        class TargetClass1(object):
            @validation.method(rules.InstanceNameValid)
            def meth(self, instance_name):
                return "meth"

        validation.apply()
        # setup data

        # do test
        target = TargetClass1()
        actual = target.meth("valid_name")

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.InvalidParameterValue,
                          target.meth, '')
        self.assertRaises(exception.InvalidParameterValue,
                          target.meth, '1' * 256)

    def test_instance_running_require(self):
        # setup validation
        class TargetClass1(object):
            @validation.method(rules.InstanceRunningRequire)
            def meth(self, instance_id):
                return "meth"

        validation.apply()
        # setup data
        values = {'id': 1,
                  'image_ref': 'ami-00000001',
                  'project_id': 'fake',
                  'power_state': power_state.RUNNING
                 }
        db.instance_create(self.context, values)

        values = {'id': 2,
                  'image_ref': 'ami-00000002',
                  'project_id': 'fake',
                  'power_state': power_state.CRASHED
                 }

        db.instance_create(self.context, values)
        # do test
        target = TargetClass1()
        actual = target.meth(1)

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.InstanceNotRunning, target.meth, 2)

    def test_project_require(self):
        FLAGS.auth_driver = 'nova.auth.dbdriver.DbDriver'
        # setup validation

        class TargetClass(object):
            @validation.method(rules.ProjectRequire)
            def meth(self, project_id):
                return "meth"

        validation.apply()
        # setup data
        values = {'id': 'fake'}
        db.project_create(self.context, values)
        # do test
        target = TargetClass()
        actual = target.meth('fake')

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.ProjectNotFound, target.meth, 'not found')

    def test_user_require(self):
        FLAGS.auth_driver = 'nova.auth.dbdriver.DbDriver'
        # setup validation

        class TargetClass(object):
            @validation.method(rules.UserRequire)
            def meth(self, user_id):
                return "meth"

        validation.apply()
        # setup data
        values = {'id': 'fake'}
        db.user_create(self.context, values)
        # do test
        target = TargetClass()
        actual = target.meth('fake')

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.UserNotFound, target.meth, 'not found')

    def test_network_require(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.NetworkRequire)
            def meth(self, network_id):
                return "meth"

        validation.apply()
        # setup data
        values = {'id': 100}
        db.network_create_safe(self.context, values)
        # do test
        target = TargetClass()
        actual = target.meth(100)

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.NetworkNotFound, target.meth, 999)

    def test_network_uuids_exist(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.NetworkUuidsExists)
            def meth(self, context, uuids):
                return "meth"

        validation.apply()
        # setup data
        values = {'id': 100, 'uuid': 'uuid1', 'host': 'host1'}
        db.network_create_safe(self.context, values)
        values = {'id': 101, 'uuid': 'uuid2', 'host': 'host1'}
        db.network_create_safe(self.context, values)

        # do test
        target = TargetClass()
        actual = target.meth(self.context, ['uuid1', 'uuid2'])

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.NetworkNotFound,
                          target.meth, self.context, ['uuid1', 'not found'])

    def test_network_fixed_ips_exist(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.NetworkFixedIpsValid)
            def meth(self, context, fixed_ips):
                return "meth"

        validation.apply()
        # setup data
        values = {'id': 100, 'uuid': 'uuid1', 'host': 'host1'}
        db.network_create_safe(self.context, values)
        values = {'id': 101, 'uuid': 'uuid2', 'host': 'host1'}
        db.network_create_safe(self.context, values)
        values = {'id': 100, 'address': '10.1.1.1'}
        db.fixed_ip_create(self.context, values)
        values = {'id': 101, 'address': '10.1.1.2'}
        db.fixed_ip_create(self.context, values)

        # do test
        target = TargetClass()
        actual = target.meth(self.context, ['10.1.1.1', '10.1.1.2'])

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.FixedIpInvalid,
                          target.meth, self.context, ['10.1.1.1', 'invalid'])

    def test_console_require(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.ConsoleRequire)
            def meth(self, instance_id, console_id):
                return "meth"

        validation.apply()
        # setup data
        values = {'id': 100}
        db.instance_create(self.context, values)
        values = {'id': 1, 'instance_id': 100}
        db.console_create(self.context, values)

        # do test
        target = TargetClass()
        actual = target.meth(100, 1)

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.ConsoleNotFoundForInstance,
                          target.meth, 101, 1)

    def test_flavor_require(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.FlavorRequire)
            def meth(self, flavor_id):
                return "meth"

        validation.apply()

        # do test
        target = TargetClass()
        actual = target.meth(1)

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.FlavorNotFound, target.meth, 999)

    def test_image_require(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.ImageRequire)
            def meth(self, image_id):
                return "meth"

        validation.apply()
        # fake image stored images 1,2,3,4,5
        # do test
        target = TargetClass()
        actual = target.meth(1)

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.ImageNotFound, target.meth, 999)

    def test_image_name_valid(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.ImageNameValid)
            def meth(self, image_name):
                return "meth"

        validation.apply()
        # fake image stored images 1,2,3,4,5
        # do test
        target = TargetClass()
        actual = target.meth("not duplicated")

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.Duplicate, target.meth, "fakeimage123456")

    def test_image_metadata_require(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.ImageMetadataRequire)
            def meth(self, image_id, metadata_id):
                return "meth"

        validation.apply()
        # fake image stored images 1,2,3,4,5
        # do test
        target = TargetClass()
        actual = target.meth(1, 'kernel_id')

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.NotFound, target.meth, 1, 'not found')

    def test_zone_require(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.ZoneRequire)
            def meth(self, zone_id):
                return "meth"

        validation.apply()
        # setup data
        values = {'id': 1, 'name': 'nova'}
        db.zone_create(self.context, values)
        # do test
        target = TargetClass()
        actual = target.meth(1)

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.ZoneNotFound, target.meth, 999)

    def test_keypair_require(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.KeypairRequire)
            def meth(self, keypair_name):
                return "meth"

        validation.apply()
        # setup data
        values = {'id': 1, 'name': 'key1', 'user_id': self.context.user_id}
        db.key_pair_create(self.context, values)
        # do test
        target = TargetClass()
        actual = target.meth('key1')

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.KeypairNotFound, target.meth, 'key2')

    def test_keypair_name_valid(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.KeypairNameValid)
            def meth(self, keypair_name):
                return "meth"

        validation.apply()
        # setup data
        values = {'id': 1, 'name': 'key1', 'user_id': self.context.user_id}
        db.key_pair_create(self.context, values)
        # do test
        target = TargetClass()
        actual = target.meth('newkey')

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.KeyPairExists, target.meth, 'key1')

    def test_floating_ip_require(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.FloatingIpRequire)
            def meth(self, floating_ip_id):
                return "meth"

        validation.apply()
        # setup data
        values = {'id': 1, 'address': '192.168.0.1'}
        db.floating_ip_create(self.context, values)
        # do test
        target = TargetClass()
        actual = target.meth(1)

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(exception.FloatingIpNotFound, target.meth, 999)
