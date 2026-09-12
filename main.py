import os
import re
import threading
import gspread
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.clock import Clock

# --- НАСТРОЙКИ ---
CREDENTIALS_FILE = "credentials.json"
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1ipHOZB4Xjs0XLWbUDRAykXvCox4KW17l57Lmjky1hHU/edit"

class MusicLibraryApp(App):
    def build(self):
        self.worksheet = None
        self.raw_data = []

        # Главный контейнер (вертикальный)
        self.root_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        # Статус-бар сверху
        self.status_label = Label(text="Инициализация...", size_hint_y=None, height=40, color=(1, 1, 0, 1))
        self.root_layout.add_widget(self.status_label)

        # --- БЛОК ПОИСКА ---
        search_layout = BoxLayout(orientation='vertical', size_hint_y=None, height=130, spacing=5)
        
        self.search_title = TextInput(hint_text="Название произведения", multiline=False)
        self.search_author = TextInput(hint_text="Автор (Фамилия / Имя)", multiline=False)
        
        btn_search = Button(text="🔍 Найти ноты", background_color=(0.2, 0.6, 1, 1))
        btn_search.bind(on_press=self.start_search)

        search_layout.add_widget(self.search_title)
        search_layout.add_widget(self.search_author)
        search_layout.add_widget(btn_search)
        self.root_layout.add_widget(search_layout)

        # --- СПИСОК РЕЗУЛЬТАТОВ (вместо Treeview) ---
        self.scroll_view = ScrollView()
        self.results_grid = GridLayout(cols=1, spacing=5, size_hint_y=None)
        self.results_grid.bind(minimum_height=self.results_grid.setter('height'))
        self.scroll_view.add_widget(self.results_grid)
        self.root_layout.add_widget(self.scroll_view)

        # --- БЛОК ДОБАВЛЕНИЯ НОВЫХ НОТ ---
        add_layout = BoxLayout(orientation='vertical', size_hint_y=None, height=160, spacing=5)
        add_layout.add_widget(Label(text="➕ Добавить новое произведение:", size_hint_y=None, height=30))
        
        self.add_folder = TextInput(hint_text="Номер папки", multiline=False)
        self.add_author = TextInput(hint_text="Автор", multiline=False)
        self.add_title = TextInput(hint_text="Название произведения", multiline=False)
        
        btn_add = Button(text="Сохранить в базу", background_color=(0.2, 0.8, 0.2, 1))
        btn_add.bind(on_press=self.add_note)

        add_layout.add_widget(self.add_folder)
        add_layout.add_widget(self.add_author)
        add_layout.add_widget(self.add_title)
        add_layout.add_widget(btn_add)
        
        self.root_layout.add_widget(add_layout)

        # Запускаем подключение к Google Таблицам в фоне
        threading.Thread(target=self.connect_to_google_sheets, daemon=True).start()

        return self.root_layout

    # --- ЛОГИКА ---
    def update_status(self, text, dt=None):
        """Безопасное обновление текста в интерфейсе из другого потока"""
        self.status_label.text = text

    def connect_to_google_sheets(self):
        Clock.schedule_once(lambda dt: self.update_status("⏳ Подключение к Google Таблицам..."))
        try:
            if not os.path.exists(CREDENTIALS_FILE):
                Clock.schedule_once(lambda dt: self.update_status("❌ Ошибка: Файл ключа не найден!"))
                return

            gc = gspread.service_account(filename=CREDENTIALS_FILE)
            match = re.search(r'/d/([a-zA-Z0-9-_]+)', GOOGLE_SHEET_URL)
            sheet_id = match.group(1)
            sh = gc.open_by_key(sheet_id)
            self.worksheet = sh.worksheets()[0]
            self.raw_data = self.worksheet.get_all_values()
            
            Clock.schedule_once(lambda dt: self.update_status(f"✅ База загружена! Строк: {len(self.raw_data)}"))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.update_status("❌ Ошибка сети или доступа!"))
            print(f"Ошибка подключения: {e}")

    def start_search(self, instance):
        if not self.worksheet:
            self.update_status("⚠️ База еще не загрузилась. Подождите.")
            return
            
        title_q = self.search_title.text.lower().strip()
        author_q = self.search_author.text.lower().strip()
        
        self.results_grid.clear_widgets()
        self.update_status("⏳ Идет поиск...")

        count = 0
        for row in self.raw_data:
            if not any(str(c).strip() for c in row):
                continue
                
            folder = str(row[0]) if len(row) > 0 else ""
            author = str(row[1]) if len(row) > 1 else ""
            title = str(row[2]) if len(row) > 2 else ""

            # Простейший поиск по совпадению текста
            if (title_q in title.lower()) and (author_q in author.lower()):
                result_text = f"Папка: {folder} | {author} - {title}"
                lbl = Label(text=result_text, size_hint_y=None, height=50, 
                            text_size=(self.root_layout.width - 40, None), 
                            halign='left', valign='middle')
                self.results_grid.add_widget(lbl)
                count += 1

        self.update_status(f"🔍 Найдено совпадений: {count}")

    def add_note(self, instance):
        if not self.worksheet:
            self.update_status("⚠️ Нет подключения к таблице!")
            return
            
        folder = self.add_folder.text.strip()
        author = self.add_author.text.strip()
        title = self.add_title.text.strip()

        if not folder and not title:
            self.update_status("⚠️ Заполните хотя бы папку или название!")
            return

        self.update_status("⏳ Сохранение...")
        
        # Запускаем сохранение в фоне, чтобы интерфейс телефона не завис
        threading.Thread(target=self._add_to_sheet_worker, args=(folder, author, title), daemon=True).start()

    def _add_to_sheet_worker(self, folder, author, title):
        try:
            new_row = [folder, author, title]
            self.worksheet.append_row(new_row)
            self.raw_data.append(new_row)
            Clock.schedule_once(lambda dt: self._clear_add_inputs())
            Clock.schedule_once(lambda dt: self.update_status("✅ Произведение успешно добавлено!"))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.update_status(f"❌ Ошибка добавления: {e}"))

    def _clear_add_inputs(self):
        self.add_folder.text = ""
        self.add_author.text = ""
        self.add_title.text = ""


if __name__ == '__main__':
    MusicLibraryApp().run()
