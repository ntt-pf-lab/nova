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

import nova
from nova import context
from nova import flags
from nova import log
from nova.ha import manager as notifier_manager
from nova import rpc
from nova import test
from nova import db
from nova import utils


class HaNotifierTestCase (test.TestCase):
    """Test case for Ha Notifications"""
    def setUp(self):
        super(HaNotifierTestCase, self).setUp()
        self.stubs = stubout.StubOutForTesting()
        self.user_id = 'fake'
        self.project_id = 'fake'
        self.context = context.RequestContext(self.user_id, self.project_id)
        self.manager = utils.import_object(
            'nova.ha.manager.NotificatinManager')

    def test_notify_success(self):
        message = {}
        message['message_id'] = '1'
        message['publisher_id'] = 'compute'
        message['event_type'] = 'nova.compute.api.API.create'
        message['priority'] = 'INFO'
        message['payload'] = {'context': {'request_id': '1'}}

        self.manager.notify(message, self.context)

        result = db.api.eventlog_get(self.context,
                                     '1',
                                     session=None)
        self.assertEqual('1', result.request_id)
        self.assertEqual('1', result.message_id)
        self.assertEqual('compute', result.publisher_id)
        self.assertEqual('nova.compute.api.API.create', result.event_type)
        self.assertEqual('INFO', result.priority)
        self.assertEqual('Success', result.status)

    def test_notify_no_request_id(self):
        message = {}
        message['message_id'] = '1'
        message['publisher_id'] = 'compute'
        message['event_type'] = 'nova.compute.api.API.create'
        message['priority'] = 'INFO'
        message['payload'] = {'args': {'instance_id': '1'}}

        self.manager.notify(message, self.context)

        result = db.api.eventlog_get(self.context,
                                     '1',
                                     session=None)
        self.assertEqual("default_request", result.request_id)

    def test_notify_run_instance_cleanup(self):

        self.mock_cast_flag = False

        def mock_cast(context, topic, msg):
            self.mock_cast_flag = True

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        self.args1 = '{"args": {"instance_id": 1}, "method": "run_instance"}'
        db.api.eventlog_create(self.context,
                               dict(id='1',
                                    request_id='1',
                                    message_id='1',
                                    event_type='nova.compute.api.API.create',
                                    publisher_id='compute',
                                    priority='INFO',
                                    message=self.args1,
                                    status='Success',
                                    user_id='fake',
                                    tenant_id='fake'))

        db.api.eventlog_create(self.context,
                               dict(id='2',
                                    request_id='1',
                                    message_id='2',
                                    event_type='run_instance',
                                    publisher_id='scheduler',
                                    priority='INFO',
                                    message=self.args1,
                                    status='Success',
                                    user_id='fake',
                                    tenant_id='fake'))

        message = {}
        message['request_id'] = 1
        message['message_id'] = '3'
        message['publisher_id'] = 'compute'
        message['event_type'] = 'run_instance'
        message['payload'] = {"method": "run_instance",
                              "args": {"topic": "compute",
                                       "instance_id": 1},
                                       "context": {"request_id": "1"}}
        message['priority'] = 'ERROR'

        self.manager.notify(message, self.context)

        self.assertEqual(True, self.mock_cast_flag)

    def test_notify_terminate_instance_cleanup(self):

        self.mock_cast_flag = False

        def mock_cast(context, topic, msg):
            self.mock_cast_flag = True

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        self.args1 = '{"args": {"instance_id": 1},\
                       "method": "run_instance"}'
        db.api.eventlog_create(self.context,
                               dict(id='1',
                                    request_id='1',
                                    message_id='1',
                                    event_type='nova.compute.api.API.delete',
                                    publisher_id='compute',
                                    priority='INFO',
                                    message=self.args1,
                                    status='Success',
                                    user_id='fake',
                                    tenant_id='fake'))

        db.api.eventlog_create(self.context,
                               dict(id='2',
                                    request_id='1',
                                    message_id='2',
                                    event_type='terminate_instance',
                                    publisher_id='scheduler',
                                    priority='INFO',
                                    message=self.args1,
                                    status='Success',
                                    user_id='fake',
                                    tenant_id='fake'))

        message = {}
        message['request_id'] = 1
        message['message_id'] = '3'
        message['publisher_id'] = 'compute'
        message['event_type'] = 'terminate_instance'
        message['payload'] = {"method": "terminate_instance",
                              "args": {"topic": "compute",
                                       "instance_id": 1},
                              "context": {"request_id": "1"}}
        message['priority'] = 'ERROR'

        self.manager.notify(message, self.context)

        self.assertEqual(True, self.mock_cast_flag)

    def test_notify_reboot_instance_cleanup(self):

        self.mock_cast_flag = False

        def mock_cast(context, topic, msg):
            self.mock_cast_flag = True

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        self.args1 = '{"args": {"instance_id": 1}, "method": "run_instance"}'
        db.api.eventlog_create(self.context,
                               dict(id='1',
                                    request_id='1',
                                    message_id='1',
                                    event_type='nova.compute.api.API.reboot',
                                    publisher_id='compute',
                                    priority='INFO',
                                    message=self.args1,
                                    status='Success',
                                    user_id='fake',
                                    tenant_id='fake'))

        db.api.eventlog_create(self.context,
                               dict(id='2',
                                    request_id='1',
                                    message_id='2',
                                    event_type='reboot_instance',
                                    publisher_id='scheduler',
                                    priority='INFO',
                                    message=self.args1,
                                    status='Success',
                                    user_id='fake',
                                    tenant_id='fake'))

        message = {}
        message['request_id'] = 1
        message['message_id'] = '3'
        message['publisher_id'] = 'compute'
        message['event_type'] = 'reboot_instance'
        message['payload'] = {"method": "reboot_instance",
                              "args": {"topic": "compute",
                                       "instance_id": 1},
                               "context": {"request_id": "1"}}
        message['priority'] = 'ERROR'

        self.manager.notify(message, self.context)

        self.assertEqual(True, self.mock_cast_flag)

    def test_notify_timeout_run_instance_cleanup(self):

        self.mock_cast_flag = False

        def mock_cast(context, topic, msg):
            self.mock_cast_flag = True

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        self.args1 = '{"args": {"instance_id": 1}, "method": "run_instance"}'
        db.api.eventlog_create(self.context,
                               dict(id='1',
                                    request_id='1',
                                    message_id='1',
                                    event_type='nova.compute.api.API.create',
                                    publisher_id='compute',
                                    priority='INFO',
                                    message=self.args1,
                                    status='Success',
                                    user_id='fake',
                                    tenant_id='fake'))

        db.api.eventlog_create(self.context,
                               dict(id='2',
                                    request_id='1',
                                    message_id='2',
                                    event_type='run_instance',
                                    publisher_id='scheduler',
                                    priority='INFO',
                                    message=self.args1,
                                    status='Success',
                                    user_id='fake',
                                    tenant_id='fake'))

        db.api.eventlog_create(self.context,
                               dict(id='3',
                                    request_id='1',
                                    message_id='3',
                                    event_type='run_instance',
                                    publisher_id='compute',
                                    priority='INFO',
                                    message=self.args1,
                                    status='Running',
                                    user_id='fake',
                                    tenant_id='fake'))
        message = {}
        message['request_id'] = 1
        message['message_id'] = '3'
        message['publisher_id'] = 'compute'
        message['event_type'] = 'run_instance'
        message['payload'] = {"method": "run_instance",
                              "args": {"topic": "compute",
                                       "instance_id": 1},
                              "context": {"request_id": "1"}}
        message['priority'] = 'ERROR'
        message['status'] = 'Timeout'

        self.manager.notify(message, self.context)

        self.assertEqual(True, self.mock_cast_flag)

    def test_notify_no_instance_id(self):

        self.mock_cast_flag = False

        def mock_cast(context, topic, msg):
            self.mock_cast_flag = True

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        self.args1 = '{"args": {"no_instance_id": 1},'\
                     ' "method": "run_instance"}'
        db.api.eventlog_create(self.context,
                               dict(id='1',
                                    request_id='1',
                                    message_id='1',
                                    event_type='nova.compute.api.API.create',
                                    publisher_id='compute',
                                    priority='INFO',
                                    message=self.args1,
                                    status='Success',
                                    user_id='fake',
                                    tenant_id='fake'))

        message = {}
        message['request_id'] = 1
        message['message_id'] = '3'
        message['publisher_id'] = 'compute'
        message['event_type'] = 'run_instance'
        message['payload'] = {"method": "run_instance",
                              "args": {"topic": "compute",
                                       "no_instance_id": 1},
                              "context": {"request_id": "1"}}
        message['priority'] = 'ERROR'

        self.manager.notify(message, self.context)

        self.assertEqual(False, self.mock_cast_flag)

    def test_notify_no_topic_run_instance(self):

        self.mock_cast_flag = False

        def mock_cast(context, topic, msg):
            self.mock_cast_flag = True

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        self.args1 = '{"args": {"instance_id": 1}, "method": "run_instance"}'
        db.api.eventlog_create(self.context,
                               dict(id='1',
                                    request_id='1',
                                    message_id='1',
                                    event_type='nova.compute.api.API.create',
                                    publisher_id='scheduler',
                                    priority='INFO',
                                    message=self.args1,
                                    status='Success',
                                    user_id='fake',
                                    tenant_id='fake'))

        message = {}
        message['request_id'] = 1
        message['message_id'] = '3'
        message['publisher_id'] = 'network'
        message['event_type'] = 'run_instance'
        message['payload'] = {"method": "run_instance",
                              "args": {"topic": "network",
                                       "instance_id": 1},
                              "context": {"request_id": "1"}}
        message['priority'] = 'ERROR'

        self.manager.notify(message, self.context)

        self.assertEqual(False, self.mock_cast_flag)

    def test_notify_no_topic_terminate_instance(self):

        self.mock_cast_flag = False

        def mock_cast(context, topic, msg):
            self.mock_cast_flag = True

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        self.args1 = '{"args": {"instance_id": 1},'\
                     '"method": "terminate_instance"}'
        db.api.eventlog_create(self.context,
                               dict(id='1',
                                    request_id='1',
                                    message_id='1',
                                    event_type='nova.compute.api.API.delete',
                                    publisher_id='scheduler',
                                    priority='INFO',
                                    message=self.args1,
                                    status='Success',
                                    user_id='fake',
                                    tenant_id='fake'))

        message = {}
        message['request_id'] = 1
        message['message_id'] = '3'
        message['publisher_id'] = 'network'
        message['event_type'] = 'terminate_instance'
        message['payload'] = {"method": "terminate_instance",
                              "args": {"topic": "network",
                                       "instance_id": 1},
                              "context": {"request_id": "1"}}
        message['priority'] = 'ERROR'

        self.manager.notify(message, self.context)

        self.assertEqual(False, self.mock_cast_flag)

    def test_notify_no_topic_reboot_instance(self):

        self.mock_cast_flag = False

        def mock_cast(context, topic, msg):
            self.mock_cast_flag = True

        self.stubs.Set(nova.rpc, 'cast', mock_cast)

        self.args1 = '{"args": {"instance_id": 1},'\
                     '"method": "reboot_instance"}'
        db.api.eventlog_create(self.context,
                               dict(id='1',
                                    request_id='1',
                                    message_id='1',
                                    event_type='nova.compute.api.API.reboot',
                                    publisher_id='scheduler',
                                    priority='INFO',
                                    message=self.args1,
                                    status='Success',
                                    user_id='fake',
                                    tenant_id='fake'))

        message = {}
        message['request_id'] = 1
        message['message_id'] = '3'
        message['publisher_id'] = 'network'
        message['event_type'] = 'reboot_instance'
        message['payload'] = {"method": "terminate_instance",
                              "args": {"topic": "network",
                                       "instance_id": 1},
                                       "context": {"request_id": "1"}}
        message['priority'] = 'ERROR'

        self.manager.notify(message, self.context)

        self.assertEqual(False, self.mock_cast_flag)


