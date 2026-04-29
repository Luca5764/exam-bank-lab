@echo off
chcp 65001 >nul
echo ========================================
echo  Custom_Quiz 打包工具
echo ========================================
echo.

:: 確認 pyinstaller 存在
where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [錯誤] 找不到 pyinstaller，請先安裝：
    echo   pip install pyinstaller
    pause
    exit /b 1
)

:: 清理舊的建置
if exist dist\Custom_Quiz rmdir /s /q dist\Custom_Quiz
if exist build rmdir /s /q build

echo 開始打包...
pyinstaller Custom_Quiz.spec

if errorlevel 1 (
    echo.
    echo [失敗] 打包過程發生錯誤，請查看上方訊息。
    pause
    exit /b 1
)

echo.
echo ========================================
echo  打包完成！
echo  輸出位置：dist\Custom_Quiz\
echo  執行檔：  dist\Custom_Quiz\Custom_Quiz.exe
echo ========================================
echo.
echo 可以將整個 dist\Custom_Quiz\ 資料夾壓縮後分享給別人。
pause
