# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 Openstack LLC.
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


import datetime
import unittest

from nova import context
from nova import exception
from nova import test
from nova.image import glance

from nova.tests.api.openstack import fakes
import stubout
from nose.plugins.attrib import attr
from glance import client
from glance.common import exception as clientexception
import tempfile
from nova import flags
import os

FLAGS = flags.FLAGS


class StubGlanceClient(object):

    def __init__(self, images, add_response=None, update_response=None):
        self.images = images
        self.add_response = add_response
        self.update_response = update_response

    def set_auth_token(self, auth_tok):
        pass

    def get_image_meta(self, image_id):
        return self.images[image_id]

    def get_images_detailed(self, filters=None, marker=None, limit=None):
        images = self.images.values()
        if marker is None:
            index = 0
        else:
            for index, image in enumerate(images):
                if image['id'] == marker:
                    index += 1
                    break
        # default to a page size of 3 to ensure we flex the pagination code
        return images[index:index + 3]

    def get_image(self, image_id):
        return self.images[image_id], []

    def add_image(self, metadata, data):
        return self.add_response

    def update_image(self, image_id, metadata, data):
        return self.update_response


class NullWriter(object):
    """Used to test ImageService.get which takes a writer object"""

    def write(self, *arg, **kwargs):
        pass


class BaseGlanceTest(unittest.TestCase):
    NOW_GLANCE_OLD_FORMAT = "2010-10-11T10:30:22"
    NOW_GLANCE_FORMAT = "2010-10-11T10:30:22.000000"
    NOW_DATETIME = datetime.datetime(2010, 10, 11, 10, 30, 22)

    def setUp(self):
        self.client = StubGlanceClient(None)
        self.service = glance.GlanceImageService(client=self.client)
        self.context = context.RequestContext(None, None)

    def assertDateTimesFilled(self, image_meta):
        self.assertEqual(image_meta['created_at'], self.NOW_DATETIME)
        self.assertEqual(image_meta['updated_at'], self.NOW_DATETIME)
        self.assertEqual(image_meta['deleted_at'], self.NOW_DATETIME)

    def assertDateTimesEmpty(self, image_meta):
        self.assertEqual(image_meta['updated_at'], None)
        self.assertEqual(image_meta['deleted_at'], None)

    def assertDateTimesBlank(self, image_meta):
        self.assertEqual(image_meta['updated_at'], '')
        self.assertEqual(image_meta['deleted_at'], '')


class TestGlanceImageServiceProperties(BaseGlanceTest):
    def test_show_passes_through_to_client(self):
        """Ensure attributes which aren't BASE_IMAGE_ATTRS are stored in the
        properties dict
        """
        fixtures = {'image1': {'id': '1', 'name': 'image1', 'is_public': True,
                               'foo': 'bar',
                               'properties': {'prop1': 'propvalue1'}}}
        self.client.images = fixtures
        image_meta = self.service.show(self.context, 'image1')

        expected = {'id': '1', 'name': 'image1', 'is_public': True,
                    'properties': {'prop1': 'propvalue1', 'foo': 'bar'}}
        self.assertEqual(image_meta, expected)

    def test_show_raises_when_no_authtoken_in_the_context(self):
        fixtures = {'image1': {'name': 'image1', 'is_public': False,
                               'foo': 'bar',
                               'properties': {'prop1': 'propvalue1'}}}
        self.client.images = fixtures
        self.context.auth_token = False

        expected = {'name': 'image1', 'is_public': True,
                    'properties': {'prop1': 'propvalue1', 'foo': 'bar'}}
        self.assertRaises(exception.ImageNotFound,
                          self.service.show, self.context, 'image1')

    def test_show_passes_through_to_client_with_authtoken_in_context(self):
        fixtures = {'image1': {'name': 'image1', 'is_public': False,
                               'foo': 'bar',
                               'properties': {'prop1': 'propvalue1'}}}
        self.client.images = fixtures
        self.context.auth_token = True

        expected = {'name': 'image1', 'is_public': False,
                    'properties': {'prop1': 'propvalue1', 'foo': 'bar'}}

        image_meta = self.service.show(self.context, 'image1')
        self.assertEqual(image_meta, expected)

    def test_detail_passes_through_to_client(self):
        fixtures = {'image1': {'id': '1', 'name': 'image1', 'is_public': True,
                               'foo': 'bar',
                               'properties': {'prop1': 'propvalue1'}}}
        self.client.images = fixtures
        image_meta = self.service.detail(self.context)
        expected = [{'id': '1', 'name': 'image1', 'is_public': True,
                    'properties': {'prop1': 'propvalue1', 'foo': 'bar'}}]
        self.assertEqual(image_meta, expected)


