# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 NTT
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

import cStringIO

from nova import context
from nova import flags
from nova import log
from nova import test
from nova.notifier import api as notifier

import logging
import sys
from nose.plugins.attrib import attr

flags.DEFINE_multistring('list_notifier_drivers',
                         ['nova.notifier.no_op_notifier'],
                         'List of drivers to send notifications')

FLAGS = flags.FLAGS


def _fake_context():
    return context.RequestContext(1, 1)


class RootLoggerTestCase(test.TestCase):
    def setUp(self):
        super(RootLoggerTestCase, self).setUp()
        self.log = log.logging.root

    def test_is_nova_instance(self):
        self.assert_(isinstance(self.log, log.NovaLogger))

    def test_name_is_nova(self):
        self.assertEqual("nova", self.log.name)

    def test_handlers_have_nova_formatter(self):
        formatters = []
        for h in self.log.handlers:
            f = h.formatter
            if isinstance(f, log.NovaFormatter):
                formatters.append(f)
        self.assert_(formatters)
        self.assertEqual(len(formatters), len(self.log.handlers))

    def test_handles_context_kwarg(self):
        self.log.info("foo", context=_fake_context())
        self.assert_(True)  # didn't raise exception

    def test_module_level_methods_handle_context_arg(self):
        log.info("foo", context=_fake_context())
        self.assert_(True)  # didn't raise exception

    def test_module_level_audit_handles_context_arg(self):
        log.audit("foo", context=_fake_context())
        self.assert_(True)  # didn't raise exception

    def test_will_be_verbose_if_verbose_flag_set(self):
        self.flags(verbose=True)
        log.reset()
        self.assertEqual(log.DEBUG, self.log.level)

    def test_will_not_be_verbose_if_verbose_flag_not_set(self):
        self.flags(verbose=False)
        log.reset()
        self.assertEqual(log.INFO, self.log.level)


class LogHandlerTestCase(test.TestCase):
    def test_log_path_logdir(self):
        self.flags(logdir='/some/path', logfile=None)
        self.assertEquals(log._get_log_file_path(binary='foo-bar'),
                         '/some/path/foo-bar.log')

    def test_log_path_logfile(self):
        self.flags(logfile='/some/path/foo-bar.log')
        self.assertEquals(log._get_log_file_path(binary='foo-bar'),
                         '/some/path/foo-bar.log')

    def test_log_path_none(self):
        self.flags(logdir=None, logfile=None)
        self.assertTrue(log._get_log_file_path(binary='foo-bar') is None)

    def test_log_path_logfile_overrides_logdir(self):
        self.flags(logdir='/some/other/path',
                   logfile='/some/path/foo-bar.log')
        self.assertEquals(log._get_log_file_path(binary='foo-bar'),
                         '/some/path/foo-bar.log')


