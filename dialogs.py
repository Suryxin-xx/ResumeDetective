"""
新增投递对话框
包含：公司名、岗位名、文件选择、JD 原文、备注
"""

import shutil
from pathlib import Path
from datetime import datetime

import paths
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QDialogButtonBox,
)
from PyQt6.QtCore import Qt


class AddResumeDialog(QDialog):
    """新增投递弹窗"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新增投递")
        self.resize(500, 450)

        self._selected_file = ""  # 原始文件路径
        self._result_data = None  # 提交时保存结果

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # 公司名
        self.edit_company = QLineEdit()
        self.edit_company.setPlaceholderText("必填")
        form.addRow("公司名：", self.edit_company)

        # 岗位名
        self.edit_position = QLineEdit()
        self.edit_position.setPlaceholderText("必填")
        form.addRow("岗位名：", self.edit_position)

        # 文件选择
        file_layout = QHBoxLayout()
        self.edit_file = QLineEdit()
        self.edit_file.setReadOnly(True)
        self.edit_file.setPlaceholderText("选择 PDF/DOCX 简历文件（可选）")
        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self._on_browse)
        file_layout.addWidget(self.edit_file)
        file_layout.addWidget(btn_browse)
        form.addRow("简历文件：", file_layout)

        # 版本备注
        self.edit_version = QLineEdit()
        self.edit_version.setPlaceholderText("如：v2.0-技术岗专用")
        form.addRow("版本备注：", self.edit_version)

        self.edit_source = QLineEdit()
        self.edit_source.setPlaceholderText("如：官网、内推、牛客、招聘群")
        form.addRow("投递来源：", self.edit_source)

        self.edit_job_link = QLineEdit()
        self.edit_job_link.setPlaceholderText("岗位官网链接（建议与 JD 快照一起保存）")
        form.addRow("岗位链接：", self.edit_job_link)

        # JD 原文
        self.edit_jd = QTextEdit()
        self.edit_jd.setPlaceholderText("粘贴岗位描述（JD）原文...")
        self.edit_jd.setMaximumHeight(150)
        form.addRow("JD 原文：", self.edit_jd)

        layout.addLayout(form)

        # 确定/取消
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_browse(self):
        """选择简历文件"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择简历文件",
            "",
            "简历文件 (*.pdf *.docx);;所有文件 (*.*)",
        )
        if path:
            self._selected_file = path
            self.edit_file.setText(path)

    def _on_accept(self):
        """确认提交前的校验"""
        company = self.edit_company.text().strip()
        position = self.edit_position.text().strip()

        if not company or not position:
            QMessageBox.warning(self, "信息不完整", "公司名和岗位名为必填项。")
            return

        self._result_data = {
            "company_name": company,
            "position_name": position,
            "source_file": self._selected_file,
            "jd_text": self.edit_jd.toPlainText().strip(),
            "application_source": self.edit_source.text().strip(),
            "job_link": self.edit_job_link.text().strip(),
            "version_note": self.edit_version.text().strip(),
        }
        self.accept()

    def get_result(self):
        """获取表单数据（accept 后调用）"""
        return self._result_data

    @staticmethod
    def copy_file_to_resumes(source_path, company_name, position_name):
        """
        将源文件拷贝到 data/Resumes/ 目录，自动重命名为 公司_岗位_时间戳.扩展名
        返回相对路径，如 data/Resumes/字节跳动_后端_20260101_170101.pdf
        """
        if not source_path:
            return ""

        src = Path(source_path)
        dst_dir = paths.RESUMES_DIR
        dst_dir.mkdir(parents=True, exist_ok=True)

        # 自动重命名：公司_岗位_时间戳
        safe_company = "".join(c for c in company_name if c.isalnum() or c in " \u4e00-\u9fff").strip()
        safe_position = "".join(c for c in position_name if c.isalnum() or c in " \u4e00-\u9fff").strip()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = src.suffix.lower()
        new_name = f"{safe_company}_{safe_position}_{timestamp}{suffix}"

        dst = dst_dir / new_name
        shutil.copy2(str(src), str(dst))
        return f"data/Resumes/{dst.name}"
