"""Structured interview scheduling and review workspace for the desktop app."""

from PyQt6.QtCore import QDateTime
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import db_manager


class InterviewDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新增面试安排 / 复盘")
        self.resize(620, 650)
        layout = QFormLayout(self)

        self.application = QComboBox()
        for app in db_manager.get_applications_with_resume():
            if app["current_status"] != "终止":
                self.application.addItem(
                    f'{app["company_name"]} · {app["position_name"]}', app["id"]
                )
        self.round = QComboBox()
        self.round.addItems(["一面", "二面", "三面", "HR 面", "其他"])
        self.interview_time = QDateTimeEdit(QDateTime.currentDateTime())
        self.interview_time.setCalendarPopup(True)
        self.interview_time.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.result = QComboBox()
        self.result.addItems(["待确认", "通过", "未通过", "取消"])
        self.questions = QTextEdit()
        self.questions.setPlaceholderText("记录主要问题、算法题或项目追问")
        self.weak_points = QTextEdit()
        self.weak_points.setPlaceholderText("哪些问题没有答好")
        self.summary = QTextEdit()
        self.summary.setPlaceholderText("整体感受、面试官风格和复盘结论")
        self.follow_up = QTextEdit()
        self.follow_up.setPlaceholderText("后续需要复习、准备或跟进什么")

        layout.addRow("对应岗位：", self.application)
        layout.addRow("面试轮次：", self.round)
        layout.addRow("面试时间：", self.interview_time)
        layout.addRow("当前结果：", self.result)
        layout.addRow("面试问题：", self.questions)
        layout.addRow("薄弱点：", self.weak_points)
        layout.addRow("复盘总结：", self.summary)
        layout.addRow("后续行动：", self.follow_up)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def result_data(self):
        return {
            "application_id": self.application.currentData(),
            "round_name": self.round.currentText(),
            "interview_time": self.interview_time.dateTime().toString("yyyy-MM-dd HH:mm"),
            "result": self.result.currentText(),
            "questions": self.questions.toPlainText().strip(),
            "weak_points": self.weak_points.toPlainText().strip(),
            "summary": self.summary.toPlainText().strip(),
            "follow_up": self.follow_up.toPlainText().strip(),
        }


class InterviewsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        heading = QLabel("面试安排与复盘")
        heading.setStyleSheet("font-size:20px;font-weight:700;")
        subtitle = QLabel("一条记录对应一轮面试；终止岗位的历史复盘仍会保留。")
        subtitle.setStyleSheet("color:#64748a;")
        layout.addWidget(heading)
        layout.addWidget(subtitle)

        toolbar = QHBoxLayout()
        add_button = QPushButton("＋ 新增面试")
        add_button.clicked.connect(self._add)
        self.delete_button = QPushButton("删除选中")
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self._delete)
        self.search = QComboBox()
        self.search.addItems(["全部结果", "待确认", "通过", "未通过", "取消"])
        self.search.currentIndexChanged.connect(self.refresh)
        toolbar.addWidget(add_button)
        toolbar.addWidget(self.delete_button)
        toolbar.addStretch()
        toolbar.addWidget(self.search)
        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["公司 / 岗位", "轮次", "时间", "结果", "问题", "薄弱点", "复盘", "后续行动"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.itemSelectionChanged.connect(
            lambda: self.delete_button.setEnabled(self.table.currentRow() >= 0)
        )
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self):
        selected_result = self.search.currentText() if hasattr(self, "search") else "全部结果"
        records = db_manager.get_interviews()
        if selected_result != "全部结果":
            records = [record for record in records if record.get("result") == selected_result]
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = [
                f'{record.get("company_name", "")} · {record.get("position_name", "")}',
                record.get("round", ""),
                record.get("interview_time", ""),
                record.get("result", "待确认"),
                record.get("questions", ""),
                record.get("weak_points", ""),
                record.get("summary", ""),
                record.get("follow_up", ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                item.setToolTip(str(value or ""))
                if column == 0:
                    item.setData(256, record["id"])
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.delete_button.setEnabled(False)

    def _add(self):
        dialog = InterviewDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        data = dialog.result_data()
        if data["application_id"] is None:
            QMessageBox.information(self, "暂无岗位", "请先新增一条流程中的投递。")
            return
        db_manager.add_interview(**data)
        if data["follow_up"]:
            db_manager.update_application_details(
                data["application_id"], next_action=data["follow_up"]
            )
        self.refresh()

    def _delete(self):
        row = self.table.currentRow()
        if row < 0:
            return
        interview_id = self.table.item(row, 0).data(256)
        answer = QMessageBox.question(
            self,
            "确认删除",
            "删除这条面试记录？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            db_manager.delete_interview(interview_id)
            self.refresh()
