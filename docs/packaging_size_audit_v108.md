# KeiFrame v108 发行包体积审计

审计日期：2026-11-23

发行基准：`dist/Keiframe_Release_v108`

审计性质：只读检查、临时目录压缩实测与源码静态分析。本报告之外未修改业务代码、资源、依赖、spec、构建脚本、`dist/` 或 `build/`。

## 1. 执行摘要

### 1.1 最重要的发现

1. **当前主发行目录实际为 301,988,103 bytes（287.998 MiB / 301.988 MB），共 1,399 个文件。** 本机 Bandizip 7.30 CLI 使用 `-l:9` 生成的 7z 为 **102,437,797 bytes（97.692 MiB / 102.438 MB）**，与用户所述“约 98 MB”高度吻合。Bandizip/Windows 软件常把二进制 MiB 显示成“MB”；若网盘限制是严格的 100,000,000 bytes，这个文件实际已经超限。
2. **当前主包包含本应作为独立 addon 的 PP-OCRv5 三个文件。** `resources/ocr/ppocrv5` 共 **15.949 MiB**，其中 ONNX 模型 15.861 MiB。临时副本排除该目录后，Bandizip 同参数实测为 **88.538 MB**，减少 **13.900 MB**；7-Zip 高压实测由 **100.226 MB** 降为 **86.466 MB**，减少 **13.760 MB**。这是当前收益最大、证据最强的打包层修正。
3. **当前成品与构建合同不一致。** `build-keiframe.bat:42-45` 明确声明主包排除 OCR addon，`README.md` 也把它描述为可选独立 addon；但当前主包包含完整模型，而 `dist/KeiFrame_PP-OCRv5_Addon` 只有 `README.txt`。对当前 robocopy 命令的 `/L` dry-run 会排除模型，所以仅凭现状无法判定是旧脚本、后处理还是人工移动导致；能确认的是 v108 成品不可由当前合同解释，发布装配需要先可复现化。
4. 未压缩体积最大的五类仍是 **PyQt5/Qt（82.409 MiB）**、**OpenCV（82.309 MiB）**、**NumPy（27.742 MiB）**、**pandas/openpyxl 依赖链（20.645 MiB）**、**Python 解释器及标准库（16.898 MiB）**。PP-OCRv5 addon 为 15.949 MiB，是第七大分类，但因 ONNX 压缩率低，对最终 7z 的影响远高于其排名。
5. **不建议为了 80 MB 目标立即全面重写 Rust/C++。** 仅恢复既有 addon 分发合同，成品就已回到 86.466–88.538 MB。无 addon 的 Qt 候选裁剪对照为 83.035 MB；再完成 pandas 替换、字体子集化或地图笔记优化中的一个，十进制 80 MB 很可能可达。全面原生重写只应在“完整离线单包、功能不减、低于 50 MB”成为硬性长期目标且 Python 路线验证失败后立项。

### 1.2 证据等级

- **已实测确认**：当前发行目录字节数、分类、前 30 文件、前 20 目录、SHA-256 重复文件；Bandizip 完整包；7-Zip 完整包；排除 PP-OCRv5 的完整包对照；重点目录独立压缩；Qt 排除体积对照。
- **源码静态分析确认**：依赖实际 import、pandas 用途、Qt Multimedia/SVG/JPEG 用途、资源路径、spec/build 复制关系、FFmpeg 文件缺失、未接入模块被强制收集、PP-OCRv5 的可选 addon 语义。
- **合理推测**：干净 headless OpenCV、pandas 重构、字体子集化、WebP 资源变更后的最终 full-solid 节省范围。
- **尚待验证**：所有候选裁剪包的 Windows 实机启动、音频、托盘、图标、DPI、SC2 截图/OCR；Bandizip GUI“最高压缩”的所有参数是否与 CLI `-l:9` 完全相同；原作者 C++ 版本的同功能可比体积。

## 2. 统计口径与方法

### 2.1 MB 与 MiB

- 1 MB = 1,000,000 bytes（十进制）。
- 1 MiB = 1,048,576 bytes（二进制）。
- 100 MB = 95.367 MiB；100 MiB = 104.858 MB。
- 本报告的目录、类别和文件表以 MiB 为主；压缩结果同时给出 bytes、MiB 与 MB。网盘阈值必须以真实 bytes 判断。

### 2.2 发行基准

- 唯一发行基准是当前磁盘上的 `dist/Keiframe_Release_v108`，不是源码目录，也不是 `dist/KeiFrame_PP-OCRv5_Addon`。
- 当前基准含 1,399 个文件、182 个子目录。
- 项目目录中没有对应的原始 `.7z` 文件，无法读取用户原包元数据；但本机 Bandizip CLI 的结果与“约 98 MB”一致。
- 工作区审计前已有 `build-keiframe.bat` 未提交修改，内容是将发行目录名由 v107b 改为 v108；本轮没有覆盖该修改。

