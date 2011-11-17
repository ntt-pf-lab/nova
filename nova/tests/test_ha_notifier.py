# Copyright 2011 OpenStack LLC.
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

import stubout
import logging
import nova
from nova import context
from nova import flags
from nova import log
from nova import rpc
from nova.notifier.api import notify
from nova.ha import notifier
from nova import test
from nova import exception


class HaNotifiationTestCase(test.TestCase):
    """Test case for billing notifications"""
    def setUp(self):
        super(HaNotifiationTestCase, self).setUp()
        self.context = context.get_admin_context()

    def tearDown(self):
        self.stubs.UnsetAll()
        super(HaNotifiationTestCase, self).tearDown()

    def test_notification_by_api_decorator(self):

        self.stubs.Set(nova.flags.FLAGS, 'notification_driver',
                               'nova.ha.notifier')
        self.mock_cast_flag = False
        self.topic = None
        self.msg = {}

        def example_api(self_dummy, context, args1, args2):
            """ The self test unit, using a dummy. """
            return args1 + args2

        example_api = nova.ha.notifier.api_decorator(
                            'example_api',
                             example_api)

        def mock_cast(context, topic, msg):
            self.topic = topic
            self.msg = msg
            self.mock_cast_flag = True

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        self.assertEqual(3, example_api('self_dummy', self.context, 1, 2))
        self.assertEqual(True, self.mock_cast_flag)
        self.assertEqual('notification', self.topic)
        self.assertEqual('notify', self.msg['method'])
        self.assertEqual('INFO',
            self.msg['args']['message']['priority'])
        self.assertEqual(True,
            'context' in self.msg['args']['message']['payload'])
        self.assertEqual([1, 2],
            self.msg['args']['message']['payload']['args'])
        self.assertEqual({},
            self.msg['args']['message']['payload']['kwarg'])

    def test_notification_by_api_decorator_check(self):

        self.stubs.Set(nova.flags.FLAGS, 'notification_driver',
                               'nova.ha.notifier')

        self.mock_cast_flag = False
        self.topic = None
        self.msg = {}

        def example_api(self_dummy, context, args1, args2, args3, **kwarg):
            """ The self test unit, using a dummy. """
            return args1 + args2 + args3

        example_api = nova.ha.notifier.api_decorator(
                            'example_api_check',
                             example_api)

        def mock_cast(context, topic, msg):
            self.topic = topic
            self.msg = msg
            self.mock_cast_flag = True

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        self.assertEqual(6,
            example_api('self_dummy', self.context, 1, 2, 3, fake=1, fake1=2))
        self.assertEqual(True, self.mock_cast_flag)
        self.assertEqual('notification', self.topic)
        self.assertEqual('notify', self.msg['method'])
        self.assertEqual('INFO',
            self.msg['args']['message']['priority'])
        self.assertEqual([1, 2, 3],
            self.msg['args']['message']['payload']['args'])
        self.assertEqual({'fake': 1, 'fake1': 2},
            self.msg['args']['message']['payload']['kwarg'])
        self.assertEqual(True,
            'context' in self.msg['args']['message']['payload'])

    def test_exception_notification_by_api_decorator(self):

        self.stubs.Set(nova.flags.FLAGS, 'notification_driver',
                               'nova.ha.notifier')

        self.mock_cast_flag = False
        self.topic = None
        self.msg = {}

        def example_api(self_dummy, context, args1, args2):
            """ The self test unit, using a dummy. """
            raise exception.Error("Test Exception")

        example_api = nova.ha.notifier.api_decorator(
                            'example_api',
                             example_api)

        def mock_cast(context, topic, msg):
            self.topic = topic
            self.msg = msg
            self.mock_cast_flag = True

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        self.assertRaises(exception.Error, example_api,
                                           'self_dummy',
                                           self.context,
                                           1,
                                           2)
        self.assertEqual(True, self.mock_cast_flag)
        self.assertEqual('notification', self.topic)
        self.assertEqual('notify', self.msg['method'])
        self.assertEqual('ERROR',
            self.msg['args']['message']['priority'])
        self.assertEqual('Test Exception',
            self.msg['args']['message']['payload']['error'])
        self.assertEqual([1, 2],
            self.msg['args']['message']['payload']['args'])
        self.assertEqual({},
            self.msg['args']['message']['payload']['kwarg'])
        self.assertEqual(True,
            'context' in self.msg['args']['message']['payload'])

    def test_notification_by_api_decorator_error_param(self):

        self.stubs.Set(nova.flags.FLAGS, 'notification_driver',
                               'nova.ha.notifier')

        self.mock_cast_flag = False
        self.topic = None
        self.msg = {}

        def example_api(self_dummy):
            """ The self test unit, using a dummy. """
            return 1

        example_api = nova.ha.notifier.api_decorator(
                            'example_api_check',
                             example_api)

        def mock_cast(context, topic, msg):
            self.topic = topic
            self.msg = msg
            self.mock_cast_flag = True

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        self.assertEqual(1,
            example_api('self_dummy'))
        self.assertEqual(True, self.mock_cast_flag)
        self.assertEqual('notification', self.topic)
        self.assertEqual('notify', self.msg['method'])
        self.assertEqual('INFO',
            self.msg['args']['message']['priority'])
        self.assertEqual([],
            self.msg['args']['message']['payload']['args'])
        self.assertEqual({},
            self.msg['args']['message']['payload']['kwarg'])
        self.assertEqual(False,
            'context' in self.msg['args']['message']['payload'])

    def test_send_ha_notification(self):

        self.stubs.Set(nova.flags.FLAGS, 'notification_driver',
                               'nova.ha.notifier')

        self.mock_cast_flag = False
        self.topic = None
        self.msg = {}

        def mock_cast(context, topic, msg):
            self.topic = topic
            self.msg = msg
            self.mock_cast_flag = True

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        notify('publisher_id', 'event_type',
                nova.notifier.api.WARN, dict(a=3))

        self.assertEqual(self.mock_cast_flag, True)
        self.assertEqual('publisher_id',
            self.msg['args']['message']['publisher_id'])
        self.assertEqual('event_type',
            self.msg['args']['message']['event_type'])
        self.assertEqual('notify', self.msg['method'])
        self.assertEqual('WARN',
            self.msg['args']['message']['priority'])
        self.assertEqual('notify', self.msg['method'])
        self.assertEqual({'a': 3},
            self.msg['args']['message']['payload'])

    def test_notification_by_api_decorator_check_context(self):

        self.stubs.Set(nova.flags.FLAGS, 'notification_driver',
                               'nova.ha.notifier')

        self.mock_cast_flag = False
        self.topic = None
        self.msg = {}

        def example_api(self_dummy, self_dummy2, context):
            """ The self test unit, using a dummy. """
            return 1

        example_api = nova.ha.notifier.api_decorator(
                            'example_api_check',
                             example_api)

        def mock_cast(context, topic, msg):
            self.topic = topic
            self.msg = msg
            self.mock_cast_flag = True

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        self.assertEqual(1,
            example_api('self_dummy', 'self_dummy1', self.context))
        self.assertEqual(True, self.mock_cast_flag)
        self.assertEqual('notification', self.topic)
        self.assertEqual('notify', self.msg['method'])
        self.assertEqual('INFO',
            self.msg['args']['message']['priority'])
        self.assertEqual(['self_dummy1'],
            self.msg['args']['message']['payload']['args'])
        self.assertEqual({},
            self.msg['args']['message']['payload']['kwarg'])
        self.assertEqual(True,
            'context' in self.msg['args']['message']['payload'])

    def test_notification_by_api_decorator_kwarg_heck(self):

        class example_class(object):
            def __init__(self):
                pass

        self.stubs.Set(nova.flags.FLAGS, 'notification_driver',
                               'nova.ha.notifier')

        self.mock_cast_flag = False
        self.topic = None
        self.msg = {}

        def example_api(self_dummy, context, args1, args2, args3, **kwarg):
            """ The self test unit, using a dummy. """
            return args1 + args2 + args3

        example_api = nova.ha.notifier.api_decorator(
                            'example_api_check',
                             example_api)

        def mock_cast(context, topic, msg):
            self.topic = topic
            self.msg = msg
            self.mock_cast_flag = True

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        self.assertEqual(6,
            example_api('self_dummy', self.context, 1, 2, 3,
                                         fake=1,
                                         fake1=example_class()))
        self.assertEqual(True, self.mock_cast_flag)
        self.assertEqual('notification', self.topic)
        self.assertEqual('notify', self.msg['method'])
        self.assertEqual('INFO',
            self.msg['args']['message']['priority'])
        self.assertEqual([1, 2, 3],
            self.msg['args']['message']['payload']['args'])
        self.assertEqual({'fake': 1},
            self.msg['args']['message']['payload']['kwarg'])
        self.assertEqual(True,
            'context' in self.msg['args']['message']['payload'])

    def test_notification_by_api_decorator_arg_check(self):

        class example_class(object):
            def __init__(self):
                pass

        self.stubs.Set(nova.flags.FLAGS, 'notification_driver',
                               'nova.ha.notifier')

        self.mock_cast_flag = False
        self.topic = None
        self.msg = {}

        def example_api(self_dummy, context, args1, args2, args3, **kwarg):
            """ The self test unit, using a dummy. """
            return args2 + args3

        example_api = nova.ha.notifier.api_decorator(
                            'example_api_check',
                             example_api)

        def mock_cast(context, topic, msg):
            self.topic = topic
            self.msg = msg
            self.mock_cast_flag = True

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        self.assertEqual(5,
            example_api('self_dummy', self.context, example_class(), 2, 3,
                                         fake=1,
                                         fake1=example_class()))
        self.assertEqual(True, self.mock_cast_flag)
        self.assertEqual('notification', self.topic)
        self.assertEqual('notify', self.msg['method'])
        self.assertEqual('INFO',
            self.msg['args']['message']['priority'])
        self.assertEqual([],
            self.msg['args']['message']['payload']['args'])
        self.assertEqual({'fake': 1},
            self.msg['args']['message']['payload']['kwarg'])
        self.assertEqual(True,
            'context' in self.msg['args']['message']['payload'])


class PublishErrorsHandlerTestCase(test.TestCase):
    """Test for nova.log.PublishErrorsHandler. """

    def setUp(self):
        super(PublishErrorsHandlerTestCase, self).setUp()
        self.handler = logging.Handler()
        self.publisherrorshandler = log.PublishErrorsHandler(logging.ERROR)

    def test_emit(self):
        """Test for nova.log.PublishErrorsHandler.emit monkey patch. """
        self.stub_flg = False

        def fake_notifier(*args, **kwargs):
            self.stub_flg = True

        self.stubs.Set(nova.notifier.api, 'notify', fake_notifier)
        logrecord = logging.LogRecord('name', 'WARN', 'tmp', 1,
                                      'message', None, None)
        self.publisherrorshandler.emit(logrecord)
        self.assert_(self.stub_flg)
