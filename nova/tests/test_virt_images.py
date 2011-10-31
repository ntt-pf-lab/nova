# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 NTT
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import os
import datetime
from nose.plugins.attrib import attr
from nova import image
from nova.image import glance
from nova.virt import images as virt_images
from nova import context
from nova import test
from nova import exception
from nova import utils
from nova import flags

FLAGS = flags.FLAGS


def _fake_get_glance_client(context, image_href):
    """nova.image.glance.get_glance_client() include bug(#198)"""

    image_href = image_href or 0
    if str(image_href).isdigit():
        glance_host, glance_port = glance.pick_glance_api_server()
        glance_client = glance._create_glance_client(context, glance_host,
                                              glance_port)
        return (glance_client, int(image_href))

    try:
        (image_id, host, port) = glance._parse_image_ref(image_href)
    except ValueError:
        raise exception.InvalidImageRef(image_href=image_href)
    glance_client = glance._create_glance_client(context, host, port)
    return (glance_client, image_id)


class VirtImagesTestCase(test.TestCase):
    def setUp(self):
        super(VirtImagesTestCase, self).setUp()
#        glance_stubs.stubout_glance_client(self.stubs)

        self.user_id = 'fake'
        self.project_id = 'fake'
        self.context = context.RequestContext(self.user_id, self.project_id)

        # nova.image.glance.get_glance_client include bug(#198)
        self.stubs.Set(glance, 'get_glance_client',
                       _fake_get_glance_client)

    @attr(kind='small')
    def test_fetch(self):
        """ Ensure return metadata and writes data
            when image_href is href"""

        def stub_get(self, context, image_id, data):
            data.write('test chunk')
            return {'id': '1',
                    'name': 'fakeimage1'}

        self.stubs.Set(glance.GlanceImageService, 'get', stub_get)

        image1 = {'id': '1',
                 'name': 'fakeimage1'}

        # parameter
        image_href = 'http://fakeserver:9292/images/1'
        path = '/tmp/virt_images.part'
        self.assertFalse(os.path.exists(path))

        metadata = virt_images.fetch(self.context, image_href, path,
                                   self.user_id, self.project_id)

        self.assertEqual(image1, metadata)
        self.assert_(os.path.exists(path))
        with open(path, 'r') as f:
            self.assertEqual('test chunk', f.read())
        os.remove(path)

    @attr(kind='small')
    def test_fetch_parameter_image_href_is_id(self):
        """ Ensure return metadata and writes data
            when image_href is id"""

        # metadata(nova.image.fake.FakeImageService)
        timestamp = datetime.datetime(2011, 01, 01, 01, 02, 03)
        image1 = {'id': '123456',
                 'name': 'fakeimage123456',
                 'created_at': timestamp,
                 'updated_at': timestamp,
                 'deleted_at': None,
                 'deleted': False,
                 'status': 'active',
                 'is_public': False,
                 'properties': {'kernel_id': FLAGS.null_kernel,
                                'ramdisk_id': FLAGS.null_kernel,
                                'architecture': 'x86_64'}}

        # parameter
        image_href = 123456
        path = '/tmp/virt_images.part'
        self.assertFalse(os.path.exists(path))

        metadata = virt_images.fetch(self.context, image_href, path,
                                   self.user_id, self.project_id)

        self.assertEqual(image1, metadata)
        self.assert_(os.path.exists(path))
        with open(path, 'r') as f:
            self.assertEqual('fake chunk', f.read())
        os.remove(path)

    @attr(kind='small')
    def test_fetch_parameter_image_href_invalid(self):
        """ Ensure exception.InvalidImageRef
            when href is invalid strings"""

        image_href = 'httpfakeserver9292images1'
        path = '/tmp/virt_images.part'

        self.assertRaises(exception.InvalidImageRef,
                          virt_images.fetch,
                          self.context, image_href, path,
                          self.user_id, self.project_id)

    @attr(kind='small')
    def test_fetch_parameter_image_href_empty(self):
        """ Ensure exception.ImageNotFound
            when href is empty(or none)"""

        image_href = ''
        path = '/tmp/virt_images.part'
        self.assertFalse(os.path.exists(path))

        self.assertRaises(exception.ImageNotFound,
                          virt_images.fetch,
                          self.context, image_href, path,
                          self.user_id, self.project_id)

        self.assert_(os.path.exists(path))
        os.remove(path)

    @attr(kind='small')
    def test_fetch_parameter_path_empty(self):
        """ Ensure IOError when path is empty"""

        image_href = 123456
        path = ''

        # No such file or directory
        self.assertRaises(IOError,
                          virt_images.fetch,
                          self.context, image_href, path,
                          self.user_id, self.project_id)

    @attr(kind='small')
    def test_fetch_to_raw(self):
        """ Ensure return metadata and rename data
            when file format is raw"""

        def stub_utils_execute(*cmd, **kwargs):
            return 'file format:raw', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        # metadata(nova.image.fake.FakeImageService)
        timestamp = datetime.datetime(2011, 01, 01, 01, 02, 03)
        image1 = {'id': '123456',
                 'name': 'fakeimage123456',
                 'created_at': timestamp,
                 'updated_at': timestamp,
                 'deleted_at': None,
                 'deleted': False,
                 'status': 'active',
                 'is_public': False,
                 'properties': {'kernel_id': FLAGS.null_kernel,
                                'ramdisk_id': FLAGS.null_kernel,
                                'architecture': 'x86_64'}}

        # parameter
        image_href = 123456
        path = '/tmp/virt_images'

        self.assertFalse(os.path.exists("%s.part" % path))

        # file format=raw
        metadata = virt_images.fetch_to_raw(self.context, image_href, path,
                                   self.user_id, self.project_id)

        # Ensure return value
        self.assertEqual(image1, metadata)

        # Ensure file
        self.assertFalse(os.path.exists("%s.part" % path))
        self.assert_(os.path.exists(path))
        os.remove(path)

    @attr(kind='small')
    def test_fetch_to_raw_configuration_not_include_fileformat_in_qemu_info(self):
        """ Ensure exception.ImageUnacceptable
            when not include file_format in qemu_image_info"""

        def stub_utils_execute(*cmd, **kwargs):
            return 'format:raw', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        # parameter
        image_href = 123456
        path = '/tmp/virt_images'

        self.assertFalse(os.path.exists("%s.part" % path))

        # Ensure raise exception.ImageUnacceptable
        self.assertRaises(exception.ImageUnacceptable,
                          virt_images.fetch_to_raw,
                          self.context, image_href, path,
                          self.user_id, self.project_id)

        # Ensure file
        self.assertFalse(os.path.exists("%s.part" % path))
        self.assertFalse(os.path.exists(path))

    @attr(kind='small')
    def test_fetch_to_raw_configuration_trim_space(self):
        """ Ensure return metadata and rename data
            when file format is raw"""

        def stub_utils_execute(*cmd, **kwargs):
            # return value:space + raw => ' raw'
            return 'file format: raw', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        # metadata(nova.image.fake.FakeImageService)
        timestamp = datetime.datetime(2011, 01, 01, 01, 02, 03)
        image1 = {'id': '123456',
                 'name': 'fakeimage123456',
                 'created_at': timestamp,
                 'updated_at': timestamp,
                 'deleted_at': None,
                 'deleted': False,
                 'status': 'active',
                 'is_public': False,
                 'properties': {'kernel_id': FLAGS.null_kernel,
                                'ramdisk_id': FLAGS.null_kernel,
                                'architecture': 'x86_64'}}

        # parameter
        image_href = 123456
        path = '/tmp/virt_images'
        self.assertFalse(os.path.exists("%s.part" % path))

        # file format=raw
        metadata = virt_images.fetch_to_raw(self.context, image_href, path,
                                   self.user_id, self.project_id)

        # Ensure return value
        self.assertEqual(image1, metadata)

        # Ensure file
        self.assertFalse(os.path.exists("%s.part" % path))
        self.assert_(os.path.exists(path))
        os.remove(path)

    @attr(kind='small')
    def test_fetch_to_raw_configuration_fileformat_qcow(self):
        """ Ensure return metadata, convert to raw and rename data
            when file format is not raw(qcow)"""

        self.convert_flag = False

        def stub_utils_execute(*cmd, **kwargs):
            if cmd[4] == 'info' and cmd[5] == '/tmp/virt_images.part':
                return 'file format:qcow', 0
            elif cmd[1] == 'convert':
                with open('/tmp/virt_images.converted', 'w') as f:
                    f.write('fake')
                self.convert_flag = True
                return 'fake convert', 0
            elif cmd[4] == 'info' and cmd[5] == '/tmp/virt_images.converted':
                return 'file format:raw', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        # metadata(nova.image.fake.FakeImageService)
        timestamp = datetime.datetime(2011, 01, 01, 01, 02, 03)
        image1 = {'id': '123456',
                 'name': 'fakeimage123456',
                 'created_at': timestamp,
                 'updated_at': timestamp,
                 'deleted_at': None,
                 'deleted': False,
                 'status': 'active',
                 'is_public': False,
                 'properties': {'kernel_id': FLAGS.null_kernel,
                                'ramdisk_id': FLAGS.null_kernel,
                                'architecture': 'x86_64'}}

        # parameter
        image_href = 123456
        path = '/tmp/virt_images'
        self.assertFalse(os.path.exists("%s.part" % path))

        # file format=qcow
        metadata = virt_images.fetch_to_raw(self.context, image_href, path,
                                            self.user_id, self.project_id)

        # Ensure return value
        self.assertEqual(image1, metadata)

        # Ensure exec convert command
        self.assert_(self.convert_flag)

        # Ensure file
        self.assertFalse(os.path.exists("%s.part" % path))
        self.assertFalse(os.path.exists("%s.converted" % path))
        self.assert_(os.path.exists(path))
        os.remove(path)

    @attr(kind='small')
    def test_fetch_to_raw_configuration_backing_file(self):
        """ Ensure exception.ImageUnacceptable
            when include backing file in qemu_image_info"""

        def stub_utils_execute(*cmd, **kwargs):
            return ('file format:backing file\n'
                    'backing file:true'), 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        # parameter
        image_href = 123456
        path = '/tmp/virt_images'
        self.assertFalse(os.path.exists("%s.part" % path))

        # file format=qcow
        self.assertRaises(exception.ImageUnacceptable,
                          virt_images.fetch_to_raw, self.context,
                          image_href, path,
                          self.user_id, self.project_id)

        # Ensure file
        self.assertFalse(os.path.exists("%s.part" % path))

    @attr(kind='small')
    def test_fetch_to_raw_configuration_convert_fail(self):
        """ Ensure exception.ImageUnacceptable
            when file convert failed"""

        self.convert_flag = False

        def stub_utils_execute(*cmd, **kwargs):
            if cmd[4] == 'info':
                return 'file format:qcow', 0
            elif cmd[1] == 'convert':
                with open('/tmp/virt_images.converted', 'w') as f:
                    f.write('fake')
                self.convert_flag = True
                return 'fake convert', 0

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        # parameter
        image_href = 123456
        path = '/tmp/virt_images'
        self.assertFalse(os.path.exists("%s.part" % path))

        # file format=qcow
        self.assertRaises(exception.ImageUnacceptable,
                          virt_images.fetch_to_raw, self.context,
                          image_href, path,
                          self.user_id, self.project_id)

        # Ensure exec convert command
        self.assert_(self.convert_flag)

        # Ensure file
        self.assertFalse(os.path.exists("%s.part" % path))
        self.assertFalse(os.path.exists("%s.converted" % path))

    @attr(kind='small')
    def test_fetch_to_raw_exception_command_failed(self):
        """ Ensure raise exception when command failed"""

        def stub_utils_execute(*cmd, **kwargs):
            if cmd[4] == 'info':
                return 'file format:qcow', 0
            elif cmd[1] == 'convert':
                raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', stub_utils_execute)

        # parameter
        image_href = 123456
        path = '/tmp/virt_images'
        self.assertFalse(os.path.exists("%s.part" % path))

        self.assertRaises(exception.ProcessExecutionError,
                          virt_images.fetch_to_raw, self.context,
                          image_href, path,
                          self.user_id, self.project_id)

        # Ensure file
        self.assert_(os.path.exists("%s.part" % path))
        os.remove("%s.part" % path)
