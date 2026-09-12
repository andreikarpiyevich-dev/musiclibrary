[app]

# (str) Название вашего приложения
title = Music Library

# (str) Имя пакета (только английские буквы, без пробелов)
package.name = musiclib

# (str) Домен пакета (можно придумать любой)
package.domain = org.choir

# (str) Директория, где лежат исходники (точка означает текущую папку)
source.dir = .

# (str) Расширения файлов, которые нужно упаковать в APK. 
# ВАЖНО: добавлены png, jpg (для картинок) и json (для credentials_2.json)
source.include_exts = py,png,jpg,kv,atlas,json

# (list) Библиотеки, необходимые для работы программы на Android.
# ВНИМАНИЕ: Tkinter здесь нет, так как он не работает на Android. 
# Указан kivy в качестве графической библиотеки.
requirements = python3, kivy, gspread, google-auth, unidecode, rapidfuzz, deep-translator, requests

# (str) Версия вашего приложения
version = 1.0

# (str) Иконка приложения (используем ваш предоставленный файл)
icon.filename = logo.png

# (str) Ориентация экрана (portrait - вертикальная, landscape - горизонтальная, all - любая)
orientation = portrait

# (list) Разрешения для Android
# Обязательно нужен INTERNET для подключения к Google Таблицам
android.permissions = INTERNET

# (int) Целевая версия API Android (33 = Android 13)
android.api = 33

# (int) Минимальная версия API Android, на которой запустится приложение
android.minapi = 21

# (str) Архитектуры процессоров (современный стандарт для Google Play)
android.archs = arm64-v8a, armeabi-v7a

[buildozer]
# (int) Уровень логирования при сборке (2 - показывать всю информацию и ошибки)
log_level = 2

# (int) Предупреждать, если Buildozer запущен от имени суперпользователя (root)
warn_on_root = 1