### 2.3 分类方法

磁盘 DLL、PYD、包数据和资源按路径归类。`Keiframe.exe` 内含 PyInstaller `PYZ.pyz`；使用 PyInstaller archive viewer/构建 TOC 识别归档模块，并按压缩条目大小分摊到 NumPy、pandas/openpyxl、其他第三方依赖和 KeiFrame 自身代码。EXE 的其余部分计入 Python bootloader/运行时。分类总和与当前目录字节数一致，未用源码体积替代发行体积。

## 3. 发行包构成

### 3.1 总体

| 指标 | 当前结果 |
| --- | ---: |
| 实际字节数 | 301,988,103 bytes |
| 未压缩大小 | 287.998 MiB |
| 未压缩十进制大小 | 301.988 MB |
| 文件数 | 1,399 |
| 子目录数 | 182 |

### 3.2 分类汇总

| 类别 | MiB | 占比 | 说明 |
| --- | ---: | ---: | --- |
| PyQt5、Qt DLL、plugins、translations | 82.409 | 28.61% | QtWidgets/Gui/Core/Multimedia、Qt bin、24 个 plugin、95 个翻译文件 |
| OpenCV | 82.309 | 28.58% | 主要是 82.296 MiB 的单体 `cv2.pyd`；没有 FFmpeg DLL |
| NumPy | 27.742 | 9.63% | 19.446 MiB OpenBLAS、NumPy PYD 与 PYZ 纯 Python 模块 |
| pandas、openpyxl 及直接数据链 | 20.645 | 7.17% | pandas native/PYZ、openpyxl、pytz、dateutil、et_xmlfile |
| Python 解释器及标准库 | 16.898 | 5.87% | `python310.dll`、标准扩展、SSL/SQLite/UCRT、base library、bootloader |
| 图像、图标、地图笔记、非净网模板 | 16.834 | 5.85% | 地图笔记占 16.077 MiB |
| PP-OCRv5 可选 addon 模型与字典 | 15.949 | 5.54% | 当前误在主包；ONNX、字典、来源说明 |
| 其他 Python 第三方依赖 | 11.057 | 3.84% | rapidfuzz、pypinyin、aiohttp、pywin32 等 |
| 字体 | 10.064 | 3.49% | 基本全部为 `NotoSansSC-Medium.ttf` |
| 其他运行时资源 | 2.590 | 0.90% | PDF、数据库、声音、敌方资料、配置等 |
| Malwarfare OCR 模型与模板 | 1.010 | 0.35% | 根资源约 0.602 MiB，`_internal` 重复 runtime 约 0.408 MiB |
| KeiFrame 自身 Python 代码 | 0.492 | 0.17% | PYZ 内 `src.*`、入口脚本及 manifest 要求的源码数据 |
| 无法明确归类 | 0.000 | 0.00% | 本次均可归类 |

> PP-OCRv5 是敌方组成识别 addon，不是 Malwarfare frozen OCR。二者在表中分开，避免把 15.9 MiB 模型误归到净网行动资源。pandas/openpyxl 不能直接视为无用，因为它们承载 Excel 导入导出；NumPy 也被 OpenCV 与识别算法直接使用。

### 3.3 最大的 30 个文件

| # | MiB | 相对路径 |
| ---: | ---: | --- |
| 1 | 82.296 | `_internal/cv2/cv2.pyd` |
| 2 | 19.954 | `_internal/PyQt5/Qt5/bin/opengl32sw.dll` |
| 3 | 19.446 | `_internal/numpy.libs/libscipy_openblas64_-13e2df515630b4a41f92893938845698.dll` |
| 4 | 15.861 | `resources/ocr/ppocrv5/ch_PP-OCRv5_rec_mobile.onnx` |
| 5 | 10.064 | `resources/fonts/primary/NotoSansSC-Medium.ttf` |
| 6 | 6.684 | `_internal/PyQt5/Qt5/bin/Qt5Gui.dll` |
| 7 | 6.633 | `Keiframe.exe` |
| 8 | 5.745 | `_internal/PyQt5/Qt5/bin/Qt5Core.dll` |
| 9 | 5.244 | `_internal/PyQt5/Qt5/bin/Qt5Widgets.dll` |
| 10 | 4.906 | `_internal/PyQt5/QtWidgets.pyd` |
| 11 | 4.252 | `_internal/python310.dll` |
| 12 | 3.981 | `_internal/PyQt5/Qt5/bin/d3dcompiler_47.dll` |
| 13 | 3.978 | `_internal/numpy/_core/_multiarray_umath.cp310-win_amd64.pyd` |
| 14 | 3.957 | `_internal/PyQt5/Qt5/bin/Qt5Quick.dll` |
| 15 | 3.425 | `_internal/PyQt5/Qt5/bin/Qt5Qml.dll` |
| 16 | 3.291 | `_internal/libcrypto-1_1.dll` |
| 17 | 3.229 | `_internal/PyQt5/Qt5/bin/libGLESv2.dll` |
| 18 | 3.057 | `_internal/PyQt5/Qt5/bin/libcrypto-1_1-x64.dll` |
| 19 | 2.566 | `resources/memo/湮灭快车.png` |
| 20 | 2.428 | `_internal/pypinyin/phrases_dict.json` |
| 21 | 2.379 | `_internal/PyQt5/QtGui.pyd` |
| 22 | 2.369 | `_internal/PyQt5/QtCore.pyd` |
| 23 | 2.328 | `resources/memo/熔火危机.png` |
| 24 | 2.249 | `resources/memo/聚铁成兵.png` |
| 25 | 2.070 | `使用说明.pdf` |
| 26 | 2.001 | `resources/memo/净网行动.png` |
| 27 | 1.959 | `_internal/pandas/_libs/groupby.cp310-win_amd64.pyd` |
| 28 | 1.866 | `resources/memo/机会渺茫.png` |
| 29 | 1.777 | `_internal/pandas/_libs/hashtable.cp310-win_amd64.pyd` |
| 30 | 1.719 | `_internal/pandas/_libs/algos.cp310-win_amd64.pyd` |

