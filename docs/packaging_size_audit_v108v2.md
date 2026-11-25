# KeiFrame v108 发行包体积重新审计

审计日期为 2026-11-26。唯一测量对象为 `dist/Keiframe_Release_v108/`。以下目标线均按网盘可能采用的十进制字节判断。**1 MiB = 1,048,576 bytes，1 MB = 1,000,000 bytes。** 构成和节省量以 MiB 为主，面向上传的表格另列 MB。

## 1. 执行摘要

**现有完整包已经达到 80 MB 目标。** 当前目录共 **630 个文件、246,120,499 bytes（234.719 MiB）**。本机 Bandizip 最高等级得到 **78,959,974 bytes（78.960 MB）**，7-Zip 高压得到 **76,813,373 bytes（76.813 MB）**。保留现有全部文件，分别比 80 MB 小 1.040 MB 和 3.187 MB。继续使用 Python 足以解决当前上传问题。

| 交付目标 | 已测到的结果 | 决策 |
| --- | --- | --- |
| 完整包 <80 MB | 两种压缩程序均达标。以 7-Zip 分发时距 100 MB 还有 23.187 MB | 可直接采用已核对内容的归档。下一个源码构建另行验收 |
| 相同内容与使用体验 | 原文件完整归档 76.813 MB。十张笔记 PNG 仅在临时副本中无损重压，整包 76.586 MB | 当前可高把握按约 77 MB 规划。像素优化的额外空间有限 |
| 程序功能和内置笔记齐全，允许单列说明书 | 保持原始资源，只单列 PDF 后主包 74.917 MB | 约 75 MB 可行。离线说明需附同版 PDF |
| 主包 <70 MB | 单列地图笔记时主包 60.099 MB，连说明书也单列时为 58.203 MB | 分件分发有较高把握。保留所有内容于同一文件时，尚无验过的低风险路径 |
| 主包 <50 MB | 同时单列笔记、说明书和字体仍为 53.537 MB | 若必须单件、同功能且同画质，需进一步改资源表示或依赖。当前没有依据为此全面重写 |

**当前最值得处理的是构建可复现性。** 发行 EXE 中的 Excel 路径已改用 openpyxl，pandas 为零；工作区的 Excel 顶层导入和 spec 仍要求 pandas。现有发行品已使用 headless OpenCV，并已分离可选 PP-OCRv5 模型。上述项目再次“排除”的当前收益均为零。旧审计中的约 98、用户所述约 98 MB、当前同名目录应分别记录，不能凭 v108 名称认定为同一份文件。

证据分为四种。**已实测确认**指本次文件字节、归档目录、校验、压缩或像素对照。**源码静态分析确认**指源码、构建配置、冻结字节码名称及二进制依赖的可见调用关系。**合理推测**指据此推导的设计和风险。**尚待验证**指需要重建、运行游戏、确认外部发布条件或制作原型的结论。

## 2. 发行目录构成

从根目录递归枚举普通文件，包含隐藏项，统计文件内容长度。空目录和 NTFS 分配簇不计字节。根层为 `_internal/` 252 个文件、`resources/` 375 个文件、EXE/PDF/BAT 各一个。`dist/KeiFrame_PP-OCRv5_Addon/`、构建中间目录、本机嵌入式 Python 与工作区源码均未计入。

### 互斥分类（已实测确认）

直接读取发行 EXE 的 PyInstaller CArchive 和其中的 PYZ 索引。849 个模块按条目**已存储**长度归属；入口 `main` 计入业务，15 份外置 Python 包文件、推理及路由源码也计入业务。CPython 类含 python310.dll、base_library.zip、标准库扩展及其 SQLite/OpenSSL 等原生支持库。共享运行库另列，Qt 私有目录的 DLL 随 Qt 计。两处净网资源各按实际占用计入，净网 Python 源码只计到业务代码。EXE 剩余部分单列。下表“外置文件”不含拆分计量的 EXE；按字节加总恰好等于发行目录，显示值独立四舍五入。

