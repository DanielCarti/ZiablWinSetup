# 🚀 ZiablWinSetup

<div align="center">
  <img src="assets/icon.png" width="120" height="120" alt="ZiablWinSetup Logo" />
  <h3>Современная утилита для массовой установки софта, драйверов и тонкой настройки Windows 10/11</h3>

  <p>
    <a href="https://github.com/DanielCarti/ZiablWinSetup/releases/latest"><img src="https://img.shields.io/github/v/release/DanielCarti/ZiablWinSetup?style=for-the-badge&color=2563eb&label=Release" alt="Latest Release" /></a>
    <a href="https://github.com/DanielCarti/ZiablWinSetup/releases/latest"><img src="https://img.shields.io/github/downloads/DanielCarti/ZiablWinSetup/total?style=for-the-badge&color=10b981&label=Downloads" alt="Downloads" /></a>
    <img src="https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011%20(x64)-0078d4?style=for-the-badge&logo=windows" alt="Platform" />
    <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License" />
  </p>

  <p align="center">
    <img src="assets/screenshots/main_catalog.png" alt="Главный экран ZiablWinSetup" width="920" />
  </p>
</div>

---

## 🌟 О проекте

**ZiablWinSetup** — это легковесный, автономный и быстрый инструмент для автоматической подготовки, установки софта и оптимизации системы после чистой установки Windows или покупки нового ПК.

Больше не нужно вручную открывать десятки сайтов, закрывать баннеры и кликать «Далее-Далее-Готово»: выберите нужные программы галочками, примените рекомендуемые твики системы и нажмите **«Скачать выбранное»**!

<p align="center">
  <img src="assets/screenshots/header_tabs.png" alt="Навигация по разделам" width="500" />
</p>

Интерфейс разделен на четыре ключевые рабочие зоны:
1. **[Приложения]** — обширный каталог из 71 актуальной программы, утилиты и библиотеки runtimes с пакетной загрузкой и тихой установкой.
2. **[Твики и фичи]** — моментальная оптимизация Windows, ускорение SSD, удаление встроенной рекламы и возврат классического меню.
3. **[Metro приложения]** — встроенный деблоатер предустановленных UWP-приложений Windows с возможностью удаления и восстановления в один клик.
4. **[Автозагрузка]** — продвинутый менеджер автозапуска приложений уровня CCleaner и Autoruns (реестр, папки автозапуска, планировщик задач).

---

## ✨ Ключевые возможности

### 📦 1. Богатый каталог софта (71 приложение)
Все программы распределены по 10 удобным категориям с мгновенным поиском и фильтрацией:

* 🌐 **Браузеры**: Google Chrome, Opera GX, Mozilla Firefox, Brave, Dolphin{anty}
* 🎬 **Медиа**: VLC Media Player, K-Lite Codec Pack Full, Picasa 3, OBS Studio, Adobe Photoshop, Adobe Premiere Pro, NVIDIA Broadcast
* 🔧 **Системные утилиты**: 7-Zip, WinRAR, Everything, Total Commander, EarTrumpet, CPU-Z, HWiNFO, ShareX, PowerToys, CrystalDiskInfo, CrystalDiskMark, OCCT, Uninstall Tool, Unlocker, Unchecky, HitmanPro
* 📚 **Библиотеки и Runtimes**: DirectX End-User Runtimes (June 2010), Visual C++ Runtimes All-in-One, Visual C++ 2015-2022 (x64/x86), .NET Desktop Runtime 8.0/9.0/6.0, .NET Framework 4.8.1, .NET Framework 3.5
* 💬 **Связь и мессенджеры**: Telegram Desktop, Discord, Claude Desktop, ChatGPT, Todoist
* 💻 **Разработка**: Visual Studio Code, PyCharm Community, Sublime Text, Notepad++, Git, Python 3, Eclipse Temurin JDK 21, Open Code Interpreter, Claude Code
* 🖥️ **GPU и драйверы**: NVIDIA App, AMD Software: Adrenalin, GPU-Z, FurMark, Driver Booster
* 🔒 **VPN и сеть**: AmneziaVPN, Zapret (обход блокировок Discord & YouTube), YogaDNS, TeleProxy, Opera Proxy, AnyDesk
* 🎮 **Игры и загрузки**: Steam, Roblox, TLauncher (Minecraft), qBittorrent, BitTorrent, Dropbox
* 📑 **Офис и документы**: Obsidian, LibreOffice, OpenOffice