class MessageTestCase (test.TestCase):
    """Test case for Ha Notifications"""
    def setUp(self):
        super(MessageTestCase, self).setUp()
        self.user_id = 'fake'
        self.project_id = 'fake'
        self.context = context.RequestContext(self.user_id, self.project_id)
        self.args1 = '{"args": {"instance_id": 1}, "method": "run_instance"}'
        db.api.eventlog_create(self.context,
                               dict(id='1',
                                    request_id='1',
                                    message_id='1',
                                    event_type='event_type',
                                    publisher_id='compute',
                                    priority='INFO',
                                    message=self.args1,
                                    status='Success',
                                    user_id='fake',
                                    tenant_id='fake'))

        db.api.eventlog_create(self.context,
                               dict(id='2',
                                    request_id='1',
                                    message_id='2',
                                    event_type='run_instance',
                                    publisher_id='compute01',
                                    priority='INFO',
                                    message=self.args1,
                                    status='Success',
                                    user_id='fake',
                                    tenant_id='fake'))

        db.api.eventlog_create(self.context,
                               dict(id='3',
                                    request_id='1',
                                    message_id='3',
                                    event_type='event_type',
                                    publisher_id='compute',
                                    priority='INFO',
                                    message=self.args1,
                                    status='Faild',
                                    user_id='fake',
                                    tenant_id='fake'))

        db.api.eventlog_create(self.context,
                               dict(id='4',
                                    request_id='1',
                                    message_id='4',
                                    event_type='event_type',
                                    publisher_id='compute',
                                    priority='INFO',
                                    message=self.args1,
                                    status='Timeout',
                                    user_id='fake',
                                    tenant_id='fake'))

        self.message = notifier_manager.Message(
            db.eventlog_get_all_by_request_id(self.context, '1', session=None))

    def test_first(self):
        result = self.message.first()
        self.assertEqual('1', result.request_id)
        self.assertEqual('1', result.message_id)
        self.assertEqual('event_type', result.event_type)
        self.assertEqual('compute', result.publisher_id)
        self.assertEqual('INFO', result.priority)
        self.assertEqual(self.args1, result.message)
        self.assertEqual('Success', result.status)
        self.assertEqual('fake', result.user_id)
        self.assertEqual('fake', result.tenant_id)

    def test_cause(self):
        result = self.message.cause()
        self.assertEqual(2, len(result))
        self.assertEqual('1', result[1].request_id)
        self.assertEqual('4', result[1].message_id)
        self.assertEqual('event_type', result[1].event_type)
        self.assertEqual('compute', result[1].publisher_id)
        self.assertEqual('INFO', result[1].priority)
        self.assertEqual(self.args1, result[1].message)
        self.assertEqual('Timeout', result[1].status)
        self.assertEqual('fake', result[1].user_id)
        self.assertEqual('fake', result[1].tenant_id)

    def test_all(self):
        result = self.message.all()
        self.assertEqual(4, len(result))
        self.assertEqual('1', result[3].request_id)
        self.assertEqual('4', result[3].message_id)
        self.assertEqual('event_type', result[3].event_type)
        self.assertEqual('compute', result[3].publisher_id)
        self.assertEqual('INFO', result[3].priority)
        self.assertEqual(self.args1, result[3].message)
        self.assertEqual('Timeout', result[3].status)
        self.assertEqual('fake', result[3].user_id)
        self.assertEqual('fake', result[3].tenant_id)

    def test_get_topic(self):
        result = self.message.get_topic('run_instance')
        self.assertEqual('compute01', result)

    def test_get_instanceId(self):
        result = self.message.get_instanceId()
        self.assertEqual(1, result)