| 类别 | 外置文件数 | EXE 内 MiB | 合计 MiB | 目录占比 |
| --- | ---: | ---: | ---: | ---: |
| OpenCV | 12 | 0.000 | 81.885 | 34.89% |
| PyQt5、Qt DLL 和 plugins | 35 | 0.000 | 65.776 | 28.02% |
| NumPy（含 OpenBLAS） | 23 | 1.030 | 27.742 | 11.82% |
| 图像、图标、地图笔记与其他识别图 | 152 | 0.000 | 16.834 | 7.17% |
| CPython、标准库及其原生支持库 | 24 | 1.389 | 14.451 | 6.16% |
| 其他第三方依赖与冻结辅助模块 | 63 | 0.723 | 10.679 | 4.55% |
| 字体及其目录占位 | 2 | 0.000 | 10.064 | 4.29% |
| 共享 MSVC、UCRT 和 Windows API 转接 DLL | 46 | 0.000 | 2.445 | 1.04% |
| 交付附件（使用说明 PDF、端口修复 BAT） | 2 | 0.000 | 2.073 | 0.88% |
| Malwarfare OCR 模型、模板、清单及专用配置 | 207 | 0.000 | 1.012 | 0.43% |
| 其他运行时资源（数据库、音频、CSV 等） | 48 | 0.000 | 0.515 | 0.22% |
| KeiFrame 自身 Python 代码 | 15 | 0.363 | 0.493 | 0.21% |
| EXE 引导程序、冻结启动脚本和归档结构余额 | 0 | 0.423 | 0.423 | 0.18% |
| openpyxl 与 et_xmlfile | 0 | 0.327 | 0.327 | 0.14% |
| pandas | 0 | 0.000 | 0.000 | 0.00% |
| 无法明确归类 | 0 | 0.000 | 0.000 | 0.00% |
| **总计** | **629 + 1 个 EXE** | **4.255** | **234.719** | **100%** |

图像类中仅 `resources/memo/` 就有 10 张 PNG（含背景）；字体为一份 Noto Sans SC Medium 与一个空占位。其他第三方主要有 RapidFuzz、pypinyin、aiohttp 及其依赖、pywin32、keyboard 和 mss。openpyxl 有 176 个 PYZ 条目，et_xmlfile 有 3 个；NumPy 同时服务识别链，单列且不分摊给 Excel。

### 体积最大的 30 个文件

路径相对发行根，按真实字节降序。这里展示整个 EXE 的文件长度。

| 排名 | 相对路径 | MiB |
| ---: | --- | ---: |
| 1 | `_internal/cv2/cv2.pyd` | 81.871 |
| 2 | `_internal/PyQt5/Qt5/bin/opengl32sw.dll` | 19.954 |
| 3 | `_internal/numpy.libs/libscipy_openblas64_-13e2df515630b4a41f92893938845698.dll` | 19.446 |
| 4 | `resources/fonts/primary/NotoSansSC-Medium.ttf` | 10.064 |
| 5 | `_internal/PyQt5/Qt5/bin/Qt5Gui.dll` | 6.684 |
| 6 | `_internal/PyQt5/Qt5/bin/Qt5Core.dll` | 5.745 |
| 7 | `_internal/PyQt5/Qt5/bin/Qt5Widgets.dll` | 5.244 |
| 8 | `_internal/PyQt5/QtWidgets.pyd` | 4.906 |
| 9 | `Keiframe.exe` | 4.255 |
| 10 | `_internal/python310.dll` | 4.252 |
| 11 | `_internal/PyQt5/Qt5/bin/d3dcompiler_47.dll` | 3.981 |
| 12 | `_internal/numpy/_core/_multiarray_umath.cp310-win_amd64.pyd` | 3.978 |
| 13 | `_internal/libcrypto-1_1.dll` | 3.291 |
| 14 | `_internal/PyQt5/Qt5/bin/libGLESv2.dll` | 3.229 |
| 15 | `_internal/PyQt5/Qt5/bin/libcrypto-1_1-x64.dll` | 3.057 |
| 16 | `resources/memo/湮灭快车.png` | 2.566 |
| 17 | `_internal/pypinyin/phrases_dict.json` | 2.428 |
| 18 | `_internal/PyQt5/QtGui.pyd` | 2.379 |
| 19 | `_internal/PyQt5/QtCore.pyd` | 2.369 |
| 20 | `resources/memo/熔火危机.png` | 2.328 |
| 21 | `resources/memo/聚铁成兵.png` | 2.249 |
| 22 | `使用说明.pdf` | 2.070 |
| 23 | `resources/memo/净网行动.png` | 2.001 |
| 24 | `resources/memo/机会渺茫.png` | 1.866 |
| 25 | `resources/memo/虚空降临.png` | 1.632 |
| 26 | `resources/memo/黑暗杀星.png` | 1.531 |
| 27 | `_internal/rapidfuzz/distance/metrics_cpp_avx2.cp310-win_amd64.pyd` | 1.464 |
| 28 | `_internal/rapidfuzz/distance/metrics_cpp.cp310-win_amd64.pyd` | 1.459 |
| 29 | `_internal/sqlite3.dll` | 1.441 |
| 30 | `_internal/PyQt5/Qt5/plugins/platforms/qwindows.dll` | 1.409 |

### 体积最大的 20 个目录

各行含所有后代文件，排除发行根本身。父子行彼此重叠。

