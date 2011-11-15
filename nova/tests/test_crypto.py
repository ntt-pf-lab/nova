# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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
"""
Tests for Crypto module.
"""

import mox
import os
import shutil
import stubout
import tempfile
import M2Crypto

from nova import crypto
from nova import db
from nova import exception
from nova import flags
from nova import test
from nova import utils
from nose.plugins.attrib import attr

FLAGS = flags.FLAGS


certificates = [{'id': 1,
                 'user_id': 'test_user',
                 'project_id': 'test_project',
                 'file_name': 'test_file'},
                {'id': 2,
                 'user_id': 'test_user',
                 'project_id': 'test_project',
                 'file_name': 'test_file'}]


class CryptoTestCase(test.TestCase):
    """Test for nova.crypto. """
    def setUp(self):
        super(CryptoTestCase, self).setUp()
        self.crypto = crypto

    def _create_file(self, filename, s=''):
        dirname = os.path.dirname(filename)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        with open(filename, 'w') as f:
            f.write(s)

    def _read_file(self, filename):
        with open(filename, 'r') as f:
            return f.read()

    @attr(kind='small')
    def test_ca_folder_cfg_not_use_project_ca(self):
        """Test for nova.crypto.ca_folder. """
        self.flags(use_project_ca=False)
        project_id = 'fake'

        ref = self.crypto.ca_folder(project_id)
        ca_folder = flags.FLAGS.ca_path
        self.assertEqual(ca_folder, ref)

    @attr(kind='small')
    def test_ca_folder_cfg_use_project_ca(self):
        """Test for nova.crypto.ca_folder. """
        self.flags(use_project_ca=True)
        project_id = 'fake'

        ref = self.crypto.ca_folder(project_id)
        ca_folder = os.path.join(flags.FLAGS.ca_path, 'projects', project_id)
        self.assertEqual(ca_folder, ref)

    @attr(kind='small')
    def test_ca_path(self):
        """Test for nova.crypto.ca_path. """
        self.flags(use_project_ca=False)
        project_id = 'fake'

        ref = self.crypto.ca_path(project_id)
        ca_path = os.path.join(flags.FLAGS.ca_path, FLAGS.ca_file)
        self.assertEqual(ca_path, ref)

    @attr(kind='small')
    def test_key_path(self):
        """Test for nova.crypto.key_path. """
        self.flags(use_project_ca=False)
        project_id = 'fake'

        ref = self.crypto.key_path(project_id)
        key_path = os.path.join(flags.FLAGS.ca_path, FLAGS.key_file)
        self.assertEqual(key_path, ref)

    @attr(kind='small')
    def test_fetch_ca_param_project_id_is_not_none_and_chain_is_true(self):
        """Test for nova.crypto.fetch_ca. """
        self.flags(use_project_ca=True)
        project_id = 'fake'
        chain = True
        project_ca_path = self.crypto.ca_path(project_id)
        self._create_file(project_ca_path, 'cacert_project')
        ca_path = self.crypto.ca_path(None)
        ca_path_exist = os.path.exists(ca_path)
        if ca_path_exist:
            ca_str = self._read_file(ca_path)
        self._create_file(ca_path, 'cacert')

        ref = self.crypto.fetch_ca(project_id, chain)
        self.assertEqual('cacert_project' + 'cacert', ref)

        os.remove(project_ca_path)
        if ca_path_exist:
            self._create_file(ca_path, ca_str)
        else:
            os.remove(ca_path)

    @attr(kind='small')
    def test_fetch_ca_param_project_id_is_not_none_and_chain_is_false(self):
        """Test for nova.crypto.fetch_ca. """
        self.flags(use_project_ca=True)
        project_id = 'fake'
        chain = False
        project_ca_path = self.crypto.ca_path(project_id)
        self._create_file(project_ca_path, 'cacert_project')

        ref = self.crypto.fetch_ca(project_id, chain)
        self.assertEqual('cacert_project', ref)

        os.remove(project_ca_path)

    @attr(kind='small')
    def test_fetch_ca_param_project_id_is_none(self):
        """Test for nova.crypto.fetch_ca. """
        self.flags(use_project_ca=True)
        project_id = None
        ca_path = self.crypto.ca_path(None)
        ca_path_exist = os.path.exists(ca_path)
        if ca_path_exist:
            ca_str = self._read_file(ca_path)
        self._create_file(ca_path, 'cacert')

        ref = self.crypto.fetch_ca(project_id)
        self.assertEqual('cacert', ref)

        if ca_path_exist:
            self._create_file(ca_path, ca_str)
        else:
            os.remove(ca_path)

    @attr(kind='small')
    def test_fetch_ca_cfg_not_use_project_ca(self):
        """Test for nova.crypto.fetch_ca. """
        self.flags(use_project_ca=False)
        project_id = 'fake'
        ca_path = self.crypto.ca_path(None)
        ca_path_exist = os.path.exists(ca_path)
        if ca_path_exist:
            ca_str = self._read_file(ca_path)
        self._create_file(ca_path, 'cacert')

        ref = self.crypto.fetch_ca(project_id)
        self.assertEqual('cacert', ref)

        if ca_path_exist:
            self._create_file(ca_path, ca_str)
        else:
            os.remove(ca_path)

    @attr(kind='small')
    def test_fetch_ca_ex_open_project_ca_path(self):
        """
        FileError is raised when IOError occurred
        in open(ca_path(project_id), 'r')
        """
        self.flags(use_project_ca=True)
        project_id = 'fake'

        def stub_ca_path(project_id=None):
            if project_id == 'fake':
                return ''

        self.stubs.Set(self.crypto, 'ca_path', stub_ca_path)

        self.assertRaises(exception.FileError,
                          self.crypto.fetch_ca,
                          project_id)

    @attr(kind='small')
    def test_fetch_ca_ex_open_ca_path(self):
        """
        FileError is raised when IOError occurred
        in open(ca_path(None), 'r')
        """
        self.flags(use_project_ca=True)
        project_id = None

        def stub_ca_path(project_id=None):
            if project_id == None:
                return ''

        self.stubs.Set(self.crypto, 'ca_path', stub_ca_path)

        self.assertRaises(exception.FileError,
                          self.crypto.fetch_ca,
                          project_id)

    @attr(kind='small')
    def test_generate_fingerprint(self):
        """Test for nova.crypto.generate_fingerprint. """
        self.mox.StubOutWithMock(utils, 'execute')
        out = 'ssh-rsa AAAAAAAAAA test_user@test_host'
        utils.execute(mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg()).AndReturn((out, None))
        self.mox.ReplayAll()

        ref = self.crypto.generate_fingerprint('./.ssh/id_rsa')
        self.assertEqual('AAAAAAAAAA', ref)

    @attr(kind='small')
    def test_generate_fingerprint_ex_utils_execute(self):
        """
        ProcessExecutionError is raised

        """
        self.mox.StubOutWithMock(utils, 'execute')
        utils.execute(mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg()).\
                AndRaise(exception.ProcessExecutionError)
        self.mox.ReplayAll()

        self.assertRaises(exception.ProcessExecutionError,
                          self.crypto.generate_fingerprint,
                          './.ssh/id_rsa')

    @attr(kind='small')
    def test_generate_key_pair(self):
        """Test for nova.crypto.generate_key_pair. """
        self.mox.StubOutWithMock(tempfile, 'mkdtemp')
        self.mox.StubOutWithMock(utils, 'execute')
        temp_dir = os.path.join(os.getcwd(), 'crypto')
        tempfile.mkdtemp().AndReturn(temp_dir)
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg())
        self._create_file(os.path.join(temp_dir, 'temp'), 'AAAAAAAAAA')
        self._create_file(os.path.join(temp_dir, 'temp.pub'), 'BBBBBBBBBB')
        out = 'ssh-rsa CCCCCCCCCC test_user@test_host'
        utils.execute(mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg()).AndReturn((out, None))
        self.mox.ReplayAll()

        ref = self.crypto.generate_key_pair()
        self.assertEqual(('AAAAAAAAAA', 'BBBBBBBBBB', 'CCCCCCCCCC'), ref)

    @attr(kind='small')
    def test_generate_key_pair_param_bits_is_less_than_minimum(self):
        """
        ProcessExecutionError is raised
        when bits is less than the minimum size for RSA keys
        """
        bits = 767
        self.assertRaises(exception.ProcessExecutionError,
                          self.crypto.generate_key_pair,
                          bits=bits)

    @attr(kind='small')
    def test_generate_key_pair_ex_tempfile_mkdtemp(self):
        """
        FileError is raised when OSError occurred in tempfile.mkdtemp()
        """
        self.mox.StubOutWithMock(tempfile, 'mkdtemp')
        tempfile.mkdtemp().AndRaise(OSError)
        self.mox.ReplayAll()

        self.assertRaises(exception.FileError,
                          self.crypto.generate_key_pair)

    @attr(kind='small')
    def test_generate_key_pair_ex_utils_execute(self):
        """
        ProcessExecutionError is raised
        """
        self.mox.StubOutWithMock(utils, 'execute')
        utils.execute(mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg()).\
                AndRaise(exception.ProcessExecutionError)
        self.mox.ReplayAll()

        self.assertRaises(exception.ProcessExecutionError,
                          self.crypto.generate_key_pair)

    @attr(kind='small')
    def test_generate_key_pair_ex_private_key_open(self):
        """
        FileError is raised when IOError occurred in open(keyfile)
        """
        self.mox.StubOutWithMock(tempfile, 'mkdtemp')
        self.mox.StubOutWithMock(utils, 'execute')
        temp_dir = os.path.join(os.getcwd(), 'crypto')
        tempfile.mkdtemp().AndReturn(temp_dir)
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg())
        out = 'ssh-rsa CCCCCCCCCC test_user@test_host'
        utils.execute(mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg()).AndReturn((out, None))
        self.mox.ReplayAll()

        self.assertRaises(exception.FileError,
                          self.crypto.generate_key_pair)

    @attr(kind='small')
    def test_generate_key_pair_ex_public_key_open(self):
        """
        FileError is raised when IOError occurred in open(keyfile + '.pub')
        """
        self.mox.StubOutWithMock(tempfile, 'mkdtemp')
        self.mox.StubOutWithMock(utils, 'execute')
        temp_dir = os.path.join(os.getcwd(), 'crypto')
        tempfile.mkdtemp().AndReturn(temp_dir)
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg())
        self._create_file(os.path.join(temp_dir, 'temp.pub'), 'BBBBBBBBBB')
        out = 'ssh-rsa CCCCCCCCCC test_user@test_host'
        utils.execute(mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg()).AndReturn((out, None))
        self.mox.ReplayAll()

        self.assertRaises(exception.FileError,
                          self.crypto.generate_key_pair)

    @attr(kind='small')
    def test_generate_key_pair_ex_shutil_rmtree(self):
        """
        OSError is not raised even when OSError occured in shutil.rmtree()
        """
        self._msg = None
        self._args = None
        self._kwargs = None

        def stub_warn(msg, *args, **kwargs):
            self._msg = msg
            self._args = args
            self._kwargs = kwargs

        self.mox.StubOutWithMock(tempfile, 'mkdtemp')
        self.mox.StubOutWithMock(utils, 'execute')
        temp_dir = os.path.join(os.getcwd(), 'crypto')
        self.mox.StubOutWithMock(shutil, 'rmtree')
        self.stubs.Set(self.crypto.LOG, 'warn', stub_warn)
        tempfile.mkdtemp().AndReturn(temp_dir)
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg())
        self._create_file(os.path.join(temp_dir, 'temp'), 'AAAAAAAAAA')
        self._create_file(os.path.join(temp_dir, 'temp.pub'), 'BBBBBBBBBB')
        out = 'ssh-rsa CCCCCCCCCC test_user@test_host'
        utils.execute(mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg(),
                      mox.IgnoreArg()).AndReturn((out, None))
        ex = OSError()
        shutil.rmtree(mox.IgnoreArg()).AndRaise(ex)
        self.mox.ReplayAll()

        ref = self.crypto.generate_key_pair()
        self.assertEqual(('AAAAAAAAAA', 'BBBBBBBBBB', 'CCCCCCCCCC'), ref)
        self.assertEqual('Failed to remove dir %s: %s', self._msg)
        self.assertEqual(temp_dir, self._args[0])
        self.assertEqual(ex, self._args[1])

    @attr(kind='small')
    def test_ssl_pub_to_ssh_pub(self):
        """Test for nova.crypto.ssl_pub_to_ssh_pub. """
        private_key = crypto.generate_key_pair()[0]
        key = M2Crypto.RSA.load_key_string(private_key, callback=lambda: None)
        bio = M2Crypto.BIO.MemoryBuffer()
        key.save_pub_key_bio(bio)
        public_key = bio.read()
        ref = self.crypto.ssl_pub_to_ssh_pub(public_key)
        self.assertEqual('ssh-rsa', ref.split(' ')[0])
        self.assertTrue(ref.split(' ')[1])
        self.assertTrue(ref.split(' ')[2])

    @attr(kind='small')
    def test_generate_x509_cert(self):
        """Test for nova.crypto.generate_x509_cert. """
        self.flags(use_project_ca=True)
        self.mox.StubOutWithMock(utils, 'execute')
        self.mox.StubOutWithMock(tempfile, 'mkdtemp')
        self.mox.StubOutWithMock(self.crypto, '_sign_csr')
        self.mox.StubOutWithMock(db, 'certificate_create')
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg())
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg())
        self.crypto._sign_csr(mox.IgnoreArg(),
                             mox.IgnoreArg()).AndReturn(('ccc', 'sss'))
        db.certificate_create(mox.IgnoreArg(), mox.IgnoreArg())
        temp_dir = os.path.join(os.getcwd(), 'crypto')
        tempfile.mkdtemp().AndReturn(temp_dir)
        self.mox.ReplayAll()

        user_id = 'test_user'
        project_id = 'fake'
        bits = 1024
        ca_path = self.crypto.ca_path(project_id)
        # make sure the condition that ca_path exists
        if not os.path.exists(ca_path):
            self._create_file(ca_path)
        # make a file {path to temp_dir}/crypto/temp.key
        self._create_file(os.path.join(temp_dir, 'temp.key'), 'aaa')
        # make a file {path to temp_dir}/crypto/temp.csr
        self._create_file(os.path.join(temp_dir, 'temp.csr'), 'bbb')

        ref = self.crypto.generate_x509_cert(user_id, project_id, bits=bits)
        self.assertEqual(('aaa', 'sss'), ref)

    @attr(kind='small')
    def test_generate_x509_cert_ex_tempfile_mkdtemp(self):
        """
        FileError is raised when OSError occurred in tempfile.mkdtemp()
        """
        self.mox.StubOutWithMock(tempfile, 'mkdtemp')
        tempfile.mkdtemp().AndRaise(OSError)
        self.mox.ReplayAll()

        user_id = 'test_user'
        project_id = 'fake'
        bits = 1024
        self.assertRaises(exception.FileError,
                          self.crypto.generate_x509_cert,
                          user_id, project_id, bits=bits)

    @attr(kind='small')
    def test_generate_x509_cert_ex_utils_execute(self):
        """
        ProcessExecutionError is raised
        """
        self.mox.StubOutWithMock(utils, 'execute')
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg()).\
                AndRaise(exception.ProcessExecutionError)
        self.mox.ReplayAll()

        user_id = 'test_user'
        project_id = 'fake'
        bits = 1024
        self.assertRaises(exception.ProcessExecutionError,
                          self.crypto.generate_x509_cert,
                          user_id, project_id, bits=bits)

    @attr(kind='small')
    def test_generate_x509_cert_ex_private_key_open(self):
        """
        FileError is raised when IOError occurred in open(keyfile)
        """
        self.flags(use_project_ca=True)
        self.mox.StubOutWithMock(tempfile, 'mkdtemp')
        self.mox.StubOutWithMock(utils, 'execute')
        temp_dir = os.path.join(os.getcwd(), 'crypto')
        tempfile.mkdtemp().AndReturn(temp_dir)
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg())
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg())
        self.mox.ReplayAll()

        user_id = 'test_user'
        project_id = 'fake'
        bits = 1024
        self.assertRaises(exception.FileError,
                          self.crypto.generate_x509_cert,
                          user_id, project_id, bits=bits)

    @attr(kind='small')
    def test_generate_x509_cert_ex_csr_open(self):
        """
        FileError is raised when IOError occurred in open(csrfile)
        """
        self.flags(use_project_ca=True)
        self.mox.StubOutWithMock(tempfile, 'mkdtemp')
        self.mox.StubOutWithMock(utils, 'execute')
        temp_dir = os.path.join(os.getcwd(), 'crypto')
        tempfile.mkdtemp().AndReturn(temp_dir)
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg())
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg())
        self.mox.ReplayAll()

        user_id = 'test_user'
        project_id = 'fake'
        bits = 1024
        ca_path = self.crypto.ca_path(project_id)
        # make sure the condition that ca_path exists
        if not os.path.exists(ca_path):
            self._create_file(ca_path)
        # make a file {path to temp_dir}/crypto/temp.key
        self._create_file(os.path.join(temp_dir, 'temp.key'), 'aaa')

        self.assertRaises(exception.FileError,
                          self.crypto.generate_x509_cert,
                          user_id, project_id, bits=bits)

    @attr(kind='small')
    def test_generate_x509_cert_ex_shutil_rmtree(self):
        """
        OSError is not raised even when OSError occured in shutil.rmtree()
        """
        self._msg = None
        self._args = None
        self._kwargs = None

        def stub_warn(msg, *args, **kwargs):
            self._msg = msg
            self._args = args
            self._kwargs = kwargs

        self.flags(use_project_ca=True)
        self.mox.StubOutWithMock(utils, 'execute')
        self.mox.StubOutWithMock(tempfile, 'mkdtemp')
        self.mox.StubOutWithMock(shutil, 'rmtree')
        self.stubs.Set(self.crypto.LOG, 'warn', stub_warn)
        self.mox.StubOutWithMock(self.crypto, '_sign_csr')
        self.mox.StubOutWithMock(db, 'certificate_create')
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg())
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg())
        self.crypto._sign_csr(mox.IgnoreArg(),
                             mox.IgnoreArg()).AndReturn(('ccc', 'sss'))
        db.certificate_create(mox.IgnoreArg(), mox.IgnoreArg())
        temp_dir = os.path.join(os.getcwd(), 'crypto')
        tempfile.mkdtemp().AndReturn(temp_dir)
        ex = OSError()
        shutil.rmtree(mox.IgnoreArg()).AndRaise(ex)
        self.mox.ReplayAll()

        user_id = 'test_user'
        project_id = 'fake'
        bits = 1024
        ca_path = self.crypto.ca_path(project_id)
        # make sure the condition that ca_path exists
        if not os.path.exists(ca_path):
            self._create_file(ca_path)
        # make a file {path to temp_dir}/crypto/temp.key
        self._create_file(os.path.join(temp_dir, 'temp.key'), 'aaa')
        # make a file {path to temp_dir}/crypto/temp.csr
        self._create_file(os.path.join(temp_dir, 'temp.csr'), 'bbb')

        ref = self.crypto.generate_x509_cert(user_id, project_id, bits=bits)
        self.assertEqual(('aaa', 'sss'), ref)
        self.assertEqual('Failed to remove dir %s: %s', self._msg)
        self.assertEqual(temp_dir, self._args[0])
        self.assertEqual(ex, self._args[1])

    @attr(kind='small')
    def test_generate_vpn_files(self):
        """Test for nova.crypto.generate_vpn_files. """
        self.flags(use_project_ca=True)
        self._count = 0

        def stub_execute(*cmd, **kwargs):
            self._count += 1
            self._create_file(csr_fn, 'sss')
            self._create_file(crt_fn)

        self.stubs.Set(utils, 'execute', stub_execute)
        self.mox.StubOutWithMock(self.crypto, '_sign_csr')
        self.crypto._sign_csr(mox.IgnoreArg(),
                             mox.IgnoreArg()).AndReturn(('ccc', 'sss'))
        self.mox.ReplayAll()

        project_id = 'fake'
        project_folder = self.crypto.ca_folder(project_id)
        csr_fn = os.path.join(project_folder, 'server.csr')
        crt_fn = os.path.join(project_folder, 'server.crt')
        ca_path = self.crypto.ca_path(project_id)
        # make sure the condition that ca_path exists
        if not os.path.exists(ca_path):
            self._create_file(ca_path)

        self.crypto.generate_vpn_files(project_id)
        self.assertEqual(1, self._count)

        os.remove(csr_fn)
        os.remove(crt_fn)

    @attr(kind='small')
    def test_generate_vpn_files_param_crt_fn_exists(self):
        """Test for nova.crypto.generate_vpn_files. """
        self.flags(use_project_ca=True)
        self._count = 0

        def stub_execute(*cmd, **kwargs):
            self._count += 1

        self.stubs.Set(utils, 'execute', stub_execute)

        project_id = 'fake'
        project_folder = self.crypto.ca_folder(project_id)
        crt_fn = os.path.join(project_folder, 'server.crt')
        # make sure that server.crt already exists
        self._create_file(crt_fn)

        self.crypto.generate_vpn_files(project_id)
        self.assertEqual(0, self._count)

        os.remove(crt_fn)

    @attr(kind='small')
    def test_generate_vpn_files_ex_csr_open(self):
        """
        FileError is raised when IOError occurred in open(csr_fn, 'r')
        """
        self.flags(use_project_ca=True)

        def stub_execute(*cmd, **kwargs):
            pass

        self.stubs.Set(utils, 'execute', stub_execute)

        project_id = 'fake'
        self.assertRaises(exception.FileError,
                          self.crypto.generate_vpn_files,
                          project_id)

    @attr(kind='small')
    def test_generate_vpn_files_ex_crt_open(self):
        """
        FileError is raised when IOError occurred in open(crt_fn, 'w')
        """
        self.flags(use_project_ca=True)

        def stub_execute(*cmd, **kwargs):
            self._create_file(csr_fn, 'sss')

        def stub_sign_csr(csr_text, ca_folder):
            self._create_file(crt_fn)
            os.chmod(crt_fn, int('000', 8))
            return ('ccc', 'sss')

        self.stubs.Set(utils, 'execute', stub_execute)
        self.stubs.Set(self.crypto, '_sign_csr', stub_sign_csr)

        project_id = 'fake'
        project_folder = self.crypto.ca_folder(project_id)
        csr_fn = os.path.join(project_folder, 'server.csr')
        crt_fn = os.path.join(project_folder, 'server.crt')
        if os.path.exists(crt_fn):
            os.remove(crt_fn)
        ca_path = self.crypto.ca_path(project_id)
        # make sure the condition that ca_path exists
        if not os.path.exists(ca_path):
            self._create_file(ca_path)

        self.assertRaises(exception.FileError,
                          self.crypto.generate_vpn_files,
                          project_id)

        os.remove(csr_fn)
        os.remove(crt_fn)

    @attr(kind='small')
    def test_sign_csr_cfg_use_project_ca(self):
        """Test for nova.crypto.sign_csr. """
        self.flags(use_project_ca=True)
        self.mox.StubOutWithMock(utils, 'execute')
        self.mox.StubOutWithMock(tempfile, 'mkdtemp')
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg())
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                AndReturn(('aaa=bbb=ccc', None))
        temp_dir = os.path.join(os.getcwd(), 'crypto')
        tempfile.mkdtemp().AndReturn(temp_dir)
        self.mox.ReplayAll()

        csr_text = 'test'
        project_id = 'fake'
        ca_path = self.crypto.ca_path(project_id)
        # make sure the condition that ca_path does not exist
        if os.path.exists(ca_path):
            os.remove(ca_path)
        # make a file {path to temp_dir}/crypto/outbound.csr
        outbound = os.path.join(temp_dir, 'outbound.csr')
        self._create_file(outbound, 'ddd')

        ref = self.crypto.sign_csr(csr_text, project_id)
        self.assertEqual(('ccc', 'ddd'), ref)
        self.assertFalse(os.path.exists(temp_dir))

    @attr(kind='small')
    def test_sign_csr_cfg_not_use_project_ca(self):
        """Test for nova.crypto.sign_csr. """
        self.flags(use_project_ca=False)
        self.mox.StubOutWithMock(utils, 'execute')
        self.mox.StubOutWithMock(tempfile, 'mkdtemp')
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                AndReturn(('aaa=bbb=ccc', None))
        temp_dir = os.path.join(os.getcwd(), 'crypto')
        tempfile.mkdtemp().AndReturn(temp_dir)
        self.mox.ReplayAll()

        csr_text = 'test'
        project_id = 'fake'
        # make a file {path to temp_dir}/crypto/outbound.csr
        outbound = os.path.join(temp_dir, 'outbound.csr')
        self._create_file(outbound, 'ddd')

        ref = self.crypto.sign_csr(csr_text, project_id)
        self.assertEqual(('ccc', 'ddd'), ref)
        self.assertFalse(os.path.exists(temp_dir))

    @attr(kind='small')
    def test_sign_csr_param_ca_path_does_exists(self):
        """Test for nova.crypto.sign_csr. """
        self.flags(use_project_ca=True)
        self.mox.StubOutWithMock(utils, 'execute')
        self.mox.StubOutWithMock(tempfile, 'mkdtemp')
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                AndReturn(('aaa=bbb=ccc', None))
        temp_dir = os.path.join(os.getcwd(), 'crypto')
        tempfile.mkdtemp().AndReturn(temp_dir)
        self.mox.ReplayAll()

        csr_text = 'test'
        project_id = 'fake'
        ca_path = self.crypto.ca_path(project_id)
        # make sure the condition that ca_path exists
        if not os.path.exists(ca_path):
            self._create_file(ca_path)
        # make a file {path to temp_dir}/crypto/outbound.csr
        outbound = os.path.join(temp_dir, 'outbound.csr')
        self._create_file(outbound, 'ddd')

        ref = self.crypto.sign_csr(csr_text, project_id)
        self.assertEqual(('ccc', 'ddd'), ref)
        self.assertFalse(os.path.exists(temp_dir))

    @attr(kind='small')
    def test_sign_csr_param_ca_folder_does_not_exist(self):
        """Test for nova.crypto.sign_csr. """
        self.flags(use_project_ca=True)
        self.mox.StubOutWithMock(utils, 'execute')
        self.mox.StubOutWithMock(tempfile, 'mkdtemp')
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg())
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                AndReturn(('aaa=bbb=ccc', None))
        temp_dir = os.path.join(os.getcwd(), 'crypto')
        tempfile.mkdtemp().AndReturn(temp_dir)
        self.mox.ReplayAll()

        csr_text = 'test'
        project_id = 'fake'
        ca_path = self.crypto.ca_path(project_id)
        # make sure the condition that ca_path does not exist
        if os.path.exists(ca_path):
            os.remove(ca_path)
        ca_folder = self.crypto.ca_folder(project_id)
        # make sure the condition that ca_folder does not exist
        if os.path.exists(ca_folder):
            shutil.rmtree(ca_folder)
        self.assertFalse(os.path.exists(ca_folder))
        # make a file {path to temp_dir}/crypto/outbound.csr
        outbound = os.path.join(temp_dir, 'outbound.csr')
        self._create_file(outbound, 'ddd')

        ref = self.crypto.sign_csr(csr_text, project_id)
        self.assertEqual(('ccc', 'ddd'), ref)
        self.assertTrue(os.path.exists(ca_folder))
        self.assertFalse(os.path.exists(temp_dir))

    @attr(kind='small')
    def test_sign_csr_ex_tempfile_mkdtemp(self):
        """
        FileError is raised when OSError occurred in tempfile.mkdtemp()
        """
        self.flags(use_project_ca=False)

        self.mox.StubOutWithMock(tempfile, 'mkdtemp')
        tempfile.mkdtemp().AndRaise(OSError)
        self.mox.ReplayAll()

        csr_text = 'test'
        project_id = 'fake'
        self.assertRaises(exception.FileError,
                          self.crypto.sign_csr,
                          csr_text, project_id)

    @attr(kind='small')
    def test_sign_csr_ex_inbound_open(self):
        """
        FileError is raised when IOError occurred in open(inbound, 'w')
        """
        self.flags(use_project_ca=False)

        self.mox.StubOutWithMock(tempfile, 'mkdtemp')
        tempfile.mkdtemp().AndReturn('/')
        self.mox.ReplayAll()

        csr_text = 'test'
        project_id = 'fake'
        self.assertRaises(exception.FileError,
                          self.crypto.sign_csr,
                          csr_text, project_id)

    @attr(kind='small')
    def test_sign_csr_ex_os_makedirs(self):
        """
        FileError is raised when OSError occurred in os.makedirs()
        """
        self.flags(use_project_ca=True)

        self.mox.StubOutWithMock(utils, 'execute')
        self.mox.StubOutWithMock(tempfile, 'mkdtemp')
        self.mox.StubOutWithMock(os, 'makedirs')
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg())
        temp_dir = os.path.join(os.getcwd(), 'crypto')
        tempfile.mkdtemp().AndReturn(temp_dir)
        os.makedirs(mox.IgnoreArg()).AndRaise(OSError)
        self.mox.ReplayAll()

        csr_text = 'test'
        project_id = 'fake'
        ca_path = self.crypto.ca_path(project_id)
        # make sure the condition that ca_path does not exist
        if os.path.exists(ca_path):
            os.remove(ca_path)
        ca_folder = self.crypto.ca_folder(project_id)
        # make sure the condition that ca_folder does not exist
        if os.path.exists(ca_folder):
            shutil.rmtree(ca_folder)

        self.assertRaises(exception.FileError,
                          self.crypto.sign_csr,
                          csr_text, project_id)

    @attr(kind='small')
    def test_sign_csr_ex_utils_execute(self):
        """
        ProcessExecutionError is raised
        """
        self.flags(use_project_ca=False)
        self.mox.StubOutWithMock(utils, 'execute')
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                AndRaise(exception.ProcessExecutionError)
        self.mox.ReplayAll()

        csr_text = 'test'
        project_id = 'fake'
        self.assertRaises(exception.ProcessExecutionError,
                          self.crypto.sign_csr,
                          csr_text, project_id)

    @attr(kind='small')
    def test_sign_csr_ex_outbound_open(self):
        """
        FileError is raised when IOError occurred in open(outbound, 'r')
        """
        self.flags(use_project_ca=False)

        self.mox.StubOutWithMock(tempfile, 'mkdtemp')
        self.mox.StubOutWithMock(utils, 'execute')
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                AndReturn(('aaa=bbb=ccc', None))
        temp_dir = os.path.join(os.getcwd(), 'crypto')
        tempfile.mkdtemp().AndReturn(temp_dir)
        self.mox.ReplayAll()

        csr_text = 'test'
        project_id = 'fake'
        self.assertRaises(exception.FileError,
                          self.crypto.sign_csr,
                          csr_text, project_id)

    @attr(kind='small')
    def test_sign_csr_ex_shutil_rmtree(self):
        """
        OSError is not raised even when OSError occured in shutil.rmtree()
        """
        self.flags(use_project_ca=False)

        self._msg = None
        self._args = None
        self._kwargs = None

        def stub_warn(msg, *args, **kwargs):
            self._msg = msg
            self._args = args
            self._kwargs = kwargs

        self.mox.StubOutWithMock(utils, 'execute')
        self.mox.StubOutWithMock(tempfile, 'mkdtemp')
        self.mox.StubOutWithMock(shutil, 'rmtree')
        self.stubs.Set(self.crypto.LOG, 'warn', stub_warn)
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        utils.execute(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
                      mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                AndReturn(('aaa=bbb=ccc', None))
        temp_dir = os.path.join(os.getcwd(), 'crypto')
        tempfile.mkdtemp().AndReturn(temp_dir)
        ex = OSError()
        shutil.rmtree(mox.IgnoreArg()).AndRaise(ex)
        self.mox.ReplayAll()

        csr_text = 'test'
        project_id = 'fake'
        # make a file {path to temp_dir}/crypto/outbound.csr
        outbound = os.path.join(temp_dir, 'outbound.csr')
        self._create_file(outbound, 'ddd')

        ref = self.crypto.sign_csr(csr_text, project_id)
        self.assertEqual(('ccc', 'ddd'), ref)
        self.assertEqual('Failed to remove dir %s: %s', self._msg)
        self.assertEqual(temp_dir, self._args[0])
        self.assertEqual(ex, self._args[1])

        os.remove(outbound)

    @attr(kind='small')
    def test_compute_md5(self):
        """Test for nova.crypto.compute_md5. """
        s = 'foo'
        fp = tempfile.TemporaryFile()
        fp.write(s)

        ref = self.crypto.compute_md5(fp)
        self.assertEqual('acbd18db4cc2f85cedef654fccc4a4d8', ref)

        fp.close()

    @attr(kind='small')
    def test_compute_md5_ex_file_not_open(self):
        """
        IOError is raised when file not open for reading
        """
        fp = open('foo.temp', 'w')

        self.assertRaises(IOError,
                          self.crypto.compute_md5, fp)

        fp.close()


class SymmetricKeyTestCase(test.TestCase):
    """Test case for Encrypt/Decrypt"""
    def test_encrypt_decrypt(self):
        key = 'c286696d887c9aa0611bbb3e2025a45a'
        plain_text = "The quick brown fox jumped over the lazy dog."

        # No IV supplied (all 0's)
        encrypt = crypto.encryptor(key)
        cipher_text = encrypt(plain_text)
        self.assertNotEquals(plain_text, cipher_text)

        decrypt = crypto.decryptor(key)
        plain = decrypt(cipher_text)

        self.assertEquals(plain_text, plain)

        # IV supplied ...
        iv = '562e17996d093d28ddb3ba695a2e6f58'
        encrypt = crypto.encryptor(key, iv)
        cipher_text = encrypt(plain_text)
        self.assertNotEquals(plain_text, cipher_text)

        decrypt = crypto.decryptor(key, iv)
        plain = decrypt(cipher_text)

        self.assertEquals(plain_text, plain)


class RevokeCertsTest(test.TestCase):

    def setUp(self):
        super(RevokeCertsTest, self).setUp()
        self.stubs = stubout.StubOutForTesting()

    def tearDown(self):
        self.stubs.UnsetAll()
        super(RevokeCertsTest, self).tearDown()

    @attr(kind='small')
    def test_revoke_cert(self):
        """Test for nova.crypto.revoke_cert. """
        project_id = 'fake'
        file_name = 'test_file'

        self._count = 0
        self._cmd = []
        self._kwargs = []

        def stub_execute(*cmd, **kwargs):
            self._count += 1
            self._cmd.append(cmd)
            self._kwargs.append(kwargs)

        self.stubs.Set(utils, 'execute', stub_execute)

        crypto.revoke_cert(project_id, file_name)
        self.assertEqual(2, self._count)
        self.assertEqual(('openssl', 'ca', '-config', './openssl.cnf',
                          '-revoke', file_name),
                         self._cmd[0])
        self.assertEqual(('openssl', 'ca', '-gencrl', '-config',
                          './openssl.cnf', '-out', FLAGS.crl_file),
                         self._cmd[1])

    def test_revoke_certs_by_user_and_project(self):
        user_id = 'test_user'
        project_id = 2
        file_name = 'test_file'

        def mock_certificate_get_all_by_user_and_project(context,
                                                         user_id,
                                                         project_id):

            return [{"user_id": user_id, "project_id": project_id,
                                          "file_name": file_name}]

        self.stubs.Set(db, 'certificate_get_all_by_user_and_project',
                           mock_certificate_get_all_by_user_and_project)

        self.mox.StubOutWithMock(crypto, 'revoke_cert')
        crypto.revoke_cert(project_id, file_name)

        self.mox.ReplayAll()

        crypto.revoke_certs_by_user_and_project(user_id, project_id)

        self.mox.VerifyAll()

    @attr(kind='small')
    def test_revoke_certs_by_user_and_project_ex_revoke_cert(self):
        """
        All certificates are revoked
        even when exception is raised in revoke_cert()
        """
        self._revoke_count = 0

        def stub_revoke_cert(project_id, file_name):
            self._revoke_count += 1
            if self._revoke_count == 1:
                raise exception.ProcessExecutionError()

        self.mox.StubOutWithMock(db, 'certificate_get_all_by_user_and_project')
        self.stubs.Set(crypto, 'revoke_cert', stub_revoke_cert)
        db.certificate_get_all_by_user_and_project(
                    mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg()).\
                    AndReturn(certificates)
        self.mox.ReplayAll()

        user_id = 'test_user'
        project_id = 'test_project'
        self.assertRaises(exception.RevokeCertException,
                          crypto.revoke_certs_by_user_and_project,
                          user_id, project_id)
        self.assertEqual(2, self._revoke_count)

    def test_revoke_certs_by_user(self):
        user_id = 'test_user'
        project_id = 2
        file_name = 'test_file'

        def mock_certificate_get_all_by_user(context, user_id):

            return [{"user_id": user_id, "project_id": project_id,
                                          "file_name": file_name}]

        self.stubs.Set(db, 'certificate_get_all_by_user',
                                    mock_certificate_get_all_by_user)

        self.mox.StubOutWithMock(crypto, 'revoke_cert')
        crypto.revoke_cert(project_id, mox.IgnoreArg())

        self.mox.ReplayAll()

        crypto.revoke_certs_by_user(user_id)

        self.mox.VerifyAll()

    @attr(kind='small')
    def test_revoke_certs_by_user_ex_revoke_cert(self):
        """
        All certificates are revoked
        even when exception is raised in revoke_cert()
        """
        self._revoke_count = 0

        def stub_revoke_cert(project_id, file_name):
            self._revoke_count += 1
            if self._revoke_count == 1:
                raise exception.ProcessExecutionError()

        self.mox.StubOutWithMock(db, 'certificate_get_all_by_user')
        self.stubs.Set(crypto, 'revoke_cert', stub_revoke_cert)
        db.certificate_get_all_by_user(mox.IgnoreArg(),
                                       mox.IgnoreArg()).AndReturn(certificates)
        self.mox.ReplayAll()

        user_id = 'test_user'
        self.assertRaises(exception.RevokeCertException,
                          crypto.revoke_certs_by_user,
                          user_id)
        self.assertEqual(2, self._revoke_count)

    def test_revoke_certs_by_project(self):
        user_id = 'test_user'
        project_id = 2
        file_name = 'test_file'

        def mock_certificate_get_all_by_project(context, project_id):

            return [{"user_id": user_id, "project_id": project_id,
                                          "file_name": file_name}]

        self.stubs.Set(db, 'certificate_get_all_by_project',
                                    mock_certificate_get_all_by_project)

        self.mox.StubOutWithMock(crypto, 'revoke_cert')
        crypto.revoke_cert(project_id, mox.IgnoreArg())

        self.mox.ReplayAll()

        crypto.revoke_certs_by_project(project_id)

        self.mox.VerifyAll()

    @attr(kind='small')
    def test_revoke_certs_by_project_ex_revoke_cert(self):
        """
        All certificates are revoked
        even when exception is raised in revoke_cert()
        """
        self._revoke_count = 0

        def stub_revoke_cert(project_id, file_name):
            self._revoke_count += 1
            if self._revoke_count == 1:
                raise exception.ProcessExecutionError()

        self.mox.StubOutWithMock(db, 'certificate_get_all_by_project')
        self.stubs.Set(crypto, 'revoke_cert', stub_revoke_cert)
        db.certificate_get_all_by_project(
                                mox.IgnoreArg(), mox.IgnoreArg()).\
                                AndReturn(certificates)
        self.mox.ReplayAll()

        project_id = 'test_project'
        self.assertRaises(exception.RevokeCertException,
                          crypto.revoke_certs_by_project,
                          project_id)
        self.assertEqual(2, self._revoke_count)