### 3.4 最大的 20 个目录

目录大小包含全部后代，因此父子目录会重叠，不能相加。

| # | MiB | 占总包 | 文件数 | 相对路径 |
| ---: | ---: | ---: | ---: | --- |
| 1 | 235.329 | 81.71% | 1,018 | `_internal` |
| 2 | 82.408 | 28.61% | 146 | `_internal/PyQt5` |
| 3 | 82.309 | 28.58% | 12 | `_internal/cv2` |
| 4 | 71.081 | 24.68% | 140 | `_internal/PyQt5/Qt5` |
| 5 | 59.964 | 20.82% | 21 | `_internal/PyQt5/Qt5/bin` |
| 6 | 43.963 | 15.27% | 378 | `resources` |
| 7 | 19.995 | 6.94% | 2 | `_internal/numpy.libs` |
| 8 | 16.562 | 5.75% | 51 | `_internal/pandas` |
| 9 | 16.554 | 5.75% | 44 | `_internal/pandas/_libs` |
| 10 | 16.077 | 5.58% | 10 | `resources/memo` |
| 11 | 15.949 | 5.54% | 3 | `resources/ocr` |
| 12 | 15.949 | 5.54% | 3 | `resources/ocr/ppocrv5` |
| 13 | 10.064 | 3.49% | 2 | `resources/fonts` |
| 14 | 10.064 | 3.49% | 1 | `resources/fonts/primary` |
| 15 | 6.494 | 2.25% | 13 | `_internal/numpy` |
| 16 | 5.958 | 2.07% | 24 | `_internal/PyQt5/Qt5/plugins` |
| 17 | 5.497 | 1.91% | 8 | `_internal/rapidfuzz` |
| 18 | 5.159 | 1.79% | 95 | `_internal/PyQt5/Qt5/translations` |
| 19 | 4.167 | 1.45% | 16 | `_internal/pandas/_libs/tslibs` |
| 20 | 4.038 | 1.40% | 2 | `_internal/numpy/_core` |

### 3.5 重复、可疑和非正式发行候选

#### 已实测确认

- 当前主包的 PP-OCRv5 三个文件与源码 `resources/ocr/ppocrv5` 的 SHA-256 完全一致，但它们违反当前“独立 addon”的装配合同。更异常的是，旁边的 `dist/KeiFrame_PP-OCRv5_Addon` 只有 `README.txt`，没有模型和字典。
- 全目录哈希检查发现 147 组相同内容，理论重复字节 1,331,268 bytes（1.270 MiB）。多数是 `pytz` 时区别名，不能按普通重复文件删除。
- `_internal/numpy.libs/...msvcp140...dll` 与 `_internal/pandas.libs/...msvcp140...dll` 内容相同，每份 0.548 MiB；文件名和 wheel 私有加载路径不同，不能直接手删，需通过 wheel/build A/B 验证。
- spec 将 Malwarfare runtime 收进 `_internal/resources/...`，build 又复制根 `resources/`。两套 runtime 共约 0.408 MiB 内容相同；solid 压缩可利用重复内容，所以实际删除收益低于原始大小。
- `resources/db/db_backups/` 含三份随包备份，共 224 KiB；源码未发现运行时读取 `db_backups`。如只供开发恢复，可从发行复制清单排除，但收益很小。
- 未发现 `opencv_videoio_ffmpeg*`、`avcodec`、`avformat` 或 `avutil` 文件，说明 `Keiframe.spec:128-134` 的 OpenCV FFmpeg 排除在 v108 输出中生效。
- 当前发行目录没有 `tests/`、`debug/`、训练录像、GT、Candidate、Shadow 等开发资产。