| 排名 | 相对路径 | 文件数 | 递归 MiB |
| ---: | --- | ---: | ---: |
| 1 | `_internal/` | 252 | 200.377 |
| 2 | `_internal/cv2/` | 12 | 81.885 |
| 3 | `_internal/PyQt5/` | 35 | 65.776 |
| 4 | `_internal/PyQt5/Qt5/` | 29 | 54.448 |
| 5 | `_internal/PyQt5/Qt5/bin/` | 16 | 51.604 |
| 6 | `resources/` | 375 | 28.014 |
| 7 | `_internal/numpy.libs/` | 2 | 19.995 |
| 8 | `resources/memo/` | 10 | 16.077 |
| 9 | `resources/fonts/` | 2 | 10.064 |
| 10 | `resources/fonts/primary/` | 1 | 10.064 |
| 11 | `_internal/numpy/` | 13 | 6.494 |
| 12 | `_internal/rapidfuzz/` | 8 | 5.497 |
| 13 | `_internal/numpy/_core/` | 2 | 4.038 |
| 14 | `_internal/pypinyin/` | 38 | 3.204 |
| 15 | `_internal/rapidfuzz/distance/` | 3 | 3.136 |
| 16 | `_internal/PyQt5/Qt5/plugins/` | 13 | 2.844 |
| 17 | `_internal/numpy/random/` | 9 | 2.087 |
| 18 | `_internal/PyQt5/Qt5/plugins/platforms/` | 1 | 1.409 |
| 19 | `resources/templates/` | 235 | 0.708 |
| 20 | `resources/icons/` | 80 | 0.650 |

### 重复、调试和交付用途

- **实测** 全部文件按长度及 SHA-256 分组，有 34 组相同内容，组内首份之外有 43 份，合计 452,265 bytes（0.431 MiB，含空文件）。这是磁盘内容重复量。即使内容相同，不同加载路径也可能各有用途。
- **实测 + 静态** 两侧 `resources/templates/malwarfare/runtime_1920_2560/` 的 19 个文件和 `runtime_3840/` 的 14 个文件分别逐一相同，外置重复量合计 428,040 bytes。冻结模型通过模块相对路径读 `_internal`；英文 legacy 通过 EXE 旁的模板目录读资源。保留内部模型、配置、3840 清单所列 Python 文件和外部 legacy 模板。只把两棵外部 frozen 子树作为候选。
- **实测** `resources/db/db_backups/` 有三份备份。只有 enemies.db 与活动库逐字节相同，maps.db 和 mutators.db 虽同长度却内容不同。转为单列备份会改变离线恢复材料，必须保留同版恢复来源。
- **静态 + 实测** `src.settings_window.test_setting` 已进 PYZ，压缩条目仅 863 bytes；源码以 FakeMainWindow 单独开测试窗口。未接入主流程的死亡摇篮组件与旧 map_processor 也在 PYZ，死亡摇篮数字模板 29 个文件共 0.007 MiB。反之，`game_state_service.py:15` 确实导入 debug_utils，`main.py:34` 导入 DPI 诊断；以名称批量排除会伤及启动依赖。
- **候选** pypinyin 的类型提示、NumPy 的 `_multiarray_tests…pyd` 和空字体占位有审查价值。需分别查包内惰性导入和 wheel hooks，再决定是否过滤。保留许可证和所需 metadata。未见录像、训练集、根 tests 树、运行日志、本机 settings.json 或 ONNX 模型进入主包。`resources/ocr/` 无文件。PDF 和端口修复 BAT 是脚本明确交付的附件。

## 3. 原始归档查验和 7z 对照

### 归档身份

仓库内（含忽略的 build 目录）找到六份既有审计 7z。逐一将文件相对路径、长度和 CRC32 与当前发行目录对照，空文件按零长度校验。`build/size-audit-v108/official-final.7z` 的 **630/630 个文件匹配，无额外文件**，`7z t` 通过。它可作为当前目录的一份现成归档。其 SHA-256 为 `365ae7c1a37fefc23ad8b99dc0c69d63519b2484e1643c41a853e3cfcd0352c2`，以下数值未以其他目录代替发行品。

| 同目录已有归档 | 文件数 | 与当前同路径、同长度、同 CRC 的文件数 | 物理长度（bytes） |
| --- | ---: | ---: | ---: |
| official-final.7z | 630 | 630 | 76,813,373 |
| stage3-final.7z | 630 | 628 | 76,809,488 |
| stage2-headless.7z | 1,892 | 628 | 82,807,121 |
| stage1-qt-trim.7z | 1,289 | 616 | 83,166,777 |
| stage0-baseline-rebuild.7z | 1,400 | 616 | 86,598,562 |
| baseline-no-addon.7z | 1,396 | 572 | 86,465,441 |

