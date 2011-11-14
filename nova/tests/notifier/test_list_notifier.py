# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
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

import stubout

import nova.notifier.api
from nova import test
from nova import utils
from nova import log as logging
from nova.notifier import list_notifier
from nova.notifier import log_notifier
from nova.notifier import no_op_notifier
from nova.notifier.api import notify
from nova.exception import ClassNotFound
from nose.plugins.attrib import attr


class NotifierListTestCase(test.TestCase):
    """Test case for notifications"""

    def setUp(self):
        super(NotifierListTestCase, self).setUp()
        list_notifier._reset_drivers()
        self.stubs = stubout.StubOutForTesting()
        # Mock log to add one to exception_count when log.exception is called

        def mock_exception(cls, *args):
            self.exception_count += 1

        self.exception_count = 0
        list_notifier_log = logging.getLogger('nova.notifier.list_notifier')
        self.stubs.Set(list_notifier_log, "exception", mock_exception)
        # Mock no_op notifier to add one to notify_count when called.

        def mock_notify(cls, *args):
            self.notify_count += 1

        self.notify_count = 0
        self.stubs.Set(nova.notifier.no_op_notifier, 'notify', mock_notify)
        # Mock log_notifier to raise RuntimeError when called.

        def mock_notify2(cls, *args):
            raise RuntimeError("Bad notifier.")

        self.stubs.Set(nova.notifier.log_notifier, 'notify', mock_notify2)

    def tearDown(self):
        self.stubs.UnsetAll()
        list_notifier._reset_drivers()
        super(NotifierListTestCase, self).tearDown()

    def test_send_notifications_successfully(self):
        self.flags(notification_driver='nova.notifier.list_notifier',
                   list_notifier_drivers=['nova.notifier.no_op_notifier',
                                          'nova.notifier.no_op_notifier'])
        notify('publisher_id', 'event_type',
                nova.notifier.api.WARN, dict(a=3))
        self.assertEqual(self.notify_count, 2)
        self.assertEqual(self.exception_count, 0)

    def test_send_notifications_with_errors(self):

        self.flags(notification_driver='nova.notifier.list_notifier',
                   list_notifier_drivers=['nova.notifier.no_op_notifier',
                                          'nova.notifier.log_notifier'])
        notify('publisher_id', 'event_type', nova.notifier.api.WARN, dict(a=3))
        self.assertEqual(self.notify_count, 1)
        self.assertEqual(self.exception_count, 1)

    def test_when_driver_fails_to_import(self):
        self.flags(notification_driver='nova.notifier.list_notifier',
                   list_notifier_drivers=['nova.notifier.no_op_notifier',
                                          'nova.notifier.logo_notifier',
                                          'fdsjgsdfhjkhgsfkj'])
        notify('publisher_id', 'event_type', nova.notifier.api.WARN, dict(a=3))
        self.assertEqual(self.exception_count, 2)
        self.assertEqual(self.notify_count, 1)

    @attr(kind='small')
    def test_notify(self):
        self.flags(notification_driver='nova.notifier.list_notifier',
                   list_notifier_drivers=['nova.notifier.no_op_notifier'])

        msg = dict(message_id=str('message_id'),
                   publisher_id='publisher_id',
                   event_type='event_type',
                   priority='WARN',
                   payload=(dict(a=3)),
                   timestamp=str(utils.utcnow()))

        list_notifier.notify(msg)

        self.assertEqual(1, self.notify_count)
        self.assertEqual(0, self.exception_count)

    @attr(kind='small')
    def test_notify_exceptions(self):

        self.flags(notification_driver='nova.notifier.list_notifier',
                   list_notifier_drivers=['nova.notifier.no_op_notifier',
                                          'nova.notifier.log_notifier'])

        msg = dict(publisher_id='publisher_id',
                   event_type='event_type',
                   priority='INFO',
                   payload=(dict(a=3)))

        list_notifier.notify(msg)

        self.assertEqual(1, self.notify_count)
        self.assertEqual(1, self.exception_count)

    @attr(kind='small')
    def test_get_drivers(self):
        """no set the driver"""

        list_drivers = list_notifier._get_drivers()

        if not list_drivers is None:
            self.success_count = 1

        self.assertEqual(1, self.success_count)

    @attr(kind='small')
    def test_get_drivers_exceptions(self):

        def mock_driver_exception(cls, *args):
            self.driver_exception_count += 1
            raise ClassNotFound

        self.driver_exception_count = 0
        self.stubs.Set(utils, 'import_object', mock_driver_exception)

        self.flags(notification_driver='nova.notifier.list_notifier',
                   list_notifier_drivers=['nova.notifier.no_op_notifier'])

        list_notifier._get_drivers()

        self.assertEqual(1, self.driver_exception_count)
