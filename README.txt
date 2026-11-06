TELEGRAM ACTIVITY TRACKER 2.0 — WINDOWS EXE

В этом архиве теперь есть tracker.py (исходный файл, которого не хватало в предыдущей сборке).

ЗАГРУЗКА В GITHUB:
1. Откройте репозиторий https://github.com/sqwuio/telegram-activity-tracker
2. Загрузите tracker.py в корень репозитория (рядом с папкой .github).
3. Замените .github/workflows/build-windows.yml файлом из этого архива.
4. Commit changes. Откройте Actions и дождитесь успешной сборки.
5. В успешном запуске скачайте Artifact TelegramTracker-Windows.
6. Распакуйте ZIP и запустите TelegramTracker.exe.

На вашем Windows-компьютере Python устанавливать не нужно. Сборка происходит на GitHub.

ПРИ ПЕРВОМ ЗАПУСКЕ:
- API ID и API HASH: https://my.telegram.org
- Номер телефона вашего Telegram-аккаунта
- Username целевого аккаунта
- Код Telegram и, если включена, пароль двухэтапной проверки.

ВАЖНО:
- Используйте только аккаунт, которым вы вправе пользоваться, и учитывайте настройки приватности собеседника.
- Программа не обходит скрытие времени последнего посещения.
- Опрос раз в 20 секунд; время начала/окончания определяется с погрешностью до интервала.
- Не публикуйте telegram_tracker_session.session и config.json: они дают доступ к вашей авторизованной сессии.
- База telegram_activity.db создаётся рядом с EXE.