匹配归档的头部为 10,619 bytes，方法为 `LZMA2:27 LZMA:20 BCJ2`，solid 开启，2 个块。头部可识别编码链和字典属性；无法据此反推创建软件、线程数或用户 GUI 设置。未在审计范围内找到用户所说的约 98 MB Bandizip 原件。上一版[审计报告](packaging_size_audit_v108.md)记录的是 1,399 文件、301,988,103 bytes 的另一份同名目录；旧 Bandizip 结果为 102,437,797 bytes（97.692 MiB）。这是历史记录，与用户口述相容，不能鉴定用户当时上传的文件。

### 压缩方法与可复现口径

两种工具均读取现有发行目录；所有新归档、候选副本只写入系统临时目录。本轮没有执行 PyInstaller。以下为 PowerShell 参数示意，`$archive` 指系统临时目录中的新文件绝对路径。两行分别在指定工作目录执行，归档名须不同。

```powershell
# 工作目录为 dist，Bandizip 带上发行目录名
bz c -l:9 -fmt:7z -r -y $archive Keiframe_Release_v108

# 工作目录为 dist/Keiframe_Release_v108，内容位于归档根
7z a -t7z -mx=9 -m0=lzma2 -md=128m -mfb=273 -ms=on -mmt=2 $archive .
7z l -slt $archive
7z t $archive
```

Bandizip CLI 的 9 为其最高等级，产物为 `LZMA2:26`（64 MiB 字典）、solid、1 块、头部 12,380 bytes。7-Zip 指定 128 MiB 字典、273 fast bytes、两线程，其自动可执行文件过滤使头部显示 BCJ2 等方法，2 个 solid 块。两种完整包均通过完整性测试。**工具、过滤器、字典、分块与根目录布局存在差别**，本轮二者相差 2.047 MiB 是两个明确交付方案的实测差值。不能归因为某一参数，也不能推定与未知 GUI 设置等价。

### 完整目录与完整候选包（已实测确认）

除第一行外，全表使用上面的同一 7-Zip 命令、相同输入起点和目录布局。每个候选从完整目录独立计算；对单列文件用排除参数直接读取原目录。表中“节省”均相对完整 7-Zip 基准。拆成附件时必须另计附件及解压路径；下载全套不会免费节省这部分内容。

| 临时归档输入 | bytes | 7z MiB | 十进制 MB | 节省 MiB |
| --- | ---: | ---: | ---: | ---: |
| Bandizip 7.30 Beta x64，完整目录 | 78,959,974 | 75.302 | 78.960 | 不同工具 |
| 7-Zip 23.01 x64，完整目录 | 76,813,373 | 73.255 | 76.813 | 0.000 |
| 外部两套净网 frozen 副本及 db_backups 单列 | 76,806,189 | 73.248 | 76.806 | 0.007 |
| 十张笔记 PNG 无损重压，仍含全部笔记 | 76,585,818 | 73.038 | 76.586 | 0.217 |
| 单列使用说明 PDF | 74,917,164 | 71.447 | 74.917 | 1.808 |
| 单列字体目录 | 72,141,479 | 68.799 | 72.141 | 4.455 |
| 去掉 opengl32sw.dll（仅作风险对照） | 72,005,318 | 68.670 | 72.005 | 4.585 |
| 单列地图笔记目录 | 60,099,342 | 57.315 | 60.099 | 15.940 |
| 单列地图笔记和 PDF | 58,203,175 | 55.507 | 58.203 | 17.748 |
| 单列地图笔记、PDF 和字体 | 53,536,959 | 51.057 | 53.537 | 22.198 |

PNG 对照在单独的临时副本中做。对原 PNG 的 IDAT 流尝试 zlib 等级 9 与 Pillow PNG 优化，后者要求 IHDR、PLTE、tRNS 一致。保留原有其他块，逐图验证解码后的尺寸和 RGBA 字节相同，仅取变小的候选。10 张合计减少 296,993 个磁盘字节，整包只省 227,555 bytes。未在 Qt 真机显示这些临时文件。

**固定开销与压缩性。** 完整 7-Zip 成品占发行原始字节的 31.21%，Bandizip 为 32.08%。下表把指定文件单独放入新 solid 7z，使用同一组 7-Zip 参数。这些集合有交叉，且整包会共享字典、改变分块与头部，**独立压缩值既不能相加，也不能当作裁剪收益**。

