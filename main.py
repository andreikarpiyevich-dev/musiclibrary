import sys
from types import ModuleType

# Заглушка для отсутствующего в Android стандартного модуля wsgiref (нужно для gspread/google-auth)
if "wsgiref" not in sys.modules:
    wsgiref_mock = ModuleType("wsgiref")
    sys.modules["wsgiref"] = wsgiref_mock
    simple_server_mock = ModuleType("wsgiref.simple_server")
    sys.modules["wsgiref.simple_server"] = simple_server_mock
    wsgiref_mock.simple_server = simple_server_mock

import os
import re
import threading
import unicodedata
from functools import lru_cache
from pathlib import Path

import flet as ft
import gspread
from google.oauth2.service_account import Credentials
from unidecode import unidecode
from rapidfuzz import fuzz
from deep_translator import GoogleTranslator


def resource_path(relative_path: str) -> str:
    """
    Получает абсолютный путь к ресурсам (на компьютере и в памяти Android).
    """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    assets_dir = Path(os.environ.get("FLET_ASSETS_DIR", str(Path(base_path) / "assets")))
    path_in_assets = assets_dir / relative_path
    if path_in_assets.exists():
        return str(path_in_assets)
    return os.path.join(base_path, relative_path)


# --- НАСТРОЙКИ И ПУТИ ---
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1ipHOZB4Xjs0XLWbUDRAykXvCox4KW17l57Lmjky1hHU/edit?gid=2128320143#gid=2128320143"
CREDENTIALS_FILE = resource_path("credentials.json")

# --- СЛОВАРЬ РАСКЛАДКИ КЛАВИАТУРЫ ---
RU_KEYS = "йцукенгшщзхъфывапролджэячсмитьбю.ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,"
EN_KEYS = "qwertyuiop[]asdfghjkl;'zxcvbnm,./QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>?"

TRANS_RU_TO_EN = str.maketrans(RU_KEYS, EN_KEYS)
TRANS_EN_TO_RU = str.maketrans(EN_KEYS, RU_KEYS)

# --- БАЗА ИЗВЕСТНЫХ АВТОРОВ (ДВУСТОРОННЯЯ) ---
KNOWN_COMPOSERS = {
    "чайковский": ["tchaikovsky", "tschaikowsky", "chaikovsky", "cajkovskij"],
    "рахманинов": ["rachmaninoff", "rachmaninov", "rahmaninov"],
    "шостакович": ["shostakovich", "schostakowitsch", "sostakovic"],
    "прокофьев": ["prokofiev", "prokofjew", "prokofeff"],
    "скрябин": ["scriabin", "skryabin", "skriabin"],
    "стравинский": ["stravinsky", "stravinski"],
    "мусоргский": ["mussorgsky", "moussorgsky", "musorgsky"],
    "бородин": ["borodin"],
    "римский-корсаков": ["rimsky-korsakov", "rimskikorsakov"],
    "глинка": ["glinka"],
    "шнитке": ["schnittke"],
    "моцарт": ["mozart"],
    "бетховен": ["beethoven"],
    "бах": ["bach", "bakh"],
    "вагнер": ["wagner"],
    "григ": ["grieg"],
    "дворжак": ["dvorak", "dvorzak"],
    "дебюсси": ["debussy"],
    "шопен": ["chopin"],
    "лист": ["liszt"],
    "брамс": ["brahms"],
    "гендель": ["haendel", "handel"],
    "гайдн": ["haydn"],
    "шуберт": ["schubert"],
    "шуман": ["schumann"],
    "мендельсон": ["mendelssohn"],
    "верди": ["verdi"],
    "пуччини": ["puccini"],
    "вивальди": ["vivaldi"],
    "шёнберг": ["schoenberg", "schonberg"],
    "шенберг": ["schoenberg", "schonberg"],
}

COMPOSER_ALIASES = {}
for cyr, lat_list in KNOWN_COMPOSERS.items():
    all_forms = {cyr} | set(lat_list)
    for form in all_forms:
        COMPOSER_ALIASES[form] = all_forms


def switch_keyboard_layout(text: str) -> list:
    return [text.translate(TRANS_RU_TO_EN), text.translate(TRANS_EN_TO_RU)]


def phonetic_normalize(text: str) -> str:
    t = text.lower()
    t = unidecode(t)
    replacements = [
        ("shtch", "sh"), ("shch", "sh"), ("tsch", "ch"), ("tch", "ch"),
        ("sch", "sh"), ("cz", "ch"), ("sz", "sh"), ("w", "v"), ("eu", "oy"),
        ("ch", "h"), ("kh", "h"), ("ck", "k"), ("tz", "s"), ("ts", "s"),
        ("ph", "f"), ("off", "ov"), ("ff", "v"), ("ij", "y"), ("iy", "y"),
        ("ii", "i"), ("aa", "a"), ("ee", "e"), ("oo", "o"), ("uu", "u"),
    ]
    for old, new in replacements:
        t = t.replace(old, new)
    return re.sub(r'([a-z])\1+', r'\1', t)


