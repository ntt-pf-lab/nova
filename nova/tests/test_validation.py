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
from nova import validation


class FooCondition(validation.Validator):
    def validate_foo(self, value):
        if value != 'foo':
            raise ValueError("Isn't foo: %s" % value)


class BarCondition(validation.Validator):
    def validate_bar(self, value):
        if value != 'bar':
            raise ValueError("Isn't bar: %s" % value)


class ValidationFrameworkTestCase(test.TestCase):
    """Test Case for the framework."""

    def tearDown(self):
        super(ValidationFrameworkTestCase, self).tearDown()
        del validation.filters[:]

    def test_apply_to_method(self):
        # decorator
        class TargetClass1(object):
            @validation.method(FooCondition)
            def meth(self, foo):
                return "meth"

        # wrap it later
        class TargetClass2(object):
            def meth(self, foo):
                return "meth"

        TargetClass2.meth = validation\
                .method(FooCondition)(TargetClass2.meth)

        validation.apply()

        for klass in (TargetClass1, TargetClass2):
            obj = klass()
            self.assertEqual(obj.meth("foo"), "meth")
            self.assertRaises(ValueError, obj.meth, "bar")

    def test_apply_to_function(self):
        # decorator
        @validation.function(FooCondition)
        def func1(foo):
            return foo

        # wrap it later
        def func2(foo):
            return foo
        func2 = validation\
                .function(FooCondition)(func2)

        validation.apply()

        for func in (func1, func2):
            self.assertRaises(ValueError, func, "bar")
            self.assertEqual(func("foo"), "foo")

    def test_multi_conditions(self):
        @validation.function(FooCondition, BarCondition)
        def func(foo, bar):
            return (foo, bar)

        validation.apply()

        self.assertEqual(func("foo", "bar"), ("foo", "bar"))
        self.assertRaises(ValueError, func, "fooo", "bar")
        self.assertRaises(ValueError, func, "foo", "baz")

    def test_wrong_number_of_arguments(self):
        @validation.function(FooCondition)
        def func(foo):
            return foo

        validation.apply()

        self.assertRaises(TypeError, func, "foo", "bar")

    def test_not_apply_validation(self):
        @validation.function(FooCondition)
        def func(foo):
            return foo

        # not apply validation
        # validation.apply()

        self.assertEqual(func("bar"), "bar")
        self.assertEqual(func("foo"), "foo")

    def test_keyword_argument(self):
        @validation.function(FooCondition)
        def func(**kwargs):
            return kwargs['foo']

        validation.apply()

        # for keyword argument only case.
        self.assertRaises(ValueError, func, foo="bar")
        self.assertEqual(func(foo="foo"), "foo")

    def test_default_and_keyword_argument(self):
        @validation.function(FooCondition)
        def func(foo='aaa', bar='bbb', **kwargs):
            return foo

        validation.apply()

        self.assertRaises(ValueError, func, foo="bar")
        self.assertRaises(ValueError, func)
        self.assertEqual(func(foo="foo"), "foo")
        self.assertEqual(func("foo"), "foo")

    def test_positional_default_and_keyword_argument(self):
        @validation.function(FooCondition)
        def func(a, foo='aaa', bar='bbb', *args, **kwargs):
            return foo

        validation.apply()

        self.assertRaises(ValueError, func, object(), foo="bar")
        self.assertRaises(ValueError, func, object())
        self.assertEqual(func(object(), foo="foo"), "foo")

    def test_positional_mapped_argument(self):
        @validation.function(BarCondition)
        def func(foo, bar, baz):
            return bar

        validation.apply()

        self.assertRaises(ValueError, lambda: func('foo', bar="baz", baz='baz'))
        self.assertEqual(func('foo', bar="bar", baz='baz'), "bar")

    def test_initialize(self):
        d = {}

        class ACondition(validation.Validator):
            def __init__(self, target, *args, **kwargs):
                self.target = target
                self.args = args
                self.kwargs = kwargs

            def validate_context(self, value):
                # instance is shared over validator methods.
                d['*args'] = self.args
                d['**kwargs'] = self.kwargs
                d['value'] = value

        @validation.function(ACondition)
        def do_with_context(context):
            return context

        validation.apply()

        context = object()
        self.assertEqual(do_with_context(context), context)
        self.assertEqual(d, {
            '*args': (context,),
            '**kwargs': {},
            'value': context})

    def test_multi_param_validation(self):
        class ACondition(validation.Validator):
            def validations(self):
                validation_map = {}
                validation_map[('foo', 'bar')] = self.check_params
                return validation_map

            def check_params(self, foo, bar):
                assert (foo, bar) == ('foo', 'bar')

        @validation.function(ACondition)
        def func(foo, bar, baz):
            return (foo, bar, baz)

        validation.apply()

        self.assertEqual(func('foo', 'bar', 'baz'), ('foo', 'bar', 'baz'))
        self.assertRaises(AssertionError, func, 'aaa', 'bar', 'baz')
        self.assertRaises(AssertionError, func, 'foo', 'bbb', 'baz')

    def test_alias(self):
        class ACondition(validation.Validator):
            def validate_bar(self, value):
                assert value == 'bar'

        @validation.function(ACondition, alias={'foo': 'bar'})
        def func(foo):
            return (foo,)

        validation.apply()

        self.assertEqual(func('bar'), ('bar',))
        self.assertRaises(AssertionError, func, 'foo')
