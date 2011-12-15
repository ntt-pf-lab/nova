# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 XXX
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

from sqlalchemy import Column, Table, MetaData, Boolean

meta = MetaData()

use_gw = Column('use_gw', Boolean, default=True)


def upgrade(migrate_engine):
    meta.bind = migrate_engine

    fixed_ips = Table('fixed_ips', meta, autoload=True)
    fixed_ips.create_column(use_gw)


def downgrade(migrate_engine):
    meta.bind = migrate_engine

    fixed_ips = Table('fixed_ips', meta, autoload=True)
    fixed_ips.drop_column(use_gw)