class NovaFormatterTestCase(test.TestCase):
    def setUp(self):
        super(NovaFormatterTestCase, self).setUp()
        self.flags(logging_context_format_string="HAS CONTEXT "\
                                              "[%(request_id)s]: %(message)s",
                   logging_default_format_string="NOCTXT: %(message)s",
                   logging_debug_format_suffix="--DBG")
        self.log = log.logging.root
        self.stream = cStringIO.StringIO()
        self.handler = log.StreamHandler(self.stream)
        self.log.addHandler(self.handler)
        self.level = self.log.level
        self.log.setLevel(log.DEBUG)

    def tearDown(self):
        self.log.setLevel(self.level)
        self.log.removeHandler(self.handler)
        super(NovaFormatterTestCase, self).tearDown()

    def test_uncontextualized_log(self):
        self.log.info("foo")
        self.assertEqual("NOCTXT: foo\n", self.stream.getvalue())

    def test_contextualized_log(self):
        ctxt = _fake_context()
        self.log.info("bar", context=ctxt)
        expected = "HAS CONTEXT [%s]: bar\n" % ctxt.request_id
        self.assertEqual(expected, self.stream.getvalue())

    def test_debugging_log(self):
        self.log.debug("baz")
        self.assertEqual("NOCTXT: baz --DBG\n", self.stream.getvalue())

    @attr(kind='small')
    def test_audit_parameter(self):
        """Test for nova.log.NovaLogger.audit"""
        self.stub_flg = False

        def fake_log(*args, **kwargs):
            if args[5].get("environment") == 'environ' \
            and args[5].get("nova_version") != None:
                self.stub_flg = True

        self.stubs.Set(logging.Logger, '_log', fake_log)
        self.log.audit(1, 'message', None, extra={'environment': 'environ'})
        self.assert_(self.stub_flg)

    @attr(kind='small')
    def test_audit_parameter_log_extra_is_none(self):
        """Test for nova.log.NovaLogger.audit"""
        self.stub_flg = False

        def fake_log(*args, **kwargs):
            if args[5].get("environment") == None \
            and args[5].get("nova_version") != None:
                self.stub_flg = True

        self.stubs.Set(logging.Logger, '_log', fake_log)
        self.log.audit(1, 'message', None)
        self.assert_(self.stub_flg)

    @attr(kind='small')
    def test_audit_parameter_is_enabled_for(self):
        """Test for nova.log.NovaLogger.audit. """
        self.stub_flg = True

        def fake_log(*args, **kwargs):
            self.stub_flg = False

        self.stubs.Set(log.NovaLogger, '_log', fake_log)
        app = log.NovaLogger('test', level=log.DEBUG)
        log.AUDIT = -100
        app.audit('nova_test')
        self.assert_(self.stub_flg)
        log.AUDIT = logging.INFO + 1

    @attr(kind='small')
    def test_format_parameter_record_exc_info_has_value(self):
        """Test for nova.log.NovaFormatter.format. """
        self.stub_flg = False

        def fake_format_exception(*args, **kwargs):
            self.stub_flg = True
            return 'fake_exc_info'

        self.stubs.Set(log.NovaFormatter,
                       'formatException',
                       fake_format_exception)
        fake_record = logging.LogRecord('name', 'WARN', '/tmp', 1,
                                        'message', None,
                                        exc_info=('testA', 'testB', 'testC'))
        tmp = log.NovaFormatter()
        tmp.format(fake_record)
        self.assert_(self.stub_flg)

    @attr(kind='small')
    def test_format_configuration_logging_context_format_string_invalid(self):
        """Test for nova.log.NovaFormatter.format. """
        self.flags(logging_context_format_string=None)
        ref = log.NovaFormatter()
        logrecord = logging.LogRecord('name', 'WARN', '/tmp', 1,
                                    'message', None, None)
        result = ref.format(logrecord)
        self.judge_flg = False
        if 'NOCTXT' in result:
            self.judge_flg = True
        self.assert_(self.judge_flg)

    @attr(kind='small')
    def test_format_configuration_logging_default_format_string_invalid(self):
        """Test for nova.log.NovaFormatter.format. """
        self.flags(logging_default_format_string='invalid_flg_format')
        ref = log.NovaFormatter()
        logrecord = logging.LogRecord('fake_name', 'DEBUG', '/tmp', 1,
                                    'message', None, None)
        result = ref.format(logrecord)
        self.assertEqual(result, 'invalid_flg_format')

    @attr(kind='small')
    def test_format_configuration_logging_debug_format_suffix_invalid(self):
        """Test for nova.log.NovaFormatter.format. """
        self.flags(logging_debug_format_suffix='')
        ref = log.NovaFormatter()
        logrecord = logging.LogRecord('fake_name', 'INFO', '/tmp', 3,
                                    'message', None, None)
        result = ref.format(logrecord)
        self.judge_flg = False
        if 'NOCTXT' in result:
            self.judge_flg = True
        self.assert_(self.judge_flg)

    @attr(kind='small')
    def test_format_exception(self):
        """Test for nova.log.NovaFormatter.formatException. """
        self.stub_flg = False

        def fake_logging_formatter_format_exception(*args, **kwargs):
                self.stub_flg = True

        self.stubs.Set(logging.Formatter,
                       'formatException',
                       fake_logging_formatter_format_exception)
        fake_log = log._formatter
        fake_log.formatException(sys.exc_info(), None)
        self.assert_(self.stub_flg)

    @attr(kind='small')
    def test_format_exception_parameter_record_is_not_none(self):
        """Test for nova.log.NovaFormatter.formatException. """
        fake_formatter = log._formatter
        fake_formatter.formatException(sys.exc_info())
        target_log = log.getLogger('nova.tests.network')
        fake_formatter.formatException(sys.exc_info(), target_log)

    @attr(kind='small')
    def test_format_exception_logging_exception_prefix_invalid(self):
        """Test for nova.log.NovaFormatter.formatException. """
        self.flags(logging_exception_prefix='invalid_format_flg')
        fake_formatter = log._formatter
        fake_formatter.formatException(sys.exc_info())
        target_log = log.getLogger('nova.tests.network')
        result = fake_formatter.formatException(sys.exc_info(), target_log)
        self.judge_flg = False
        if 'invalid_format_flg' in result:
            self.judge_flg = True
        self.assert_(self.judge_flg)


