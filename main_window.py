"""
主窗口 — 4 面板：投递看板 / 资料库 / AI 助手 / 工具
"""

import html
import re
import sys, os
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QSplitter, QListWidget,
    QListWidgetItem, QFileDialog, QMessageBox, QApplication, QComboBox,
    QGroupBox, QLineEdit, QFormLayout, QSpinBox, QDialogButtonBox,
    QAbstractItemView,
    QDialog, QScrollBar, QScrollArea, QGridLayout,
)
from PyQt6.QtCore import QByteArray, Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QAction, QTextCursor

import db_manager
import config_manager
import cli_ai
import ai_service
import paths
import local_gateway
import chat_history as ch
from board_widget import BoardWidget
from table_view import TableView
from detail_dialog import JobDetailDialog
from materials_widget import MaterialsWidget
from job_targets_widget import JobTargetsWidget
from tasks_widget import TasksWidget

STATUS_COLORS = {
    "已投递": "#BBDEFB", "简历初筛": "#FFE0B2", "笔试/无笔试": "#E1BEE7",
    "业务面试": "#C8E6C9", "HR面": "#B2EBF2", "Offer": "#FFCDD2", "终止": "#CFD8DC",
}
STATUS_LIST = ["已投递", "简历初筛", "笔试/无笔试", "业务面试", "HR面", "Offer", "终止"]


