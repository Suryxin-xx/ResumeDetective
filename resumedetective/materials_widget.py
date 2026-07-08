"""
个人资料库组件
管理经历碎片的增删改查、筛选、导入导出
支持时间范围、类型/标签筛选
新增个人信息编辑模块
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QTextEdit, QLineEdit, QComboBox,
    QFormLayout, QGroupBox, QSplitter, QMessageBox, QDialog,
    QDialogButtonBox, QDateEdit, QFileDialog, QStackedWidget,
)
from PyQt6.QtCore import Qt, QSize, QDate, QTimer

from . import db_manager
from . import paths


class MaterialEditDialog(QDialog):
    """新增/编辑经历碎片"""

    def __init__(self, parent=None, material=None):
        super().__init__(parent)
        self.setWindowTitle("编辑经历碎片" if material else "新增经历碎片")
        self.resize(520, 480)
        self._material = material
        self._setup_ui()
        if material:
            self._load_data(material)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_type = QComboBox()
        self.combo_type.setEditable(True)
        self.combo_type.addItems(["项目经历", "实习经历", "获奖经历", "科研项目",
                                   "竞赛经历", "学生工作", "志愿活动", "技能证书"])
        self.combo_type.setCurrentText("项目经历")
        form.addRow("类型：", self.combo_type)

        self.edit_title = QLineEdit()
        self.edit_title.setPlaceholderText("标题（如：智能推荐系统）")
        form.addRow("标题：", self.edit_title)

        self.edit_tags = QLineEdit()
        self.edit_tags.setPlaceholderText("标签，逗号分隔")
        form.addRow("标签：", self.edit_tags)

        # 起止时间
        date_layout = QHBoxLayout()
        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDate(QDate.currentDate())
        self.date_start.setSpecialValueText("不限")
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        date_layout.addWidget(QLabel("开始："))
        date_layout.addWidget(self.date_start)
        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDate(QDate.currentDate())
        self.date_end.setSpecialValueText("至今")
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        date_layout.addWidget(QLabel("结束："))
        date_layout.addWidget(self.date_end)
        form.addRow("时间：", date_layout)

        self.edit_content = QTextEdit()
        self.edit_content.setPlaceholderText("详细描述...")
        form.addRow("内容：", self.edit_content)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_data(self, m):
        self.combo_type.setEditText(m.get("material_type", ""))
        self.edit_title.setText(m.get("title", ""))
        self.edit_tags.setText(m.get("tags", ""))
        st = m.get("start_time", "")
        if st:
            try:
                self.date_start.setDate(QDate.fromString(st, "yyyy-MM-dd"))
            except Exception:
                pass
        et = m.get("end_time", "")
        if et:
            try:
                self.date_end.setDate(QDate.fromString(et, "yyyy-MM-dd"))
            except Exception:
                pass
        self.edit_content.setText(m.get("content", ""))

    def _on_accept(self):
        if not self.edit_title.text().strip() and not self.edit_content.toPlainText().strip():
            QMessageBox.warning(self, "信息不完整", "标题和内容至少填一项。")
            return
        self.accept()

    def get_data(self):
        st = self.date_start.date().toString("yyyy-MM-dd")
        et = self.date_end.date().toString("yyyy-MM-dd")
        return {
            "material_type": self.combo_type.currentText(),
            "title": self.edit_title.text().strip(),
            "content": self.edit_content.toPlainText().strip(),
            "tags": self.edit_tags.text().strip(),
            "start_time": st,
            "end_time": et,
        }


class MaterialsWidget(QWidget):
    """资料库主组件（含经历碎片 + 个人信息两个子页面）"""

    MATERIAL_TYPES = ["全部", "项目经历", "实习经历", "获奖经历", "科研项目",
                      "竞赛经历", "学生工作", "志愿活动", "技能证书"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._on_search_timeout)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ── 顶部页签切换 ──
        section_bar = QHBoxLayout()
        section_bar.setContentsMargins(4, 4, 4, 0)
        self.btn_section_materials = QPushButton("📋 经历碎片")
        self.btn_section_materials.setFixedHeight(32)
        self.btn_section_materials.setStyleSheet(
            "font-weight:bold;font-size:13px;padding:4px 20px;"
            "border:1px solid #BDBDBD;border-radius:4px;background:#E3F2FD;")
        self.btn_section_materials.clicked.connect(lambda: self._switch_section(0))
        section_bar.addWidget(self.btn_section_materials)
        self.btn_section_profile = QPushButton("👤 个人信息")
        self.btn_section_profile.setFixedHeight(32)
        self.btn_section_profile.setStyleSheet(
            "font-weight:normal;font-size:13px;padding:4px 20px;"
            "border:1px solid #BDBDBD;border-radius:4px;background:#FAFAFA;")
        self.btn_section_profile.clicked.connect(lambda: self._switch_section(1))
        section_bar.addWidget(self.btn_section_profile)
        section_bar.addStretch()
        layout.addLayout(section_bar)

        # ── 内容区：QStackedWidget ──
        self.stack = QStackedWidget()

        # 页面 0：经历碎片
        self._page_materials = QWidget()
        self._setup_materials_page()
        self.stack.addWidget(self._page_materials)

        # 页面 1：个人信息
        self._page_profile = QWidget()
        self._setup_profile_page()
        self.stack.addWidget(self._page_profile)

        layout.addWidget(self.stack, stretch=1)

    def _switch_section(self, index):
        self.stack.setCurrentIndex(index)
        # 更新按钮样式
        mats_style = (
            "font-weight:bold;font-size:13px;padding:4px 20px;"
            "border:1px solid #BDBDBD;border-radius:4px;background:#E3F2FD;"
            if index == 0 else
            "font-weight:normal;font-size:13px;padding:4px 20px;"
            "border:1px solid #BDBDBD;border-radius:4px;background:#FAFAFA;"
        )
        prof_style = (
            "font-weight:bold;font-size:13px;padding:4px 20px;"
            "border:1px solid #BDBDBD;border-radius:4px;background:#E3F2FD;"
            if index == 1 else
            "font-weight:normal;font-size:13px;padding:4px 20px;"
            "border:1px solid #BDBDBD;border-radius:4px;background:#FAFAFA;"
        )
        self.btn_section_materials.setStyleSheet(mats_style)
        self.btn_section_profile.setStyleSheet(prof_style)
        if index == 0:
            self.refresh()
        elif index == 1:
            self._load_profile()

    # ════════════════════════════════════════════
    # 经历碎片页面
    # ════════════════════════════════════════════

    def _setup_materials_page(self):
        layout = QVBoxLayout(self._page_materials)

        # ── 顶部按钮栏 ──
        top_bar = QHBoxLayout()
        self.btn_add = QPushButton("＋ 新建")
        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit = QPushButton("✏ 编辑")
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_delete = QPushButton("🗑 删除")
        self.btn_delete.clicked.connect(self._on_delete)
        top_bar.addWidget(self.btn_add)
        top_bar.addWidget(self.btn_edit)
        top_bar.addWidget(self.btn_delete)
        self.lbl_count = QLabel("0 条")
        self.lbl_count.setStyleSheet("color:#666;padding-left:8px;")

        self.btn_refresh = QPushButton("🔄 刷新")
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_import_md = QPushButton("📄 导入MD")
        self.btn_import_md.clicked.connect(self._on_import_md)
        self.btn_import_xlsx = QPushButton("📥 导入Excel")
        self.btn_import_xlsx.clicked.connect(self._on_import_xlsx)
        self.btn_export_xlsx = QPushButton("📤 导出Excel")
        self.btn_export_xlsx.clicked.connect(self._on_export_xlsx)
        self.btn_template = QPushButton("📄 模板")
        self.btn_template.clicked.connect(self._on_template)
        top_bar.addWidget(self.btn_refresh)
        top_bar.addWidget(self.btn_import_md)
        top_bar.addWidget(self.btn_import_xlsx)
        top_bar.addWidget(self.btn_export_xlsx)
        top_bar.addWidget(self.btn_template)
        top_bar.addStretch()
        top_bar.addWidget(self.lbl_count)
        layout.addLayout(top_bar)

        # ── 筛选栏 ──
        filter_bar = QHBoxLayout()
        self.filter_type = QComboBox()
        self.filter_type.addItems(self.MATERIAL_TYPES)
        self.filter_type.currentTextChanged.connect(lambda _: self.refresh())
        filter_bar.addWidget(QLabel("类型："))
        filter_bar.addWidget(self.filter_type)

        self.filter_keyword = QLineEdit()
        self.filter_keyword.setPlaceholderText("搜索标题/内容/标签...")
        self.filter_keyword.textChanged.connect(lambda _: self._search_timer.start(300))
        self.filter_keyword.returnPressed.connect(self.refresh)
        filter_bar.addWidget(self.filter_keyword, stretch=1)

        btn_search = QPushButton("🔍 搜索")
        btn_search.clicked.connect(self.refresh)
        filter_bar.addWidget(btn_search)
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self._clear_filters)
        filter_bar.addWidget(btn_clear)
        layout.addLayout(filter_bar)

        # ── 列表 + 预览 ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.list_widget = QListWidget()
        self.list_widget.setMinimumWidth(200)
        self.list_widget.currentRowChanged.connect(self._on_selection_changed)
        self.list_widget.itemDoubleClicked.connect(lambda _: self._on_edit())
        splitter.addWidget(self.list_widget)

        preview = QWidget()
        preview_layout = QVBoxLayout(preview)
        self.preview_title = QLabel("未选中资料")
        self.preview_title.setStyleSheet("font-size:16px;font-weight:bold;color:#222;")
        self.preview_meta = QLabel("类型 / 时间 / 标签")
        self.preview_meta.setStyleSheet("color:#666;")
        self.preview_content = QTextEdit()
        self.preview_content.setReadOnly(True)
        self.preview_content.setPlaceholderText("选中左侧资料后查看完整内容。双击左侧条目可直接编辑。")
        for w in (self.preview_title, self.preview_meta):
            w.setWordWrap(True)
        preview_layout.addWidget(self.preview_title)
        preview_layout.addWidget(self.preview_meta)
        preview_layout.addWidget(self.preview_content, stretch=1)
        splitter.addWidget(preview)
        splitter.setSizes([280, 520])
        layout.addWidget(splitter, stretch=1)

    def _on_search_timeout(self):
        self.refresh()

    def refresh(self):
        """按筛选条件重新加载经历碎片列表"""
        if self.stack.currentIndex() != 0:
            return
        self.list_widget.clear()
        mtype = self.filter_type.currentText()
        kw = self.filter_keyword.text().strip()
        mt = mtype if mtype != "全部" else ""
        materials = db_manager.get_materials_filtered(material_type=mt, keyword=kw)
        self._materials_data = materials
        self.lbl_count.setText(f"{len(materials)} 条")
        for m in materials:
            text = m['title'] or '(无标题)'
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, m["id"])
            meta = f"{m.get('material_type','')} | {m.get('start_time','')} ~ {m.get('end_time','')} | {m.get('tags','')}"
            item.setToolTip(meta)
            item.setSizeHint(QSize(220, 42))
            self.list_widget.addItem(item)
        if not materials:
            self._clear_preview()

    def _on_selection_changed(self, index):
        item = self.list_widget.currentItem()
        if item is None:
            return
        mid = item.data(Qt.ItemDataRole.UserRole)
        for m in self._materials_data:
            if m["id"] == mid:
                self.preview_title.setText(m['title'] or "(无标题)")
                st, et = m.get("start_time", ""), m.get("end_time", "")
                time_text = f"{st} ~ {et}" if st or et else "时间未填写"
                tags = m.get("tags", "") or "无标签"
                self.preview_meta.setText(f"{m['material_type']} | {time_text} | {tags}")
                self.preview_content.setText(m["content"])
                break

    def _clear_preview(self):
        self.preview_title.setText("未选中资料")
        self.preview_meta.setText("类型 / 时间 / 标签")
        self.preview_content.clear()

    def _clear_filters(self):
        self.filter_type.setCurrentText("全部")
        self.filter_keyword.clear()
        self.refresh()

    def _get_selected_id(self):
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _get_selected_data(self):
        mid = self._get_selected_id()
        if mid is None:
            return None
        for m in self._materials_data:
            if m["id"] == mid:
                return m
        return None

    def _on_add(self):
        dialog = MaterialEditDialog(self)
        if dialog.exec() == MaterialEditDialog.DialogCode.Accepted:
            db_manager.add_material(**dialog.get_data())
            self.refresh()

    def _on_edit(self):
        m = self._get_selected_data()
        if m is None:
            QMessageBox.information(self, "提示", "请先选中一条记录。")
            return
        dialog = MaterialEditDialog(self, m)
        if dialog.exec() == MaterialEditDialog.DialogCode.Accepted:
            data = dialog.get_data()
            db_manager.update_material(m["id"], **data)
            self.refresh()

    def _on_delete(self):
        mid = self._get_selected_id()
        if mid is None:
            QMessageBox.information(self, "提示", "请先选中一条记录。")
            return
        if QMessageBox.question(self, "确认删除", "确定删除这条经历碎片？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            db_manager.delete_material(mid)
            self.refresh()
            self._clear_preview()

    def _on_import_md(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 Markdown 文件", "", "Markdown (*.md)")
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        lines = text.strip().split("\n")
        title, content_lines, tags_parts = "", [], []
        for line in lines:
            s = line.strip()
            if s.startswith("# ") and not title:
                title = s[2:].strip()
            elif s.startswith("## "):
                tags_parts.append(s[3:].strip())
                content_lines.append(f"【{s[3:].strip()}】")
            else:
                content_lines.append(line)
            if "|" in s and s.startswith("|"):
                for c in [c.strip() for c in s.split("|") if c.strip()]:
                    if "：" in c:
                        tags_parts.append(c.split("：")[-1].strip())
        if not title:
            from pathlib import Path
            title = Path(path).stem
        tags = ",".join(dict.fromkeys(tags_parts))[:200]

        mid = db_manager.add_material("项目经历", title, "\n".join(content_lines).strip(), tags)
        # 自动弹出编辑
        m = db_manager.get_all_materials()
        m = next((x for x in m if x["id"] == mid), None)
        if m:
            dialog = MaterialEditDialog(self, m)
            if dialog.exec() == MaterialEditDialog.DialogCode.Accepted:
                db_manager.update_material(mid, **dialog.get_data())
        self.refresh()

    def _on_import_xlsx(self):
        from io_export import import_materials_xlsx
        path, _ = QFileDialog.getOpenFileName(self, "选择导入文件", "", "Excel (*.xlsx)")
        if not path:
            return
        count = import_materials_xlsx(path)
        if count > 0:
            QMessageBox.information(self, "导入完成", f"成功导入 {count} 条经历。\n可在列表中选中编辑。")
            self.refresh()
        else:
            QMessageBox.warning(self, "导入失败", "未能导入任何记录，请检查文件格式。")

    def _on_export_xlsx(self):
        from io_export import export_materials_xlsx
        path, _ = QFileDialog.getSaveFileName(self, "导出经历数据",
            str(paths.DATA_DIR / "经历碎片.xlsx"), "Excel (*.xlsx)")
        if not path:
            return
        count = export_materials_xlsx(path)
        QMessageBox.information(self, "导出完成", f"已导出 {count} 条经历。")

    def _on_template(self):
        from io_export import generate_materials_template
        path, _ = QFileDialog.getSaveFileName(self, "保存导入模板",
            str(paths.DATA_DIR / "经历碎片模板.xlsx"), "Excel (*.xlsx)")
        if not path:
            return
        generate_materials_template(path)
        QMessageBox.information(self, "模板已生成",
            f"导入模板已保存到：{path}\n\n"
            "格式说明：类型|标题|内容|标签|开始时间|结束时间\n"
            "类型可选：项目经历/实习经历/获奖经历/科研项目/竞赛经历/学生工作/志愿活动/技能证书\n"
            "时间为 yyyy-MM-dd 格式")

    # ════════════════════════════════════════════
    # 个人信息页面
    # ════════════════════════════════════════════

    def _setup_profile_page(self):
        layout = QVBoxLayout(self._page_profile)
        layout.setContentsMargins(12, 8, 12, 8)

        # 标题
        title = QLabel("👤 个人信息")
        title.setStyleSheet("font-size:16px;font-weight:bold;color:#222;margin-bottom:4px;")
        layout.addWidget(title)
        desc = QLabel("这些信息将用于简历生成和 AI 问答，与「经历碎片」分开管理。")
        desc.setStyleSheet("color:#888;font-size:12px;margin-bottom:8px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 表单
        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.p_full_name = QLineEdit()
        self.p_full_name.setPlaceholderText("姓名")
        form.addRow("姓名：", self.p_full_name)

        self.p_gender = QComboBox()
        self.p_gender.addItems(["", "男", "女", "其他"])
        form.addRow("性别：", self.p_gender)

        self.p_birth = QLineEdit()
        self.p_birth.setPlaceholderText("如：2000-01")
        form.addRow("出生年月：", self.p_birth)

        self.p_phone = QLineEdit()
        self.p_phone.setPlaceholderText("手机号")
        form.addRow("电话：", self.p_phone)

        self.p_email = QLineEdit()
        self.p_email.setPlaceholderText("邮箱")
        form.addRow("邮箱：", self.p_email)

        self.p_city = QLineEdit()
        self.p_city.setPlaceholderText("所在城市")
        form.addRow("城市：", self.p_city)

        self.p_education = QComboBox()
        self.p_education.addItems(["", "高中", "大专", "本科", "硕士", "博士", "MBA"])
        form.addRow("最高学历：", self.p_education)

        self.p_school = QLineEdit()
        self.p_school.setPlaceholderText("毕业院校")
        form.addRow("学校：", self.p_school)

        self.p_major = QLineEdit()
        self.p_major.setPlaceholderText("专业")
        form.addRow("专业：", self.p_major)

        self.p_target = QLineEdit()
        self.p_target.setPlaceholderText("如：后端开发 / 产品经理")
        form.addRow("求职方向：", self.p_target)

        self.p_github = QLineEdit()
        self.p_github.setPlaceholderText("GitHub 链接（可选）")
        form.addRow("GitHub：", self.p_github)

        self.p_portfolio = QLineEdit()
        self.p_portfolio.setPlaceholderText("作品集链接（可选）")
        form.addRow("作品集：", self.p_portfolio)

        self.p_summary = QTextEdit()
        self.p_summary.setPlaceholderText("个人总结/自我介绍（可选）")
        self.p_summary.setMaximumHeight(120)
        form.addRow("个人总结：", self.p_summary)

        layout.addLayout(form)

        # 保存按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_save_profile = QPushButton("💾 保存个人信息")
        self.btn_save_profile.setFixedHeight(36)
        self.btn_save_profile.setStyleSheet("font-weight:bold;font-size:13px;padding:4px 24px;")
        self.btn_save_profile.clicked.connect(self._on_save_profile)
        btn_row.addWidget(self.btn_save_profile)
        layout.addLayout(btn_row)

        layout.addStretch()

    def _load_profile(self):
        """加载个人信息到表单"""
        data = db_manager.get_profile()
        if data is None:
            self._clear_profile_form()
            return
        self.p_full_name.setText(data.get("full_name", ""))
        gender = data.get("gender", "")
        idx = self.p_gender.findText(gender)
        self.p_gender.setCurrentIndex(max(idx, 0))
        self.p_birth.setText(data.get("birth_date", ""))
        self.p_phone.setText(data.get("phone", ""))
        self.p_email.setText(data.get("email", ""))
        self.p_city.setText(data.get("city", ""))
        edu = data.get("education", "")
        idx2 = self.p_education.findText(edu)
        self.p_education.setCurrentIndex(max(idx2, 0))
        self.p_school.setText(data.get("school", ""))
        self.p_major.setText(data.get("major", ""))
        self.p_target.setText(data.get("target_role", ""))
        self.p_github.setText(data.get("github_url", ""))
        self.p_portfolio.setText(data.get("portfolio_url", ""))
        self.p_summary.setText(data.get("summary", ""))

    def _clear_profile_form(self):
        self.p_full_name.clear()
        self.p_gender.setCurrentIndex(0)
        self.p_birth.clear()
        self.p_phone.clear()
        self.p_email.clear()
        self.p_city.clear()
        self.p_education.setCurrentIndex(0)
        self.p_school.clear()
        self.p_major.clear()
        self.p_target.clear()
        self.p_github.clear()
        self.p_portfolio.clear()
        self.p_summary.clear()

    def _on_save_profile(self):
        """保存个人信息"""
        data = {
            "full_name": self.p_full_name.text().strip(),
            "gender": self.p_gender.currentText(),
            "birth_date": self.p_birth.text().strip(),
            "phone": self.p_phone.text().strip(),
            "email": self.p_email.text().strip(),
            "city": self.p_city.text().strip(),
            "education": self.p_education.currentText(),
            "school": self.p_school.text().strip(),
            "major": self.p_major.text().strip(),
            "target_role": self.p_target.text().strip(),
            "summary": self.p_summary.toPlainText().strip(),
            "github_url": self.p_github.text().strip(),
            "portfolio_url": self.p_portfolio.text().strip(),
        }
        db_manager.save_profile(data)
        QMessageBox.information(self, "保存成功", "个人信息已保存。")