| 独立输入 | 原始 MiB | 独立 7z MiB | 压后 / 原始 |
| --- | ---: | ---: | ---: |
| Qt 整棵 _internal/PyQt5 | 65.776 | 16.472 | 25.0% |
| OpenCV 整棵 _internal/cv2 | 81.885 | 19.592 | 23.9% |
| NumPy、numpy.libs 和 dist-info（EXE 内条目另计） | 26.712 | 4.839 | 18.1% |
| Keiframe.exe（含混合 PYZ） | 4.255 | 3.980 | 93.5% |
| python310.dll + base_library.zip（CPython 样本） | 4.978 | 1.494 | 30.0% |
| 地图笔记及背景 | 16.077 | 15.942 | 99.2% |
| 字体目录 | 10.064 | 4.453 | 44.3% |
| 两侧 Malwarfare 资源树（含外部 legacy） | 1.010 | 0.394 | 39.0% |
| 整个外置 resources | 28.014 | 21.461 | 76.6% |
| 使用说明 PDF | 2.070 | 1.809 | 87.3% |
| 外部两棵 frozen 副本 + db_backups | 0.627 | 0.363 | 58.0% |
| RapidFuzz 外置文件 | 5.497 | 0.807 | 14.7% |
| pypinyin 外置文件 | 3.204 | 0.558 | 17.4% |

- DLL/PYD 的机器码压得动，单个 cv2.pyd 虽有 81.871 MiB，整个 cv2 目录独立归档约 19.6 MiB。Python 标准库和应用所在的 EXE 行为不同，PYZ 模块本身已按条目压缩，整个 EXE 再做 7z 后仍保留约 94%。
- PNG 笔记已高度压缩，只换封装或再提高压缩等级收益小；**将其整个移出主包，节省却接近其磁盘体积**。反过来，删除 0.627 MiB 的数据库备份与重复模型，只让完整包减少 0.007 MiB，而该集合单独压缩还有 0.363 MiB。处理“压不动”和处理“跨文件重复”要依据不同的整包对照。
- OCR 应区分两套。小型净网 NPZ、模板、manifest 随主包发；敌方组成所用 PP-OCRv5 大模型在当前主包占零。保留 addon 能力仍需主包中的 OpenCV DNN。不能用历史 ONNX 大小估计当前收益。

## 4. 构建配置与发行品的实际对应

