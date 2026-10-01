@echo off
chcp 65001 >nul
setlocal enableextensions enabledelayedexpansion

:: ================= 配置区 =================
set "SCRIPT_DIR=%~dp0"
set "PROJECT_NAME=Keiframe"
set "SPEC_FILE=Keiframe.spec"
set "RELEASE_DIR=%SCRIPT_DIR%dist\Keiframe_Release_v1.07"
set "ADDON_DIR=%SCRIPT_DIR%dist\KeiFrame_PP-OCRv5_Addon"
set "OCR_SOURCE_DIR=%SCRIPT_DIR%resources\ocr\ppocrv5"
:: =========================================

cd /d "%SCRIPT_DIR%"

echo [1/5] 正在清理旧的打包文件...
if exist "%SCRIPT_DIR%build" rmdir /s /q "%SCRIPT_DIR%build"
if exist "%SCRIPT_DIR%dist" rmdir /s /q "%SCRIPT_DIR%dist"
if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"

echo [2/5] 正在使用 PyInstaller 进行打包...
.\python\python.exe -m PyInstaller --clean %SPEC_FILE%

if errorlevel 1 (
    echo [错误] 打包过程出错！
    pause
    exit /b 1
)

echo [3/5] 正在组装主发布文件夹...
mkdir "%RELEASE_DIR%"

:: Keiframe.spec 的 onedir 输出固定为 dist\Keiframe。
echo 复制 PyInstaller 输出目录...
xcopy /e /i /y "%SCRIPT_DIR%dist\%PROJECT_NAME%" "%RELEASE_DIR%\"
if errorlevel 1 (
    echo [错误] PyInstaller 输出目录复制失败！
    pause
    exit /b 1
)

:: 主包复制所有运行时资源，但 PP-OCRv5 模型和字典属于独立 addon。
if exist "%SCRIPT_DIR%resources" (
    echo 正在复制主程序资源（排除 OCR addon）...
    robocopy "%SCRIPT_DIR%resources" "%RELEASE_DIR%\resources" /E /XD "%OCR_SOURCE_DIR%" /NFL /NDL /NJH /NJS /NP
    if errorlevel 8 (
        echo [错误] 主程序资源复制失败！
        pause
        exit /b 1
    )
)

echo [4/5] 正在生成 KeiFrame PP-OCRv5 Addon...
if not exist "%OCR_SOURCE_DIR%\ch_PP-OCRv5_rec_mobile.onnx" (
    echo [错误] 缺少 PP-OCRv5 模型文件：%OCR_SOURCE_DIR%\ch_PP-OCRv5_rec_mobile.onnx
    pause
    exit /b 1
)
if not exist "%OCR_SOURCE_DIR%\ppocrv5_dict.txt" (
    echo [错误] 缺少 PP-OCRv5 字典文件：%OCR_SOURCE_DIR%\ppocrv5_dict.txt
    pause
    exit /b 1
)
if not exist "%OCR_SOURCE_DIR%\SOURCE.txt" (
    echo [错误] 缺少 SOURCE.txt：%OCR_SOURCE_DIR%\SOURCE.txt
    pause
    exit /b 1
)

mkdir "%ADDON_DIR%\resources\ocr\ppocrv5"
copy /y "%OCR_SOURCE_DIR%\ch_PP-OCRv5_rec_mobile.onnx" "%ADDON_DIR%\resources\ocr\ppocrv5\"
copy /y "%OCR_SOURCE_DIR%\ppocrv5_dict.txt" "%ADDON_DIR%\resources\ocr\ppocrv5\"
copy /y "%OCR_SOURCE_DIR%\SOURCE.txt" "%ADDON_DIR%\resources\ocr\ppocrv5\"
if exist "%OCR_SOURCE_DIR%\README.txt" copy /y "%OCR_SOURCE_DIR%\README.txt" "%ADDON_DIR%\README.txt"
if errorlevel 1 (
    echo [错误] OCR addon 组装失败！
    pause
    exit /b 1
)

:: 复制其他说明文件
if exist "%SCRIPT_DIR%使用说明.pdf" copy /y "%SCRIPT_DIR%使用说明.pdf" "%RELEASE_DIR%\"
if exist "%SCRIPT_DIR%端口修复.bat" copy /y "%SCRIPT_DIR%端口修复.bat" "%RELEASE_DIR%\"

echo [5/5] 打包完成！
echo 最终软件位于: %RELEASE_DIR%
echo OCR addon 位于: %ADDON_DIR%
echo ----------------------------------------------------
pause
