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

import logging
import logging.handlers

import nova
from nova import context
from nova.exception import Error
from nova import flags
from nova import rpc
from nova import log as LOG
from nova.notifier import api
from nova import utils
from nova.notifier import rabbit_notifier
from nova.db import sqlalchemy
from nova import db
import json

FLAGS = flags.FLAGS



def db_decorator(name, fn):
    """ decorator for notify which is used from utils.monkey_patch()

        :param name: name of the function
        :param function: - object of the function
        :returns: function -- decorated function

    """
    def wrapped_func(*args, **kwarg):
        LOG.debug(args)
        LOG.debug(kwarg)
        body = {}

#        if not args and len(args) > 1:
        print name
        print args
        if name.startswith('nova.db.sqlalchemy.models'):
            actionm = name.split('.')[-1]
            if actionm in ('add', 'update', 'delete'):
                tablename = args[0].__tablename__
#                if tablename.lower() == 'instances':
                if tablename.lower() not in ('novabase',
                                             'eventlog'):
                    v1 = ''
                    if len(args) > 1:
                        v1 = args[1]
                    print 'db action: table %s, action %s, param %s'\
                               % (tablename, actionm, v1)

                    values = dict(message=utils.dumps(v1),
                          message_id=tablename,
                          event_type='db',
                          status=actionm,
                          request_id='',
                          user_id='',
                          tenant_id='',
                          publisher_id='',
                          priority='INFO')
#                    f = open('/var/log/event.log', 'a')
#                    f.write(str(values))
#                    f.write('\n')
#                    f.close()
                    db.eventlog_create(context.get_admin_context(), values)

        ret = None
        try:
            ret = fn(*args, **kwarg)
        except Error as e:
            body['error'] = "%s" % e
            raise e
        return ret
    return wrapped_func


def api_decorator(name, fn):
    """ decorator for notify which is used from utils.monkey_patch()

        :param name: name of the function
        :param function: - object of the function
        :returns: function -- decorated function

    """
    def wrapped_func(*args, **kwarg):
        LOG.debug(args)
        LOG.debug(kwarg)
        body = {}
        body['args'] = []
        body['kwarg'] = {}
        original_args = args
        for arg in args[1:]:
            if isinstance(arg, context.RequestContext):
                body['context'] = arg
            else:
                body['args'].append(arg)
        try:
            utils.dumps(body['args'])
        except:
            LOG.warn(_('Encode Faild arg: %s') % body['args'])
            body['args'] = []
        for key in kwarg:
            try:
                utils.dumps(kwarg[key])
                body['kwarg'][key] = kwarg[key]
            except:
                LOG.warn(_('Encode Faild kwarg: %s') % kwarg[key])

        api.notify(FLAGS.default_publisher_id,
                            name,
                            FLAGS.default_notification_level,
                            body)

        ret = None
        try:
            ret = fn(*original_args, **kwarg)
        #except Error as e:
        except Exception as e:
            print FLAGS.notification_driver
            body['error'] = "%s" % e
            api.notify(FLAGS.default_publisher_id,
                            name,
                            'ERROR',
                            body)
            raise e
        return ret
    return wrapped_func


def emit(self, record):
    if 'list_notifier_drivers' in FLAGS:
        if 'nova.notifier.log_notifier' in  FLAGS.list_notifier_drivers:
            return

    api.notify('nova.error.publisher', 'error_notification',
         api.ERROR, dict(error=self.format(record).split('\n')))


def notify(message):
    """Notifies the recipient of the desired event given the model.
    Log notifications using nova's default logging system"""
    #LOG.info('yyyyyyy666666666')
    nova_context = context.get_admin_context()
    message['method'] = 'notify'
    priority = message.get('priority',
                           FLAGS.default_notification_level)
    priority = priority.lower()
    #LOG.info('yyyyyyy777777')
    rpc.cast(nova_context, FLAGS.notification_topic, {'method': 'notify',
                                                 'args': {'message': message}})
    #LOG.info('yyyyyyy888888')

#Patching Emit function
nova.log.PublishErrorsHandler.emit = emit
