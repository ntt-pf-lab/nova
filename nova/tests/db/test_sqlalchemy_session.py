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
from nova.db.sqlalchemy import session as db_session
from nova import test
from nova import flags

import eventlet
import sqlalchemy


FLAGS = flags.FLAGS


class SQLAlchemySessionTestCase(test.TestCase):

    @attr(kind='small')
    def test_get_session(self):
        session = db_session.get_session()
        self.assertEqual("<class 'sqlalchemy.orm.session.Session'>",
                         str(session.__class__))

    @attr(kind='small')
    def test_get_session_configuration(self):
        """ Ensure get engine, get maker and return a SQLAlchemy session"""
        db_session._ENGINE = None
        db_session._MAKER = None
        session = db_session.get_session()
        self.assert_(db_session._ENGINE is not None)
        self.assert_(db_session._MAKER is not None)
        self.assertEqual("<class 'sqlalchemy.orm.session.Session'>",
                         str(session.__class__))

    @attr(kind='small')
    def test_get_session_parametar(self):
        """ Ensure return a SQLAlchemy session
            when parametar is not default"""
        session = db_session.get_session(autocommit=False,
                                         expire_on_commit=True)
        self.assertEqual("<class 'sqlalchemy.orm.session.Session'>",
                         str(session.__class__))

    @attr(kind='small')
    def test_get_engine_configuration_drivername_is_other(self):
        """ Ensure return a SQLAlchemy engine
            when drivername is not sqlite"""
        self.flags(sql_connection='other:///home/fake/other_db')

        def fake_create_engine(*cmd, **kwargs):
            return 'other.engine'

        self.stubs.Set(sqlalchemy, 'create_engine',
                       fake_create_engine)

        engine = db_session.get_engine()
        self.assertEqual('other.engine', engine)
