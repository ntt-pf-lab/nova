# vim: tabstop=4 shiftwidth=4 softtabstop=4

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
Tests For nova.scheduler.base_scheduler
"""

from nova import flags
from nova import test
from nova.scheduler import base_scheduler
from nova.scheduler import zone_manager
from nose.plugins.attrib import attr
from nose.plugins.skip import SkipTest

FLAGS = flags.FLAGS

class FakeBaseScheduler(base_scheduler.BaseScheduler):
    # No need to stub anything at the moment
    pass


class FakeZoneManager(zone_manager.ZoneManager):
    def __init__(self):
        self.service_states = {
            'host1': {
                'compute': {'host_memory_free': 1073741824},
            },
            'host2': {
                'compute': {'host_memory_free': 2147483648},
            },
            'host3': {
                'compute': {'host_memory_free': 3221225472},
            },
            'host4': {
                'compute': {'host_memory_free': 999999999},
            },
        }


class BaseSchedulerTestCase(test.TestCase):
    """Test for nova.scheduler.base_scheduler.BaseScheduler. """

    def setUp(self):
        super(BaseSchedulerTestCase, self).setUp()
        self.basescheduler = base_scheduler.BaseScheduler()

    @attr(kind='small')
    def test_filter_hosts(self):
        """Test for nova.scheduler.base_scheduler.BaseScheduler.filter_hosts. """
        topic = 'compute'
        request_spec = {}
        instance_type = dict(name='tiny',
                             memory_mb=50,
                             vcpus=10,
                             local_gb=500,
                             flavorid=1,
                             swap=500,
                             rxtx_quota=30000,
                             rxtx_cap=200,
                             extra_specs={})
        request_spec['instance_type'] = instance_type
        hosts = 'testhost'
        zm = FakeZoneManager()
        self.basescheduler.set_zone_manager(zm)
        ref = self.basescheduler.filter_hosts(topic, request_spec, hosts)
        hostlist = [(host, services)
                    for host, services in zm.service_states.iteritems()]
        self.assertEqual(hostlist, ref)

    @attr(kind='small')
    def test_filter_hosts_parameter_instance_type_is_none(self):
        """Test for nova.scheduler.base_scheduler.BaseScheduler.filter_hosts. """
        topic = 'compute'
        request_spec = {}
        hosts = 'testhost'
        ref = self.basescheduler.filter_hosts(topic, request_spec, hosts)
        self.assertEqual(hosts, ref)

    def test_weigh_hosts(self):
        """
        Try to weigh a short list of hosts and make sure enough
        entries for a larger number instances are returned.
        """

        sched = FakeBaseScheduler()

        # Fake out a list of hosts
        zm = FakeZoneManager()
        hostlist = [(host, services['compute'])
                    for host, services in zm.service_states.items()
                    if 'compute' in services]

        # Call weigh_hosts()
        num_instances = len(hostlist) * 2 + len(hostlist) / 2
        instlist = sched.weigh_hosts('compute',
                                     dict(num_instances=num_instances),
                                     hostlist)

        # Should be enough entries to cover all instances
        self.assertEqual(len(instlist), num_instances)

    @attr(kind='small')
    def test_weigh_hosts_parameter_num_instances_is_zero(self):
        """Test for nova.scheduler.base_scheduler.BaseScheduler.weigh_hosts. """
        topic = 'compute'
        request_spec = {}
        request_spec['num_instances'] = 0
        zm = FakeZoneManager()
        hosts = [(host, services['compute'])
                 for host, services in zm.service_states.items()
                 if 'compute' in services]
        
        instlist = self.basescheduler.weigh_hosts(topic, request_spec, hosts)
        self.assertEqual(0, len(instlist))

    @attr(kind='small')
    def test_weigh_hosts_parameter_hosts_is_empty(self):
        """Test for nova.scheduler.base_scheduler.BaseScheduler.weigh_hosts. """
        raise SkipTest("FIXME This test case goes into an infinite roop.")
        
        topic = 'compute'
        request_spec = {}
        request_spec['num_instances'] = 4
        hosts = []
        
        instlist = self.basescheduler.weigh_hosts(topic, request_spec, hosts)
        self.assertEqual(None, instlist)