@lru_cache(maxsize=512)
def translate_cached(text: str, target_lang: str) -> str:
    try:
        return GoogleTranslator(source='auto', target=target_lang).translate(text)
    except Exception as e:
        print(f"[translate_cached] Ошибка перевода '{text}' -> {target_lang}: {e}")
        return ""


def get_multilingual_variants(text: str) -> list:
    text_clean = text.strip().lower()
    if not text_clean:
        return [""]

    variants = {text_clean}

    if text_clean in COMPOSER_ALIASES:
        variants.update(COMPOSER_ALIASES[text_clean])

    all_sources = [text_clean]
    for layout_variant in switch_keyboard_layout(text_clean):
        layout_clean = layout_variant.strip().lower()
        variants.add(layout_clean)
        all_sources.append(layout_clean)
        if layout_clean in COMPOSER_ALIASES:
            variants.update(COMPOSER_ALIASES[layout_clean])

    for source in list(variants):
        variants.add(unidecode(source))

    current_variants = list(variants)
    for v in current_variants:
        variants.add(phonetic_normalize(v))

    for source in all_sources:
        for target_lang in ['en', 'ru']:
            translated = translate_cached(source, target_lang)
            if translated:
                t_low = translated.lower()
                variants.add(t_low)
                variants.add(unidecode(t_low))
                variants.add(phonetic_normalize(t_low))

    return list(variants)


def normalize_text_universal(text: str) -> str:
    if not text:
        return ""
    text = str(text).lower()
    text = unidecode(text)
    text = re.sub(r'[^a-z0-9\s]', '', text)
    return text.strip()


def matches_search(query_text: str, target_row_str: str) -> bool:
    if not query_text.strip():
        return True

    target_norm = normalize_text_universal(target_row_str)
    target_tokens = target_norm.split()
    target_phonetic_tokens = [phonetic_normalize(t) for t in target_tokens]

    query_variants = get_multilingual_variants(query_text)

    for variant in query_variants:
        norm_query = normalize_text_universal(variant)
        if not norm_query:
            continue

        query_tokens = norm_query.split()
        query_phonetic_tokens = [phonetic_normalize(q) for q in query_tokens]

        matched_all = True
        for q_tok, q_phon in zip(query_tokens, query_phonetic_tokens):
            found = False
            is_short = len(q_tok) <= 3

            for t_tok, t_phon in zip(target_tokens, target_phonetic_tokens):
                if q_tok == t_tok or q_phon == t_phon:
                    found = True
                    break
                if not is_short:
                    if fuzz.ratio(q_tok, t_tok) >= 82 or fuzz.ratio(q_phon, t_phon) >= 82:
                        found = True
                        break
            if not found:
                matched_all = False
                break

        if matched_all and query_tokens:
            return True

    return False


