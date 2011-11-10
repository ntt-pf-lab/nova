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
        self.stubs = stubout.StubOutForTesting()

    def tearDown(self):
        self.stubs.UnsetAll()
        super(HaNotifiationTestCase, self).tearDown()

    def test_send_notification_by_api_decorator(self):
        self.mock_cast = False

        def example_api(arg1, arg2):
            return arg1 + arg2

        example_api = nova.ha.notifier.api_decorator(
                            'example_api',
                             example_api)

        def mock_cast(cls, *args):
            self.mock_cast = True

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        class Mock(object):
            pass
        self.assertEqual(3, example_api(1, 2))

    def test_send_notification_by_api_decorator_check(self):
        self.mock_cast = False

        def example_api(args1, args2, args3, args4, **kwarg):
            return args1

        example_api = nova.ha.notifier.api_decorator(
                            'example_api',
                             example_api)

        def mock_cast(cls, *args):
            self.mock_cast = True

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        class Mock(object):
            pass
        self.assertEqual(1, example_api(1, 2, 3, 4, fake=1, fake1=2))

    def test_exception_notification_by_api_decorator(self):
        self.mock_cast = False

        def example_api(arg1, arg2):
            raise exception.Error("Test Exception")

        example_api = nova.ha.notifier.api_decorator(
                            'example_api',
                             example_api)

        def mock_cast(cls, *args):
            self.mock_cast = True

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        class Mock(object):
            pass
        self.assertRaises(exception.Error, example_api, 1, 2)

    def test_send_ha_notification(self):

        self.stubs.Set(nova.flags.FLAGS, 'notification_driver',
                               'nova.ha.notifier')
        self.mock_cast = False

        def mock_cast(cls, *args):
            self.mock_cast = True

        class Mock(object):
            pass

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        notify('publisher_id', 'event_type',
                nova.notifier.api.WARN, dict(a=3))

        self.assertEqual(self.mock_cast, True)


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