class TestGetterDateTimeNoneTests(BaseGlanceTest):

    def test_show_handles_none_datetimes(self):
        self.client.images = self._make_none_datetime_fixtures()
        image_meta = self.service.show(self.context, 'image1')
        self.assertDateTimesEmpty(image_meta)

    def test_show_handles_blank_datetimes(self):
        self.client.images = self._make_blank_datetime_fixtures()
        image_meta = self.service.show(self.context, 'image1')
        self.assertDateTimesBlank(image_meta)

    def test_detail_handles_none_datetimes(self):
        self.client.images = self._make_none_datetime_fixtures()
        image_meta = self.service.detail(self.context)[0]
        self.assertDateTimesEmpty(image_meta)

    def test_detail_handles_blank_datetimes(self):
        self.client.images = self._make_blank_datetime_fixtures()
        image_meta = self.service.detail(self.context)[0]
        self.assertDateTimesBlank(image_meta)

    def test_get_handles_none_datetimes(self):
        self.client.images = self._make_none_datetime_fixtures()
        writer = NullWriter()
        image_meta = self.service.get(self.context, 'image1', writer)
        self.assertDateTimesEmpty(image_meta)

    def test_get_handles_blank_datetimes(self):
        self.client.images = self._make_blank_datetime_fixtures()
        writer = NullWriter()
        image_meta = self.service.get(self.context, 'image1', writer)
        self.assertDateTimesBlank(image_meta)

    def test_show_makes_datetimes(self):
        self.client.images = self._make_datetime_fixtures()
        image_meta = self.service.show(self.context, 'image1')
        self.assertDateTimesFilled(image_meta)
        image_meta = self.service.show(self.context, 'image2')
        self.assertDateTimesFilled(image_meta)

    def test_detail_makes_datetimes(self):
        self.client.images = self._make_datetime_fixtures()
        image_meta = self.service.detail(self.context)[0]
        self.assertDateTimesFilled(image_meta)
        image_meta = self.service.detail(self.context)[1]
        self.assertDateTimesFilled(image_meta)

    def test_get_makes_datetimes(self):
        self.client.images = self._make_datetime_fixtures()
        writer = NullWriter()
        image_meta = self.service.get(self.context, 'image1', writer)
        self.assertDateTimesFilled(image_meta)
        image_meta = self.service.get(self.context, 'image2', writer)
        self.assertDateTimesFilled(image_meta)

    def _make_datetime_fixtures(self):
        fixtures = {
            'image1': {
                'id': '1',
                'name': 'image1',
                'is_public': True,
                'created_at': self.NOW_GLANCE_FORMAT,
                'updated_at': self.NOW_GLANCE_FORMAT,
                'deleted_at': self.NOW_GLANCE_FORMAT,
            },
            'image2': {
                'id': '2',
                'name': 'image2',
                'is_public': True,
                'created_at': self.NOW_GLANCE_OLD_FORMAT,
                'updated_at': self.NOW_GLANCE_OLD_FORMAT,
                'deleted_at': self.NOW_GLANCE_OLD_FORMAT,
            },
        }
        return fixtures

    def _make_none_datetime_fixtures(self):
        fixtures = {'image1': {'id': '1',
                               'name': 'image1',
                               'is_public': True,
                               'updated_at': None,
                               'deleted_at': None}}
        return fixtures

    def _make_blank_datetime_fixtures(self):
        fixtures = {'image1': {'id': '1',
                               'name': 'image1',
                               'is_public': True,
                               'updated_at': '',
                               'deleted_at': ''}}
        return fixtures