class NovaLoggerTestCase(test.TestCase):
    def setUp(self):
        super(NovaLoggerTestCase, self).setUp()
        levels = FLAGS.default_log_levels
        levels.append("nova-test=AUDIT")
        self.flags(default_log_levels=levels,
                   verbose=True)
        self.log = log.getLogger('nova-test')

    def test_has_level_from_flags(self):
        self.assertEqual(log.AUDIT, self.log.level)

    def test_child_log_has_level_of_parent_flag(self):
        l = log.getLogger('nova-test.foo')
        self.assertEqual(log.AUDIT, l.level)

    @attr(kind='small')
    def test_setup_from_flags_configuration(self):
        """Test for nova.log.NovaRootLogger.setup_from_flags. """
        self.flags(default_log_levels=['=aaaaa',
                                       '=bbbbb',
                                       'ccccc',
                                       'ddddd',
                                       'eeeee'])

        ref = log.NovaLogger('name', level=log.NOTSET)
        ref.setup_from_flags()
        self.assertEquals(logging.NOTSET, ref.level)

    @attr(kind='small')
    def test_audit(self):
        """Test for nova.log.NovaLogger.audit. """
        self.stub_flg = False

        def fake_log(*args, **kwargs):
            self.stub_flg = True

        self.stubs.Set(log.NovaLogger, '_log', fake_log)
        app = log.NovaLogger('test', level=log.DEBUG)
        self.assertEqual(None, app.audit('test'))
        self.assert_(self.stub_flg)
        self.stubs.UnsetAll()

    @attr(kind='small')
    def test_audit_parameter_extra_is_not_none(self):
        """Test for nova.log.NovaLogger.audit. """
        self.stub_flg = False

        def fake_logging_logger_log(*args, **kwargs):
            self.stub_flg = True

        self.stubs.Set(logging.Logger, '_log', fake_logging_logger_log)
        ref = log.NovaLogger('name', level=log.NOTSET)
        ref.audit('message', None, extra={'environment': 'environ'})
        self.assert_(self.stub_flg)

    @attr(kind='small')
    def test_exception(self):
        """Test for nova.log.NovaLogger.exception. """
        self.stub_flg = False

        def fake_error_test_case(msg, *args, **kwargs):
            if msg == 'test_message' and kwargs.get('exc_info') == 1:
                self.stub_flg = True

        ref = log.NovaLogger('name', level=log.NOTSET)
        self.stubs.Set(ref, 'error', fake_error_test_case)
        ref.exception('test_message', None, exc_info=None)
        self.assert_(self.stub_flg)

    @attr(kind='small')
    def test_exception_parameter_exc_info_is_not_none(self):
        """Test for nova.log.NovaLogger.exception. """
        self.stub_flg = False

        def fake_error_case(msg, *args, **kwargs):
            if msg == 'test' and kwargs.get('exc_info') == 2:
                self.stub_flg = True

        ref = log.NovaLogger('test', level=log.INFO)
        self.stubs.Set(ref, 'error', fake_error_case)
        ref.exception('test', None, exc_info=2)
        self.assert_(self.stub_flg)

    @attr(kind='small')
    def test_exception_configuration_env_is_none(self):
        """Test for nova.log.NovaLogger.exception. """
        self.stub_flg = True
        self.fake_num = 0

        def fake_error_test(msg, *args, **kwargs):
            if msg == 'fake_message':
                self.fake_num += 1

            if self.fake_num == 2:
                self.stub_flg = False

        ref = log.NovaLogger('name', level=log.NOTSET)
        self.stubs.Set(ref, 'error', fake_error_test)
        result = ref.exception('fake_message',
                               None,
                               extra={'environment': None})
        self.assertEqual(None, result)
        self.assert_(self.stub_flg)

    @attr(kind='small')
    def test_exception_configuration_env_is_not_none(self):
        """Test for nova.log.NovaLogger.exception. """
        self.stub_flg = False
        self.fake_num = 0

        def fake_error(msg, *args, **kwargs):
            if self.fake_num == 0:
                if args == (5, 'fake_message', None) \
                and kwargs == {'exc_info': 1,
                               'extra': {'environment':
                                {'k3': 333, 'k2': 2222, 'k1': 111}}}:
                    self.fake_num += 1

            elif self.fake_num == 1:
                if args == ('Environment: {}',) \
                and kwargs == {'extra':
                               {'environment':
                                {'k3': 333, 'k2': 2222, 'k1': 111}}}:
                    self.stub_flg = True

        self.stubs.Set(logging.Logger, 'error', fake_error)
        ref = log.NovaLogger('test_name', level=log.ERROR)
        req = {'k1': 111, 'k2': 2222, 'k3': 333}
        extra = {'environment': req}
        ref.exception(5, 'fake_message', None, extra=extra)
        self.assert_(self.stub_flg)

    @attr(kind='small')
    def test_exception_env_is_not_none_and_isinstance_is_false(self):
        """Test for nova.log.NovaLogger.exception. """
        self.stub_flg = False
        self.fake_num = 0

        def fake_error(msg, *args, **kwargs):
            if self.fake_num == 0:
                if args == (10, 'fake_message', None) \
                and kwargs == {'exc_info': 1,
                               'extra': {'environment':
                                         {'test1': '111',
                                          'test2': '2222'}}}:
                    self.fake_num += 1

            elif self.fake_num == 1:
                if args == ('Environment: '
                            '{"test1": "111", "test2": "2222"}',) \
                and kwargs == {'extra':
                               {'environment':
                                {'test1': '111',
                                 'test2': '2222'}}}:
                    self.stub_flg = True

        self.stubs.Set(logging.Logger, 'error', fake_error)
        ref = log.NovaLogger('fake_test_name', level=log.INFO)
        req = {'test1': '111', 'test2': '2222'}
        extra = {'environment': req}
        ref.exception(10, 'fake_message', None, extra=extra)
        self.assert_(self.stub_flg)


