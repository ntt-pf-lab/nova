#-*- coding: utf-8 -*
import unittest
import stubout
from itertools import count


class IptablesManagerRollbackTest(unittest.TestCase):
    def test_settings_length(self):
        """check IptablesManager's default settings length."""
        import nova.network.linux_net as linux_net
        import nova.network.iptables_helper as helper
        
        mngr = linux_net.IptablesManager()
        settings = helper.make_settings(mngr.ipv4, mngr.ipv6, True)
        self.assertEqual(len(settings), 3)

    def test_rollback_called_count(self):
        """check rollback called."""
        from nova.exception import ProcessExecutionError
        import nova.network.linux_net as linux_net
        import nova.network.iptables_helper as helper

        cnt = count(1)
        stop = 3
        def fake(cmd_name, *args, **kwargs):
            """Raise Error at last element."""
            if cmd_name.endswith("-save") and next(cnt) == stop:
                raise ProcessExecutionError
            return "", ""
        mngr = linux_net.IptablesManager(fake)

        stb = stubout.StubOutForTesting()
        cnt = count()
        stb.Set(helper.IptableCommand, "rollback", lambda *args, **kwargs: next(cnt))
        try:
            mngr.apply()
        except ProcessExecutionError:
            self.assertEqual(next(cnt), stop)


if __name__ == "__main__":
    unittest.main()
