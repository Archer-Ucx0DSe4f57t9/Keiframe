@echo off
setlocal EnableDelayedExpansion

:: ==========================================
:: 1. 自动获取管理员权限
:: ==========================================
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"

if '%errorlevel%' NEQ '0' (
    echo 正在请求管理员权限...
    goto UACPrompt
) else ( goto gotAdmin )

:UACPrompt
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    exit /B

:gotAdmin
    if exist "%temp%\getadmin.vbs" ( del "%temp%\getadmin.vbs" )
    pushd "%CD%"
    CD /D "%~dp0"

:: ==========================================
:: 2. 核心逻辑执行
:: ==========================================
cls
echo ==============================================
echo       端口 6119 排除范围配置脚本
echo ==============================================
echo.

echo [1/3] 正在停止 winnat 服务...
net stop winnat >nul 2>&1
if %errorlevel% EQU 0 (
    echo     - 服务已停止。
) else (
    echo     - 服务未运行或无需停止。
)

echo.
echo [2/3] 正在尝试锁定端口 6119...
:: 执行命令并隐藏标准输出，只在该步骤出错时处理
netsh int ipv4 add excludedportrange protocol=tcp startport=6119 numberofports=1 >nul 2>&1

:: 检查上一条命令是否出错 (%errorlevel% 不为 0 代表出错)
if %errorlevel% NEQ 0 (
    goto ErrorHandler
)

echo     - 成功！端口 6119 已添加到排除列表。

echo.
echo [3/3] 正在重启 winnat 服务...
net start winnat >nul 2>&1
echo     - 服务已恢复。

echo.
echo ==============================================
echo  恭喜！脚本执行成功，端口已保留。
echo ==============================================
echo.
pause
exit

:: ==========================================
:: 3. 错误处理与重启引导
:: ==========================================
:ErrorHandler
echo.
echo ==========================================================
echo  [ERROR] 设置失败！
echo ==========================================================
echo.
echo  系统提示端口已被占用 (The process cannot access the file...)
echo.
echo  原因：
echo  Windows 的某个服务（可能是 Hyper-V 或系统组件）已经占用了 6119 端口。
echo.
echo  解决方案：
echo  必须【重启电脑】以释放端口。
echo  请在重启后，尽量在打开其他软件前运行此脚本。
echo.
echo  (为了恢复网络，正在尝试重新启动 winnat 服务...)
net start winnat >nul 2>&1
echo.

set /p user_choice=">>> 是否现在立即重启电脑？(输入 Y 确认，输入 N 退出): "

if /i "%user_choice%"=="Y" (
    echo 正在准备重启...
    shutdown /r /t 0
) else (
    echo.
    echo 你选择了稍后重启。请记住重启后再次运行此脚本。
    pause
)