class NovaRootLoggerTestCase(test.TestCase):
    @attr(kind='small')
    def setUp(self):
        super(NovaRootLoggerTestCase, self).setUp()

    @attr(kind='small')
    def test_setup_from_flags_parameter(self):
        """Test for nova.log.NovaRootLogger.setup_from_flags. """
        self.flags(use_syslog=True)
        app = log.NovaRootLogger('nova_test', level=log.FATAL)
        self.assertEqual(None, app.setup_from_flags())

    @attr(kind='small')
    def test_set_up_from_flags_parameter_logpath_is_not_none(self):
        """Test for nova.log.NovaRootLogger.setup_from_flags. """
        def fake_get_log_file_path(*args, **kwargs):
            return  'binary=foo-bar'

        self.stubs.Set(log, '_get_log_file_path', fake_get_log_file_path)
        ref = log.NovaRootLogger('nova_test', level=log.FATAL)
        self.assert_(isinstance(ref, log.NovaRootLogger))

    @attr(kind='small')
    def test_set_up_from_flags_parameter_self_syslog_has_value(self):
        """Test for nova.log.NovaRootLogger.setup_from_flags. """
        self.stub_flg = False

        def fake_removeHandler(*args, **kwargs):
            self.stub_flg = True

        self.stubs.Set(logging.Logger, 'removeHandler', fake_removeHandler)
        ref = log.NovaRootLogger('nova', level=log.FATAL)
        ref.syslog = 'fake_syslog'
        ref.setup_from_flags()
        self.assert_(self.stub_flg)
        ref.syslog = None

    @attr(kind='small')
    def test_set_up_from_flags_flags_publish_errors_is_not_false(self):
        """Test for nova.log.NovaRootLogger.setup_from_flags. """
        self.stub_flg = False

        def fake_add_handler(*args, **kwargs):
            self.stub_flg = True

        self.stubs.Set(log.NovaLogger, 'addHandler', fake_add_handler)
        ref = log.NovaRootLogger('nova', level=log.ERROR)
        self.flags(publish_errors='fake_publish_errors')
        ref.setup_from_flags()
        self.assert_(self.stub_flg)

    @attr(kind='small')
    def test_set_up_from_flags_logpath_equals_self_logpath(self):
        """Test for nova.log.NovaRootLogger.setup_from_flags. """
        import os
        self.sample_log = '/tmp/test_fake.log'

        def fake_get_log_file_path(*args, **kwargs):
            return  self.sample_log

        ref = log.NovaRootLogger('nova_test', level=log.DEBUG)
        ref.logpath = self.sample_log
        with open(self.sample_log, 'w') as s:
            s.write('123')
        os.chmod(self.sample_log, 0777)
        self.assert_(os.access(self.sample_log, os.X_OK))
        self.assert_(os.path.exists(self.sample_log))
        self.stubs.Set(log, '_get_log_file_path', fake_get_log_file_path)
        ref.setup_from_flags()
        self.assert_(os.access(self.sample_log, os.X_OK))
        os.remove(self.sample_log)

    @attr(kind='small')
    def test_set_up_from_flags_st_mode_is_not_equal_S_IFREG(self):
        """Test for nova.log.NovaRootLogger.setup_from_flags. """
        import os

        def fake_get_log_file_path(*args, **kwargs):
            return '/tmp/test_sample4.log'

        self.sample_log = '/tmp/test_sample4.log'
        self.assertFalse(os.path.exists(self.sample_log))
        with open(self.sample_log, 'w') as s:
            s.write('123')
        os.chmod(self.sample_log, 0777)
        self.assert_(os.access(self.sample_log, os.X_OK))
        self.assert_(os.path.exists(self.sample_log))
        self.stubs.Set(log, '_get_log_file_path', fake_get_log_file_path)
        ref = log.NovaRootLogger('nova_test', level=log.DEBUG)
        ref.setup_from_flags()
        self.assertFalse(os.access(self.sample_log, os.X_OK))
        os.remove(self.sample_log)


