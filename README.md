# KeiFrame

KeiFrame 是一个面向《星际争霸 II》合作模式的 Windows 桌面辅助工具。它读取本机游戏客户端公开的 `127.0.0.1:6119` 状态接口，并结合屏幕截图、OpenCV 模板匹配和 PyQt5 覆盖层，展示地图时间线并提供事件提醒。

本仓库是开发者向源码仓库。普通用户发行版与使用说明维护在[金山文档](https://www.kdocs.cn/l/cvCj6uEth9os)。当前界面和提醒文本主要面向简体中文用户。

> KeiFrame 不修改游戏文件、不注入游戏进程，也不读取受保护的游戏内存。图像识别只处理本机游戏窗口截图。

## 主要能力

- 从 SC2 本机 6119 API 获取游戏时间、玩家列表和游戏内/外状态。
- 根据玩家数据自动识别合作任务地图，也允许手动搜索和切换地图。
- 从 SQLite 时间线加载地图事件与突变事件，显示下一事件并提前弹出提示。
- 识别敌方种族和突变因子；按配置显示图标、文字与音频提醒。
- 在可选 PP-OCRv5 addon 可用时识别敌方组成，并以无声文字提示名称；没有 addon 时该识别功能单独禁用。
- 提供自定义倒计时、地图笔记、泽拉图神器提醒和补给提醒。
- 对“净网行动”使用画面文字模板识别处理动态倒计时。
- 对部分存在分支的地图使用小地图红点检测自动选择版本，用户可手动覆盖。
- 提供设置窗口、全局快捷键、系统托盘和可锁定的置顶窗口。

## 运行要求

- Windows 10/11。项目依赖 Win32 窗口句柄、全局快捷键、DPI 和屏幕捕获能力，不保证能在 macOS 或 Linux 运行。
- Python 3.10 为当前随项目分发的嵌入式运行时基线。
- 《星际争霸 II》客户端；自动读取对局状态时需要本机 `127.0.0.1:6119` 可用。

## 从源码运行

在仓库根目录使用 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m src.main
```

必须从仓库根目录启动，项目使用 `src.*` 绝对导入，资源路径也以项目根目录为基准。根目录 `requirements.txt` 是开发环境的宽松依赖清单；`src/requirements.txt` 是另一份版本化清单，两者目前并不完全一致。

首次运行会使用 `src/config.py` 中的默认配置。本地设置由根目录的 `settings.json` 覆盖，该文件属于用户状态并已被 Git 忽略。

## 项目结构

```text
Keiframe/
├── src/
│   ├── main.py                         # 进程入口、日志、DPI 与 QApplication
│   ├── qt_gui.py                       # 主窗口、Qt 信号槽和兼容入口
│   ├── app_runtime.py                  # 运行时装配、对局重置和退出清理
│   ├── game_state_service.py           # 6119 轮询、截图和共享游戏状态
│   ├── game_readers/                   # 底层画面识别器
│   ├── map_handlers/                   # 地图时间线、分支和特殊地图状态机
│   ├── event_managers_and_notifiers/   # 倒计时、突变、神器、补给和敌方组成提醒
│   ├── presentation_modules/           # Toast、文字覆盖层和声音播放
│   ├── settings_window/                # 设置、校验及 Excel 导入导出界面
│   ├── ui/                             # 主窗口布局与菜单
│   ├── db/                             # SQLite 连接和 DAO
│   └── utils/                          # 路径、日志、DPI、窗口等工具
├── resources/
│   ├── db/                             # 地图、突变和敌方组成数据库
│   ├── templates/                      # 图像识别模板
│   ├── memo/                           # 地图笔记图片
│   ├── icons/ fonts/ sounds/           # UI 与提醒资源
│   └── enemy_comps/ troops/            # 敌方组成和兵种数据
├── tests/                              # 单元测试、调试脚本与截图样本
├── python/                             # Windows 嵌入式 Python 运行时
├── Keiframe.spec                       # PyInstaller 配置
└── build-keiframe.bat                  # Windows 发布目录构建脚本
```

更完整的项目语境见 [`context.md`](context.md)，运行时模块和数据流见 [`architecture.md`](architecture.md)。参与开发或使用自动化代理前，请先阅读 [`AGENTS.md`](AGENTS.md)。

## 数据与配置

- `resources/db/maps.db`：地图、搜索关键词和地图事件时间线。
- `resources/db/mutators.db`：突变因子元数据和提醒时间线。
- `resources/db/enemies.db`：敌方组成分级数据；当前主窗口未打开该数据库连接。
- `resources/enemy_comps/*.csv`：已确认敌方组成的 t1~t7 注意单位资料；提醒管理器通过共享 Advisor 一次性加载，并按英文或中文组成名查询。
- `src/game_readers/enemy_composition_catalog.py`：19 条敌方组成的 canonical English、已验证中文名、种族和 OCR aliases；这是生产识别与展示的唯一 catalog source of truth。
- `resources/templates/`：突变、种族、补给、小地图和特殊地图识别模板。
- `settings.json`：用户本地覆盖配置，不应提交。

设置窗口支持地图/突变时间线的 Excel 导入导出。导入会覆盖涉及对象的原有数据库记录，修改数据前应先保留对应数据库备份。

## 验证

文档或纯 Python 修改完成后，至少运行：

```powershell
python -m compileall -q src
python -m unittest tests.test_cradle_of_death_phase_detector tests.test_cradle_of_death_wave_manager
git diff --check
```

不要直接运行无筛选的 `unittest discover` 或 `pytest tests`：`tests/` 中包含依赖真实窗口、6119 API、截图样本或人工观察的调试脚本。

图像识别、DPI、全局快捷键和覆盖层位置仍需要在 Windows 与实际游戏环境中手工验证。测试时应记录分辨率、Windows 缩放、游戏语言、ROI 和识别阈值。

## 打包

仅在确实需要生成发布包时运行：

```powershell
.\build-keiframe.bat
```

脚本会递归清理 `build/` 和 `dist/`，调用项目内嵌 Python 的 PyInstaller，然后将除 `resources/ocr/ppocrv5/` 外的运行时资源复制到主发布目录，并在 `dist/KeiFrame_PP-OCRv5_Addon/` 生成独立 OCR addon。主程序没有 addon 时仍可启动，但敌方组成识别会被禁用；安装 addon 后重启即可启用。生成物不应提交到仓库。

## 6119 端口

无法读取游戏状态时，先确认 SC2 正在运行，并检查 `http://127.0.0.1:6119/game/` 与 `/ui/` 是否可访问。仓库中的 `端口修复.bat` 会以管理员权限调整 Windows 网络配置；仅在理解其影响且确实需要时运行。

## 当前限制

- 依赖 Windows、SC2 窗口和固定屏幕区域；不同分辨率、语言、UI 缩放或游戏更新可能降低识别率。
- 敌方组成识别依赖独立 PP-OCRv5 addon；真实游戏中的 tooltip、覆盖层位置、5 秒隐藏和 DPI 组合仍需手工验收。
- `resources/` 是运行时必需内容，源码运行和发布目录都必须保持其结构。
- “死亡摇篮”倒计时、阶段和偷车波次组件已存在并有核心单元测试，但当前尚未接入主窗口的地图选择与生命周期流程。
- README 只描述当前源码行为；普通用户操作流程以发行版使用说明为准。

## 贡献

- 保持画面读取、业务状态机、提醒展示和持久化边界清晰。
- 新地图逻辑放在 `map_handlers/`，底层识别放在 `game_readers/`，不要继续把地图特例堆入主窗口。
- 不写死开发机路径；统一使用 `src.utils.fileutil` 解析运行时路径。
- 后台线程不得直接操作 Qt 控件，应通过信号、槽或主线程定时器传递结果。
- 保留历史公开名称的兼容性，避免与任务无关的大范围重命名或格式化。

## License 与致谢

项目采用 [MIT License](LICENSE)。

KeiFrame 基于 ylkangpeter 的 `sc2timer` 项目继续开发，由 Archer 维护。
