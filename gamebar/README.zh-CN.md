# Keiframe Xbox Game Bar 全屏覆盖层

这个 UWP 小组件只负责把 Keiframe 已有的 Qt 界面显示到 Xbox Game Bar。
地图、计时、识别、提醒和快捷键逻辑仍全部运行在 Python 主程序中。

它用于绕过普通 Qt 置顶窗口无法稳定覆盖 Direct3D 真全屏的问题，不注入游戏
进程，也不修改游戏文件。Python 主程序通过 UWP 的本地状态目录向小组件发送
裁剪后的透明 PNG 帧。

## 支持的显示方式

- 16:9：窗口最大化、无边框全屏、真全屏。
- 21:9：2560×1080、3440×1440、3840×1600。
- 游戏为 16:9、显示器为 21:9 时，覆盖层以游戏实际画面为坐标基准，保持居中，
  不会把内容定位到左右黑边。
- 截图识别始终归一化为 1920×1080，现有识别区域和提醒位置无需改写。
- 窗口模式和窗口最大化继续使用原来的 Qt 覆盖层；真全屏才使用 Game Bar 小组件。

## 正确启动和使用

按以下顺序启动：

1. 完全退出旧的 Keiframe，避免后台存在两个主程序。
2. 启动《星际争霸 II》并进入真全屏。
3. 运行打包版 `dist/Keiframe/Keiframe.exe`，或者运行源码版
   `.venv/Scripts/pythonw.exe -m src.main`。
4. 按 `Win+G`，在小组件菜单中打开“Keiframe 全屏覆盖层”。

首次使用还要做一次 Game Bar 自身的设置：

1. 固定 Keiframe 小组件。
2. 点击屏幕顶部 Game Bar 工具栏里的鼠标图标，开启“点透/单击浏览”。
3. 按 `Esc` 关闭 Game Bar 编辑界面并返回游戏。

点透是 Game Bar 的系统级开关，不是 Keiframe 的“锁定”功能。开启点透后，
小组件仍然显示，但它后面的《星际争霸 II》可以正常接收鼠标。微软的公开接口
只允许小组件读取开关状态，不允许小组件替用户强制开启；Game Bar 会记住用户
的选择。

需要调整小组件时按 `Win+G`：

- 拖动 Game Bar 标题栏可移动小组件。
- 点击小组件内的“切换锁定”可切换 Keiframe 本体的锁定状态。
- 点击小组件内的“关闭”或标题栏的 `X` 可隐藏小组件。
- 调整完成后重新确认顶部鼠标图标处于点透状态，再按 `Esc` 回到游戏。

## 开发环境

- Visual Studio 2022
- “通用 Windows 平台开发”工作负载
- Windows 10 SDK 10.0.19041
- x64 构建目标

打开 `Keiframe.GameBar/Keiframe.GameBar.csproj`，还原 NuGet 包后生成并部署。
也可以从仓库根目录直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\gamebar\build-gamebar.ps1
```

脚本会自动查找 Visual Studio 2022 的 MSBuild，还原 NuGet 包，并把 x64 Debug
测试包输出到 `gamebar/artifacts/GameBar`。可用参数包括
`-Configuration Release`、`-OutputDirectory <路径>` 和 `-NoRestore`。

Debug 包使用 Windows 11 的无签名测试包机制，首次安装需要管理员 PowerShell：

```powershell
$packageDir = ".\gamebar\artifacts\GameBar\Keiframe.GameBar_1.0.0.6_x64_Debug_Test"
$dependencies = Get-ChildItem "$packageDir\Dependencies\x64\*.appx"
Add-AppxPackage `
  -Path "$packageDir\Keiframe.GameBar_1.0.0.6_x64_Debug.msix" `
  -DependencyPath $dependencies.FullName `
  -AllowUnsigned
```

需要把包交给其他测试用户时，应提供完整的
`Keiframe.GameBar_1.0.0.6_x64_Debug_Test` 目录，不能只发送其中的 MSIX，
否则目标电脑可能缺少 `Dependencies\x64` 内的运行库。Windows 10 应使用可信
证书签名的包，不能使用上述 Windows 11 无签名测试安装方式。

部署成功后：

1. 先启动 Keiframe 和《星际争霸 II》。
2. 打开 Xbox Game Bar，在小组件菜单中选择“Keiframe 全屏覆盖层”。
3. 首次使用时将小组件固定，并打开 Game Bar 的点击穿透。这两个开关由 Game Bar
   保存，微软的接口不允许小组件替用户强制开启。
4. 小组件从自身的 `LocalState\overlay.frame` 邮箱读取裁剪后的透明 PNG，
   并随小组件尺寸自动缩放。

也可以用官方 Game Bar 控制协议直接打开小组件：

```text
ms-gamebar:/activate/Keiframe.GameBar_83kdtmzvrsrdt_App_KeiframeOverlay
```

小组件首次启动使用紧凑尺寸并居中，然后根据第一帧内容调整大小。它不再创建覆盖
整个屏幕的透明窗口，因此即使尚未开启点透，也只会阻挡小组件自身的小块区域。
内部图像使用等比缩放，不会拉伸 16:9 内容。
