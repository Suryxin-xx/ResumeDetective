"""供本地浏览器 QA 使用的短生命周期网关进程。"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import local_gateway
import db_manager
import paths


if not paths.DATA_DIR.name.lower().startswith("resume-detective-qa-"):
    raise RuntimeError("QA server must use an isolated RESUME_DETECTIVE_DATA_DIR")
paths.ensure_data_directories()
db_manager.init_db()
if not db_manager.get_applications_with_resume():
    active_resume = db_manager.add_resume(
        "示例科技", "后端开发工程师", "",
        jd_text="负责高并发服务与数据平台建设。",
        application_source="官网",
        job_link="https://example.com/jobs/backend",
    )
    active_app = db_manager.add_application(
        active_resume,
        "业务面试",
        4,
        applied_at="2026-07-20",
        application_deadline="2026-08-05",
        next_action="准备系统设计面试",
        next_action_due_at="2026-07-30T19:30",
        last_follow_up_at="2026-07-27",
    )
    db_manager.update_resume_details(active_resume, city="上海")
    db_manager.add_interview(
        active_app,
        "一面",
        "2026-07-26 14:00",
        "项目追问较深入，整体节奏正常。",
        result="通过",
        questions="缓存一致性、索引优化、项目架构",
        weak_points="消息队列故障恢复回答不完整",
        follow_up="复习消息队列可靠性",
    )
    db_manager.add_job_task("整理项目指标", "2026-07-31", 3, notes="补充量化结果")

    archived_resume = db_manager.add_resume(
        "历史公司", "数据开发工程师", "",
        application_source="内推",
    )
    archived_app = db_manager.add_application(archived_resume, "已投递", 2)
    db_manager.update_application_status(archived_app, "简历初筛")
    db_manager.update_application_status(archived_app, "终止")
local_gateway.start_gateway(18765)
while True:
    time.sleep(1)