| 检查点 | 证据及影响 |
| --- | --- |
| 入口与环境 | `build-keiframe.bat:14–35` 切根目录、清理 build/dist、调用 `python/python.exe -m PyInstaller --clean Keiframe.spec`，再从 dist/Keiframe 复制 onedir 内容。`Keiframe.spec:82–91` 明选 src/main.py 并把项目内 site-packages 加入搜索路径。未发现本入口另外调用 Qt 裁剪或无 pandas 的 spec；本轮未执行脚本。 |
| 成品与源码偏差 | `build/Keiframe/Keiframe.exe`、`PYZ-00.pyz` 分别与当前发行 EXE、EXE 内 PYZ 逐字节相同。配套 `Analysis-00.toc:103–127` 可见 build/python-headless hooks 及 pandas 排除；当前 spec 反而在第 95 行强制导入 pandas。TOC 属于已有构建旁证，不能证明谁或哪次提交组装了发行包。 |
| 两份 requirements | 根清单显式列 pandas、openpyxl、opencv-python-headless、PyInstaller；`src/requirements.txt` 给出 pandas 3.0.0、NumPy 2.4.2、headless 4.13.0.92，另列 Pillow、pynput、skimage、win32gui。BAT 没有安装上述任一清单。发行品可见 CPython 3.10、numpy-2.2.6、cv2 5.0.0.93 headless；检查到的项目内 python 环境同时有 opencv_python 与 opencv_python_headless 元数据。多个 wheel 共享 cv2 名称，元数据本身不能鉴定生效的二进制。 |
| Excel 链 | `src/settings_window/tabs.py:293–294` → `settings_window.py:757、783`、setting_data_handler → `utils/excel_utils.py:1、41` 的 DataFrame、ExcelWriter、read_excel，`utils/data_validator.py:84` 和 `settings_window/complex_inputs.py:248` 也用 pandas。冻结 EXE 中三个对应模块的代码对象却显示 Workbook/load_workbook 或 ExcelUtil，PYZ 中无 pandas，磁盘也无 pandas 目录或原生扩展。只给**当前源码**加 excludes 会破坏设置入口。 |
| src 全收集与强制导入 | `Keiframe.spec:12、92–102` 收集全部 src 子模块；test_setting 是已证实的非生产入口。aiohttp、win32api、pypinyin 分别用于 6119、Win32 与拼音，rapidfuzz 在 `game_readers/enemy_composition_matcher.py:130` 惰性导入，sip 是绑定支持。src.config、logging_util 有直接引用。删除冗余 hiddenimport 拼写本身未必改变依赖闭包；还要覆盖 `map_handlers/malwarfare/__init__.py:22–39` 的惰性导入和 addon 装/卸两态。 |
| Qt 和间接依赖 | 发行 Qt5 目录只含 bin、plugins，无 translations/QML。plugins 只余 13 个文件，覆盖 Windows 平台、样式、图像、SVG 图标、音频/媒体服务、bearer 和 M3U。源码 `presentation_modules/sound_player.py:9` 使用 QMediaPlayer，`control_window.py:34–35` 载入 SVG，`tray_manager.py:27` 创建托盘。PE 普通导入表证实 Qt5Multimedia、dsengine 和 wmfengine 依赖 Qt5Network。剩余 M3U 插件仅 0.032 MiB，需核对播放后端；opengl32sw、ANGLE、D3D 和不同版本的运行库要覆盖无硬件加速、远程桌面及 DLL 搜索顺序。整类 Qt 裁剪和 translations 收益不能再套用。 |
| OpenCV、FFmpeg 和 NumPy | `Keiframe.spec:128–134` 按目标 basename 前缀过滤 a.binaries；对**整个发行树**查找 `opencv_videoio_ffmpeg*` 为零，排除目标已实现。cv2/version.py 写 headless=True，cv2.pyd 内构建信息也显示 GUI=NONE，同时 FFMPEG=YES (prebuilt binaries)。后者是 wheel 的构建能力，不能推出有独立 FFmpeg DLL 随包。当前用 mss 截图（game_state_service.py:333），未发现生产 VideoCapture/VideoWriter，未见第二套 Qt GUI 由 OpenCV 带入。cv2.pyd 内仍列 dnn、imgcodecs、imgproc、stitching、videoio 等；单体已经编译，按目录排除不会剥离内部模块。净网 time/count 用 np.linalg.norm，NumPy 的核心和 linalg 原生文件中可识别随包 OpenBLAS 名称。 |
| 资源和复制 | `Keiframe.spec:18–80` 收集净网配置、模型及 3840 声明的推理文件到 _internal；BAT 第 45 行 robocopy /E 再复制外部资源，排除 OCR addon；第 71–74 行另组 addon，第 82–83 行加 PDF/BAT。两处 runtime 重复已逐文件验证。xcopy 搬运 onedir 输出会占构建区空间，但单独归档发行目录不会再包含同级另一套程序。普通资源由 `src/utils/fileutil.py:6、35` 从 EXE 旁解析；净网 `runtime_3840.py:45、167–189` 使用模块相对路径，校验资源 SHA 和声明的 Python 文件存在性。 |
| 其他大包及可疑内容 | 当前主包目录和 PYZ 未见 Pillow、torch、onnxruntime、pandas；`Keiframe.spec:105–120` 已排除多项。OpenCV + Qt 分别用于数组识别和桌面显示，不能因二者能解码图像就判为重复。没有证据支持低风险整包移除 NumPy、openpyxl、RapidFuzz 或 QtMultimedia。已有 spec 的 upx=True（148、166）不能证明实际使用 UPX，追加 UPX 的净收益待整包 A/B。 |

## 5. 优化方案与优先顺序

节省列指**当前 v108 完整 7z 的变化**。A 为发行层，B 为轻量代码或依赖调整，C 为架构调整。高/中/低投入是相对工程量估计，包含验证。效果标为“待验证”的项目不计入目标预算。