class TestMutatorDateTimeTests(BaseGlanceTest):
    """Tests create(), update()"""

    def test_create_handles_datetimes(self):
        self.client.add_response = self._make_datetime_fixture()
        image_meta = self.service.create(self.context, {})
        self.assertDateTimesFilled(image_meta)

    def test_create_handles_none_datetimes(self):
        self.client.add_response = self._make_none_datetime_fixture()
        dummy_meta = {}
        image_meta = self.service.create(self.context, dummy_meta)
        self.assertDateTimesEmpty(image_meta)

    def test_update_handles_datetimes(self):
        self.client.images = {'image1': self._make_datetime_fixture()}
        self.client.update_response = self._make_datetime_fixture()
        dummy_meta = {}
        image_meta = self.service.update(self.context, 'image1', dummy_meta)
        self.assertDateTimesFilled(image_meta)

    def test_update_handles_none_datetimes(self):
        self.client.images = {'image1': self._make_datetime_fixture()}
        self.client.update_response = self._make_none_datetime_fixture()
        dummy_meta = {}
        image_meta = self.service.update(self.context, 'image1', dummy_meta)
        self.assertDateTimesEmpty(image_meta)

    def _make_datetime_fixture(self):
        fixture = {'id': 'image1', 'name': 'image1', 'is_public': True,
                   'created_at': self.NOW_GLANCE_FORMAT,
                   'updated_at': self.NOW_GLANCE_FORMAT,
                   'deleted_at': self.NOW_GLANCE_FORMAT}
        return fixture

    def _make_none_datetime_fixture(self):
        fixture = {'id': 'image1', 'name': 'image1', 'is_public': True,
                   'updated_at': None,
                   'deleted_at': None}
        return fixture


class TestGlanceSerializer(unittest.TestCase):
    def test_serialize(self):
        metadata = {'name': 'image1',
                    'is_public': True,
                    'foo': 'bar',
                    'properties': {
                        'prop1': 'propvalue1',
                        'mappings': [
                            {'virtual': 'aaa',
                             'device': 'bbb'},
                            {'virtual': 'xxx',
                             'device': 'yyy'}],
                        'block_device_mapping': [
                            {'virtual_device': 'fake',
                             'device_name': '/dev/fake'},
                            {'virtual_device': 'ephemeral0',
                             'device_name': '/dev/fake0'}]}}

        converted_expected = {
            'name': 'image1',
            'is_public': True,
            'foo': 'bar',
            'properties': {
                'prop1': 'propvalue1',
                'mappings':
                '[{"device": "bbb", "virtual": "aaa"}, '
                '{"device": "yyy", "virtual": "xxx"}]',
                'block_device_mapping':
                '[{"virtual_device": "fake", "device_name": "/dev/fake"}, '
                '{"virtual_device": "ephemeral0", '
                '"device_name": "/dev/fake0"}]'}}
        converted = glance._convert_to_string(metadata)
        self.assertEqual(converted, converted_expected)
        self.assertEqual(glance._convert_from_string(converted), metadata)