#### 源码静态分析确认

- `collect_submodules('src')`（`Keiframe.spec:10-12`）把 `src.settings_window.test_setting`、尚未接入的 Cradle of Death 组件和历史 `map_processor.py` 强制放入 PYZ。它们本身很小，主要风险是扩大隐式依赖面，不是数十 MB 的主因。
- `_internal/src/map_handlers/malwarfare/*.py` 是 manifest/模块相对资源校验的一部分；与 PYZ 字节码逻辑重复，但不能在不修改并验证协议的情况下删除。
- `使用说明.pdf` 2.070 MiB，已高度压缩且由构建脚本明确复制，不能只因体积认定为多余。

## 4. 7z 压缩分析

### 4.1 Bandizip 最高等级复现

工具：Bandizip console tool 7.30 Beta x64。

```text
bz c -l:9 -fmt:7z -r -y <temp.7z> Keiframe_Release_v108
```

7-Zip 读取归档元数据：`Method = LZMA2:26`、`Solid = +`、`Blocks = 1`。Bandizip CLI 未暴露 GUI 中全部高级选项，因此不能证明与用户 GUI“最高压缩”逐项相同；但结果 97.692 MiB 与“约 98 MB”高度一致。

### 4.2 完整包和排除 addon 对照

7-Zip 23.01 x64 参数：

```text
7z a -t7z -mx=9 -m0=lzma2 -md=128m -mfb=273 -ms=on -mmt=on <temp.7z> Keiframe_Release_v108
```

7-Zip 归档元数据：`Method = LZMA2:27 LZMA:20 BCJ2`、`Solid = +`、`Blocks = 2`。

| 测试 | bytes | MiB | MB | 相对当前完整包 |
| --- | ---: | ---: | ---: | ---: |
| 当前未压缩目录 | 301,988,103 | 287.998 | 301.988 | — |
| Bandizip `-l:9` 当前完整包 | 102,437,797 | 97.692 | 102.438 | 基准 |
| 7-Zip 明确高压参数当前完整包 | 100,226,095 | 95.583 | 100.226 | 比 Bandizip 少 2.212 MB |
| Bandizip `-l:9`，临时副本排除 PP-OCRv5 | 88,537,928 | 84.436 | 88.538 | 少 13.900 MB |
| 7-Zip 明确高压参数，临时副本排除 PP-OCRv5 | 86,465,740 | 82.460 | 86.466 | 少 13.760 MB |

结论：用户的约 98“MB”很可能是 97.692 MiB 的显示值；真实文件为 102.438 MB。PP-OCRv5 ONNX 本身压缩率较低，分离 addon 对最终归档的收益接近其原始体积，而不是像 DLL/PYD 那样只留下约 20%–25%。

### 4.3 重点目录独立压缩

独立归档的 header、文件顺序和 solid 字典与完整包不同，**不能相加，也不等于从 full-solid 完整包移除它们后的精确节省量**。

| 测试对象 | 原始 MiB | 独立 7z MiB | 独立 7z MB | 压缩后/原始 |
| --- | ---: | ---: | ---: | ---: |
| OpenCV 磁盘文件 | 82.310 | 19.710 | 20.67 | 23.95% |
| PyQt5/Qt 磁盘文件 | 82.408 | 19.740 | 20.70 | 23.96% |
| NumPy 磁盘文件 | 26.710 | 4.840 | 5.07 | 18.12% |
| pandas native/data（不含 EXE 内 PYZ） | 18.080 | 3.340 | 3.50 | 18.47% |
| 当前全部根 `resources/`（含 addon） | 43.963 | 34.600 | 36.28 | 78.70% |
| 根 `resources/`（排除 addon） | 28.014 | 21.460 | 22.50 | 76.61% |
| PP-OCRv5 addon | 15.949 | 13.140 | 13.78 | 82.39% |
| 地图笔记 PNG | 16.077 | 15.940 | 16.72 | 99.16% |
| 字体 | 10.064 | 4.450 | 4.67 | 44.25% |
| Qt translations | 5.159 | 0.680 | 0.71 | 13.18% |
| pypinyin 磁盘数据 | 3.204 | 0.560 | 0.58 | 17.42% |
| rapidfuzz 磁盘文件 | 5.497 | 0.810 | 0.85 | 14.68% |

关键判断：

- OpenCV、Qt、NumPy 和 pandas 的 DLL/PYD/JSON 在 solid 7z 中压缩率高；不能把 82 MiB 的 `cv2.pyd` 当作可节省 82 MiB。
- 地图笔记 PNG 已几乎不可再由 7z 压缩，16.72 MB 是压缩包中的“硬体积”。
- PP-OCRv5 独立压缩仍有 13.78 MB，是当前最明确的单项收益。
- 字体独立 7z 为 4.67 MB；子集化或删除的归档收益上限约为该值，而不是原始 10.064 MiB。
- Malwarfare runtime/model/template 仅约 1 MiB，不是主矛盾。

