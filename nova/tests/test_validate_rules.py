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
from nova.compute import power_state, vm_states, task_states
import sys
import webob


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
                  'metadata': {'key1': 'value1'},
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
                        rules.ImageRequireAPI,
                        resolver=InstanceCreationResolver)
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
        self.assertRaises(webob.exc.HTTPNotFound, target.meth, invalid_image)
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
                  'metadata': {'key1': 'value1'},
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
                  'power_state': power_state.RUNNING,
                 }
        db.instance_create(self.context, values)

        values = {'id': 2,
                  'image_ref': 'ami-00000002',
                  'project_id': 'fake',
                  'power_state': power_state.CRASHED,
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
            @validation.method(rules.ImageRequireAPI)
            def meth(self, image_id):
                return "meth"

        validation.apply()
        # fake image stored images 1,2,3,4,5
        # do test
        target = TargetClass()
        actual = target.meth(1)

        # assertion
        self.assertEqual("meth", actual)
        self.assertRaises(webob.exc.HTTPNotFound, target.meth, 999)

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
        self.assertRaises(exception.Invalid, target.meth, "1".zfill(256))

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
        self.assertRaises(webob.exc.HTTPConflict, target.meth, 'key1')

    def test_keypair_name_valid_blank(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.KeypairNameValid)
            def meth(self, keypair_name):
                return "meth"
        validation.apply()
        target = TargetClass()
        keypair_name = ""
        # perform target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, keypair_name)

    def test_keypair_name_valid_none(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.KeypairNameValid)
            def meth(self, keypair_name):
                return "meth"
        validation.apply()
        target = TargetClass()
        keypair_name = None
        # perform target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, keypair_name)

    def test_keypair_name_valid_invalid_length(self):
        # setup validation
        expected = "expectedvalue"

        class TargetClass(object):
            @validation.method(rules.KeypairNameValid)
            def meth(self, keypair_name):
                return expected
        validation.apply()
        target = TargetClass()
        keypair_name1 = "".join(["a" for i in range(0, 255)])
        keypair_name2 = "".join(["a" for i in range(0, 256)])
        actual = target.meth(keypair_name1)
        # perform target and assert result
        self.assertEqual(actual, expected)
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, keypair_name2)

    def test_keypair_name_valid_exists(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.KeypairNameValid)
            def meth(self, keypair_name):
                return "not return"
        validation.apply()
        target = TargetClass()
        keypair_name = "validkeyname"
        # setup data
        values = {'id': 1, 'name': keypair_name,
                'user_id': self.context.user_id}
        db.key_pair_create(self.context, values)
        # perform target and assert result
        self.assertRaises(webob.exc.HTTPConflict, target.meth, keypair_name)

    def test_keypair_name_db_error(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.KeypairNameValid)
            def meth(self, keypair_name):
                raise exception.DBError("Failed to query")
                return "not return"
        validation.apply()
        target = TargetClass()
        keypair_name = "validkeyname"
        # perform target and assert result
        self.assertRaises(exception.DBError, target.meth, keypair_name)

    def test_keypair_exists_success(self):
        # setup validation
        expected = "success result"

        class TargetClass(object):
            @validation.method(rules.KeypairExists)
            def meth(self, keypair_name):
                return expected
        validation.apply()
        target = TargetClass()
        keypair_name = "validkeyname"
        # setup data
        values = {'id': 1, 'name': keypair_name,
                'user_id': self.context.user_id}
        db.key_pair_create(self.context, values)
        instance = {'id': 1, 'key_name': "other_key"}
        db.instance_create(self.context, instance)
        # perform target
        actual = target.meth(keypair_name)
        # assert result
        self.assertEqual(actual, expected)

    def test_keypair_exists_keypair_used(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.KeypairExists)
            def meth(self, keypair_name):
                return "not return"
        validation.apply()
        target = TargetClass()
        keypair_name = "validkeyname"
        # setup data
        values = {'id': 1, 'name': keypair_name,
                'user_id': self.context.user_id}
        db.key_pair_create(self.context, values)
        instance = {'id': 1, 'key_name': keypair_name}
        db.instance_create(self.context, instance)
        # perform target and assert result
        self.assertRaises(webob.exc.HTTPConflict, target.meth, keypair_name)

    def test_keypair_exists_keypair_not_found(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.KeypairExists)
            def meth(self, keypair_name):
                return "not return"
        validation.apply()
        target = TargetClass()
        keypair_name = "validkeyname"
        # perform target and assert result
        self.assertRaises(webob.exc.HTTPNotFound, target.meth, keypair_name)

    def test_keypair_exists_db_error(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.KeypairExists)
            def meth(self, keypair_name):
                raise exception.DBError("Failed to query")
                return "not return"
        validation.apply()
        target = TargetClass()
        keypair_name = "validkeyname"
        values = {'id': 1, 'name': keypair_name,
                'user_id': self.context.user_id}
        db.key_pair_create(self.context, values)
        # perform target and assert result
        self.assertRaises(exception.DBError, target.meth, keypair_name)

    def test_keypair_is_rsa_public_key_invalid(self):
        # setup validation
        class TargetClass(object):
            @validation.method(rules.KeypairIsRsa)
            def meth(self, public_key):
                return "meth"

        validation.apply()
        valid_key1 = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDcsnT+yXD1Y2h7IU47TyBUJZf8HmHyzpwyuzGxu5512XM7xhHM5aWjQVEccsxvg242MDUbwGWGa69j68cW9XR8fpDWzZLaGEmIbpdVbGUVajwDBgwMSANPQG2H0jQOMUSptiW4xMq5lzWLtm3cCvBmuaTMhRqRSuizAvCdPuuUNdvcszOtYIa+I6uFzmlqJVH63egEeBe+Z5TuY+HdKyyi9zp36sPYM47xKf0LKD+mc07xgDzjEVI0fiTbrEWhsUUDEHKNcVvGP7w2r8CZqEQYWqpTqbE7XJsXCM+iq52Y2slqvhO+Dv8xltFQqu3crqzzxsR/PwGiOAeH45/sWNpt openstack@ubuntu"
        valid_key2 = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDcsnT+yXD1Y2h7IU47TyBUJZf8HmHyzpwyuzGxu5512XM7xhHM5aWjQVEccsxvg242MDUbwGWGa69j68cW9XR8fpDWzZLaGEmIbpdVbGUVajwDBgwMSANPQG2H0jQOMUSptiW4xMq5lzWLtm3cCvBmuaTMhRqRSuizAvCdPuuUNdvcszOtYIa+I6uFzmlqJVH63egEeBe+Z5TuY+HdKyyi9zp36sPYM47xKf0LKD+mc07xgDzjEVI0fiTbrEWhsUUDEHKNcVvGP7w2r8CZqEQYWqpTqbE7XJsXCM+iq52Y2slqvhO+Dv8xltFQqu3crqzzxsR/PwGiOAeH45/sWNpt"
        invalid_key = "AAAAB3NzaC1yc2EAAAADAQABAAABAQDcsnT+yXD1Y2h7IU47TyBUJZf8HmHyzpwyuzGxu5512XM7xhHM5aWjQVEccsxvg242MDUbwGWGa69j68cW9XR8fpDWzZLaGEmIbpdVbGUVajwDBgwMSANPQG2H0jQOMUSptiW4xMq5lzWLtm3cCvBmuaTMhRqRSuizAvCdPuuUNdvcszOtYIa+I6uFzmlqJVH63egEeBe+Z5TuY+HdKyyi9zp36sPYM47xKf0LKD+mc07xgDzjEVI0fiTbrEWhsUUDEHKNcVvGP7w2r8CZqEQYWqpTqbE7XJsXCM+iq52Y2slqvhO+Dv8xltFQqu3crqzzxsR/PwGiOAeH45/sWNpt openstack@ubuntu"

        # do test
        target = TargetClass()
        actual = target.meth(valid_key1)
        self.assertEqual("meth", actual)
        actual = target.meth(valid_key2)
        self.assertEqual("meth", actual)

        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, invalid_key)
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, 'key1')

    def test_instance_require_api_by_uuid_instance_is_exists(self):
        # prepare test
        expected = "success reuslt"

        class TargetClass(object):
            @validation.method(rules.InstanceRequireAPI)
            def meth(self, instance_id):
                return expected
        validation.apply()
        target = TargetClass()
        uuid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        instance_id = 10
        values = {'id': instance_id, 'uuid': uuid}
        db.instance_create(self.context, values)
        # perfom target
        actual = target.meth(uuid)
        #assert result
        self.assertEqual(actual, expected)

    def test_instance_require_api_by_uuid_instance_not_found(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.InstanceRequireAPI)
            def meth(self, instance_id):
                raise Exception("not return")
                return "not return"
        validation.apply()
        target = TargetClass()
        uuid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPNotFound, target.meth, uuid)

    def test_instance_require_api_by_instance_id_instance_is_exists(self):
        # prepare test
        expected = "success reuslt"

        class TargetClass(object):
            @validation.method(rules.InstanceRequireAPI)
            def meth(self, instance_id):
                return expected
        validation.apply()
        target = TargetClass()
        instance_id = 10
        values = {'id': instance_id}
        db.instance_create(self.context, values)
        # perfom target
        actual = target.meth(instance_id)
        #assert result
        self.assertEqual(actual, expected)

    def test_instance_require_api_by_instance_id_instance_not_found(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.InstanceRequireAPI)
            def meth(self, instance_id):
                raise Exception("not return")
                return "not return"
        validation.apply()
        target = TargetClass()
        instance_id = 10
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPNotFound, target.meth, instance_id)

    def test_instance_require_api_db_error(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.InstanceRequireAPI)
            def meth(self, instance_id):
                raise exception.DBError("Failed to query")
                return "not return"
        validation.apply()
        target = TargetClass()
        instance_id = 10
        values = {'id': instance_id}
        db.instance_create(self.context, values)
        # perfom target and assert result
        self.assertRaises(exception.DBError, target.meth, instance_id)

    def test_instance_can_snapshot_not_found_by_uuid(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.InstanceCanSnapshot)
            def meth(self, instance_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        uuid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPNotFound, target.meth, uuid)

    def test_instance_can_snapshot_not_found_by_instance_id(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.InstanceCanSnapshot)
            def meth(self, instance_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        instance_id = 10
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPNotFound, target.meth, instance_id)

    def test_instance_can_snapshot_active_and_none(self):
        # prepare test
        expected = "success result"

        class TargetClass(object):
            @validation.method(rules.InstanceCanSnapshot)
            def meth(self, instance_id):
                return expected
        validation.apply()
        target = TargetClass()
        instance_id = 10
        values = {'id': instance_id,
                'vm_state': vm_states.ACTIVE,
                'task_state': None}
        db.instance_create(self.context, values)
        # perfom target
        actual = target.meth(instance_id)
        # assert result
        self.assertEqual(actual, expected)

    def test_instance_can_snapshot_snapshotting(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.InstanceCanSnapshot)
            def meth(self, instance_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        instance_id = 10
        values = {'id': instance_id,
                'vm_state': vm_states.ACTIVE,
                'task_state': task_states.IMAGE_SNAPSHOT}
        db.instance_create(self.context, values)
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPConflict, target.meth, instance_id)

    def test_instance_can_snapshot_non_active(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.InstanceCanSnapshot)
            def meth(self, instance_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        instance_id = 10
        values = {'id': instance_id,
                'vm_state': vm_states.BUILDING,
                'task_state': task_states.SCHEDULING}
        db.instance_create(self.context, values)
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPForbidden, target.meth, instance_id)

    def test_instance_can_snapshot_db_error(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.InstanceCanSnapshot)
            def meth(self, instance_id):
                raise exception.DBError("Failed to query.")
                return "not return"
        validation.apply()
        target = TargetClass()
        instance_id = 10
        values = {'id': instance_id,
                'vm_state': vm_states.ACTIVE,
                'task_state': None}
        db.instance_create(self.context, values)
        # perfom target and assert result
        self.assertRaises(exception.DBError, target.meth, instance_id)

    def test_instance_name_valid_api(self):
        # prepare test
        expected = "success result"

        class TargetClass(object):
            @validation.method(rules.InstanceNameValidAPI)
            def meth(self, instance_name):
                return expected
        validation.apply()
        target = TargetClass()
        instance_name = "valid instance name"
        # perform target
        actual = target.meth(instance_name)
        # assert result
        self.assertEqual(actual, expected)

    def test_instance_name_valid_api_name_required_blank(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.InstanceNameValidAPI)
            def meth(self, instance_name):
                return "not return"
        validation.apply()
        target = TargetClass()
        instance_name = ""
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, instance_name)

    def test_instance_name_valid_api_name_required_none(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.InstanceNameValidAPI)
            def meth(self, instance_name):
                return "not return"
        validation.apply()
        target = TargetClass()
        instance_name = None
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, instance_name)

    def test_instance_name_valid_api_invalid_long_length(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.InstanceNameValidAPI)
            def meth(self, instance_name):
                return "not return"
        validation.apply()
        target = TargetClass()
        instance_name = "".join(["a" for i in range(0, 256)])
        if len(instance_name) <= 255:
            self.assertEqual(True, False)
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, instance_name)

    def test_instance_can_reboot_active_none(self):
        # prepare test
        expected = "success result"

        class TargetClass(object):
            @validation.method(rules.InstanceCanReboot)
            def meth(self, instance_id):
                return expected
        validation.apply()
        target = TargetClass()
        instance_id = 10
        values = {'id': instance_id,
                'vm_state': vm_states.ACTIVE,
                'task_state': None}
        db.instance_create(self.context, values)
        # perform target
        actual = target.meth(instance_id)
        # assert result
        self.assertEqual(actual, expected)

    def test_instance_can_reboot_active_rebooting(self):
        # prepare test
        expected = "success result"

        class TargetClass(object):
            @validation.method(rules.InstanceCanReboot)
            def meth(self, instance_id):
                return expected
        validation.apply()
        target = TargetClass()
        instance_id = 10
        values = {'id': instance_id,
                'vm_state': vm_states.ACTIVE,
                'task_state': task_states.REBOOTING}
        db.instance_create(self.context, values)
        # perform target
        actual = target.meth(instance_id)
        # assert result
        self.assertEqual(actual, expected)

    def test_instance_can_reboot_non_active(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.InstanceCanReboot)
            def meth(self, instance_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        instance_id = 10
        values = {'id': instance_id,
                'vm_state': vm_states.BUILDING,
                'task_state': None}
        db.instance_create(self.context, values)
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPForbidden, target.meth, instance_id)

    def test_instance_can_reboot_not_found_instance(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.InstanceCanReboot)
            def meth(self, instance_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        instance_id = 10
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPNotFound, target.meth, instance_id)

    def test_instance_can_reboot_db_error(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.InstanceCanReboot)
            def meth(self, instance_id):
                raise exception.DBError("Failed to query.")
                return "not return"
        validation.apply()
        target = TargetClass()
        uuid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        values = {
                'uuid': uuid,
                'vm_state': vm_states.ACTIVE,
                'task_state': None}
        db.instance_create(self.context, values)
        # perfom target and assert result
        self.assertRaises(exception.DBError, target.meth, uuid)

    def test_instance_can_destroy_sucess(self):
        # prepare test
        expected = "success result"

        class TargetClass(object):
            @validation.method(rules.InstanceCanDestroy)
            def meth(self, instance_id):
                return expected
        validation.apply()
        target = TargetClass()
        instance_id = 10
        values = {'id': instance_id,
                'vm_state': vm_states.ACTIVE,
                'task_state': None}
        db.instance_create(self.context, values)
        # perform target
        actual = target.meth(instance_id)
        # assert result
        self.assertEqual(actual, expected)

    def test_instance_can_destroy_not_found(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.InstanceCanDestroy)
            def meth(self, instance_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        instance_id = 10
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPNotFound, target.meth, instance_id)

    def test_instance_can_destroy_rebooting_instance(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.InstanceCanDestroy)
            def meth(self, instance_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        instance_id = 10
        values = {'id': instance_id,
                'vm_state': vm_states.ACTIVE,
                'task_state': task_states.REBOOTING}
        db.instance_create(self.context, values)
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPForbidden, target.meth, instance_id)

    def test_instance_can_destroy_db_error(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.InstanceCanDestroy)
            def meth(self, instance_id):
                raise exception.DBError("Failed to query.")
                return "not return"
        validation.apply()
        target = TargetClass()
        uuid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        values = {
                'uuid': uuid,
                'vm_state': vm_states.ACTIVE,
                'task_state': None}
        db.instance_create(self.context, values)
        # perfom target and assert result
        self.assertRaises(exception.DBError, target.meth, uuid)

    def test_image_name_valid_api_valid_name(self):
        # prepare test
        expected = "success result"

        class TargetClass(object):
            @validation.method(rules.ImageNameValidAPI)
            def meth(self, image_name):
                return expected
        validation.apply()
        target = TargetClass()
        image_name = "valid image name"
        # perform target
        actual = target.meth(image_name)
        # assert result
        self.assertEqual(actual, expected)

    def test_image_name_valid_api_blank(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.ImageNameValidAPI)
            def meth(self, image_name):
                return "not return"
        validation.apply()
        target = TargetClass()
        image_name = ""
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, image_name)

    def test_image_name_valid_api_none(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.ImageNameValidAPI)
            def meth(self, image_name):
                return "not return"
        validation.apply()
        target = TargetClass()
        image_name = None
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, image_name)

    def test_image_name_valid_api_invalid_length(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.ImageNameValidAPI)
            def meth(self, image_name):
                return "not return"
        validation.apply()
        target = TargetClass()
        image_name = "".join(["a" for i in range(0, 256)])
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, image_name)

    def test_image_name_valid_api_db_error(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.ImageNameValidAPI)
            def meth(self, image_name):
                raise exception.DBError("Failed to query")
                return "not return"
        validation.apply()
        target = TargetClass()
        image_name = "valid name"
        # perfom target and assert result
        self.assertRaises(exception.DBError, target.meth, image_name)

    def test_metadata_valid_api_valid_key_and_value(self):
        # prepare test
        expected = "success result"

        class TargetClass(object):
            @validation.method(rules.MetadataValidAPI)
            def meth(self, metadata):
                return expected
        validation.apply()
        target = TargetClass()
        metadata = {"aaa": "bbb", "ccc": "ddd"}
        # perform target
        actual = target.meth(metadata)
        # assert result
        self.assertEqual(actual, expected)

    def test_metadata_valid_api_empty(self):
        # prepare test
        expected = "success result"

        class TargetClass(object):
            @validation.method(rules.MetadataValidAPI)
            def meth(self, metadata):
                return expected
        validation.apply()
        target = TargetClass()
        metadata = {}
        # perform target
        actual = target.meth(metadata)
        # assert result
        self.assertEqual(actual, expected)

    def test_metadata_valid_api_none(self):
        # prepare test
        expected = "success result"

        class TargetClass(object):
            @validation.method(rules.MetadataValidAPI)
            def meth(self, metadata):
                return expected
        validation.apply()
        target = TargetClass()
        metadata = None
        # perform target
        actual = target.meth(metadata)
        # assert result
        self.assertEqual(actual, expected)

    def test_metadata_valid_api_invalid_key_length(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.MetadataValidAPI)
            def meth(self, metadata):
                return "not return"
        validation.apply()
        target = TargetClass()
        metadata = {"a" * 256: "bbb"}
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, metadata)

    def test_metadata_valid_api_invalid_value_length(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.MetadataValidAPI)
            def meth(self, metadata):
                return "not return"
        validation.apply()
        target = TargetClass()
        metadata = {"aaa": "bbb", "ccc": "d" * 256}
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, metadata)

    def test_metadata_valid_api_key_and_value_are_blank(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.MetadataValidAPI)
            def meth(self, metadata):
                return "not return"
        validation.apply()
        target = TargetClass()
        metadata = {"": ""}
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, metadata)

    def test_flavor_require_api_valid_flavor(self):
        # prepare test
        expected = "success result"

        class TargetClass(object):
            @validation.method(rules.FlavorRequireAPI)
            def meth(self, flavor_id):
                return expected
        validation.apply()
        target = TargetClass()
        flavor_id = "1"
        # perform target
        actual = target.meth(flavor_id)
        # assert result
        self.assertEqual(actual, expected)

    def test_flavor_require_api_negative_value(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.FlavorRequireAPI)
            def meth(self, flavor_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        flavor_id = "-10"
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, flavor_id)

    def test_flavor_require_api_too_large(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.FlavorRequireAPI)
            def meth(self, flavor_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        flavor_id = sys.maxint + 1
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, flavor_id)

    def test_flavor_require_api_not_number(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.FlavorRequireAPI)
            def meth(self, flavor_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        flavor_id = "not number"
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, flavor_id)

    def test_flavor_require_api_not_found(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.FlavorRequireAPI)
            def meth(self, flavor_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        flavor_id = "100000"
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPNotFound, target.meth, flavor_id)

    def test_flavor_require_api_db_error(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.FlavorRequireAPI)
            def meth(self, flavor_id):
                raise exception.DBError("Failed to query")
                return "not return"
        validation.apply()
        target = TargetClass()
        flavor_id = "1"
        # perfom target and assert result
        self.assertRaises(exception.DBError, target.meth, flavor_id)

    def test_flavor_require_for_create_server_api_valid_flavor(self):
        # prepare test
        expected = "success result"

        class TargetClass(object):
            @validation.method(rules.FlavorRequireForCreateServerAPI)
            def meth(self, flavor_id):
                return expected
        validation.apply()
        target = TargetClass()
        flavor_id = "1"
        # perform target
        actual = target.meth(flavor_id)
        # assert result
        self.assertEqual(actual, expected)

    def test_flavor_require_for_create_server_api_negative_value(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.FlavorRequireForCreateServerAPI)
            def meth(self, flavor_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        flavor_id = "-10"
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, flavor_id)

    def test_flavor_require_for_create_server_api_too_large(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.FlavorRequireForCreateServerAPI)
            def meth(self, flavor_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        flavor_id = sys.maxint + 1
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, flavor_id)

    def test_flavor_require_for_create_server_api_not_number(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.FlavorRequireForCreateServerAPI)
            def meth(self, flavor_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        flavor_id = "not number"
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, flavor_id)

    def test_flavor_require_for_create_server_api_not_found(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.FlavorRequireForCreateServerAPI)
            def meth(self, flavor_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        flavor_id = "100000"
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, flavor_id)

    def test_flavor_require_for_create_server_api_db_error(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.FlavorRequireForCreateServerAPI)
            def meth(self, flavor_id):
                raise exception.DBError("Failed to query")
                return "not return"
        validation.apply()
        target = TargetClass()
        flavor_id = "1"
        # perfom target and assert result
        self.assertRaises(exception.DBError, target.meth, flavor_id)

    def test_image_require_api_valid_image(self):
        # prepare test
        expected = "success result"

        class TargetClass(object):
            @validation.method(rules.ImageRequireAPI)
            def meth(self, image_id):
                return expected
        validation.apply()
        target = TargetClass()
        image_id = "1"
        # perform target
        actual = target.meth(image_id)
        # assert result
        self.assertEqual(actual, expected)

    def test_image_require_api_negative_value(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.ImageRequireAPI)
            def meth(self, image_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        image_id = "-10"
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, image_id)

    def test_image_require_api_too_large(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.ImageRequireAPI)
            def meth(self, image_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        image_id = sys.maxint + 1
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, image_id)

    def test_image_require_api_not_digit(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.ImageRequireAPI)
            def meth(self, image_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        image_id = 1.1
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPNotFound, target.meth, image_id)

    def test_image_require_api_not_number(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.ImageRequireAPI)
            def meth(self, image_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        image_id = "not number"
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, image_id)

    def test_image_require_api_not_found(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.ImageRequireAPI)
            def meth(self, image_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        image_id = "12345"
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPNotFound, target.meth, image_id)

    def test_image_require_api_db_error(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.ImageRequireAPI)
            def meth(self, image_id):
                raise exception.DBError("Failed to query")
                return "not return"
        validation.apply()
        target = TargetClass()
        image_id = "1"
        # perfom target and assert result
        self.assertRaises(exception.DBError, target.meth, image_id)

    def test_image_require_for_create_server_api_valid_image(self):
        # prepare test
        expected = "success result"

        class TargetClass(object):
            @validation.method(rules.ImageRequireForCreateServerAPI)
            def meth(self, image_id):
                return expected
        validation.apply()
        target = TargetClass()
        image_id = "1"
        # perform target
        actual = target.meth(image_id)
        # assert result
        self.assertEqual(actual, expected)

    def test_image_require_for_create_server_api_negative_value(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.ImageRequireForCreateServerAPI)
            def meth(self, image_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        image_id = "-10"
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, image_id)

    def test_image_require_for_create_server_api_too_large(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.ImageRequireForCreateServerAPI)
            def meth(self, image_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        image_id = sys.maxint + 1
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, image_id)

    def test_image_require_for_create_server_api_not_digit(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.ImageRequireForCreateServerAPI)
            def meth(self, image_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        image_id = 1.1
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, image_id)

    def test_image_require_for_create_server_api_not_number(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.ImageRequireForCreateServerAPI)
            def meth(self, image_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        image_id = "not number"
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, image_id)

    def test_image_require_for_create_server_api_not_found(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.ImageRequireForCreateServerAPI)
            def meth(self, image_id):
                return "not return"
        validation.apply()
        target = TargetClass()
        image_id = "12345"
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, image_id)

    def test_image_require_for_create_server_api_db_error(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.ImageRequireForCreateServerAPI)
            def meth(self, image_id):
                raise exception.DBError("Failed to query")
                return "not return"
        validation.apply()
        target = TargetClass()
        image_id = "1"
        # perfom target and assert result
        self.assertRaises(exception.DBError, target.meth, image_id)

    def test_zone_name_valid_api_valid_name(self):
        # prepare test
        expected = "success result"

        class TargetClass(object):
            @validation.method(rules.ZoneNameValidAPI)
            def meth(self, zone_name):
                return expected
        validation.apply()
        target = TargetClass()
        zone_name = "zone"
        # perform target
        actual = target.meth(zone_name)
        # assert result
        self.assertEqual(actual, expected)

    def test_zone_name_valid_api_blank(self):
        # prepare test
        expected = "success result"

        class TargetClass(object):
            @validation.method(rules.ZoneNameValidAPI)
            def meth(self, zone_name):
                return expected
        validation.apply()
        target = TargetClass()
        zone_name = ""
        # perform target
        actual = target.meth(zone_name)
        # assert result
        self.assertEqual(actual, expected)

    def test_zone_name_valid_api_none(self):
        # prepare test
        expected = "success result"

        class TargetClass(object):
            @validation.method(rules.ZoneNameValidAPI)
            def meth(self, zone_name):
                return expected
        validation.apply()
        target = TargetClass()
        zone_name = None
        # perform target
        actual = target.meth(zone_name)
        # assert result
        self.assertEqual(actual, expected)

    def test_zone_name_valid_api_not_found(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.ZoneNameValidAPI)
            def meth(self, zone_name):
                return "not return"
        validation.apply()
        target = TargetClass()
        zone_name = "hoge1:hoge2:hoge3"
        # perfom target and assert result
        self.assertRaises(webob.exc.HTTPBadRequest, target.meth, zone_name)

    def test_zone_name_valid_api_db_error(self):
        # prepare test
        class TargetClass(object):
            @validation.method(rules.ZoneNameValidAPI)
            def meth(self, zone_name):
                raise exception.DBError("Failed to query")
                return "not return"
        validation.apply()
        target = TargetClass()
        zone_name = "zone"
        # perfom target and assert result
        self.assertRaises(exception.DBError, target.meth, zone_name)

    def test_zone_name_valid_api_find_service(self):
        # prepare test
        expected = "success result"

        class TargetClass(object):
            @validation.method(rules.ZoneNameValidAPI)
            def meth(self, zone_name):
                return expected
        validation.apply()
        target = TargetClass()
        zone, host = ("zone", "host")
        values = {
                'host': host,
                'binary': 'nova-compute',
                }
        db.service_create(self.context, values)
        zone_name = ":".join([zone, host])
        # perform target
        actual = target.meth(zone_name)
        # assert result
        self.assertEqual(actual, expected)
