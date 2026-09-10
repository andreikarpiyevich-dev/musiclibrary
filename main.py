import os
import re
import sys
import threading
import flet as ft
from functools import lru_cache
import gspread
from google.oauth2.service_account import Credentials
from unidecode import unidecode
from rapidfuzz import fuzz
from deep_translator import GoogleTranslator


def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1ipHOZB4Xjs0XLWbUDRAykXvCox4KW17l57Lmjky1hHU/edit?gid=2128320143#gid=2128320143"
CREDENTIALS_FILE = resource_path("credentials.json")

# --- ЛОГИКА ПОИСКА И ТРАНСЛИТЕРАЦИИ ---
RU_KEYS = "йцукенгшщзхъфывапролджэячсмитьбю.ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,"
EN_KEYS = "qwertyuiop[]asdfghjkl;'zxcvbnm,./QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>?"
TRANS_RU_TO_EN = str.maketrans(RU_KEYS, EN_KEYS)
TRANS_EN_TO_RU = str.maketrans(EN_KEYS, RU_KEYS)

KNOWN_COMPOSERS = {
    "чайковский": ["tchaikovsky", "tschaikowsky", "chaikovsky"],
    "рахманинов": ["rachmaninoff", "rachmaninov", "rahmaninov"],
    "шостакович": ["shostakovich", "schostakowitsch"],
    "прокофьев": ["prokofiev", "prokofjew"],
    "скрябин": ["scriabin", "skryabin"],
    "стравинский": ["stravinsky"],
    "мусоргский": ["mussorgsky"],
    "моцарт": ["mozart"],
    "бетховен": ["beethoven"],
    "бах": ["bach", "bakh"],
    "вагнер": ["wagner"],
    "шопен": ["chopin"],
    "лист": ["liszt"],
    "брамс": ["brahms"],
}
COMPOSER_ALIASES = {}
for cyr, lat_list in KNOWN_COMPOSERS.items():
    all_forms = {cyr} | set(lat_list)
    for form in all_forms:
        COMPOSER_ALIASES[form] = all_forms


def switch_keyboard_layout(text: str) -> list:
    return [text.translate(TRANS_RU_TO_EN), text.translate(TRANS_EN_TO_RU)]


def phonetic_normalize(text: str) -> str:
    t = unidecode(text.lower())
    replacements = [
        ("shtch", "sh"), ("shch", "sh"), ("tsch", "ch"), ("tch", "ch"),
        ("sch", "sh"), ("w", "v"), ("ch", "h"), ("kh", "h"), ("ph", "f")
    ]
    for old, new in replacements:
        t = t.replace(old, new)
    return re.sub(r'([a-z])\1+', r'\1', t)


@lru_cache(maxsize=512)
def translate_cached(text: str, target_lang: str) -> str:
    try:
        return GoogleTranslator(source='auto', target=target_lang).translate(text)
    except Exception:
        return ""


def get_multilingual_variants(text: str) -> list:
    text_clean = text.strip().lower()
    if not text_clean:
        return [""]
    variants = {text_clean}
    if text_clean in COMPOSER_ALIASES:
        variants.update(COMPOSER_ALIASES[text_clean])
    for layout_variant in switch_keyboard_layout(text_clean):
        layout_clean = layout_variant.strip().lower()
        variants.add(layout_clean)
        if layout_clean in COMPOSER_ALIASES:
            variants.update(COMPOSER_ALIASES[layout_clean])
    for source in list(variants):
        variants.add(unidecode(source))
        variants.add(phonetic_normalize(source))
    return list(variants)