### 4.4 无 addon 的 Qt 完整包排除对照

| 对照包（均排除 PP-OCRv5） | MiB | MB | 相对无 addon 7-Zip 基准 | 状态 |
| --- | ---: | ---: | ---: | --- |
| 无 addon 完整基准 | 82.460 | 86.466 | — | 已实测 |
| 再排除全部 Qt translations | 81.780 | 85.752 | 0.680 MiB / 0.714 MB | 仅压缩实测，未运行 |
| 再排除 translations + Qt/QML/plugin 候选 | 79.190 | 83.035 | 3.270 MiB / 3.431 MB | 仅压缩实测，未运行 |

候选包括：`qminimal`、`qoffscreen`、`qwebgl`、静态引用未见使用的 GIF/ICNS/TGA/TIFF/WBMP/WebP image plugin、`qxdgdesktopportal`、touch plugin，以及 Qt Quick/QML/QMLModels/WebSockets/DBus DLL。保留 Windows platform、Qt Multimedia、audio/mediaservice、SVG、ICO、JPEG、playlist、Windows style 和软件 OpenGL fallback。此结果只是体积上界实验，必须逐项做 Windows 启动、音频、托盘、SVG/JPEG、文件对话框、远程桌面与软件 OpenGL 回归。

## 5. 打包配置审计

### 5.1 发布装配与 addon 合同

- `build-keiframe.bat:42-45` 期望主包复制 `resources/` 时排除 `resources/ocr/ppocrv5`，`build-keiframe.bat:53-74` 再生成独立 addon。
- 当前主包却含完整模型，独立 addon 只有 README。当前 robocopy 命令以 `/L` dry-run 时会正确排除模型，因此不能直接断言脚本语法失效；更准确的结论是：**当前 v108 目录与当前脚本不一致，成品来源或后处理不可复现。**
- 这是 P0 发布问题：既影响体积，也影响“主包是否默认启用敌方组成 OCR”的产品语义。修正时必须明确主包与 addon 是分别发布，还是决定合并；不能同时宣称“可选 addon”又把模型放入主包。

### 5.2 PyInstaller 收集范围

- `collect_submodules('src')` 过宽（`Keiframe.spec:10-12`）。当前做法将未接入和测试式模块强制打入 PYZ。建议以后改为显式动态模块清单或移除后检查 Analysis 缺失项，预计 7z 收益小于 0.1 MB。
- `hiddenimports`（`Keiframe.spec:92-101`）中，`aiohttp`、`pandas`、`pypinyin`、`win32api`、`src.config`、`src.utils.logging_util` 都有静态 import；`rapidfuzz` 是函数内 import，通常仍可发现；`PyQt5.sip` 有运行时 import，应保留。清理价值主要是降低误收集风险。

### 5.3 Qt

- 95 个 translations 共 5.159 MiB；源码没有 `QTranslator`、`installTranslator` 或 `QLocale`，是高可信候选。
- Windows 正常 GUI 需要 `qwindows.dll`。`qminimal`、`qoffscreen`、`qwebgl` 是候选，但需验证异常显卡、远程桌面和 DPI。
- Qt Multimedia/MP3 有明确生产调用（`src/presentation_modules/sound_player.py:8-116`），audio、mediaservice、playlist 不能按名称删除。
- SVG、ICO、JPEG 有生产资源调用，应保留相应 plugin。若地图笔记改 WebP，`qwebp.dll` 必须保留，与“删 WebP plugin”互斥。
- `opengl32sw.dll` 是软件 OpenGL fallback。它在 7z 中压缩率较高，删除风险大，不列为低风险优化。

### 5.4 OpenCV

- `Keiframe.spec:128-134` 的 FFmpeg 排除已生效。
- 当前 `_internal/cv2/version.py` 显示 `opencv-python 5.0.0.93`、`headless = False`；两份 requirements 却声明 `opencv-python-headless`，`src/requirements.txt:5` 为 4.13.0.92。
- 嵌入式环境同时有 `opencv_python_headless-4.13.0.92.dist-info` 与 `opencv_python-5.0.0.93.dist-info`。构建脚本直接使用现有环境（`build-keiframe.bat:21-22`），没有创建 clean env。
- `cv2.pyd` 是单体二进制，不能从成品中手删 videoio/highgui/DNN 子模块。先做干净 headless wheel A/B，需要更大收益时才考虑自定义 OpenCV build。

### 5.5 pandas、openpyxl 与 NumPy