**Особенности менеджера загрузок:**
- Пакетное скачивание в несколько параллельных потоков с отображением прогресс-бара и скорости.
- Поддержка тихой (фоновой) установки без участия пользователя.
- Автоматическая распаковка ZIP-архивов и создание готовых ярлыков на Рабочем столе (Zapret и др.).

---

### 🔄 2. Интеллектуальный центр обновлений

<p align="center">
  <img src="assets/screenshots/updates_banner.png" alt="Центр обновлений" width="860" />
</p>

- **Автоматический мониторинг версий**: сканирование установленного софта через Winget и GitHub Releases API.
- **Информативная панель**: мгновенное уведомление о количестве доступных обновлений.
- **Редизайн кнопки «Обновить»**: выразительная Windows 11 кнопка с подсветкой и акцентным градиентом прямо на карточке программы.
- **Гибкие исключения**: удобное модальное окно для исключения программ из массового обновления (например, для специфических или портативных версий ПО).
- **Синхронизация на лету**: повторное сканирование системы без перезапуска приложения.

<p align="center">
  <img src="assets/screenshots/update_exclusions.png" alt="Окно исключений из автообновления" width="520" />
</p>

---

### ⚡ 3. Системные твики и оптимизация («Твики и фичи»)

<p align="center">
  <img src="assets/screenshots/tweaks_view.png" alt="Твики и оптимизация" width="920" />
</p>

Каждый твик сопровождается подробным описанием и безопасным переключателем:

| Твик | Описание и эффект |
| :--- | :--- |
| 🚀 **Максимальная производительность** | Разблокировка и активация скрытой схемы электропитания Windows *Ultimate Performance* для максимального отклика CPU. |
| 📁 **Показ расширений файлов** | Автоматическое включение отображения расширений всех типов файлов в Проводнике. |
| 📋 **Классическое контекстное меню** | Возврат полного контекстного меню в стиле Windows 10 в проводнике Windows 11 (без пункта «Показать дополнительные параметры»). |
| 🚫 **Блокировка рекламы в торрентах** | Полное отключение встроенных рекламных баннеров и всплывающих промо в клиентах BitTorrent и uTorrent (с возможностью обратного включения). |
| 💾 **Отключение индексации SSD** | Остановка и отключение службы `WSearch` (Windows Search) для снижения фонового износа ячеек памяти SSD (TBW) и разгрузки диска. |
| 🔍 **Скрытие поиска на Панели задач** | Отключение громоздкой поисковой строки на панели задач для освобождения свободного места. |
| 📌 **Выравнивание Панели задач влево** | Перенос меню «Пуск» и закреплённых иконок к левому краю экрана в стиле Windows 10. |
| 🧹 **Очистка кэша Steam** | Удаление накопившегося кэша HTML-браузера, шейдеров и временных файлов загрузок Steam без затрагивания игр. |
| 💬 **Очистка медиа-кэша Telegram** | Безопасное освобождение гигабайтов кэша видео, аудио и изображений Telegram Desktop. |
| 🔇 **Отключение рекламы в меню Пуск** | Блокировка рекомендаций, подсказок и рекламных плиток в меню «Пуск» Windows 10/11. |

---

### 🪟 4. Встроенные Metro / UWP приложения («Metro приложения»)

<p align="center">
  <img src="assets/screenshots/metro_apps.png" alt="Metro приложения" width="920" />
</p>

Удобный графический деблоатер стандартных Windows AppX-пакетов:
- **Контроль над 21 встроенным приложением**: Погода MSN, Новости, Кортана, Связь с телефоном, Камера, Карты, Xbox Game Bar, Запись голоса, Советы, Microsoft Solitaire, Paint 3D, Clipchamp и др.
- **Удаление в один клик**: быстрое удаление предустановленного «мусора» через официальный PowerShell AppX API.
- **Восстановление в один клик**: повторная регистрация из системного хранилища Windows или переход на страницу в Microsoft Store.
- **Пакетные операции**: выделение нужных приложений чекбоксами и одновременное удаление или восстановление.

