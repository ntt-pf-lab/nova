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
from nova import exception
from nova import flags
from nova import log as logging
from nova import utils
from nova.api.openstack import common
from nova.api.openstack import extensions

LOG = logging.getLogger("nova.api.contrib.eventlogs")
FLAGS = flags.FLAGS

SUPPORTED_FILTERS = {
    'limit': 'limit',
    'type': 'type',
    'offset': 'offset',
    'logged_since': 'created_at',
    'marker': 'marker'
}

RESPONSE_FIELDS = ['request_id', 'priority', 'message', 'status', 'event_type',
                 'user_id', 'id']

#expected filter field values
LOG_TYPES = ['DEBUG', 'INFO', 'ERROR', 'ALL']


class EventLogsController(object):
    """ EventLogs API controller for the Openstack API """

    def _get_filters(self, req):
        """
        Return a dictionary of query param filters from the request, validate
        the params and set default values for limit and offset if not provided

        :param req: the Request object coming from the wsgi layer
        :retval a dict of key/value filters
        """
        filters = {}
        for param in req.str_params:
            if param in SUPPORTED_FILTERS:
                value = req.str_params.get(param)

                if param == 'type' and value not in LOG_TYPES:
                    err_str = "Invalid log type: %s" % str(value)
                    raise webob.exc.HTTPBadRequest(explanation=err_str)
                if param in ['limit', 'offset', 'marker']:
                    err_str = "Invalid %s: %s" % (param, str(value))
                    try:
                        value = int(value)
                    except  ValueError:
                        raise webob.exc.HTTPBadRequest(explanation=err_str)
                    else:
                        if param == 'limit' and value <= 0:
                            raise webob.exc.HTTPBadRequest(explanation=err_str)
                        elif param == 'offset' and value < 0:
                            raise webob.exc.HTTPBadRequest(explanation=err_str)
                if param == 'logged_since':
                    try:
                        parsed = utils.parse_isotime(value)
                    except ValueError:
                        msg = _('Invalid logged_since: %s' % str(value))
                        raise webob.exc.HTTPBadRequest(explanation=msg)
                    value = parsed
                param = SUPPORTED_FILTERS[param]
                filters[param] = value
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
        return eventlogs

    def generate_href(self, req, eventlog_id):
        base_path = req.url
        query_params = []
        if req.query_string:
            base_path = req.path_url
            for param in req.query_string.split('&'):
                if param.find('marker') == -1:
                    query_params.append(param)

        query_params.append("marker=%d" % eventlog_id)
        next_href = base_path + "?" + '&'.join(query_params)
        return next_href

    def _build_links(self, req, logs, limited_logs):
        """Build the pagination links"""
        last_id = -1
        resultset_last_id = -1
        if limited_logs:
            last_id = limited_logs[-1]['id']
        if logs:
            resultset_last_id = logs[-1]['id']

        if last_id == -1 or last_id == resultset_last_id:
            return []
        link_dict = {'href': self.generate_href(req, last_id), 'rel': 'next'}
        return [link_dict]

    def _build(self, req, logs, limited_logs):
        """Build the paginated response body"""
        links = self._build_links(req, logs, limited_logs)
        result = {'eventlogs': self._build_response(limited_logs)}

        if links:
            result['eventlogs_links'] = links
        return result

    def index(self, req):
        """Validate the filters provided in request, apply filters and return
        the appropriate API Logs.
        """
        params = self._get_filters(req)
        params['type'] = params.get('type', 'ALL')
        logs = self._get_eventlogs(req, params)
        max_limit = max(params.get('limit'), FLAGS.pagination_limit)
        if params.get('marker'):
            limited_logs = common.limited_by_marker(logs,
                                                    req,
                                                    max_limit=max_limit)
        else:
            limited_logs = common.limited(logs, req, max_limit=max_limit)
        result = self._build(req, logs, limited_logs)
        return result

    def show(self, req, id):
        """Return data about the given request_id."""
        try:
            ctxt = req.environ['nova.context']
            eventlogs = db.api.eventlog_get_all_by_request_id(ctxt, id)
        except exception.NotFound:
            msg = _('Request id %s not found') % id
            raise webob.exc.HTTPNotFound(explanation=msg)

        result = {'eventlogs': self._build_response(eventlogs)}
        return result


class Eventlogs(extensions.ExtensionDescriptor):

    def get_name(self):
        return "Eventlogs"

    def get_alias(self):
        return "os-event-logs"

    def get_description(self):
        return "Eventlogs Support"

    def get_namespace(self):
        return "http://docs.openstack.org/ext/logs/api/v1.1"

    def get_updated(self):
        return "2011-12-12T00:00:00+00:00"

    def get_resources(self):
        resources = []

        res = extensions.ResourceExtension(
                'logs',
                EventLogsController())

        resources.append(res)
        return resources