- pandas 用途集中在 `src/utils/excel_utils.py:1-134`、`src/utils/data_validator.py:2,84` 和 `src/settings_window/complex_inputs.py:248-250`。
- openpyxl 已负责工作簿格式、列宽、保护和保存。可以用 openpyxl 逐行读写，并用 `None`/`math.isnan` 替代 pandas 空值逻辑；必须回归 Excel 类型、文本时间、空行、列顺序和旧文件兼容。
- NumPy 被截图、OpenCV、OCR、模板匹配和状态机直接使用，不能随 pandas 一起删除。
- 实际构建为 NumPy 2.2.6、pandas 2.3.3；`src/requirements.txt` 声明 2.4.2 与 3.0.0。版本漂移会影响功能、ABI 与体积。

### 5.6 resources、开发资产与 UPX

- spec 在 `Keiframe.spec:17-80` 收集 Malwarfare runtime，build 又复制根资源，形成约 0.408 MiB runtime 重复。根副本能否排除需冻结环境验证。
- 没有发现 `tests/`、训练数据、录屏、GT、Candidate 或 Shadow 进入正式包。
- `resources/db/db_backups`、未接入 Cradle of Death 模板/代码是否保留属于产品决策，收益小，不应未经确认删除。
- spec 设置 `upx=True`（`Keiframe.spec:148,166`），但本机找不到 UPX。最终还要 solid 7z 时，UPX 可能破坏 LZMA/BCJ2 跨文件压缩，只有完整归档 A/B 后才应采用。

## 6. 优化方案与量化

节省均指最终 7z；没有 full-solid 实测时标为估计或待验证。关联项目不能简单相加。

| 级别 / 项目 | 当前依据 | 预计节省的 7z 体积 | 修改成本 | 功能风险 | 优先级 |
| --- | --- | ---: | --- | --- | --- |
| A：恢复 PP-OCRv5 独立 addon 合同 | 当前主包含完整 addon；完整排除对照 | **Bandizip 13.900 MB、7-Zip 13.760 MB，已实测** | 0.5–1 天 | 低到中；未装 addon 的用户不再有敌方组成 OCR，符合当前文档定义 | P0 |
| A：固定可复现构建、核对主包/addon 清单 | 当前主包与脚本不一致，独立 addon 不完整 | 收益已包含上一项 | 0.5–1 天 | 低；发布可靠性 | P0 |
| A：固定 7-Zip 高压 solid 参数 | 当前完整包比 Bandizip 少 2.212 MB；无 addon 少 2.072 MB | **约 2.1–2.2 MB，已实测** | 0.5 天 | 低；确认解压兼容 | P0 |
| A：干净、锁版本的 headless OpenCV | 实际打入 full 5.0.0.93，与清单不符 | **待验证；粗略 0–5+ MB** | 0.5–1 天 A/B | 低到中；DNN/截图/模板匹配回归 | P0 |
| A：排除 Qt translations | 无 addon 完整排除对照 | **0.714 MB，已实测** | 0.5 天 | 低；检查原生对话/系统文本 | P0 |
| A：逐项裁剪 Qt platform/image/QML 候选 | 无 addon 候选包 83.035 MB | **3.431 MB 含 translations；增量 2.717 MB** | 1–2 天 | 低到中；Windows/音频/图标/OpenGL 验收 | P0 |
| A：停止复制根 Malwarfare runtime 副本 | 原始重复 0.408 MiB | **0–0.36 MB，待验证** | 0.5–1 天 | 低到中；相对路径/manifest | P1 |
| A：排除 `db_backups` | 224 KiB，源码未见读取 | **约 0.02–0.15 MB，待验证** | 0.5 天 | 低；失去随包恢复副本 | P2 |
| A：收紧 `collect_submodules`/hiddenimports | PYZ 含未接入/测试式模块 | **大概率 <0.1 MB** | 1 天 | 低到中；漏动态 import | P2 |
| B：openpyxl + 标准库替代 pandas | pandas native 独立 3.50 MB，另有 PYZ | **约 5.5–6.5 MB，需 full build** | 3–6 天 | 中；Excel 类型、空值、格式 | P1 |
| B：地图笔记改 lossless WebP | PNG 已不可再压；试编码约减少 37% | **约 5.5–6.5 MB，待完整包验证** | 2–4 天 | 中；透明度/清晰度/保留 qwebp | P1 |
| B：字体子集化并保留系统 fallback | 字体独立 7z 4.67 MB | **估计 3–4.5 MB** | 1–3 天 | 中；缺字、样式、系统差异 | P1 |
| B：memo/font 独立资源包 | 两者独立压缩约 21.4 MB | **主程序可少约 20–21 MB；总下载不变** | 1–3 天 | 中；安装和缺资源体验 | P1（单文件限制） |
| B：静态别名替代 pypinyin | 磁盘独立 7z 0.58 MB | **约 0.5–0.7 MB** | 1–2 天 | 中；拼音搜索覆盖下降 | P2 |
| B：自定义最小 OpenCV | 当前 OpenCV 独立压缩 20.67 MB | **粗略 3–10 MB，证据不足** | 1–3 周 | 中到高；ABI/DNN/CPU 兼容 | P2 |
| C：C++ 全面重写（保留 Qt/OpenCV） | 去 Python/pandas/PyQt binding，保留 Qt/OpenCV/资源 | **粗略成包 40–70 MB** | 6–12+ 人月 | 高 | P3 |
| C：C++（Win32/Direct2D + 精简 OpenCV） | 同时去 Python 与 Qt | **粗略成包 25–50 MB** | 9–18+ 人月 | 很高 | P3 |
| C：Rust 全面重写 | 去 Python/PyQt，重建 GUI/OpenCV/Win32 绑定 | **粗略成包 25–55 MB** | 10–20+ 人月 | 很高 | P3 |
| C：Python + Rust/C++ 混合 | Python host、PyQt 和多数 runtime 仍在 | **通常 0–10 MB，甚至可能增大** | 1–4+ 人月 | 中到高 | P3（适合性能） |

