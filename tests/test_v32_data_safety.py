import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import data_safety
import db_manager
import config_manager


class V32DataAndBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data_dir = self.root / "ResumeDetective-LocalData"
        self.data_dir.mkdir()
        self.db_file = self.data_dir / "data.db"
        self.backup_root = self.root / "ResumeDetective-LocalData-Backups"
        self.patches = [
            patch.object(db_manager, "DB_FILE", self.db_file),
            patch.object(db_manager, "DATA_DIR", self.data_dir),
            patch.object(db_manager, "_sync_excel_mirror"),
            patch.object(data_safety.paths, "DATA_DIR", self.data_dir),
            patch.object(data_safety.paths, "DB_FILE", self.db_file),
            patch.object(
                data_safety.paths,
                "ensure_data_directories",
                side_effect=lambda: self.data_dir.mkdir(parents=True, exist_ok=True),
            ),
            patch.object(data_safety, "BACKUP_ROOT", self.backup_root),
        ]
        for item in self.patches:
            item.start()
        db_manager.init_db()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_workspace_branding_cannot_be_overridden_by_personal_config(self):
        config_file = self.data_dir / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "workspace_title": "我的秋招台",
                    "developer_name": "自定义名字",
                    "contact_email": "custom@example.com",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        with patch.object(config_manager, "CONFIG_FILE", config_file):
            preferences = config_manager.get_workspace_preferences()
            config_manager.set_workspace_preferences(
                "新标题", "仍想覆盖", "override@example.com"
            )
            saved = json.loads(config_file.read_text(encoding="utf-8"))

        self.assertEqual(preferences["title"], "我的秋招台")
        self.assertEqual(preferences["developer_name"], "Suryxin-xx")
        self.assertEqual(preferences["contact_email"], "Finlandxxu@outlook.com")
        self.assertEqual(
            preferences["project_url"],
            "https://github.com/Suryxin-xx/ResumeDetective",
        )
        self.assertEqual(saved["workspace_title"], "新标题")
        self.assertEqual(saved["developer_name"], "自定义名字")
        self.assertEqual(saved["contact_email"], "custom@example.com")

    def test_schema_dates_generated_task_and_interview_fields(self):
        resume_id = db_manager.add_resume("测试公司", "后端开发", "")
        app_id = db_manager.add_application(
            resume_id,
            applied_at="2026-07-28",
            application_deadline="2026-08-01",
            next_action="准备一面",
            next_action_due_at="2026-07-30T19:30",
            last_follow_up_at="2026-07-29",
        )
        app = next(item for item in db_manager.get_applications_with_resume() if item["id"] == app_id)
        self.assertEqual(app["applied_at"], "2026-07-28")
        self.assertEqual(app["application_deadline"], "2026-08-01")
        self.assertEqual(app["next_action_due_at"], "2026-07-30T19:30")

        generated = [
            item for item in db_manager.get_job_tasks("open")
            if item.get("source") == "application_next_action"
        ]
        self.assertEqual(len(generated), 1)
        self.assertIn("准备一面", generated[0]["title"])

        interview_id = db_manager.add_interview(
            app_id,
            "一面",
            "2026-07-31 14:00",
            "整体顺利",
            result="通过",
            questions="缓存一致性",
            weak_points="追问不够完整",
            follow_up="复习消息队列",
        )
        interview = next(item for item in db_manager.get_interviews() if item["id"] == interview_id)
        self.assertEqual(interview["result"], "通过")
        self.assertEqual(interview["follow_up"], "复习消息队列")

    def test_backup_is_verified_and_restore_keeps_a_safety_copy(self):
        resume_id = db_manager.add_resume("备份公司", "测试岗位", "")
        db_manager.add_application(resume_id)
        note = self.data_dir / "notes.txt"
        note.write_text("before", encoding="utf-8")

        backup = data_safety.create_backup("unit-test")
        manifest = json.loads((backup / "backup-manifest.json").read_text(encoding="utf-8"))
        self.assertIn("data.db", manifest["files"])
        self.assertTrue(data_safety.database_health(backup / "data.db")["ok"])

        note.write_text("after", encoding="utf-8")
        connection = sqlite3.connect(self.db_file)
        try:
            connection.execute("DELETE FROM applications")
            connection.commit()
        finally:
            connection.close()
        safety_copy = data_safety.restore_backup(backup)

        self.assertEqual(note.read_text(encoding="utf-8"), "before")
        self.assertTrue(safety_copy.is_dir())
        connection = sqlite3.connect(self.db_file)
        try:
            count = connection.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 1)

    def test_stage_state_category_tags_and_scheduled_backup(self):
        resume_id = db_manager.add_resume(
            "分类公司", "供应链岗位", "", job_category="供应链", tags="国企, 重点"
        )
        app_id = db_manager.add_application(
            resume_id, "测评", stage_state="待处理"
        )
        app = next(item for item in db_manager.get_applications_with_resume() if item["id"] == app_id)
        self.assertEqual(app["stage_state"], "待处理")
        self.assertEqual(app["job_category"], "供应链")
        self.assertEqual(app["tags"], "国企, 重点")

        with patch.object(
            config_manager,
            "get_backup_preferences",
            return_value={
                "enabled": True,
                "interval_days": 7,
                "last_backup_at": "",
            },
        ), patch.object(config_manager, "mark_automatic_backup_completed") as mark:
            backup = data_safety.maybe_create_automatic_backup()
        self.assertTrue(backup.is_dir())
        mark.assert_called_once()


if __name__ == "__main__":
    unittest.main()
