# -*- mode: python ; coding: utf-8 -*-
import json
import os
import sys
from PyInstaller.utils.hooks import collect_submodules

# 1. 环境与路径初始化
pro_root = os.path.abspath(os.getcwd())

# 强制收集所有业务逻辑子模块（如 map_handlers, utils 等）
# 这样可以解决你提到的大量 src.xxx.yyy 导入问题
src_submodules = collect_submodules('src')

# The frozen Malwarfare runtime resolves these production resources relative
# to its packaged module location. Keep the small verified bundle inside the
# PyInstaller onedir payload; the normal resources copy remains unchanged.
malwarfare_runtime_datas = [
    (os.path.join(pro_root, 'config', 'malwarfare_zh.json'), 'config'),
    (
        os.path.join(pro_root, 'resources', 'malwarfare'),
        os.path.join('resources', 'malwarfare'),
    ),
]

# The opt-in 3840 bundle verifies both its resource hashes and the declared
# pure-inference Python file inventory. Include exactly those manifest entries
# in the onedir payload so the frozen app can verify itself without a source
# checkout, analysis data, recordings, Candidate, Shadow, or GT artifacts.
malwarfare_3840_manifest_path = os.path.join(
    pro_root,
    'resources',
    'malwarfare_3840',
    'runtime_bundle_manifest.json',
)
with open(malwarfare_3840_manifest_path, 'r', encoding='utf-8') as manifest_file:
    malwarfare_3840_manifest = json.load(manifest_file)
malwarfare_runtime_datas.append(
    (
        os.path.join(pro_root, 'resources', 'malwarfare_3840'),
        os.path.join('resources', 'malwarfare_3840'),
    )
)
for relative_path in malwarfare_3840_manifest['python_files']:
    path_parts = relative_path.split('/')
    malwarfare_runtime_datas.append(
        (
            os.path.join(pro_root, *path_parts),
            os.path.dirname(relative_path),
        )
    )
# The resolution Router composes the 2560 and 3840 bundles but is intentionally
# outside the 3840-only manifest. Keep it visible in the packaged audit tree.
malwarfare_runtime_datas.append(
    (
        os.path.join(pro_root, 'src', 'malwarfare', 'runtime_router.py'),
        os.path.join('src', 'malwarfare'),
    )
)

a = Analysis(
    ['src/main.py'],
    pathex=[
        pro_root,  # 确保能识别以 src 开头的导入
        os.path.join(pro_root, 'python', 'Lib', 'site-packages')
    ],
    binaries=[],
    # PP-OCRv5 remains an external addon. The small Malwarfare frozen runtime
    # bundle is embedded because its public API uses module-relative defaults.
    datas=malwarfare_runtime_datas,
    hiddenimports=[
        'PyQt5.sip',
        'aiohttp',
        'pandas',
        'pypinyin',
        'rapidfuzz',
        'win32api',
        'src.config',
        'src.utils.logging_util'
    ] + src_submodules,
    hookspath=[],
    hooksconfig={},
    # 排除不需要的大型库以减小体积
    excludes=[
        'tkinter',
        'matplotlib',
        'easyocr',
        'torch',
        'IPython',
        # No source module uses Pillow; screenshots and resources use OpenCV
        # and Qt directly.
        'PIL',
        # Benchmark-only OCR dependencies; production uses OpenCV DNN.
        'rapidocr',
        'onnxruntime',
        'omegaconf',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# KeiFrame uses OpenCV for image/template/DNN operations and captures frames
# through mss. The OpenCV wheel's optional FFmpeg video codecs are not used by
# the application and account for a large amount of release size.
a.binaries = [
    entry
    for entry in a.binaries
    if not os.path.basename(entry[0]).lower().startswith(
        'opencv_videoio_ffmpeg'
    )
]

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