class MainWindow(QMainWindow):
    """简历侦探主窗口"""

    _ai_signal = pyqtSignal(bool, str, str)  # 跨线程 AI 响应 (ok, reply, model)
    _ai_chunk_signal = pyqtSignal(str, bool)  # 流式 AI 块 (text, is_finished)
    _pdf_done_signal = pyqtSignal(bool, str)  # PDF→图片完成 (success, msg)
    _imgpdf_done_signal = pyqtSignal(bool, str, object)  # 文档→图片版PDF完成 (success, msg, btn)
    _balance_signal = pyqtSignal(object)  # DeepSeek 余额
    _reasonix_upgrade_signal = pyqtSignal(bool, str)  # Reasonix 升级结果

    def __init__(self):
        super().__init__()
        self.setWindowTitle("简历侦探 Resume Detective")
        self.resize(1280, 780)
        self.setMinimumSize(960, 640)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.statusBar().setSizeGripEnabled(True)

        # 全局字体放大
        font = QFont("Microsoft YaHei", 10)
        self.setFont(font)

        self._cur_chat = None
        self._selected_app_id = None
        self._selected_jt_context = None  # 来自意向公司的 JD 上下文
        self._selected_ai_app_ids = set()
        self._selected_ai_jt_ids = set()
        self._chat_messages = []
        self._api_models_cache = []
        self._auto_scroll = True  # AI 聊天区是否自动跟随到底部
        self._stream_message_index = None
        self._ai_stream_cursor = None
        self._open_detail = None  # 保存详情弹窗引用防 GC
        self._cli_busy = False
        self._ai_signal.connect(self._ai_done)
        self._ai_chunk_signal.connect(self._on_ai_chunk)
        self._pdf_done_signal.connect(self._pdf2img_done)
        self._imgpdf_done_signal.connect(self._imgpdf_done)
        self._balance_signal.connect(self._on_balance_updated)
        self._reasonix_upgrade_signal.connect(self._on_upgrade_reasonix_done)

        # 旧版 API Key 迁移（明文 config.json -> 加密存储）
        migrated = config_manager.migrate_api_key_from_legacy()
        if migrated:
            self.statusBar().showMessage("🔒 API Key 已迁移到加密存储", 3000)

        # ── 中控 Tab ──
        self.tabs = QTabWidget()
        self.tabs.tabBar().setMovable(True)
        self.tabs.tabBar().tabMoved.connect(self._save_current_tab_order)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

        self._init_board_page()
        self._init_tasks_page()
        self._init_materials_page()
        self._init_ai_page()
        self._init_job_targets_page()
        self._init_tools_page()

        self._tab_defs = [
            ("board", self.page_board, "📋 投递看板"),
            ("tasks", self.page_tasks, "✓ 行动清单"),
            ("materials", self.page_materials, "📚 资料库"),
            ("ai", self.page_ai, "🤖 AI 助手"),
            ("targets", self.page_job_targets, "🎯 意向公司"),
            ("tools", self.page_tools, "🔧 工具"),
        ]
        self._restore_tab_order()
        self._apply_apple_style()
        self._restore_window_geometry()

        self.statusBar().showMessage("就绪", 3000)

    # ── Tab 切换 ──

    def _on_tab_changed(self, idx):
        current = self.tabs.widget(idx)
        page_board = getattr(self, "page_board", None)
        page_materials = getattr(self, "page_materials", None)
        page_tasks = getattr(self, "page_tasks", None)
        page_job_targets = getattr(self, "page_job_targets", None)
        page_ai = getattr(self, "page_ai", None)

        if current is page_board and hasattr(self, 'board_widget'):
            self.board_widget.refresh()
            self._refresh_ai_context_picker()
        elif current is page_materials and hasattr(self, 'materials_widget'):
            self.materials_widget.refresh()
        elif current is page_tasks and hasattr(self, 'tasks_widget'):
            self.tasks_widget.refresh()
        elif current is page_job_targets and hasattr(self, 'job_targets_widget'):
            self.job_targets_widget.refresh()
            self._refresh_ai_context_picker()
        elif current is page_ai:
            self._refresh_ai_context_picker()

    def _restore_tab_order(self):
        saved = config_manager.get_tab_order()
        widget_by_key = {key: widget for key, widget, _ in self._tab_defs}
        title_by_key = {key: title for key, _, title in self._tab_defs}
        ordered = [key for key in saved if key in widget_by_key]
        for key, _, _ in self._tab_defs:
            if key not in ordered:
                ordered.append(key)

        while self.tabs.count():
            self.tabs.removeTab(0)
        for key in ordered:
            self.tabs.addTab(widget_by_key[key], title_by_key[key])

    def _tab_key_for_widget(self, widget):
        for key, page, _ in self._tab_defs:
            if page is widget:
                return key
        return None

    def _save_current_tab_order(self, *_):
        order = []
        for idx in range(self.tabs.count()):
            key = self._tab_key_for_widget(self.tabs.widget(idx))
            if key:
                order.append(key)
        if order:
            config_manager.set_tab_order(order)

    def _reset_tab_order(self):
        config_manager.set_tab_order([key for key, _, _ in self._tab_defs])
        self._restore_tab_order()
        self.statusBar().showMessage("已恢复默认工具栏顺序", 3000)

    def _restore_window_geometry(self):
        """Restore a previous size without ever preventing the user from resizing the window."""
        geometry = config_manager.get_window_geometry()
        if not geometry:
            return
        try:
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
        except Exception:
            # A stale layout record should never block application startup.
            pass

    def closeEvent(self, event):
        try:
            geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
            config_manager.set_window_geometry(geometry)
        except Exception:
            pass
        super().closeEvent(event)

    def _apply_apple_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #f5f5f7;
                color: #1d1d1f;
            }
            QTabWidget {
                background: transparent;
            }
            QTabWidget::pane {
                border: 1px solid #d8d8de;
                border-radius: 18px;
                background: #fbfbfd;
                top: -1px;
            }
            QTabBar::tab {
                background: #ececf1;
                color: #3a3a40;
                border: 1px solid #d8d8de;
                border-bottom: none;
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
                padding: 8px 15px;
                margin-right: 6px;
                min-width: 96px;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #111111;
            }
            QGroupBox {
                border: 1px solid #d8d8de;
                border-radius: 16px;
                margin-top: 12px;
                padding-top: 12px;
                background: #ffffff;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid #d6d6db;
                border-radius: 12px;
                padding: 0 12px;
                min-height: 30px;
            }
            QPushButton:hover {
                background: #f0f3f6;
            }
            QPushButton:pressed {
                background: #e7ebf0;
            }
            QPushButton[class="primary"] {
                background: #0071e3;
                color: #ffffff;
                border-color: #0071e3;
                font-weight: 700;
            }
            QPushButton[class="primary"]:hover {
                background: #0077ed;
            }
            QPushButton[class="destructive"] {
                color: #b42318;
            }
            QLineEdit, QTextEdit, QComboBox, QListWidget, QTableWidget {
                background: #ffffff;
                border: 1px solid #d8d8de;
                border-radius: 14px;
                padding: 4px 10px;
            }
            QLineEdit, QComboBox {
                min-height: 32px;
            }
            QComboBox {
                padding-right: 26px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border: none;
                background: transparent;
            }
            QTextEdit {
                padding: 8px 10px;
            }
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QListWidget:focus, QTableWidget:focus {
                border: 2px solid #0071e3;
            }
            QListWidget::item:selected, QTableWidget::item:selected {
                background: #dfeaf7;
                color: #1d1d1f;
            }
            QTableWidget {
                gridline-color: #ececf1;
                alternate-background-color: #f8f8fa;
            }
            QHeaderView::section {
                background: #f5f5f7;
                color: #6e6e73;
                border: none;
                border-bottom: 1px solid #d8d8de;
                padding: 9px 8px;
                font-weight: 700;
            }
            QSplitter::handle {
                background: #e5e5ea;
                margin: 5px 1px;
            }
            QSplitter::handle:hover {
                background: #c7c7cc;
            }
            QLabel#pageTitle {
                color: #1d1d1f;
                font-size: 22px;
                font-weight: 700;
                background: transparent;
            }
            QLabel#pageSubtitle {
                color: #6e6e73;
                font-size: 12px;
                background: transparent;
            }
            QLabel#taskSummary {
                color: #355c7d;
                background: #eef4ff;
                border: 1px solid #d6e2f5;
                border-radius: 12px;
                padding: 8px 12px;
                font-weight: 700;
            }
            QScrollBar#chatScrollBar::groove:vertical {
                width: 8px;
                background: #e5e7eb;
                border-radius: 4px;
                margin: 4px 5px;
            }
            QScrollBar#chatScrollBar::handle:vertical {
                min-height: 52px;
                width: 18px;
                margin: 0 -4px;
                background: #8aa9c8;
                border: 1px solid #6d90b4;
                border-radius: 9px;
            }
            QScrollBar#chatScrollBar::handle:vertical:hover {
                background: #5f8fbe;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 12px;
                margin: 4px 2px 4px 2px;
            }
            QScrollBar::handle:vertical {
                background: #c7ccd6;
                min-height: 36px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover {
                background: #aeb6c3;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                background: #eef1f5;
                border: 1px solid #d8d8de;
                height: 14px;
                border-radius: 6px;
            }
            QStatusBar {
                background: #f5f5f7;
            }
        """)

    # ── 投递看板页 ──

    def _init_board_page(self):
        self.page_board = QWidget()
        self.tabs.addTab(self.page_board, "投递看板")
        layout = QVBoxLayout(self.page_board)
        layout.setContentsMargins(8, 8, 8, 8)

        # 顶部工具栏
        toolbar = QHBoxLayout()
        btn_add = QPushButton("✚ 新增投递")
        btn_add.setFixedHeight(36)
        btn_add.setStyleSheet("font-weight:bold;font-size:13px;padding:4px 16px;")
        btn_add.clicked.connect(self._on_add)
        toolbar.addWidget(btn_add)
        btn_refresh = QPushButton("🔄 刷新")
        btn_refresh.setFixedHeight(36)
        btn_refresh.clicked.connect(self._on_safe_refresh)
        toolbar.addWidget(btn_refresh)
        btn_import = QPushButton("📥 导入")
        btn_import.setFixedHeight(36)
        btn_import.clicked.connect(self._on_import_xlsx)
        toolbar.addWidget(btn_import)
        btn_export = QPushButton("📤 导出")
        btn_export.setFixedHeight(36)
        btn_export.clicked.connect(self._on_export_xlsx)
        toolbar.addWidget(btn_export)
        btn_tpl = QPushButton("📄 模板")
        btn_tpl.setFixedHeight(36)
        btn_tpl.clicked.connect(self._on_export_template)
        toolbar.addWidget(btn_tpl)
        # 模式切换
        self._board_mode = "board"
        self.btn_mode = QPushButton("📋 表格模式")
        self.btn_mode.setFixedHeight(36)
        self.btn_mode.clicked.connect(self._toggle_mode)
        toolbar.addWidget(self.btn_mode)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.stack_board = QWidget()
        self.stack_layout = QVBoxLayout(self.stack_board)
        self.stack_layout.setContentsMargins(0, 0, 0, 0)

        self.board_widget = BoardWidget()
        self.table_view = TableView()
        self.table_view.card_selected.connect(self._on_card_double_click)
        self.board_widget.card_selected.connect(self._on_card_double_click)
        self.board_widget.card_focused.connect(self._update_ai_context)

        self._cur_mode = "board"
        self.stack_layout.addWidget(self.board_widget)
        self.stack_layout.addWidget(self.table_view)
        self.table_view.hide()
        layout.addWidget(self.stack_board, stretch=1)

    def _toggle_mode(self):
        if self._cur_mode == "board":
            self._cur_mode = "table"
            self.board_widget.hide()
            self.table_view.refresh()
            self.table_view.show()
            self.btn_mode.setText("📋 泳道模式")
        else:
            self._cur_mode = "board"
            self.table_view.hide()
            self.board_widget.refresh()
            self.board_widget.show()
            self.btn_mode.setText("📋 表格模式")

    def _on_add(self):
        from dialogs import AddResumeDialog
        d = AddResumeDialog(self)
        if d.exec() == QDialog.DialogCode.Accepted:
            data = d.get_result()
            if data:
                file_path = AddResumeDialog.copy_file_to_resumes(
                    data["source_file"], data["company_name"], data["position_name"])
                rid = db_manager.add_resume(
                    data["company_name"], data["position_name"], file_path,
                    jd_text=data["jd_text"], version_note=data.get("version_note", ""),
                    application_source=data.get("application_source", ""),
                    job_link=data.get("job_link", ""),
                )
                if rid:
                    db_manager.add_application(rid)
                self.board_widget.refresh()
                self._refresh_ai_context_picker()

    def _on_safe_refresh(self):
        try:
            self.board_widget.refresh()
            self._refresh_ai_context_picker()
        except Exception as e:
            print("refresh error:", e)

    def _on_export_template(self):
        from io_export import generate_template
        from pathlib import Path
        p = Path.cwd() / "data" / "导入模板.xlsx"
        generate_template(str(p))
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "模板已生成", f"请查看：{p}")

    def _on_import_xlsx(self):
        from io_export import import_xlsx
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        p, _ = QFileDialog.getOpenFileName(self, "选择导入文件", "", "Excel (*.xlsx)")
        if not p:
            return
        try:
            n = import_xlsx(p)
            self._on_safe_refresh()
            QMessageBox.information(self, "导入完成", f"成功导入 {n} 条记录")
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))

    def _on_export_xlsx(self):
        from io_export import export_xlsx
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        p, _ = QFileDialog.getSaveFileName(self, "导出投递数据", "投递数据.xlsx", "Excel (*.xlsx)")
        if not p:
            return
        try:
            n = export_xlsx(p)
            QMessageBox.information(self, "导出完成", f"已导出 {n} 条记录")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    # ── 详情 ──


    def _on_card_double_click(self, app_id):
        if app_id is None:
            return
        apps = db_manager.get_applications_with_resume()
        ad = next((a for a in apps if a["id"] == app_id), None)
        if ad is None:
            return
        d = JobDetailDialog(ad, self)
        d.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        d.finished.connect(lambda *_: self._on_safe_refresh())
        d.show()
        d.raise_()
        d.activateWindow()
        self._open_detail = d

    def _update_ai_context(self, app_id):
        self._selected_app_id = app_id
        self._selected_jt_context = None
        self._update_ai_context_label()

    def _on_jt_send_to_ai(self, company, position, jd_text):
        self._selected_app_id = None
        self._selected_jt_context = {
            "company_name": company,
            "position_name": position,
            "jd_text": jd_text,
        }
        self._update_ai_context_label()
        self.tabs.setCurrentWidget(self.page_ai)

    def _selected_context_keys(self):
        return {("app", app_id) for app_id in self._selected_ai_app_ids} | {("jt", jt_id) for jt_id in self._selected_ai_jt_ids}

    def _refresh_ai_context_picker(self):
        if not hasattr(self, "ai_context_list"):
            return
        selected_keys = self._selected_context_keys()
        keyword = self.ai_context_filter.text().strip().lower() if hasattr(self, "ai_context_filter") else ""
        self.ai_context_list.setVisible(bool(keyword) or bool(selected_keys))
        self.ai_context_list.blockSignals(True)
        self.ai_context_list.clear()

        for app in db_manager.get_applications_with_resume():
            haystack = " ".join([
                app.get("company_name", ""),
                app.get("position_name", ""),
                app.get("city", ""),
                app.get("current_status", ""),
                app.get("jd_text", ""),
            ]).lower()
            if keyword and keyword not in haystack:
                continue
            if not keyword and ("app", app["id"]) not in selected_keys:
                continue
            label = f"[投递] {app.get('company_name','')} - {app.get('position_name','')}"
            extras = [x for x in [app.get("current_status", ""), app.get("city", "")] if x]
            if extras:
                label += " | " + " / ".join(extras)
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, ("app", app["id"]))
            item.setToolTip(app.get("jd_text", "") or label)
            self.ai_context_list.addItem(item)
            if ("app", app["id"]) in selected_keys:
                item.setSelected(True)

        for target in db_manager.get_job_targets_filtered():
            haystack = " ".join([
                target.get("company_name", ""),
                target.get("position_name", ""),
                target.get("city", ""),
                target.get("status", ""),
                target.get("jd_text", ""),
            ]).lower()
            if keyword and keyword not in haystack:
                continue
            if not keyword and ("jt", target["id"]) not in selected_keys:
                continue
            label = f"[意向] {target.get('company_name','')} - {target.get('position_name','')}"
            extras = [x for x in [target.get("status", ""), target.get("city", "")] if x]
            if extras:
                label += " | " + " / ".join(extras)
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, ("jt", target["id"]))
            item.setToolTip(target.get("jd_text", "") or label)
            self.ai_context_list.addItem(item)
            if ("jt", target["id"]) in selected_keys:
                item.setSelected(True)

        self.ai_context_list.blockSignals(False)
        self._sync_selected_ai_context_from_list()
        self._update_ai_context_label()

    def _sync_selected_ai_context_from_list(self):
        app_ids, jt_ids = set(), set()
        for item in getattr(self, "ai_context_list", QListWidget()).selectedItems():
            data = item.data(Qt.ItemDataRole.UserRole)
            if not data:
                continue
            source, row_id = data
            if source == "app":
                app_ids.add(row_id)
            elif source == "jt":
                jt_ids.add(row_id)
        self._selected_ai_app_ids = app_ids
        self._selected_ai_jt_ids = jt_ids

    def _on_ai_context_selection_changed(self):
        self._sync_selected_ai_context_from_list()
        self._update_ai_context_label()

    def _clear_ai_context_selection(self):
        if hasattr(self, "ai_context_list"):
            self.ai_context_list.clearSelection()
        self._selected_ai_app_ids.clear()
        self._selected_ai_jt_ids.clear()
        self._refresh_ai_context_picker()
        self._update_ai_context_label()

    def _get_manual_ai_context_entries(self):
        entries = []
        app_map = {a["id"]: a for a in db_manager.get_applications_with_resume()}
        target_map = {t["id"]: t for t in db_manager.get_job_targets_filtered()}
        for app_id in self._selected_ai_app_ids:
            app = app_map.get(app_id)
            if app:
                entries.append({"source": "投递", "company_name": app.get("company_name", ""), "position_name": app.get("position_name", ""), "city": app.get("city", ""), "status": app.get("current_status", ""), "jd_text": app.get("jd_text", "")})
        for jt_id in self._selected_ai_jt_ids:
            jt = target_map.get(jt_id)
            if jt:
                entries.append({"source": "意向", "company_name": jt.get("company_name", ""), "position_name": jt.get("position_name", ""), "city": jt.get("city", ""), "status": jt.get("status", ""), "jd_text": jt.get("jd_text", "")})
        return entries

    def _update_ai_context_label(self):
        manual_entries = self._get_manual_ai_context_entries()
        if manual_entries:
            app_count = sum(1 for item in manual_entries if item["source"] == "投递")
            jt_count = sum(1 for item in manual_entries if item["source"] == "意向")
            parts = []
            if app_count:
                parts.append(f"{app_count} 个投递")
            if jt_count:
                parts.append(f"{jt_count} 个意向 JD")
            self.ai_ctx.setText("📎 已手动选中：" + " / ".join(parts))
            return
        if self._selected_jt_context:
            self.ai_ctx.setText(f"🎯 当前意向：{self._selected_jt_context.get('company_name','')} - {self._selected_jt_context.get('position_name','')}")
            return
        if self._selected_app_id is None:
            self.ai_ctx.setText("📌 未选中卡片（可自由提问）")
            return
        apps = db_manager.get_applications_with_resume()
        ad = next((a for a in apps if a["id"] == self._selected_app_id), None)
        if ad:
            self.ai_ctx.setText(f"📌 当前投递：{ad['company_name']} - {ad['position_name']}")
        else:
            self.ai_ctx.setText("📌 未选中卡片（可自由提问）")

    # ── 行动清单页 ──

    def _init_tasks_page(self):
        self.page_tasks = QWidget()
        layout = QVBoxLayout(self.page_tasks)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tasks_widget = TasksWidget()
        self.tasks_widget.data_changed.connect(self._on_safe_refresh)
        layout.addWidget(self.tasks_widget)

    def _init_materials_page(self):
        self.page_materials = QWidget()
        self.tabs.addTab(self.page_materials, "资料库")
        layout = QVBoxLayout(self.page_materials)
        self.materials_widget = MaterialsWidget()
        layout.addWidget(self.materials_widget)

    # ── AI 页面 ──


    def _init_ai_page(self):
        self.page_ai = QWidget()
        self.tabs.addTab(self.page_ai, "AI 助手")
        layout = QVBoxLayout(self.page_ai)
        layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 4, 0)

        self.ai_ctx = QLabel("📌 未选中卡片（可自由提问）")
        self.ai_ctx.setStyleSheet("background:#eef4ff;border:1px solid #d6e2f5;padding:10px 12px;border-radius:14px;font-size:12px;color:#355c7d;")
        lv.addWidget(self.ai_ctx)

        self.ai_chat = QTextEdit()
        self.ai_chat.setReadOnly(True)
        self.ai_chat.setFont(QFont("Microsoft YaHei UI", 11))
        self.ai_chat.setPlaceholderText("AI 回复将显示在这里...")
        self.ai_chat.setMinimumHeight(200)
        self.ai_chat.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.ai_chat.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.ai_chat.setStyleSheet("font-size:14px;padding:10px;background:#f7f8fa;border:1px solid #d8d8de;border-radius:18px;")
        chat_row = QHBoxLayout()
        chat_row.setSpacing(6)
        chat_row.addWidget(self.ai_chat, stretch=1)
        self.ai_scroll_slider = QScrollBar(Qt.Orientation.Vertical)
        self.ai_scroll_slider.setObjectName("chatScrollBar")
        self.ai_scroll_slider.setFixedWidth(18)
        self.ai_scroll_slider.setToolTip("拖动滑块阅读长回复")
        self.ai_scroll_slider.setEnabled(False)
        chat_bar = self.ai_chat.verticalScrollBar()
        chat_bar.rangeChanged.connect(self._sync_ai_scroll_slider_range)
        chat_bar.valueChanged.connect(self.ai_scroll_slider.setValue)
        self.ai_scroll_slider.valueChanged.connect(chat_bar.setValue)
        chat_row.addWidget(self.ai_scroll_slider)
        lv.addLayout(chat_row, stretch=1)

        self.ai_input = QTextEdit()
        self.ai_input.setFont(QFont("Microsoft YaHei UI", 11))
        self.ai_input.setPlaceholderText("输入问题...（Ctrl+Enter 发送）")
        self.ai_input.setMaximumHeight(120)
        self.ai_input.setMinimumHeight(50)
        self.ai_input.setStyleSheet("font-size:13px;padding:8px;background:#ffffff;border:1px solid #cfd5df;border-radius:14px;")
        self.ai_input.installEventFilter(self)
        self.ai_chat.verticalScrollBar().valueChanged.connect(self._on_chat_scroll)
        lv.addWidget(self.ai_input)

        biz_row = QHBoxLayout()
        self.btn_jd_analysis = QPushButton("📊 JD 分析")
        self.btn_jd_analysis.setFixedHeight(32)
        self.btn_jd_analysis.setToolTip("分析当前选中岗位的 JD 要求")
        self.btn_jd_analysis.clicked.connect(lambda: self._on_ai_biz("jd_analysis"))
        biz_row.addWidget(self.btn_jd_analysis)
        self.btn_gen_resume = QPushButton("📝 生成简历")
        self.btn_gen_resume.setFixedHeight(32)
        self.btn_gen_resume.setToolTip("基于 JD + 个人信息 + 经历生成简历初稿")
        self.btn_gen_resume.clicked.connect(lambda: self._on_ai_biz("gen_resume"))
        biz_row.addWidget(self.btn_gen_resume)
        self.btn_rewrite = QPushButton("✍ 重写经历")
        self.btn_rewrite.setFixedHeight(32)
        self.btn_rewrite.setToolTip("重写项目经历，使其更匹配目标岗位")
        self.btn_rewrite.clicked.connect(lambda: self._on_ai_biz("rewrite"))
        biz_row.addWidget(self.btn_rewrite)
        self.btn_match = QPushButton("🎯 匹配分析")
        self.btn_match.setFixedHeight(32)
        self.btn_match.setToolTip("分析当前 JD 与个人资料的匹配度和补强方向")
        self.btn_match.clicked.connect(lambda: self._on_ai_biz("match_analysis"))
        biz_row.addWidget(self.btn_match)
        self.btn_self_intro = QPushButton("🎤 自我介绍")
        self.btn_self_intro.setFixedHeight(32)
        self.btn_self_intro.setToolTip("生成面试自我介绍稿")
        self.btn_self_intro.clicked.connect(lambda: self._on_ai_biz("self_intro"))
        biz_row.addWidget(self.btn_self_intro)
        biz_row.addStretch()
        lv.addLayout(biz_row)

        biz_row2 = QHBoxLayout()
        self.btn_interview = QPushButton("面试训练")
        self.btn_interview.setFixedHeight(32)
        self.btn_interview.setToolTip("基于当前 JD 和个人经历生成结构化面试题")
        self.btn_interview.clicked.connect(lambda: self._on_ai_biz("interview_training"))
        biz_row2.addWidget(self.btn_interview)
        self.btn_compare = QPushButton("岗位对比")
        self.btn_compare.setFixedHeight(32)
        self.btn_compare.setToolTip("比较多个已选岗位的匹配度、风险和准备成本")
        self.btn_compare.clicked.connect(lambda: self._on_ai_biz("job_compare"))
        biz_row2.addWidget(self.btn_compare)
        biz_row2.addStretch()
        lv.addLayout(biz_row2)

        inp_btn = QHBoxLayout()
        self.btn_ai_send = QPushButton("📤 发送")
        self.btn_ai_send.setFixedHeight(34)
        self.btn_ai_send.setStyleSheet("font-weight:bold;font-size:13px;")
        self.btn_ai_send.clicked.connect(self._on_ai_send)
        inp_btn.addStretch()
        inp_btn.addWidget(self.btn_ai_send)
        lv.addLayout(inp_btn)
        splitter.addWidget(left)

        right_content = QWidget()
        rv = QVBoxLayout(right_content)
        rv.setContentsMargins(4, 0, 0, 0)
        rv.setSpacing(6)

        grp_ctx = QGroupBox("📎 会话上下文")
        gcv = QVBoxLayout(grp_ctx)
        self.ai_context_hint = QLabel("可直接在这里勾选投递卡片和意向 JD，不必先切到别的页面。")
        self.ai_context_hint.setWordWrap(True)
        self.ai_context_hint.setStyleSheet("color:#6e6e73;font-size:12px;padding:0 2px;")
        gcv.addWidget(self.ai_context_hint)
        self.ai_context_filter = QLineEdit()
        self.ai_context_filter.setPlaceholderText("搜索公司 / 岗位 / 城市 / JD")
        self.ai_context_filter.textChanged.connect(self._refresh_ai_context_picker)
        gcv.addWidget(self.ai_context_filter)
        self.ai_context_list = QListWidget()
        self.ai_context_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.ai_context_list.setMinimumHeight(0)
        self.ai_context_list.setMaximumHeight(132)
        self.ai_context_list.itemSelectionChanged.connect(self._on_ai_context_selection_changed)
        gcv.addWidget(self.ai_context_list)
        ctx_btns = QHBoxLayout()
        btn_ctx_refresh = QPushButton("刷新上下文")
        btn_ctx_refresh.setFixedHeight(32)
        btn_ctx_refresh.clicked.connect(self._refresh_ai_context_picker)
        ctx_btns.addWidget(btn_ctx_refresh)
        btn_ctx_clear = QPushButton("清空选择")
        btn_ctx_clear.setFixedHeight(32)
        btn_ctx_clear.clicked.connect(self._clear_ai_context_selection)
        ctx_btns.addWidget(btn_ctx_clear)
        gcv.addLayout(ctx_btns)
        rv.addWidget(grp_ctx)

        grp_his = QGroupBox("📜 历史对话")
        ghv = QVBoxLayout(grp_his)
        self.history_list = QListWidget()
        self.history_list.setMinimumHeight(180)
        self.history_list.currentItemChanged.connect(self._on_history_selected)
        ghv.addWidget(self.history_list)

        his_btns = QHBoxLayout()
        btn_new = QPushButton("✚ 新对话")
        btn_new.setFixedHeight(32)
        btn_new.clicked.connect(self._new_chat)
        his_btns.addWidget(btn_new)
        btn_rename = QPushButton("✏ 重命名")
        btn_rename.setFixedHeight(32)
        btn_rename.clicked.connect(self._on_rename_chat)
        his_btns.addWidget(btn_rename)
        btn_del = QPushButton("🗑")
        btn_del.setFixedHeight(32)
        btn_del.setToolTip("删除当前对话")
        btn_del.clicked.connect(self._on_del_chat)
        his_btns.addWidget(btn_del)
        btn_export = QPushButton("📤 MD")
        btn_export.setFixedHeight(32)
        btn_export.setToolTip("导出为 Markdown")
        btn_export.clicked.connect(self._on_export_chat)
        his_btns.addWidget(btn_export)
        ghv.addLayout(his_btns)
        rv.addWidget(grp_his)

        grp_api = QGroupBox("🔑 API 设置")
        gav = QFormLayout(grp_api)
        self.ai_channel = QComboBox()
        self.ai_channel.addItem("API 直连（推荐）", "api")
        self.ai_channel.addItem("Reasonix CLI（可选）", "reasonix")
        self.ai_channel.currentIndexChanged.connect(self._on_channel_changed)
        gav.addRow("通道：", self.ai_channel)
        self.cli_status = QLabel("")
        self.cli_status.setStyleSheet("color:#888;font-size:11px;padding:2px 0;")
        gav.addRow("", self.cli_status)

        cli_btn_row = QHBoxLayout()
        self.btn_cli_init = QPushButton("🧩 初始化配置")
        self.btn_cli_init.setFixedHeight(32)
        self.btn_cli_init.clicked.connect(self._on_init_reasonix)
        cli_btn_row.addWidget(self.btn_cli_init)
        self.btn_cli_upgrade = QPushButton("⬆ 升级内核")
        self.btn_cli_upgrade.setFixedHeight(32)
        self.btn_cli_upgrade.clicked.connect(self._on_upgrade_reasonix)
        cli_btn_row.addWidget(self.btn_cli_upgrade)
        self.btn_cli_help = QPushButton("❓ 安装说明")
        self.btn_cli_help.setFixedHeight(32)
        self.btn_cli_help.clicked.connect(self._on_cli_help)
        cli_btn_row.addWidget(self.btn_cli_help)
        gav.addRow("", cli_btn_row)
        self.cli_status.hide(); self.btn_cli_init.hide(); self.btn_cli_upgrade.hide(); self.btn_cli_help.hide()

        self.ai_model = QComboBox()
        self.ai_model.setEditable(False)
        self._populate_models(fetch_remote=False)
        model_row = QHBoxLayout()
        model_row.addWidget(self.ai_model, stretch=1)
        btn_refresh_models = QPushButton("刷新模型")
        btn_refresh_models.setFixedHeight(32)
        btn_refresh_models.clicked.connect(self._on_refresh_models)
        model_row.addWidget(btn_refresh_models)
        gav.addRow("模型：", model_row)

        self.btn_ai_key = QPushButton("设置 API Key")
        self.btn_ai_key.clicked.connect(self._on_set_api_key)
        gav.addRow("", self.btn_ai_key)

        bal_row = QHBoxLayout()
        self.ai_balance = QLabel("余额：--")
        self.ai_balance.setStyleSheet("color:#888;")
        bal_row.addWidget(self.ai_balance)
        btn_refresh_bal = QPushButton("刷新")
        btn_refresh_bal.setFixedHeight(32)
        btn_refresh_bal.setToolTip("刷新余额")
        btn_refresh_bal.clicked.connect(self._update_balance)
        bal_row.addWidget(btn_refresh_bal)
        gav.addRow("", bal_row)
        rv.addWidget(grp_api)

        rv.addStretch()
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setWidget(right_content)
        splitter.addWidget(right_scroll)
        splitter.setSizes([760, 340])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, stretch=1)

        self._load_last_chat()
        self._refresh_ai_context_picker()
        self._update_balance()
        self._bal_timer = QTimer(self)
        self._bal_timer.timeout.connect(self._update_balance)
        self._bal_timer.start(600_000)

    def _populate_models(self, show_message=False, fetch_remote=False):
        self.ai_model.clear()
        channel = self.ai_channel.currentData() or "api"
        if channel == "reasonix":
            reasonix_info = cli_ai.get_local_provider_choices()
            default_model = reasonix_info.get("default_model", "")
            provider_choices = reasonix_info.get("providers", [])
            if not default_model and not provider_choices:
                self.ai_model.addItem("请先初始化 Reasonix 配置", "")
                self.ai_model.setEnabled(False)
                if show_message:
                    self.statusBar().showMessage("请先点击「初始化配置」生成本地 Reasonix 配置", 4000)
                return
            default_label = default_model or "Reasonix 当前默认配置"
            self.ai_model.addItem(f"使用默认配置（{default_label}）", "")
            for display, model_ref in provider_choices:
                self.ai_model.addItem(display, model_ref)
            self.ai_model.setEnabled(True)
            self.ai_model.setCurrentIndex(0)
            if show_message:
                count = max(self.ai_model.count() - 1, 0)
                self.statusBar().showMessage(
                    f"已加载 {count} 个 Reasonix 可选模型，可直接使用默认配置",
                    4000,
                )
            return
        api_key = config_manager.get_api_key()
        if not api_key:
            self.ai_model.addItem("请先设置 API Key", "")
            self.ai_model.setEnabled(False)
            if show_message:
                QMessageBox.information(self, "模型列表", "请先设置 API Key，再刷新模型列表。")
            return

        models = self._api_models_cache
        if fetch_remote:
            models = cli_ai.get_available_models(api_key)
            if models:
                self._api_models_cache = models
            else:
                self.ai_model.addItem("模型获取失败，请检查 Key/网络", "")
                self.ai_model.setEnabled(False)
                if show_message:
                    QMessageBox.warning(self, "模型列表", "未能从 API 获取模型列表，请检查 API Key 或网络。")
                return

        if not models:
            self.ai_model.addItem("点击“刷新模型”加载可用模型", "")
            self.ai_model.setEnabled(False)
            if show_message:
                self.statusBar().showMessage("尚未加载 API 模型列表", 3000)
            return

        self.ai_model.setEnabled(True)
        for display, key in models:
            self.ai_model.addItem(display, key)
        self.ai_model.setCurrentIndex(0)
        if show_message:
            self.statusBar().showMessage(f"已加载 {len(models)} 个模型", 3000)

    def eventFilter(self, obj, event):
        if obj is self.ai_input and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Return and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self._on_ai_send()
                return True
        return super().eventFilter(obj, event)

    def _on_refresh_models(self):
        """按当前通道刷新模型列表。API 通道才会请求远端，CLI 仅重读本地配置。"""
        is_api = (self.ai_channel.currentData() or "api") == "api"
        self._populate_models(show_message=True, fetch_remote=is_api)

    def _on_set_api_key(self):
        from PyQt6.QtWidgets import QInputDialog, QMessageBox
        if config_manager.has_api_key():
            # 已有 Key：仅允许替换，不显示旧 Key
            ret = QMessageBox.question(
                self, "替换 API Key",
                "API Key 已设置。\n\n是否要替换为新的 Key？\n（当前 Key 不会被显示，替换后旧 Key 立即失效）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if ret != QMessageBox.StandardButton.Yes:
                return
            key, ok = QInputDialog.getText(self, "替换 API Key",
                "请输入新的 DeepSeek API Key：",
                QLineEdit.EchoMode.Password,
            )
            if ok and key.strip():
                config_manager.set_api_key(key.strip())
                cli_ai.sync_local_reasonix_env(key.strip())
                self._populate_models(fetch_remote=False)
                self.statusBar().showMessage("✅ API Key 已替换", 3000)
        else:
            # 首次设置
            key, ok = QInputDialog.getText(self, "设置 API Key",
                "请输入你的 DeepSeek API Key：",
                QLineEdit.EchoMode.Password)
            if ok and key.strip():
                config_manager.set_api_key(key.strip())
                cli_ai.sync_local_reasonix_env(key.strip())
                self._populate_models(fetch_remote=False)
                self.statusBar().showMessage("✅ API Key 已保存", 3000)

    # ── CLI 通道控制 ──

    def _on_channel_changed(self, idx):
        """通道切换时：显示/隐藏 CLI 控件，更新状态"""
        channel = self.ai_channel.itemData(idx)
        is_cli = (channel == "reasonix")
        self.cli_status.setVisible(is_cli)
        self.btn_cli_init.setVisible(is_cli)
        self.btn_cli_upgrade.setVisible(is_cli)
        self.btn_cli_help.setVisible(is_cli)
        if is_cli:
            if cli_ai.find_reasonix():
                cli_ai.ensure_local_reasonix_config(api_key=config_manager.get_api_key() or None)
            self._update_cli_status()
        self._populate_models(fetch_remote=False)

    def _update_cli_status(self):
        """检测 CLI 并更新状态标签（短文案 + tooltip）"""
        status = cli_ai.get_reasonix_status()
        reasonix_info = cli_ai.get_local_provider_choices()
        provider_count = len(reasonix_info.get("providers", []))
        default_model = reasonix_info.get("default_model", "")
        if status.get("found"):
            suffix = f" | 已加载 {provider_count} 个模型" if provider_count else ""
            self.cli_status.setText(f"✅ 已检测到 CLI：reasonix.exe{suffix}")
            tip = [str(status.get("path") or "")]
            if status.get("version"):
                tip.append(f"版本：{status['version']}")
            if default_model:
                tip.append(f"默认配置：{default_model}")
            if provider_count:
                tip.append("可选模型：" + " / ".join(p[0] for p in reasonix_info["providers"]))
            if not status.get("config_exists"):
                tip.append("尚未初始化本地 config.toml")
            self.cli_status.setToolTip("\n".join(tip))
            self.cli_status.setStyleSheet("color:#2E7D32;font-size:11px;padding:2px 0;")
        else:
            self.cli_status.setText("⚠️ 未检测到应用内 CLI")
            self.cli_status.setToolTip("请将 reasonix.exe 放入项目的 Reasonix Cli/ 目录。")
            self.cli_status.setStyleSheet("color:#C62828;font-size:11px;padding:2px 0;")

    def _selected_reasonix_provider(self):
        """返回当前选中的 Reasonix provider；空字符串表示使用默认配置。"""
        if (self.ai_channel.currentData() or "api") != "reasonix":
            return ""
        return (self.ai_model.currentData() or "").strip()

    def _assistant_header(self, channel, model_id):
        if channel == "reasonix":
            if model_id:
                return f"AI ({html.escape(model_id)} / Reasonix)"
            return "AI (Reasonix 默认配置)"
        return f"AI ({html.escape(model_id)} / API)"

    def _resolve_reasonix_executable(self):
        """使用用户自行安装并明确配置的 Reasonix CLI。"""
        return cli_ai.find_reasonix()

    def _on_init_reasonix(self):
        """在外置个人数据目录初始化 Reasonix 配置和 .env。"""
        api_key = config_manager.get_api_key()
        ok = cli_ai.ensure_local_reasonix_config(api_key=api_key or None)
        if ok:
            self._update_cli_status()
            self._populate_models(show_message=True, fetch_remote=False)
            self.statusBar().showMessage("✅ 已初始化 Reasonix 本地配置", 4000)
        else:
            QMessageBox.warning(self, "初始化失败", "未能生成 Reasonix 配置，请检查个人数据目录的写入权限。")


    def _on_upgrade_reasonix(self):
        if self._cli_busy:
            return
        self._cli_busy = True
        self.btn_cli_upgrade.setEnabled(False)
        self.btn_cli_upgrade.setText("⏳ 升级中...")
        import threading
        def worker():
            ok, output = cli_ai.upgrade_reasonix()
            self._reasonix_upgrade_signal.emit(ok, output or "")
        threading.Thread(target=worker, daemon=True).start()

    def _on_upgrade_reasonix_done(self, ok, output):
        self._cli_busy = False
        if hasattr(self, "btn_cli_upgrade"):
            self.btn_cli_upgrade.setEnabled(True)
            self.btn_cli_upgrade.setText("⬆ 升级内核")
        self._update_cli_status()
        if ok:
            QMessageBox.information(self, "升级完成", output or "升级成功")
        else:
            QMessageBox.warning(self, "升级失败", output or "升级失败")

    def _on_cli_help(self):
        """显示 Reasonix 安装说明"""
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Reasonix CLI 安装说明",
            "Reasonix CLI 是可选的 AI 增强通道。\n\n"
            "安装方式：\n"
            "1. 下载官方 Windows 版 reasonix\n"
            "2. 解压到项目下的 Reasonix Cli/ 目录\n"
            "3. 回到 AI 页点击「初始化配置」\n"
            "4. 如已设置 API Key，程序会同步写入本地 Reasonix .env\n\n"
            "当前项目只认应用目录内的 CLI，不会再扫描桌面、PATH 或 AppData。")

    # ── AI 发送 ──

    def _on_ai_send(self):
        text = self.ai_input.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "提示", "请输入问题。")
            return

        channel = self.ai_channel.currentData() or "api"
        api_key = config_manager.get_api_key()

        if channel == "reasonix":
            model_id = self._selected_reasonix_provider()
        else:
            model_id = self.ai_model.currentData()
            if not model_id:
                QMessageBox.information(self, "请选择模型", "请先设置 API Key，并点击\u201c刷新模型\u201d获取可用模型。")
                return
            if not api_key:
                QMessageBox.information(self, "设置 API Key", "请先设置 API Key。")
                return

        self.ai_input.clear()

        if self._cur_chat:
            ch.add_message(self._cur_chat, "user", text)
        self._append_chat_message("user", text)
        self.btn_ai_send.setEnabled(False)
        self.btn_ai_send.setText("\u23f3 生成中...")

        system_prompt, prompt = self._build_ai_prompt(text)
        self._current_reply = ""
        self._start_ai_reply(model_id, channel)

        import threading
        def worker(m=model_id, p=prompt, sp=system_prompt, chn=channel):
            if chn == "reasonix":
                cli_exe = self._resolve_reasonix_executable()
                if not cli_exe:
                    self._ai_chunk_signal.emit("未找到 Reasonix CLI。请从上游项目自行下载，并放入 Reasonix Cli/ 目录。", True)
                    return
                cli_ai.sync_local_reasonix_env(api_key or None)
                merged_prompt = f"{sp}\n\n{p}" if sp else p
                ok, reply = cli_ai.call_reasonix_blocking(merged_prompt, model=m, cli_path=str(cli_exe))
                self._ai_chunk_signal.emit(reply if ok else f"Reasonix 调用失败：{reply}", True)
                return
            for chunk, is_last in cli_ai.call_deepseek_api_stream(
                p, model=m, api_key=api_key, system_prompt=sp
            ):
                self._ai_chunk_signal.emit(chunk, is_last)
        threading.Thread(target=worker, daemon=True).start()


    def _collect_active_context_entries(self):
        manual_entries = self._get_manual_ai_context_entries()
        if manual_entries:
            return manual_entries
        if self._selected_jt_context:
            return [{"source": "target", "company_name": self._selected_jt_context.get("company_name", ""), "position_name": self._selected_jt_context.get("position_name", ""), "city": "", "status": "", "jd_text": self._selected_jt_context.get("jd_text", "") }]
        if self._selected_app_id is None:
            return []
        apps = db_manager.get_applications_with_resume()
        ad = next((a for a in apps if a["id"] == self._selected_app_id), None)
        if not ad:
            return []
        return [{"source": "application", "company_name": ad.get("company_name", ""), "position_name": ad.get("position_name", ""), "city": ad.get("city", ""), "status": ad.get("current_status", ""), "jd_text": ad.get("jd_text", "") }]

    def _build_ai_prompt(self, user_text):
        entries = self._collect_active_context_entries()
        if not entries:
            return "", user_text
        materials = db_manager.search_materials(user_text)
        if len(entries) == 1:
            item = entries[0]
            return ai_service.build_prompt(item.get("company_name", ""), item.get("position_name", ""), item.get("status", ""), item.get("jd_text", ""), materials, user_text)

        system_prompt = "You are a job application assistant. Answer strictly from the selected application cards, target JDs, and resume materials. Do not invent experience."
        sections = ["[Selected Contexts]"]
        for idx, item in enumerate(entries, start=1):
            sections.append(f"### {idx}. [{item.get('source','context')}] {item.get('company_name','')} - {item.get('position_name','')}")
            if item.get("city"):
                sections.append(f"City: {item['city']}")
            if item.get("status"):
                sections.append(f"Status: {item['status']}")
            if item.get("jd_text"):
                sections.append("JD:\n" + item["jd_text"])
            sections.append("")
        if materials:
            sections.append("[Related Materials]")
            for m in materials:
                sections.append(f"- [{m.get('material_type','experience')}] {m.get('title','')}: {m.get('content','')}")
            sections.append("")
        sections.append("[User Question]\n" + user_text)
        return system_prompt, "\n".join(sections)

    def _on_ai_biz(self, action):
        channel = self.ai_channel.currentData() or "api"
        api_key = config_manager.get_api_key()
        if channel == "reasonix":
            model_id = self._selected_reasonix_provider()
        else:
            model_id = self.ai_model.currentData()
            if not model_id:
                QMessageBox.information(self, "请选择模型", "请先设置 API Key，并点击“刷新模型”获取可用模型。")
                return
            if not api_key:
                QMessageBox.information(self, "设置 API Key", "请先设置 API Key。")
                return

        profile = db_manager.get_profile() if hasattr(db_manager, "get_profile") else None
        materials = db_manager.get_all_materials() if hasattr(db_manager, "get_all_materials") else []
        entries = self._collect_active_context_entries()
        jd_parts, seen = [], set()
        for item in entries:
            jd_text = (item.get("jd_text", "") or "").strip()
            if jd_text and jd_text not in seen:
                seen.add(jd_text)
                jd_parts.append(jd_text)
        jd_text = "\n\n---\n\n".join(jd_parts)

        if action == "jd_analysis":
            if not jd_text:
                QMessageBox.information(self, "缺少 JD", "当前没有可分析的 JD，请先选择投递卡片或意向公司 JD。")
                return
            _, prompt = ai_service.build_jd_analysis_prompt(jd_text)
        elif action == "match_analysis":
            if not jd_text:
                QMessageBox.information(self, "缺少 JD", "当前没有可分析的 JD，请先选择投递卡片或意向公司 JD。")
                return
            _, prompt = ai_service.build_match_analysis_prompt(jd_text, profile, materials)
        elif action == "gen_resume":
            _, prompt = ai_service.build_resume_draft_prompt(jd_text, profile, materials)
        elif action == "rewrite":
            from PyQt6.QtWidgets import QInputDialog
            titles = [m.get("title", "(???)") for m in materials]
            if not titles:
                QMessageBox.information(self, "缺少资料", "资料库里还没有可重写的经历内容，请先补充资料库。")
                return
            item, ok = QInputDialog.getItem(self, "选择经历", "请选择要重写的经历：", titles, 0, False)
            if not ok:
                return
            selected = next((m for m in materials if m.get("title", "(???)") == item), None)
            if not selected:
                return
            _, prompt = ai_service.build_project_rewrite_prompt(selected, jd_text)
        elif action == "self_intro":
            _, prompt = ai_service.build_self_intro_prompt(profile, materials, jd_text)
        elif action == "interview_training":
            if not jd_text:
                QMessageBox.information(self, "缺少 JD", "请先在上下文搜索框中选择至少一个带 JD 的岗位。")
                return
            _, prompt = ai_service.build_interview_training_prompt(jd_text, profile, materials)
        elif action == "job_compare":
            if len(entries) < 2:
                QMessageBox.information(self, "需要多个岗位", "请在上下文搜索框中至少选择两个投递或意向岗位。")
                return
            _, prompt = ai_service.build_job_compare_prompt(entries, profile)
        else:
            return

        self.ai_input.setText(prompt)
        self.statusBar().showMessage("已生成草稿，请补充或修改后按 Ctrl+Enter 发送。", 5000)
        self.ai_input.setFocus()

    def _on_ai_chunk(self, text, is_last):
        if text:
            self._current_reply += text
            if self._stream_message_index is not None:
                self._chat_messages[self._stream_message_index]["content"] = self._current_reply
                self._render_chat_messages()
        if is_last:
            self.btn_ai_send.setEnabled(True)
            self.btn_ai_send.setText("📤 发送")
            if self._stream_message_index is not None:
                self._chat_messages[self._stream_message_index]["streaming"] = False
                self._render_chat_messages()
            self._stream_message_index = None
            self._ai_stream_cursor = None
            if self._cur_chat and self._current_reply:
                ch.add_message(self._cur_chat, "assistant", self._current_reply)
            self._update_balance()

    def _on_chat_scroll(self, value):
        """监听聊天区滚动位置：用户在底部时跟随，上滑时暂停自动跟随。"""
        sb = self.ai_chat.verticalScrollBar()
        at_bottom = (sb.maximum() - value) < 20
        self._auto_scroll = at_bottom

    def _sync_ai_scroll_slider_range(self, minimum, maximum):
        """Keep the visible drag slider in lockstep with the hidden QTextEdit scrollbar."""
        self.ai_scroll_slider.blockSignals(True)
        self.ai_scroll_slider.setRange(minimum, maximum)
        self.ai_scroll_slider.setPageStep(self.ai_chat.verticalScrollBar().pageStep())
        self.ai_scroll_slider.setValue(self.ai_chat.verticalScrollBar().value())
        self.ai_scroll_slider.setEnabled(maximum > minimum)
        self.ai_scroll_slider.blockSignals(False)


    def _render_chat_messages(self):
        old_scroll = self.ai_chat.verticalScrollBar().value()
        old_max = max(self.ai_chat.verticalScrollBar().maximum(), 1)
        blocks = [self._message_to_html(msg) for msg in self._chat_messages]
        self.ai_chat.setHtml("<div style='font-family:Microsoft YaHei UI,Microsoft YaHei,Segoe UI,sans-serif;font-size:14px;padding:6px 4px;color:#1f2937;'>" + "".join(blocks) + "</div>")
        sb = self.ai_chat.verticalScrollBar()
        if self._auto_scroll:
            sb.setValue(sb.maximum())
        else:
            sb.setValue(int(sb.maximum() * (old_scroll / old_max)))

    def _clean_ai_content(self, content):
        text = content or ""
        text = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"(?im)^\s*▎\s*thinking\s*$", "", text)
        text = re.sub(r"(?im)^\s*thinking\s*$", "", text)
        text = re.sub(r"(?im)^\s*>\s*", "", text)
        text = re.sub(r"(?im)^\s*---+\s*$", "", text)
        text = re.sub(r"(?im)^\s*###\s*", "", text)
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        text = re.sub(r"(?m)^[ \t]+$", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _message_to_html(self, msg):
        role = msg.get("role", "assistant")
        content = self._clean_ai_content(msg.get("content", ""))
        timestamp = msg.get("timestamp", "")
        header = msg.get("header", "")
        streaming = msg.get("streaming", False)
        name = "你" if role == "user" else "AI"
        border = "#adc8f6" if role == "user" else "#b7e4c7"
        bg = "#f3f7ff" if role == "user" else "#f4fbf6"
        badge = "#355c7d" if role == "user" else "#2d6a4f"
        ts = f" <span style='color:#8e8e93;font-size:11px;'>[{html.escape(timestamp)}]</span>" if timestamp else ""
        title = html.escape(header or name)
        tail = " <span style='color:#8e8e93;font-size:11px;'>生成中...</span>" if streaming else ""
        safe_content = html.escape(content).replace("\n", "<br>")
        body = safe_content or "<span style='color:#a1a1aa;'>等待回复...</span>"
        return (
            f"<div style='margin:10px 0;padding:14px 16px;border-radius:18px;background:{bg};border:1px solid {border};'>"
            f"<div style='margin:0 0 8px 0;color:{badge};font-size:12px;font-weight:700;'>{title}{ts}{tail}</div>"
            f"<div style='white-space:pre-wrap;line-height:1.65;color:#263238;font-size:14px;font-family:Microsoft YaHei UI,Microsoft YaHei,Segoe UI,sans-serif;'>{body}</div></div>"
        )

    def _append_chat_message(self, role, content, timestamp="", header="", streaming=False):
        self._chat_messages.append({
            "role": role,
            "content": content,
            "timestamp": timestamp,
            "header": header,
            "streaming": streaming,
        })
        self._render_chat_messages()

    def _start_ai_reply(self, model_id, channel):
        self._append_chat_message(
            "assistant",
            "",
            header=self._assistant_header(channel, model_id),
            streaming=True,
        )
        self._stream_message_index = len(self._chat_messages) - 1

    def _ai_done(self, ok, reply, model=""):
        self.btn_ai_send.setEnabled(True)
        self.btn_ai_send.setText("📤 发送")
        if ok:
            self._append_chat_message("assistant", reply)
            if self._cur_chat:
                ch.add_message(self._cur_chat, "assistant", reply)
        else:
            self._append_chat_message("assistant", f"错误：{reply}")
        self._update_balance()

    # ── 聊天管理 ──

    def _on_history_selected(self, cur, prev):
        if cur:
            cid = cur.data(Qt.ItemDataRole.UserRole)
            if cid and cid != self._cur_chat:
                self._cur_chat = cid
                data = ch.load_chat(cid)
                self._chat_messages = []
                if data:
                    for m in data.get("messages", []):
                        r, c = m["role"], m.get("content", "")
                        t = m.get("timestamp", "")
                        self._chat_messages.append({
                            "role": r,
                            "content": c,
                            "timestamp": t,
                            "header": "",
                            "streaming": False,
                        })
                self._render_chat_messages()

    def _refr_chats_list(self):
        self.history_list.blockSignals(True)
        self.history_list.clear()
        for c in ch.list_chats():
            item = QListWidgetItem(c["title"])
            item.setData(Qt.ItemDataRole.UserRole, c["id"])
            self.history_list.addItem(item)
        self.history_list.blockSignals(False)

    def _load_last_chat(self):
        chats = ch.list_chats()
        if chats:
            self._cur_chat = chats[0]["id"]
            data = ch.load_chat(self._cur_chat)
            self._chat_messages = []
            if data:
                for m in data.get("messages", []):
                    r, c = m["role"], m.get("content", "")
                    t = m.get("timestamp", "")
                    self._chat_messages.append({
                        "role": r,
                        "content": c,
                        "timestamp": t,
                        "header": "",
                        "streaming": False,
                    })
        else:
            self._new_chat()
        if chats:
            self._render_chat_messages()
        self._refr_chats_list()
        # 选中当前对话
        for i in range(self.history_list.count()):
            if self.history_list.item(i).data(Qt.ItemDataRole.UserRole) == self._cur_chat:
                self.history_list.setCurrentRow(i)
                break

    def _new_chat(self):
        cid = ch.new_chat()
        self._cur_chat = cid
        self._chat_messages = []
        self._render_chat_messages()
        self._refr_chats_list()
        for i in range(self.history_list.count()):
            if self.history_list.item(i).data(Qt.ItemDataRole.UserRole) == cid:
                self.history_list.setCurrentRow(i)
                break

    def _on_rename_chat(self):
        if not self._cur_chat:
            return
        from PyQt6.QtWidgets import QInputDialog
        title, ok = QInputDialog.getText(self, "重命名对话", "输入新名称：")
        if ok and title.strip():
            ch.rename_chat(self._cur_chat, title.strip())
            self._refr_chats_list()

    def _on_del_chat(self):
        if not self._cur_chat:
            return
        if QMessageBox.question(self, "确认", "删除当前对话？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
            return
        ch.delete_chat(self._cur_chat)
        self._refr_chats_list()
        self._load_last_chat()

    def _on_export_chat(self):
        if not self._cur_chat:
            return
        p, _ = QFileDialog.getSaveFileName(
            self, "导出对话", str(paths.DATA_DIR / f"{self._cur_chat}.md"), "Markdown (*.md)")
        if not p:
            return
        md = ch.export_md(self._cur_chat)
        with open(p, "w", encoding="utf-8") as f:
            f.write(md)
        QMessageBox.information(self, "导出完成", f"已导出到：{p}")

    def _update_balance(self):
        import threading
        self.ai_balance.setText("余额：查询中...")
        def worker():
            api_key = config_manager.get_api_key()
            bal = ch.get_balance(api_key)
            self._balance_signal.emit(bal)
        threading.Thread(target=worker, daemon=True).start()

    def _on_balance_updated(self, balance):
        if balance is not None:
            self.ai_balance.setText(f"余额：¥{balance}")
        else:
            self.ai_balance.setText("余额：--")

    # ── 意向公司页 ──

    def _init_job_targets_page(self):
        self.page_job_targets = QWidget()
        self.tabs.addTab(self.page_job_targets, "意向公司")
        layout = QVBoxLayout(self.page_job_targets)
        self.job_targets_widget = JobTargetsWidget()
        self.job_targets_widget.send_to_ai.connect(self._on_jt_send_to_ai)
        self.job_targets_widget.data_changed.connect(self._on_safe_refresh)
        self.job_targets_widget.data_changed.connect(self._refresh_ai_context_picker)
        layout.addWidget(self.job_targets_widget)

    # ── 工具页 ──

    def _init_tools_page(self):
        self.page_tools = QWidget()
        self.tabs.addTab(self.page_tools, "工具")
        layout = QGridLayout(self.page_tools)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(12)

        # 全局加大字号
        btn_font = QFont("Microsoft YaHei", 11)
        card_style = (
            "QGroupBox { margin-top: 18px; padding: 14px 10px 10px 10px; "
            "border: 1px solid #d9dee8; border-radius: 14px; background: #ffffff; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; "
            "padding: 0 6px; color: #253047; font-weight: 700; background: #f5f5f7; }"
        )

        # 文件管理
        grp1 = QGroupBox("📂 文件管理")
        grp1.setStyleSheet(card_style)
        g1 = QVBoxLayout(grp1)
        g1.addWidget(QLabel("管理简历/数据文件夹"))
        btn1 = QPushButton("📁 打开 data 文件夹")
        btn1.setFont(btn_font)
        btn1.setFixedHeight(40)
        btn1.clicked.connect(lambda: os.startfile(str(paths.DATA_DIR)))
        g1.addWidget(btn1)
        grp1.setMinimumHeight(118)
        layout.addWidget(grp1, 0, 0)

        # PDF → 图片
        grp2 = QGroupBox("📷 PDF → 图片")
        grp2.setStyleSheet(card_style)
        g2 = QVBoxLayout(grp2)
        g2.addWidget(QLabel("将 PDF 每页导出为 PNG/JPEG/TIFF 图片（支持 DPI 设置）"))
        self.btn_pdf2img = QPushButton("📷 PDF → 图片")
        self.btn_pdf2img.setFont(btn_font)
        self.btn_pdf2img.setFixedHeight(40)
        self.btn_pdf2img.clicked.connect(self._run_pdf2img)
        g2.addWidget(self.btn_pdf2img)
        grp2.setMinimumHeight(118)
        layout.addWidget(grp2, 0, 1)

        # 文档 → 图片版 PDF
        grp3 = QGroupBox("📄 文档 → 图片版 PDF")
        grp3.setStyleSheet(card_style)
        g3 = QVBoxLayout(grp3)
        g3.addWidget(QLabel("将 Word/图片/PDF 转为图片版 PDF（适合提交/归档）"))
        btn_imgpdf = QPushButton("📄 文档 → 图片版 PDF")
        btn_imgpdf.setFont(btn_font)
        btn_imgpdf.setFixedHeight(40)
        btn_imgpdf.clicked.connect(self._run_imgpdf)
        g3.addWidget(btn_imgpdf)
        grp3.setMinimumHeight(118)
        layout.addWidget(grp3, 1, 0)

        # 本地网页看板设置
        grp4 = QGroupBox("🌐 网页看板设置")
        grp4.setStyleSheet(card_style)
        g4 = QVBoxLayout(grp4)
        g4.addWidget(QLabel("仅限本机访问（127.0.0.1）。可修改端口，保存后立即重启网页网关。"))
        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("端口："))
        self.gateway_port = QSpinBox()
        self.gateway_port.setRange(1024, 65535)
        self.gateway_port.setValue(config_manager.get_gateway_port())
        self.gateway_port.setFixedWidth(120)
        port_row.addWidget(self.gateway_port)
        btn_gateway_save = QPushButton("保存并重启网关")
        btn_gateway_save.setFixedHeight(34)
        btn_gateway_save.clicked.connect(self._save_gateway_port)
        port_row.addWidget(btn_gateway_save)
        port_row.addStretch()
        g4.addLayout(port_row)
        self.gateway_url_label = QLabel(f"当前地址：{local_gateway.get_url()}")
        self.gateway_url_label.setStyleSheet("color:#52657d;")
        g4.addWidget(self.gateway_url_label)
        grp4.setMinimumHeight(132)
        layout.addWidget(grp4, 1, 1)

        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(2, 1)

    def _save_gateway_port(self):
        """保存端口并平滑切换正在运行的本机网关。"""
        port = self.gateway_port.value()
        try:
            url = local_gateway.restart_gateway(port)
            config_manager.set_gateway_port(port)
        except OSError as exc:
            QMessageBox.warning(self, "端口不可用", f"端口 {port} 已被其他程序占用，已保留原网页网关。\n\n{exc}")
            return
        self.gateway_url_label.setText(f"当前地址：{url}")
        self.statusBar().showMessage(f"网页网关已切换到 {url}", 6000)

    # ── PDF → 图片（子线程）──

    def _run_pdf2img(self):
        from PyQt6.QtWidgets import QDialog, QSpinBox, QComboBox, QFormLayout, QDialogButtonBox
        import threading

        dlg = QDialog(self)
        dlg.setWindowTitle("PDF → 图片 - 设置")
        fl = QFormLayout(dlg)
        sp = QSpinBox()
        sp.setRange(72, 600); sp.setValue(200); sp.setSuffix(" DPI")
        fl.addRow("分辨率：", sp)
        fmt = QComboBox()
        fmt.addItems(["PNG", "JPEG", "TIFF", "BMP", "WEBP"])
        fl.addRow("格式：", fmt)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        fl.addRow(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        dpi, img_fmt = sp.value(), fmt.currentText()

        p, _ = QFileDialog.getOpenFileName(self, "选择 PDF", "", "PDF (*.pdf)")
        if not p:
            return
        src = Path(p)
        out_dir = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        if not out_dir:
            return

        self.statusBar().showMessage("⏳ 正在转换 (PDF→图片)...")
        self.btn_pdf2img.setEnabled(False)
        self.btn_pdf2img.setText("⏳ 转换中...")

        def worker():
            try:
                from tools_pdf2img import pdf_to_images
                files = pdf_to_images(p, out_dir, fmt=img_fmt, dpi=dpi)
                for i, old in enumerate(files):
                    ext = Path(old).suffix
                    new = Path(out_dir) / f"{src.stem}-图片-{i+1}{ext}"
                    try:
                        Path(old).rename(new)
                    except OSError:
                        import shutil
                        shutil.copy2(old, new)
                self._pdf_done_signal.emit(True, f"✅ 已导出 {len(files)} 张 {img_fmt} 图片")
            except Exception as e:
                import traceback
                err_msg = f"{type(e).__name__}: {e}\n\n{traceback.format_exc()[:200]}"
                self._pdf_done_signal.emit(False, err_msg)

        threading.Thread(target=worker, daemon=True).start()

    def _pdf2img_done(self, success, msg):
        self.btn_pdf2img.setEnabled(True)
        self.btn_pdf2img.setText("📷 PDF → 图片")
        if success:
            self.statusBar().showMessage(msg, 8000)
        else:
            self.statusBar().clearMessage()
            QMessageBox.warning(self, "转换错误", msg)

    # ── 文档 → 图片版 PDF（子线程）──

    def _run_imgpdf(self):
        from PyQt6.QtWidgets import QDialog, QSpinBox, QFormLayout, QDialogButtonBox
        import threading

        dlg = QDialog(self)
        dlg.setWindowTitle("文档 → 图片版 PDF - 设置")
        fl = QFormLayout(dlg)
        sp = QSpinBox()
        sp.setRange(72, 600); sp.setValue(200); sp.setSuffix(" DPI")
        fl.addRow("分辨率：", sp)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        fl.addRow(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        dpi = sp.value()

        p, _ = QFileDialog.getOpenFileName(
            self, "选择文件", "", "支持格式 (*.pdf *.docx *.doc *.jpg *.jpeg *.png *.bmp *.tiff)")
        if not p:
            return
        src = Path(p)
        default_name = f"{src.stem}-图片版.pdf"
        out, _ = QFileDialog.getSaveFileName(self, "保存为", str(src.parent / default_name), "PDF (*.pdf)")
        if not out:
            return

        self.statusBar().showMessage("⏳ 正在转换 (文档→图片版PDF)...")
        btn = self.sender()
        btn.setEnabled(False)
        btn.setText("⏳ 转换中...")

        def worker():
            try:
                from tools_imgpdf import convert_to_image_pdf
                convert_to_image_pdf(p, out, dpi=dpi)
                self._imgpdf_done_signal.emit(True, f"✅ 已生成：{out}", btn)
            except Exception as e:
                import traceback
                err_msg = f"{type(e).__name__}: {e}\n\n{traceback.format_exc()[:200]}"
                self._imgpdf_done_signal.emit(False, err_msg, btn)

        threading.Thread(target=worker, daemon=True).start()

    def _imgpdf_done(self, success, msg, btn=None):
        b = btn if btn else self.sender()
        if b:
            b.setEnabled(True)
            b.setText("📄 文档 → 图片版 PDF")
        if success:
            self.statusBar().showMessage(msg, 8000)
        else:
            self.statusBar().clearMessage()
            QMessageBox.warning(self, "转换错误", msg)
