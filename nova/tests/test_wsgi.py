# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 United States Government as represented by the
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

"""Unit tests for `nova.wsgi`."""

import os.path
import tempfile

import unittest

import nova.exception
import nova.test
import nova.wsgi

from nova import test
from nova import wsgi
from nova import exception
from nose.plugins.attrib import attr
import webob
from eventlet.greenio import GreenSocket as gsocket
from eventlet import greenthread
import socket
import greenlet
import routes


class TestLoaderNothingExists(unittest.TestCase):
    """Loader tests where os.path.exists always returns False."""

    def setUp(self):
        self._os_path_exists = os.path.exists
        os.path.exists = lambda _: False

    def test_config_not_found(self):
        self.assertRaises(
            nova.exception.PasteConfigNotFound,
            nova.wsgi.Loader,
        )

    def tearDown(self):
        os.path.exists = self._os_path_exists


class TestLoaderNormalFilesystem(unittest.TestCase):
    """Loader tests with normal filesystem (unmodified os.path module)."""

    _paste_config = """
[app:test_app]
use = egg:Paste#static
document_root = /tmp
    """

    def setUp(self):
        self.config = tempfile.NamedTemporaryFile(mode="w+t")
        self.config.write(self._paste_config.lstrip())
        self.config.seek(0)
        self.config.flush()
        self.loader = nova.wsgi.Loader(self.config.name)

    def test_config_found(self):
        self.assertEquals(self.config.name, self.loader.config_path)

    def test_app_not_found(self):
        self.assertRaises(
            nova.exception.PasteAppNotFound,
            self.loader.load_app,
            "non-existant app",
        )

    def test_app_found(self):
        url_parser = self.loader.load_app("test_app")
        self.assertEquals("/tmp", url_parser.directory)

    def tearDown(self):
        self.config.close()


class TestWSGIServer(unittest.TestCase):
    """WSGI server tests."""

    def test_no_app(self):
        server = nova.wsgi.Server("test_app", None)
        self.assertEquals("test_app", server.name)

    def test_start_random_port(self):
        server = nova.wsgi.Server("test_random_port", None, host="127.0.0.1")
        self.assertEqual(0, server.port)
        server.start()
        self.assertNotEqual(0, server.port)
        server.stop()
        server.wait()


class FakeApp(wsgi.Application):
    """ fake wsgi app implement for test"""

    def __init__(self, app):
        self.app = app

    @webob.dec.wsgify(RequestClass=webob.Request)
    def __call__(self, req):
        return '200 OK\n'


