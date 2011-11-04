# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
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
Tests For nova.notifier.no_op_notifier
"""

from nova import compute
from nova import context
from nova import db
from nova import exception
from nova import flags
from nova import log as logging
from nova import rpc
from nova import test
from nova import utils
from nose.plugins.attrib import attr
from nova.notifier import api
from nova.notifier import no_op_notifier


class No_op_notifierTestCase(test.TestCase):
    """Test for nova.notifier.no_op_notifier. """
    def setUp(self):
        super(No_op_notifierTestCase, self).setUp()

    @attr(kind='small')
    def test_notify(self):
        """Test for nova.notifier.no_op_notifier.notify.
        Verify no_op_notifier.notify be called.
        No need to assert because this method has no implements"""

        def mock_import_object(message):
            return no_op_notifier

        self.stubs.Set(utils, 'import_object', mock_import_object)

        api.notify(api.publisher_id("compute"), 'event_type',
                   'DEBUG', dict(a=3))
