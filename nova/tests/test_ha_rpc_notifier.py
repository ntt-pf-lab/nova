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

import json
import eventlet
import datetime
import nova
from nova import context
from nova import flags
from nova import log as LOG
from nova import rpc
from nova.ha import rpc_notifier
from nova.ha import notifier
from nova import db
from nova import test


class RpcNotifierTestCase(test.TestCase):
    """Test case for rpc notifications"""
    def setUp(self):
        super(RpcNotifierTestCase, self).setUp()
        self.stubs = stubout.StubOutForTesting()
        self.conn = rpc.create_connection(True)
        self.context = context.get_admin_context()
        self.receiver = TestReceiver()
        self.conn.create_consumer('test', self.receiver, False)
        self.conn.consume_in_thread()

    def tearDown(self):
        self.stubs.UnsetAll()
        super(RpcNotifierTestCase, self).tearDown()

    def test_send_notification_by_rpc_decorator(self):

        def example_api(arg1, arg2):
            return arg1 + arg2

        example_api = nova.ha.rpc_notifier.rpc_decorator(
                            'example_api',
                             example_api)

        self.assertEqual(3, example_api(1, 2))

    def test_cast_send_notification_by_rpc_decorator(self):

        def cast(context, topic, message):
            pass

        example_api = nova.ha.rpc_notifier.rpc_decorator(
                            'nova.rpc.impl_kombu.cast',
                             cast)
        value = 42
        result = cast(self.context, 'test',
                      {"method": "echo",
                       "args": {"value": value}})

        self.assertEqual(None, result)

    def test_call_send_notification_by_rpc_decorator(self):

        def call(context, topic, message):
            pass

        example_api = nova.ha.rpc_notifier.rpc_decorator(
                            'nova.rpc.impl_kombu.call',
                             call)

        value = 42

        result = rpc_notifier.call(self.context, 'test',
                                   {"method": "echo",
                                    "args": {"value": value}})

        self.assertEqual(value, result)

    def test_call_succeed(self):
        value = 42
        result = rpc_notifier.call(self.context, 'test', {"method": "echo",
                                                 "args": {"value": value}})
        self.assertEqual(value, result)

    def test_cast_succeed(self):
        value = 42
        result = rpc_notifier.cast(self.context, 'test', {"method": "echo",
                                                 "args": {"value": value}})
        self.assertEqual(None, result)

    def test_cast_succeed_datetime_encoder(self):
        value = {'created_at':
                 datetime.datetime(2011, 11, 11, 11, 11, 11, 111111)}
        result = rpc_notifier.cast(self.context, 'test', {"method": "echo",
                                                 "args": {"value": value}})
        self.assertEqual(None, result)

    def test_consume_configuration(self):
        """Test for nova.rpc.impl_kombu.ConsumerBase.consume. """
        self.conn.declare_topic_consumer('a_topic', None)
        self.assertRaises(ValueError, self.conn.consume)


class RpcTimeOutCheckTestCase(test.TestCase):
    def setUp(self):
        super(RpcTimeOutCheckTestCase, self).setUp()
        self.context = context.get_admin_context()

    def test_ha_timeout(self):
        self.mock_notifier = False

        def mock_notifier(*args, **kwargs):
            self.mock_notifier = True

        self.stubs.Set(notifier, 'notify', mock_notifier)

        con = {}
        con['id'] = 1
        con['request_id'] = '1'
        con['message_id'] = '1'
        con['event_type'] = 'event_type'
        con['publisher_id'] = 'compute'
        con['priority'] = 'INFO'
        args1 = "{'args': {'instance_id': '1'},'method': 'run_instance'}"
        con['message'] = args1
        con['status'] = rpc_notifier.EVENTLOG_STATUS_RUNNUNG
        con['user_id'] = 'fake'
        con['tenant_id'] = 'fake'

        db.eventlog_create(self.context, con)
        self.flags(message_timeout=0.05)

        message = {"args": 1, "method": 'run_instance'}
        rpc_notifier.check_timeout(self.context,
                                   '1',
                                   'test',
                                   'compute',
                                   '1',
                                   message)

        self.assertEqual(True, self.mock_notifier)

    def test_ha_no_timeout(self):

        con = {}
        con['id'] = 1
        con['request_id'] = '1'
        con['message_id'] = '1'
        con['event_type'] = 'event_type'
        con['publisher_id'] = 'compute'
        con['priority'] = 'INFO'
        args1 = "{'args': {'instance_id': '1'},'method': 'run_instance'}"
        con['message'] = args1
        con['status'] = rpc_notifier.EVENTLOG_STATUS_SUCCESS
        con['user_id'] = 'fake'
        con['tenant_id'] = 'fake'

        db.eventlog_create(self.context, con)

        message = {"args": 1, "method": "run_instance"}
        rpc_notifier.check_timeout(self.context,
                                   '1',
                                   'test',
                                   'compute',
                                   '1',
                                    message)

        result = db.eventlog_get(self.context, '1', session=None)

        self.assertEqual("Success", result['status'])


class TestReceiver(object):
    """Simple Proxy class so the consumer has methods to call.

    Uses static methods because we aren't actually storing any state.

    """
    @staticmethod
    def echo(context, value):
        """Simply returns whatever value is sent in."""
        LOG.debug(_("Received %s"), value)
        return value

    @staticmethod
    def context(context, value):
        """Returns dictionary version of context."""
        LOG.debug(_("Received %s"), context)
        return context.to_dict()

    @staticmethod
    def echo_three_times(context, value):
        context.reply(value)
        context.reply(value + 1)
        context.reply(value + 2)

    @staticmethod
    def echo_three_times_yield(context, value):
        yield value
        yield value + 1
        yield value + 2

    @staticmethod
    def fail(context, value):
        """Raises an exception with the value sent in."""
        raise Exception(value)
