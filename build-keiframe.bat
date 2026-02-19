@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ================= 配置区 =================
set PROJECT_NAME=Keiframe
set SPEC_FILE=Keiframe.spec
set RELEASE_DIR=Keiframe_Release_v1.0
:: =========================================

echo [1/4] 正在清理旧的打包文件...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist %RELEASE_DIR% rmdir /s /q %RELEASE_DIR%

echo [2/4] 正在使用 PyInstaller 进行打包...
.\python\python.exe -m PyInstaller --clean %SPEC_FILE%

if %ERRORLEVEL% NEQ 0 (
    echo [错误] 打包过程出错！
    pause
    exit /b %ERRORLEVEL%
)

echo [3/4] 正在组装发布文件夹...
mkdir %RELEASE_DIR%

:: 自动寻找 dist 下生成的第一个文件夹并复制其内容
for /f "delims=" %%i in ('dir /b /ad dist') do (
    set ACTUAL_DIST=dist\%%i
    echo 发现生成的程序目录: !ACTUAL_DIST!
    xcopy /e /i /y "!ACTUAL_DIST!" "%RELEASE_DIR%\"
)

:: 复制 resources 文件夹
if exist resources (
    echo 正在复制资源文件...
    xcopy /e /i /y "resources" "%RELEASE_DIR%\resources"
)

:: 复制其他说明文件
if exist 使用说明.pdf copy /y 使用说明.pdf "%RELEASE_DIR%\"
if exist 端口修复.bat copy /y 端口修复.bat "%RELEASE_DIR%\"

echo [4/4] 打包完成！
echo 最终软件位于: %RELEASE_DIR%
echo ----------------------------------------------------
pause