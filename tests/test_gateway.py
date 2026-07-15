import http.client
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import local_gateway


class GatewayHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        resume_dir = Path(self.temp_dir.name) / "data" / "Resumes"
        resume_dir.mkdir(parents=True)
        self.resume_file = resume_dir / "拼多多_产品管培生_中文简历.pdf"
        self.resume_bytes = b"%PDF-1.7\n" + bytes(range(256)) * 8
        self.resume_file.write_bytes(self.resume_bytes)

        self.patches = [
            patch.object(local_gateway.paths, "RESUMES_DIR", resume_dir),
            patch.object(
                local_gateway,
                "_find_application",
                return_value={"id": 12, "file_path": str(self.resume_file)},
            ),
            patch.object(local_gateway, "_recycle_application", return_value=True),
        ]
        for item in self.patches:
            item.start()

        self.server = local_gateway.ThreadingHTTPServer(
            (local_gateway.HOST, 0), local_gateway._Handler
        )
        local_gateway._server_port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def request(self, method, path, *, headers=None, body=None):
        connection = http.client.HTTPConnection(
            local_gateway.HOST, self.server.server_port, timeout=3
        )
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        payload = response.read()
        result = response.status, response.getheaders(), payload
        connection.close()
        return result

    def test_health_and_main_pages_are_reachable(self):
        status, _, payload = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertIn(b'"status":"ok"', payload)

        page_cases = (("/", "overview"), ("/board", "board"), ("/applications", "apps"))
        with patch.object(local_gateway, "_overview_page", return_value="overview"), \
             patch.object(local_gateway, "_board_page", return_value="board"), \
             patch.object(local_gateway, "_applications_page", return_value="apps"):
            for path, expected in page_cases:
                status, _, payload = self.request("GET", path)
                self.assertEqual(status, 200)
                self.assertEqual(payload.decode("utf-8"), expected)

    def test_chinese_resume_filename_has_one_valid_content_length(self):
        status, headers, payload = self.request("GET", "/resume/12")
        self.assertEqual(status, 200)
        self.assertEqual(payload, self.resume_bytes)
        self.assertEqual(
            len([value for key, value in headers if key.lower() == "content-length"]),
            1,
        )
        disposition = dict(headers)["Content-Disposition"]
        disposition.encode("ascii")
        self.assertIn("filename*=UTF-8''", disposition)

    def test_resume_head_and_range(self):
        status, headers, payload = self.request("HEAD", "/resume/12")
        self.assertEqual(status, 200)
        self.assertEqual(payload, b"")
        self.assertEqual(int(dict(headers)["Content-Length"]), len(self.resume_bytes))

        status, headers, payload = self.request(
            "GET", "/resume/12", headers={"Range": "bytes=10-109"}
        )
        self.assertEqual(status, 206)
        self.assertEqual(payload, self.resume_bytes[10:110])
        self.assertEqual(dict(headers)["Content-Range"], f"bytes 10-109/{len(self.resume_bytes)}")

    def test_invalid_range_and_missing_page_return_complete_errors(self):
        status, headers, payload = self.request(
            "GET", "/resume/12", headers={"Range": "bytes=99999-100000"}
        )
        self.assertEqual(status, 416)
        self.assertEqual(payload, b"")
        self.assertEqual(dict(headers)["Content-Length"], "0")

        status, headers, payload = self.request("GET", "/missing")
        self.assertEqual(status, 404)
        self.assertEqual(len(payload), int(dict(headers)["Content-Length"]))

    def test_untrusted_host_and_origin_are_rejected(self):
        connection = http.client.HTTPConnection(local_gateway.HOST, self.server.server_port, timeout=3)
        connection.putrequest("GET", "/health", skip_host=True)
        connection.putheader("Host", "attacker.invalid")
        connection.endheaders()
        response = connection.getresponse()
        self.assertEqual(response.status, 403)
        response.read()
        connection.close()

        status, _, _ = self.request(
            "POST",
            "/application/999/delete",
            headers={"Origin": "https://attacker.invalid", "Content-Length": "0"},
        )
        self.assertEqual(status, 403)

    def test_post_redirect_is_zero_length(self):
        status, headers, payload = self.request(
            "POST",
            "/application/999/delete",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=b"",
        )
        self.assertEqual(status, 303)
        self.assertEqual(payload, b"")
        self.assertEqual(dict(headers)["Content-Length"], "0")
        self.assertEqual(dict(headers)["Location"], "/applications")


if __name__ == "__main__":
    unittest.main()
