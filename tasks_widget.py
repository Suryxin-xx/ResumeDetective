"""Local action list for deadlines, follow-ups, interviews, and written tests."""

from datetime import date

from PyQt6.QtCore import Qt, QDate, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import db_manager


class TaskDialog(QDialog):
    """Small focused editor so task entry stays faster than opening a spreadsheet."""

    def __init__(self, parent=None, task=None):
        super().__init__(parent)
        self._task = task or {}
        self.setWindowTitle("编辑行动" if task else "新增行动")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(12)

        self.title_input = QLineEdit(self._task.get("title", ""))
        self.title_input.setPlaceholderText("例如：完成笔试 / 给 HR 跟进 / 准备二面")
        form.addRow("行动内容", self.title_input)

        self.priority_combo = QComboBox()
        self.priority_combo.addItem("普通", 0)
        self.priority_combo.addItem("重要", 1)
        self.priority_combo.addItem("高优先级", 2)
        self.priority_combo.addItem("紧急", 3)
        self.priority_combo.setCurrentIndex(max(0, min(int(self._task.get("priority", 0)), 3)))
        form.addRow("优先级", self.priority_combo)

        due_row = QWidget()
        due_layout = QHBoxLayout(due_row)
        due_layout.setContentsMargins(0, 0, 0, 0)
        self.has_due = QCheckBox("设置截止日期")
        due_layout.addWidget(self.has_due)
        self.due_edit = QDateEdit()
        self.due_edit.setCalendarPopup(True)
        self.due_edit.setDisplayFormat("yyyy-MM-dd")
        due_layout.addWidget(self.due_edit)
        due_layout.addStretch()
        due_value = self._task.get("due_date", "")
        if due_value:
            parsed = QDate.fromString(due_value, "yyyy-MM-dd")
            self.due_edit.setDate(parsed if parsed.isValid() else QDate.currentDate())
            self.has_due.setChecked(True)
        else:
            self.due_edit.setDate(QDate.currentDate())
        self.has_due.toggled.connect(self.due_edit.setEnabled)
        self.due_edit.setEnabled(self.has_due.isChecked())
        form.addRow("时间", due_row)

        self.scope_combo = QComboBox()
        self._populate_scopes()
        form.addRow("关联事项", self.scope_combo)

        self.notes_input = QTextEdit(self._task.get("notes", ""))
        self.notes_input.setPlaceholderText("可写面试链接、准备方向或跟进备注")
        self.notes_input.setMinimumHeight(90)
        form.addRow("备注", self.notes_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_scopes(self):
        self.scope_combo.addItem("不关联具体岗位", ("", None))
        for app in db_manager.get_applications_with_resume():
            text = f"投递 · {app.get('company_name', '')} - {app.get('position_name', '')}"
            self.scope_combo.addItem(text, ("application", app["id"]))
        for target in db_manager.get_job_targets_filtered():
            text = f"意向 · {target.get('company_name', '')} - {target.get('position_name', '')}"
            self.scope_combo.addItem(text, ("target", target["id"]))

        desired = (self._task.get("scope_type", ""), self._task.get("scope_id"))
        for index in range(self.scope_combo.count()):
            if self.scope_combo.itemData(index) == desired:
                self.scope_combo.setCurrentIndex(index)
                break

    def _accept_if_valid(self):
        if not self.title_input.text().strip():
            QMessageBox.information(self, "缺少内容", "请写下这项行动要完成什么。")
            self.title_input.setFocus()
            return
        self.accept()

    def get_result(self):
        scope_type, scope_id = self.scope_combo.currentData()
        return {
            "title": self.title_input.text().strip(),
            "priority": self.priority_combo.currentData(),
            "due_date": self.due_edit.date().toString("yyyy-MM-dd") if self.has_due.isChecked() else "",
            "scope_type": scope_type,
            "scope_id": scope_id,
            "notes": self.notes_input.toPlainText().strip(),
        }


class TasksWidget(QWidget):
    """A local, sortable task list with no account, sync service, or personal-data upload."""

    data_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        heading = QHBoxLayout()
        title_group = QVBoxLayout()
        title = QLabel("行动清单")
        title.setObjectName("pageTitle")
        title_group.addWidget(title)
        subtitle = QLabel("把笔试、面试准备、投递跟进和截止日期放在一个地方。所有内容仅保存在本机。")
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        title_group.addWidget(subtitle)
        heading.addLayout(title_group, stretch=1)
        self.summary_label = QLabel()
        self.summary_label.setObjectName("taskSummary")
        heading.addWidget(self.summary_label)
        layout.addLayout(heading)

        toolbar = QHBoxLayout()
        self.state_filter = QComboBox()
        self.state_filter.addItem("待办", "open")
        self.state_filter.addItem("已完成", "done")
        self.state_filter.addItem("全部", "all")
        self.state_filter.currentIndexChanged.connect(self.refresh)
        toolbar.addWidget(self.state_filter)
        toolbar.addStretch()
        self.add_button = QPushButton("新增行动")
        self.add_button.setProperty("class", "primary")
        self.add_button.clicked.connect(self._add_task)
        toolbar.addWidget(self.add_button)
        self.edit_button = QPushButton("编辑")
        self.edit_button.clicked.connect(self._edit_task)
        toolbar.addWidget(self.edit_button)
        self.state_button = QPushButton("标记完成")
        self.state_button.clicked.connect(self._toggle_task_state)
        toolbar.addWidget(self.state_button)
        self.delete_button = QPushButton("删除")
        self.delete_button.setProperty("class", "destructive")
        self.delete_button.clicked.connect(self._delete_task)
        toolbar.addWidget(self.delete_button)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["状态", "截止日期", "优先级", "行动", "关联岗位", "备注", "创建时间"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self._update_actions)
        self.table.itemDoubleClicked.connect(lambda _: self._edit_task())
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        self.table.setColumnWidth(0, 72)
        self.table.setColumnWidth(1, 105)
        self.table.setColumnWidth(2, 84)
        self.table.setColumnWidth(3, 260)
        self.table.setColumnWidth(4, 250)
        self.table.setColumnWidth(5, 260)
        self.table.setColumnWidth(6, 145)
        layout.addWidget(self.table, stretch=1)

    def _scope_labels(self):
        labels = {}
        for app in db_manager.get_applications_with_resume():
            labels[("application", app["id"])] = f"投递 · {app.get('company_name', '')} - {app.get('position_name', '')}"
        for target in db_manager.get_job_targets_filtered():
            labels[("target", target["id"])] = f"意向 · {target.get('company_name', '')} - {target.get('position_name', '')}"
        return labels

    def refresh(self):
        selected_id = self._selected_task_id()
        state = self.state_filter.currentData()
        tasks = db_manager.get_job_tasks("" if state == "all" else state)
        labels = self._scope_labels()
        today = date.today().isoformat()
        overdue = sum(1 for task in db_manager.get_job_tasks("open") if task.get("due_date") and task["due_date"] < today)
        due_today = sum(1 for task in db_manager.get_job_tasks("open") if task.get("due_date") == today)
        self.summary_label.setText(f"待办 {len(db_manager.get_job_tasks('open'))}  ·  今天 {due_today}  ·  已逾期 {overdue}")

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for row, task in enumerate(tasks):
            self.table.insertRow(row)
            task_id = task["id"]
            state_text = "已完成" if task.get("state") == "done" else "待办"
            due_date = task.get("due_date", "") or "未设置"
            priority = int(task.get("priority", 0))
            priority_text = ["普通", "重要", "高", "紧急"][max(0, min(priority, 3))]
            scope = labels.get((task.get("scope_type", ""), task.get("scope_id")), "未关联")
            values = [state_text, due_date, priority_text, task.get("title", ""), scope, task.get("notes", ""), (task.get("created_at", "") or "")[:16]]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, task_id)
                if column in (0, 1, 2):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if task.get("state") == "open" and task.get("due_date") and task["due_date"] < today:
                    item.setForeground(QColor("#b42318"))
                elif task.get("state") == "done":
                    item.setForeground(QColor("#86868b"))
                self.table.setItem(row, column, item)

        self.table.setSortingEnabled(True)
        if selected_id is not None:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == selected_id:
                    self.table.selectRow(row)
                    break
        self._update_actions()

    def _selected_task_id(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected_task(self):
        task_id = self._selected_task_id()
        if task_id is None:
            return None
        return next((task for task in db_manager.get_job_tasks("") if task["id"] == task_id), None)

    def _update_actions(self):
        task = self._selected_task()
        enabled = task is not None
        self.edit_button.setEnabled(enabled)
        self.state_button.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)
        if task:
            self.state_button.setText("重新打开" if task.get("state") == "done" else "标记完成")

    def _add_task(self):
        dialog = TaskDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        data = dialog.get_result()
        db_manager.add_job_task(**data)
        self.refresh()
        self.data_changed.emit()

    def _edit_task(self):
        task = self._selected_task()
        if not task:
            return
        dialog = TaskDialog(self, task)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        db_manager.update_job_task(task["id"], **dialog.get_result())
        self.refresh()
        self.data_changed.emit()

    def _toggle_task_state(self):
        task = self._selected_task()
        if not task:
            return
        db_manager.set_job_task_state(task["id"], "open" if task.get("state") == "done" else "done")
        self.refresh()
        self.data_changed.emit()

    def _delete_task(self):
        task = self._selected_task()
        if not task:
            return
        answer = QMessageBox.question(
            self,
            "删除行动",
            f"确定删除“{task.get('title', '')}”吗？此操作无法撤销。",
            QMessageBox.StandardButton.Delete | QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Delete:
            return
        db_manager.delete_job_task(task["id"])
        self.refresh()
        self.data_changed.emit()
