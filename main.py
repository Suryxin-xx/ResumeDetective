"""
简历侦探（Resume Detective）—— 程序入口
首次运行自动创建 data/ 数据目录
"""

import sys

from PyQt6.QtWidgets import QApplication

import db_manager
import paths


def main():
    # 创建数据目录（data/ data/Resumes/）
    paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
    paths.RESUMES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[配置] 数据目录: {paths.DATA_DIR}")

    # 初始化数据库
    db_manager.init_db()
    print("[数据库] 初始化完成")

    # 启动主窗口
    app = QApplication(sys.argv)
    app.setApplicationName("ResumeDetective")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    # 延迟导入避免循环
    from main_window import MainWindow
    main()
