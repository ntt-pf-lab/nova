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
Unit Tests for remote procedure calls using queue
"""

import mox
import greenlet

from nova import context
from nova import db
from nova import exception
from nova import flags
from nova import rpc
from nova import test
from nova import service
from nova import manager
from nova import wsgi
from nova.compute import manager as compute_manager
from nose.plugins.attrib import attr
from nova.rpc import impl_kombu
from nova.db import sqlalchemy
FLAGS = flags.FLAGS
flags.DEFINE_string("fake_manager", "nova.tests.test_service.FakeManager",
                    "Manager for testing")


class FakeManager(manager.Manager):
    """Fake manager for tests"""
    def test_method(self):
        return 'manager'


class ExtendedService(service.Service):
    def test_method(self):
        return 'service'


class ServiceManagerTestCase(test.TestCase):
    """Test cases for Services"""
    def test_message_gets_to_manager(self):
        serv = service.Service('test',
                               'test',
                               'test',
                               'nova.tests.test_service.FakeManager')
        serv.start()
        self.assertEqual(serv.test_method(), 'manager')

    def test_override_manager_method(self):
        serv = ExtendedService('test',
                               'test',
                               'test',
                               'nova.tests.test_service.FakeManager')
        serv.start()
        self.assertEqual(serv.test_method(), 'service')

    @attr(kind='small')
    def test_start_and_kill(self):
        host = 'foo'
        binary = 'nova-fake'
        topic = 'volume'

        admin_context = context.get_admin_context()
        app = service.Service.create(host=host,
                                     binary=binary,
                                     topic=topic)
        self.assertRaises(exception.HostBinaryNotFound,
                          service.db.service_get_by_args,
                          admin_context, host, binary)
        app.start()
        service_ref = db.service_get_by_args(admin_context, host, binary)
        self.assert_(topic, service_ref['topic'])
        app.kill()
        self.assertRaises(exception.HostBinaryNotFound,
                          service.db.service_get_by_args,
                          admin_context, host, binary)

    @attr(kind='small')
    def test_service_and_periodic_tasks(self):
        self.error_list = []

        def fake_manager_periodic_tasks(*args, **kwargs):
            self.error_list = ['error', 'test', 'sample']
            return self.error_list

        host = 'foo'
        binary = 'nova-volume'
        topic = 'volume'
        self.stubs.Set(manager.Manager,
                       'periodic_tasks',
                       fake_manager_periodic_tasks)
        app = service.Service.create(host=host,
                                     binary=binary,
                                     topic=topic)
        app.periodic_tasks()
        self.assertEqual(self.error_list, ['error', 'test', 'sample'])


class ServiceFlagsTestCase(test.TestCase):

    def test_service_enabled_on_create_based_on_flag(self):
        self.flags(enable_new_services=True)
        host = 'foo'
        binary = 'nova-fake'
        app = service.Service.create(host=host, binary=binary)
        app.start()
        app.stop()
        ref = db.service_get(context.get_admin_context(), app.service_id)
        db.service_destroy(context.get_admin_context(), app.service_id)
        self.assert_(not ref['disabled'])

    def test_service_disabled_on_create_based_on_flag(self):
        self.flags(enable_new_services=False)
        host = 'foo'
        binary = 'nova-fake'
        app = service.Service.create(host=host, binary=binary)
        app.start()
        app.stop()
        ref = db.service_get(context.get_admin_context(), app.service_id)
        db.service_destroy(context.get_admin_context(), app.service_id)
        self.assert_(ref['disabled'])


class FlagsOfServiceTestCase(test.TestCase):
    """Test cases for flags of Service class"""

    @attr(kind='small')
    def setUp(self):
        super(FlagsOfServiceTestCase, self).setUp()
        self.rpc_backend = FLAGS.rpc_backend
        FLAGS.rpc_backend = 'nova.rpc.impl_carrot'

    @attr(kind='small')
    def tearDown(self):
        FLAGS.rpc_backend = self.rpc_backend
        super(FlagsOfServiceTestCase, self).tearDown()

    @attr(kind='small')
    def test_service_flags_report_interval_is_on(self):
        self.flags(enable_new_services=False)
        host = 'foo'
        binary = 'nova-fake'
        app = service.Service.create(host=host,
                                     binary=binary,
                                     report_interval=10)
        app.start()
        app.stop()
        ref = db.service_get(context.get_admin_context(), app.service_id)
        db.service_destroy(context.get_admin_context(), app.service_id)
        self.assert_(ref['disabled'])

    @attr(kind='small')
    def test_service_flags_periodic_interval_is_one(self):
        self.flags(enable_new_services=True)
        host = 'foo'
        binary = 'nova-fake'
        app = service.Service.create(host=host,
                                     binary=binary,
                                     periodic_interval=20)
        app.start()
        app.stop()
        ref = db.service_get(context.get_admin_context(), app.service_id)
        db.service_destroy(context.get_admin_context(), app.service_id)
        self.assert_(not ref['disabled'])


class ServiceAndStopTestCase(test.TestCase):
    '''Testcases for Stop method of Service class occurs iteration'''

    @attr(kind='small')
    def setUp(self):
        super(ServiceAndStopTestCase, self).setUp()
        self.rpc_backend = FLAGS.rpc_backend
        FLAGS.rpc_backend = 'nova.rpc.impl_carrot'
        self.mox.StubOutWithMock(service, 'db')

    @attr(kind='small')
    def tearDown(self):
        FLAGS.rpc_backend = self.rpc_backend
        super(ServiceAndStopTestCase, self).tearDown()

    @attr(kind='small')
    def test_service_and_stop_parameter_timers_is_one(self):
        host = 'foo'
        binary = 'bar'
        topic = 'test'
        service_ref = {'id': 1,
                       'host': host,
                       'binary': binary,
                       'topic': topic,
                       'report_count': 1,
                       'availability_zone': 'nova'}

        service.db.service_get_by_args(mox.IgnoreArg(),
                                      host,
                                      binary).AndReturn(service_ref)
        self.mox.ReplayAll()
        serv = service.Service(host,
                               binary,
                               topic,
                               'nova.tests.test_service.FakeManager',
                               report_interval=10)
        serv.start()
        serv.model_disconnected = True
        serv.report_state()
        serv.stop()
        self.assertEquals([], serv.timers)


class ServiceTestCase(test.TestCase):
    """Test cases for Services"""

    def setUp(self):
        super(ServiceTestCase, self).setUp()
        self.mox.StubOutWithMock(service, 'db')

    @attr(kind='small')
    def test_service_and_create_parameter_manager_is_not_None(self):
        host = 'foo'
        binary = 'nova-volume'
        topic = 'volume'
        manager = 'nova.volume.manager.VolumeManager'
        app = service.Service.create(host=host,
                                     binary=binary,
                                     topic=topic,
                                     manager=manager)
        self.assertTrue(isinstance(app, service.Service))

    def test_create(self):
        host = 'foo'
        binary = 'nova-fake'
        topic = 'fake'

        # NOTE(vish): Create was moved out of mox replay to make sure that
        #             the looping calls are created in StartService.
        app = service.Service.create(host=host, binary=binary, topic=topic)

        self.assert_(app)

    def test_report_state_newly_disconnected(self):
        host = 'foo'
        binary = 'bar'
        topic = 'test'
        service_create = {'host': host,
                          'binary': binary,
                          'topic': topic,
                          'report_count': 0,
                          'availability_zone': 'nova'}
        service_ref = {'host': host,
                          'binary': binary,
                          'topic': topic,
                          'report_count': 0,
                          'availability_zone': 'nova',
                          'id': 1}

        service.db.service_get_by_args(mox.IgnoreArg(),
                                      host,
                                      binary).AndRaise(exception.NotFound())
        service.db.service_create(mox.IgnoreArg(),
                                  service_create).AndReturn(service_ref)
        service.db.service_get(mox.IgnoreArg(),
                               mox.IgnoreArg()).AndRaise(Exception())

        self.mox.ReplayAll()
        serv = service.Service(host,
                               binary,
                               topic,
                               'nova.tests.test_service.FakeManager')
        serv.start()
        serv.report_state()
        self.assert_(serv.model_disconnected)

    def test_report_state_newly_connected(self):
        host = 'foo'
        binary = 'bar'
        topic = 'test'
        service_create = {'host': host,
                          'binary': binary,
                          'topic': topic,
                          'report_count': 0,
                          'availability_zone': 'nova'}
        service_ref = {'host': host,
                          'binary': binary,
                          'topic': topic,
                          'report_count': 0,
                          'availability_zone': 'nova',
                          'id': 1}

        service.db.service_get_by_args(mox.IgnoreArg(),
                                      host,
                                      binary).AndRaise(exception.NotFound())
        service.db.service_create(mox.IgnoreArg(),
                                  service_create).AndReturn(service_ref)
        service.db.service_get(mox.IgnoreArg(),
                               service_ref['id']).AndReturn(service_ref)
        service.db.service_update(mox.IgnoreArg(), service_ref['id'],
                                  mox.ContainsKeyValue('report_count', 1))

        self.mox.ReplayAll()
        serv = service.Service(host,
                               binary,
                               topic,
                               'nova.tests.test_service.FakeManager')
        serv.start()
        serv.model_disconnected = True
        serv.report_state()

        self.assert_(not serv.model_disconnected)

    @attr(kind='small')
    def test_service_and_create_parameter_binary_is_None(self):
        host = 'foo'
        binary = None
        topic = 'volume'
        manager = 'nova.volume.manager.VolumeManager'
        report_interval = 10

        result = service.Service.create(host=host,
                                        binary=binary,
                                        topic=topic,
                                        manager=manager,
                                        report_interval=report_interval)
        self.assert_(isinstance(result, service.Service))

    @attr(kind='small')
    def test_service_and_stop_exception_conn_close_pass(self):
        def fake_conn_close():
            return exception

        host = 'foo'
        binary = 'nova-volume'
        topic = 'volume'
        manager = 'nova.volume.manager.VolumeManager'
        self.stubs.Set(rpc.impl_carrot, 'Connection', fake_conn_close)
        app = service.Service.create(host=host,
                                     binary=binary,
                                     topic=topic,
                                     manager=manager)
        self.assertEqual(None, app.stop())
        self.assertEquals([], app.timers)


class TestWSGIService(test.TestCase):

    def setUp(self):
        super(TestWSGIService, self).setUp()
        self.stubs.Set(wsgi.Loader, "load_app", mox.MockAnything())

    def test_service_random_port(self):
        test_service = service.WSGIService("test_service")
        self.assertEquals(0, test_service.port)
        test_service.start()
        self.assertNotEqual(0, test_service.port)
        test_service.stop()


class TestLauncher(test.TestCase):

    def setUp(self):
        super(TestLauncher, self).setUp()
        self.stubs.Set(wsgi.Loader, "load_app", mox.MockAnything())
        self.service = service.WSGIService("test_service")

    def test_launch_app(self):
        self.assertEquals(0, self.service.port)
        launcher = service.Launcher()
        launcher.launch_server(self.service)
        self.assertEquals(0, self.service.port)
        launcher.stop()

    @attr(kind='small')
    def test_launcher_and_run_server_configuration_start(self):
        self.stub_flg = False

        def fake_wait(*args, **kwargs):
            self.stub_flg = True
            return 'passed wait method'

        self.stubs.Set(service.Service, 'wait', fake_wait)
        server = service.Service.create(binary='nova-compute')
        self.assertEqual(None, service.Launcher().run_server(server))
        self.assert_(self.stub_flg)

    @attr(kind='small')
    def test_launcher_and_stop_configuration_iter_is_zero(self):
        launcher = service.Launcher()
        launcher._services = []
        result = launcher.stop()
        self.assertEqual(None, result)

    @attr(kind='small')
    def test_launcher_and_wait_configuration_iter_is_zero(self):
        launcher = service.Launcher()
        launcher._services = []
        result = launcher.wait()
        self.assertEqual(None, result)

    @attr(kind='small')
    def test_launcher_and_wait_configuration_iter_is_one(self):
        server = service.Service.create(binary='nova-compute')
        launcher = service.Launcher()
        launcher._services = [server]
        result = launcher.wait()
        self.assertEqual(None, result)

    @attr(kind='small')
    def test_launcher_and_wait_configuration_iter_is_three(self):
        self.num = 0

        def fake_wait(*args, **kwargs):
            if fake_wait:
                self.num += 1

        self.stubs.Set(service.Service, 'wait', fake_wait)
        server1 = service.Service.create(binary='nova-compute')
        server2 = service.Service.create(binary='nova-volume')
        server3 = service.Service.create(binary='nova-network')
        launcher = service.Launcher()
        launcher._services = [server1, server2, server3]
        launcher._services
        self.assertFalse(0, self.num)
        launcher.wait()
        self.assertEqual(3, self.num)

    @attr(kind='small')
    def test_launcher_and_wait_exception(self):
        self.stub_flg = False

        def fake_wait(*args, **kwargs):
            self.stub_flg = True
            raise greenlet.GreenletExit

        self.stubs.Set(service.Service, 'wait', fake_wait)
        server = service.Service.create(binary='nova-compute')
        launcher = service.Launcher()
        launcher._services = [server]
        result = launcher.wait()
        self.assert_(self.stub_flg)
        self.assertEqual(None, result)

    @attr(kind='small')
    def test_serve_configuration_launcher_is_None(self):
        app = service.serve()
        self.assertEqual(None, app)

    @attr(kind='small')
    def test_serve_configuration_launcher_is_not_None(self):
        server = service.Service.create(binary='nova-compute')
        launcher = service.Launcher()
        launcher._services = [server]
        app = service.serve()
        self.assertEqual(None, app)

    @attr(kind='small')
    def test_wait_normal(self):
        app = service.wait()
        self.assertEqual(None, app)

    @attr(kind='small')
    def test_wait_exception_KeyboardInterrupt(self):
        self.stub_flg = False

        def fake_wait(*args, **kwargs):
            self.stub_flg = True
            raise KeyboardInterrupt

        self.stubs.Set(service.Launcher, 'wait', fake_wait)
        app = service.wait()
        self.assert_(self.stub_flg)
        self.assertEqual(None, app)
