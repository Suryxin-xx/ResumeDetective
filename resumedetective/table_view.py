"""
表格视图 — 投递记录表格，支持排序、状态编辑、右键菜单
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QComboBox, QMenu, QMessageBox,
    QLineEdit, QPushButton, QLabel,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QAction

from . import db_manager

STATUS_COLORS = {
    "已投递": "#BBDEFB", "简历初筛": "#FFE0B2", "笔试/无笔试": "#E1BEE7",
    "业务面试": "#C8E6C9", "HR面": "#B2EBF2", "Offer": "#FFCDD2", "终止": "#CFD8DC",
}
STATUS_LIST = ["已投递", "简历初筛", "笔试/无笔试", "业务面试", "HR面", "Offer", "终止"]
HEADERS = ["#", "优先级", "公司", "岗位", "城市", "当前状态", "投递时间", "更新时间", "状态历史"]
COL_WIDTHS = [40, 100, 140, 140, 100, 120, 140, 140, 220]


class StatusDelegate:
    """辅助：双击状态列弹出编辑"""


class TableView(QWidget):
    """投递记录表格视图"""

    card_selected = pyqtSignal(int)  # app_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._apps_data = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 排序/筛选工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["默认(添加顺序)", "优先级(高→低)", "投递时间(最新)", "更新时间(最新)"])
        self.sort_combo.currentIndexChanged.connect(self._apply_sort)
        toolbar.addWidget(QLabel("排序："))
        toolbar.addWidget(self.sort_combo)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["全部状态"] + STATUS_LIST)
        self.filter_combo.currentIndexChanged.connect(self._apply_sort)
        toolbar.addWidget(QLabel("筛选："))
        toolbar.addWidget(self.filter_combo)
        toolbar.addStretch()

        layout.addLayout(toolbar)

        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(True)

        # 选中行样式（柔和蓝底 + 深色字，避免看不清）
        self.table.setStyleSheet("""
            QTableWidget::item:selected {
                background-color: #BBDEFB;
                color: #1a1a1a;
            }
            QTableWidget::item:hover {
                background-color: #E3F2FD;
            }
        """)

        # 列宽
        for i, w in enumerate(COL_WIDTHS):
            self.table.setColumnWidth(i, w)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        # 交互
        self.table.cellDoubleClicked.connect(self._on_cell_double_click)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)

        layout.addWidget(self.table)

    def refresh(self):
        """从数据库重新加载"""
        self._apps_data = db_manager.get_applications_with_resume()
        self._populate_table()

    def _populate_table(self):
        """填充表格数据（由 refresh 和 _apply_sort 复用）"""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for row, app in enumerate(self._apps_data):
            self.table.insertRow(row)

            # 序号
            self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))

            # 优先级
            pri = app.get("priority", 0)
            pi = QTableWidgetItem("★" * pri if pri else "")
            pi.setData(Qt.ItemDataRole.UserRole, app["id"])
            pi.setData(Qt.ItemDataRole.UserRole + 1, pri)
            pi.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, pi)

            self.table.setItem(row, 2, QTableWidgetItem(app["company_name"]))
            self.table.setItem(row, 3, QTableWidgetItem(app["position_name"]))
            self.table.setItem(row, 4, QTableWidgetItem(app.get("city", "")))

            status = app["current_status"]
            si = QTableWidgetItem(status)
            si.setBackground(QColor(STATUS_COLORS.get(status, "#ECEFF1")))
            si.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            si.setData(Qt.ItemDataRole.UserRole + 2, app["id"])
            self.table.setItem(row, 5, si)

            self.table.setItem(row, 6, QTableWidgetItem(app.get("upload_time", "")))
            self.table.setItem(row, 7, QTableWidgetItem(app.get("status_update_time", "")))

            history = app.get("status_history", "")
            if history:
                entries = history.strip().split("\n")
                short = "; ".join(
                    e.split(": ", 1)[-1] if ": " in e else e for e in entries[-3:]
                )
                hi = QTableWidgetItem(short)
                hi.setToolTip(history)
            else:
                hi = QTableWidgetItem("")
            self.table.setItem(row, 8, hi)

        self.table.setSortingEnabled(True)

    def _get_app_id(self, row):
        """从第 1 列（优先级）获取 app_id"""
        item = self.table.item(row, 1)
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _on_cell_double_click(self, row, col):
        """双击处理：状态列弹编辑，优先级列双击切换，其他列打开详情"""
        if col == 1:
            self._edit_priority(row)
        elif col == 5:
            self._edit_status(row)
        elif col not in (0, 1, 5):
            app_id = self._get_app_id(row)
            if app_id is not None:
                self.card_selected.emit(app_id)

    def _edit_status(self, row):
        """双击状态列：弹出 QComboBox 直接改状态"""
        app_id = self._get_app_id(row)
        if app_id is None:
            return

        current_item = self.table.item(row, 5)
        current = current_item.text() if current_item else ""
        combo = QComboBox()
        combo.addItems(STATUS_LIST)
        combo.setCurrentText(current)
        # 用 QMenu 作为弹出容器
        menu = QMenu(self.table)
        menu.setStyleSheet("QMenu { menu-width: 140px; }")
        action = QAction(f"  {current}  →  ", None)
        action.setDisabled(True)
        menu.addAction(action)
        menu.addSeparator()
        for s in STATUS_LIST:
            if s == current:
                continue
            a = QAction(f"  {s}  ", None)
            a.setData(s)
            a.triggered.connect(lambda checked, ns=s: self._do_change_status(app_id, row, ns))
            menu.addAction(a)
        # 显示在状态列位置
        cell_rect = self.table.visualRect(self.table.model().index(row, 5))
        menu.exec(self.table.viewport().mapToGlobal(cell_rect.bottomLeft()))

    def _do_change_status(self, app_id, row, new_status):
        """执行状态变更"""
        db_manager.update_application_status(app_id, new_status)
        self.refresh()

    def _edit_priority(self, row):
        """双击优先级列：循环切换 0-5"""
        app_id = self._get_app_id(row)
        if app_id is None:
            return
        item = self.table.item(row, 1)
        cur = item.data(Qt.ItemDataRole.UserRole + 1) or 0
        new_pri = (cur + 1) % 6  # 0→1→2→3→4→5→0
        db_manager.update_priority(app_id, new_pri)
        self.refresh()

    def _apply_sort(self):
        """根据排序/筛选条件刷新"""
        sort_idx = self.sort_combo.currentIndex()
        filter_status = self.filter_combo.currentText()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        apps = db_manager.get_applications_with_resume()

        # 筛选
        if filter_status and filter_status != "全部状态":
            apps = [a for a in apps if a["current_status"] == filter_status]

        # 排序
        if sort_idx == 1:
            apps.sort(key=lambda a: -(a.get("priority", 0) or 0))
        elif sort_idx == 2:
            apps.sort(key=lambda a: a.get("upload_time", "") or "", reverse=True)
        elif sort_idx == 3:
            apps.sort(key=lambda a: a.get("status_update_time", "") or "", reverse=True)

        self._apps_data = apps
        self._populate_table()
        self.table.setSortingEnabled(True)

    def _on_context_menu(self, pos):
        """右键菜单：删除、打开详情"""
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        app_id = self._get_app_id(row)
        if app_id is None:
            return
        menu = QMenu(self.table)
        act_detail = menu.addAction("📋 打开详情")
        act_detail.triggered.connect(lambda: self.card_selected.emit(app_id))
        menu.addSeparator()
        act_del = menu.addAction("🗑 删除此记录")
        act_del.triggered.connect(lambda: self._delete_row(app_id))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _delete_row(self, app_id):
        """删除行"""
        apps = db_manager.get_applications_with_resume()
        app = next((a for a in apps if a["id"] == app_id), None)
        if app is None:
            return
        reply = QMessageBox.question(
            self, "确认删除", f"确定删除 {app['company_name']} - {app['position_name']} 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            db_manager.delete_resume(app["resume_id"])
            self.refresh()