---

### 🚀 5. Менеджер автозагрузки Windows («Автозагрузка»)
Продвинутый инструмент управления автозапуском, находящий скрытые элементы, которые часто не видит стандартный Диспетчер задач:
- **Глубокое сканирование всех источников**:
  - Системный и пользовательский реестр: `HKCU\Run`, `HKCU\RunOnce`, `HKLM\Run`, `HKLM\RunOnce`, `WOW6432Node` (32-битные приложения).
  - Папки «Автозагрузка»: `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup` и `%PROGRAMDATA%\...`.
  - Запланированные задачи Windows: авторизационные триггеры в Планировщике задач (`Task Scheduler`).
- **Безопасное включение и отключение**: интеграция с системным механизмом Windows `StartupApproved` (сохраняет пути и команды без риска их потери).
- **Определение издателя**: автоматическое чтение метаданных Win32 VersionInfo и определение официального разработчика.
- **Действия в один клик**: моментальный переход к файлу в Проводнике Windows (`explorer.exe /select`) и полное удаление лишних записей.

---

### 🪟 6. Системный трей и автозапуск приложения
- **Миниатюрная иконка в трее**: аккуратная иконка с возможностью быстро свернуть/развернуть окно кликом.
- **Контекстное меню трея**: открытие окна, запуск проверки обновлений софта, переключение автозапуска и чистый выход.
- **Сворачивание при закрытии**: фоновая работа без загромождения Панели задач.
- **Автозапуск с Windows**: удобный переключатель в настройках для тихого старта в трее при загрузке системы (`--tray`).

---

### 🎨 7. Дизайн и эргономика
- **Windows 11 Fluent Design**: полупрозрачность Mica, гарнитура Segoe UI Variable, стилизованные чекбоксы и кнопки.
- **Поддержка тем**: переключение между тёмной и светлой темами оформления.
- **Мгновенный перевод интерфейса (RU / EN)**: бесшовное переключение языка на лету без перезапуска.
- **Защита от случайного прерывания**: диалоговое предупреждение при попытке закрыть окно во время активного скачивания или установки.

---

## 🚀 Как запустить

### Вариант 1. Готовый EXE-файл (Рекомендуется)
Скачайте актуальный релиз без необходимости устанавливать Python и зависимости:

👉 **[Скачать последнюю версию ZiablWinSetup.exe](https://github.com/DanielCarti/ZiablWinSetup/releases/latest)**

Просто сохраните файл и запустите его от имени администратора.

### Вариант 2. Запуск из исходного кода
```bash
# Клонируйте репозиторий
git clone https://github.com/DanielCarti/ZiablWinSetup.git
cd ZiablWinSetup

# Установите зависимости
pip install -r requirements.txt

# Запустите проект
python main.py
```
Либо дважды кликните по файлу `run.bat`.

---

## 🛠️ Сборка собственного EXE

Для компиляции автономного исполняемого файла используется **PyInstaller**:
```bash
pyinstaller --clean ZiablWinSetup.spec
```
Или выполните скрипт сборщика:
```cmd
build.bat
```
Собранный исполняемый файл будет помещён в директорию `dist/ZiablWinSetup.exe`.

---

## 💻 Стек технологий

- **Ядро**: Python 3.10+ (ctypes, subprocess, winreg, urllib, Win32 API)
- **GUI-движок**: [pywebview](https://pywebview.flowrl.com/) (Microsoft Edge WebView2 Chromium)
- **UI/UX**: HTML5, Vanilla CSS3 (Fluent Design System, CSS Variables, Flexbox/Grid), SVG-иконки
- **Менеджеры пакетов**: Winget CLI, GitHub REST API, прямые CDN-зеркала
- **Сборка и CI/CD**: PyInstaller, GitHub Actions (.github/workflows/release.yml)

---

## 📄 Лицензия

Проект распространяется под лицензией **MIT**. Подробности в файле [LICENSE](LICENSE).
