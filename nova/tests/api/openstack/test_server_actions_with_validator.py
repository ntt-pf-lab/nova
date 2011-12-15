import base64
import datetime
import json

import stubout
import webob

from nova import context
from nova import utils
from nova import exception
from nova import flags
from nova.api.openstack import validators
from nova import validation
from nova.api.openstack import create_instance_helper
from nova.compute import vm_states
from nova.compute import instance_types
import nova.db.api
from nova import test
from nova.tests.api.openstack import common
from nova.tests.api.openstack import fakes

FLAGS = flags.FLAGS


def return_server_by_id(context, id):
    return stub_instance(id)


def instance_update(context, instance_id, kwargs):
    return stub_instance(instance_id)


def return_server_with_attributes(**kwargs):
    def _return_server(context, id):
        return stub_instance(id, **kwargs)
    return _return_server


def return_server_with_state(vm_state, task_state=None):
    return return_server_with_attributes(vm_state=vm_state,
                                         task_state=task_state)


def return_server_with_uuid_and_state(vm_state, task_state=None):
    def _return_server(context, id):
        return return_server_with_state(vm_state, task_state)
    return _return_server


def stub_instance(id, metadata=None, image_ref="10", flavor_id="1",
                  name=None, vm_state=None, task_state=None):
    if metadata is not None:
        metadata_items = [{'key':k, 'value':v} for k, v in metadata.items()]
    else:
        metadata_items = [{'key':'seq', 'value':id}]

    inst_type = instance_types.get_instance_type_by_flavor_id(int(flavor_id))

    instance = {
        "id": int(id),
        "created_at": datetime.datetime(2010, 10, 10, 12, 0, 0),
        "updated_at": datetime.datetime(2010, 11, 11, 11, 0, 0),
        "admin_pass": "",
        "user_id": "fake",
        "project_id": "fake",
        "image_ref": image_ref,
        "kernel_id": "",
        "ramdisk_id": "",
        "launch_index": 0,
        "key_name": "",
        "key_data": "",
        "vm_state": vm_state or vm_states.ACTIVE,
        "task_state": task_state,
        "memory_mb": 0,
        "vcpus": 0,
        "local_gb": 0,
        "hostname": "",
        "host": "",
        "instance_type": dict(inst_type),
        "user_data": "",
        "reservation_id": "",
        "mac_address": "",
        "scheduled_at": utils.utcnow(),
        "launched_at": utils.utcnow(),
        "terminated_at": utils.utcnow(),
        "availability_zone": "",
        "display_name": name or "server%s" % id,
        "display_description": "",
        "locked": False,
        "metadata": metadata_items,
        "access_ip_v4": "",
        "access_ip_v6": "",
        "uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "virtual_interfaces": [],
    }

    instance["fixed_ips"] = {
        "address": '192.168.0.1',
        "floating_ips": [],
    }

    return instance


class MockSetAdminPassword(object):
    def __init__(self):
        self.instance_id = None
        self.password = None

    def __call__(self, context, instance_id, password):
        self.instance_id = instance_id
        self.password = password


class ServerActionsTestV11(test.TestCase):

    def setUp(self):
        self.maxDiff = None
        super(ServerActionsTestV11, self).setUp()
        self.stubs = stubout.StubOutForTesting()
        fakes.stub_out_auth(self.stubs)
        self.stubs.Set(nova.db.api, 'instance_get', return_server_by_id)
        self.stubs.Set(nova.db.api, 'instance_update', instance_update)

        fakes.stub_out_glance(self.stubs)
        fakes.stub_out_compute_api_snapshot(self.stubs)
        service_class = 'nova.image.glance.GlanceImageService'
        self.service = utils.import_object(service_class)
        self.context = context.RequestContext(1, None)
        self.service.delete_all()
        self.sent_to_glance = {}
        fakes.stub_out_glance_add_image(self.stubs, self.sent_to_glance)
        self.flags(allow_instance_snapshots=True)

    def tearDown(self):
        self.stubs.UnsetAll()

    def test_create_image_no_server(self):
        mapper = validators.APIValidateMapper() 
        mapper.map()
        validation.apply()

        body = {
            'createImage': {
                'name': 'Snapshot 1'
            }
        }
        req = webob.Request.blank('/v1.1/fake/servers/notfound/action')
        req.method = 'POST'
        req.body = json.dumps(body)
        req.headers["content-type"] = "application/json"
        response = req.get_response(fakes.wsgi_app())
        self.assertEqual(404, response.status_int)
