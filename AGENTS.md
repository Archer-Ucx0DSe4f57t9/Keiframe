# AGENTS.md

本文件适用于仓库根目录及其所有子目录。除非更深层目录存在更具体的 `AGENTS.md`，在本项目中工作的自动化代理必须遵循以下约定。

## 开始工作前

1. 阅读根目录的 `README.md`、`context.md` 和 `architecture.md`，确认产品边界与当前装配关系。
2. 检查 `git status --short`，保留用户已有的未提交修改。不要覆盖、回滚或顺手整理无关文件。
3. 从仓库根目录执行命令。项目使用 `src.*` 绝对导入，部分资源路径也依赖项目根目录。
4. 先定位实际调用关系，再修改。README 或注释可能落后于源码，最终以当前代码、数据库结构和构建脚本为准。
5. 只处理用户授权的范围。诊断任务默认只调查和说明，不自行实现修复。

## 项目速览

KeiFrame 是面向《星际争霸 II》合作模式的 Windows 桌面辅助工具：

- Python + PyQt5 主界面和透明覆盖层。
- `127.0.0.1:6119` 本机 API 提供游戏时间、玩家和界面状态。
- `mss` 截取 SC2 窗口，OpenCV 对共享截图执行模板匹配。
- SQLite 保存地图与突变时间线；`settings.json` 保存本地用户覆盖配置。
- PyInstaller `onedir` 发布，`resources/` 在构建后复制到可执行文件旁边。

源码入口是：

```powershell
python -m src.main
```

目标平台是 Windows。窗口句柄、全局快捷键、系统托盘、DPI 与屏幕捕获逻辑不保证跨平台。

## 文档职责

- `README.md`：对外项目介绍、环境、运行、验证和打包入口。
- `context.md`：产品目标、术语、边界、数据来源和当前约束。
- `architecture.md`：运行时组件、线程模型、数据流、生命周期和扩展点。
- `AGENTS.md`：代理的工作规则、修改边界和验证要求。

行为、入口、目录或关键限制发生变化时，同步更新对应文档；不要在四份文档中复制同一大段内容。

## 目录职责

- `src/main.py`：日志轮换、进程 DPI 初始化、Qt 属性和 `QApplication` 创建。DPI 配置必须早于主要 PyQt UI 导入。
- `src/qt_gui.py`：`TimerWindow`，负责装配服务、识别器、管理器、Qt 信号和退出生命周期。
- `src/game_state_service.py`：6119 API 轮询、SC2 窗口截图与共享 `GlobalState`。它只应维护事实状态，不承载 UI 展示。
- `src/game_readers/`：底层图像识别。尽量输出结构化识别结果，不直接控制界面。
- `src/map_handlers/`：地图加载、事件调度、地图分支和地图专属状态机。
- `src/event_managers_and_notifiers/`：倒计时、突变、神器、补给等提醒业务。
- `src/presentation_modules/`：Toast、覆盖文字与音频播放。
- `src/settings_window/`、`src/ui/`、`src/ui_setup.py`：设置窗口及主界面布局。
- `src/db/`：SQLite 连接与 DAO；业务层通过这里访问数据库。
- `src/utils/`：路径、日志、DPI、窗口、校验及 Excel 工具。
- `resources/`：运行时数据库、模板、图标、字体、声音和地图笔记；目录结构属于发布接口的一部分。
- `tests/`：少量可稳定运行的 `unittest` 与大量人工调试脚本、截图样本的混合目录。
- `python/`：随项目分发的 Python 3.10 嵌入式运行时，不是普通源码目录。
- `build/`、`dist/`、`debug/`、日志、缓存、IDE 元数据和本地 `settings.json`：生成物或用户状态，不作为源码修改。

## 实现约束

### 路径与资源

- 保持现有 `src.*` 绝对导入方式。
- 运行时路径统一通过 `src.utils.fileutil.get_project_root()` 和 `get_resources_dir()` 解析，不写死开发机绝对路径。
- 源码环境的项目根目录与 PyInstaller 环境的可执行文件目录含义不同，修改路径逻辑时必须同时考虑两者。
- `Keiframe.spec` 不内嵌 `resources/`；`build-keiframe.bat` 在打包后复制整个资源目录。新增资源要验证源码路径与发布路径。

### Qt、线程与生命周期

- `src/main.py` 的 Windows DPI 和 Qt 高 DPI 属性必须在导入主要 UI 模块及创建 `QApplication` 前设置，不得随意调整初始化顺序。
- 后台线程或异步任务不得直接修改 Qt 控件；使用现有 Qt 信号、槽或主线程定时器。
- 长耗时截图、OCR、网络轮询和模板匹配不能阻塞 GUI 主线程。
- 访问 `game_state_service.state.latest_screenshot` 等共享可变状态时沿用 `screenshot_lock`；读图后尽快释放锁。
- 新后台任务必须尊重 `state.app_closing`，提供幂等的 `reset()` / `shutdown()`，并在 `TimerWindow.safe_exit()` 中接入清理。
- 新游戏和离开游戏会触发 `reset_game_info`。新增有局内状态的组件必须接入重置链路，避免跨局残留。

