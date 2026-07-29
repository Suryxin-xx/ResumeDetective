"""独立网页工作台入口：后台运行，并通过 Windows 系统托盘管理。"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import webbrowser

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QStyle, QSystemTrayIcon

import db_manager
import local_gateway
import paths
from excel_sync import sync_application_workbook


def _arguments():
    parser = argparse.ArgumentParser(description="Resume Detective 本地网页工作台")
    parser.add_argument("--silent", action="store_true", help="启动后不自动打开浏览器")
    parser.add_argument("--port", type=int, help="仅本次运行使用指定端口")
    return parser.parse_args()


def _prepare_data():
    paths.migrate_legacy_data_if_needed()
    paths.ensure_data_directories()
    db_manager.init_db()
    try:
        sync_application_workbook()
    except OSError:
        # Excel 正在打开时保留数据库更新，下次同步会补写镜像。
        pass


def _open_browser(url: str):
    webbrowser.open(url)


def main():
    args = _arguments()
    app = QApplication(sys.argv)
    app.setApplicationName("Resume Detective Gateway")
    app.setQuitOnLastWindowClosed(False)

    try:
        _prepare_data()
        url = local_gateway.start_gateway(args.port)
    except Exception as exc:
        QMessageBox.critical(
            None,
            "网页工作台启动失败",
            f"无法启动本地网页工作台。\n\n{exc}",
        )
        return 1

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.warning(
            None,
            "系统托盘不可用",
            f"网页工作台已启动：{url}\n\n当前系统无法显示托盘图标，关闭此提示后程序将退出。",
        )
        local_gateway.stop_gateway()
        return 1

    icon = app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip(f"Resume Detective 网页工作台\n{url}")

    menu = QMenu()
    address_action = QAction(url, menu)
    address_action.setEnabled(False)
    menu.addAction(address_action)
    open_action = QAction("打开网页工作台", menu)
    open_action.triggered.connect(lambda: _open_browser(url))
    menu.addAction(open_action)
    menu.addSeparator()
    quit_action = QAction("退出网页工作台", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: _open_browser(url)
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        )
        else None
    )
    tray.show()
    tray.showMessage(
        "Resume Detective",
        f"网页工作台正在后台运行\n{url}",
        QSystemTrayIcon.MessageIcon.Information,
        3500,
    )

    app.aboutToQuit.connect(local_gateway.stop_gateway)
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(1000)

    no_browser = args.silent or os.environ.get("RESUME_DETECTIVE_NO_BROWSER") == "1"
    if not no_browser:
        QTimer.singleShot(250, lambda: _open_browser(url))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