| 优先级与项目 | 当前依据及预计节省的 7z 体积 | 成本 / 功能风险 | 影响与验收要求 |
| --- | --- | --- | --- |
| P0 · A 固定归档输入与高压参数 | 同一正式目录，本轮 7-Zip 相对 Bandizip 小 2.047 MiB；直接分发已匹配的 official-final 即为 76.813 MB | 低 / 低 | 只选择主包根。记录文件数、归档 bytes、SHA、解压后的 EXE/resources 位置；addon 保持单列 |
| P0 · B 对齐源码、spec 与已验证字节的发行方案 | 成品已有 headless、Qt 精简、openpyxl-only、无 FFmpeg DLL、无主包 ONNX。相对当前再省 **0 MiB**，作用是防回涨。下次构建体积差待验证 | 中 / 中 | 先找到与冻结 Excel 行为及构建环境匹配的版本，在隔离副本比对后恢复维护。覆盖设置窗口启动、地图/突变导入导出、空白/NaN、净网 count、时间文本、保护/列宽、旧工作簿和副本数据库覆盖语义；保留 NumPy 识别 |
| P1 · A 离线 PDF 单列 | 全包对照少 **1.808 MiB**；含完整程序和笔记的主包 74.917 MB | 低 / 低 | 同版 PDF 作为单独下载，程序无需改变；用户一次下载获得的离线材料有变化 |
| P1 · A 无损重压内置笔记 PNG | 10 张逐像素相同，完整包少 **0.217 MiB** | 低 / 低 | 仍用原名、原格式和背景；用现有 Qt 在目标 DPI 复查透明度和笔记显示。若只为上传 80 MB 可跳过 |
| P1 · B 将地图笔记作为资源包（仅在需要 <70 MB 时） | 单列笔记少 **15.940 MiB**；同时单列 PDF 的联合对照少 **17.748 MiB** | 低至中 / 中 | `src/memo_overlay.py:72–113` 依赖 background.png 和地图名.png。安装时恢复原目录，未安装时给明确提示；测试已有自定义笔记、同名覆盖、临时和常驻显示。完整用户仍下载两部分 |
| P2 · B 字体子集或可选字体 | 完全单列字体实测少 **4.455 MiB**；子集方案实际收益待验证 | 中 / 中 | `src/main.py:40–44` 有 Microsoft YaHei 回退；中文、英文、动态地图/玩家名、自定义文字、缺字回退、换行与 DPI 均需测。包含全部字符和同样字形时不能按“去掉全部字体”计 |
| P2 · A 收紧资源和非生产模块 | 两棵外置 frozen 副本及三份备份联合仅少 **0.007 MiB**。test_setting 的 PYZ 条目 863 bytes；其余 src 收集、类型提示、测试 PYD、M3U 插件的独立整包收益待验证 | 低至中 / 分项低至中 | 先隔离已知测试入口。模型需跑中英文、1920/2560/3840 和清单校验；备份单列前验证恢复；M3U 需测音频播放。不要按扩展名清全树 |
| P2 · B 调整拼音或匹配后端 | pypinyin 与 RapidFuzz 外置文件分别独立压缩 0.558、0.807 MiB；替代实现净收益待验证 | 中 / 中 | `src/ui_setup.py:416` 首字母检索、敌方组成模糊匹配的分数/排序及 SIMD 回退均有用户可见结果，对照多音字、并列候选、旧 CPU 和 addon |
| P3 · B 调整 Qt 后端 | 去掉 opengl32sw.dll 的整包实验少 **4.585 MiB**，仍为 72.005 MB。精简其他插件、改音频后端的净收益待验证 | 中至高 / 高 | 此文件提供软件渲染回退。低规格 GPU、远程桌面、无加速、透明覆盖层、多屏 DPI、音频和托盘验收前保留默认包；不要将全部 Qt 重新裁一遍 |
| P3 · B 定制 OpenCV / 数值库 | cv2 独立 19.592 MiB 左右。headless 与 FFmpeg 排除已生效；新编译的净收益**待验证** | 高 / 高 | 建最小 wheel 或独立后端，覆盖颜色/几何变换、PNG 解码、模板匹配及可选 DNN ONNX、CPU 指令集、NPZ 与数值一致性。先记录样本识别输出和线程耗时。升级或删除 OpenBLAS 须实际重建并测 NumPy |
| P3 · C 全 Rust / 全 C++ / 混合 | 三者均无可运行的同功能候选，节省量**待验证**。预算锚点见下节 | 全量极高，混合中至高 / 高 | 用同一份资源、相同 addon 合同、相同压缩命令测原型；再决定是否迁移 |

**实施顺序。** 先留存当前内容匹配归档的散列和文件清单，安排一次隔离的可复现构建；用户本轮未授权重建。若目标只到 80 MB，可在这里停。想多留一点余量，优先单列说明书；仍要求完整单件时，无损 PNG 优化只增加约 0.23 MB 余量。有明确的 70 MB 主包需求且接受第二个下载时，优先单列笔记。除非更严格的单件目标长期存在，暂缓 Qt 渲染回退裁剪、定制 OpenCV 和原生重写。

## 6. Rust、C++ 与混合迁移的体积预算

**没有证据可承诺原生包为 10 MB，或为 Rust、C++ 各给一个可靠成品大小。** 为回答“能压到多大”，另外将当前发行品中可跨语言沿用的文件组合实压。以下使用相同的 7-Zip 参数，均为资产或代理组合，均不能运行。它们为新程序划出明确的**剩余预算**。

| 实测输入组合 | 归档 MiB | 十进制 MB | 对同功能原型意味着什么 |
| --- | ---: | ---: | --- |
| 外部 resources + PDF + BAT | 23.271 | 24.401 | 仅这些现成交付内容就超过 10 MB。在 50 MB 内约余 25.599 MB，供程序、GUI、识别引擎及其余内部资源使用 |
| 上述内容 + 当前 Qt5 的 bin、plugins（不含 PyQt 绑定） | 37.739 | 39.572 | 若复用现有 Qt 原生部署，在 50 MB 内只余约 10.428 MB 给程序与识别等内容 |
| 上述 Qt 组合 + 当前 cv2.pyd 作为视觉引擎大小代理 | 57.334 | 60.119 | PYD 带 Python 绑定，原生实现会换用别的库。约 60 MB 展示了保留同量级视觉二进制的成本，不能当作原生预计成品 |

