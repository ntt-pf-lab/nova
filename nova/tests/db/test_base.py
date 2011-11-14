# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 NTT
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from nose.plugins.attrib import attr
import sys
from nova import db
from nova import test
from nova import flags

FLAGS = flags.FLAGS


class BaseTestCase(test.TestCase):
    def test_init(self):
        import_str = 'nova.db.migration'
        db_base = db.base.Base(db_driver=import_str)
        self.assertEqual(sys.modules[import_str], db_base.db)

    def test_init_db_driver_none(self):
        import_str = FLAGS.db_driver
        db_base = db.base.Base(db_driver=None)
        self.assertEqual(sys.modules[import_str], db_base.db)
