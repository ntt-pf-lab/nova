# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 Justin Santa Barbara
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
import os
import tempfile
import socket

import nova
from nova import exception
from nova import flags
from nova import test
from nova import utils

from nose.plugins.attrib import attr
from nova.compute import manager
import sys
import paramiko
from eventlet import greenthread
from nova import context
from nova import db
import lockfile

FLAGS = flags.FLAGS

flags.DEFINE_string('test_backend', 'DumyBackend',
                    'The backend to use for test')


class ExecuteTestCase(test.TestCase):
    def test_retry_on_failure(self):
        fd, tmpfilename = tempfile.mkstemp()
        _, tmpfilename2 = tempfile.mkstemp()
        try:
            fp = os.fdopen(fd, 'w+')
            fp.write('''#!/bin/sh
# If stdin fails to get passed during one of the runs, make a note.
if ! grep -q foo
then
    echo 'failure' > "$1"
fi
# If stdin has failed to get passed during this or a previous run, exit early.
if grep failure "$1"
then
    exit 1
fi
runs="$(cat $1)"
if [ -z "$runs" ]
then
    runs=0
fi
runs=$(($runs + 1))
echo $runs > "$1"
exit 1
''')
            fp.close()
            os.chmod(tmpfilename, 0755)
            self.assertRaises(exception.ProcessExecutionError,
                              utils.execute,
                              tmpfilename, tmpfilename2, attempts=10,
                              process_input='foo',
                              delay_on_retry=False)
            fp = open(tmpfilename2, 'r+')
            runs = fp.read()
            fp.close()
            self.assertNotEquals(runs.strip(), 'failure', 'stdin did not '
                                                          'always get passed '
                                                          'correctly')
            runs = int(runs.strip())
            self.assertEquals(runs, 10,
                              'Ran %d times instead of 10.' % (runs,))
        finally:
            os.unlink(tmpfilename)
            os.unlink(tmpfilename2)

    @attr(kind='small')
    def test_unknown_kwargs_raises_error(self):
        self.assertRaises(exception.InvalidInput,
                          utils.execute,
                          '/bin/true', this_is_not_a_valid_kwarg=True)

    def test_no_retry_on_success(self):
        fd, tmpfilename = tempfile.mkstemp()
        _, tmpfilename2 = tempfile.mkstemp()
        try:
            fp = os.fdopen(fd, 'w+')
            fp.write('''#!/bin/sh
# If we've already run, bail out.
grep -q foo "$1" && exit 1
# Mark that we've run before.
echo foo > "$1"
# Check that stdin gets passed correctly.
grep foo
''')
            fp.close()
            os.chmod(tmpfilename, 0755)
            utils.execute(tmpfilename,
                          tmpfilename2,
                          process_input='foo',
                          attempts=2)
        finally:
            os.unlink(tmpfilename)
            os.unlink(tmpfilename2)


class GetFromPathTestCase(test.TestCase):
    def test_tolerates_nones(self):
        f = utils.get_from_path

        input = []
        self.assertEquals([], f(input, "a"))
        self.assertEquals([], f(input, "a/b"))
        self.assertEquals([], f(input, "a/b/c"))

        input = [None]
        self.assertEquals([], f(input, "a"))
        self.assertEquals([], f(input, "a/b"))
        self.assertEquals([], f(input, "a/b/c"))

        input = [{'a': None}]
        self.assertEquals([], f(input, "a"))
        self.assertEquals([], f(input, "a/b"))
        self.assertEquals([], f(input, "a/b/c"))

        input = [{'a': {'b': None}}]
        self.assertEquals([{'b': None}], f(input, "a"))
        self.assertEquals([], f(input, "a/b"))
        self.assertEquals([], f(input, "a/b/c"))

        input = [{'a': {'b': {'c': None}}}]
        self.assertEquals([{'b': {'c': None}}], f(input, "a"))
        self.assertEquals([{'c': None}], f(input, "a/b"))
        self.assertEquals([], f(input, "a/b/c"))

        input = [{'a': {'b': {'c': None}}}, {'a': None}]
        self.assertEquals([{'b': {'c': None}}], f(input, "a"))
        self.assertEquals([{'c': None}], f(input, "a/b"))
        self.assertEquals([], f(input, "a/b/c"))

        input = [{'a': {'b': {'c': None}}}, {'a': {'b': None}}]
        self.assertEquals([{'b': {'c': None}}, {'b': None}], f(input, "a"))
        self.assertEquals([{'c': None}], f(input, "a/b"))
        self.assertEquals([], f(input, "a/b/c"))

    def test_does_select(self):
        f = utils.get_from_path

        input = [{'a': 'a_1'}]
        self.assertEquals(['a_1'], f(input, "a"))
        self.assertEquals([], f(input, "a/b"))
        self.assertEquals([], f(input, "a/b/c"))

        input = [{'a': {'b': 'b_1'}}]
        self.assertEquals([{'b': 'b_1'}], f(input, "a"))
        self.assertEquals(['b_1'], f(input, "a/b"))
        self.assertEquals([], f(input, "a/b/c"))

        input = [{'a': {'b': {'c': 'c_1'}}}]
        self.assertEquals([{'b': {'c': 'c_1'}}], f(input, "a"))
        self.assertEquals([{'c': 'c_1'}], f(input, "a/b"))
        self.assertEquals(['c_1'], f(input, "a/b/c"))

        input = [{'a': {'b': {'c': 'c_1'}}}, {'a': None}]
        self.assertEquals([{'b': {'c': 'c_1'}}], f(input, "a"))
        self.assertEquals([{'c': 'c_1'}], f(input, "a/b"))
        self.assertEquals(['c_1'], f(input, "a/b/c"))

        input = [{'a': {'b': {'c': 'c_1'}}},
                 {'a': {'b': None}}]
        self.assertEquals([{'b': {'c': 'c_1'}}, {'b': None}], f(input, "a"))
        self.assertEquals([{'c': 'c_1'}], f(input, "a/b"))
        self.assertEquals(['c_1'], f(input, "a/b/c"))

        input = [{'a': {'b': {'c': 'c_1'}}},
                 {'a': {'b': {'c': 'c_2'}}}]
        self.assertEquals([{'b': {'c': 'c_1'}}, {'b': {'c': 'c_2'}}],
                          f(input, "a"))
        self.assertEquals([{'c': 'c_1'}, {'c': 'c_2'}], f(input, "a/b"))
        self.assertEquals(['c_1', 'c_2'], f(input, "a/b/c"))

        self.assertEquals([], f(input, "a/b/c/d"))
        self.assertEquals([], f(input, "c/a/b/d"))
        self.assertEquals([], f(input, "i/r/t"))

    def test_flattens_lists(self):
        f = utils.get_from_path

        input = [{'a': [1, 2, 3]}]
        self.assertEquals([1, 2, 3], f(input, "a"))
        self.assertEquals([], f(input, "a/b"))
        self.assertEquals([], f(input, "a/b/c"))

        input = [{'a': {'b': [1, 2, 3]}}]
        self.assertEquals([{'b': [1, 2, 3]}], f(input, "a"))
        self.assertEquals([1, 2, 3], f(input, "a/b"))
        self.assertEquals([], f(input, "a/b/c"))

        input = [{'a': {'b': [1, 2, 3]}}, {'a': {'b': [4, 5, 6]}}]
        self.assertEquals([1, 2, 3, 4, 5, 6], f(input, "a/b"))
        self.assertEquals([], f(input, "a/b/c"))

        input = [{'a': [{'b': [1, 2, 3]}, {'b': [4, 5, 6]}]}]
        self.assertEquals([1, 2, 3, 4, 5, 6], f(input, "a/b"))
        self.assertEquals([], f(input, "a/b/c"))

        input = [{'a': [1, 2, {'b': 'b_1'}]}]
        self.assertEquals([1, 2, {'b': 'b_1'}], f(input, "a"))
        self.assertEquals(['b_1'], f(input, "a/b"))

    @attr(kind='small')
    def test_bad_xpath(self):
        f = utils.get_from_path

        self.assertRaises(exception.InvalidInput, f, [], None)
        self.assertRaises(exception.InvalidInput, f, [], "")
        self.assertRaises(exception.InvalidInput, f, [], "/")
        self.assertRaises(exception.InvalidInput, f, [], "/a")
        self.assertRaises(exception.InvalidInput, f, [], "/a/")
        self.assertRaises(exception.InvalidInput, f, [], "//")
        self.assertRaises(exception.InvalidInput, f, [], "//a")
        self.assertRaises(exception.InvalidInput, f, [], "a//a")
        self.assertRaises(exception.InvalidInput, f, [], "a//a/")
        self.assertRaises(exception.InvalidInput, f, [], "a/a/")

    def test_real_failure1(self):
        # Real world failure case...
        #  We weren't coping when the input was a Dictionary instead of a List
        # This led to test_accepts_dictionaries
        f = utils.get_from_path

        inst = {'fixed_ip': {'floating_ips': [{'address': '1.2.3.4'}],
                             'address': '192.168.0.3'},
                'hostname': ''}

        private_ips = f(inst, 'fixed_ip/address')
        public_ips = f(inst, 'fixed_ip/floating_ips/address')
        self.assertEquals(['192.168.0.3'], private_ips)
        self.assertEquals(['1.2.3.4'], public_ips)

    def test_accepts_dictionaries(self):
        f = utils.get_from_path

        input = {'a': [1, 2, 3]}
        self.assertEquals([1, 2, 3], f(input, "a"))
        self.assertEquals([], f(input, "a/b"))
        self.assertEquals([], f(input, "a/b/c"))

        input = {'a': {'b': [1, 2, 3]}}
        self.assertEquals([{'b': [1, 2, 3]}], f(input, "a"))
        self.assertEquals([1, 2, 3], f(input, "a/b"))
        self.assertEquals([], f(input, "a/b/c"))

        input = {'a': [{'b': [1, 2, 3]}, {'b': [4, 5, 6]}]}
        self.assertEquals([1, 2, 3, 4, 5, 6], f(input, "a/b"))
        self.assertEquals([], f(input, "a/b/c"))

        input = {'a': [1, 2, {'b': 'b_1'}]}
        self.assertEquals([1, 2, {'b': 'b_1'}], f(input, "a"))
        self.assertEquals(['b_1'], f(input, "a/b"))


