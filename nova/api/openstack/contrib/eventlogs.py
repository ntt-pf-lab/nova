# vim: tabstop=4 shiftwidth=4 softtabstop=4

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

""" EventLog API extension"""

import webob
from nova import db
from nova.api.openstack import extensions
from nova import log as logging
from nova import exception

LOG = logging.getLogger("nova.api.contrib.eventlogs")

SUPPORTED_FILTERS = {
    'limit': 'limit',
    'type': 'type',
    'offset': 'offset',
    'logged_since': 'created_at'
}

RESPONSE_FIELDS = ['request_id', 'priority', 'message', 'status', 'event_type',
                 'user_id']


class EventLogsController(object):
    """ EventLogs API controller for the Openstack API """

    def _get_filters(self, req):
        """
        Return a dictionary of query param filters from the request

        :param req: the Request object coming from the wsgi layer
        :retval a dict of key/value filters
        """
        filters = {}
        for param in req.str_params:
            if param in SUPPORTED_FILTERS:
                filters[param] = req.str_params.get(param)
        return filters

    def _build_response(self, logs):
        """Filters out the required fields from DB response."""
        log_list = []
        for log in logs:
            log_dict = {}
            for field in RESPONSE_FIELDS:
                log_dict[field] = log[field]
            log_list.append(log_dict)
        return log_list

    def _get_eventlogs(self, req, filters, is_detail=True):
        """Helper function that returns a list of eventlogs dicts."""
        ctxt = req.environ['nova.context']
        eventlogs = db.api.eventlog_get_all(ctxt, filters)
        result = {'eventlogs': self._build_response(eventlogs)}
        return result

    def index(self, req):
        """
        Return API Logs
        """
        filters = self._get_filters(req)
        return self._get_eventlogs(req, filters)

    def show(self, req, id):
        """Return data about the given request_id."""
        try:
            ctxt = req.environ['nova.context']
            eventlogs = db.api.eventlog_get_all_by_request_id(ctxt, id)
        except exception.NotFound:
            return webob.exc.HTTPNotFound()

        result = {'eventlogs': self._build_response(eventlogs)}
        return result


class Eventlogs(extensions.ExtensionDescriptor):

    def get_name(self):
        return "Eventlogs"

    def get_alias(self):
        return "eventlogs"

    def get_description(self):
        return "Eventlogs Support"

    def get_namespace(self):
        return \
         "http://docs.openstack.org/ext/logs/api/v1.1"

    def get_updated(self):
        return "2011-12-12T00:00:00+00:00"

    def get_resources(self):
        resources = []

        res = extensions.ResourceExtension(
                'logs',
                EventLogsController())

        resources.append(res)
        return resources