class PublishErrorsHandlerTestCase(test.TestCase):
    """Test for nova.log.PublishErrorsHandler. """
    @attr(kind='small')
    def setUp(self):
        super(PublishErrorsHandlerTestCase, self).setUp()
        self.handler = logging.Handler()
        self.publisherrorshandler = log.PublishErrorsHandler(logging.ERROR)

    @attr(kind='small')
    def test_emit(self):
        """Test for nova.log.PublishErrorsHandler.emit. """
        self.stub_flg = False

        def fake_notifier(*args, **kwargs):
            self.stub_flg = True

        self.stubs.Set(notifier, 'notify', fake_notifier)
        logrecord = logging.LogRecord('name', 'WARN', '/tmp', 1,
                                      'message', None, None)
        self.publisherrorshandler.emit(logrecord)
        self.assert_(self.stub_flg)

    @attr(kind='small')
    def test_emit_cfg_list_notifier_drivers_in_flags(self):
        """Test for nova.log.PublishErrorsHandler.emit. """

        self.stub_flg = False

        def fake_notifier(*args, **kwargs):
            self.stub_flg = True

        self.stubs.Set(notifier, 'notify', fake_notifier)
        logrecord = logging.LogRecord('name', 'WARN', '/tmp', 1,
                                      'message', None, None)
        self.publisherrorshandler.emit(logrecord)
        self.assert_(self.stub_flg)

    @attr(kind='small')
    def test_emit_cfg_log_notifier_in_list_notifier_drivers(self):
        """Test for nova.log.PublishErrorsHandler.emit. """

        self.flags(list_notifier_drivers=['nova.notifier.rabbit_notifier',
                                          'nova.notifier.log_notifier'])
        self.stub_flg = True

        def fake_notifier(*args, **kwargs):
            self.stub_flg = False

        self.stubs.Set(notifier, 'notify', fake_notifier)
        logrecord = logging.LogRecord('name', 'WARN', '/tmp', 1,
                                      'message', None, None)
        self.publisherrorshandler.emit(logrecord)
        self.assert_(self.stub_flg)


