@echo off
chcp 65001 >nul
echo ========================================
echo   🚀 ZiablWinSetup - Build to EXE
echo ========================================
echo.

:: Проверяем Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python не найден! Установите Python и добавьте в PATH.
    pause
    exit /b 1
)

:: Устанавливаем зависимости
echo [1/3] Проверка и установка зависимостей...
pip install -r requirements.txt
pip install pyinstaller

:: Собираем exe
echo.
echo [2/3] Сборка ZiablWinSetup.exe (это займёт 1-2 минуты)...
python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name ZiablWinSetup ^
    --icon assets\icon.ico ^
    --add-data "app;app" ^
    --add-data "assets;assets" ^
    --collect-all customtkinter ^
    main.py

if errorlevel 1 (
    echo.
    echo [ОШИБКА] Сборка завершилась с ошибкой!
    pause
    exit /b 1
)

:: Готово
echo.
echo [3/3] Сборка успешно завершена!
echo.
echo Готовый исполняемый файл: dist\ZiablWinSetup.exe
echo.
pause