class ServerTestCase(test.TestCase):
    """Test for nova.wsgi.Server"""

    def setUp(self):
        super(ServerTestCase, self).setUp()
        self.app = FakeApp('test')
        self.server = wsgi.Server(name='server1', app=self.app,
                                  host='127.0.0.1', port=1234, pool_size=3)

    def tearDown(self):
        super(ServerTestCase, self).tearDown()

        try:
            self.server.stop()
        except Exception:
            pass

        try:
            self.server._socket.close()
        except Exception:
            pass

    @attr(kind='small')
    def test_start(self):
        """Test for nova.wsgi.Server.start.
        Make sure server be start with socket listening"""

        self.sock_host = None
        self.sock_port = None

        def fake_accept(sock):
            # for assertion
            self.sock_host, self.sock_port = sock.getsockname()[:2]

        self.stubs.Set(gsocket, 'accept', fake_accept)

        self.server.start(backlog=2)

        # switch to server greenthread
        greenthread.sleep(0)
        self.assertEqual('127.0.0.1', self.sock_host)
        self.assertEqual(1234, self.sock_port)

    @attr(kind='small')
    def test_start_parameter_backlog(self):
        """Test for nova.wsgi.Server.start.
        Verify number of queued socket connections.
        Parameter backlog Should be at least 1.
        But no error raised even is minus, Maybe need validation"""

        self.sock_host = None
        self.sock_port = None

        def fake_accept(sock):
            # for assertion
            self.sock_host, self.sock_port = sock.getsockname()[:2]

        self.stubs.Set(gsocket, 'accept', fake_accept)
        self.assertRaises(exception.InvalidInput,
                          self.server.start,
                          backlog=0)

    @attr(kind='small')
    def test_start_exception(self):
        """Test for nova.wsgi.Server.start.
        The server thread will be terminate if unexpected exception raised"""

        def fake_accept(sock):
            # raise unexpected exception to make thread exit
            raise socket.error

        self.stubs.Set(gsocket, 'accept', fake_accept)

        self.server.start()

        # switch to server greenthread
        greenthread.sleep(0)
        self.assertTrue(self.server._server.dead)
        # start again to confirm socket is not binding
        self.server.start()

    @attr(kind='small')
    def test_start_tcp(self):
        """Test for nova.wsgi.Server.start_tcp.
        Make sure tcp server be start with socket listening"""

        self.sock_host = None
        self.sock_port = None

        def fake_accept(sock):
            # for assertion
            self.sock_host, self.sock_port = sock.getsockname()[:2]

        self.stubs.Set(gsocket, 'accept', fake_accept)

        self.server.start_tcp(self.app, 1235, host='127.0.0.1',
                                    key=None, backlog=128)

        # switch to server greenthread
        greenthread.sleep(0)
        self.assertEqual('127.0.0.1', self.sock_host)
        self.assertEqual(1235, self.sock_port)

    @attr(kind='small')
    def test_start_tcp_parameter(self):
        """Test for nova.wsgi.Server.start_tcp.
        Pass through any exception to caller for invalid parameter"""

        self.assertRaises(TypeError,
                self.server.start_tcp, self.app, port=None, host='127.0.0.1',
                                    key=None, backlog=0)

    @attr(kind='small')
    def test_start_tcp_exception(self):
        """Test for nova.wsgi.Server.start_tcp.
        Pass through any exception to caller"""

        self.server.start_tcp(self.app, 1237, host='127.0.0.1',
                                    key=None, backlog=-1)

        # start twice will be raise socket error
        self.assertRaises(socket.error,
                self.server.start_tcp, self.app, 1237, host='127.0.0.1',
                key=None, backlog=2)

    @attr(kind='small')
    def test_start_tcp_exception_terminate(self):
        """Test for nova.wsgi.Server.start_tcp.
        Server thread will be terminate if socket exception happened"""

        self.sock_host = None
        self.sock_port = None

        def fake_accept(sock):
            # for assertion
            self.sock_host, self.sock_port = sock.getsockname()[:2]
            # uncatched exception, exit
            raise socket.error

        self.stubs.Set(gsocket, 'accept', fake_accept)

        self.server.start_tcp(self.app, 1245, host='127.0.0.1',
                                    key=None, backlog=128)

        # switch to server greenthread
        greenthread.sleep(0)
        self.assertEqual('127.0.0.1', self.sock_host)
        self.assertEqual(1245, self.sock_port)

    @attr(kind='small')
    def test_start_tcp_exception_continue(self):
        """Test for nova.wsgi.Server.start_tcp. Server thread will be continue
        even if SystemExit and KeyboardInterrupt exception happened"""

        self.sock_host = None
        self.sock_port = None
        self.sock_accept_counter = 0

        def fake_accept(sock):
            # for assertion
            self.sock_host, self.sock_port = sock.getsockname()[:2]
            self.sock_accept_counter += 1

            if self.sock_accept_counter >= 10:
                # uncatched exception, exit
                raise socket.error
            else:
                # catched exception, continue
                raise SystemExit

        self.stubs.Set(gsocket, 'accept', fake_accept)

        self.server.start_tcp(self.app, 1246, host='127.0.0.1',
                                    key=None, backlog=128)

        # switch to server greenthread
        greenthread.sleep(0)
        self.assertEqual('127.0.0.1', self.sock_host)
        self.assertEqual(1246, self.sock_port)
        self.assertEqual(True, self.sock_accept_counter >= 10)

    @attr(kind='small')
    def test_stop(self):
        """Test for nova.wsgi.Server.stop.
        Verify server thread be terminated and socket be closed"""

        self.server.start()
        # switch to server greenthread
        greenthread.sleep(0)
        self.assertEqual(False, self.server._server.dead)

        self.server.stop()

        self.assertEqual(True, self.server._server.dead)
        # confirm socket be closed
        self.server.start(backlog=128)

    @attr(kind='small')
    def test_stop_parameter_tcp(self):
        """Test for nova.wsgi.Server.stop.
        Verify tcp server thread be terminated and socket be closed"""

        self.server.start_tcp(self.app, 1238, host='127.0.0.1',
                                    key=None, backlog=2)
        # switch to server greenthread
        greenthread.sleep(0)
        self.server.stop()
        self.assertEqual(None, self.server._tcp_server)

    @attr(kind='small')
    def test_wait(self):
        """Test for nova.wsgi.Server.wait.
        Current thread be blocked when calling wait,
        and wakeup until a result be returned or exception raised"""

        self.sock_host = None
        self.sock_port = None

        def fake_accept(sock):
            # block a while
            greenthread.sleep(0.3)

            # for assertion
            self.sock_host, self.sock_port = sock.getsockname()[:2]
            # raise a exception for wake up
            raise socket.error

        self.stubs.Set(gsocket, 'accept', fake_accept)

        self.server.start()

        # wait a while , but server thread is not available
        greenthread.sleep(0.1)
        self.assertEqual(None, self.sock_host)
        self.assertEqual(None, self.sock_port)

        self.assertRaises(socket.error,
                          self.server.wait)

        self.assertEqual('127.0.0.1', self.sock_host)
        self.assertEqual(1234, self.sock_port)

    @attr(kind='small')
    def test_wait_exception(self):
        """Test for nova.wsgi.Server.wait.
        Current thread be blocked when calling wait,
        and return normally when GreenletExit exception raised"""

        self.sock_host = None
        self.sock_port = None

        def fake_wait(sock):
            # for assertion
            self.sock_host, self.sock_port = ('127.0.0.1', 1234)
            # raise a exception for wake up
            raise greenlet.GreenletExit

        self.stubs.Set(greenthread.GreenThread, 'wait', fake_wait)

        self.server.start()
        # switch to server greenthread
        greenthread.sleep(0)

        #greenlet.GreenletExit be catch in wait
        self.server.wait()

        self.assertEqual('127.0.0.1', self.sock_host)
        self.assertEqual(1234, self.sock_port)


