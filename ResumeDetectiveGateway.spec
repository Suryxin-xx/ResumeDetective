# -*- mode: python ; coding: utf-8 -*-
"""独立网页看板打包配置：生成可双击运行的单文件网关程序。"""

block_cipher = None

a = Analysis(
    ['gateway_main.py'], pathex=['.'], binaries=[], datas=[],
    hiddenimports=[
        'db_manager', 'config_manager', 'secure_store', 'paths', 'excel_sync',
        'local_gateway', 'file_ops', 'openpyxl', 'openpyxl.worksheet.table',
    ],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=['PyQt6'], noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='ResumeDetectiveGateway', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=True, disable_windowed_traceback=False,
)
