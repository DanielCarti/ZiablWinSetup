@echo off
chcp 65001 >nul
title ZiablWinSetup Launcher
cd /d "%~dp0"

echo ===================================================
echo           🚀 ZiablWinSetup Launcher
echo ===================================================
echo.

:: Проверка Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден в системе!
    echo Установите Python 3.10+ с сайта https://python.org
    echo и не забудьте отметить галочку "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

:: Проверка зависимостей
python -c "import customtkinter, PIL" >nul 2>&1
if errorlevel 1 (
    echo [ИНФО] Первичная установка библиотек...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось установить зависимости.
        pause
        exit /b 1
    )
)

:: Запуск приложения
if exist "dist\ZiablWinSetup.exe" (
    echo [ИНФО] Запуск скомпилированного ZiablWinSetup.exe...
    start "" "dist\ZiablWinSetup.exe"
    exit /b 0
)

echo [ИНФО] Запуск ZiablWinSetup (исходный код)...
start "" python main.py
exit /b 0