class ApplicationTestCase(test.TestCase):
    """Test for nova.wsgi.Application. """
    def setUp(self):
        super(ApplicationTestCase, self).setUp()
        self.application = wsgi.Application()

    @attr(kind='small')
    def test_call_exception(self):
        """Test for nova.wsgi.Application.__call__
        Make sure NotImplementedError be raised"""

        self.assertRaises(NotImplementedError,
            self.application, environ=None, start_response=None)

    @attr(kind='small')
    def test_factory(self):
        """Test for nova.wsgi.Application.factory. Verify return class type"""

        ref = wsgi.Application.factory(None)

        self.assertEqual('Application', ref.__class__.__name__)

    @attr(kind='small')
    def test_factory_parameter(self):
        """Test for nova.wsgi.Application.factory.
        Verify local_config parameter be passed to __init__
        Raise a TypeError because not implement __init__ with parameters"""

        local_config = dict(arg1='1')

        # do not implements __init__ with parameter at this super class
        self.assertRaises(TypeError,
                    wsgi.Application.factory, None, **local_config)

    @attr(kind='small')
    def test_factory_parameter_init(self):
        """Test for nova.wsgi.Application.factory.
        Verify called from implement class, and parameter be pass to init"""

        local_config = dict(app='testapp')

        # FakeApp implements Application
        ref = FakeApp.factory(None, **local_config)

        self.assertEqual('testapp', ref.app)


class MiddlewareTestCase(test.TestCase):
    """Test for nova.wsgi.Middleware. """
    def setUp(self):
        super(MiddlewareTestCase, self).setUp()

    @attr(kind='small')
    def test_factory(self):
        """Test for nova.wsgi.Middleware.factory.
        Verify factory with a application parameter"""

        factory = wsgi.Middleware.factory(global_config=None)
        ref = factory(app='testapp')
        self.assertEqual('testapp', ref.application)

    @attr(kind='small')
    def test_init_parameter(self):
        """Test for nova.wsgi.Middleware.factory.
        Verify parameter be pass to __init__"""

        local_config = dict(key1='1')

        ref = wsgi.Middleware.factory(global_config=None,
                                          **local_config)(app='testapp')

        self.assertEqual('testapp', ref.application)

    @attr(kind='small')
    def test_call(self):
        """Test for nova.wsgi.Middleware.process_request.
        Verify app's __call__ be executed"""

        middleware = wsgi.Middleware.factory(global_config=None)(
                                    app=FakeApp('fake'))
        env = dict(REQUEST_METHOD='HEAD')

        # __call__
        ref = middleware(req=webob.Request(env))

        self.assertTrue(ref.status.startswith('200'))

    @attr(kind='small')
    def test_call_parameter_none(self):
        """Test for nova.wsgi.Middleware.__call__.
        Verify req parameter is None"""

        middleware = wsgi.Middleware.factory(global_config=None)(
                                    app=FakeApp('fake'))

        # __call__
        ref = middleware(req=None)

        self.assertEqual(False, ref.status.startswith('200'))

    @attr(kind='small')
    def test_process_request(self):
        """Test for nova.wsgi.Middleware.process_request.
        Make sure return None"""

        middleware = wsgi.Middleware.factory(global_config=None)(
                                    app=FakeApp('fake'))

        ref = middleware.process_request(req='abc')

        self.assertEqual(None, ref)

    @attr(kind='small')
    def test_process_response(self):
        """Test for nova.wsgi.Middleware.process_response.
        Make sure just return parameter's value"""

        middleware = wsgi.Middleware.factory(global_config=None)(
                                    app=FakeApp('fake'))
        response = '200 ok , header'

        ref = middleware.process_response(response)

        self.assertEqual(response, ref)