def matches_search(query_text: str, target_row_str: str) -> bool:
    if not query_text.strip():
        return True
    target_norm = unidecode(target_row_str.lower())
    target_tokens = re.sub(r'[^a-z0-9\s]', '', target_norm).split()
    target_phonetics = [phonetic_normalize(t) for t in target_tokens]

    for variant in get_multilingual_variants(query_text):
        norm_query = re.sub(r'[^a-z0-9\s]', '', unidecode(variant.lower()))
        query_tokens = norm_query.split()
        if not query_tokens:
            continue
        matched_all = True
        for q_tok in query_tokens:
            q_phon = phonetic_normalize(q_tok)
            found = False
            for t_tok, t_phon in zip(target_tokens, target_phonetics):
                if q_tok == t_tok or q_phon == t_phon or (len(q_tok) > 3 and fuzz.ratio(q_tok, t_tok) >= 82):
                    found = True
                    break
            if not found:
                matched_all = False
                break
        if matched_all:
            return True
    return False


# --- ИНТЕРФЕЙС FLET ---
def main(page: ft.Page):
    page.title = "Music Library"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 10

    raw_data = []
    worksheet = None

    status_text = ft.Text("⏳ Подключение к базе данных...", size=12, color=ft.Colors.GREY_700)
    
    # Поля поиска
    search_title = ft.TextField(label="Название произведения", expand=True)
    search_author = ft.TextField(label="Автор", expand=True)
    results_list = ft.ListView(expand=True, spacing=5, divider_thickness=1)

    # Поля добавления
    add_folder = ft.TextField(label="Номер папки")
    add_author = ft.TextField(label="Автор произведения")
    add_title = ft.TextField(label="Название произведения")

    def load_sheets():
        nonlocal worksheet, raw_data
        try:
            scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
            gc = gspread.authorize(creds)
            sh = gc.open_by_url(GOOGLE_SHEET_URL)
            worksheet = sh.sheet1
            raw_data = worksheet.get_all_values()
            status_text.value = f"✅ Готово! Загружено строк: {len(raw_data)}"
            run_search(None)
        except Exception as e:
            status_text.value = f"❌ Ошибка подключения: {e}"
        page.update()

    def run_search(e):
        results_list.controls.clear()
        title_q = search_title.value or ""
        author_q = search_author.value or ""
        count = 0

        for row in raw_data:
            if not any(row):
                continue
            row_str = " ".join(row)
            if matches_search(title_q, row_str) and matches_search(author_q, row_str):
                folder = row[0] if len(row) > 0 else ""
                author = row[1] if len(row) > 1 else ""
                title = row[2] if len(row) > 2 else ""

                results_list.controls.append(
                    ft.Card(
                        content=ft.ListTile(
                            leading=ft.Chip(label=ft.Text(folder)),
                            title=ft.Text(title, weight=ft.FontWeight.BOLD),
                            subtitle=ft.Text(author),
                        )
                    )
                )
                count += 1
        status_text.value = f"Найдено совпадений: {count}"
        page.update()

    def add_entry(e):
        if not add_title.value and not add_folder.value:
            return
        status_text.value = "⏳ Добавление записи..."
        page.update()

        def worker():
            nonlocal raw_data
            new_row = [add_folder.value, add_author.value, add_title.value]
            worksheet.append_row(new_row)
            raw_data.append(new_row)
            add_folder.value = ""
            add_author.value = ""
            add_title.value = ""
            status_text.value = "✅ Успешно добавлено!"
            run_search(None)

        threading.Thread(target=worker, daemon=True).start()

    # Сборка UI
    search_tab = ft.Column([
        ft.Row([search_title, search_author]),
        ft.ElevatedButton("🔍 Искать", on_click=run_search),
        ft.Divider(),
        results_list
    ], expand=True)

    add_tab = ft.Column([
        add_folder,
        add_author,
        add_title,
        ft.ElevatedButton("➕ Добавить в Google Таблицу", on_click=add_entry)
    ])

    tabs = ft.Tabs(
        selected_index=0,
        tabs=[
            ft.Tab(text="🔍 Поиск", content=search_tab),
            ft.Tab(text="➕ Добавить", content=add_tab),
        ],
        expand=True
    )

    page.add(tabs, status_text)
    threading.Thread(target=load_sheets, daemon=True).start()


ft.app(target=main)