## 7. 优先优化路线

### 阶段 0：恢复正确、可复现的发布边界

1. 明确 PP-OCRv5 是独立 addon 还是主包内置。按当前 README/build 合同，应从主包排除，并让独立 addon 真正包含模型、字典和来源说明。
2. 为主包/addon 生成文件清单或哈希；构建后断言主包不含 addon、addon 必含三个文件。
3. 固定 clean build 环境和依赖版本，消除 full/headless OpenCV 共存。
4. 固定压缩程序、版本、参数和最终 bytes，同时记录 MB/MiB。

这一阶段不改业务代码即可把当前 Bandizip 成品从 102.438 MB 实测降到 88.538 MB；改用本报告 7-Zip 参数为 86.466 MB。

### 阶段 1：低风险 PyInstaller 裁剪

1. 排除 Qt translations。
2. 逐项排除非 Windows platform、未用 image plugin 与 QML/Quick 候选，每一步验证启动、音频、托盘、图标、原生对话框、软件 OpenGL 和远程桌面。
3. 处理根/`_internal` Malwarfare runtime 重复与 `db_backups`。
4. 最后收紧 `collect_submodules`/hiddenimports；这项收益小。

无 addon 的 Qt 候选对照为 83.035 MB，低于 80 MiB，但仍高于十进制 80 MB。

### 阶段 2：一个边界清晰的中风险项目

1. pandas → openpyxl/标准库：位置集中，预计 5.5–6.5 MB。
2. 字体子集化：比完全删除可控。
3. lossless WebP memo：收益大，但与裁剪 `qwebp.dll` 互斥。
4. 若只解决网盘单文件限制，memo/font 资源包比原生重写直接；PP-OCRv5 已应独立分发。

`83.035 MB Qt 候选包 + pandas 重构` 的关联估计为 **约 76.5–77.5 MB**。这不是已构建结果，但说明 80 MB 不需要全面原生重写。

### 阶段 3：70 MB 与 50 MB

- **70 MB**：Qt 裁剪 + pandas 后还需字体、memo 或 OpenCV 中至少一个项目；有合理路径，但不能把独立数字直接相加后承诺结果。
- **50 MB**：先验证资源拆分/重编码、干净 headless OpenCV、自定义最小 OpenCV。若要求所有资源内置、功能不减且单包低于 50 MB，才进入原生 GUI/识别栈原型。

### 达成 80 MB 的机会

- 只修 addon 分发并换 7-Zip：**已实测 86.466 MB，不能达到 80 MB。**
- 再做全部 Qt 候选裁剪：**已压缩实测 83.035 MB，仍不能证明低于十进制 80 MB。**
- 在上述基础上完成 pandas、字体或 memo 任一高收益中风险项目：**高概率，约 80%–90% 可低于 80 MB**；最终必须以 clean full build 和 Windows 回归确认。

## 8. Rust/C++ 重构评估

### 8.1 能移除与仍需保留的内容

全面原生且不嵌入 Python 时，可移除 Python 解释器/标准库、PyInstaller bootloader、pandas/openpyxl Python 栈、NumPy Python binding、PyQt binding、pypinyin/rapidfuzz wheel。GUI 改 Win32/Direct2D 可再移除 Qt；图像算法直接用 `cv::Mat` 或自研实现可去 NumPy/OpenBLAS。

仍需保留或替代：OpenCV C++ 或等价图像处理/DNN；地图笔记、图标、字体、声音、SQLite 数据库、Malwarfare 模型/模板；SQLite native 与图片/字体/音频解码；PP-OCRv5 或等价 OCR runtime。

无 addon 的根资源独立压缩仍有 22.50 MB，其中地图笔记 16.72 MB。去 Python 不会自动得到 10 MB 包；原作者结果必须在同功能、同资源、同 GUI/识别库口径下比较。