class GlanceTestCase(test.TestCase):
    """Test for nova.image.glance """
    def setUp(self):
        super(GlanceTestCase, self).setUp()

    @attr(kind='small')
    def test_get_glance_client(self):
        """Test for nova.image.glance.get_glance_client.
        Make sure return a glance client object with specified host and port"""

        image_href = 10

        ref = glance.get_glance_client(context.get_admin_context(), image_href)

        self.assertEqual(glance.pick_glance_api_server()[0], ref[0].host)
        self.assertEqual(glance.pick_glance_api_server()[1], ref[0].port)
        self.assertEqual(image_href, ref[1])

    @attr(kind='small')
    def test_get_glance_client_parameter_id(self):
        """Test for nova.image.glance.get_glance_client.
        Verify image_ref parameter can be a numeric string """

        image_href = '10'

        ref = glance.get_glance_client(context.get_admin_context(), image_href)

        self.assertEqual(glance.pick_glance_api_server()[0], ref[0].host)
        self.assertEqual(glance.pick_glance_api_server()[1], ref[0].port)
        self.assertEqual(10, ref[1])

    @attr(kind='small')
    def test_get_glance_client_parameter_imgurl(self):
        """Test for nova.image.glance.get_glance_client.
        Verify image_ref parameter can be a url """

        # url with host and port and id
        id = 10
        host = 'localhost'
        port = 1234

        image_href = 'http://' + host + ':' + str(port) + '/image/' + str(id)
        ref = glance.get_glance_client(context.get_admin_context(), image_href)

        self.assertEqual(host, ref[0].host)
        self.assertEqual(port, ref[0].port)
        self.assertEqual(id, ref[1])

        # url without port
        id = 10
        host = 'localhost'
        port = ''

        image_href = 'http://' + host + '/image/' + str(id)
        ref = glance.get_glance_client(context.get_admin_context(), image_href)

        self.assertEqual(host, ref[0].host)
        self.assertEqual(80, ref[0].port)
        self.assertEqual(id, ref[1])

        # url without host
        id = 10
        host = ''
        port = 1234

        image_href = 'http://' + host + ':' + str(port) + '/image/' + str(id)
        ref = glance.get_glance_client(context.get_admin_context(), image_href)

        self.assertEqual(host, ref[0].host)
        self.assertEqual(port, ref[0].port)
        self.assertEqual(id, ref[1])

        # url without host and port
        id = 10
        host = ''
        port = ''

        image_href = '/image/' + str(id)
        ref = glance.get_glance_client(context.get_admin_context(), image_href)

        self.assertEqual(host, ref[0].host)
        self.assertEqual(80, ref[0].port)
        self.assertEqual(id, ref[1])

    @attr(kind='small')
    def test_get_glance_client_parameter_with_keystone(self):
        """Test for nova.image.glance.get_glance_client.
        Make sure return a glance client object that context is keystone """

        image_href = '10'

        ctx = context.get_admin_context()
        ctx.strategy = 'keystone'

        ref = glance.get_glance_client(ctx, image_href)

        self.assertEqual(glance.pick_glance_api_server()[0], ref[0].host)
        self.assertEqual(glance.pick_glance_api_server()[1], ref[0].port)
        self.assertEqual(10, ref[1])

    @attr(kind='small')
    def test_get_glance_client_exception(self):
        """Test for nova.image.glance.get_glance_client.
        Raise InvalidImageRef if image_href parameter is a string"""

        image_href = '/abcd'

        self.assertRaises(exception.InvalidImageRef,
            glance.get_glance_client, context.get_admin_context(), image_href)

    @attr(kind='small')
    def test_pick_glance_api_server_configuration(self):
        """Test for nova.image.glance.pick_glance_api_server.
        Verify take a random host and port from glance_api_servers flag"""

        self.flags(glance_api_servers=['host1:1234', 'host2:5678'])

        ref = glance.pick_glance_api_server()

        self.assertTrue(ref in (('host1', 1234), ('host2', 5678)))


class GlanceImageServiceTestCase(test.TestCase):
    """Test for nova.image.glance.GlanceImageService."""
    def setUp(self):
        super(GlanceImageServiceTestCase, self).setUp()

        self.stubs = stubout.StubOutForTesting()
        fakes.stub_out_compute_api_snapshot(self.stubs)