# --- FLET GUI ПРИЛОЖЕНИЕ ---
def main(page: ft.Page):
    page.title = "Music Library — Поиск нот"
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.VERTICAL

    worksheet = [None]
    raw_data = []
    selected_row_idx = [None]

    # Статус бар
    status_text = ft.Text("Инициализация подключения...", color=ft.colors.BLUE, weight=ft.FontWeight.BOLD)

    # Элементы вкладки "Поиск"
    entry_title = ft.TextField(label="Слово/слова из названия", width=280)
    entry_author = ft.TextField(label="Фамилия / Имя автора", width=280)

    results_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Папка")),
            ft.DataColumn(ft.Text("Автор")),
            ft.DataColumn(ft.Text("Название произведения")),
        ],
        rows=[],
        border=ft.border.all(1, ft.colors.OUTLINE),
        vertical_lines=ft.border.BorderSide(1, ft.colors.OUTLINE),
        horizontal_lines=ft.border.BorderSide(1, ft.colors.OUTLINE),
    )

    results_container = ft.Container(
        content=ft.Column([results_table], scroll=ft.ScrollMode.AUTO),
        border=ft.border.all(1, ft.colors.OUTLINE_VARIANT),
        border_radius=8,
        padding=5,
        height=320,
    )

    # Поля редактирования выбранной строки
    edit_folder = ft.TextField(label="Папка", width=100)
    edit_author = ft.TextField(label="Автор", width=220)
    edit_title = ft.TextField(label="Название", width=320)

    # Элементы вкладки "Добавить"
    add_folder = ft.TextField(label="Номер папки", width=250)
    add_author = ft.TextField(label="Автор произведения", width=300)
    add_title = ft.TextField(label="Название произведения", width=350)
    add_status = ft.Text("")

    def set_status(msg, color=ft.colors.BLUE):
        status_text.value = msg
        status_text.color = color
        page.update()

    def connect_to_sheets():
        def worker():
            try:
                set_status("⏳ Загрузка базы данных из Google Таблицы...", ft.colors.BLUE)
                scopes = [
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]
                credentials = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
                gc = gspread.authorize(credentials)
                sh = gc.open_by_url(GOOGLE_SHEET_URL)
                
                selected_ws = None
                for ws in sh.worksheets():
                    if ws.title.strip().lower() in ["лист1", "лист 1", "sheet1", "sheet 1"]:
                        selected_ws = ws
                        break
                if not selected_ws:
                    selected_ws = sh.worksheets()[0]
                
                worksheet[0] = selected_ws
                raw_data.clear()
                raw_data.extend(worksheet[0].get_all_values())
                filled_rows = [r for r in raw_data if any(str(c).strip() for c in r)]
                
                set_status(f"Готово! Подключено к листу: '{worksheet[0].title}'. Строк: {len(filled_rows)}", ft.colors.GREEN)
                run_search()
            except Exception as e:
                set_status(f"❌ Ошибка подключения: {e}", ft.colors.RED)
        threading.Thread(target=worker, daemon=True).start()

    def run_search(e=None):
        title_query = entry_title.value.strip()
        author_query = entry_author.value.strip()
        set_status("⏳ Выполняется интеллектуальный поиск...", ft.colors.BLUE)

        def search_worker():
            matching_items = []
            for idx, row in enumerate(raw_data):
                if not any(str(cell).strip() for cell in row):
                    continue
                row_str = " ".join([str(cell) for cell in row])
                t_matched = matches_search(title_query, row_str) if title_query else True
                a_matched = matches_search(author_query, row_str) if author_query else True
                if t_matched and a_matched:
                    c_folder = row[0] if len(row) > 0 else ""
                    c_author = row[1] if len(row) > 1 else ""
                    c_title = row[2] if len(row) > 2 else ""
                    matching_items.append((idx, (c_folder, c_author, c_title)))

            def update_ui():
                results_table.rows.clear()
                for original_idx, (fld, auth, ttl) in matching_items:
                    def make_handler(r_idx, f, a, t):
                        return lambda ev: select_row(r_idx, f, a, t)

                    results_table.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(fld)),
                                ft.DataCell(ft.Text(auth)),
                                ft.DataCell(ft.Text(ttl)),
                            ],
                            on_select_changed=make_handler(original_idx, fld, auth, ttl),
                        )
                    )
                set_status(f"Найдено совпадений: {len(matching_items)}", ft.colors.GREEN)
                page.update()

            page.run_task(update_ui) if hasattr(page, "run_task") else update_ui()

        threading.Thread(target=search_worker, daemon=True).start()

    def select_row(idx, fld, auth, ttl):
        selected_row_idx[0] = idx
        edit_folder.value = fld
        edit_author.value = auth
        edit_title.value = ttl
        set_status(f"Выбрана строка №{idx + 1} для редактирования", ft.colors.BLUE)
        page.update()

    def clear_search(e):
        entry_title.value = ""
        entry_author.value = ""
        run_search()

    def clear_edit(e):
        edit_folder.value = ""
        edit_author.value = ""
        edit_title.value = ""
        selected_row_idx[0] = None
        set_status("Форма редактирования очищена.", ft.colors.BLUE)
        page.update()

    def save_changes(e):
        if selected_row_idx[0] is None:
            set_status("⚠️ Сначала выберите строку в таблице!", ft.colors.RED)
            return
        new_folder = edit_folder.value.strip()
        new_author = edit_author.value.strip()
        new_title = edit_title.value.strip()
        sheet_row_num = selected_row_idx[0] + 1

        def worker():
            try:
                set_status("⏳ Сохранение изменений в таблицу...", ft.colors.BLUE)
                worksheet[0].update(
                    range_name=f"A{sheet_row_num}:C{sheet_row_num}",
                    values=[[new_folder, new_author, new_title]],
                    value_input_option="USER_ENTERED"
                )
                if selected_row_idx[0] < len(raw_data):
                    raw_data[selected_row_idx[0]] = [new_folder, new_author, new_title]
                set_status("✅ Изменения успешно сохранены!", ft.colors.GREEN)
                run_search()
            except Exception as err:
                set_status(f"❌ Ошибка сохранения: {err}", ft.colors.RED)
        threading.Thread(target=worker, daemon=True).start()

    def delete_note(e):
        if selected_row_idx[0] is None:
            set_status("⚠️ Сначала выберите строку для удаления!", ft.colors.RED)
            return
        sheet_row_num = selected_row_idx[0] + 1

        def worker():
            try:
                set_status("⏳ Удаление строки...", ft.colors.BLUE)
                worksheet[0].delete_rows(sheet_row_num)
                if selected_row_idx[0] < len(raw_data):
                    del raw_data[selected_row_idx[0]]
                clear_edit(None)
                set_status("🗑️ Строка удалена!", ft.colors.GREEN)
                run_search()
            except Exception as err:
                set_status(f"❌ Ошибка удаления: {err}", ft.colors.RED)
        threading.Thread(target=worker, daemon=True).start()

    def add_note(e):
        fld = add_folder.value.strip()
        auth = add_author.value.strip()
        ttl = add_title.value.strip()
        if not ttl and not fld:
            add_status.value = "Заполните хотя бы номер папки или название!"
            add_status.color = ft.colors.RED
            page.update()
            return

        def worker():
            try:
                set_status("⏳ Добавление новой записи...", ft.colors.BLUE)
                new_row = [fld, auth, ttl]
                all_vals = worksheet[0].get_all_values()
                last_filled = 0
                for idx, r in enumerate(all_vals, start=1):
                    if any(str(c).strip() for c in r):
                        last_filled = idx
                next_row = last_filled + 1
                if next_row > worksheet[0].row_count:
                    worksheet[0].add_rows(50)
                worksheet[0].update(
                    range_name=f"A{next_row}:C{next_row}",
                    values=[new_row],
                    value_input_option="USER_ENTERED"
                )
                if next_row - 1 < len(raw_data):
                    raw_data[next_row - 1] = new_row
                else:
                    while len(raw_data) < next_row - 1:
                        raw_data.append(["", "", ""])
                    raw_data.append(new_row)

                add_folder.value = ""
                add_author.value = ""
                add_title.value = ""
                add_status.value = f"✅ Успешно добавлено в строку №{next_row}!"
                add_status.color = ft.colors.GREEN
                set_status(f"✅ Добавлено в строку №{next_row}", ft.colors.GREEN)
                run_search()
            except Exception as err:
                add_status.value = f"Ошибка: {err}"
                add_status.color = ft.colors.RED
                set_status(f"❌ Ошибка добавления: {err}", ft.colors.RED)
            page.update()
        threading.Thread(target=worker, daemon=True).start()

    # --- Структура вкладок ---
    search_tab = ft.Tab(
        text="🔍 Поиск и база нот",
        content=ft.Container(
            padding=15,
            content=ft.Column([
                ft.Row([entry_title, entry_author], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
                ft.Row([
                    ft.ElevatedButton("🔍 Искать", on_click=run_search, bgcolor=ft.colors.BLUE_700, color=ft.colors.WHITE),
                    ft.ElevatedButton("🧹 Очистить", on_click=clear_search),
                    ft.ElevatedButton("🔄 Обновить", on_click=lambda e: connect_to_sheets()),
                ], spacing=10),
                results_container,
                ft.Divider(),
                ft.Text("✏️ Редактирование выбранной записи", weight=ft.FontWeight.BOLD),
                ft.Row([edit_folder, edit_author, edit_title], wrap=True, spacing=10),
                ft.Row([
                    ft.ElevatedButton("💾 Сохранить", on_click=save_changes, bgcolor=ft.colors.GREEN_700, color=ft.colors.WHITE),
                    ft.ElevatedButton("🧹 Очистить форму", on_click=clear_edit),
                    ft.ElevatedButton("🗑️ Удалить", on_click=delete_note, bgcolor=ft.colors.RED_700, color=ft.colors.WHITE),
                ], spacing=10),
            ], spacing=15, scroll=ft.ScrollMode.AUTO)
        )
    )

    add_tab = ft.Tab(
        text="➕ Добавить новое",
        content=ft.Container(
            padding=20,
            content=ft.Column([
                ft.Text("Форма добавления нового произведения", size=18, weight=ft.FontWeight.BOLD),
                add_folder,
                add_author,
                add_title,
                ft.ElevatedButton("💾 Сохранить в таблицу", on_click=add_note, bgcolor=ft.colors.GREEN_700, color=ft.colors.WHITE),
                add_status,
            ], spacing=15, alignment=ft.MainAxisAlignment.START)
        )
    )

    tabs = ft.Tabs(
        selected_index=0,
        animation_duration=300,
        tabs=[search_tab, add_tab],
        expand=True
    )

    page.add(
        ft.Column([
            status_text,
            tabs
        ], expand=True, spacing=10)
    )

    connect_to_sheets()

if __name__ == "__main__":
    ft.app(target=main)
