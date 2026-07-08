# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置
打包命令：pyinstaller ResumeDetective.spec
"""

import os
import sys

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
        # 项目模块
        'resumedetective',
        'resumedetective.config_manager',
        'resumedetective.db_manager',
        'resumedetective.models',
        'resumedetective.main_window',
        'resumedetective.board_widget',
        'resumedetective.table_view',
        'resumedetective.detail_dialog',
        'resumedetective.dialogs',
        'resumedetective.materials_widget',
        'resumedetective.ai_service',
        'resumedetective.cli_ai',
        'resumedetective.chat_history',
        'resumedetective.io_export',
        'resumedetective.paths',
        'resumedetective.tools_pdf2img',
        'resumedetective.tools_imgpdf',
        'resumedetective.job_targets_widget',
        'resumedetective.secure_store',
        'resumedetective.file_ops',
        'PIL',
        'fitz',
        'openpyxl',
        'requests',
        'comtypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