class HandleExceptionTestCase(test.TestCase):
    @attr(kind='small')
    def test_handle_exception(self):
        """Test for nova.log.NovaFormatter.format. """
        self.stub_flg = False

        def fake_root_critical(*args, **kwargs):
            if not kwargs:
                self.stub_flg = True

        self.stubs.Set(logging.root, 'critical', fake_root_critical)
        self.flags(verbose=False)
        log.handle_exception('test1', 'test2', 'test3')
        self.assert_(self.stub_flg)

    @attr(kind='small')
    def test_handle_exception_configuration_verbose_is_not_false(self):
        """Test for nova.log.handle_exception. """
        self.stub_flg = False

        def fake_root_critical_test(*args, **kwargs):
            if kwargs.get('exc_info') == ('test1', 'test2', 'test3'):
                self.stub_flg = True

        self.stubs.Set(logging.root, 'critical', fake_root_critical_test)
        self.flags(verbose=True)
        log.handle_exception('test1', 'test2', 'test3')
        self.assert_(self.stub_flg)


class SetUpTestCase(test.TestCase):
    @attr(kind='small')
    def test_set_up_normal(self):
        """Test for nova.log.setup. """
        self.stub_flg = False
        self.stub_flg2 = True

        def fake_reset(*args, **kwargs):
            self.stub_flg = True

        def fake_fixupParents(*args, **kwargs):
            self.stub_flg2 = False

        self.stubs.Set(log, 'reset', fake_reset)
        self.stubs.Set(logging.Manager, '_fixupParents', fake_fixupParents)
        logging.root = log.NovaLogger('name_fake', level=log.CRITICAL)
        log.setup()
        self.assert_(self.stub_flg)
        self.assertFalse(self.stub_flg2)

    @attr(kind='small')
    def test_set_up_configuration_isinstance_is_not_none(self):
        """Test for nova.log.setup. """
        self.stub_flg = True

        def fake_reset_for_set_up(*args, **kwargs):
            self.stub_flg = False

        logging.root = log.NovaRootLogger('name_fake', level=log.WARN)
        log.setup()
        self.assert_(self.stub_flg)

    @attr(kind='small')
    def test_set_up_configuration_handlers_is_three(self):
        """Test for nova.log.setup. """
        self.stub_flg = False
        self.stub_handle_flg = True

        def fake_reset_test(*args, **kwargs):
            self.stub_flg = True

        self.stubs.Set(log, 'reset', fake_reset_test)
        logging.root = log.NovaLogger('name_fake', level=log.CRITICAL)
        h1 = logging.Handler(log.DEBUG)
        h2 = logging.Handler(log.INFO)
        h3 = logging.Handler(log.ERROR)
        logging.root.handlers = [h1, h2, h3]
        log.setup()
        for handler in logging.root.handlers:
            return handler
        if h1 and h2 and h3 not in handler:
            self.stub_handle_flg = True

        self.assert_(self.stub_flg)
        self.assert_(self.stub_flg2)
        self.assert_(self.stub_handle_flg)


class WritableLoggerTestCase(test.TestCase):
    @attr(kind='small')
    def test_write(self):
        """Test for nova.log.WritableLogger.write. """
        self.stub_flg = False

        def fake_logger_log(*args, **kwargs):
            self.stub_flg = True

        self.stubs.Set(logging.Logger, 'log', fake_logger_log)
        app = log.WritableLogger(log.logging, level=logging.DEBUG)
        app.write('fake_message')
        self.assert_(self.stub_flg)


class LogGlobalMethodTestCase(test.TestCase):
    @attr(kind='small')
    def test_dictify_context(self):
        """Test for nova.log._dictify_context. """
        ref = log._dictify_context(None)
        self.assertEqual(ref, None)

    @attr(kind='small')
    def test_dictify_context_parameter_context_is_not_dictionary(self):
        """Test for nova.log._dictify_context. """
        ctxt = context.get_admin_context()
        ref = log._dictify_context(ctxt)
        self.assertTrue(isinstance(ctxt, context.RequestContext))
        self.stub_flg = False
        if isinstance(ref, dict):
            self.stub_flg = True
        self.assert_(self.stub_flg)

    @attr(kind='small')
    def test_dictify_parameter_instance_is_not_false(self):
        """Test for nova.log._dictify_context. """
        fake_context = {'test1': 'dict1', 'test2': 'dict2'}
        ref = log._dictify_context(fake_context)
        self.assertEqual(ref, {'test1': 'dict1', 'test2': 'dict2'})

    @attr(kind='small')
    def test_get_binary_name(self):
        """Test for nova.log._get_binary_name. """
        self.assert_('run_tests.py', log._get_binary_name())
