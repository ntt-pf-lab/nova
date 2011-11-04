# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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
Billing Service
"""

import os
import logging
import json
import uuid

from nova import db
from nova import flags
from nova import log as logging
from nova import manager
from nova import rpc
from nova import utils
from nova.compute import instance_types
from nova.scheduler import zone_manager


LOG = logging.getLogger('ha.manager')
FLAGS = flags.FLAGS


DEFAULT_REQUEST_ID = 'default_request'
DEFAULT_USER_ID = 'defautl_user'
DEFAULT_TENANT_ID = 'defautl_tenant'
EVENTLOG_STATUS_SUCCESS = 'Success'
EVENTLOG_STATUS_FAILD = 'Faild'
EVENTLOG_STATUS_TIMEOUT = 'Timeout'
EVENTLOG_STATUS_CLEANUP = 'Cleanup'

class NotificatinManager(manager.Manager):
    """Manages  billing_notify notify. """

    def notify(self, message, context=None):
        """Register the database notifications billing_notify. """

        event_type = message['event_type'].replace('.','_')
        if hasattr(self,event_type):
            method = getattr(self,event_type)
            method(message)
        LOG.debug(json.dumps(message))


        status = None
        request_id = 0

        if 'status' in message:
            request_id = message['request_id']
            status = EVENTLOG_STATUS_TIMEOUT
            db.eventlog_update(context, message['message_id'], {'status':
                               EVENTLOG_STATUS_TIMEOUT})
        else:
            tenant_id = 0
            user_id = 0
            try:
                request_id = message['payload']['context']['request_id']
            except:
                pass

            try:
                 tenant_id = message['payload']['project_id']
            except:
                pass

            try:
                 tenant_id = message['payload']['context']['project_id']
            except:
                pass

            try:
                user_id = message['payload']['user_id']
            except:
                pass

            try:
                user_id = message['payload']['context']['user_id']
            except:
                pass

            if not request_id:
                request_id = DEFAULT_REQUEST_ID

            if not tenant_id:
                tenant_id = DEFAULT_TENANT_ID

            if not user_id:
                user_id = DEFAULT_USER_ID

            if message['priority'] == 'ERROR':
                status = EVENTLOG_STATUS_FAILD
            else:
                status = EVENTLOG_STATUS_SUCCESS

            values = dict(message=json.dumps(message['payload']),
                          message_id=message['message_id'],
                          event_type=message['event_type'],
                          status=status,
                          request_id=request_id,
                          user_id=user_id,
                          tenant_id=tenant_id,
                          publisher_id=message['publisher_id'],
                          priority=message['priority'])

            db.eventlog_create(context, values)


        # API fails when calling API, all of the  API, API to get any error.
        if status == EVENTLOG_STATUS_FAILD or status == EVENTLOG_STATUS_TIMEOUT:
            # Get the information you want to cleanup the request_ID.
            msg = Message(db.eventlog_get_all_by_request_id(context, request_id, session=None))
            
            # If you can get the API for Cleanup is to run cleaupu.
            if msg.first:

                cleanup = CleanupManager(msg)
                cleanup_msg = cleanup.getCleanupMessage()

                if cleanup_msg:
                    LOG.debug('start cleanup cast')
                    cleanup_values = dict(message=json.dumps(cleanup_msg),
                          message_id=uuid.uuid4(),
                          event_type='nova.ha.manager.NotificatinManager.notify',
                          status=EVENTLOG_STATUS_CLEANUP,
                          request_id=request_id,
                          user_id=DEFAULT_USER_ID,
                          tenant_id=DEFAULT_TENANT_ID,
                          publisher_id=cleanup_msg['topic'],
                          priority=FLAGS.default_notification_level)
                    
                    db.eventlog_create(context, cleanup_values)
                    # cast a message to the cleanup
                    cleanup.cleanup_cast(context, cleanup_msg)


class Message(object):
    """ Get the Message from the EventLog. """

    def __init__(self, logs):
       self.logs = logs


    def first(self):
       """ Eventlog to return the first API information. """
       return self.logs[0]


    def cause(self):
       """ Eventlog to return the error API information."""
       eventlog_ref = []
       for log in self.logs:
           if EVENTLOG_STATUS_FAILD == log['status'] or EVENTLOG_STATUS_TIMEOUT == log['status']:
               eventlog_ref.append(log)
       return eventlog_ref

 
    def all(self):
       """ Eventlog to return the all API information."""
       return self.logs


    def get_topic(self, topicType):
        """ Get the topic from eventlog. """
        topic = None
        for log in self.logs:
            if topicType in log['event_type']:
                if log['publisher_id'].find('compute') != -1:
                    topic = log['publisher_id']
                    break
        return topic

    def get_instanceId(self):
        """ Get the incatance_id from eventlog message. """
        instance_id = None
        for log in self.logs:
           msg = json.loads(log['message'])
           if 'args' in msg:
                if 'instance_id' in msg['args']:
                    instance_id = msg['args']['instance_id']
                    break

        return instance_id


class CleanupManager(object):
    """ Cleaup extract the API from the Message. """

    def __init__(self, message):
        self.message = message


    def getCleanupMessage(self):
        """ Cleanup methods to get the API that failed."""
        message = self.message.first()
        first_api = message['event_type']

        #TODO How to mapping of API
        cleanup_api = {'nova.compute.api.API.create':'terminate_instance',
                       'nova.compute.api.API.delete':'terminate_instance'}

        #TODO How to create Messae
        #TODO The combination of API and Message
        cleanup_value = {}
        if first_api in cleanup_api:
            method = cleanup_api[first_api]
            if self.message.get_instanceId() is None:
                return
            instance_id = self.message.get_instanceId()
            if self.message.get_topic('run_instance') is None:
                return
            cleanup_value['topic'] = self.message.get_topic('run_instance')
            cleanup_value['message'] = {'args':{'instance_id': instance_id},
                                        'method': method}

        return cleanup_value

    def cleanup_cast(self, context, message):
        """ Cast to run the cleanup. """
        rpc.cast(context, message['topic'], message['message'])

