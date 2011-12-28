# Copyright 2010 OpenStack LLC.
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

from webob import exc

from nova import context
from nova import exception
from nova import flags
from nova import log as logging
from nova.api.openstack import wsgi
from nova.network import api


FLAGS = flags.FLAGS
LOG = logging.getLogger('nova.api.openstack')


class Controller(object):
    """ The Server API base controller class for the OpenStack API.
        networks API supports v1.1 only. """

    def __init__(self):
        self.network_api = api.API()

    def index(self, req):
        return exc.HTTPNotFound()

    def detail(self, req):
        return exc.HTTPNotFound()

    def show(self, req, id):
        return exc.HTTPNotFound()

    def create(self, req, body):
        return exc.HTTPNotFound()

    def delete(self, req, id):
        return exc.HTTPNotFound()


class ControllerV11(Controller):
    """v1.1 OpenStack API controller"""

    def _get_networks(self, req, is_detail):
        context = req.environ['nova.context']
        if context.project_id == "default":
            context.project_id = None

        networks = self.network_api.get_networks(context,
                      context.project_id, is_detail)
        return dict(networks=networks)

    def index(self, req):
        return self._get_networks(req, is_detail=False)

    def detail(self, req):
        return self._get_networks(req, is_detail=True)

    def show(self, req, id):
        context = req.environ['nova.context']
        if context.project_id == "default":
            context.project_id = None
        try:
            network = self.network_api.get_network_info(context, id)
        except exception.NetworkNotFoundForUUID:
            return exc.HTTPNotFound()

        return dict(network=network)

    def create(self, req, body):
        context = req.environ['nova.context']
        if context.project_id == "default":
            context.project_id = None

        if not body or not 'network' in body:
            raise exc.HTTPBadRequest()

        network_dict = body['network']

        try:
            network = self.network_api.create_network(context,
                         context.project_id, network_dict)
        except exception.ApiError as err:
            return exc.HTTPBadRequest(explanation=str(err))
        return dict(network=network)

    def delete(self, req, id):
        context = req.environ['nova.context']
        if context.project_id == "default":
            context.project_id = None
        try:
            self.network_api.delete_network(context, id)
        except exception.NetworkNotFoundForUUID:
            return exc.HTTPNotFound()


def create_resource(version):
    controller = {
        '1.0': Controller,
        '1.1': ControllerV11,
    }[version]()

    metadata = {
        "attributes": {
            "network": [ "created_at", "updated_at",
                         "id", "injected", "cidr",
                         "bridge", "gateway",
                         "dns1", "vlan", "vpn",
                         "vpn_private_address",
                         "dhcp_start", "project_id", "host",
                         "cidr_v6", "gateway_v6", "label",
                         "bridge_interface", "dhcp_server",
                         "multi_host", "dns2", "uuid", "priority" ]
        },
    }

    serializer = wsgi.ResponseSerializer({'application/xml': \
        wsgi.XMLDictSerializer(metadata=metadata, xmlns=wsgi.XMLNS_V11)})
    supported_content_types = ('application/json', 'application/xml')
    deserializer = wsgi.RequestDeserializer(
        supported_content_types=supported_content_types)

    return wsgi.Resource(controller, serializer=serializer,
                         deserializer=deserializer)