class DebugTestCase(test.TestCase):
    """Test for nova.wsgi.Debug. """
    def setUp(self):
        super(DebugTestCase, self).setUp()

    @attr(kind='small')
    def test_call(self):
        """Test for nova.wsgi.Debug.__call__.
        Make sure request and response be log out"""

        debug = wsgi.Debug.factory(global_config=None)(
                                    app=FakeApp('fake'))

        env = dict(REQUEST_METHOD='HEAD')
        # __call__
        ref = debug(req=webob.Request(env))

        self.assertEqual(True, ref.status.startswith('200'))
        self.assertNotEqual(None, ref.app_iter)

    @attr(kind='small')
    def test_print_generator(self):
        """Test for nova.wsgi.Debug.print_generator.
        Make sure generator print out body contents"""

        list = ['1', '2']
        gen = wsgi.Debug.print_generator(list)

        ref0 = gen.next()
        self.assertEqual(list[0], ref0)

        ref1 = gen.next()
        self.assertEqual(list[1], ref1)


class LoaderTestCase(test.TestCase):
    """Test for nova.wsgi.Loader. """
    def setUp(self):
        super(LoaderTestCase, self).setUp()

    @attr(kind='small')
    def test_init_configuration(self):
        """Test for nova.wsgi.Loader.__init__.
        Should raise PasteConfigNotFound
        if config flag and parameter is None"""

        self.flags(api_paste_config=None)

        self.assertRaises(exception.PasteConfigNotFound,
                          wsgi.Loader, config_path=None)

    @attr(kind='small')
    def test_load_app_parameter(self):
        """Test for nova.wsgi.Loader.load_app.
        Verify config exist and app not exist """

        loader = wsgi.Loader(config_path='../../etc/nova/api-paste.ini')

        self.assertRaises(exception.PasteAppNotFound,
                          loader.load_app, 'noauth')


class RouterTestCase(test.TestCase):
    """Test for nova.wsgi.Router. """
    def setUp(self):
        super(RouterTestCase, self).setUp()

    @attr(kind='small')
    def test_init(self):
        """Test for nova.wsgi.Router.init.
        Verify parameter be set to instance field"""

        mapper = routes.Mapper()

        router = wsgi.Router(mapper)

        self.assertEqual(mapper, router.map)
        self.assertEqual(mapper, router._router.mapper)

    @attr(kind='small')
    def test_init_parameter(self):
        """Test for nova.wsgi.Router.init.
        Verify mapper parameter can be None"""

        mapper = None

        router = wsgi.Router(mapper)

        self.assertEqual(mapper, router.map)
        self.assertEqual(mapper, router._router.mapper)

    @attr(kind='small')
    def test_call_parameter_notfound(self):
        """Test for nova.wsgi.Router.call.
        Verify return 404 error when request is not in mapping"""

        def fake_start_response(status, header):
            pass

        mapper = routes.Mapper()
        mapper.connect(None, '/abc/{path_info:.*}',
                       controller=FakeApp('testapp'))

        router = wsgi.Router(mapper)
        router._router.singleton = False

        env = dict(REQUEST_METHOD='GET', SERVER_NAME='localhost',
                   SERVER_PORT='8080', PATH_INFO='/bac/')
        env.update({'wsgi.url_scheme': 'http'})

        # __call__
        ref = router(req=webob.Request(env))(env, fake_start_response)

        self.assertTrue(ref[0].startswith('404 Not Found'))

    @attr(kind='small')
    def test_call(self):
        """Test for nova.wsgi.Router.call.
        Verify mapper's controller app be executed for matching url"""

        def fake_start_response(status, header):
            pass

        mapper = routes.Mapper()
        mapper.connect(None, 'url1',
                       controller=FakeApp('testapp'))

        router = wsgi.Router(mapper)
        router._router.singleton = False

        env = dict(REQUEST_METHOD='GET', SERVER_NAME='localhost',
                   SERVER_PORT='8080', PATH_INFO='url1')
        env.update({'wsgi.url_scheme': 'http'})
        env.update({'wsgi.url_scheme': 'http'})

        # __call__
        ref = router(req=webob.Request(env))(env, fake_start_response)

        self.assertTrue(ref[0].startswith('200 OK'))
