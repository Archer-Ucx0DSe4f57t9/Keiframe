# KeiFrame

[English](README.md)
[![Deep Dive on zread](https://img.shields.io/badge/zread-Technical%20Notes-blue)](https://zread.ai/Archer-Ucx0DSe4f57t9/Keiframe)  
[![License](https://img.shields.io/github/license/Archer-Ucx0DSe4f57t9/keiframe)](https://github.com/Archer-Ucx0DSe4f57t9/keiframe/blob/main/LICENSE)

KeiFrame 是一个面向《星际争霸 II》合作模式的时间线驱动事件提醒的背板工具。

本仓库仅包含开发者向源码版本。  
普通用户发行版与使用说明另行维护于https://www.kdocs.cn/l/cvCj6uEth9os

维护者：Archer（Nga ID：天童凯伊）

---

## 项目说明

KeiFrame 基于 `sc2timer` 进行结构重构与扩展开发。

核心目标：

- 时间线抽象
- 事件驱动提醒机制
- 可配置渲染层
- 音频通知系统
- 可扩展数据定义

本软件不修改游戏文件，不注入进程，不访问受保护资源。

---

## 架构概览

### 时间线引擎
- 基于 SQLlite的时间定义
- 倒计时生命周期管理
- 事件调度系统

### 表现层
- GUI 设置界面
- 字体与颜色配置
- 提示渲染逻辑

### 音频层
- 自定义音频播放
- 事件触发映射

地图数据与核心逻辑完全解耦。

---

## 项目结构

对于项目不同模块的具体功能，建议点击顶部zread链接查看。但请注意，zread对于游戏具体功能有不少错误。
```

Keiframe/
├── src/                              │   ├── main.py                       # 应用程序入口点
│   ├── config.py                     # 中央配置 (由 settings.json 覆盖)
│   ├── config_hotkeys.py             # 快捷键绑定配置
│   ├── qt_gui.py                     # 主 Qt 窗口和信号/槽连接
│   ├── control_window.py             # 锁定/解锁控制面板
│   ├── game_state_service.py         # 通过端口 6119 监控游戏状态
│   ├── game_time_handler.py          # 时间流逝管理
│   ├── language_manager.py           # 多语言支持 (EN/ZH)
│   ├── memo_overlay.py               # 带有动画的地图备注覆盖层
│   ├── countdown_manager.py          # 并发计时器管理
│   ├── db/                           # 数据库层
│   │   ├── db_manager.py             # SQLite 连接管理
│   │   ├── daos.py                   # 数据访问对象基类
│   │   ├── map_daos.py               # 地图数据操作
│   │   ├── mutator_daos.py           # 突变数据操作
│   │   └── enemy_comp_daos.py        # 敌方组成数据操作
│   ├── map_handlers/                 # 地图识别和事件管理
│   │   ├── map_processor.py          # 地图模板加载器和处理器
│   │   ├── IdentifyMap.py            # 地图识别逻辑
│   │   ├── map_event_manager.py      # 通用地图事件调度
│   │   ├── map_loader.py             # 地图配置加载
│   │   ├── malwarfare_map_handler.py # 净网行动的画面识别模块
│   │   ├── malwarfare_event_manager.py # 净网行动的事件管理器
│   │   └── malwarfate_ocr_processor.py # 净网行动的OCR文本识别引擎
│   ├── mutaor_handlers/              # 突变和种族识别
│   │   ├── mutator_and_enemy_race_recognizer.py # 模板匹配识别器
│   │   └── mutator_manager.py        # 突变数据管理
│   ├── output/                       # 输出和展示层
│   │   ├── message_presenter.py      # 带有轮廓的警报文本渲染
│   │   ├── toast_manager.py          # Toast 通知管理
│   │   └── sound_player.py           # 音频播放系统
│   ├── settings_window/              # 配置 UI
│   │   ├── settings_window.py        # 主设置对话框
│   │   ├── tabs.py                   # 设置选项卡组织
│   │   ├── widgets.py                # 自定义 UI 组件
│   │   ├── setting_data_handler.py   # 设置数据管理
│   │   └── complex_inputs.py         # 复杂输入组件
│   ├── ui_setup.py                   # UI 初始化助手
│   ├── app_window_manager.py         # 窗口管理实用程序
│   ├── tray_manager.py               # 系统托盘图标和菜单
│   ├── troop_util.py                 # 部队相关实用程序
│   └── utils/                        # 实用程序模块
│       ├── fileutil.py               # 文件路径操作
│       ├── logging_util.py           # 日志配置
│       ├── math_utils.py             # 数学计算
│       ├── font_uitils.py            # 字体加载和管理
│       ├── window_utils.py           # 窗口定位实用程序
│       ├── data_validator.py         # 数据验证助手
│       ├── debug_utils.py            # 调试实用程序
│       └── excel_utils.py            # Excel 文件操作
├── resources/                        # 运行时资源
│   ├── db/                           # SQLite 数据库文件
│   │   ├── maps.db                   # 地图数据库
│   │   ├── mutators.db               # 突变数据库
│   │   ├── enemies.db                # 敌方组成数据库
│   │   └── db_backups/               # 数据库备份文件
│   ├── enemy_comps/                  # 敌方组成 CSV 文件
│   ├── templates/                    # 识别模板
│   │   ├── en_blue/ en_green/ en_orange/ en_yellow/
│   │   ├── zh_blue/ zh_green/ zh_orange/ zh_yellow/
│   │   ├── races/                    # 种族图标模板
│   │   └── mutators/                 # 突变图标模板
│   ├── icons/                        # 应用程序图标
│   ├── fonts/                        # 自定义字体文件
│   ├── sounds/                       # 警报声音文件
│   ├── memo/                         # 地图备注图像
│   └── troops/                       # 部队图标资源
├── python/                           # 嵌入式 Python 环境
├── requirements.txt                  # Python 依赖项
└── build-keiframe.bat                # Windows 构建脚本


```

---

## 开发环境配置

```bash
git clone https://github.com/<your-github>/keiframe.git
cd keiframe

python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

python -m src.main

```

----------

## 端口说明（6119）

默认监听端口：`6119`

若端口绑定失败：

-   检查端口是否被占用
    
-   Windows 下可运行 `端口修复.bat`（需要管理员权限）
    
-   或运行下面的命令
```bash
stop winnat

netsh int ipv4 add excludedportrange protocol=tcp startport=6119 numberofports=1

net start winnat
```
    

----------

## 贡献说明

-   保持数据与引擎分离
    
-   避免硬编码地图逻辑
    
-   保持模块化结构
    
-   大型修改请先提交 Issue
    

----------

## 开源协议

MIT License

详见 `LICENSE`

----------

## 致谢

基于 `sc2timer` （https://github.com/ylkangpeter/sc2-expo） 项目开发。

重构与维护：Archer