class GenericUtilsTestCase(test.TestCase):
    def test_parse_server_string(self):
        result = utils.parse_server_string('::1')
        self.assertEqual(('::1', ''), result)
        result = utils.parse_server_string('[::1]:8773')
        self.assertEqual(('::1', '8773'), result)
        result = utils.parse_server_string('2001:db8::192.168.1.1')
        self.assertEqual(('2001:db8::192.168.1.1', ''), result)
        result = utils.parse_server_string('[2001:db8::192.168.1.1]:8773')
        self.assertEqual(('2001:db8::192.168.1.1', '8773'), result)
        result = utils.parse_server_string('192.168.1.1')
        self.assertEqual(('192.168.1.1', ''), result)
        result = utils.parse_server_string('192.168.1.2:8773')
        self.assertEqual(('192.168.1.2', '8773'), result)
        result = utils.parse_server_string('192.168.1.3')
        self.assertEqual(('192.168.1.3', ''), result)
        result = utils.parse_server_string('www.example.com:8443')
        self.assertEqual(('www.example.com', '8443'), result)
        result = utils.parse_server_string('www.example.com')
        self.assertEqual(('www.example.com', ''), result)
        # error case
        result = utils.parse_server_string('www.exa:mple.com:8443')
        self.assertEqual(('', ''), result)

    def test_bool_from_str(self):
        self.assertTrue(utils.bool_from_str('1'))
        self.assertTrue(utils.bool_from_str('2'))
        self.assertTrue(utils.bool_from_str('-1'))
        self.assertTrue(utils.bool_from_str('true'))
        self.assertTrue(utils.bool_from_str('True'))
        self.assertTrue(utils.bool_from_str('tRuE'))
        self.assertFalse(utils.bool_from_str('False'))
        self.assertFalse(utils.bool_from_str('false'))
        self.assertFalse(utils.bool_from_str('0'))
        self.assertFalse(utils.bool_from_str(None))
        self.assertFalse(utils.bool_from_str('junk'))


class IsUUIDLikeTestCase(test.TestCase):
    def assertUUIDLike(self, val, expected):
        result = utils.is_uuid_like(val)
        self.assertEqual(result, expected)

    def test_good_uuid(self):
        val = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        self.assertUUIDLike(val, True)

    def test_integer_passed(self):
        val = 1
        self.assertUUIDLike(val, False)

    def test_non_uuid_string_passed(self):
        val = 'foo-fooo'
        self.assertUUIDLike(val, False)


class ToPrimitiveTestCase(test.TestCase):
    def test_list(self):
        self.assertEquals(utils.to_primitive([1, 2, 3]), [1, 2, 3])

    def test_empty_list(self):
        self.assertEquals(utils.to_primitive([]), [])

    def test_tuple(self):
        self.assertEquals(utils.to_primitive((1, 2, 3)), [1, 2, 3])

    def test_dict(self):
        self.assertEquals(utils.to_primitive(dict(a=1, b=2, c=3)),
                          dict(a=1, b=2, c=3))

    def test_empty_dict(self):
        self.assertEquals(utils.to_primitive({}), {})

    def test_datetime(self):
        x = datetime.datetime(1, 2, 3, 4, 5, 6, 7)
        self.assertEquals(utils.to_primitive(x), "0001-02-03 04:05:06.000007")

    def test_iter(self):
        class IterClass(object):
            def __init__(self):
                self.data = [1, 2, 3, 4, 5]
                self.index = 0

            def __iter__(self):
                return self

            def next(self):
                if self.index == len(self.data):
                    raise StopIteration
                self.index = self.index + 1
                return self.data[self.index - 1]

        x = IterClass()
        self.assertEquals(utils.to_primitive(x), [1, 2, 3, 4, 5])

    def test_iteritems(self):
        class IterItemsClass(object):
            def __init__(self):
                self.data = dict(a=1, b=2, c=3).items()
                self.index = 0

            def __iter__(self):
                return self

            def next(self):
                if self.index == len(self.data):
                    raise StopIteration
                self.index = self.index + 1
                return self.data[self.index - 1]

        x = IterItemsClass()
        ordered = utils.to_primitive(x)
        ordered.sort()
        self.assertEquals(ordered, [['a', 1], ['b', 2], ['c', 3]])

    def test_instance(self):
        class MysteryClass(object):
            a = 10

            def __init__(self):
                self.b = 1

        x = MysteryClass()
        self.assertEquals(utils.to_primitive(x, convert_instances=True),
                          dict(b=1))

        self.assertEquals(utils.to_primitive(x), x)

    def test_typeerror(self):
        x = bytearray  # Class, not instance
        self.assertEquals(utils.to_primitive(x), u"<type 'bytearray'>")

    def test_nasties(self):
        def foo():
            pass
        x = [datetime, foo, dir]
        ret = utils.to_primitive(x)
        self.assertEquals(len(ret), 3)
        self.assertTrue(ret[0].startswith(u"<module 'datetime' from "))
        self.assertTrue(ret[1].startswith(u'<function foo at 0x'))
        self.assertEquals(ret[2], u'<built-in function dir>')


class MonkeyPatchTestCase(test.TestCase):
    """Unit test for utils.monkey_patch()."""
    def setUp(self):
        super(MonkeyPatchTestCase, self).setUp()
        self.example_package = 'nova.tests.monkey_patch_example.'
        self.flags(
            monkey_patch=True,
            monkey_patch_modules=[self.example_package + 'example_a' + ':'
            + self.example_package + 'example_decorator'])

    def test_monkey_patch(self):
        utils.monkey_patch()
        nova.tests.monkey_patch_example.CALLED_FUNCTION = []
        from nova.tests.monkey_patch_example import example_a, example_b

        self.assertEqual('Example function', example_a.example_function_a())
        exampleA = example_a.ExampleClassA()
        exampleA.example_method()
        ret_a = exampleA.example_method_add(3, 5)
        self.assertEqual(ret_a, 8)

        self.assertEqual('Example function', example_b.example_function_b())
        exampleB = example_b.ExampleClassB()
        exampleB.example_method()
        ret_b = exampleB.example_method_add(3, 5)

        self.assertEqual(ret_b, 8)
        package_a = self.example_package + 'example_a.'
        self.assertTrue(package_a + 'example_function_a'
            in nova.tests.monkey_patch_example.CALLED_FUNCTION)

        self.assertTrue(package_a + 'ExampleClassA.example_method'
            in nova.tests.monkey_patch_example.CALLED_FUNCTION)
        self.assertTrue(package_a + 'ExampleClassA.example_method_add'
            in nova.tests.monkey_patch_example.CALLED_FUNCTION)
        package_b = self.example_package + 'example_b.'
        self.assertFalse(package_b + 'example_function_b'
            in nova.tests.monkey_patch_example.CALLED_FUNCTION)
        self.assertFalse(package_b + 'ExampleClassB.example_method'
            in nova.tests.monkey_patch_example.CALLED_FUNCTION)
        self.assertFalse(package_b + 'ExampleClassB.example_method_add'
            in nova.tests.monkey_patch_example.CALLED_FUNCTION)