### 模块边界

- 新地图逻辑优先放在 `map_handlers/`，图像识别放在 `game_readers/`，提醒编排放在 `event_managers_and_notifiers/`，渲染放在 `presentation_modules/`。
- `src/qt_gui.py` 只做装配和信号协调，避免继续累积地图专属算法。
- 识别器不要读写表格、Toast 或数据库；状态机不要自行截屏；展示组件不要决定业务触发条件。
- `CradleOfDeathMapHandler`、阶段检测器和波次管理器当前尚未接入主流程。若完成接入，必须同时处理地图切换、新局重置和安全退出，并补充集成验证。
- `src/map_handlers/map_processor.py` 当前没有进入主装配路径。修改前先确认它是待用组件还是历史代码，不要默认把它当作当前数据源。

### 配置与持久化

- `src/config.py` 是默认值；根目录 `settings.json` 是本地覆盖且已忽略。不要把本机设置内容复制进文档、测试或提交。
- 新增用户设置时，至少检查默认值、外部覆盖、设置控件、校验、保存/加载和旧配置缺字段时的兼容性。
- 数据库访问复用 `DBManager` 和 DAO。新连接应明确生命周期并关闭。
- 修改 `resources/db/*.db` 必须是任务明确要求的数据变更；先说明覆盖语义，并保留或更新备份的意图。
- 设置窗口的 Excel 导入会先删除涉及对象的旧记录再导入，测试时使用副本或可恢复数据。
- 根目录 `requirements.txt` 是宽松开发清单，`src/requirements.txt` 是版本化清单；修改依赖时说明两个环境的影响，不要顺手统一或重排版本。

### 代码风格与兼容性

- 延续周边代码的 4 空格缩进、`snake_case` 函数/变量和 `PascalCase` 类名。
- 使用 `src.utils.logging_util.get_logger(__name__)`。库代码避免新增无条件 `print`，日志不得写入敏感信息或大块原始图像数据。
- 用户可见文字优先沿用既有中英文词汇与游戏内命名。当前不少提示只有简体中文，不要声称已经完整国际化。
- 一些文件名、类名和公开方法有历史拼写问题。除非任务要求迁移，否则保留兼容，不做无关重命名。
- 仓库没有统一格式化器；修改应聚焦任务范围，避免整文件机械格式化。

## 常用命令

开发环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m src.main
```

最小静态验证：

```powershell
python -m compileall -q src
git diff --check
```

当前可稳定自动运行的核心单元测试：

```powershell
python -m unittest tests.test_cradle_of_death_phase_detector tests.test_cradle_of_death_wave_manager
```

不要默认运行无筛选的 `unittest discover` 或 `pytest tests`。多个 `test_*.py` 实际是截图工具、实时 API/窗口实验或需要本地图像的人工脚本。

打包命令：

```powershell
.\build-keiframe.bat
```

该脚本会递归删除 `build/` 和 `dist/`。只有用户明确要求验证或生成发布包时才运行，且不要提交生成物。

## 按变更类型验证

- 纯逻辑：编写隔离的 `unittest`，用伪造状态、Toast 或识别结果代替真实游戏。
- 识别算法：使用对应截图样本和专用调试脚本，记录分辨率、游戏语言、ROI、缩放与阈值。
- GUI / DPI / 坐标：在 Windows 上手工启动，至少检查 100% 缩放；涉及坐标换算时再覆盖目标 DPI、分辨率和多显示器。
- 6119 API、全局快捷键、托盘或 SC2 窗口检测：需要本机运行游戏后手工验证。无法验证时在交付中明确说明。
- 配置：验证旧 `settings.json` 缺少新字段时仍可用默认值启动。
- 数据库：验证事务、旧数据兼容和备份恢复路径。
- 发布：仅按需打包，并确认最终可执行文件旁有完整 `resources/`。

## 禁止与谨慎事项

- 不编辑或提交 `build/`、`dist/`、`debug/`、`Keiframe.log`、缓存、IDE 元数据、本地 `settings.json` 或临时 Excel。
- 不为了缩小仓库删除 `tests/` 的大型截图、`resources/` 资产或嵌入式 Python 文件，它们可能用于识别回归和离线发布。
- 不执行 `端口修复.bat`，除非用户明确要求修复 6119 端口并理解它需要管理员权限且会调整 Windows 网络配置。
- 不使用破坏性 Git 命令，不覆盖用户未提交修改，不提交生成物。
- 不把尚未接入主流程的模块描述为已发布功能。

## 完成标准

交付时必须说明：

- 修改了哪些文件和行为。
- 运行了哪些自动检查及结果。
- 哪些 Windows、游戏、DPI、识别或打包场景未实际验证。
- 是否存在兼容性、数据迁移、资源或发布目录影响。

新增功能应有与风险相称的测试。只修改文档时不需要启动游戏或打包，但仍应检查链接、路径、命令、`git diff --check`，并确认未触碰代码与资源。
