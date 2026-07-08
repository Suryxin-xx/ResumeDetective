"""
job_targets_widget.py — 意向公司/岗位管理组件
支持排序、筛选、隐藏已投递、优先级、一键转为投递/发送到 AI
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QComboBox, QMessageBox, QDialog, QFormLayout, QTextEdit,
    QDialogButtonBox, QCheckBox, QSpinBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor

from . import db_manager

HEADERS = ["#", "优先级", "公司", "岗位", "城市", "状态", "更新时间", "JD 摘要", "备注"]
STATUS_LIST = ["全部", "待研究", "待投递", "已投递", "暂不考虑"]


class JobTargetEditDialog(QDialog):
    """新增/编辑意向公司"""

    STATUS_OPTIONS = ["待研究", "待投递", "已投递", "暂不考虑"]

    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self._data = data
        self.setWindowTitle("编辑意向公司" if data else "新增意向公司")
        self.resize(500, 440)
        self._setup_ui()
        if data:
            self._load_data(data)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.edit_company = QLineEdit()
        self.edit_company.setPlaceholderText("公司名称（必填）")
        form.addRow("公司：", self.edit_company)

        self.edit_position = QLineEdit()
        self.edit_position.setPlaceholderText("岗位名称（必填）")
        form.addRow("岗位：", self.edit_position)

        self.edit_city = QLineEdit()
        self.edit_city.setPlaceholderText("城市（可选）")
        form.addRow("城市：", self.edit_city)

        self.combo_status = QComboBox()
        self.combo_status.addItems(self.STATUS_OPTIONS)
        form.addRow("状态：", self.combo_status)

        self.spin_priority = QSpinBox()
        self.spin_priority.setRange(0, 5)
        self.spin_priority.setToolTip("优先级 0-5")
        form.addRow("优先级：", self.spin_priority)

        self.edit_jd = QTextEdit()
        self.edit_jd.setPlaceholderText("粘贴 JD 原文...")
        self.edit_jd.setMaximumHeight(100)
        form.addRow("JD 原文：", self.edit_jd)

        self.edit_link = QLineEdit()
        self.edit_link.setPlaceholderText("JD 来源链接（可选）")
        form.addRow("来源链接：", self.edit_link)

        self.edit_notes = QTextEdit()
        self.edit_notes.setPlaceholderText("备注（可选）")
        self.edit_notes.setMaximumHeight(60)
        form.addRow("备注：", self.edit_notes)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_data(self, d):
        self.edit_company.setText(d.get("company_name", ""))
        self.edit_position.setText(d.get("position_name", ""))
        self.edit_city.setText(d.get("city", ""))
        status = d.get("status", "待研究")
        idx = self.combo_status.findText(status)
        self.combo_status.setCurrentIndex(max(idx, 0))
        self.spin_priority.setValue(d.get("priority", 0))
        self.edit_jd.setText(d.get("jd_text", ""))
        self.edit_link.setText(d.get("jd_link", ""))
        self.edit_notes.setText(d.get("notes", ""))

    def _on_accept(self):
        if not self.edit_company.text().strip() or not self.edit_position.text().strip():
            QMessageBox.warning(self, "信息不完整", "公司名和岗位名为必填项。")
            return
        self.accept()

    def get_data(self):
        return {
            "company_name": self.edit_company.text().strip(),
            "position_name": self.edit_position.text().strip(),
            "city": self.edit_city.text().strip(),
            "status": self.combo_status.currentText(),
            "priority": self.spin_priority.value(),
            "jd_text": self.edit_jd.toPlainText().strip(),
            "jd_link": self.edit_link.text().strip(),
            "notes": self.edit_notes.toPlainText().strip(),
        }


class JobTargetsWidget(QWidget):
    """意向公司列表组件"""

    send_to_ai = pyqtSignal(str, str, str)  # company, position, jd_text
    data_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self.refresh)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ── 顶部按钮栏 ──
        top_bar = QHBoxLayout()
        self.btn_add = QPushButton("＋ 新增意向")
        self.btn_add.setFixedHeight(32)
        self.btn_add.clicked.connect(self._on_add)
        top_bar.addWidget(self.btn_add)
        self.btn_edit = QPushButton("✏ 编辑")
        self.btn_edit.setFixedHeight(32)
        self.btn_edit.clicked.connect(self._on_edit)
        top_bar.addWidget(self.btn_edit)
        self.btn_delete = QPushButton("🗑 删除")
        self.btn_delete.setFixedHeight(32)
        self.btn_delete.clicked.connect(self._on_delete)
        top_bar.addWidget(self.btn_delete)
        self.btn_apply = QPushButton("📤 转为投递")
        self.btn_apply.setFixedHeight(32)
        self.btn_apply.setStyleSheet("font-weight:bold;color:#1565C0;")
        self.btn_apply.setToolTip("将选中的意向公司转为投递看板记录")
        self.btn_apply.clicked.connect(self._on_convert)
        top_bar.addWidget(self.btn_apply)
        self.btn_send_ai = QPushButton("🤖 发送到 AI")
        self.btn_send_ai.setFixedHeight(32)
        self.btn_send_ai.setStyleSheet("font-weight:bold;color:#2E7D32;")
        self.btn_send_ai.setToolTip("将当前选中 JD 设为 AI 上下文")
        self.btn_send_ai.clicked.connect(self._on_send_to_ai)
        top_bar.addWidget(self.btn_send_ai)
        self.lbl_count = QLabel("0 条")
        self.lbl_count.setStyleSheet("color:#666;padding-left:8px;")
        top_bar.addStretch()
        top_bar.addWidget(self.lbl_count)
        layout.addLayout(top_bar)

        # ── 排序 + 筛选栏 ──
        filter_bar = QHBoxLayout()
        sort_label = QLabel("排序：")
        filter_bar.addWidget(sort_label)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["默认", "优先级(高→低)", "更新时间(最新)", "公司名"])
        self.sort_combo.currentIndexChanged.connect(self.refresh)
        filter_bar.addWidget(self.sort_combo)

        filter_bar.addWidget(QLabel("状态："))
        self.filter_status = QComboBox()
        self.filter_status.addItems(STATUS_LIST)
        self.filter_status.currentTextChanged.connect(lambda _: self.refresh())
        filter_bar.addWidget(self.filter_status)

        self.chk_hide_applied = QCheckBox("隐藏已投递")
        self.chk_hide_applied.stateChanged.connect(lambda _: self.refresh())
        filter_bar.addWidget(self.chk_hide_applied)

        self.filter_keyword = QLineEdit()
        self.filter_keyword.setPlaceholderText("搜索公司/岗位/JD...")
        self.filter_keyword.textChanged.connect(lambda _: self._search_timer.start(300))
        filter_bar.addWidget(self.filter_keyword, stretch=1)

        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self._clear_filters)
        filter_bar.addWidget(btn_clear)
        layout.addLayout(filter_bar)

        # ── 表格 ──
        self.table = QTableWidget()
        self.table.setColumnCount(len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        # 柔和选中样式
        self.table.setStyleSheet("""
            QTableWidget::item:selected {
                background-color: #BBDEFB;
                color: #1a1a1a;
            }
            QTableWidget::item:hover {
                background-color: #E3F2FD;
            }
        """)
        self.table.cellDoubleClicked.connect(self._on_cell_double_click)
        # 表头点击排序
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self._sort_col = -1
        self._sort_desc = False
        layout.addWidget(self.table, stretch=1)

        # 列宽
        col_widths = [36, 70, 140, 140, 70, 80, 140, 180, 100]
        for i, w in enumerate(col_widths):
            if i < len(col_widths):
                self.table.setColumnWidth(i, w)

    def refresh(self):
        """重新加载列表"""
        status = self.filter_status.currentText()
        kw = self.filter_keyword.text().strip()
        st = status if status != "全部" else ""
        targets = db_manager.get_job_targets_filtered(status=st, keyword=kw)

        # 隐藏已投递
        if self.chk_hide_applied.isChecked():
            targets = [t for t in targets if t.get("status") != "已投递"]

        # 排序
        sort_idx = self.sort_combo.currentIndex()
        if sort_idx == 1:
            targets.sort(key=lambda t: -(t.get("priority", 0) or 0))
        elif sort_idx == 2:
            targets.sort(key=lambda t: t.get("updated_at", ""), reverse=True)
        elif sort_idx == 3:
            targets.sort(key=lambda t: t.get("company_name", ""))

        self._targets_data = targets
        self.lbl_count.setText(f"{len(targets)} 条")
        self.table.setRowCount(len(targets))

        for row, t in enumerate(targets):
            self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))

            pri = t.get("priority", 0)
            pi = QTableWidgetItem("★" * pri if pri else "")
            pi.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            pi.setData(Qt.ItemDataRole.UserRole + 1, pri)
            self.table.setItem(row, 1, pi)

            self.table.setItem(row, 2, QTableWidgetItem(t.get("company_name", "")))
            self.table.setItem(row, 3, QTableWidgetItem(t.get("position_name", "")))
            self.table.setItem(row, 4, QTableWidgetItem(t.get("city", "")))
            self.table.setItem(row, 5, QTableWidgetItem(t.get("status", "")))

            updated = t.get("updated_at", "")
            self.table.setItem(row, 6, QTableWidgetItem(updated[:16] if updated else ""))

            jd = t.get("jd_text", "")
            jd_short = jd[:60] + "..." if len(jd) > 60 else jd
            self.table.setItem(row, 7, QTableWidgetItem(jd_short))
            self.table.setItem(row, 8, QTableWidgetItem(t.get("notes", "")))

            # 存储 id
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, t["id"])

    def _on_cell_double_click(self, row, col):
        """双击优先级列切换"""
        if col == 1:
            self._toggle_priority(row)
            return
        self.table.selectRow(row)
        self._on_edit()

    def _toggle_priority(self, row):
        """循环切换优先级 0→1→2→3→4→5→0"""
        item = self.table.item(row, 1)
        if item:
            cur = item.data(Qt.ItemDataRole.UserRole + 1) or 0
            new_pri = (cur + 1) % 6
            tid = self._get_selected_id()
            if tid is not None:
                db_manager.update_job_target_priority(tid, new_pri)
                self.refresh()
                self.data_changed.emit()

    def _on_header_clicked(self, col):
        """表头点击排序"""
        import time
        if self._sort_col == col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col = col
            self._sort_desc = False

        data = self._targets_data[:]
        if col == 0:
            pass  # 序号不排序
        elif col == 1:
            data.sort(key=lambda t: t.get("priority", 0) or 0, reverse=self._sort_desc)
        elif col == 2:
            data.sort(key=lambda t: t.get("company_name", ""), reverse=self._sort_desc)
        elif col == 3:
            data.sort(key=lambda t: t.get("position_name", ""), reverse=self._sort_desc)
        elif col == 4:
            data.sort(key=lambda t: t.get("city", ""), reverse=self._sort_desc)
        elif col == 5:
            data.sort(key=lambda t: t.get("status", ""), reverse=self._sort_desc)
        elif col == 6:
            data.sort(key=lambda t: t.get("updated_at", ""), reverse=self._sort_desc)

        self._targets_data = data
        self._repopulate(data)

    def _repopulate(self, targets):
        """重新填充表格（不重新查询）"""
        self.table.setRowCount(len(targets))
        for row, t in enumerate(targets):
            self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            pri = t.get("priority", 0)
            pi = QTableWidgetItem("★" * pri if pri else "")
            pi.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            pi.setData(Qt.ItemDataRole.UserRole + 1, pri)
            self.table.setItem(row, 1, pi)
            self.table.setItem(row, 2, QTableWidgetItem(t.get("company_name", "")))
            self.table.setItem(row, 3, QTableWidgetItem(t.get("position_name", "")))
            self.table.setItem(row, 4, QTableWidgetItem(t.get("city", "")))
            self.table.setItem(row, 5, QTableWidgetItem(t.get("status", "")))
            updated = t.get("updated_at", "")
            self.table.setItem(row, 6, QTableWidgetItem(updated[:16] if updated else ""))
            jd = t.get("jd_text", "")
            self.table.setItem(row, 7, QTableWidgetItem(jd[:60] + "..." if len(jd) > 60 else jd))
            self.table.setItem(row, 8, QTableWidgetItem(t.get("notes", "")))
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, t["id"])

    def _clear_filters(self):
        self.filter_status.setCurrentText("全部")
        self.filter_keyword.clear()
        self.chk_hide_applied.setChecked(False)
        self.sort_combo.setCurrentIndex(0)
        self.refresh()

    def _get_selected_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _get_selected_data(self):
        tid = self._get_selected_id()
        if tid is None:
            return None
        for t in self._targets_data:
            if t["id"] == tid:
                return t
        return None

    def _on_add(self):
        dlg = JobTargetEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            db_manager.add_job_target(**data)
            self.refresh()
            self.data_changed.emit()

    def _on_edit(self):
        t = self._get_selected_data()
        if t is None:
            QMessageBox.information(self, "提示", "请先选中一条记录。")
            return
        dlg = JobTargetEditDialog(self, t)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            db_manager.update_job_target(t["id"], **data)
            self.refresh()
            self.data_changed.emit()

    def _on_delete(self):
        tid = self._get_selected_id()
        if tid is None:
            QMessageBox.information(self, "提示", "请先选中一条记录。")
            return
        if QMessageBox.question(self, "确认删除",
                "确定删除这条意向公司记录？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
            return
        db_manager.delete_job_target(tid)
        self.refresh()
        self.data_changed.emit()

    def _on_convert(self):
        tid = self._get_selected_id()
        if tid is None:
            QMessageBox.information(self, "提示", "请先选中一条意向公司记录。")
            return
        t = self._get_selected_data()
        if t is None:
            return
        if t.get("status") == "已投递":
            QMessageBox.information(self, "提示", "该记录状态已为「已投递」，无需重复转换。")
            return
        if QMessageBox.question(self, "确认转换",
                f"将「{t['company_name']} - {t['position_name']}」转为投递看板记录？\n\n"
                "转换后该条意向状态将变为「已投递」。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
            return
        ok, result = db_manager.convert_job_target_to_application(tid)
        if ok:
            QMessageBox.information(self, "转换成功",
                "已成功转为投递记录，可在「投递看板」中查看和管理。")
            self.refresh()
            self.data_changed.emit()
        else:
            QMessageBox.warning(self, "转换失败", f"转换失败：{result}")

    def _on_send_to_ai(self):
        t = self._get_selected_data()
        if t is None:
            QMessageBox.information(self, "提示", "请先选中一条意向公司记录。")
            return
        jd = t.get("jd_text", "").strip()
        if not jd:
            QMessageBox.information(self, "提示", "该意向公司未录入 JD，请在编辑时添加 JD 原文。")
            return
        self.send_to_ai.emit(
            t.get("company_name", ""),
            t.get("position_name", ""),
            jd,
        )