### 8.2 迁移难度

| 子系统 | C++ | Rust | 主要风险 |
| --- | --- | --- | --- |
| Windows GUI、透明覆盖层、托盘、DPI | 中 | 高 | DPI、多显示器、点击穿透、生命周期 |
| SC2 窗口定位与截图 | 中 | 中 | client rect、DPI、色彩格式、帧率 |
| 全局热键 | 低到中 | 中 | 权限、冲突、退出注销 |
| SQLite/DAO | 低 | 低 | schema、事务、兼容性 |
| OpenCV 模板匹配与 DNN | 中 | 中到高 | ABI/FFI、模型一致性 |
| Malwarfare 状态机 | 中 | 中 | 阈值、缓存、线程、诊断一致性 |
| UI/后台线程生命周期 | 中到高 | 高 | 跨线程 UI、reset/shutdown |
| Excel 导入导出 | 中 | 中到高 | 格式、文本时间、空值、保护兼容 |

### 8.3 方案判断

- **C++**：与 OpenCV、Qt、Win32 生态最接近；若确需原生重写，迁移风险低于 Rust。保留 Qt/OpenCV 会保留两大 native 体积源；改 Win32/Direct2D 和最小 OpenCV 才可能接近 25–50 MB。
- **Rust**：内存安全和并发有长期价值，但主要难点是 Windows GUI、OpenCV/OCR 生态和行为一致性。只为减包选择 Rust，收益/成本比不如 C++。
- **混合实现**：适合把耗时 OCR/图像算法迁到 native 扩展以提升性能。Python/PyQt host 仍在，通常不会显著减包，还可能同时携带两套 runtime。

### 8.4 原作者 C++ 架构

仓库内没有可与 KeiFrame 主程序逐功能对照的原作者 C++ 发布源码、依赖清单或包构成；独立 Malwarfare C++ 模板工具不是主程序重写。因此“60 多 MB 降到 10 MB 以内”只能作为外部线索。若取得原作者功能矩阵、GUI 框架、OpenCV 链接方式、资源清单和压缩参数，应先做同口径比较。

## 9. 最终建议

1. **先修 Python 发布装配，不进入全面 Rust/C++ 重写。** 恢复 PP-OCRv5 独立 addon 已实测把 Bandizip 成品降至 88.538 MB、7-Zip 降至 86.466 MB。
2. 第二优先是**固定 clean build 与压缩口径**。当前 OpenCV 与 requirements 不一致，成品又与 addon 合同不一致，继续比较会失真。
3. 最值得优先实施的五项：
   1. 修复主包/addon 装配并增加构建后文件清单断言；
   2. 固定 7-Zip 高压 solid 参数；
   3. 用干净环境只保留目标 headless OpenCV，做完整 A/B；
   4. 排除 Qt translations，并逐项验证 Qt/QML/plugin 候选；
   5. 用 openpyxl/标准库替代 pandas；如不愿改代码，则优先字体子集化。
4. **80 MB 短期目标有高概率通过 Python 路线达到。** 当前还没有实测成品低于十进制 80 MB，但在 83.035 MB 对照上完成一个 3–6 MB 中风险项目即可进入目标区间。
5. **70 MB 仍可先尝试 Python 依赖/资源优化；50 MB 才值得做架构性原型。** 即使进入原生评估，也优先 C++ 小原型，不建议仅因包体积全面改写 Rust。

## 10. 本轮验证与未验证项

### 已执行

- 递归统计当前 `dist/Keiframe_Release_v108` 全部 1,399 个文件。
- PyInstaller EXE/PYZ/TOC 内容拆分与未接入模块核对。
- SHA-256 重复文件检查。
- Bandizip 7.30 `-l:9` 当前完整包和无 addon 临时副本实测。
- 7-Zip 23.01 当前完整包、无 addon 临时副本、重点目录和 Qt 排除体积对照。
- 源码 import、动态 import、资源路径、spec、build、requirements 静态核对。
- OpenCV/NumPy/pandas/openpyxl 实际版本核对。
- 当前 robocopy addon 排除规则的 `/L` dry-run。
- 临时归档和临时副本清理检查。

### 未执行

- 未运行 `build-keiframe.bat`，未重新生成或修改 `dist/`、`build/`。
- 未安装、卸载或升级依赖。
- 未启动 KeiFrame、SC2、6119 API、热键、托盘、音频、覆盖层或识别器。
- 未验证候选 Qt 裁剪包能否启动；Qt 结果仅为体积对照。
- 未测试 Windows DPI、多显示器、真实游戏、OCR 精度或最终发布完整性。
- 未取得用户原始 Bandizip 7z；CLI 结果虽吻合，但不能证明 GUI 参数完全相同。
- 未验证 runtime 根副本、Qt plugin 或数据库备份删除后的功能安全性。
