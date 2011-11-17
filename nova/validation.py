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
import inspect
import logging

LOG = logging.getLogger("nova.validation")
filters = []


def function(*validators, **kwargs):
    alias = kwargs.get('alias', None)
    resolver = kwargs.get('resolver', None)
    filter = Filter(validators, resolver=resolver, alias=alias)
    filters.append(filter)
    return filter.connect_to


def method(*validators, **kwargs):
    alias = kwargs.get('alias', None)
    resolver = kwargs.get('resolver', None)
    filter = Filter(validators, resolver=resolver, alias=alias, method=True)
    filters.append(filter)
    return filter.connect_to


def apply():
    while len(filters):
        filter = filters.pop()
        filter.apply()


class Validator(object):
    """
    Validator.

    When a method name is validate_XXX', its collected for the param 'XXX'
    as a validation by default.
    For example, if the target param name is 'foo', thus 'validate_foo'.
    """
    def __init__(self, target, *args, **kwargs):
        """
        Validator object will be created at each calling time.
        Then GCed in same time.

        The argument passed to target function is also passed into
        the constructor. So, you can share the passed argument over
        validator methods.
        """

    def _config(self, config):
        """
        Validator object has some validate configuration.
        For example, regex validator should be have the regex pattern.
        The argument stored as validator's field.
        """
        self.config = config

    def _is_validation(self, method):
        """
        True when a method which the name starts with 'validate_'.
        """
        return (inspect.ismethod(method) \
                and method.im_func.func_name.startswith('validate_'))

    def validations(self):
        """
        Returns validation which is method prefixed with 'validation_'.
        """
        validation_map = {}
        for (method_name, method) in inspect.getmembers(self,
                                                        self._is_validation):
            validation_name = method_name.replace('validate_', '')
            validation_map[(validation_name,)] = method
        return validation_map

    def handle_exception(self, e):
        """
        Handle validation exception. should be customize for context.
        """
        raise e


class Resolver(object):
    """
    Resolver.

    Resolver handle parameter to convert it treat with validator.
    For example, some web request object consist with dict.
    validator require flat type value, so resolver should extract
    dict to flat value.
    """
    def resolve_parameter(self, params):
        """
        resolve parameter should take dict to another dict.
        """
        return params


class AliasResolver(Resolver):
    """
    AliasResolver is default resolver to convert parameter names.

    For example, set alias as {'id': 'server_id'} and the call values as
    {'id': '1', 'name': 'fake'}. Result of conversion is following.
    {'server_id': '1', 'name': 'fake'}
    So, validator for server_id and name maybe works.
    """
    def __init__(self, alias):
        """
        set up alias map.
        """
        self.alias = alias

    def resolve_parameter(self, params):
        """
        change key/value mapping of params.
        """
        for source, dest in self.alias.items():
            params[dest] = params.pop(source)
        return params


class ConflictError(ValueError):
    pass


class Filter(object):
    def __init__(self, validators, alias=None,
                 resolver=None, method=False, **kwargs):
        self.validators = validators
        if resolver:
            self.resolver = resolver()
        else:
            self.resolver = AliasResolver(alias or {})
        self.method = method
        self._map = {}
        self._config = kwargs
        self.args = None

    def connect_to(self, target):
        self.target = target

        def _f(*args, **kwargs):
            # Do not do anything if apply() is not called yet.
            if getattr(self, 'args', None) is not None:
                v_args = list(args)
                v_kwargs = dict(kwargs)
                # Unshift first as self.
                if self.method:
                    v_args = v_args[1:]

                # the name value mapper for validator.
                params = {}
                # weave runtime parameter names and values.
                if not (len(self.args) == len(v_args) or
                        len(self.args) + len(self.defaults) > len(v_args)):
                    raise TypeError("Number of arguments is different.")
                for (i, name) in enumerate(self.args):
                    if len(v_args) > 0:
                        params[name] = v_args.pop(0)

                defaults = list(self.defaults)
                # weave defaults
                while v_args and defaults:
                    (key, _value) = defaults.pop(0)
                    v_kwargs[key] = v_args.pop(0)
                # set rest defaults
                for key, value in defaults:
                    v_kwargs.setdefault(key, value)
                params.update(v_kwargs)

                # apply resolver
                params = self.resolver.resolve_parameter(params)
                # make valiation map at each calling.
                validators = []
                validate_map = {}
                exception_handlers = {}
                for validator_class in self.validators:
                    validator = validator_class(self.target, *args, **kwargs)
                    validator._config(self._config)
                    validators.append(validator)
                    for names, validation in validator.validations().items():
                        if names in validate_map:
                            raise ConflictError(
                                "Validation exists for '%s'" % names)
                        validate_map[names] = validation
                        exception_handlers[names] = validator.handle_exception

                # publish params
                for validator in validators:
                    validator.params = params
                # do validation
                validated_names = set()
                for names, validation in validate_map.items():
                    target_params = []
                    for name in names:
                        if name in params:
                            target_params.append(params[name])
                        validated_names.add(name)
                    try:
                        validation(*target_params)
                    except Exception as ex:
                        exception_handlers[names](ex)

                for name in set(params) - validated_names:
                    LOG.debug("No validator for '%s'" % name)

            return self.target(*args, **kwargs)
        return _f

    def apply(self):
        for validator in self.validators:
            if not inspect.isclass(validator):
                raise ValueError("Specify class object as validator. %s"
                                  % validator)

        argspec = inspect.getargspec(self.target)
        args = list(argspec.args or ())
        defaults = list(argspec.defaults or ())

        # weave defaults
        self.defaults = []
        while defaults:
            self.defaults.insert(0, (args.pop(-1), defaults.pop(-1)))

        if self.method:
            # Unshift first as self.
            args = args[1:]

        self.args = args
