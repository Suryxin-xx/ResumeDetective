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

        page_cases = (("/", "overview"), ("/board", "board"), ("/applications", "apps"), ("/interviews", "interviews"), ("/resumes", "resumes"))
        with patch.object(local_gateway, "_overview_page", return_value="overview"), \
             patch.object(local_gateway, "_board_page", return_value="board"), \
             patch.object(local_gateway, "_applications_page", return_value="apps"), \
             patch.object(local_gateway, "_interviews_page", return_value="interviews"), \
             patch.object(local_gateway, "_resumes_page", return_value="resumes"):
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

    def test_interview_post_returns_to_interview_workspace(self):
        with patch.object(local_gateway.db_manager, "add_interview") as add_interview:
            body = b"application_id=12&round=%E4%B8%80%E9%9D%A2&summary=ok"
            status, headers, payload = self.request(
                "POST", "/interview",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                body=body,
            )
        self.assertEqual(status, 303)
        self.assertEqual(payload, b"")
        self.assertEqual(dict(headers)["Location"], "/interviews")
        add_interview.assert_called_once()

    def test_terminated_application_can_be_reopened(self):
        with patch.object(local_gateway.db_manager, "update_application_status") as update_status:
            status, headers, payload = self.request(
                "POST", "/application/12/reopen",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                body=b"",
            )
        self.assertEqual(status, 303)
        self.assertEqual(payload, b"")
        self.assertEqual(dict(headers)["Location"], "/applications")
        update_status.assert_called_once_with(12, "已投递")


class GatewayPageTests(unittest.TestCase):
    def setUp(self):
        self.apps = [
            {"id": 1, "resume_id": 11, "company_name": "进行中公司", "position_name": "后端工程师", "current_status": "业务面试", "city": "上海", "application_source": "官网", "next_action": "准备二面", "status_update_time": "2026-07-18 09:30:00", "file_path": "", "priority": 2, "job_link": "", "jd_text": "Python", "upload_time": "2026-07-10"},
            {"id": 2, "resume_id": 12, "company_name": "归档公司", "position_name": "算法工程师", "current_status": "终止", "city": "北京", "application_source": "内推", "next_action": "", "status_update_time": "2026-07-17 18:20:00", "file_path": "", "priority": 0, "job_link": "", "jd_text": "", "upload_time": "2026-07-11"},
        ]

    def test_overview_focuses_on_actions_not_interview_form(self):
        with patch.object(local_gateway.db_manager, "get_applications_with_resume", return_value=self.apps), \
             patch.object(local_gateway.db_manager, "get_job_tasks", return_value=[]):
            page = local_gateway._overview_page(8765)
        self.assertIn("快速进入工作区", page)
        self.assertNotIn("新增面试复盘", page)

    def test_board_has_bounded_lanes_table_and_status_time(self):
        with patch.object(local_gateway.db_manager, "get_applications_with_resume", return_value=self.apps):
            page = local_gateway._board_page(8765)
        self.assertIn('class="lane-body"', page)
        self.assertIn('id="tableView"', page)
        self.assertIn('id="boardArchive"', page)
        self.assertIn('id="toggleTerminated"', page)
        self.assertIn('class="archived-row hidden"', page)
        self.assertIn("已终止岗位 · 1", page)
        self.assertIn("状态更新时间", page)
        self.assertIn("2026-07-18 09:30", page)

    def test_application_management_is_compact_and_archives_terminated_jobs(self):
        with patch.object(local_gateway.db_manager, "get_applications_with_resume", return_value=self.apps), \
             patch.object(local_gateway, "_safe_resume_path", return_value=None):
            page = local_gateway._applications_page(8765)
        self.assertIn('id="editor-1"', page)
        self.assertNotIn('id="editor-2"', page)
        self.assertIn("已终止岗位 · 1", page)
        self.assertIn('/application/2/reopen', page)
        self.assertIn("状态更新时间", page)

    def test_resume_workspace_reports_missing_bindings(self):
        with patch.object(local_gateway.db_manager, "get_applications_with_resume", return_value=self.apps), \
             patch.object(local_gateway, "_safe_resume_path", return_value=None):
            page = local_gateway._resumes_page(8765)
        self.assertIn("关联简历汇总", page)
        self.assertIn("当前待绑定 / 缺失", page)
        self.assertIn('id="resumeArchive"', page)
        self.assertIn("历史关联简历 · 1", page)
        self.assertIn('/applications#app-1', page)
        self.assertNotIn('/applications#app-2', page)

    def test_interviews_are_grouped_by_application_and_keep_history(self):
        interviews = [
            {"application_id": 1, "company_name": "进行中公司", "position_name": "后端工程师", "round": "二面", "interview_time": "2026-07-18 10:00", "summary": "系统设计"},
            {"application_id": 1, "company_name": "进行中公司", "position_name": "后端工程师", "round": "一面", "interview_time": "2026-07-17 10:00", "summary": "项目追问"},
            {"application_id": 2, "company_name": "归档公司", "position_name": "算法工程师", "round": "一面", "interview_time": "2026-07-16 10:00", "summary": "动态规划"},
        ]
        with patch.object(local_gateway.db_manager, "get_applications_with_resume", return_value=self.apps), \
             patch.object(local_gateway.db_manager, "get_interviews", return_value=interviews):
            page = local_gateway._interviews_page(8765)
        self.assertEqual(page.count('class="review-group"'), 2)
        self.assertIn("2 个岗位 · 3 轮面试", page)
        self.assertIn("进行中公司 · 后端工程师", page)
        self.assertIn("归档公司 · 算法工程师", page)
        self.assertIn("2 轮", page)


if __name__ == "__main__":
    unittest.main()