这些数字不是通用下限，改变资源编码、单列资源、新编译模块或调整联接方式都会改变结果。不能把三行相减后再叠加到另一个 solid 包。如果采用 Win32 原生界面、只随包交付所需视觉内核，并把新增程序和引擎控制在剩余约 25.6 MB 内，**同内容 50 MB 有条件可行**。采用与当前规模相当的 Qt 和视觉运行库时，不宜把 50 MB 当交付承诺。

| 路线 | 可真正移除及仍需承担的成本 | 迁移难点、维护与验证 |
| --- | --- | --- |
| 全 Rust | 最后一个 Python 路径退出后才可移除解释器、PYZ、PyQt 绑定、Python 版 Excel/HTTP/Win32/键盘工具与 NumPy wheel。纯 Win32 GUI 可省 Qt；沿用 Qt 或 Rust OpenCV 绑定仍须核算原生库。字体、笔记、数据库、净网模型及可选敌方 OCR 仍有交付成本 | 6119 JSON、SQLite、计时状态机较易对照。Win32 消息循环、透明无焦点窗口、托盘、热键、DPI 和屏幕捕获需要重新实现和整体验证；Qt/视觉 FFI、打包及长期升级增加维护面。保持 Excel 语义需要等价 XLSX 处理 |
| 全 C++ | 同样能去掉 CPython 与 Python 绑定；Qt Widgets、OpenCV 可直接复用 C++ 接口。同框架迁移保留 Qt 运行库，选择 Win32 或最小化链接才可能取得更大的净收益。需保留 SQLite（系统或随包）、图像解码、识别及音频实现 | UI 行为映射、OpenCV 算子复用相对直接；对象生命周期、热键线程、截图缓冲、退出/跨局重置、ABI 和原生依赖发布需维护。净网 NPZ/manifest 和 OCR 输出要逐帧对齐，不能只演示主窗口 |
| Python + Rust/C++ | 单独迁移热点仍需 Python、Qt 和未替换的 wheel，加一份原生库可能增大包。只有全部使用点移出且从依赖闭包中消失，才可能省去整个 cv2/NumPy 等后端。若复用 Qt UI，Qt 成本保留 | 适用于有明确大小或性能目标的隔离识别后端试验。需维护两种工具链、数组交换、异常/线程边界、addon 调用与版本一致性；以“能删去最后一个旧依赖”为验收条件 |

**可借鉴范围。** 项目 README 将 ylkangpeter 的 sc2timer 列为来源。此次可读项目材料中未见可将其 C++ 主程序、压缩器、功能矩阵和资源逐项对齐的交付证据。原作者据称从 60 多 MB 到 10 MB 以内只能作为比较线索。若以后取得原作者材料，优先比较 GUI 是否用 Win32、视觉库如何链接、是否内置地图笔记/字体、是否支持 Excel、净网三套分辨率和可选 DNN。独立模板工具也不能代替此比较。

## 7. 最终建议与验证边界

**发布当前版本优先采用现有 Python 发行品。** 在完整内容和原始文件不变的条件下，可按 **76.813 MB** 对外规划；如必须使用本机 Bandizip CLI，按 **78.960 MB**。两种归档都已低于十进制 80 MB。下版源码直接重建的结果待验证，应先解决 spec 与发行 Excel 实现的偏差，再按最终归档的字节数决定能否上传。单列 PDF 的约 75 MB 和单列笔记的约 60 MB 分别对应两种不同的用户交付条件。

**本轮验证**覆盖所有发行文件的递归长度、分类总和、前 30 文件/前 20 目录、SHA-256 重复组、EXE/PYZ 条目、现有归档的路径/长度/CRC、匹配归档完整性、两套压缩程序、整包候选与独立压缩、PNG 尺寸与像素。系统临时归档和候选副本已清理。

**仍待验证**的项目包括 Windows 干净机首次启动、Win10/11 显示后端/系统字体、托盘热键、多屏/100% 与高 DPI、音频、真实 SC2 的 6119/截图、中英文净网及敌方 OCR（含 addon 缺失和安装）、旧 Excel 往返与数据库恢复、从当前仓库重新打包的体积及网盘实际限额。候选归档大小仅证明压缩结果。此次仅新增本报告，未改业务、配置、资源、依赖、数据库或发布布局；不存在本轮数据迁移。
