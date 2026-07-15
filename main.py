"""
简历侦探（Resume Detective）—— 程序入口
首次运行自动创建 data/ 数据目录
"""

import sys

from PyQt6.QtWidgets import QApplication

import db_manager
import paths
import local_gateway
from excel_sync import sync_application_workbook


def main():
    # 创建数据目录（data/ data/Resumes/）
    paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
    paths.RESUMES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[配置] 数据目录: {paths.DATA_DIR}")

    # 初始化数据库
    db_manager.init_db()
    print("[数据库] 初始化完成")
    try:
        sync_application_workbook()
        print(f"[Excel 镜像] 已更新: {paths.APPLICATION_MIRROR_FILE}")
    except OSError as exc:
        print(f"[Excel 镜像] 未更新（文件可能正在打开）: {exc}")
    try:
        gateway_url = local_gateway.start_gateway()
        print(f"[本地看板] 已启动: {gateway_url}")
    except OSError as exc:
        # 端口可能已被旧实例占用；桌面端不应因此无法启动。
        print(f"[本地看板] 未启动: {exc}")

    # 启动主窗口
    app = QApplication(sys.argv)
    app.setApplicationName("ResumeDetective")
    window = MainWindow()
    window.show()
    exit_code = app.exec()
    local_gateway.stop_gateway()
    sys.exit(exit_code)


if __name__ == "__main__":
    # 延迟导入避免循环
    from main_window import MainWindow
    main()
