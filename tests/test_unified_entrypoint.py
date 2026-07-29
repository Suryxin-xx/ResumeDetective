import sys
import unittest
from unittest.mock import patch

import main


class UnifiedEntrypointTests(unittest.TestCase):
    def test_gateway_flag_dispatches_without_starting_desktop(self):
        with (
            patch.object(sys, "argv", ["ResumeDetective.exe", "--gateway", "--silent"]),
            patch.object(main, "_gateway_main", return_value=7) as gateway,
            patch.object(main, "_desktop_main") as desktop,
        ):
            self.assertEqual(main.main(), 7)
        gateway.assert_called_once_with()
        desktop.assert_not_called()

    def test_default_dispatches_to_desktop(self):
        with (
            patch.object(sys, "argv", ["ResumeDetective.exe"]),
            patch.object(main, "_gateway_main") as gateway,
            patch.object(main, "_desktop_main", return_value=0) as desktop,
        ):
            self.assertEqual(main.main(), 0)
        desktop.assert_called_once_with()
        gateway.assert_not_called()

    def test_gateway_entry_removes_only_dispatch_flag(self):
        with (
            patch.object(sys, "argv", ["ResumeDetective.exe", "--gateway", "--silent", "--port", "9876"]),
            patch("gateway_main.main", return_value=0) as gateway,
        ):
            self.assertEqual(main._gateway_main(), 0)
            self.assertEqual(sys.argv, ["ResumeDetective.exe", "--silent", "--port", "9876"])
        gateway.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
