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

import stubout
import logging

from nova import test
from nova import utils
import nova.notifier.api
from nova.notifier.api import notify
from nova.notifier import log_notifier
from nose.plugins.attrib import attr


class NotifierLogTestCase(test.TestCase):
    """Test case for notifications"""

    def setUp(self):
        super(NotifierLogTestCase, self).setUp()
        self.stubs = stubout.StubOutForTesting()

    def tearDown(self):
        self.stubs.UnsetAll()
        super(NotifierLogTestCase, self).tearDown()

    @attr(kind='small')
    def test_notify_parameter(self):
        self.flags(notification_driver='nova.notifier.log_notifier')

        def mock_notify(cls, *args):
            self.notify_count += 1

        self.notify_count = 0
        self.stubs.Set(log_notifier, 'notify', mock_notify)

        notify('publisher_id', 'event_type',
                nova.notifier.api.WARN, dict(a=3))

        self.assertEqual(1, self.notify_count)

    @attr(kind='small')
    def test_notify(self):

        def mock_get_logger(s, msg):
            self.success_count += 1

        self.success_count = 0
        self.stubs.Set(logging.Logger, 'warn', mock_get_logger)

        msg = dict(message_id=str('message_id'),
                   publisher_id='publisher_id',
                   event_type='event_type',
                   priority='WARN',
                   payload=(dict(a=3)),
                   timestamp=str(utils.utcnow()))

        log_notifier.notify(msg)

        self.assertEqual(1, self.success_count)
