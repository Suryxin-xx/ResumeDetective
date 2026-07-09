"""
泳道看板组件
7 列状态泳道，支持鼠标拖拽卡片切换状态
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QPushButton,
    QAbstractItemView,
    QStackedWidget,
    QLineEdit,
    QComboBox,
)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QColor

import db_manager
from table_view import TableView

# 7 个状态定义
STATUS_LIST = [
    "已投递",
    "简历初筛",
    "笔试/无笔试",
    "业务面试",
    "HR面",
    "Offer",
    "终止",
]

# 各状态对应的颜色（浅色背景）
STATUS_COLORS = {
    "已投递": QColor("#E3F2FD"),       # 浅蓝
    "简历初筛": QColor("#FFF3E0"),      # 浅橙
    "笔试/无笔试": QColor("#F3E5F5"),   # 浅紫
    "业务面试": QColor("#E8F5E9"),      # 浅绿
    "HR面": QColor("#E0F7FA"),          # 浅青
    "Offer": QColor("#FFEBEE"),         # 浅红（喜庆）
    "终止": QColor("#ECEFF1"),          # 浅灰
}

STATUS_HEADER_COLORS = {
    "已投递": QColor("#BBDEFB"),
    "简历初筛": QColor("#FFE0B2"),
    "笔试/无笔试": QColor("#E1BEE7"),
    "业务面试": QColor("#C8E6C9"),
    "HR面": QColor("#B2EBF2"),
    "Offer": QColor("#FFCDD2"),
    "终止": QColor("#CFD8DC"),
}


class DropListWidget(QListWidget):
    """支持拖放的自定义 QListWidget"""

    card_clicked = pyqtSignal(int)     # app_id — 双击时发射
    card_focused = pyqtSignal(int)     # app_id — 单击选中时发射
    status_changed = pyqtSignal(int, str)  # app_id, new_status — 拖放完成后发射

    def __init__(self, status, parent=None):
        super().__init__(parent)
        self._status = status
        self._normal_border = "1px solid #ccc"
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSpacing(2)
        self.setMinimumWidth(160)
        self.installEventFilter(self)

    def dragMoveEvent(self, event):
        """允许所有拖入；悬停时高亮边框"""
        self.setStyleSheet(
            self.styleSheet().replace(self._normal_border, "2px solid #1976D2")
            if self._normal_border in self.styleSheet()
            else self.styleSheet()
        )
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        """拖拽离开时恢复边框"""
        self.setStyleSheet(
            self.styleSheet().replace("2px solid #1976D2", self._normal_border)
        )
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        """拖放完成后更新数据库，拒绝 super().dropEvent() 避免 Qt 默认复制行为"""
        source = event.source()
        if not isinstance(source, DropListWidget):
            event.ignore()
            return

        item = source.currentItem()
        if item is None:
            event.ignore()
            return

        app_id = item.data(Qt.ItemDataRole.UserRole)
        if app_id is None:
            event.ignore()
            return

        new_status = self._status
        db_manager.update_application_status(app_id, new_status)

        # 恢复默认边框
        self.setStyleSheet(
            self.styleSheet().replace("2px solid #1976D2", self._normal_border)
        )

        event.acceptProposedAction()

        # 整个界面从数据库重新加载，避免 Qt 默认复制 + refresh 竞态导致双卡片
        self.status_changed.emit(app_id, new_status)

    def mousePressEvent(self, event):
        """单击选中（高亮 + 通知上层更新上下文）"""
        super().mousePressEvent(event)
        item = self.itemAt(event.position().toPoint())
        if item:
            app_id = item.data(Qt.ItemDataRole.UserRole)
            if app_id is not None:
                self.card_focused.emit(app_id)

    def mouseDoubleClickEvent(self, event):
        """双击打开详情弹窗"""
        item = self.itemAt(event.position().toPoint())
        if item:
            app_id = item.data(Qt.ItemDataRole.UserRole)
            if app_id is not None:
                self.card_clicked.emit(app_id)
        super().mouseDoubleClickEvent(event)


class CardItem(QListWidgetItem):
    """自定义看板卡片（显示优先级 + 公司名 + 岗位名）"""
    def __init__(self, company_name, position_name, app_id, priority=0, city=""):
        stars = "★" * priority if priority else ""
        prefix = f"{stars} " if stars else ""
        display = f"{prefix}{company_name}\n{position_name}"
        super().__init__(display)
        self.setSizeHint(QSize(140, 58))
        self.setData(Qt.ItemDataRole.UserRole, app_id)
        tip_parts = []
        if priority:
            tip_parts.append(f"{'★'*priority}")
        tip_parts.append(f"{company_name} - {position_name}")
        if city:
            tip_parts.append(f"📍 {city}")
        self.setToolTip(" | ".join(tip_parts))
        # 单行省略：启用自动换行并固定宽度
        self.setTextAlignment(Qt.AlignmentFlag.AlignCenter)


class BoardWidget(QWidget):
    """泳道看板主组件（支持泳道/表格双模式切换）"""

    card_selected = pyqtSignal(int)  # app_id — 双击详情
    card_focused = pyqtSignal(int)   # app_id — 单击选中

    def __init__(self, parent=None):
        super().__init__(parent)
        self._columns = {}  # status -> {'list': DropListWidget, 'header': QLabel}
        self._view_mode = "kanban"
        self._filter_kw = ""
        self._filter_status = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # ── 顶部操作栏（精简：视图切换 + 统计）──
        top_bar = QHBoxLayout()
        top_bar.addStretch()

        # 仪表盘统计
        self.label_total = QLabel("总投递: 0")
        self.label_interview = QLabel("面试中: 0")
        self.label_offer = QLabel("Offer: 0")
        for lbl in (self.label_total, self.label_interview, self.label_offer):
            lbl.setStyleSheet("padding: 4px 12px; font-weight: bold;")
        top_bar.addWidget(self.label_total)
        top_bar.addWidget(self.label_interview)
        top_bar.addWidget(self.label_offer)

        layout.addLayout(top_bar)

        # ── 搜索筛选栏 ──
        filter_bar = QHBoxLayout()
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("搜索公司/岗位...")
        self.filter_input.textChanged.connect(self._apply_filter)
        filter_bar.addWidget(self.filter_input, stretch=1)
        self.filter_status = QComboBox()
        self.filter_status.addItems(["全部状态", "已投递", "简历初筛", "笔试/无笔试",
                                      "业务面试", "HR面", "Offer", "终止"])
        self.filter_status.currentTextChanged.connect(lambda _: self._apply_filter())
        filter_bar.addWidget(QLabel("状态："))
        filter_bar.addWidget(self.filter_status)
        layout.addLayout(filter_bar)

        # ── 视图容器（泳道 / 表格） ──
        self.view_stack = QStackedWidget()

        # 泳道视图（原有看板）
        self._setup_kanban_view()

        # 表格视图
        self.table_view = TableView()
        self.table_view.card_selected.connect(self.card_selected.emit)
        self.view_stack.addWidget(self.table_view)

        layout.addWidget(self.view_stack, stretch=1)

    def _setup_kanban_view(self):
        """创建泳道看板视图"""
        kanban = QWidget()
        kanban_layout = QVBoxLayout(kanban)
        kanban_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        columns_widget = QWidget()
        self.columns_layout = QHBoxLayout(columns_widget)
        self.columns_layout.setSpacing(6)
        self.columns_layout.setContentsMargins(4, 0, 4, 0)

        for status in STATUS_LIST:
            col_widget = self._create_column(status)
            self.columns_layout.addWidget(col_widget)

        scroll.setWidget(columns_widget)
        kanban_layout.addWidget(scroll)
        self.view_stack.addWidget(kanban)

    def _create_column(self, status):
        """创建单列泳道"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        # 列标题（带计数占位）
        header = QLabel(f"{status} (0)")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setFixedHeight(32)
        header.setStyleSheet(
            f"background-color: {STATUS_HEADER_COLORS[status].name()};"
            f"font-weight: bold; border-radius: 4px; padding: 2px;"
        )
        layout.addWidget(header)

        # 卡片列表
        list_widget = DropListWidget(status, self)
        list_widget.setStyleSheet(
            f"background-color: {STATUS_COLORS[status].name()};"
            f"border: {list_widget._normal_border}; border-radius: 4px;"
        )
        # 转发信号
        list_widget.card_clicked.connect(self.card_selected.emit)
        list_widget.card_focused.connect(self.card_focused.emit)
        # 拖放后自动刷新看板
        list_widget.status_changed.connect(lambda *_: self.refresh())
        self._columns[status] = {"list": list_widget, "header": header}
        layout.addWidget(list_widget, stretch=1)

        return widget

    def refresh(self):
        """从数据库重新加载（应用筛选）"""
        try:
            apps = db_manager.get_applications_with_resume()
        except Exception as e:
            print("board refresh db error:", e)
            return

        # 客户端筛选
        kw = self._filter_kw
        fs = self._filter_status
        if kw or (fs and fs != "全部状态"):
            filtered = []
            for a in apps:
                if fs and fs != "全部状态" and a["current_status"] != fs:
                    continue
                if kw:
                    text = (a["company_name"] + a["position_name"]).lower()
                    if kw not in text:
                        continue
                filtered.append(a)
            apps = filtered

        # 刷新泳道
        for col in self._columns.values():
            col["list"].clear()
        counts = {s: 0 for s in STATUS_LIST}
        for app in apps:
            col = self._columns.get(app["current_status"])
            if col:
                counts[app["current_status"]] += 1
                item = CardItem(app["company_name"], app["position_name"], app["id"], app.get("priority", 0), app.get("city", ""))
                col["list"].addItem(item)

        # 添加排序按钮（每列加排序指示器）
        for st in STATUS_LIST:
            col = self._columns.get(st)
            if col:
                col["header"].setText(f"{st} ({counts[st]})")

        # 刷新表格
        self.table_view.refresh()

        # 更新顶部统计
        self._update_stats()

    def _update_stats(self):
        """更新顶部统计数字"""
        apps = db_manager.get_applications_with_resume()
        total = len(apps)
        interviewing = sum(
            1 for a in apps if a["current_status"] in ("业务面试", "HR面")
        )
        offers = sum(1 for a in apps if a["current_status"] == "Offer")
        self.label_total.setText(f"总投递: {total}")
        self.label_interview.setText(f"面试中: {interviewing}")
        self.label_offer.setText(f"Offer: {offers}")

    def _toggle_view(self):
        """切换表格/泳道视图"""
        if self._view_mode == "kanban":
            self._view_mode = "table"
            self.view_stack.setCurrentIndex(1)
            self.btn_toggle_view.setText("📋 泳道视图")
        else:
            self._view_mode = "kanban"
            self.view_stack.setCurrentIndex(0)
            self.btn_toggle_view.setText("📋 表格视图")

    def _apply_filter(self):
        """应用搜索/状态筛选"""
        self._filter_kw = self.filter_input.text().strip().lower()
        self._filter_status = self.filter_status.currentText()
        self.refresh()
