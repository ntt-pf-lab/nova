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
Tests For nova.notifier.api
"""

from nova import exception
from nova import flags
from nova import log as logging
from nova import test
from nova import utils
from nova import rpc
from nose.plugins.attrib import attr
from nova.notifier import api

LOG = logging.getLogger('nova.exception')
FLAGS = flags.FLAGS
DUMMY_NOTIFY_CALLED = False


def notify(message):
    """Notifies the recipient of the desired event given the model"""
    global DUMMY_NOTIFY_CALLED
    DUMMY_NOTIFY_CALLED = True


class ApiTestCase(test.TestCase):
    """Test for nova.notifier.api. """
    def setUp(self):
        super(ApiTestCase, self).setUp()

    @attr(kind='small')
    def test_notify_decorator(self):
        """Test for nova.notifier.api.publisher_id. """
        self._notify_decorator_called = False

        def dummy_fn(*args):
            self._notify_decorator_called = True

        api.notify_decorator("compute", dummy_fn)()

        self.assertEqual(self._notify_decorator_called, True)

    @attr(kind='small')
    def test_publisher_id_parameter(self):
        """Test for nova.notifier.api.publisher_id. """
        self.flags(host='ubuntu')
        ref = api.publisher_id("compute")
        self.assertEqual("compute.ubuntu", ref)

        ref = api.publisher_id("compute", "yellowdog")
        self.assertEqual("compute.yellowdog", ref)

    @attr(kind='small')
    def test_notify_exception(self):
        """Test for nova.notifier.api.notify. """
        self.mock_notify_called = False

        def mock_notify(message):
            self.mock_notify_called = True
            raise exception.Error()

        self.stubs.Set(utils.import_object(FLAGS.notification_driver),
                       'notify', mock_notify)
        api.notify(api.publisher_id("compute"), 'event_type',
                   'DEBUG', dict(a=3))
        self.assertEqual(self.mock_notify_called, True)

    @attr(kind='small')
    def test_notify_configuration(self):
        """Test for nova.notifier.api.notify. """
        self.flags(notification_driver='nova.tests.notifier.test_notifier_api')

        api.notify(api.publisher_id("compute"), 'event_type',
                   'DEBUG', dict(a=3))

        self.assertEqual(DUMMY_NOTIFY_CALLED, True)

    @attr(kind='small')
    def test_notify_invalid_priority_exception(self):
        def mock_cast(cls, *args):
            pass

        self.stubs.Set(rpc, 'cast', mock_cast)
        self.assertRaises(api.BadPriorityException,
                api.notify, 'publisher_id',
                'event_type', 'bad priority', dict(a=3))

    @attr(kind='small')
    def test_notify_payload_parameter_empty_string(self):
        """Test for nova.notifier.api.notify#payload """
        self.payload = None

        def mock_notify(message):
            self.payload = message['payload']
        self.stubs.Set(utils.import_object(FLAGS.notification_driver),
        'notify', mock_notify)

        # empty string
        api.notify(api.publisher_id("compute"), 'event_type', 'DEBUG', '')
        self.assertEqual('', self.payload)

    @attr(kind='small')
    def test_notify_payload_parameter_normal_string(self):
        """Test for nova.notifier.api.notify#payload """
        self.payload = None

        def mock_notify(message):
            self.payload = message['payload']
        self.stubs.Set(utils.import_object(FLAGS.notification_driver),
        'notify', mock_notify)

        # string
        api.notify(api.publisher_id("compute"), 'event_type', 'DEBUG', 'str')
        self.assertEqual('str', self.payload)

    @attr(kind='small')
    def test_notify_payload_parameter_number(self):
        """Test for nova.notifier.api.notify#payload """
        self.payload = None

        def mock_notify(message):
            self.payload = message['payload']
        self.stubs.Set(utils.import_object(FLAGS.notification_driver),
        'notify', mock_notify)

        # number
        api.notify(api.publisher_id("compute"), 'event_type', 'DEBUG', 123)
        self.assertEqual(123, self.payload)

    @attr(kind='small')
    def test_notify_payload_parameter_class(self):
        """Test for nova.notifier.api.notify#payload """
        self.payload = None
        self.exception_count = 0

        def mock_notify(message):
            self.payload = message['payload']
        self.stubs.Set(utils.import_object(FLAGS.notification_driver),
        'notify', mock_notify)

        def mock_notify_exception(message):
            self.payload = message['payload']
            self.exception_count = self.exception_count + 1
            raise exception.Error()
        self.stubs.Set(utils.import_object(FLAGS.notification_driver),
                    'notify', mock_notify_exception)

        # class
        class Mock(object):
            pass
        api.notify(api.publisher_id("compute"), 'event_type', 'DEBUG', Mock)
        self.assertEqual(self.payload,
                    "<class 'nova.tests.notifier.test_notifier_api.Mock'>")

        self.assertEqual(1, self.exception_count)
