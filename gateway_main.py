"""独立网页看板入口：不启动 PyQt 桌面窗口。"""

import signal
import os
import sys
import time
import webbrowser

import db_manager
import local_gateway
import paths
from excel_sync import sync_application_workbook


def main():
    paths.migrate_legacy_data_if_needed()
    paths.ensure_data_directories()
    db_manager.init_db()
    try:
        sync_application_workbook()
    except OSError as exc:
        print(f"Excel 镜像正在被占用，本次未更新：{exc}")
    try:
        url = local_gateway.start_gateway()
    except OSError as exc:
        print(f"无法启动网页看板。地址 {local_gateway.get_url()} 已被占用。\n{exc}")
        return 1
    print("Resume Detective 网页看板已启动（不含桌面窗口）。")
    print(f"访问地址：{url}")
    print("按 Ctrl+C 可停止网页看板。")
    if os.environ.get("RESUME_DETECTIVE_NO_BROWSER") != "1":
        webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止网页看板…")
    finally:
        local_gateway.stop_gateway()
    return 0


if __name__ == "__main__":
    sys.exit(main())
