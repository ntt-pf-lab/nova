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
import unittest
import stubout
from itertools import count


class IptablesManagerConfigureTest(unittest.TestCase):
    def test_settings_length(self):
        """check IptablesManager's default settings length."""
        import nova.network.linux_net as linux_net
        import nova.network.iptables_helper as helper
        
        mngr = linux_net.IptablesManager()
        settings = helper.make_settings(mngr.ipv4, mngr.ipv6, True)
        self.assertEqual(len(settings), 3)

class IptablesManagerRollbackTest(unittest.TestCase):
    def setUp(self):
        from nova.exception import ProcessExecutionError
        import nova.network.iptables_helper as helper
        
        ##########################
        # step1 : create fake
        ##########################
        self.cnt = count(1)
        def fake(cmd_name, *args, **kwargs):
            """Raise Error at last element."""
            if cmd_name.endswith("-save") and next(self.cnt) == 3:
                raise ProcessExecutionError
            return "", ""
        self.fake_executable = fake

        ##########################
        # step2 : stub out
        ##########################
        self.stb = stubout.StubOutForTesting()
        self.rollbacks = count()
        self.stb.Set(helper.IptableCommand, "rollback",
                     lambda *args, **kwargs: next(self.rollbacks))

    def tearDown(self):
        self.stb.UnsetAll()

    def test_rollback_called_count(self):
        """check rollback called."""
        from nova.exception import ProcessExecutionError
        import nova.network.linux_net as linux_net

        mngr = linux_net.IptablesManager(self.fake_executable)
        try:
            mngr.apply()
        except ProcessExecutionError:
            self.assertEqual(next(self.rollbacks), 2)


if __name__ == "__main__":
    unittest.main()
