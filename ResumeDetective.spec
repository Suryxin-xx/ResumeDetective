# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置
打包命令：pyinstaller ResumeDetective.spec
"""

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'config_manager',
        'db_manager',
        'models',
        'main_window',
        'board_widget',
        'table_view',
        'detail_dialog',
        'dialogs',
        'materials_widget',
        'ai_service',
        'cli_ai',
        'chat_history',
        'io_export',
        'paths',
        'tools_pdf2img',
        'tools_imgpdf',
        'job_targets_widget',
        'tasks_widget',
        'interviews_widget',
        'data_safety',
        'local_gateway',
        'gateway_main',
        'gateway_instance',
        'excel_sync',
        'secure_store',
        'file_ops',
        'PIL',
        'fitz',
        'openpyxl',
        'openpyxl.worksheet.table',
        'requests',
        'comtypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 当前功能不使用这些可选模块。显式排除可避免全局构建环境把它们
    # 连同大体积二进制依赖一起收集；对应PDF/Excel功能由自动化测试覆盖。
    excludes=[
        'numpy',
        'numpy.core',
        'numpy._core',
        'docx',
        'lxml',
        'PyQt6.QtPdf',
        'PyQt6.QtPdfWidgets',
        'PIL.AvifImagePlugin',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ResumeDetective',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='file_version_info.txt',
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ResumeDetective',
)
