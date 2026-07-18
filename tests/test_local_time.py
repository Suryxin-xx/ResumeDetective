import unittest
from datetime import datetime, timezone

import db_manager


class LocalTimeDisplayTests(unittest.TestCase):
    def test_sqlite_utc_timestamp_is_displayed_in_computer_local_time(self):
        value = "2026-07-18 15:30:00"
        expected = (
            datetime(2026, 7, 18, 15, 30, tzinfo=timezone.utc)
            .astimezone()
            .strftime("%Y-%m-%d %H:%M:%S")
        )
        self.assertEqual(db_manager.utc_timestamp_to_local(value), expected)

    def test_invalid_or_empty_timestamp_is_preserved_safely(self):
        self.assertEqual(db_manager.utc_timestamp_to_local(""), "")
        self.assertEqual(db_manager.utc_timestamp_to_local(None), "")
        self.assertEqual(db_manager.utc_timestamp_to_local("未知时间"), "未知时间")


if __name__ == "__main__":
    unittest.main()
