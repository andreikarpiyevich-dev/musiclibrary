import os
from pathlib import Path
import flet as ft
import gspread

# Функция для корректного поиска credentials.json на компьютере и в памяти телефона (Android)
def get_credentials_path():
    default_path = Path(__file__).parent / "credentials.json"
    assets_dir = Path(os.environ.get("FLET_ASSETS_DIR", str(Path(__file__).parent / "assets")))
    
    path_in_assets = assets_dir / "credentials.json"
    if path_in_assets.exists():
        return str(path_in_assets)
    return str(default_path)

def main(page: ft.Page):
    page.title = "Music Library"
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.VERTICAL

    # Статус подключения к Google Таблицам
    status_text = ft.Text("Подключение к таблице...", color=ft.colors.BLUE)
    
    sheet = None
    try:
        cred_path = get_credentials_path()
        gc = gspread.service_account(filename=cred_path)
        # ВНИМАНИЕ: Замените "MusicLibrary" на точное название вашей Google Таблицы
        sh = gc.open("MusicLibrary") 
        sheet = sh.sheet1
        status_text.value = "Подключено к Google Таблицам!"
        status_text.color = ft.colors.GREEN
    except Exception as e:
        status_text.value = f"Ошибка подключения: {e}"
        status_text.color = ft.colors.RED

    # --- Элементы вкладки "Поиск" ---
    search_input = ft.TextField(label="Введите название или исполнителя", width=300)
    results_column = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)

    def on_search_click(e):
        query = search_input.value.strip()
        if not query:
            return
        
        results_column.controls.clear()
        results_column.controls.append(ft.Text(f"Поиск: {query}"))
        
        # Сюда вы можете вставить вашу логику поиска (rapidfuzz, транслитерация и т.д.)
        # Например, чтение строк из таблицы:
        if sheet:
            try:
                records = sheet.get_all_records()
                results_column.controls.append(ft.Text(f"Всего записей в таблице: {len(records)}"))
            except Exception as err:
                results_column.controls.append(ft.Text(f"Ошибка чтения таблицы: {err}"))
        
        page.update()

    search_tab = ft.Tab(
        text="Поиск",
        content=ft.Container(
            padding=20,
            content=ft.Column([
                status_text,
                search_input,
                ft.ElevatedButton("Найти", on_click=on_search_click),
                results_column
            ], alignment=ft.MainAxisAlignment.START)
        )
    )

    # --- Элементы вкладки "Добавить" ---
    add_input = ft.TextField(label="Новая запись", width=300)
    add_status = ft.Text()

    def on_add_click(e):
        val = add_input.value.strip()
        if val and sheet:
            try:
                sheet.append_row([val])
                add_status.value = "Успешно добавлено!"
                add_status.color = ft.colors.GREEN
                add_input.value = ""
            except Exception as err:
                add_status.value = f"Ошибка: {err}"
                add_status.color = ft.colors.RED
            page.update()

    add_tab = ft.Tab(
        text="Добавить",
        content=ft.Container(
            padding=20,
            content=ft.Column([
                add_input,
                ft.ElevatedButton("Сохранить в таблицу", on_click=on_add_click),
                add_status
            ], alignment=ft.MainAxisAlignment.START)
        )
    )

    # Главные вкладки приложения
    tabs = ft.Tabs(
        selected_index=0,
        animation_duration=300,
        tabs=[search_tab, add_tab],
        expand=True
    )

    page.add(tabs)

if __name__ == "__main__":
    ft.app(target=main)
