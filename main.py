"""Resume Detective 统一程序入口。

默认启动桌面应用；传入 ``--gateway`` 时，使用同一个可执行文件启动
独立网页工作台。两个模式共享同一套 PyInstaller 运行时，避免重复打包。
"""

import sys

from PyQt6.QtWidgets import QApplication

import db_manager
from gateway_instance import GatewayControlBridge, GatewayInstance
import paths
import local_gateway
import config_manager
from excel_sync import sync_application_workbook

GATEWAY_FLAG = "--gateway"


def _desktop_main():
    from main_window import MainWindow

    migrated, migration_message = paths.migrate_legacy_data_if_needed()
    if migrated:
        print(f"[数据迁移] {migration_message}")
    paths.ensure_data_directories()
    print(f"[配置] 数据目录: {paths.DATA_DIR}")

    app = QApplication(sys.argv)
    app.setApplicationName("ResumeDetective")

    # 初始化数据库
    db_manager.init_db()
    print("[数据库] 初始化完成")
    try:
        sync_application_workbook()
        print(f"[Excel 镜像] 已更新: {paths.APPLICATION_MIRROR_FILE}")
    except OSError as exc:
        print(f"[Excel 镜像] 未更新（文件可能正在打开）: {exc}")
    gateway_instance = GatewayInstance()
    owns_gateway = gateway_instance.try_acquire()
    gateway_state = {"owned": owns_gateway}
    if owns_gateway:
        def control_gateway(action: str):
            if action == "shutdown":
                local_gateway.stop_gateway()
                local_gateway.set_control_handler(None)
                local_gateway.set_address_handler(None)
                gateway_instance.release()
                gateway_state["owned"] = False
            else:
                local_gateway.restart_gateway(
                    config_manager.get_gateway_port(), force=True
                )

        control_bridge = GatewayControlBridge(control_gateway, app)
        local_gateway.set_control_handler(control_bridge.submit)
        local_gateway.set_address_handler(gateway_instance.publish)
        try:
            gateway_url = local_gateway.start_gateway()
            print(f"[本地看板] 已启动: {gateway_url}")
        except OSError as exc:
            # 端口可能被其他程序占用；桌面端不应因此无法启动。
            print(f"[本地看板] 未启动: {exc}")
            local_gateway.set_control_handler(None)
            local_gateway.set_address_handler(None)
            gateway_instance.release()
            owns_gateway = False
            gateway_state["owned"] = False
    else:
        print("[本地看板] 已有实例正在运行，桌面端不再重复启动")

    # 启动主窗口
    window = MainWindow()
    window.show()
    exit_code = app.exec()
    if gateway_state["owned"]:
        local_gateway.stop_gateway()
        local_gateway.set_control_handler(None)
        local_gateway.set_address_handler(None)
        gateway_instance.release()
    return exit_code


def _gateway_main():
    # gateway_main 自己使用 argparse；转交前移除统一入口专用参数。
    sys.argv = [sys.argv[0], *(arg for arg in sys.argv[1:] if arg != GATEWAY_FLAG)]
    from gateway_main import main as run_gateway

    return run_gateway()


def main():
    if GATEWAY_FLAG in sys.argv[1:]:
        return _gateway_main()
    return _desktop_main()


if __name__ == "__main__":
    sys.exit(main())