class UtilsTestCase(test.TestCase):
    """Test for nova.utils """
    def setUp(self):
        super(UtilsTestCase, self).setUp()
        self.utils = utils
        self.utils.clear_time_override()

    @attr(kind='small')
    def test_abspath(self):
        """Test for nova.utils.abspath.
        Return a abstract path base on nova's path"""

        s = 'abc'
        ref = self.utils.abspath(s)
        self.assertTrue(ref.endswith(s))
        self.assertTrue(ref.find('nova') > 0)

    @attr(kind='small')
    def test_abspath_parameter_fullpath(self):
        """Test for nova.utils.abspath. Make sure full path be returned"""

        s = os.path.sep + 'home'
        ref = self.utils.abspath(s)
        self.assertEqual(s, ref)

    @attr(kind='small')
    def test_advance_time_delta(self):
        """Test for nova.utils.advance_time_delta. Make sure time be shift"""

        sec = 60
        ref = self.utils.utcnow()

        self.utils.set_time_override(ref)
        self.utils.advance_time_delta(
                        timedelta=datetime.timedelta(seconds=sec))

        self.assertEqual(datetime.timedelta(seconds=sec),
                         self.utils.utcnow.override_time - ref)

    @attr(kind='small')
    def test_advance_time_delta_exception(self):
        """Test for nova.utils.advance_time_delta.
        Make sure assertion error be raised when override_time is None"""

        self.utils.clear_time_override()

        self.assertRaises(AssertionError,
            self.utils.advance_time_delta, datetime.timedelta(seconds=10))

    @attr(kind='small')
    def test_advance_time_delta_parameter(self):
        """Test for nova.utils.advance_time_delta.
        Make sure the shift time can be minus and zero"""

        # test minus delta
        sec = -60
        delta = datetime.timedelta(seconds=sec)

        ref = self.utils.utcnow()

        self.utils.set_time_override(ref)
        self.utils.advance_time_delta(delta)

        self.assertEqual(delta,
                         (self.utils.utcnow.override_time - ref))

        # test 0 delta
        delta = datetime.timedelta(seconds=0)

        ref = self.utils.utcnow()

        self.utils.set_time_override(ref)
        self.utils.advance_time_delta(delta)

        self.assertEqual(delta,
                         (self.utils.utcnow.override_time - ref))

    @attr(kind='small')
    def test_advance_time_seconds(self):
        """Test for nova.utils.advance_time_seconds.
        Make sure time be shift by second"""

        # test minus delta
        sec = 60
        delta = datetime.timedelta(seconds=sec)

        ref = self.utils.utcnow()
        self.utils.set_time_override(ref)

        self.utils.advance_time_seconds(seconds=sec)

        self.assertEqual(delta,
                         (self.utils.utcnow.override_time - ref))

    @attr(kind='small')
    def test_advance_time_seconds_parameter(self):
        """Test for nova.utils.advance_time_seconds.
        Make sure the shift time can be minus """

        # test minus delta
        sec = -60
        delta = datetime.timedelta(seconds=sec)

        ref = self.utils.utcnow()
        self.utils.set_time_override(ref)

        self.utils.advance_time_seconds(seconds=sec)

        self.assertEqual(delta,
                         (self.utils.utcnow.override_time - ref))

    @attr(kind='small')
    def test_advance_time_seconds_exception(self):
        """Test for nova.utils.advance_time_seconds.
        Raises AssertionError if override_time is None"""

        self.utils.clear_time_override()

        self.assertRaises(AssertionError,
            self.utils.advance_time_seconds, seconds=10)

    @attr(kind='small')
    def test_bool_from_str(self):
        """Test for nova.utils.bool_from_str.
        Return boolean True if input is 'true'"""

        ref = self.utils.bool_from_str('true')
        self.assertEqual(True, ref)

    @attr(kind='small')
    def test_bool_from_str_parameter(self):
        """Test for nova.utils.bool_from_str.
        Verify the parameter can be string, int and bool"""

        # string
        ref = self.utils.bool_from_str(val='0')
        self.assertEqual(False, ref)

        ref = self.utils.bool_from_str(val='1')
        self.assertEqual(True, ref)

        ref = self.utils.bool_from_str(val='false')
        self.assertEqual(False, ref)

        ref = self.utils.bool_from_str(val='true')
        self.assertEqual(True, ref)

        ref = self.utils.bool_from_str(val='False')
        self.assertEqual(False, ref)

        ref = self.utils.bool_from_str(val='True')
        self.assertEqual(True, ref)

        # int
        ref = self.utils.bool_from_str(val=0)
        self.assertEqual(False, ref)

        ref = self.utils.bool_from_str(val=1)
        self.assertEqual(True, ref)

        # bool
        ref = self.utils.bool_from_str(val=False)
        self.assertEqual(False, ref)

        ref = self.utils.bool_from_str(val=True)
        self.assertEqual(True, ref)

        # invalid
        ref = self.utils.bool_from_str(val='ABCD')
        self.assertEqual(False, ref)

    @attr(kind='small')
    def test_check_isinstance(self):
        """Test for nova.utils.check_isinstance. Verify int type parameter"""
        param = 1
        ref = self.utils.check_isinstance(obj=param, cls=int)
        self.assertEqual(param, ref)

    @attr(kind='small')
    def test_check_isinstance_parameter(self):
        """Test for nova.utils.check_isinstance.
        Verify string , map and object type's parameters"""

        # str type
        param = dict(obj='abcd', cls=str)
        ref = self.utils.check_isinstance(**param)
        self.assertEqual(param['obj'], ref)

        # dict type
        param = dict(obj={'key': 'value'}, cls=dict)
        ref = self.utils.check_isinstance(**param)
        self.assertEqual(param['obj'], ref)

        # nova.compute object type
        param = dict(obj=manager.ComputeManager(),
                     cls=manager.ComputeManager)
        ref = self.utils.check_isinstance(**param)
        self.assertEqual(param['obj'], ref)

    @attr(kind='small')
    def test_check_isinstance_exception(self):
        """Test for nova.utils.check_isinstance.
        Exception be raised if instance type is dismatching"""

        self.assertRaises(exception.InvalidInput,
            self.utils.check_isinstance, 1, str)

    @attr(kind='small')
    def test_clear_time_override(self):
        """Test for nova.utils.clear_time_override.
        Make sure 'override_time' attribute be None"""

        ref = self.utils.utcnow()
        self.utils.set_time_override(ref)
        self.assertEqual(self.utils.utcnow.override_time, ref)

        self.utils.clear_time_override()

        self.assertEqual(None, self.utils.utcnow.override_time)

    @attr(kind='small')
    def test_convert_to_list_dict(self):
        """Test for nova.utils.convert_to_list_dict.
        Return a list like [ {label:lst[0]}, {label:lst[1]} ]"""

        key = 'a'
        alist = 'b'
        param = dict(lst=alist, label=key)

        ref = self.utils.convert_to_list_dict(**param)

        self.assertEqual({key: alist[0]}, ref[0])

    @attr(kind='small')
    def test_convert_to_list_dict_parameter(self):
        """Test for nova.utils.convert_to_list_dict.
        Verify parameter with multiple elements"""

        key = 'a'
        alist = ['1', '2']
        ref = self.utils.convert_to_list_dict(lst=alist, label=key)
        self.assertEqual({key: alist[0]}, ref[0])
        self.assertEqual({key: alist[1]}, ref[1])

    @attr(kind='small')
    def test_debug(self):
        """Test for nova.utils.debug.
        Make sure parameter be written to logger and be returned"""

        m = 'abc'

        def _fake_debug(msg, arg):
            self.assertEqual(m, arg)

        self.stubs.Set(utils.LOG, 'debug', _fake_debug)

        ref = self.utils.debug(arg=m)
        self.assertEqual(m, ref)

    @attr(kind='small')
    def test_default_flagfile(self):
        """Test for nova.utils.default_flagfile.
        --flagfile be add to args parameter if specified conf file exist """

        param = dict(filename='nova.conf', args=['arg1=1'])
        self.utils.default_flagfile(**param)

        # args not be changed because specified file not exist
        self.assertEqual(1, len(param['args']))

    @attr(kind='small')
    def test_default_flagfile_parameter_with_flagfile(self):
        """Test for nova.utils.default_flagfile.
        paremeter args has include flagfile"""

        param = dict(filename=self.utils.__file__, args=['flagfile=/1'])
        self.utils.default_flagfile(**param)

        # not be changed if has included
        self.assertEqual(1, len(param['args']))

    @attr(kind='small')
    def test_default_flagfile_parameter_conf_exist(self):
        """Test for nova.utils.default_flagfile.
        The file exist specified by filename"""

        param = dict(filename=self.utils.__file__, args=['arg1=1'])
        self.utils.default_flagfile(**param)

        self.assertEqual(2, len(param['args']))

    @attr(kind='small')
    def test_dumps(self):
        """Test for nova.utils.dumps. The input be convert to json format"""

        param = dict(value='abc')
        ref = self.utils.dumps(**param)

        self.assertEqual('"' + param['value'] + '"', ref)

    @attr(kind='small')
    def test_dumps_parameter_int(self):
        """Test for nova.utils.dumps. Verify int type"""

        param = dict(value=1)
        ref = self.utils.dumps(**param)

        self.assertEqual(str(param['value']), ref)

    @attr(kind='small')
    def test_dumps_parameter_dict(self):
        """Test for nova.utils.dumps. Verify dict type"""

        d1 = dict(a='123')
        param = dict(value=d1)
        ref = self.utils.dumps(**param)

        self.assertEqual('{"a": "123"}', ref)

    @attr(kind='small')
    def test_dumps_parameter_list(self):
        """Test for nova.utils.dumps. Verify list type"""

        d1 = ['123']
        param = dict(value=d1)
        ref = self.utils.dumps(**param)

        self.assertEqual('["123"]', ref)

    @attr(kind='small')
    def test_dumps_parameter_listdic(self):
        """Test for nova.utils.dumps. Verify list-dict type"""

        d1 = [dict(a='123', b='XXX'), dict(a='456')]
        param = dict(value=d1)
        ref = self.utils.dumps(**param)

        self.assertEqual('[{"a": "123", "b": "XXX"}, {"a": "456"}]', ref)

    @attr(kind='small')
    def test_dumps_parameter_exception(self):
        """Test for nova.utils.dumps. Verify object type"""

        d1 = self.utils
        param = dict(value=d1)
        ref = self.utils.dumps(**param)

        # do not raise exception if type error occured
        self.assertTrue(ref.startswith('"<module \'nova.utils\' from \''))

    @attr(kind='small')
    def test_execute(self):
        """Test for nova.utils.execute. Verify returned stdout and stderr"""

        cmd = 'dir'
        kwargs = dict()

        ref = self.utils.execute(cmd, **kwargs)

        self.assertTrue(len(ref[0]))
        self.assertEqual('', ref[1])

    @attr(kind='small')
    def test_execute_parameter_with_input(self):
        """Test for nova.utils.execute.
        Verify process_input parameter be passed to command"""

        stdinput = 'input something'

        def _fake_communicate(self, *process_input):
            stdout = stdinput
            stderr = ''
            # success return
            self.returncode = 0
            return (stdout, stderr)

        self.stubs.Set(utils.subprocess.Popen, 'communicate',
                       _fake_communicate)

        cmd = 'dir'
        kwargs = dict(process_input=stdinput)

        ref = self.utils.execute(cmd, **kwargs)

        self.assertEqual(stdinput, ref[0])
        self.assertEqual('', ref[1])

    def test_execute_parameter_with_exitcode(self):
        """Test for nova.utils.execute.
        As success if command's returncode equal inputed check_exit_code"""

        stdinput = 'cmd is ok'

        def _fake_communicate(self, *process_input):
            stdout = stdinput
            stderr = ''
            # as success return
            self.returncode = 999
            return (stdout, stderr)

        self.stubs.Set(utils.subprocess.Popen, 'communicate',
                       _fake_communicate)

        cmd = 'dir'
        kwargs = dict(check_exit_code=999)

        ref = self.utils.execute(cmd, **kwargs)

        self.assertEqual(stdinput, ref[0])
        self.assertEqual('', ref[1])

    def test_execute_parameter_with_root(self):
        """Test for nova.utils.execute. Verify sudo be add to command """

        def _fake_debug(msg, arg):
            self.assertEqual(True, arg.startswith('sudo'))
            # exit without execute command
            raise exception.ProcessExecutionError

        self.stubs.Set(utils.LOG, 'debug', _fake_debug)

        cmd = 'dir'
        kwargs = dict(run_as_root=True)

        self.assertRaises(exception.ProcessExecutionError,
                         self.utils.execute, cmd, **kwargs)

    @attr(kind='small')
    def test_execute_exception_io(self):
        """Test for nova.utils.execute.
        Verify IOError be cast to ProcessExecutionError"""

        def _fake_communicate(self, *process_input):
            raise IOError

        self.stubs.Set(utils.subprocess.Popen, 'communicate',
                       _fake_communicate)

        cmd = 'dir'
        kwargs = dict(check_exit_code=999)

        self.assertRaises(exception.ProcessExecutionError,
            self.utils.execute, cmd, **kwargs)

    @attr(kind='small')
    def test_execute_exception_retry(self):
        """Test for nova.utils.execute.
        Verify raise ProcessExecutionError after retry if error"""

        def _fake_communicate(self, *process_input):
            raise exception.ProcessExecutionError

        self.stubs.Set(utils.subprocess.Popen, 'communicate',
                       _fake_communicate)

        cmd = 'dir'
        kwargs = dict(attempts=2, delay_on_retry=True)

        self.assertRaises(exception.ProcessExecutionError,
            self.utils.execute, cmd, **kwargs)

    @attr(kind='small')
    def test_execute_exception_exit(self):
        """Test for nova.utils.execute.
        Verify raise ProcessExecutionError if returncode not be zero"""

        def _fake_communicate(self, *process_input):
            stdout = ''
            stderr = 'error:1'
            # failure return
            self.returncode = 1
            return (stdout, stderr)

        self.stubs.Set(utils.subprocess.Popen, 'communicate',
                       _fake_communicate)

        cmd = 'dir'
        kwargs = dict()

        self.assertRaises(exception.ProcessExecutionError,
            self.utils.execute, cmd, **kwargs)

    @attr(kind='small')
    def test_execute_exception_param(self):
        """Test for nova.utils.execute.
        Verify raise exception if parameter has unknown keyword"""

        def _fake_communicate(self, *process_input):
            stdout = 'out'
            stderr = ''
            # success return
            self.returncode = 0
            return (stdout, stderr)

        self.stubs.Set(utils.subprocess.Popen, 'communicate',
                       _fake_communicate)

        cmd = 'dir'
        kwargs = dict(unknown_param='invalid')

        self.assertRaises(exception.InvalidInput,
            self.utils.execute, cmd, **kwargs)

    @attr(kind='small')
    def test_fetchfile_exception(self):
        """Test for nova.utils.fetchfile.
        Should raise ProcessExecutionError if some error occured"""

        def _fake_execute(self, *cmd, **kwargs):
            raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', _fake_execute)

        self.assertRaises(exception.ProcessExecutionError,
            self.utils.fetchfile, 'locallhost', 'target')

    @attr(kind='small')
    def test_flatten_dict(self):
        """Test for nova.utils.flatten_dict. Convert nest dict to a dict"""
        f = dict(b=1)
        d = dict(a=f, c={'b': 1})

        ref = self.utils.flatten_dict(dict_=d, flattened=f)
        self.assertEqual(f, ref)

    @attr(kind='small')
    def test_gen_uuid(self):
        """Test for nova.utils.gen_uuid. Verify a uuid be generated"""

        ref = self.utils.gen_uuid()
        self.assertEqual(36, len(str(ref)))
        self.assertEqual(True, self.utils.is_uuid_like(str(ref)))

    @attr(kind='small')
    def test_generate_password(self):
        """Test for nova.utils.generate_password.
        Make sure password is specified length, include specified characters"""

        param = dict(length=20)
        param['symbols'] =\
                '23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
        ref = self.utils.generate_password(**param)
        self.assertEqual(param['length'], len(ref))
        for c in ref:
            self.assertTrue(param['symbols'].find(c) >= 0)

    @attr(kind='small')
    def test_generate_password_parameter(self):
        """Test for nova.utils.generate_password.
        Make sure password is specified length"""

        param = dict(length=50)
        param['symbols'] =\
                '23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
        ref = self.utils.generate_password(**param)
        self.assertEqual(param['length'], len(ref))
        for c in ref:
            self.assertTrue(param['symbols'].find(c) >= 0)

    @attr(kind='small')
    def test_generate_uid(self):
        """Test for nova.utils.generate_uid. Return topic-XXXX format string"""

        param = dict(topic='nova', size=10)
        ref = self.utils.generate_uid(**param)
        self.assertEqual(len(param['topic']) + 1 + param['size'], len(ref))
        self.assertTrue(ref.startswith(param['topic'] + '-'))

    @attr(kind='small')
    def test_get_from_path_exception(self):
        """Test for nova.utils.get_from_path.
        Raise Error if is a full path"""

        param = dict(items=[], path='/xml/root/')
        self.assertRaises(exception.InvalidInput,
            self.utils.get_from_path, **param)

    @attr(kind='small')
    def test_get_my_linklocal(self):
        """Test for nova.utils.get_my_linklocal.
        Get ipv6 address by ip -f inet6 command"""

        ip = 'fe80::20c:29ff:fecc:bf0f'

        def _fake_execute(self, *cmd, **kwargs):
            stdout = ''
            stdin = '2: eth0    inet6 ' + ip + '/64 ' +\
                'scope link \\       valid_lft forever preferred_lft forever'
            result = (stdin, stdout)
            return result

        self.stubs.Set(utils, 'execute', _fake_execute)

        ref = self.utils.get_my_linklocal('eth0')

        self.assertEqual(ip, ref)

    @attr(kind='small')
    def test_get_my_linklocal_exception_ipnotfound(self):
        """Test for nova.utils.get_my_linklocal.
        Raise Error if can not get ip by command"""

        ip = ''

        def _fake_execute(self, *cmd, **kwargs):
            stdout = ''
            stdin = '2: eth0    inet6 ' + ip + '/64 ' +\
                'scope link \\       valid_lft forever preferred_lft forever'
            result = (stdin, stdout)
            return result

        self.stubs.Set(utils, 'execute', _fake_execute)

        self.assertRaises(exception.LinkIpNotFound,
            self.utils.get_my_linklocal, 'interface1')

    @attr(kind='small')
    def test_get_my_linklocal_exception_cmd(self):
        """Test for nova.utils.get_my_linklocal.
        Raise Error if command execute failure"""

        def _fake_execute(self, *cmd, **kwargs):
            raise exception.ProcessExecutionError

        self.stubs.Set(utils, 'execute', _fake_execute)

        self.assertRaises(exception.LinkIpNotFound,
            self.utils.get_my_linklocal, 'interface1')

    @attr(kind='small')
    def test_import_class(self):
        """Test for nova.utils.import_class. Return a class instance"""

        p = 'nova.compute.api.API'
        ref = self.utils.import_class(p)

        self.assertEqual(p.split('.')[-1], ref.__name__)

    @attr(kind='small')
    def test_import_class_parameter_just_module(self):
        """Test for nova.utils.import_class. Return a module instance"""

        p = 'nova.utils'
        ref = self.utils.import_class(p)

        self.assertEqual(p, ref.__name__)

    @attr(kind='small')
    def test_import_class_exception(self):
        """Test for nova.utils.import_class.
        Raise ClassNotFound if not exist"""

        p = 'nova.utils.NotExistClass'
        self.assertRaises(exception.ClassNotFound,
            self.utils.import_class, p)

    @attr(kind='small')
    def test_import_object(self):
        """Test for nova.utils.import_object. Return a module instance"""

        p = 'nova.utils'
        ref = self.utils.import_object(import_str=p)
        self.assertEqual(p, ref.__name__)

    @attr(kind='small')
    def test_import_object_parameter_with_class(self):
        """Test for nova.utils.import_object. Return a class instance"""

        p = 'nova.compute.api.API'
        ref = self.utils.import_object(import_str=p)

        self.assertEqual(p.split('.')[-1], ref.__class__.__name__)

    @attr(kind='small')
    def test_import_object_exception(self):
        """Test for nova.utils.import_object.
        Raise ClassNotFound if not exist"""

        p = 'nova.notexist.Class'
        self.assertRaises(exception.ClassNotFound,
            self.utils.import_object, import_str=p)

    @attr(kind='small')
    def test_is_older_than(self):
        """Test for nova.utils.is_older_than. Verify datetime comparing"""

        diff = 10
        seconds = 5

        before = self.utils.utcnow()
        self.utils.set_time_override(before)
        # 10s
        self.utils.advance_time_seconds(seconds=diff)

        ref = self.utils.is_older_than(before, seconds)
        self.assertEqual(True, ref)

    @attr(kind='small')
    def test_is_older_than_parameter(self):
        """Test for nova.utils.is_older_than. Verify is older time"""

        diff = 5
        seconds = 10

        before = self.utils.utcnow()
        self.utils.set_time_override(before)
        self.utils.advance_time_seconds(seconds=diff)

        ref = self.utils.is_older_than(before, seconds)
        self.assertEqual(False, ref)

    @attr(kind='small')
    def test_is_older_than_parameter_same(self):
        """Test for nova.utils.is_older_than. Verify is same time"""

        diff = 5
        seconds = 5

        before = self.utils.utcnow()
        self.utils.set_time_override(before)
        self.utils.advance_time_seconds(seconds=diff)

        ref = self.utils.is_older_than(before, seconds)
        self.assertEqual(False, ref)

    @attr(kind='small')
    def test_is_uuid_like_parameter(self):
        """Test for nova.utils.is_uuid_like. Verify uuid format"""

        val = '12345678-1234-5678-1234-567812345678'
        ref = self.utils.is_uuid_like(val)
        self.assertEqual(True, ref)

        val = '12345678-1234-5678-1-234567812345678'
        ref = self.utils.is_uuid_like(val)
        self.assertEqual(False, ref)

        val = '12345678-abcf-5678-09CF-567812345678'
        ref = self.utils.is_uuid_like(val)
        self.assertEqual(True, ref)

        # not be 0-1 a-f
        val = '12345678-abcG-5678-09CF-567812345678'
        ref = self.utils.is_uuid_like(val)
        self.assertEqual(False, ref)

        # over 36 char
        val = '12345678-abcf-5678-09CF-567812345678abcd'
        ref = self.utils.is_uuid_like(val)
        self.assertEqual(False, ref)

    @attr(kind='small')
    def test_is_valid_ipv4(self):
        """Test for nova.utils.is_valid_ipv4. Verify ipv4 address"""

        ref = self.utils.is_valid_ipv4(address='127.0.0.1')
        self.assertEqual(True, ref)

    @attr(kind='small')
    def test_is_valid_ipv4_parameter_invalid_ip(self):
        """Test for nova.utils.is_valid_ipv4. Verify invalid ipv4 address"""

        ref = self.utils.is_valid_ipv4(address='127.0.0.256')
        self.assertEqual(False, ref)

        ref = self.utils.is_valid_ipv4(address='127.0.0.xx')
        self.assertEqual(False, ref)

        ref = self.utils.is_valid_ipv4(address='ip')
        self.assertEqual(False, ref)

    @attr(kind='small')
    def test_isotime(self):
        """Test for nova.utils.isotime. Convert datetime to String"""

        ref = self.utils.isotime(at=datetime.datetime.utcnow())

        # like this 2011-10-04T10:00:47Z
        self.assertEqual(20, len(ref))
        self.assertEqual(3, len(ref.split('-')))
        self.assertEqual(3, len(ref.split(':')))

    @attr(kind='small')
    def test_isotime_parameter(self):
        """Test for nova.utils.isotime. Convert current datetime to String"""

        ref = self.utils.isotime(at=None)
        self.assertEqual(20, len(ref))
        self.assertEqual(3, len(ref.split('-')))
        self.assertEqual(3, len(ref.split(':')))

    @attr(kind='small')
    def test_last_octet(self):
        """Test for nova.utils.last_octet. Verify return last digit"""

        ref = self.utils.last_octet(address='10.1')
        self.assertEqual(1, ref)

    @attr(kind='small')
    def test_last_octet_parameter(self):
        """Test for nova.utils.last_octet.
        Verify return last digit without dot"""

        ref = self.utils.last_octet(address='10')
        self.assertEqual(10, ref)

    @attr(kind='small')
    def test_loads(self):
        """Test for nova.utils.loads. Convert json string to normal"""

        s = 's'
        js = '"s"'
        ref = self.utils.loads(s=js)
        self.assertEqual(s, ref)

    @attr(kind='small')
    def test_loads_parameter(self):
        """Test for nova.utils.loads. Verify int string"""

        s = '1'
        js = '"1"'
        ref = self.utils.loads(s=js)
        self.assertEqual(s, ref)

    @attr(kind='small')
    def test_loads_parameter_dict(self):
        """Test for nova.utils.loads. Verify list-dict type"""

        d = [dict(a='123', b='XXX'), dict(a='456')]
        jd = '[{"a": "123", "b": "XXX"}, {"a": "456"}]'

        ref = self.utils.loads(s=jd)

        self.assertEqual(d, ref)

    @attr(kind='small')
    def test_map_dict_keys(self):
        """Test for nova.utils.map_dict_keys. Change key of dict"""

        d = dict(key1='1', key2='2')
        kmap = dict(key1='key0')

        ref = self.utils.map_dict_keys(dict_=d, key_map=kmap)

        self.assertTrue('key0' in ref)
        self.assertTrue(not ('key1' in ref))
        self.assertTrue('key2' in ref)

    @attr(kind='small')
    def test_map_dict_keys_parameter(self):
        """Test for nova.utils.map_dict_keys.
        Not be changed if the key not exits """

        d = dict(key1='1', key2='2')
        kmap = dict(key0='key3')

        ref = self.utils.map_dict_keys(dict_=d, key_map=kmap)

        self.assertTrue(not ('key0' in ref))
        self.assertTrue('key1' in ref)
        self.assertTrue('key2' in ref)

    @attr(kind='small')
    def test_novadir(self):
        """Test for nova.utils.novadir. Return the path of nova"""

        ref = self.utils.novadir()

        self.assertNotEquals(None, ref)

    @attr(kind='small')
    def test_parse_isotime(self):
        """Test for nova.utils.parse_isotime. Convert string to datetime"""

        t = self.utils.utcnow()

        s = self.utils.isotime(t)
        ref = self.utils.parse_isotime(timestr=s)

        s2 = self.utils.isotime(ref)
        self.assertEqual(s, s2)

    @attr(kind='small')
    def test_parse_mailmap(self):
        """Test for nova.utils.parse_mailmap.
        Return a map that include mail address in specified file"""

        ref = self.utils.parse_mailmap(mailmap='.mailmap')
        self.assertEqual({}, ref)

    @attr(kind='small')
    def test_parse_mailmap_parameter(self):
        """Test for nova.utils.parse_mailmap.
        Verify return a map like name:address"""

        def _fake_open(name, mode):
            return ['#abc', 'test@mydomain.net', 'test@mydomain.net test']

        req_version = (3, 0)
        cur_version = sys.version_info
        if (cur_version[0] > req_version[0] or
            (cur_version[0] == req_version[0] and
             cur_version[1] >= req_version[1])):
            self.stubs.Set(sys.modules['builtins'], 'open', _fake_open)
        else:
            self.stubs.Set(sys.modules['__builtin__'], 'open', _fake_open)

        ref = self.utils.parse_mailmap(mailmap=utils.__file__)

        self.assertEqual({'test': 'test@mydomain.net'}, ref)

    @attr(kind='small')
    def test_parse_server_string(self):
        """Test for nova.utils.parse_server_string.
        Return a tuple of (host, port)"""

        ref = self.utils.parse_server_string(server_str='127.0.0.1:8080')
        self.assertEqual(('127.0.0.1', '8080'), ref)

    @attr(kind='small')
    def test_parse_server_string_parameter(self):
        """Test for nova.utils.parse_server_string.
        Verify ipv6 server string"""

        ip = 'fe80::20c:29ff:fecc:bf0f'
        port = '8080'
        server_str = ip
        ref = self.utils.parse_server_string(server_str)

        self.assertEqual((ip, ''), ref)

        server_str = '[' + ip + ']:' + port
        ref = self.utils.parse_server_string(server_str)

        self.assertEqual((ip, port), ref)

        server_str = 'localhost'
        ref = self.utils.parse_server_string(server_str)

        self.assertEqual((server_str, ''), ref)

    @attr(kind='small')
    def test_parse_server_string_exception(self):
        """Test for nova.utils.parse_server_string.
        Return a empyt map if error"""

        ref = self.utils.parse_server_string(server_str=None)
        self.assertEqual(('', ''), ref)

    @attr(kind='small')
    def test_parse_strtime(self):
        """Test for nova.utils.parse_strtime.
        Convert string to datetime with specified format"""

        fmt = '%Y/%m/%d %H:%M:%S'
        t = self.utils.utcnow()
        ts = self.utils.strtime(t, fmt)

        ref = self.utils.parse_strtime(timestr=ts, fmt=fmt)

        ts2 = self.utils.strtime(ref, fmt)
        self.assertEqual(ts, ts2)

    @attr(kind='small')
    def test_partition_dict(self):
        """Test for nova.utils.partition_dict.
        Return two dict ,first include same key, and second is not same"""

        d1 = dict(key1='1', key2='2')
        d2 = dict(key1='aaaa')
        d3 = dict(key1='1')
        d4 = dict(key2='2')
        ref = self.utils.partition_dict(dict_=d1, keys=d2)
        self.assertEqual((d3, d4), ref)

    @attr(kind='small')
    def test_partition_dict_parameter(self):
        """Test for nova.utils.partition_dict. Verify list parameter"""
        d1 = dict(key1='1', key2='2')
        key = ['key1', 'key2']

        ref = self.utils.partition_dict(dict_=d1, keys=key)
        self.assertEqual((d1, {}), ref)

    @attr(kind='small')
    def test_runthis(self):
        """Test for nova.utils.runthis.
        Log out command parameter then call execute"""

        stdout = 'return ok'
        stderror = ''

        def _fake_execute(*cmd, **kwargs):
            return (stdout, stderror)

        self.stubs.Set(utils, 'execute', _fake_execute)
        cmd = 'dir'
        kwargs = {}

        ref = self.utils.runthis(None, cmd, **kwargs)
        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_set_time_override(self):
        """Test for nova.utils.set_time_override.
        Set current datetime to override_time"""

        self.assertEqual(None, self.utils.utcnow.override_time)

        self.utils.set_time_override()

        self.assertTrue(self.utils.utcnow.override_time)

    @attr(kind='small')
    def test_ssh_execute(self):
        """Test for nova.utils.ssh_execute.
        Execute ssh comman using ssh object specified"""

        def _fake_exec(*cmd, **kwargs):
            stdin = paramiko.ChannelFile(channel=paramiko.Channel(0))
            stdout = paramiko.ChannelFile(channel=paramiko.Channel(1))
            stderr = paramiko.ChannelFile(channel=paramiko.Channel(2))
            return (stdin, stdout, stderr)

        self.stubs.Set(paramiko.SSHClient, 'exec_command', _fake_exec)

        def _fake_read(self):
            id = self.channel.chanid
            out = 'stdout channel return'
            if id == 2:
                out = ''
            return out

        self.stubs.Set(paramiko.ChannelFile, 'read', _fake_read)

        def _fake_status(self):
            return 0

        self.stubs.Set(paramiko.Channel, 'recv_exit_status', _fake_status)

        ssh = paramiko.SSHClient()
        cmd = 'ssh --help'
        ref = self.utils.ssh_execute(
            ssh, cmd, process_input=None, addl_env=None, check_exit_code=True)

        self.assertEqual('stdout channel return', ref[0])
        self.assertEqual('', ref[1])

    @attr(kind='small')
    def test_ssh_execute_exception(self):
        """Test for nova.utils.ssh_execute.
        Raise ProcessExecutionError if ssh command return error status code"""

        def _fake_exec(*cmd, **kwargs):
            stdin = paramiko.ChannelFile(channel=paramiko.Channel(0))
            stdout = paramiko.ChannelFile(channel=paramiko.Channel(1))
            stderr = paramiko.ChannelFile(channel=paramiko.Channel(2))
            return (stdin, stdout, stderr)

        self.stubs.Set(paramiko.SSHClient, 'exec_command', _fake_exec)

        def _fake_read(self):
            id = self.channel.chanid
            out = ''
            if id == 2:
                out = 'stderr channel return'
            return out

        self.stubs.Set(paramiko.ChannelFile, 'read', _fake_read)

        def _fake_status(self):
            # ssh command execute error
            return 1

        self.stubs.Set(paramiko.Channel, 'recv_exit_status', _fake_status)

        ssh = paramiko.SSHClient()
        cmd = 'ssh --help'

        self.assertRaises(exception.ProcessExecutionError,
            self.utils.ssh_execute,
            ssh, cmd, process_input=None, addl_env=None, check_exit_code=True)

    @attr(kind='small')
    def test_ssh_execute_exception_io(self):
        """Test for nova.utils.ssh_execute.
        Pass through any exception to caller method """

        def _fake_exec(*cmd, **kwargs):
            raise paramiko.SSHException

        self.stubs.Set(paramiko.SSHClient, 'exec_command', _fake_exec)

        def _fake_read(self):
            id = self.channel.chanid
            out = ''
            if id == 2:
                out = 'stderr channel return'
            return out

        self.stubs.Set(paramiko.ChannelFile, 'read', _fake_read)

        def _fake_status(self):
            # ssh command execute error
            return 1

        self.stubs.Set(paramiko.Channel, 'recv_exit_status', _fake_status)

        ssh = paramiko.SSHClient()
        cmd = 'ssh --help'

        self.assertRaises(paramiko.SSHException,
            self.utils.ssh_execute,
            ssh, cmd, process_input=None, addl_env=None, check_exit_code=True)

    @attr(kind='small')
    def test_ssh_execute_parameter_input(self):
        """Test for nova.utils.ssh_execute.
        Raise Error if process_input is not None"""

        ssh = paramiko.SSHClient()
        cmd = 'ssh --help'

        self.assertRaises(exception.InvalidInput,
            self.utils.ssh_execute,
                ssh, cmd, process_input='has input',
                addl_env=None, check_exit_code=True)

    @attr(kind='small')
    def test_ssh_execute_parameter_env(self):
        """Test for nova.utils.ssh_execute.
        Raise Error if addl_env is not None"""

        ssh = paramiko.SSHClient()
        cmd = 'ssh --help'

        self.assertRaises(exception.InvalidInput,
            self.utils.ssh_execute,
                ssh, cmd, process_input=None,
                addl_env='has env', check_exit_code=True)

    @attr(kind='small')
    def test_str_dict_replace(self):
        """Test for nova.utils.str_dict_replace.
        Replace a string using specified key"""

        s = 'key1, key2'
        mapping = dict(key1='key2')

        ref = self.utils.str_dict_replace(s, mapping)
        self.assertEqual('key2, key2', ref)

    @attr(kind='small')
    def test_strtime(self):
        """Test for nova.utils.strtime.
        Convert string to datetime using specified format"""

        fmt = '%Y/%m/%d %H:%M:%S'
        ts = '2011/09/22 10:20:05'

        ref = self.utils.parse_strtime(timestr=ts, fmt=fmt)

        ts2 = self.utils.strtime(ref, fmt)
        self.assertEqual(ts, ts2)

    @attr(kind='small')
    def test_subset_dict(self):
        """Test for nova.utils.subset_dict.
        Return a sub dict include specified keys"""

        d = dict(key1='1', key2='2')
        key = ['key1']

        ref = self.utils.subset_dict(d, key)
        self.assertEqual({'key1': '1'}, ref)

    @attr(kind='small')
    def test_subset_dict_parameter(self):
        """Test for nova.utils.subset_dict. Verify list parameter"""

        d = dict(key1='1', key2='2')
        key = ['key1', 'key2']

        ref = self.utils.subset_dict(d, key)
        self.assertEqual(d, ref)

        key = []

        ref = self.utils.subset_dict(d, key)
        self.assertEqual({}, ref)

    @attr(kind='small')
    def test_synchronized(self):
        """Test for nova.utils.synchronized.
        Veirfy lock object exist duaring running"""

        @utils.synchronized('mylock')
        def _fake_f():
            self.assertTrue('mylock' in utils._semaphores)
            self.assertEqual(0, utils._semaphores['mylock'].balance)

        _fake_f()

        self.assertEqual({}, utils._semaphores)

    @attr(kind='small')
    def test_synchronized_parameter(self):
        """Test for nova.utils.synchronized.
        Verify lock file exist when external is true"""

        @utils.synchronized('mylock', True)
        def _fake_f():
            self.assertTrue('mylock' in utils._semaphores)
            self.assertEqual(0, utils._semaphores['mylock'].balance)
            self.assertTrue(
                os.path.exists(os.path.join(flags.FLAGS.lock_path,
                                            'nova-mylock.lock.lock')))

        _fake_f()

        self.assertEqual({}, utils._semaphores)

    @attr(kind='small')
    def test_synchronized_configuration(self):
        """Test for nova.utils.synchronized.
        Verify raise LockError when external is true,
        and lock file path specified by FLAGS.lock_path dose not exist"""

        self.flags(lock_path='users/test/1111/2222/no/exist')

        @utils.synchronized('mylock', True)
        def _fake_f():
            self.assertTrue('mylock' in utils._semaphores)
            self.assertEqual(0, utils._semaphores['mylock'].balance)
            self.assertTrue(
                os.path.exists(os.path.join(flags.FLAGS.lock_path,
                                            'nova-mylock.lock.lock')))

        self.assertRaises(lockfile.LockError, _fake_f)

    @test.skip_test("this method not exist in diablo release")
    @attr(kind='small')
    def test_timefunc(self):
        """Test for nova.utils.timefunc.
        Verify method execute time be log out"""

        def _fake_debug(msg):
            self.assertTrue(msg.startswith('timefunc: \'_fake_f\' took 1.'))

        self.stubs.Set(utils.LOG, 'debug', _fake_debug)

        @utils.timefunc
        def _fake_f():
            greenthread.sleep(1)

        _fake_f()

    @attr(kind='small')
    def test_usage_from_instance(self):
        """Test for nova.utils.usage_from_instance.
        Verify instance usage include element of instance entity"""

        def _create_instance():
            """Create a test instance"""

            inst = {}
            inst['image_ref'] = 1
            inst['reservation_id'] = 'r-1'
            inst['launch_time'] = '10'
            inst['user_id'] = '2'
            inst['project_id'] = '3'
            inst['instance_type_id'] = '5'
            inst['ami_launch_index'] = 0
            return db.instance_create(
                    context.RequestContext('1', '1'), inst)

        instance_ref = _create_instance()
        kw = dict(reservation_id=instance_ref['reservation_id'])

        ref = self.utils.usage_from_instance(instance_ref, **kw)

        d = dict(instance_ref.iteritems())
        d['instance_id'] = instance_ref['id']
        d['created_at'] = str(instance_ref['created_at'])
        d['instance_type'] = instance_ref['instance_type']['name']
        d['launched_at'] = 'DONTCARE'

        self.assertSubDictMatch(ref, d)

    @attr(kind='small')
    def test_utcnow(self):
        """Test for nova.utils.utcnow. Return current time """

        before = datetime.datetime.utcnow()

        now = self.utils.utcnow()

        self.assertTrue(now - before >= datetime.timedelta(seconds=0))

    @attr(kind='small')
    def test_utcnow_ts(self):
        """Test for nova.utils.utcnow_ts. Return current timestamp """

        ref = self.utils.utcnow_ts()
        self.assertTrue(ref > 0)

    @attr(kind='small')
    def test_utf8(self):
        """Test for nova.utils.utf8. Return a utf-8 encoding string"""

        v = 'abcd'
        ref = self.utils.utf8(value=v)
        self.assertEqual(v, ref)

    @attr(kind='small')
    def test_utf8_parameter(self):
        """Test for nova.utils.utf8. Verify unicode type"""

        v = unicode('abcd', 'UTF-8')
        ref = self.utils.utf8(value=v)
        self.assertEqual(v, ref)

        utf = '\xe3\x81\x82\xe3\x81\x84\xe3\x81\x86\xe3\x81\x88'
        v = unicode('\x82\xa0\x82\xa2\x82\xa4\x82\xa6', 'ms932')
        ref = self.utils.utf8(value=v)
        self.assertEqual(utf, ref)

    @attr(kind='small')
    def test_utf8_exception(self):
        """Test for nova.utils.utf8.
        Raise AssertionError if input is not str type"""

        self.assertRaises(AssertionError,
            self.utils.utf8, 2)

    @attr(kind='small')
    def test_vpn_ping(self):
        """Test for nova.utils.vpn_ping.
        Return a vpn server session id if socket interaction is success"""

        csid = 135
        ssid = 246

        def _fake_sendto(self, data, (address, port)):
            pass

        self.stubs.Set(utils.socket.socket, 'sendto', _fake_sendto)

        def _fake_recv(self, buffersize):
            return utils.struct.pack('!BQxxxxxQxxxx', 0x40, ssid, csid)

        self.stubs.Set(utils.socket.socket, 'recv', _fake_recv)

        param = dict(address='127.0.0.1', port='992',
                     timeout=0.05, session_id=csid)

        ref = self.utils.vpn_ping(**param)

        self.assertEqual(ssid, ref)

    @attr(kind='small')
    def test_vpn_ping_exception_invalid_recieve_size(self):
        """Test for nova.utils.vpn_ping.
        Return False if vpn socket recieve a unexcpected packet size"""

        def _fake_sendto(self, data, (address, port)):
            pass

        self.stubs.Set(utils.socket.socket, 'sendto', _fake_sendto)

        def _fake_recv(self, buffersize):
            return 'received packet size is not 26'

        self.stubs.Set(utils.socket.socket, 'recv', _fake_recv)

        param = dict(address='127.0.0.1', port='992',
                     timeout=0.05, session_id=None)

        ref = self.utils.vpn_ping(**param)

        self.assertEqual(False, ref)

    @attr(kind='small')
    def test_vpn_ping_exception_invalid_recieve_data(self):
        """Test for nova.utils.vpn_ping.
        Return False if vpn socket recieve a unexcpected packet data"""

        csid = 135
        ssid = 246

        def _fake_sendto(self, data, (address, port)):
            pass

        self.stubs.Set(utils.socket.socket, 'sendto', _fake_sendto)

        def _fake_recv(self, buffersize):
            # be not expected packet
            return utils.struct.pack('!BQxxxxxQxxxx', 0x99, ssid, csid)

        self.stubs.Set(utils.socket.socket, 'recv', _fake_recv)

        param = dict(address='127.0.0.1', port='992',
                     timeout=0.05, session_id=csid)

        ref = self.utils.vpn_ping(**param)

        self.assertTrue(not ref)

    @attr(kind='small')
    def test_vpn_ping_exception_timeout(self):
        """Test for nova.utils.vpn_ping.
        Return False if socket is timeout"""

        def _fake_sendto(self, data, (address, port)):
            pass

        self.stubs.Set(utils.socket.socket, 'sendto', _fake_sendto)

        def _fake_recv(self, buffersize):
            raise utils.socket.timeout

        self.stubs.Set(utils.socket.socket, 'recv', _fake_recv)

        param = dict(address='127.0.0.1', port='992',
                     timeout=0.05, session_id=None)

        ref = self.utils.vpn_ping(**param)

        self.assertEqual(False, ref)

    @attr(kind='small')
    def test_vpn_ping_exception_socketerror(self):
        """Test for nova.utils.vpn_ping.
        Pass through socket.error to caller. Should be catched"""

        def _fake_sendto(self, data, (address, port)):
            pass

        self.stubs.Set(utils.socket.socket, 'sendto', _fake_sendto)

        def _fake_recv(self, buffersize):
            raise utils.socket.error

        self.stubs.Set(utils.socket.socket, 'recv', _fake_recv)

        param = dict(address='127.0.0.1', port='992',
                     timeout=0.05, session_id=None)

        ref = self.utils.vpn_ping(**param)

        self.assertEqual(False, ref)

    @attr(kind='small')
    def test_vpn_ping_exception_ioerror(self):
        """Test for nova.utils.vpn_ping.
        ass through any exception to caller. Should be catched"""

        def _fake_sendto(self, data, (address, port)):
            pass

        self.stubs.Set(utils.socket.socket, 'sendto', _fake_sendto)

        def _fake_recv(self, buffersize):
            raise socket.error

        self.stubs.Set(utils.socket.socket, 'recv', _fake_recv)

        param = dict(address='127.0.0.1', port='992',
                     timeout=0.05, session_id=None)

        ref = self.utils.vpn_ping(**param)

        self.assertEqual(False, ref)

    @attr(kind='small')
    def test_xhtml_escape(self):
        """Test for nova.utils.xhtml_escape. Verify " be escaped """

        v = '"html"'
        ref = self.utils.xhtml_escape(value=v)

        self.assertEqual('&quot;html&quot;', ref)

    @attr(kind='small')
    def test_xhtml_escape_parameter(self):
        """Test for nova.utils.xhtml_escape. Verify tag character be escaped"""

        # tag
        v = '<html>'
        ref = self.utils.xhtml_escape(value=v)
        self.assertEqual('&lt;html&gt;', ref)

        # &
        v = 'a&b'
        ref = self.utils.xhtml_escape(value=v)
        self.assertEqual('a&amp;b', ref)

        # the apostrophe, U+0027 --> &apos;or &#39;
        v = '\'html'
        ref = self.utils.xhtml_escape(value=v)
        self.assertTrue(ref in ('&apos;html', '&#39;html'))