#        client = glance_stubs.StubGlanceClient()
#        self.glanceimageservice = glance.GlanceImageService(client=client)
        self.context = context.RequestContext('fake', 'fake', auth_token=True)
        self.glanceimageservice_real = glance.GlanceImageService()

    @attr(kind='small')
    def test_create_parameter(self):
        """Test for nova.image.glance.GlanceImageService.create.
        Verify parameter use fake client"""

        self.meta = dict(size='10k', location='e', disk_format='ami',
                        container_format='win0', checksum='250', id='2',
                        name='n', created_at=None, updated_at=None,
                        deleted_at=None, deleted=False, status='active',
                        is_public=True,
                        properties={'instance_id': '42', 'user_id': 'fake',
                                    'project_id': None, 'architecture': 'x86',
                                    'kernel_id': None, 'ramdisk_id': None,
                                    'image_state': 'available'})

        def fake_add_image(serv, image_meta=None, image_data=None):
            return self.meta

        self.stubs.Set(client.Client, 'add_image', fake_add_image)

        data = '/file1'
        ref = self.glanceimageservice_real.create(context.get_admin_context(),
                                             image_meta=self.meta, data=data)

        self.assertEqual(self.meta['properties'], ref['properties'])

    @attr(kind='small')
    def test_create_exception(self):
        """Test for nova.image.glance.GlanceImageService.create.
        Raise ClientConnectionError if can not connect to service server"""

        meta = dict(size='10k', location='e', disk_format='ami',
                        container_format='win0', checksum='250', id='2',
                        name='n', created_at=None, updated_at=None,
                        deleted_at=None, deleted=False, status='OK',
                        is_public=True)
        self.assertRaises(clientexception.ClientConnectionError,
                self.glanceimageservice_real.create,
                    context.get_admin_context(), image_meta=meta, data=None)

    @attr(kind='small')
    def test_delete_parameter(self):
        """Test for nova.image.glance.GlanceImageService.delete.
        Return true if delete success"""

        def fake_get_image_meta(self, image_id):
            return dict()

        self.stubs.Set(client.Client, 'get_image_meta', fake_get_image_meta)

        def fake_delete(self, image_id):
            return True

        self.stubs.Set(client.Client, 'delete_image', fake_delete)

        ref = self.glanceimageservice_real.delete(self.context, image_id=None)
        self.assertEqual(True, ref)

        ref = self.glanceimageservice_real.delete(self.context,
                                                  image_id='abcd')
        self.assertEqual(True, ref)

    @attr(kind='small')
    def test_delete_exception_notfound(self):
        """Test for nova.image.glance.GlanceImageService.delete.
        Raise ImageNotFound if image specified by id can not show"""

        def fake_get_image_meta(self, image_id):
            raise clientexception.NotFound

        self.stubs.Set(client.Client, 'get_image_meta', fake_get_image_meta)

        self.assertRaises(exception.ImageNotFound,
                    self.glanceimageservice_real.delete, self.context,
                        image_id=1)

    @attr(kind='small')
    def test_delete_exception_unavailable(self):
        """Test for nova.image.glance.GlanceImageService.delete.
        Raise ImageNotFound if image available checking error"""

        def fake_available(self, context, image_meta):
            return False

        self.stubs.Set(glance.GlanceImageService, '_is_image_available',
                       fake_available)

        meta = dict(id='2', is_public=True,  properties={})

        def fake_add_image(serv, image_meta=None, image_data=None):
            return dict(id='2')

        self.stubs.Set(client.Client, 'add_image', fake_add_image)

        def fake_get_image_meta(self, image_id):
            return dict()

        self.stubs.Set(client.Client, 'get_image_meta', fake_get_image_meta)

        ref = self.glanceimageservice_real.create(context.get_admin_context(),
                                             image_meta=meta, data=None)

        self.assertRaises(exception.ImageNotFound,
            self.glanceimageservice_real.delete, self.context,
                image_id=ref['id'])

    @attr(kind='small')
    def test_delete_exception_client(self):
        """Test for nova.image.glance.GlanceImageService.delete.
        Raise ImageNotFound if image specified by id can not show"""

        def fake_delete(self, image_id):
            raise client.exception.NotFound

        self.stubs.Set(client.Client, 'delete_image', fake_delete)

        def fake_show(self, context, image_id):
            pass

        self.stubs.Set(glance.GlanceImageService, 'show', fake_show)

        self.assertRaises(exception.ImageNotFound,
            self.glanceimageservice_real.delete, self.context, image_id=1)

    @attr(kind='small')
    def test_delete_all(self):
        """Test for nova.image.glance.GlanceImageService.delete_all.
        no implement"""

        ref = self.glanceimageservice_real.delete_all()
        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_detail_parameter(self):
        """Test for nova.image.glance.GlanceImageService.detail.
        Verify invalidate parameter be ignored"""

        def fake_get_images_detailed(self, **kwargs):
            return [dict(id=1)]

        self.stubs.Set(client.Client, 'get_images_detailed',
                       fake_get_images_detailed)

        validparam = dict(filters=dict(), marker='marker', limit=10,
                      sort_key='sort_key', sort_dir='sort_dir')

        kwargs = dict(key1='1')
        kwargs.update(validparam)

        ref = self.glanceimageservice_real.detail(self.context, **kwargs)

        self.assertEqual(10, len(ref))
        self.assertEqual(1, ref[0]['id'])
        self.assertTrue('key1' not in ref[0])

    @attr(kind='small')
    def test_detail_parameter_limit(self):
        """Test for nova.image.glance.GlanceImageService.detail.
        Verify return list size is little than limit parameter"""

        def fake_get_images_detailed(self, **kwargs):
            if kwargs['marker'] == '':
                return [dict(id=1)]
            elif  kwargs['marker'] == 1:
                return [dict(id=2)]
            elif  kwargs['marker'] == 2:
                return [dict(id=3)]
            else:
                return []

        self.stubs.Set(client.Client, 'get_images_detailed',
                       fake_get_images_detailed)

        kwargs = dict(filters=dict(), marker='', limit=2,
                      sort_key='sort_key', sort_dir='sort_dir')

        ref = self.glanceimageservice_real.detail(self.context, **kwargs)

        self.assertEqual(2, len(ref))

    @attr(kind='small')
    def test_detail_parameter_without_limit(self):
        """Test for nova.image.glance.GlanceImageService.detail.
        Return all images if no limit parameter specified"""

        def fake_get_images_detailed(self, **kwargs):
            if 'marker' in kwargs and kwargs['marker']:
                return []
            else:
                return [dict(id=1)]

        self.stubs.Set(client.Client, 'get_images_detailed',
                       fake_get_images_detailed)

        kwargs = dict()

        ref = self.glanceimageservice_real.detail(self.context, **kwargs)
        self.assertEqual(1, len(ref))

    @attr(kind='small')
    def test_detail_exception(self):
        """Test for nova.image.glance.GlanceImageService.detail.
        Raise ImagePaginationFailed if no id be returned"""

        def fake_get_images_detailed(self, **kwargs):
            return [dict()]

        self.stubs.Set(client.Client, 'get_images_detailed',
                       fake_get_images_detailed)

        kwargs = dict()

        self.assertRaises(exception.ImagePaginationFailed,
            self.glanceimageservice_real.detail, self.context, **kwargs)

    @attr(kind='small')
    def test_get(self):
        """Test for nova.image.glance.GlanceImageService.get.
        Make sure image meta be returned"""

        def fake_get_image(self, image_id):
            res = dict(id=1, limit=10)
            return res, ['aaa']

        self.stubs.Set(client.Client, 'get_image', fake_get_image)

        data = tempfile.NamedTemporaryFile(mode="w+t")

        ref = self.glanceimageservice_real.get(self.context,
                                               image_id=1, data=data)

        self.assertEqual(1, ref['id'])

    @attr(kind='small')
    def test_get_exception(self):
        """Test for nova.image.glance.GlanceImageService.get.
        Raise ImageNotFound if image not exist or input invalid parameter"""

        def fake_get_image(self, image_id):
            raise clientexception.NotFound()

        self.stubs.Set(client.Client, 'get_image', fake_get_image)

        data = tempfile.NamedTemporaryFile(mode="w+b")

        self.assertRaises(exception.ImageNotFound,
                          self.glanceimageservice_real.get, self.context,
                                               image_id=None, data=data)
        data.close()

    @attr(kind='small')
    def test_index_parameter(self):
        """Test for nova.image.glance.GlanceImageService.index.
        Verify just available image be returned"""

        def fake_get_images_detailed(client, **kwargs):
            self.assertEqual(6, kwargs['limit'])
            return [dict(id=1, name='img1', is_public=True, properties={}),
                dict(id=2, is_public=False, properties={}),
                dict(id=3, is_public=False, properties={'user_id':'fake'}),
                dict(id=4, is_public=False, properties={'user_id':'fake1'}),
                dict(id=5, is_public=False, properties={'project_id':'fake'}),
                dict(id=6, is_public=False, properties={'project_id':'fake1'})]

        self.stubs.Set(client.Client, 'get_images_detailed',
                       fake_get_images_detailed)

        kwargs = dict(filters=dict(), marker='marker', limit=6,
                      sort_key='sort_key', sort_dir='sort_dir')

        self.context.auth_token = False

        ref = self.glanceimageservice_real.index(self.context, **kwargs)

        self.assertEqual(3, len(ref))
        self.assertEqual(1, ref[0]['id'])
        self.assertEqual(3, ref[1]['id'])
        self.assertEqual(5, ref[2]['id'])

    @attr(kind='small')
    def test_index_exception(self):
        """Test for nova.image.glance.GlanceImageService.index.
        Raise ImagePaginationFailed if image id not be returned """

        def fake_get_images_detailed(self, **kwargs):
            return [dict()]

        self.stubs.Set(client.Client, 'get_images_detailed',
                       fake_get_images_detailed)

        kwargs = dict()

        self.assertRaises(exception.ImagePaginationFailed,
            self.glanceimageservice_real.index, self.context, **kwargs)

    @attr(kind='small')
    def test_show_exception_notfound(self):
        """Test for nova.image.glance.GlanceImageService.show.
        Raise ImageNotFound if image not exist"""

        def fake_get_image_meta(self, image_id):
            raise clientexception.NotFound

        self.stubs.Set(client.Client, 'get_image_meta', fake_get_image_meta)

        self.assertRaises(exception.ImageNotFound,
                self.glanceimageservice_real.show, self.context, image_id=None)

    @attr(kind='small')
    def test_show_exception_unavailable(self):
        """Test for nova.image.glance.GlanceImageService.show.
        Raise ImageNotFound if image is unavailable state"""

        def fake_get_image_meta(self, image_id):
            return dict(id=2, is_public=False, properties={})

        self.stubs.Set(client.Client, 'get_image_meta', fake_get_image_meta)

        self.context.auth_token = False

        self.assertRaises(exception.ImageNotFound,
                self.glanceimageservice_real.show, self.context, image_id=None)

    @attr(kind='small')
    def test_show_by_name_parameter(self):
        """Test for nova.image.glance.GlanceImageService.show_by_name.
        Verify return image that name is matching"""

        self.filter = False

        def fake_get_images_detailed(service, **kwargs):

            if 'name' in  kwargs['filters']:
                self.filter = True

            if 'marker' in kwargs and kwargs['marker']:
                return []
            else:
                return [dict(id=1, name='/image1')]

        self.stubs.Set(client.Client, 'get_images_detailed',
                       fake_get_images_detailed)

        ref = self.glanceimageservice_real.show_by_name(self.context,
                                                        name='/image1')

        self.assertEqual(1, ref['id'])
        self.assertEqual(True, self.filter)

    @attr(kind='small')
    def test_show_by_name_exception_notfound(self):
        """Test for nova.image.glance.GlanceImageService.show_by_name.
        Raise ImageNotFound if image not exist specified by name"""

        def fake_detail(self, context, **kwargs):
            return dict()

        self.stubs.Set(glance.GlanceImageService, 'detail', fake_detail)

        self.assertRaises(exception.ImageNotFound,
            self.glanceimageservice_real.show_by_name, self.context, name='/a')

    @attr(kind='small')
    def test_update_parameter(self):
        """Test for nova.image.glance.GlanceImageService.update.
        Verify metadate be updated"""

        self.meta = dict(size='10k', location='e', disk_format='ami',
                container_format='win0', checksum='250', id='2',
                name='n', created_at=None, updated_at=None,
                deleted_at=None, deleted=False, status='active',
                is_public=True,
                properties={'instance_id': '42', 'user_id': 'fake',
                            'project_id': None, 'architecture': 'x86',
                            'kernel_id': None, 'ramdisk_id': None,
                            'image_state': 'available'})

        def fake_show(self, context, image_id):
            pass

        self.stubs.Set(glance.GlanceImageService, 'show', fake_show)

        def fake_update_image(client, method, action,
                            body=None, headers=None, params=None):
            return self.meta

        self.stubs.Set(client.Client, 'update_image', fake_update_image)

        ref = self.glanceimageservice_real.update(self.context, image_id=2,
                                             image_meta=self.meta, data=None)
        self.assertEqual(self.meta, ref)

    @attr(kind='small')
    def test_update_exception(self):
        """Test for nova.image.glance.GlanceImageService.update.
        Raise ImageNotFound if update image not exist"""

        self.meta = dict(size='20k', name='n')

        def fake_show(self, context, image_id):
            raise exception.ImageNotFound

        self.stubs.Set(glance.GlanceImageService, 'show', fake_show)

        def fake_update_image(client, method, action,
                            body=None, headers=None, params=None):
            return self.meta

        self.stubs.Set(client.Client, 'update_image', fake_update_image)

        self.assertRaises(exception.ImageNotFound,
                self.glanceimageservice_real.update, self.context, image_id=1,
                        image_meta=self.meta, data=None)

    @attr(kind='small')
    def test_update_exception_notfound(self):
        """Test for nova.image.glance.GlanceImageService.update.
        Raise ImageNotFound if glance client raise NotFound exception"""

        self.meta = dict(size='20k', name='n')

        def fake_show(self, context, image_id):
            pass

        self.stubs.Set(glance.GlanceImageService, 'show', fake_show)

        def fake_update_image(client, method, action,
                            body=None, headers=None, params=None):
            raise clientexception.NotFound

        self.stubs.Set(client.Client, 'update_image', fake_update_image)

        self.assertRaises(exception.ImageNotFound,
                self.glanceimageservice_real.update, self.context, image_id=1,
                        image_meta=self.meta, data=None)

    @attr(kind='small')
    def test_update_exception_dateformat(self):
        """Test for nova.image.glance.GlanceImageService.update.
        Raise ValueError if glance client return a non-iso format datetime"""

        self.meta = dict(size='20k', name='n', updated_at='2011/11/11')

        def fake_show(self, context, image_id):
            pass

        self.stubs.Set(glance.GlanceImageService, 'show', fake_show)

        def fake_update_image(client, method, action,
                            body=None, headers=None, params=None):
            return self.meta

        self.stubs.Set(client.Client, 'update_image', fake_update_image)

        self.assertRaises(ValueError,
                self.glanceimageservice_real.update, self.context, image_id=1,
                        image_meta=self.meta, data=None)
