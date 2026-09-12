[app]
title = Music Library
package.name = musiclib
package.domain = org.choir
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json

# Библиотеки, необходимые для gspread и безопасного SSL-подключения
requirements = python3, kivy, gspread, google-auth, requests, urllib3, certifi, chardet, idna

version = 1.0
icon.filename = logo.png
orientation = portrait
android.permissions = INTERNET

# Фиксация стабильных версий SDK и автоматическое согласие с лицензией
android.api = 33
android.minapi = 21
android.build_tools_version = 33.0.2
android.accept_sdk_license = True
android.archs = arm64-v8a, armeabi-v7a

[buildozer]
log_level = 2
warn_on_root = 1
