# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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
Tests For nova.flags
"""

import gflags
from nova import flags
from nova import test
from nose.plugins.attrib import attr

FLAGS = flags.FLAGS
flags.DEFINE_string('flags_unittest', 'foo', 'for testing purposes only')


class FlagsValuesTestCase(test.TestCase):

    def setUp(self):
        super(FlagsValuesTestCase, self).setUp()
        self.FLAGS = flags.FlagValues()
        self.global_FLAGS = flags.FLAGS

    def test_define(self):
        self.assert_('string' not in self.FLAGS)
        self.assert_('int' not in self.FLAGS)
        self.assert_('false' not in self.FLAGS)
        self.assert_('true' not in self.FLAGS)

        flags.DEFINE_string('string', 'default', 'desc',
                            flag_values=self.FLAGS)
        flags.DEFINE_integer('int', 1, 'desc', flag_values=self.FLAGS)
        flags.DEFINE_bool('false', False, 'desc', flag_values=self.FLAGS)
        flags.DEFINE_bool('true', True, 'desc', flag_values=self.FLAGS)

        self.assert_(self.FLAGS['string'])
        self.assert_(self.FLAGS['int'])
        self.assert_(self.FLAGS['false'])
        self.assert_(self.FLAGS['true'])
        self.assertEqual(self.FLAGS.string, 'default')
        self.assertEqual(self.FLAGS.int, 1)
        self.assertEqual(self.FLAGS.false, False)
        self.assertEqual(self.FLAGS.true, True)

        argv = ['flags_test',
                '--string', 'foo',
                '--int', '2',
                '--false',
                '--notrue']

        self.FLAGS(argv)
        self.assertEqual(self.FLAGS.string, 'foo')
        self.assertEqual(self.FLAGS.int, 2)
        self.assertEqual(self.FLAGS.false, True)
        self.assertEqual(self.FLAGS.true, False)

    @attr(kind='small')
    def test_call_flags_use_gnu_get_opt(self):
        """
        in case using GNU getopt
        """
        self.FLAGS.UseGnuGetOpt()
        self.assert_('string' not in self.FLAGS)
        self.assert_('int' not in self.FLAGS)
        self.assert_('false' not in self.FLAGS)
        self.assert_('true' not in self.FLAGS)

        flags.DEFINE_string('string', 'default', 'desc',
                            flag_values=self.FLAGS)
        flags.DEFINE_integer('int', 1, 'desc', flag_values=self.FLAGS)
        flags.DEFINE_bool('false', False, 'desc', flag_values=self.FLAGS)
        flags.DEFINE_bool('true', True, 'desc', flag_values=self.FLAGS)

        self.assert_(self.FLAGS['string'])
        self.assert_(self.FLAGS['int'])
        self.assert_(self.FLAGS['false'])
        self.assert_(self.FLAGS['true'])
        self.assertEqual(self.FLAGS.string, 'default')
        self.assertEqual(self.FLAGS.int, 1)
        self.assertEqual(self.FLAGS.false, False)
        self.assertEqual(self.FLAGS.true, True)

        argv = ['flags_test',
                '--string', 'foo',
                '--int', '2',
                '--false',
                '--notrue']

        self.FLAGS(argv)
        self.assertEqual(self.FLAGS.string, 'foo')
        self.assertEqual(self.FLAGS.int, 2)
        self.assertEqual(self.FLAGS.false, True)
        self.assertEqual(self.FLAGS.true, False)

    @attr(kind='small')
    def test_call_exception_unrecognized_flag_error_with_unparsed_args(self):
        """
        exception will not be raised when __call__() is called before DECLARE
        """
        argv = ['flags_test', '--string', 'foo']
        args = self.FLAGS(argv)
        self.assertEqual(['flags_test', 'foo'], args)

    @attr(kind='small')
    def test_call_exception_unrecognized_flag_error_with_unparsed_args_use_gnu_get_opt(self):
        """
        exception will not be raised when __call__() is called before DECLARE in using GNU getopt
        """
        self.FLAGS.UseGnuGetOpt()
        argv = ['flags_test', '--string', 'foo']
        args = self.FLAGS(argv)
        self.assertEqual(['flags_test', 'foo'], args)

    @attr(kind='small')
    def test_call_exception_unrecognized_flag_error_without_unparsed_args(self):
        """
        exception will not be raised when argument of the option is invalid in using GNU getopt
        """
        self.FLAGS.UseGnuGetOpt()
        argv = ['flags_test', '--string']
        args = self.FLAGS(argv)
        self.assertEqual(['flags_test'], args)

    @attr(kind='small')
    def test_getitem_configuration_flag_is_dirty(self):
        """
        ParseNewFlags() is executed before __getitem__() is called
        """
        argv = ['flags_test', '--string', 'foo']
        self.FLAGS(argv)
        self.assertFalse(self.FLAGS.IsDirty('string'))
        
        flags.DEFINE_string('string', 'bar', 'desc',
                            flag_values=self.FLAGS)
        self.assert_(self.FLAGS.IsDirty('string'))
        self.assert_(self.FLAGS['string'])

    @attr(kind='small')
    def test_getattr_configuration_flag_is_dirty(self):
        """
        ParseNewFlags() is executed before __getattr__() is called
        """
        argv = ['flags_test', '--string', 'foo']
        self.FLAGS(argv)
        self.assertFalse(self.FLAGS.IsDirty('string'))
        
        flags.DEFINE_string('string', 'bar', 'desc',
                            flag_values=self.FLAGS)
        self.assert_(self.FLAGS.IsDirty('string'))
        self.assertEqual('foo', self.FLAGS.string)

    def test_declare(self):
        self.assert_('answer' not in self.global_FLAGS)
        flags.DECLARE('answer', 'nova.tests.declare_flags')
        self.assert_('answer' in self.global_FLAGS)
        self.assertEqual(self.global_FLAGS.answer, 42)

        # Make sure we don't overwrite anything
        self.global_FLAGS.answer = 256
        self.assertEqual(self.global_FLAGS.answer, 256)
        flags.DECLARE('answer', 'nova.tests.declare_flags')
        self.assertEqual(self.global_FLAGS.answer, 256)

    @attr(kind='small')
    def test_declare_flags_name_not_in_flag_values(self):
        """
        UnrecognizedFlag is raised when name not in flag_values
        """
        self.assertRaises(gflags.UnrecognizedFlag,
                          flags.DECLARE,
                          'dummy_flag', 'nova.tests.declare_flags')

    def test_runtime_and_unknown_flags(self):
        self.assert_('runtime_answer' not in self.global_FLAGS)

        argv = ['flags_test', '--runtime_answer=60', 'extra_arg']
        args = self.global_FLAGS(argv)
        self.assertEqual(len(args), 2)
        self.assertEqual(args[1], 'extra_arg')

        self.assert_('runtime_answer' not in self.global_FLAGS)

        import nova.tests.runtime_flags

        self.assert_('runtime_answer' in self.global_FLAGS)
        self.assertEqual(self.global_FLAGS.runtime_answer, 60)

    def test_long_vs_short_flags(self):
        flags.DEFINE_string('duplicate_answer_long', 'val', 'desc',
                            flag_values=self.global_FLAGS)
        argv = ['flags_test', '--duplicate_answer=60', 'extra_arg']
        args = self.global_FLAGS(argv)

        self.assert_('duplicate_answer' not in self.global_FLAGS)
        self.assert_(self.global_FLAGS.duplicate_answer_long, 60)

        flags.DEFINE_integer('duplicate_answer', 60, 'desc',
                             flag_values=self.global_FLAGS)
        self.assertEqual(self.global_FLAGS.duplicate_answer, 60)
        self.assertEqual(self.global_FLAGS.duplicate_answer_long, 'val')

    def test_flag_leak_left(self):
        self.assertEqual(FLAGS.flags_unittest, 'foo')
        FLAGS.flags_unittest = 'bar'
        self.assertEqual(FLAGS.flags_unittest, 'bar')

    def test_flag_leak_right(self):
        self.assertEqual(FLAGS.flags_unittest, 'foo')
        FLAGS.flags_unittest = 'bar'
        self.assertEqual(FLAGS.flags_unittest, 'bar')

class StrWrapperTestCase(test.TestCase):

    def setUp(self):
        super(StrWrapperTestCase, self).setUp()
        self.context = flags.FlagValues()
        self.extra_context = flags.FlagValues()

    @attr(kind='small')
    def test_getitem(self):
        flags.DEFINE_string('string', 'default', 'desc',
                            flag_values=self.context)
        flags.DEFINE_integer('int', 1, 'desc',
                             flag_values=self.extra_context)
        wrapper = flags.StrWrapper([self.context,
                                    self.extra_context])
        self.assertEqual('default', wrapper['string'])
        self.assertEqual('1', wrapper['int'])

    @attr(kind='small')
    def test_getitem_exception_key_error(self):
        """
        KeyError is raised when val is not found
        """
        wrapper = flags.StrWrapper([self.context])
        self.assertRaises(KeyError,
                          wrapper.__getitem__,
                          'string')
