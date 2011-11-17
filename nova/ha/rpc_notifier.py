# Copyright 2012 OpenStack LLC.
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

import json
import time
import eventlet
from datetime import datetime
import nova
import uuid
import nova.context
import nova.rpc.impl_kombu as rpc
import nova.log as LOG
from nova import db
from nova import flags
from nova.ha import notifier
from nova import utils
from nova import exception

FLAGS = flags.FLAGS
flags.DEFINE_integer('message_timeout', 5,
                    'Check the timeout EventLog')

EVENTLOG_STATUS_RUNNUNG = 'Running'
EVENTLOG_STATUS_SUCCESS = 'Success'
EVENTLOG_STATUS_TIMEOUT = 'Timeout'
EVENTLOG_STATUS_FAILD = 'Faild'


def rpc_decorator(name, fn):
    """ decorator for rpc notify which is used from utils.monkey_patch()

        :param name: name of the function
        :param function: - object of the function
        :returns: function -- decorated function

    """
    if name[-4:] == "call":
        return call
    elif name[-4:] == "cast":
        return cast
    return fn


def cast(context, topic, msg):
    """Sends a message on a topic without waiting for a response.
       Notification to register EventLog monkey patch for RPC.
    """
    try:
        db_message = utils.dumps(msg)
    except:
        LOG.error(_('Cast Faild Message: %s') % msg)
        return

    rpc._pack_context(msg, context)

    if msg['method'] != 'notify':
        msg_id = uuid.uuid4().hex
        msg.update({'_msg_id': msg_id})
        LOG.debug(_('MSG_ID is %s') % (msg_id))

        values = dict(message=db_message,
                      message_id=msg['_msg_id'],
                      event_type=msg['method'],
                      status=EVENTLOG_STATUS_RUNNUNG,
                      request_id=msg['_context_request_id'],
                      user_id=msg['_context_user_id'],
                      tenant_id=msg['_context_project_id'],
                      publisher_id=topic,
                      priority="INFO")

        db.eventlog_create(context, values)

        eventlet.greenthread.spawn_n(check_timeout,
                                     context,
                                     msg_id,
                                     topic,
                                     msg['method'],
                                     msg['_context_request_id'],
                                     msg)

    conn = rpc.ConnectionContext()
    conn.topic_send(topic, msg)


def call(context, topic, msg):
    """Sends a message on a topic and wait for a response.
       Notification to register EventLog monkey patch for RPC.
    """
    try:
        db_message = utils.dumps(msg)
    except:
        LOG.error(_('Cast Faild Message: %s') % msg)
        return

    rpc._pack_context(msg, context)

    msg_id = uuid.uuid4().hex
    msg.update({'_msg_id': msg_id})
    LOG.debug(_('MSG_ID is %s') % (msg_id))

    values = dict(message=db_message,
                  message_id=msg['_msg_id'],
                  event_type=msg['method'],
                  status=EVENTLOG_STATUS_RUNNUNG,
                  request_id=msg['_context_request_id'],
                  user_id=msg['_context_user_id'],
                  tenant_id=msg['_context_project_id'],
                  publisher_id=topic,
                  priority="INFO")

    db.eventlog_create(context, values)

    conn = rpc.ConnectionContext()
    wait_msg = rpc.MulticallWaiter(conn)
    conn.declare_direct_consumer(msg_id, wait_msg)
    eventlet.greenthread.spawn_n(check_timeout,
                                 context,
                                 msg_id,
                                 topic,
                                 msg['method'],
                                 msg['_context_request_id'],
                                 msg)
    conn.topic_send(topic, msg)

    rv = list(wait_msg)

    if not rv:
        return
    return rv[-1]


def consume(self, *args, **kwargs):
    options = {'consumer_tag': self.tag}
    options['nowait'] = kwargs.get('nowait', False)
    callback = kwargs.get('callback', self.callback)
    if not callback:
        raise ValueError("No callback defined")

    def _callback(raw_message):
        message = self.channel.message_to_python(raw_message)
        if '_msg_id' in  message.payload:
            if message.payload['method'] != 'notify':
                values = {'message_id': message.payload['_msg_id'],
                          'status': EVENTLOG_STATUS_SUCCESS}
                try:
                    db.eventlog_update(nova.context.get_admin_context(False),
                                   values['message_id'], values)
                except exception.EventLogNotFound:
                    LOG.warn("Specified event log is not found, ignore it")

        callback(message.payload)
        message.ack()

    self.queue.consume(*args, callback=_callback, **options)


def check_timeout(context, msg_id, topic, event_type, request_id, message):
    """Determines whether call/cast is timeout."""
    start_time = int(time.time())
    while True:
        eventlog = db.eventlog_get(context, msg_id, session=None)
        if eventlog['status'] != EVENTLOG_STATUS_RUNNUNG:
            break
        if int(time.time()) - start_time > FLAGS.message_timeout:
            new_message = dict(message_id=msg_id,
                               publisher_id=topic,
                               event_type=event_type,
                               priority="INFO",
                               request_id=request_id,
                               payload=message)
            new_message['status'] = EVENTLOG_STATUS_TIMEOUT
            notifier.notify(new_message)
            break
        eventlet.sleep(0.1)

rpc.ConsumerBase.consume = consume