class LoopingCallTestCase(test.TestCase):
    """Test for nova.utils.LoopingCall. """

    counter = 0

    def setUp(self):
        super(LoopingCallTestCase, self).setUp()
        self.utils = utils
        self.counter = 0
        self.loopingcall = None

    @attr(kind='small')
    def test_start(self):
        """Test for nova.utils.LoopingCall.start.
        Loop be started in another thread when call start"""

        def _fake_f():
            self.counter += 1

        self.loopingcall = self.utils.LoopingCall(_fake_f)
        self.assertEqual(0, self.counter)

        ref = self.loopingcall.start(interval=0.05, now=True)

        greenthread.sleep(0.3)
        self.assertTrue(self.counter > 1)
        self.assertEqual(False, ref.has_exception())

        self.loopingcall.stop()

    @attr(kind='small')
    def test_start_parameter(self):
        """Test for nova.utils.LoopingCall.start.
        starting a Loop after interval when now parameter is False"""

        def _fake_f():
            self.counter += 1

        self.loopingcall = self.utils.LoopingCall(_fake_f)
        self.assertEqual(0, self.counter)

        ref = self.loopingcall.start(interval=0.5, now=False)

        # wait a while and check not running
        greenthread.sleep(0.3)
        self.assertEqual(0, self.counter)
        self.assertEqual(False, ref.has_exception())

        # wait a while and check running
        greenthread.sleep(0.3)
        self.assertTrue(self.counter > 0)
        self.assertEqual(False, ref.has_exception())

        self.loopingcall.stop()

    @attr(kind='small')
    def test_start_exception_return_value(self):
        """Test for nova.utils.LoopingCall.start.
        Called method return a result by raising a LoopingCallDone exception"""

        def _fake_f():
            self.counter += 1
            raise self.utils.LoopingCallDone(retvalue=self.counter)

        self.loopingcall = self.utils.LoopingCall(_fake_f)

        self.assertEqual(0, self.counter)

        ref = self.loopingcall.start(interval=0, now=True)

        # wait and check
        greenthread.sleep(0.2)
        self.assertTrue(self.counter > 0)
        self.assertEqual(False, ref.has_exception())
        self.assertEqual(self.counter, ref._result)

        self.loopingcall.stop()

    @attr(kind='small')
    def test_start_exception(self):
        """Test for nova.utils.LoopingCall.start.
        The start method catch any exception and set on has_exception flag """

        def _fake_f():
            self.counter += 1
            # some exception
            raise exception.Error('error:1')

        self.loopingcall = self.utils.LoopingCall(_fake_f)
        self.assertEqual(0, self.counter)

        ref = self.loopingcall.start(interval=0, now=True)

        # wait and check
        greenthread.sleep(0.2)
        self.assertTrue(self.counter > 0)
        self.assertEqual(True, ref.has_exception())
        self.assertEqual(None, ref._result)

        self.loopingcall.stop()

    @attr(kind='small')
    def test_stop(self):
        """Test for nova.utils.LoopingCall.stop. Exit loop by calling stop"""

        def _fake_f():
            self.counter += 1

        self.loopingcall = self.utils.LoopingCall(_fake_f)
        self.assertEqual(0, self.counter)
        self.loopingcall.start(interval=0.1, now=True)
        greenthread.sleep(0.2)

        self.loopingcall.stop()

        c = self.counter
        self.assertTrue(c > 0)

        # sleep and checking not running
        greenthread.sleep(0.2)
        self.assertEqual(c, self.counter)

    @attr(kind='small')
    def test_wait(self):
        """Test for nova.utils.LoopingCall.wait.
        Current thread be blocked when calling wait,
        and wakeup until a result be returned"""

        def _fake_f():
            greenthread.sleep(0.5)
            self.counter += 1
            raise self.utils.LoopingCallDone(retvalue=self.counter)

        # start loop
        self.loopingcall = self.utils.LoopingCall(_fake_f)
        self.assertEqual(0, self.counter)
        self.loopingcall.start(interval=0.1, now=True)

        # has no result returned when called function is running
        greenthread.sleep(0.2)
        self.assertEqual(0, self.counter)

        # wait until called function return a result
        ref = self.loopingcall.wait()

        # verify result
        self.assertEqual(self.counter, ref)

        # clear
        self.loopingcall.stop()

    @attr(kind='small')
    def test_wait_exception(self):
        """Test for nova.utils.LoopingCall.wait.
        A raised exception in called method will be pass to
        main thread if in waiting state"""

        def _fake_f():
            self.counter += 1
            # some exception
            raise exception.Error('error:1')

        # start loop
        self.loopingcall = self.utils.LoopingCall(_fake_f)
        self.assertEqual(0, self.counter)
        ref = self.loopingcall.start(interval=0.1, now=True)

        # wait until called function raise some exception
        self.assertRaises(exception.Error,
                          self.loopingcall.wait)

        self.assertTrue(self.counter > 0)
        self.assertEqual(True, ref.has_exception())

        # clear
        self.loopingcall.stop()


def dumy_method(name):
    return name


class LazyPluggableTestCase(test.TestCase):
    """Test for nova.utils.LazyPluggable."""

    def setUp(self):
        super(LazyPluggableTestCase, self).setUp()
        self.utils = utils

    @attr(kind='small')
    def test_lazypluggable(self):
        """Test for nova.utils.LazyPluggable"""

        backends = dict(DumyBackend='nova.tests.test_utils')
        back = self.utils.LazyPluggable(FLAGS['test_backend'], **backends)

        ref = back.dumy_method('test')
        self.assertEqual('test', ref)

    @attr(kind='small')
    def test_lazypluggable_exception(self):
        """Test for nova.utils.LazyPluggable"""

        backends = dict(NotBeDumyBackend='nova.tests.test_utils')
        back = self.utils.LazyPluggable(FLAGS['test_backend'], **backends)

        try:
            ref = back.dumy_method('test')
            self.assertNotEquals('test', ref, 'should raise InvalidInput')
        except exception.InvalidInput, e:
            self.assertTrue(str(e).find('Invalid backend'))
