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


class VconfigRollbackTest(unittest.TestCase):
    def setUp(self):
        from nova.exception import ProcessExecutionError
        import nova.network.linux_net as linux_net
        
        stb = stubout.StubOutForTesting()
        stb.Set(linux_net, "_device_exists",
                lambda *args, **kwargs: False)
       
        self.tracking = []
        def fake(*args, **kwargs):
            self.tracking.append((args, kwargs))
            if args[0] == "ip":
                raise ProcessExecutionError
        stb.Set(linux_net, "_execute", fake)
        self.stb = stb

    def tearDown(self):
        self.stb.UnsetAll()

    def test_remove_vlan_interface(self):
        """check remove vlan interface if error occurred."""
        from nova.exception import ProcessExecutionError
        import nova.network.linux_net as linux_net
        
        driver = linux_net.LinuxBridgeInterfaceDriver()
        vlan_num = 101
        bridge_interface = "eth0"
        self.assertRaises(ProcessExecutionError,
                          lambda: driver.ensure_vlan(vlan_num,
                                                     bridge_interface,
                                                     mac_address=None))

        vlan = "vlan101"
        for idx, args in enumerate((
                ("vconfig", "set_name_type", "VLAN_PLUS_VID_NO_PAD"),
                ("vconfig", "add", bridge_interface, vlan_num),
                ("ip", "link", "set", vlan, "up"),
                ("vconfig", "rem", vlan),
            )):
            self.assertEqual(self.tracking[idx][0], args)
            self.assertEqual(self.tracking[idx][1]["run_as_root"], True)


if __name__ == "__main__":
    unittest.main()
