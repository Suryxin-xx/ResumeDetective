"""
detail_dialog.py — 投递详情弹窗
可编辑公司/岗位/城市/优先级/反馈/附件，自动保存
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QGroupBox, QMessageBox, QLineEdit, QSpinBox,
    QFileDialog, QListWidget, QListWidgetItem,
)
from PyQt6.QtCore import Qt, QTimer

import db_manager
import paths
import file_ops
from pathlib import Path

class JobDetailDialog(QDialog):
    """投递详情弹窗"""

    def __init__(self, app_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{app_data['company_name']} - {app_data['position_name']}")
        self.resize(540, 680)
        self.setMinimumWidth(420)

        self._app_id = app_data["id"]
        self._resume_id = app_data["resume_id"]
        self._deleted = False
        self._setup_ui(app_data)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._do_auto_save)
        self._save_field = None

        # 全部用统一延迟保存
        self.edit_company.textChanged.connect(lambda: self._defer("company"))
        self.edit_position.textChanged.connect(lambda: self._defer("position"))
        self.edit_city.textChanged.connect(lambda: self._defer("city"))
        self.edit_source.textChanged.connect(lambda: self._defer("application_source"))
        self.edit_job_link.textChanged.connect(lambda: self._defer("job_link"))
        self.edit_jd.textChanged.connect(lambda: self._defer("jd_text"))
        self.edit_feedback.textChanged.connect(lambda: self._defer("feedback"))
        self.edit_next.textChanged.connect(lambda: self._defer("next_action"))
        self.edit_priority.valueChanged.connect(lambda: self._defer("priority"))

        self._refresh_attachments()

    def _setup_ui(self, data):
        layout = QVBoxLayout(self)

        # ── 公司 + 岗位 ──
        row = QHBoxLayout()
        row.addWidget(QLabel("公司："))
        self.edit_company = QLineEdit(data["company_name"])
        row.addWidget(self.edit_company, stretch=1)
        row.addWidget(QLabel("岗位："))
        self.edit_position = QLineEdit(data["position_name"])
        row.addWidget(self.edit_position, stretch=1)
        row.addWidget(QLabel("优先级："))
        self.edit_priority = QSpinBox()
        self.edit_priority.setRange(0, 5)
        self.edit_priority.setValue(data.get("priority", 0))
        self.edit_priority.setFixedWidth(100)
        row.addWidget(self.edit_priority)
        layout.addLayout(row)

        # ── 城市 + 阶段 ──
        info_row = QHBoxLayout()
        info_row.addWidget(QLabel("城市："))
        self.edit_city = QLineEdit(data.get("city", ""))
        self.edit_city.setPlaceholderText("如：北京、上海")
        info_row.addWidget(self.edit_city, stretch=1)
        status = QLabel(f"阶段：{data['current_status']}")
        status.setStyleSheet("color:#555;margin-bottom:4px;")
        info_row.addWidget(status)
        layout.addLayout(info_row)

        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("投递来源："))
        self.edit_source = QLineEdit(data.get("application_source", ""))
        self.edit_source.setPlaceholderText("官网 / 内推 / 牛客 / 招聘群")
        source_row.addWidget(self.edit_source, stretch=1)
        source_row.addWidget(QLabel("岗位链接："))
        self.edit_job_link = QLineEdit(data.get("job_link", ""))
        self.edit_job_link.setPlaceholderText("https://...")
        source_row.addWidget(self.edit_job_link, stretch=2)
        layout.addLayout(source_row)

        # ── 简历 ──
        resume_row = QHBoxLayout()
        self.lbl_resume = QLabel(f"📄 {data.get('file_path') or '无简历'}")
        self.lbl_resume.setWordWrap(True)
        self.lbl_resume.setStyleSheet("color:#555;")
        resume_row.addWidget(self.lbl_resume, stretch=1)
        btn_resume = QPushButton("📎 更换简历")
        btn_resume.setFixedHeight(28)
        btn_resume.clicked.connect(self._on_change_resume)
        resume_row.addWidget(btn_resume)
        layout.addLayout(resume_row)

        # ── JD ──
        jdg = QGroupBox("JD")
        jdl = QVBoxLayout(jdg)
        self.edit_jd = QTextEdit()
        self.edit_jd.setMaximumHeight(110)
        self.edit_jd.setPlaceholderText("粘贴并保存 JD 原文，避免岗位关闭后内容丢失")
        self.edit_jd.setText(data.get("jd_text", ""))
        jdl.addWidget(self.edit_jd)
        layout.addWidget(jdg)

        # ── 反馈 ──
        fg = QGroupBox("面试反馈")
        fl = QVBoxLayout(fg)
        self.edit_feedback = QTextEdit()
        self.edit_feedback.setText(data.get("interview_feedback", ""))
        self.edit_feedback.setPlaceholderText("记录面试反馈...")
        self.edit_feedback.setMaximumHeight(80)
        fl.addWidget(self.edit_feedback)
        layout.addWidget(fg)

        # ── 下一步 ──
        ng = QGroupBox("下一步计划")
        nl = QVBoxLayout(ng)
        self.edit_next = QTextEdit()
        self.edit_next.setMaximumHeight(50)
        self.edit_next.setText(data.get("next_action", ""))
        self.edit_next.setPlaceholderText("如：准备系统设计面试...")
        nl.addWidget(self.edit_next)
        layout.addWidget(ng)

        # ── 附件 ──
        att_g = QGroupBox("附件")
        att_l = QVBoxLayout(att_g)

        self.att_list = QListWidget()
        self.att_list.setMinimumHeight(80)
        self.att_list.setMaximumHeight(120)
        self.att_list.itemDoubleClicked.connect(self._on_open_attachment)
        att_l.addWidget(self.att_list)

        att_btn_row = QHBoxLayout()
        btn_add_att = QPushButton("+ 添加附件")
        btn_add_att.setFixedHeight(28)
        btn_add_att.clicked.connect(self._on_add_attachment)
        att_btn_row.addWidget(btn_add_att)
        btn_open_folder = QPushButton("📂 打开文件夹")
        btn_open_folder.setFixedHeight(28)
        btn_open_folder.clicked.connect(self._on_open_attachment_folder)
        att_btn_row.addWidget(btn_open_folder)
        btn_del_att = QPushButton("🗑 移除选中")
        btn_del_att.setFixedHeight(28)
        btn_del_att.clicked.connect(self._on_delete_attachment)
        att_btn_row.addWidget(btn_del_att)
        att_btn_row.addStretch()
        att_l.addLayout(att_btn_row)
        layout.addWidget(att_g)

        # ── 底部按钮 ──
        btn_row = QHBoxLayout()
        btn_del = QPushButton("🗑 删除")
        btn_del.setStyleSheet("color:#C62828;")
        btn_del.clicked.connect(self._on_delete)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.setFixedWidth(100)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    # ── 自动保存 ──

    def _defer(self, field):
        self._save_field = field
        self._save_timer.start(600)

    def _do_auto_save(self):
        if self._save_field is None or self._app_id is None:
            return
        f = self._save_field
        try:
            if f == "company":
                db_manager.update_resume_details(self._resume_id, company_name=self.edit_company.text())
            elif f == "position":
                db_manager.update_resume_details(self._resume_id, position_name=self.edit_position.text())
            elif f == "city":
                db_manager.update_resume_details(self._resume_id, city=self.edit_city.text())
            elif f == "application_source":
                db_manager.update_resume_details(self._resume_id, application_source=self.edit_source.text())
            elif f == "job_link":
                db_manager.update_resume_details(self._resume_id, job_link=self.edit_job_link.text())
            elif f == "jd_text":
                db_manager.update_resume_details(self._resume_id, jd_text=self.edit_jd.toPlainText())
            elif f == "feedback":
                db_manager.update_application_details(self._app_id, interview_feedback=self.edit_feedback.toPlainText())
            elif f == "next_action":
                db_manager.update_application_details(self._app_id, next_action=self.edit_next.toPlainText())
            elif f == "priority":
                db_manager.update_application_details(self._app_id, priority=self.edit_priority.value())
        except Exception:
            pass
        self._save_field = None

    def _on_change_resume(self):
        from dialogs import AddResumeDialog
        p, _ = QFileDialog.getOpenFileName(self, "选择简历文件", "", "简历 (*.pdf *.docx *.doc *.jpg *.png)")
        if not p:
            return
        try:
            company = self.edit_company.text().strip() or "未命名公司"
            position = self.edit_position.text().strip() or "未命名岗位"
            rel_path = AddResumeDialog.copy_file_to_resumes(p, company, position)
            db_manager.update_resume_details(self._resume_id, file_path=rel_path)
            self.lbl_resume.setText(f"📄 {paths.RESUMES_DIR.joinpath(rel_path.split('/')[-1]).name}")
            QMessageBox.information(self, "完成", "简历已更新。")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"复制文件失败: {e}")

    # ── 附件管理 ──

    def _refresh_attachments(self):
        """刷新附件列表"""
        self.att_list.clear()
        if self._app_id is None:
            return
        atts = db_manager.get_attachments(self._app_id)
        for a in atts:
            name = a.get("display_name") or a.get("file_name", "(无文件名)")
            note = a.get("notes", "")
            text = name if not note else f"{name} — {note}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, a["id"])
            item.setData(Qt.ItemDataRole.ToolTipRole, a["file_path"])
            self.att_list.addItem(item)

    def _copy_to_attachments(self, src_path: str) -> str | None:
        """将文件复制到 data/Attachments/<application_id>/，返回相对路径"""
        if not self._app_id:
            return None
        att_dir = paths.ATTACHMENTS_DIR / str(self._app_id)
        att_dir.mkdir(parents=True, exist_ok=True)
        src = Path(src_path)
        if not src.exists():
            return None
        dest = att_dir / src.name
        # 重名自动加序号
        if dest.exists():
            stem = dest.stem
            suffix = dest.suffix
            i = 1
            while True:
                dest = att_dir / f"{stem}_{i}{suffix}"
                if not dest.exists():
                    break
                i += 1
        import shutil
        shutil.copy2(str(src), str(dest))
        return str(dest)

    def _on_add_attachment(self):
        if self._app_id is None:
            return
        p, _ = QFileDialog.getOpenFileName(
            self, "选择附件", "",
            "支持格式 (*.mp3 *.m4a *.wav *.png *.jpg *.jpeg *.pdf *.docx *.md *.txt *.xlsx);;所有文件 (*.*)")
        if not p:
            return
        dest_path = self._copy_to_attachments(p)
        if not dest_path:
            QMessageBox.warning(self, "错误", "复制文件失败")
            return
        src = Path(p)
        db_manager.add_attachment(
            application_id=self._app_id,
            file_name=src.name,
            file_path=dest_path,
            display_name=src.stem,
            file_type=src.suffix.lower(),
        )
        self._refresh_attachments()
        self.statusBar().showMessage(f"✅ 已添加附件：{src.name}", 3000)

    def statusBar(self):
        """向上查找主窗口状态栏"""
        parent = self.parent()
        while parent:
            if hasattr(parent, "statusBar"):
                return parent.statusBar()
            parent = parent.parent()
        class _Dummy:
            def showMessage(self, *a, **k): pass
        return _Dummy()

    def _on_open_attachment(self, item):
        fp = item.data(Qt.ItemDataRole.ToolTipRole)
        if fp and Path(fp).exists():
            import os
            os.startfile(fp)
        else:
            QMessageBox.information(self, "提示", "文件不存在，可能已被移动或删除。")

    def _on_open_attachment_folder(self):
        if not self._app_id:
            return
        folder = paths.ATTACHMENTS_DIR / str(self._app_id)
        if folder.exists():
            import os
            os.startfile(str(folder))
        else:
            QMessageBox.information(self, "提示", "该投递尚无附件。")

    def _on_delete_attachment(self):
        cur = self.att_list.currentItem()
        if not cur:
            QMessageBox.information(self, "提示", "请先选择要删除的附件。")
            return
        att_id = cur.data(Qt.ItemDataRole.UserRole)
        if not att_id:
            return
        if QMessageBox.question(self, "确认", "删除选中的附件？文件将移入回收站。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
            return
        file_path = db_manager.delete_attachment(att_id)
        if file_path:
            fp = Path(file_path)
            if fp.exists():
                ok, msg = file_ops.recycle_path(fp)
                if not ok:
                    print(f"[附件回收站] {msg}: {fp}")
        self._refresh_attachments()

    # ── 删除 ──

    def _on_delete(self):
        if QMessageBox.question(self, "确认删除",
                "删除这条投递记录吗？\n关联简历和附件文件会移入系统回收站。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
            return
        if self._save_timer.isActive():
            self._save_timer.stop()
        # 先删附件文件
        att_paths = db_manager.delete_attachments_by_application(self._app_id)
        for fp_str in att_paths:
            fp = Path(fp_str)
            if fp.exists():
                ok, msg = file_ops.recycle_path(fp)
                if not ok:
                    print(f"[附件回收站] {msg}: {fp}")
        db_manager.delete_resume(self._resume_id)
        self._deleted = True
        self._app_id = None
        self.accept()

    def was_deleted(self):
        return self._deleted
