# vim: tabstop=4 shiftwidth=4 softtabstop=4

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
"""
Tests For nova.virt.disk
"""

import os

from nova import exception
from nova import flags
from nova import test
from nova import utils
from nova.virt import disk

from nose.plugins.attrib import attr
from nose.plugins.skip import SkipTest

FLAGS = flags.FLAGS


class DiskTestCase(test.TestCase):
    """Test for nova.virt.disk."""
    def setUp(self):
        super(DiskTestCase, self).setUp()
        self.disk = disk

    def _create_file(self, file_name, size=1):
        dir_name = os.path.dirname(file_name)
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)

        with open(file_name, 'w') as f:
            f.seek(size - 1)
            f.write('\0')

    def _remove_file(self, file_name):
        try:
            os.remove(file_name)
            dir_name = os.path.dirname(file_name)
            os.removedirs(dir_name)
        except Exception:
            pass

    @attr(kind='small')
    def test_mkfs(self):
        """Test for nova.virt.disk.mkfs."""
        self._execute_mkfs_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mkfs.ext3':
                self._execute_mkfs_count += 1

        self.stubs.Set(utils, 'execute', stub_execute)

        os_type = 'linux'
        self.disk.mkfs(os_type, None, None)
        self.assertEqual(1, self._execute_mkfs_count)

    @attr(kind='small')
    def test_mkfs_cfg_not_mkfs_command(self):
        """Test for nova.virt.disk.mkfs."""
        # setup
        before_default_mkfs_command = self.disk._DEFAULT_MKFS_COMMAND
        self.disk._DEFAULT_MKFS_COMMAND = None

        self._execute_count = 0

        def stub_execute(*cmd, **kwargs):
            self._execute_count += 1

        self.stubs.Set(utils, 'execute', stub_execute)

        os_type = 'unexpected_os_type'
        self.disk.mkfs(os_type, None, None)
        self.assertEqual(0, self._execute_count)

        # teardown
        self.disk._DEFAULT_MKFS_COMMAND = before_default_mkfs_command

    @attr(kind='small')
    def test_mkfs_ex_execute_mkfs_command(self):
        """Test for nova.virt.disk.mkfs."""
        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mkfs.ext3':
                raise exception.ProcessExecutionError()

        self.stubs.Set(utils, 'execute', stub_execute)

        os_type = 'linux'
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.mkfs,
                          os_type, None, None)

    @attr(kind='small')
    def test_extend(self):
        """Test for nova.virt.disk.extend."""
        self._execute_qemu_img_count = 0
        self._execute_e2fsck_count = 0
        self._execute_resize2fs_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'qemu-img':
                self._execute_qemu_img_count += 1
            if cmd[0] == 'e2fsck':
                self._execute_e2fsck_count += 1
            if cmd[0] == 'resize2fs':
                self._execute_resize2fs_count += 1

        self.stubs.Set(utils, 'execute', stub_execute)

        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        image_path = os.path.join(temp_dir, 'image.iso')
        # create dummy image
        self._create_file(image_path, 10)
        size = 20
        self.disk.extend(image_path, size)
        self.assertEqual(1, self._execute_qemu_img_count)
        self.assertEqual(1, self._execute_e2fsck_count)
        self.assertEqual(1, self._execute_resize2fs_count)

        # remove file and directory for test
        self._remove_file(image_path)

    @attr(kind='small')
    def test_extend_param_file_size_is_grater_than_or_equal_size(self):
        """Test for nova.virt.disk.extend."""
        self._execute_qemu_img_count = 0
        self._execute_e2fsck_count = 0
        self._execute_resize2fs_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'qemu-img':
                self._execute_qemu_img_count += 1
            if cmd[0] == 'e2fsck':
                self._execute_e2fsck_count += 1
            if cmd[0] == 'resize2fs':
                self._execute_resize2fs_count += 1

        self.stubs.Set(utils, 'execute', stub_execute)

        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        image_path = os.path.join(temp_dir, 'image.iso')
        # create dummy image
        self._create_file(image_path, 10)
        size = 10
        self.disk.extend(image_path, size)
        self.assertEqual(0, self._execute_qemu_img_count)
        self.assertEqual(0, self._execute_e2fsck_count)
        self.assertEqual(0, self._execute_resize2fs_count)

        # remove file and directory for test
        self._remove_file(image_path)

    @attr(kind='small')
    def test_extend_ex_os_path_getsize(self):
        """Test for nova.virt.disk.extend."""
        raise SkipTest("OSError is raised,\
                        but ProcessExecutionError should be raised.")
        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        image_path = os.path.join(temp_dir, 'image.iso')
        size = 10
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.extend,
                          image_path, size)

    @attr(kind='small')
    def test_extend_ex_execute_qemu_img(self):
        """Test for nova.virt.disk.extend."""
        self._execute_qemu_img_count = 0
        self._execute_e2fsck_count = 0
        self._execute_resize2fs_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'qemu-img':
                self._execute_qemu_img_count += 1
                raise exception.ProcessExecutionError()
            if cmd[0] == 'e2fsck':
                self._execute_e2fsck_count += 1
            if cmd[0] == 'resize2fs':
                self._execute_resize2fs_count += 1

        self.stubs.Set(utils, 'execute', stub_execute)

        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        image_path = os.path.join(temp_dir, 'image.iso')
        # create dummy image
        self._create_file(image_path, 10)
        size = 20
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.extend,
                          image_path, size)
        self.assertEqual(1, self._execute_qemu_img_count)
        self.assertEqual(0, self._execute_e2fsck_count)
        self.assertEqual(0, self._execute_resize2fs_count)

        # remove file and directory for test
        self._remove_file(image_path)

    @attr(kind='small')
    def test_extend_ex_execute_e2fsck(self):
        """Test for nova.virt.disk.extend."""
        self._execute_qemu_img_count = 0
        self._execute_e2fsck_count = 0
        self._execute_resize2fs_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'qemu-img':
                self._execute_qemu_img_count += 1
            if cmd[0] == 'e2fsck':
                self._execute_e2fsck_count += 1
                raise exception.ProcessExecutionError()
            if cmd[0] == 'resize2fs':
                self._execute_resize2fs_count += 1

        self.stubs.Set(utils, 'execute', stub_execute)

        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        image_path = os.path.join(temp_dir, 'image.iso')
        # create dummy image
        self._create_file(image_path, 10)
        size = 20
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.extend,
                          image_path, size)
        self.assertEqual(1, self._execute_qemu_img_count)
        self.assertEqual(1, self._execute_e2fsck_count)
        self.assertEqual(0, self._execute_resize2fs_count)

        # remove file and directory for test
        self._remove_file(image_path)

    @attr(kind='small')
    def test_extend_ex_execute_resize2fs(self):
        """Test for nova.virt.disk.extend."""
        self._execute_qemu_img_count = 0
        self._execute_e2fsck_count = 0
        self._execute_resize2fs_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'qemu-img':
                self._execute_qemu_img_count += 1
            if cmd[0] == 'e2fsck':
                self._execute_e2fsck_count += 1
            if cmd[0] == 'resize2fs':
                self._execute_resize2fs_count += 1
                raise exception.ProcessExecutionError()

        self.stubs.Set(utils, 'execute', stub_execute)

        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        image_path = os.path.join(temp_dir, 'image.iso')
        # create dummy image
        self._create_file(image_path, 10)
        size = 20
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.extend,
                          image_path, size)
        self.assertEqual(1, self._execute_qemu_img_count)
        self.assertEqual(1, self._execute_e2fsck_count)
        self.assertEqual(1, self._execute_resize2fs_count)

        # remove file and directory for test
        self._remove_file(image_path)

    @attr(kind='small')
    def test_inject_data(self):
        """Test for nova.virt.disk.inject_data."""
        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        link_device = os.path.join(temp_dir, 'dev/nbd0')
        self._execute_mount_count = 0
        self._execute_umount_count = 0
        self._execute_rmdir_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mount':
                self._execute_mount_count += 1
                return None, None
            if cmd[0] == 'umount':
                self._execute_umount_count += 1
            if cmd[0] == 'rmdir':
                self._execute_rmdir_count += 1

        def stub_link_device(image, nbd):
            return link_device

        def stub_inject_data_into_fs(fs, key, net, metadata, execute):
            pass

        def stub_unlink_device(device, nbd):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)
        self.stubs.Set(self.disk, 'inject_data_into_fs',
                       stub_inject_data_into_fs)
        self.stubs.Set(self.disk, '_unlink_device', stub_unlink_device)

        # create dummy mapped_device
        self._create_file(link_device)
        image = None
        key = None
        net = None
        metadata = None
        partition = None
        nbd = False
        tune2fs = False
        self.disk.inject_data(image, key, net, metadata,
                              partition, nbd, tune2fs)
        self.assertEqual(1, self._execute_mount_count)
        self.assertEqual(1, self._execute_umount_count)
        self.assertEqual(1, self._execute_rmdir_count)

        # remove file and directory for test
        self._remove_file(link_device)

    @attr(kind='small')
    def test_inject_data_param_tune2fs(self):
        """Test for nova.virt.disk.inject_data."""
        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        link_device = os.path.join(temp_dir, 'dev/nbd0')
        self._execute_tune2fs_count = 0
        self._execute_mount_count = 0
        self._execute_umount_count = 0
        self._execute_rmdir_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'tune2fs':
                self._execute_tune2fs_count += 1
                return None, None
            if cmd[0] == 'mount':
                self._execute_mount_count += 1
                return None, None
            if cmd[0] == 'umount':
                self._execute_umount_count += 1
            if cmd[0] == 'rmdir':
                self._execute_rmdir_count += 1

        def stub_link_device(image, nbd):
            return link_device

        def stub_unlink_device(device, nbd):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)
        self.stubs.Set(self.disk, '_unlink_device', stub_unlink_device)

        # create dummy mapped_device
        self._create_file(link_device)
        image = None
        key = None
        net = None
        metadata = None
        partition = None
        nbd = False
        tune2fs = True
        self.disk.inject_data(image, key, net, metadata,
                              partition, nbd, tune2fs)
        self.assertEqual(1, self._execute_tune2fs_count)
        self.assertEqual(1, self._execute_mount_count)
        self.assertEqual(1, self._execute_umount_count)
        self.assertEqual(1, self._execute_rmdir_count)

        # remove file and directory for test
        self._remove_file(link_device)

    @attr(kind='small')
    def test_inject_data_cfg_mapped_device_does_not_exist(self):
        """Test for nova.virt.disk.inject_data."""
        raise SkipTest("Error is raised,\
                        but ProcessExecutionError should be raised.")
        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        link_device = os.path.join(temp_dir, 'dev/nbd0')
        self._execute_kpartx_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'kpartx':
                self._execute_kpartx_count += 1
                return None, None

        def stub_link_device(image, nbd):
            return link_device

        def stub_unlink_device(device, nbd):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)
        self.stubs.Set(self.disk, '_unlink_device', stub_unlink_device)

        image = None
        key = None
        net = None
        metadata = None
        partition = 1
        nbd = False
        tune2fs = False
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data,
                          image, key, net, metadata,
                          partition, nbd, tune2fs)
        self.assertEqual(2, self._execute_kpartx_count)

    @attr(kind='small')
    def test_inject_data_ex_link_device(self):
        """Test for nova.virt.disk.inject_data."""
        def stub_link_device(image, nbd):
            raise exception.ProcessExecutionError()

        self.stubs.Set(self.disk, '_link_device', stub_link_device)

        image = None
        key = None
        net = None
        metadata = None
        partition = None
        nbd = False
        tune2fs = False
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data,
                          image, key, net, metadata,
                          partition, nbd, tune2fs)

    @attr(kind='small')
    def test_inject_data_ex_execute_kpartx_stderr(self):
        """Test for nova.virt.disk.inject_data."""
        raise SkipTest("Error is raised,\
                        but ProcessExecutionError should be raised.")
        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        link_device = os.path.join(temp_dir, 'dev/nbd0')
        self._execute_kpartx_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'kpartx':
                self._execute_kpartx_count += 1
                return None, 'Error'

        def stub_link_device(image, nbd):
            return link_device

        def stub_unlink_device(device, nbd):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)
        self.stubs.Set(self.disk, '_unlink_device', stub_unlink_device)

        image = None
        key = None
        net = None
        metadata = None
        partition = 1
        nbd = False
        tune2fs = False
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data,
                          image, key, net, metadata,
                          partition, nbd, tune2fs)
        self.assertEqual(1, self._execute_kpartx_count)

    @attr(kind='small')
    def test_inject_data_ex_execute_kpartx(self):
        """Test for nova.virt.disk.inject_data."""
        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        link_device = os.path.join(temp_dir, 'dev/nbd0')
        self._execute_kpartx_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'kpartx':
                self._execute_kpartx_count += 1
                raise exception.ProcessExecutionError()

        def stub_link_device(image, nbd):
            return link_device

        def stub_unlink_device(device, nbd):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)
        self.stubs.Set(self.disk, '_unlink_device', stub_unlink_device)

        image = None
        key = None
        net = None
        metadata = None
        partition = 1
        nbd = False
        tune2fs = False
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data,
                          image, key, net, metadata,
                          partition, nbd, tune2fs)
        self.assertEqual(1, self._execute_kpartx_count)

    @attr(kind='small')
    def test_inject_data_ex_execute_tune2fs_stderr(self):
        """Test for nova.virt.disk.inject_data."""
        raise SkipTest("Exception is not raised,\
                        when err is out by utils.execute('mount', ...).")
        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        link_device = os.path.join(temp_dir, 'dev/nbd0')
        self._execute_tune2fs_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'tune2fs':
                self._execute_tune2fs_count += 1
                return None, 'Error'

        def stub_link_device(image, nbd):
            return link_device

        def stub_unlink_device(device, nbd):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)
        self.stubs.Set(self.disk, '_unlink_device', stub_unlink_device)

        # create dummy mapped_device
        self._create_file(link_device)
        image = None
        key = None
        net = None
        metadata = None
        partition = None
        nbd = False
        tune2fs = True
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data,
                          image, key, net, metadata,
                          partition, nbd, tune2fs)
        self.assertEqual(1, self._execute_tune2fs_count)

        # remove file and directory for test
        self._remove_file(link_device)

    @attr(kind='small')
    def test_inject_data_ex_execute_tune2fs(self):
        """Test for nova.virt.disk.inject_data."""
        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        link_device = os.path.join(temp_dir, 'dev/nbd0')
        self._execute_tune2fs_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'tune2fs':
                self._execute_tune2fs_count += 1
                raise exception.ProcessExecutionError()

        def stub_link_device(image, nbd):
            return link_device

        def stub_unlink_device(device, nbd):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)
        self.stubs.Set(self.disk, '_unlink_device', stub_unlink_device)

        # create dummy mapped_device
        self._create_file(link_device)
        image = None
        key = None
        net = None
        metadata = None
        partition = None
        nbd = False
        tune2fs = True
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data,
                          image, key, net, metadata,
                          partition, nbd, tune2fs)
        self.assertEqual(1, self._execute_tune2fs_count)

        # remove file and directory for test
        self._remove_file(link_device)

    @attr(kind='small')
    def test_inject_data_ex_execute_mount_stderr(self):
        """Test for nova.virt.disk.inject_data."""
        raise SkipTest("Error is raised,\
                        but ProcessExecutionError should be raised.")
        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        link_device = os.path.join(temp_dir, 'dev/nbd0')
        self._execute_mount_count = 0
        self._execute_rmdir_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mount':
                self._execute_mount_count += 1
                return None, 'Error'
            if cmd[0] == 'rmdir':
                self._execute_rmdir_count += 1

        def stub_link_device(image, nbd):
            return link_device

        def stub_unlink_device(device, nbd):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)
        self.stubs.Set(self.disk, '_unlink_device', stub_unlink_device)

        # create dummy mapped_device
        self._create_file(link_device)
        image = None
        key = None
        net = None
        metadata = None
        partition = None
        nbd = False
        tune2fs = False
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data,
                          image, key, net, metadata,
                          partition, nbd, tune2fs)
        self.assertEqual(1, self._execute_mount_count)
        self.assertEqual(1, self._execute_rmdir_count)

        # remove file and directory for test
        self._remove_file(link_device)

    @attr(kind='small')
    def test_inject_data_ex_execute_mount(self):
        """Test for nova.virt.disk.inject_data."""
        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        link_device = os.path.join(temp_dir, 'dev/nbd0')
        self._execute_mount_count = 0
        self._execute_rmdir_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mount':
                self._execute_mount_count += 1
                raise exception.ProcessExecutionError()
            if cmd[0] == 'rmdir':
                self._execute_rmdir_count += 1

        def stub_link_device(image, nbd):
            return link_device

        def stub_unlink_device(device, nbd):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)
        self.stubs.Set(self.disk, '_unlink_device', stub_unlink_device)

        # create dummy mapped_device
        self._create_file(link_device)
        image = None
        key = None
        net = None
        metadata = None
        partition = None
        nbd = False
        tune2fs = False
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data,
                          image, key, net, metadata,
                          partition, nbd, tune2fs)
        self.assertEqual(1, self._execute_mount_count)
        self.assertEqual(1, self._execute_rmdir_count)

        # remove file and directory for test
        self._remove_file(link_device)

    @attr(kind='small')
    def test_inject_data_ex_inject_data_into_fs(self):
        """Test for nova.virt.disk.inject_data."""
        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        link_device = os.path.join(temp_dir, 'dev/nbd0')
        self._execute_mount_count = 0
        self._execute_umount_count = 0
        self._execute_rmdir_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mount':
                self._execute_mount_count += 1
                return None, None
            if cmd[0] == 'umount':
                self._execute_umount_count += 1
            if cmd[0] == 'rmdir':
                self._execute_rmdir_count += 1

        def stub_link_device(image, nbd):
            return link_device

        def stub_inject_data_into_fs(fs, key, net, metadata, execute):
            raise exception.ProcessExecutionError()

        def stub_unlink_device(device, nbd):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)
        self.stubs.Set(self.disk, 'inject_data_into_fs',
                       stub_inject_data_into_fs)
        self.stubs.Set(self.disk, '_unlink_device', stub_unlink_device)

        # create dummy mapped_device
        self._create_file(link_device)
        image = None
        key = None
        net = None
        metadata = None
        partition = None
        nbd = False
        tune2fs = False
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data,
                          image, key, net, metadata,
                          partition, nbd, tune2fs)
        self.assertEqual(1, self._execute_mount_count)
        self.assertEqual(1, self._execute_umount_count)
        self.assertEqual(1, self._execute_rmdir_count)

        # remove file and directory for test
        self._remove_file(link_device)

    @attr(kind='small')
    def test_inject_data_ex_execute_umount(self):
        """Test for nova.virt.disk.inject_data."""
        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        link_device = os.path.join(temp_dir, 'dev/nbd0')
        self._execute_mount_count = 0
        self._execute_umount_count = 0
        self._execute_rmdir_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mount':
                self._execute_mount_count += 1
                return None, None
            if cmd[0] == 'umount':
                self._execute_umount_count += 1
                raise exception.ProcessExecutionError()
            if cmd[0] == 'rmdir':
                self._execute_rmdir_count += 1

        def stub_link_device(image, nbd):
            return link_device

        def stub_unlink_device(device, nbd):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)
        self.stubs.Set(self.disk, '_unlink_device', stub_unlink_device)

        # create dummy mapped_device
        self._create_file(link_device)
        image = None
        key = None
        net = None
        metadata = None
        partition = None
        nbd = False
        tune2fs = False
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data,
                          image, key, net, metadata,
                          partition, nbd, tune2fs)
        self.assertEqual(1, self._execute_mount_count)
        self.assertEqual(1, self._execute_umount_count)
        self.assertEqual(1, self._execute_rmdir_count)

        # remove file and directory for test
        self._remove_file(link_device)

    @attr(kind='small')
    def test_inject_data_ex_execute_rmdir(self):
        """Test for nova.virt.disk.inject_data."""
        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        link_device = os.path.join(temp_dir, 'dev/nbd0')
        self._execute_mount_count = 0
        self._execute_umount_count = 0
        self._execute_rmdir_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mount':
                self._execute_mount_count += 1
                return None, None
            if cmd[0] == 'umount':
                self._execute_umount_count += 1
            if cmd[0] == 'rmdir':
                self._execute_rmdir_count += 1
                raise exception.ProcessExecutionError()

        def stub_link_device(image, nbd):
            return link_device

        def stub_unlink_device(device, nbd):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)
        self.stubs.Set(self.disk, '_unlink_device', stub_unlink_device)

        # create dummy mapped_device
        self._create_file(link_device)
        image = None
        key = None
        net = None
        metadata = None
        partition = None
        nbd = False
        tune2fs = False
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data,
                          image, key, net, metadata,
                          partition, nbd, tune2fs)
        self.assertEqual(1, self._execute_mount_count)
        self.assertEqual(1, self._execute_umount_count)
        self.assertEqual(1, self._execute_rmdir_count)

        # remove file and directory for test
        self._remove_file(link_device)

    @attr(kind='small')
    def test_inject_data_ex_finally_execute_kpartx(self):
        """Test for nova.virt.disk.inject_data."""
        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        link_device = os.path.join(temp_dir, 'dev/nbd0')
        self._execute_kpartx_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'kpartx':
                self._execute_kpartx_count += 1
                if self._execute_kpartx_count == 1:
                    return None, None
                if self._execute_kpartx_count == 2:
                    raise exception.ProcessExecutionError()

        def stub_link_device(image, nbd):
            return link_device

        def stub_unlink_device(device, nbd):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)
        self.stubs.Set(self.disk, '_unlink_device', stub_unlink_device)

        image = None
        key = None
        net = None
        metadata = None
        partition = 1
        nbd = False
        tune2fs = False
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data,
                          image, key, net, metadata,
                          partition, nbd, tune2fs)
        self.assertEqual(2, self._execute_kpartx_count)

    @attr(kind='small')
    def test_inject_data_ex_unlink_device(self):
        """Test for nova.virt.disk.inject_data."""
        temp_dir = os.path.join(os.getcwd(), 'virt_disk')
        link_device = os.path.join(temp_dir, 'dev/nbd0')
        self._execute_mount_count = 0
        self._execute_umount_count = 0
        self._execute_rmdir_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mount':
                self._execute_mount_count += 1
                return None, None
            if cmd[0] == 'umount':
                self._execute_umount_count += 1
            if cmd[0] == 'rmdir':
                self._execute_rmdir_count += 1

        def stub_link_device(image, nbd):
            return link_device

        def stub_unlink_device(device, nbd):
            raise exception.ProcessExecutionError()

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)
        self.stubs.Set(self.disk, '_unlink_device', stub_unlink_device)

        # create dummy mapped_device
        self._create_file(link_device)
        image = None
        key = None
        net = None
        metadata = None
        partition = None
        nbd = False
        tune2fs = False
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data,
                          image, key, net, metadata,
                          partition, nbd, tune2fs)
        self.assertEqual(1, self._execute_mount_count)
        self.assertEqual(1, self._execute_umount_count)
        self.assertEqual(1, self._execute_rmdir_count)

        # remove file and directory for test
        self._remove_file(link_device)

    @attr(kind='small')
    def test_setup_container(self):
        """Test for nova.virt.disk.setup_container."""
        self._execute_mount_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mount':
                self._execute_mount_count += 1

        def stub_link_device(image, nbd):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)

        image = None
        container_dir = None
        nbd = False
        self.disk.setup_container(image, container_dir, nbd)
        self.assertEqual(1, self._execute_mount_count)

    @attr(kind='small')
    def test_setup_container_param_unlink_device_nbd_is_true(self):
        """Test for nova.virt.disk.setup_container."""
        self._execute_mount_count = 0
        self._execute_qemu_nbd_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mount':
                self._execute_mount_count += 1
                raise exception.ProcessExecutionError()
            if cmd[0] == 'qemu-nbd':
                self._execute_qemu_nbd_count += 1

        def stub_link_device(image, nbd):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)

        image = None
        container_dir = None
        nbd = True
        self.disk.setup_container(image, container_dir, nbd)
        self.assertEqual(1, self._execute_mount_count)
        self.assertEqual(1, self._execute_qemu_nbd_count)

    @attr(kind='small')
    def test_setup_container_param_unlink_device_nbd_is_false(self):
        """Test for nova.virt.disk.setup_container."""
        self._execute_mount_count = 0
        self._execute_losetup_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mount':
                self._execute_mount_count += 1
                raise exception.ProcessExecutionError()
            if cmd[0] == 'losetup':
                self._execute_losetup_count += 1

        def stub_link_device(image, nbd):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)

        image = None
        container_dir = None
        nbd = False
        self.disk.setup_container(image, container_dir, nbd)
        self.assertEqual(1, self._execute_mount_count)
        self.assertEqual(1, self._execute_losetup_count)

    @attr(kind='small')
    def test_setup_container_ex_link_device(self):
        """Test for nova.virt.disk.setup_container."""
        self._execute_losetup_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'losetup':
                self._execute_losetup_count += 1

        def stub_link_device(image, nbd):
            raise exception.ProcessExecutionError()

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)

        image = None
        container_dir = None
        nbd = False
        self.disk.setup_container(image, container_dir, nbd)
        self.assertEqual(1, self._execute_losetup_count)

    @attr(kind='small')
    def test_setup_container_ex_execute_mount(self):
        """Test for nova.virt.disk.setup_container."""
        self._execute_mount_count = 0
        self._execute_losetup_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mount':
                self._execute_mount_count += 1
                raise exception.ProcessExecutionError()
            if cmd[0] == 'losetup':
                self._execute_losetup_count += 1

        def stub_link_device(image, nbd):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)

        image = None
        container_dir = None
        nbd = False
        self.disk.setup_container(image, container_dir, nbd)
        self.assertEqual(1, self._execute_mount_count)
        self.assertEqual(1, self._execute_losetup_count)

    @attr(kind='small')
    def test_setup_container_ex_execute_qemu_nbd(self):
        """Test for nova.virt.disk.setup_container."""
        self._execute_mount_count = 0
        self._execute_qemu_nbd_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mount':
                self._execute_mount_count += 1
                raise exception.ProcessExecutionError()
            if cmd[0] == 'qemu-nbd':
                self._execute_qemu_nbd_count += 1
                raise exception.ProcessExecutionError()

        def stub_link_device(image, nbd):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)

        image = None
        container_dir = None
        nbd = True
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.setup_container,
                          image, container_dir, nbd)
        self.assertEqual(1, self._execute_mount_count)
        self.assertEqual(1, self._execute_qemu_nbd_count)

    @attr(kind='small')
    def test_setup_container_ex_execute_losetup(self):
        """Test for nova.virt.disk.setup_container."""
        self._execute_mount_count = 0
        self._execute_losetup_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mount':
                self._execute_mount_count += 1
                raise exception.ProcessExecutionError()
            if cmd[0] == 'losetup':
                self._execute_losetup_count += 1
                raise exception.ProcessExecutionError()

        def stub_link_device(image, nbd):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_link_device', stub_link_device)

        image = None
        container_dir = None
        nbd = False
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.setup_container,
                          image, container_dir, nbd)
        self.assertEqual(1, self._execute_mount_count)
        self.assertEqual(1, self._execute_losetup_count)

    @attr(kind='small')
    def test_destroy_container_param_instance_name_in_loop(self):
        """Test for nova.virt.disk.destroy_container."""
        self._execute_mount_count = 0
        self._execute_umount_count = 0
        self._device = None

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mount':
                self._execute_mount_count += 1
                return """aaa
bbb instance1 ccc
ddd
""", None
            if cmd[0] == 'umount':
                self._execute_umount_count += 1

        def stub_unlink_device(device, nbd):
            self._device = device

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_unlink_device', stub_unlink_device)

        target = 'target'
        instance = {'name': 'instance1'}
        nbd = False
        self.disk.destroy_container(target, instance, nbd)
        self.assertEqual(1, self._execute_mount_count)
        self.assertEqual(1, self._execute_umount_count)
        self.assertEqual('bbb', self._device)

    @attr(kind='small')
    def test_destroy_container_param_instance_name_not_in_loop(self):
        """Test for nova.virt.disk.destroy_container."""
        self._execute_mount_count = 0
        self._device = None

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mount':
                self._execute_mount_count += 1
                return '', None

        def stub_unlink_device(device, nbd):
            self._device = device

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_unlink_device', stub_unlink_device)

        target = 'target'
        instance = {'name': 'instance1'}
        nbd = False
        self.disk.destroy_container(target, instance, nbd)
        self.assertEqual(1, self._execute_mount_count)

    @attr(kind='small')
    def test_destroy_container_param_instance_is_none(self):
        """
        No exception occurred even when instance is invalid.
        """
        raise SkipTest("TypeError occurred.")
        self._execute_mount_count = 0
        self._exeption_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mount':
                self._execute_mount_count += 1
                return 'aaa', None

        def stub_exception(caller, msg, *args):
            self._exeption_count += 1

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk.LOG, 'exception', stub_exception)

        target = 'target'
        instance = None
        nbd = False
        self.disk.destroy_container(target, instance, nbd)
        self.assertEqual(1, self._execute_mount_count)
        self.assertEqual(1, self._exeption_count)

    @attr(kind='small')
    def test_destroy_container_ex_execute_mount(self):
        """Test for nova.virt.disk.destroy_container."""
        raise SkipTest("ProcessExecutionError should not be raised.")
        self._execute_mount_count = 0
        self._exeption_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mount':
                self._execute_mount_count += 1
                raise exception.ProcessExecutionError()

        def stub_exception(caller, msg, *args):
            self._exeption_count += 1

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk.LOG, 'exception', stub_exception)

        target = 'target'
        instance = {'name': 'instance1'}
        nbd = False
        self.disk.destroy_container(target, instance, nbd)
        self.assertEqual(1, self._execute_mount_count)
        self.assertEqual(1, self._exeption_count)

    @attr(kind='small')
    def test_destroy_container_ex_execute_umount(self):
        """Test for nova.virt.disk.destroy_container."""
        self._execute_mount_count = 0
        self._execute_umount_count = 0
        self._exeption_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mount':
                self._execute_mount_count += 1
                return 'aaa instance1 bbb', None
            if cmd[0] == 'umount':
                self._execute_umount_count += 1
                raise exception.ProcessExecutionError()

        def stub_exception(caller, msg, *args):
            self._exeption_count += 1

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk.LOG, 'exception', stub_exception)

        target = 'target'
        instance = {'name': 'instance1'}
        nbd = False
        self.disk.destroy_container(target, instance, nbd)
        self.assertEqual(1, self._execute_mount_count)
        self.assertEqual(1, self._execute_umount_count)
        self.assertEqual(1, self._exeption_count)

    @attr(kind='small')
    def test_destroy_container_ex_unlink_device(self):
        """Test for nova.virt.disk.destroy_container."""
        self._execute_mount_count = 0
        self._execute_umount_count = 0
        self._exeption_count = 0

        def stub_execute(*cmd, **kwargs):
            if cmd[0] == 'mount':
                self._execute_mount_count += 1
                return 'aaa instance1 bbb', None
            if cmd[0] == 'umount':
                self._execute_umount_count += 1

        def stub_unlink_device(device, nbd):
            raise exception.ProcessExecutionError()

        def stub_exception(caller, msg, *args):
            self._exeption_count += 1

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.disk, '_unlink_device', stub_unlink_device)
        self.stubs.Set(self.disk.LOG, 'exception', stub_exception)

        target = 'target'
        instance = {'name': 'instance1'}
        nbd = False
        self.disk.destroy_container(target, instance, nbd)
        self.assertEqual(1, self._execute_mount_count)
        self.assertEqual(1, self._execute_umount_count)
        self.assertEqual(1, self._exeption_count)

    @attr(kind='small')
    def test_link_device_param_nbd_is_not_none(self):

        def fake_execute(*cmd, **kwargs):
            self.assertEqual(cmd[0], 'qemu-nbd')

            stdout = 'success'
            stderr = ''
            return (stdout, stderr)

        self.stubs.Set(utils, 'execute', fake_execute)

        def fake_os_exists(name):
            return True

        self.stubs.Set(os.path, 'exists', fake_os_exists)

        device = '/dev/nbd1'

        def fake_allocate_device():
            return device

        self.stubs.Set(self.disk, '_allocate_device', fake_allocate_device)

        image = '/image/test'
        nbd = True

        ref = self.disk._link_device(image, nbd)

        self.assertEqual(device, ref)

    @attr(kind='small')
    def test_link_device_param_nbd_is_none(self):
        self.stdout = 'success'
        self.stderr = ''

        def fake_execute(*cmd, **kwargs):
            self.assertEqual(cmd[0], 'losetup')

            return (self.stdout, self.stderr)

        self.stubs.Set(utils, 'execute', fake_execute)

        device = '/dev/nbd1'

        def fake_allocate_device():
            return device

        self.stubs.Set(self.disk, '_allocate_device', fake_allocate_device)

        image = '/image/test'
        nbd = None

        ref = self.disk._link_device(image, nbd)

        self.assertEqual(self.stdout, ref)

    @attr(kind='small')
    def test_link_device_cfg_free_nbd_devices_does_not_exist(self):
        def fake_execute(*cmd, **kwargs):
            self.assertEqual(cmd[0], 'qemu-nbd')

            stdout = 'success'
            stderr = ''
            return (stdout, stderr)

        self.stubs.Set(utils, 'execute', fake_execute)

        def fake_os_exists(name):
            return True

        self.stubs.Set(os.path, 'exists', fake_os_exists)

        def fake_allocate_device():
            raise exception.Error

        self.stubs.Set(self.disk, '_allocate_device', fake_allocate_device)

        image = '/image/test'
        nbd = True

        self.assertRaises(exception.Error,
                          self.disk._link_device, image, nbd)

    @attr(kind='small')
    def test_link_device_ex_execute_qemu_nbd(self):

        def fake_execute(*cmd, **kwargs):
            self.assertEqual(cmd[0], 'qemu-nbd')

            raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', fake_execute)

        def fake_os_exists(name):
            return True

        self.stubs.Set(os.path, 'exists', fake_os_exists)

        device = '/dev/nbd1'

        def fake_allocate_device():
            return device

        self.stubs.Set(self.disk, '_allocate_device', fake_allocate_device)

        image = '/image/test'
        nbd = True

        self.assertRaises(exception.ProcessExecutionError,
                          self.disk._link_device,
                            image, nbd)

    @attr(kind='small')
    def test_link_device_ex_nbd_device_not_found(self):

        self.flags(timeout_nbd=1)

        def fake_execute(*cmd, **kwargs):
            self.assertEqual(cmd[0], 'qemu-nbd')

            stdout = 'success'
            stderr = ''
            return (stdout, stderr)

        self.stubs.Set(utils, 'execute', fake_execute)

        def fake_os_exists(name):
            return False

        self.stubs.Set(os.path, 'exists', fake_os_exists)

        device = '/dev/nbd1'

        def fake_allocate_device():
            return device

        self.stubs.Set(self.disk, '_allocate_device', fake_allocate_device)

        image = '/image/test'
        nbd = True

        self.assertRaises(exception.Error,
                          self.disk._link_device,
                                image, nbd)

    @attr(kind='small')
    def test_link_device_ex_execute_losetup_stderr(self):
        def fake_execute(*cmd, **kwargs):
            self.assertEqual(cmd[0], 'losetup')

            raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', fake_execute)

        def fake_os_exists(name):
            return True

        self.stubs.Set(os.path, 'exists', fake_os_exists)

        device = '/dev/nbd1'

        def fake_allocate_device():
            return device

        self.stubs.Set(self.disk, '_allocate_device', fake_allocate_device)

        image = '/image/test'
        nbd = False

        self.assertRaises(exception.ProcessExecutionError,
                          self.disk._link_device,
                            image, nbd)

    @attr(kind='small')
    def test_link_device_ex_execute_losetup(self):
        def fake_execute(*cmd, **kwargs):
            self.assertEqual(cmd[0], 'losetup')

            return ('', 'errored')

        self.stubs.Set(utils, 'execute', fake_execute)

        def fake_os_exists(name):
            return True

        self.stubs.Set(os.path, 'exists', fake_os_exists)

        device = '/dev/nbd1'

        def fake_allocate_device():
            return device

        self.stubs.Set(self.disk, '_allocate_device', fake_allocate_device)

        image = '/image/test'
        nbd = False

        self.assertRaises(exception.Error,
                          self.disk._link_device,
                            image, nbd)

    @attr(kind='small')
    def test_inject_data_into_fs_param_key_is_not_none(self):
        """Test for nova.virt.disk.inject_data_into_fs."""

        def fake_execute(*cmd, **kwargs):
            if cmd[0] == 'tee' and 'process_input' in kwargs:
                self.assertEqual(True,
                                 kwargs['process_input'].find(self.key) > 0)

            stdout = 'success'
            stderr = ''
            return (stdout, stderr)

        self.stubs.Set(utils, 'execute', fake_execute)

        fs = '/'
        self.key = 'ABCD1234 user@host'
        net = None
        metadata = None
        execute = None
        ref = self.disk.inject_data_into_fs(fs, self.key, net,
                                            metadata, execute)

        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_inject_data_into_fs_param_net_is_not_none(self):
        """Test for nova.virt.disk.inject_data_into_fs."""

        def fake_execute(*cmd, **kwargs):
            if cmd[0] == 'tee' and 'process_input' in kwargs:
                self.assertEqual(True,
                                 kwargs['process_input'].find(self.net) >= 0)

            stdout = 'success'
            stderr = ''
            return (stdout, stderr)

        self.stubs.Set(utils, 'execute', fake_execute)

        fs = '/'
        key = None
        self.net = 'eth0'
        metadata = None
        execute = None
        ref = self.disk.inject_data_into_fs(fs, key, self.net,
                                            metadata, execute)
        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_inject_data_into_fs_param_metadata_is_not_none(self):
        """Test for nova.virt.disk.inject_data_into_fs."""

        class FakeModel(dict):
            """Represent a model from the db"""
            def __init__(self, *args, **kwargs):
                self.update(kwargs)

            def __getattr__(self, name):
                return self[name]

        def fake_execute(*cmd, **kwargs):
            if cmd[0] == 'tee' and 'process_input' in kwargs:
                self.assertEqual(True, kwargs['process_input'].find(
                                                '{"key1": "value1"}') >= 0)

            stdout = 'success'
            stderr = ''
            return (stdout, stderr)

        self.stubs.Set(utils, 'execute', fake_execute)

        fs = '/'
        key = None
        net = None
        self.metadata = [FakeModel(key='key1', value='value1')]

        execute = None
        ref = self.disk.inject_data_into_fs(fs, key, net,
                                            self.metadata, execute)
        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_inject_data_into_fs_ex_key_execute_mkdir(self):
        """Test for nova.virt.disk.inject_data_into_fs."""

        def fake_execute(*cmd, **kwargs):
            if cmd[0] == 'mkdir':
                raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', fake_execute)

        fs = '/'
        key = 'ABCDEFG'
        net = None
        metadata = None
        execute = None
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data_into_fs,
                                fs, key, net, metadata, execute)

    @attr(kind='small')
    def test_inject_data_into_fs_ex_key_execute_chown(self):
        """Test for nova.virt.disk.inject_data_into_fs."""

        def fake_execute(*cmd, **kwargs):
            if cmd[0] == 'chown':
                raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', fake_execute)

        fs = '/'
        key = 'ABCDEFG'
        net = None
        metadata = None
        execute = None
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data_into_fs,
                                fs, key, net, metadata, execute)

    @attr(kind='small')
    def test_inject_data_into_fs_ex_key_execute_chmod(self):
        """Test for nova.virt.disk.inject_data_into_fs."""
        def fake_execute(*cmd, **kwargs):
            if cmd[0] == 'chmod':
                raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', fake_execute)

        fs = '/'
        key = 'ABCDEFG'
        net = None
        metadata = None
        execute = None
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data_into_fs,
                                fs, key, net, metadata, execute)

    @attr(kind='small')
    def test_inject_data_into_fs_ex_key_execute_tee(self):
        """Test for nova.virt.disk.inject_data_into_fs."""
        def fake_execute(*cmd, **kwargs):
            if cmd[0] == 'tee':
                raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', fake_execute)

        fs = '/'
        key = 'ABCDEFG'
        net = None
        metadata = None
        execute = None
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data_into_fs,
                                fs, key, net, metadata, execute)

    @attr(kind='small')
    def test_inject_data_into_fs_ex_net_execute_mkdir(self):
        """Test for nova.virt.disk.inject_data_into_fs."""
        def fake_execute(*cmd, **kwargs):
            if cmd[0] == 'mkdir':
                raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', fake_execute)

        fs = '/'
        key = None
        net = 'eth0'
        metadata = None
        execute = None
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data_into_fs,
                                fs, key, net, metadata, execute)

    @attr(kind='small')
    def test_inject_data_into_fs_ex_net_execute_chown(self):
        """Test for nova.virt.disk.inject_data_into_fs."""
        def fake_execute(*cmd, **kwargs):
            if cmd[0] == 'chown':
                raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', fake_execute)

        fs = '/'
        key = None
        net = 'eth0'
        metadata = None
        execute = None
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data_into_fs,
                            fs, key, net, metadata, execute)

    @attr(kind='small')
    def test_inject_data_into_fs_ex_net_execute_chmod(self):
        """Test for nova.virt.disk.inject_data_into_fs."""
        def fake_execute(*cmd, **kwargs):
            if cmd[0] == 'chmod':
                raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', fake_execute)

        fs = '/'
        key = None
        net = 'eth0'
        metadata = None
        execute = None
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data_into_fs,
                                fs, key, net, metadata, execute)

    @attr(kind='small')
    def test_inject_data_into_fs_ex_net_execute_tee(self):
        """Test for nova.virt.disk.inject_data_into_fs."""
        def fake_execute(*cmd, **kwargs):
            if cmd[0] == 'tee':
                raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', fake_execute)

        fs = '/'
        key = None
        net = 'eth0'
        metadata = None
        execute = None
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data_into_fs,
                                fs, key, net, metadata, execute)

    @attr(kind='small')
    def test_inject_data_into_fs_ex_metadata_execute_tee(self):
        """Test for nova.virt.disk.inject_data_into_fs."""

        class FakeModel(dict):
            """Represent a model from the db"""
            def __init__(self, *args, **kwargs):
                self.update(kwargs)

            def __getattr__(self, name):
                return self[name]

        def fake_execute(*cmd, **kwargs):
            if cmd[0] == 'tee':
                raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', fake_execute)

        fs = '/'
        key = None
        net = None
        metadata = [FakeModel(key='key1', value='value1')]
        execute = None
        self.assertRaises(exception.ProcessExecutionError,
                          self.disk.inject_data_into_fs,
                                fs, key, net, metadata, execute)

    @attr(kind='small')
    def test_inject_data_into_fs_param_fs_is_none(self):
        """Test for nova.virt.disk.inject_data_into_fs."""

        class FakeModel(dict):
            """Represent a model from the db"""
            def __init__(self, *args, **kwargs):
                self.update(kwargs)

            def __getattr__(self, name):
                return self[name]

        def fake_execute(*cmd, **kwargs):
            stdout = 'success'
            stderr = ''
            return (stdout, stderr)

        self.stubs.Set(utils, 'execute', fake_execute)

        fs = None
        self.key = 'ABCD1234 user@host'
        net = 'etho'
        metadata = [FakeModel(key='key1', value='value1')]
        execute = None
        ref = self.disk.inject_data_into_fs(fs, self.key, net,
                                            metadata, execute)

        self.assertEqual(None, ref)
