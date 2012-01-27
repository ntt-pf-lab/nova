# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 VA Linux Systems Japan K.K
# Copyright (c) 2011 Isaku Yamahata
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

from nova import exception
from nova import volume
from nova import log as logging

LOG = logging.getLogger("nova.compute.utils")


def terminate_volumes(db, context, instance_id):
    """delete volumes of delete_on_termination=True in block device mapping"""
    # parameter check
    try:
        db.instance_get(context, instance_id)
        bdms = db.block_device_mapping_get_all_by_instance(context,
                                                           instance_id)
        if not bdms:
            raise exception.InstanceNotFound
    except exception.InstanceNotFound:
        LOG.error(_('Parameter is invalid. instance_id=%s'), instance_id)
        raise

    ex_flag = False
    volume_api = volume.API()
    for bdm in bdms:
        #LOG.debug(_("terminating bdm %s") % bdm)
        if bdm['volume_id'] and bdm['delete_on_termination']:
            try:
                volume_api.delete(context, bdm['volume_id'])
            except exception.ApiError as ex:
                ex_flag = True
                vid = bdm['volume_id']
                LOG.error(
                    _('Exception occurred in deleting volume|%(vid)s|: %(ex)s')
                          % locals())

        try:
            db.block_device_mapping_destroy(context, bdm['id'])
        except exception.DBError as ex:
            ex_flag = True
            vid = bdm['id']
            LOG.error(_('Exception occurred in destroying '\
                        'block device mapping|%s|: %(ex)s') % locals())

    if ex_flag:
        raise exception.TerminateVolumeException()
