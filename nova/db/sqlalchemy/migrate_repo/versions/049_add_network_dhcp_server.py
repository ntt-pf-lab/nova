# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 NTT
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

from sqlalchemy import Column, Table, MetaData, String

meta = MetaData()

# Add dhcp_server colmun to networks table
dhcp_server = Column('dhcp_server',
                     String(length=255, convert_unicode=False,
                            assert_unicode=None, unicode_error=None,
                            _warn_on_bytestring=False))


def upgrade(migrate_engine):
    meta.bind = migrate_engine
    networks = Table('networks', meta, autoload=True)
    networks.create_column(dhcp_server)


def downgrade(migrate_engine):
    meta.bind = migrate_engine
    networks = Table('networks', meta, autoload=True)
    networks.drop_column(dhcp_server)
