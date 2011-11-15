# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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
"""
Unit Tests for remote procedure calls using kombu
"""

from nova import flags
from nova import context
from nova import exception
from nova import log as logging
from nova import test
from nova.rpc import impl_kombu
from nova.tests import test_rpc_common
from nose.plugins.attrib import attr

LOG = logging.getLogger('nova.tests.rpc')
FLAGS = flags.FLAGS


class RpcKombuTestCase(test_rpc_common._BaseRpcTestCase):
    def setUp(self):
        self.rpc = impl_kombu
        super(RpcKombuTestCase, self).setUp()

    def tearDown(self):
        super(RpcKombuTestCase, self).tearDown()

    def test_reusing_connection(self):
        """Test that reusing a connection returns same one."""
        conn_context = self.rpc.create_connection(new=False)
        conn1 = conn_context.connection
        conn_context.close()
        conn_context = self.rpc.create_connection(new=False)
        conn2 = conn_context.connection
        conn_context.close()
        self.assertEqual(conn1, conn2)

    def test_topic_send_receive(self):
        """Test sending to a topic exchange/queue"""

        conn = self.rpc.create_connection()
        message = 'topic test message'

        self.received_message = None

        def _callback(message):
            self.received_message = message

        conn.declare_topic_consumer('a_topic', _callback)
        conn.topic_send('a_topic', message)
        conn.consume(limit=1)
        conn.close()

        self.assertEqual(self.received_message, message)

    def test_direct_send_receive(self):
        """Test sending to a direct exchange/queue"""
        conn = self.rpc.create_connection()
        message = 'direct test message'

        self.received_message = None

        def _callback(message):
            self.received_message = message

        conn.declare_direct_consumer('a_direct', _callback)
        conn.direct_send('a_direct', message)
        conn.consume(limit=1)
        conn.close()

        self.assertEqual(self.received_message, message)

    @test.skip_test("kombu memory transport seems buggy with fanout queues "
            "as this test passes when you use rabbit (fake_rabbit=False)")
    def test_fanout_send_receive(self):
        """Test sending to a fanout exchange and consuming from 2 queues"""

        conn = self.rpc.create_connection()
        conn2 = self.rpc.create_connection()
        message = 'fanout test message'

        self.received_message = None

        def _callback(message):
            self.received_message = message

        conn.declare_fanout_consumer('a_fanout', _callback)
        conn2.declare_fanout_consumer('a_fanout', _callback)
        conn.fanout_send('a_fanout', message)

        conn.consume(limit=1)
        conn.close()
        self.assertEqual(self.received_message, message)

        self.received_message = None
        conn2.consume(limit=1)
        conn2.close()
        self.assertEqual(self.received_message, message)

    @attr(kind='small')
    def test_consume_configuration(self):
        """Test for nova.rpc.impl_kombu.ConsumerBase.consume. """
        conn = self.rpc.create_connection()
        conn.declare_topic_consumer('a_topic', None)
        self.assertRaises(ValueError, conn.consume)

    @attr(kind='small')
    def test_cancel(self):
        """Test for nova.rpc.impl_kombu.ConsumerBase.cancel. """
        conn = self.rpc.create_connection()
        message = 'fake_message'
        self.stub_flg = False

        def fake_self_queue_cancel(*args, **kwargs):
            self.stub_flg = True
        self.received_message = None

        def _callback(message):
            self.received_message = message
        self.stubs.Set(self.rpc.kombu.entity.Queue,
                       'cancel',
                       fake_self_queue_cancel)
        conn.declare_topic_consumer('a_topic', _callback)
        conn.topic_send('a_topic', message)
        conn.consume(limit=1)
        my_consume = conn.consumers[-1]
        my_consume.cancel()
        self.assert_(self.stub_flg)

    @attr(kind='small')
    def test_cancel_exception_key_error(self):
        """Test for nova.rpc.impl_kombu.ConsumerBase.cancel. """
        def fake_queue_cancel(*args, **kwargs):
            raise KeyError

        message = 'fake_message'
        self.received_message = None

        def _callback(message):
            self.received_message = message
        conn = self.rpc.create_connection()
        self.stubs.Set(self.rpc.kombu.entity.Queue,
                       'cancel',
                       fake_queue_cancel)
        conn.declare_topic_consumer('a_topic', _callback)
        conn.topic_send('a_topic', message)
        conn.consume(limit=1)
        queue = conn.consumers[-1]
        self.assertRaises(KeyError, queue.cancel)

    @attr(kind='small')
    def test_fanoutconsumer(self):
        """Test for nova.rpc.impl_kombu.FanoutConsumer """
        conn = self.rpc.create_connection()
        conn.declare_fanout_consumer(conn, 'a_topic')
        self.assert_('FanoutConsumer'in str(conn.consumers))

    @attr(kind='small')
    def test_reconnect(self):
        """Test for nova.rpc.impl_kombu.Connection.reconnect. """
        test_conn = self.rpc.Connection()
        test_conn.declare_topic_consumer('a_topic', None)
        test_conn.declare_topic_consumer('b_topic', None)
        num_before = len(test_conn.consumers)
        test_conn.reconnect()
        num_after = len(test_conn.consumers)
        self.assertEqual(num_before, num_after)

    @attr(kind='small')
    def test_reconnect_configuration_memory_transport_is_false(self):
        """Test for nova.rpc.impl_kombu.Connection.reconnect. """

        import sys

        def fake_sys_exit(*args, **kwargs):
            raise RuntimeError

        self.stubs.Set(sys, 'exit', fake_sys_exit)
        FLAGS.fake_rabbit = False
        FLAGS.rabbit_max_retries = 1
        self.assertRaises(RuntimeError, self.rpc.Connection)
        FLAGS.fake_rabbit = True
        FLAGS.rabbit_max_retries = 0

    @attr(kind='small')
    def test_reconnect_connection_success_and_memory_transport_false(self):
        """Test for nova.rpc.impl_kombu.Connection.reconnect. """
        test_conn = self.rpc.Connection()
        test_conn.declare_topic_consumer('a_topic', None)
        test_conn.declare_topic_consumer('b_topic', None)
        num_before = len(test_conn.consumers)
        test_conn.memory_transport = False
        test_conn.reconnect()
        num_after = len(test_conn.consumers)
        self.assertEqual(num_before, num_after)

    @attr(kind='small')
    def test_connect_error(self):
        """Test for nova.rpc.impl_kombu.Connection.connect_error. """
        self.stub_flg = False

        def fake_log_error(msg, *args, **kwargs):
            if msg == ("AMQP server on localhost:5672 is unreachable:"
                        " fake_exception. Trying again in 5 seconds."):
                self.stub_flg = True

        self.stubs.Set(logging.getLogger('nova.rpc'), 'error', fake_log_error)
        test_conn = self.rpc.Connection()
        test_conn.connect_error('fake_exception', 5)

    @attr(kind='small')
    def test_reset_configuration_memory_transport_is_false(self):
        """Test for nova.rpc.impl_kombu.Connection.reset. """
        test_conn = self.rpc.Connection()
        test_conn.memory_transport = False
        test_conn.reset()
        self.assertEquals([], test_conn.consumers)

    @attr(kind='small')
    def test_iterconsume_parameter_queue_is_multiple(self):
        """Test for nova.rpc.impl_kombu.Connection.iterconsume """
        message = 'test_message'
        self.received_message = None

        def _callback(message):
            self.received_message = message

        test_conn = self.rpc.Connection()
        test_conn.declare_topic_consumer('a_topic', _callback)
        test_conn.declare_topic_consumer('b_topic', _callback)
        test_conn.declare_topic_consumer('c_topic', _callback)
        test_conn.topic_send('a_topic', message)
        test_conn.topic_send('b_topic', message)
        test_conn.topic_send('c_topic', message)
        test_conn.consume(limit=1)
        ref = len(test_conn.consumers)
        self.assertEquals(3, ref)
        test_conn.close()

    @attr(kind='small')
    def test_create_consumer_parameter_fanout_is_true(self):
        """Test for nova.rpc.impl_kombu.Connection.create_consumer """
        self.stub_flg = False

        def fake_declare_fanout_consumer(*args, **kwargs):
            self.stub_flg = True
        self.stubs.Set(impl_kombu.Connection,
                       'declare_fanout_consumer',
                       fake_declare_fanout_consumer)
        test_conn = self.rpc.Connection()
        test_conn.create_consumer('test_topic', 'fake_proxy', True)
        self.assert_(self.stub_flg)

    @attr(kind='small')
    def test_proxy_callback_parameter_method_is_none(self):
        """Test for nova.rpc.impl_kombu.ProxyCallback"""
        self.stub_flg = False

        def fake_log_warn(msg, *args, **kwargs):
            if msg == ("no method for message: "
            "{u'aaa': u'abb', u'args': {u'value': 50}}"):
                self.stub_flg = True

        self.stubs.Set(logging.getLogger('nova.rpc'), 'warn', fake_log_warn)
        value = 50
        ctxt = context.get_admin_context()
        self.rpc.cast(ctxt, 'test', {"aaa": 'abb', "args": {"value": value}})
        test_conn = self.rpc.Connection()
        test_conn.reconnect()
        self.assert_(self.stub_flg)
        test_conn.close()

    @attr(kind='small')
    def test_msg_reply_parameter_type_error(self):
        """Test for nova.rpc.impl_kombu.msg_reply"""
        self.assertRaises(TypeError, self.rpc.msg_reply, [10, 20, 30])

    @attr(kind='small')
    def test_close_parameter_connection_is_none(self):
        """Test for nova.rpc.impl_kombu.ConnectionContext.close. """
        self.connectioncontext = impl_kombu.ConnectionContext()
        self.connectioncontext.close()
        self.assertRaises(exception.InvalidRPCConnectionReuse,
                          self.connectioncontext.__getattr__,
                          'key')

    @attr(kind='small')
    def test_call_multicall_is_empty(self):
        def fake_multicall(context, topic, msg):
            return []

        self.stubs.Set(self.rpc, 'multicall', fake_multicall)
        value = 10
        result = self.rpc.call(self.context,
                               'test', {"method": "echo",
                               "args": {"value": value}})
        self.assertEqual(None, result)

    @attr(kind='small')
    def test_msg_reply_raise_type_error(self):
        class fake_reply():
            pass

        dummy = fake_reply()

        def _fake_send(message):
                raise TypeError

        self.stubs.Set(self.rpc.DirectPublisher, 'send', _fake_send)
        msg_id = 'test'
        self.assertRaises(TypeError, self.rpc.msg_reply, msg_id, dummy, None)

    @attr(kind='small')
    def test_connection_cancel_consumer_thread(self):
        self._rpc_consumer_thread = 10
        result = self.rpc.Connection().cancel_consumer_thread()
        self.assertEqual(None, result)