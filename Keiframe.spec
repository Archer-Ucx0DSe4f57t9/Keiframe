# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_submodules

# 1. 环境与路径初始化
pro_root = os.path.abspath(os.getcwd())

# 强制收集所有业务逻辑子模块（如 map_handlers, utils 等）
# 这样可以解决你提到的大量 src.xxx.yyy 导入问题
src_submodules = collect_submodules('src')

a = Analysis(
    ['src/main.py'],
    pathex=[
        pro_root,  # 确保能识别以 src 开头的导入
        os.path.join(pro_root, 'python', 'Lib', 'site-packages')
    ],
    binaries=[],
    datas=[],
    hiddenimports=[
        'PyQt5.sip',
        'aiohttp',
        'pandas',
        'pypinyin',
        'win32api',
        'src.config',
        'src.utils.logging_util'
    ] + src_submodules,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 排除不需要的大型库以减小体积
    excludes=['tkinter', 'matplotlib', 'easyocr', 'torch', 'IPython'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# 2. EXE 配置
exe = EXE(
    pyz,
    a.scripts,
    [],  # onedir 模式下这里保持为空
    exclude_binaries=True,
    name='Keiframe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 建议保留控制台以观察游戏数据抓取日志
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # 如果 resources 目录下有图标，取消下面注释
    icon=os.path.join(pro_root, 'resources','icons','icon.ico') 
)

# 3. 收集所有文件到文件夹
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Keiframe'
)