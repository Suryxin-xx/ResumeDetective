import tempfile
import unittest
from pathlib import Path

from gateway_instance import GatewayInstance


class GatewayInstanceTests(unittest.TestCase):
    def test_only_one_instance_owns_a_data_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_dir = root / "portable-data"
            state_dir = root / "state"
            first = GatewayInstance(data_dir, state_dir)
            second = GatewayInstance(data_dir, state_dir)

            self.assertTrue(first.try_acquire())
            first.publish("http://127.0.0.1:18765")
            self.assertFalse(second.try_acquire())
            self.assertEqual(
                second.existing_url("http://127.0.0.1:8765", timeout=0),
                "http://127.0.0.1:18765",
            )

            first.release()
            self.assertTrue(second.try_acquire())
            second.release()

    def test_publish_rejects_non_local_addresses(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            instance = GatewayInstance(root / "data", root / "state")
            self.assertTrue(instance.try_acquire())
            try:
                with self.assertRaises(ValueError):
                    instance.publish("https://example.com")
            finally:
                instance.release()


if __name__ == "__main__":
    unittest.main()
