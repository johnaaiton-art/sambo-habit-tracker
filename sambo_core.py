# sambo_core.py
import os
import json
import datetime
import logging
import gspread
from google.oauth2.service_account import Credentials

# Moscow timezone
MOSCOW_TZ = datetime.timezone(datetime.timedelta(hours=3))
logger = logging.getLogger(__name__)

class SamboBot:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.sheet_id = os.getenv("GOOGLE_SHEET_ID")
        self.user_id = os.getenv("TELEGRAM_USER_ID")  # Stored as string
        if not all([self.bot_token, self.sheet_id, self.user_id]):
            raise ValueError("Missing required environment variables")
        self.init_sheets()

    def init_sheets(self):
        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if not creds_json:
            raise ValueError("GOOGLE_CREDENTIALS_JSON not set")
        creds_dict = json.loads(creds_json)
        credentials = Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        self.gs_client = gspread.authorize(credentials)
        self.spreadsheet = self.gs_client.open_by_key(self.sheet_id)
        self.activity_sheet = self.spreadsheet.worksheet("Activity")
        self.consumption_sheet = self.spreadsheet.worksheet("Consumption")
        self.language_sheet = self.spreadsheet.worksheet("Language")
        logger.info("Google Sheets initialized")

    def get_moscow_now(self):
        return datetime.datetime.now(MOSCOW_TZ)

    def get_week_number(self, date=None):
        if date is None:
            date = self.get_moscow_now()
        days_since_monday = date.weekday()
        week_start = date - datetime.timedelta(days=days_since_monday)
        return week_start.strftime("%Y-%m-%d")

    def find_or_create_activity_row(self, user_id, date_str, week_number):
        all_data = self.activity_sheet.get_all_values()
        for i, row in enumerate(all_data[1:], start=2):
            if len(row) > 1 and str(row[0]) == str(user_id) and row[1] == date_str:
                return i
        new_row = [str(user_id), date_str, "", "", "", "", "", week_number, ""]
        self.activity_sheet.append_row(new_row)
        return len(all_data) + 1

    def record_activity(self, user_id, habit_id):
        now = self.get_moscow_now()
        today_str = now.strftime("%Y-%m-%d")
        week_number = self.get_week_number(now)
        habit_map = {
            1: ("Prayer", "Prayer with first water"),
            2: ("Qi Gong", "Qi Gong routine"),
            3: ("Ball", "Freestyling on the ball"),
            4: ("Run/Stretch", "20 minute run and stretch"),
            5: ("Strength/Stretch", "Strengthening and stretching")
        }
        if habit_id not in habit_map:
            return False, "Invalid habit number. Use 1-5."
        column_name, habit_name = habit_map[habit_id]
        row_num = self.find_or_create_activity_row(user_id, today_str, week_number)
        if not row_num:
            return False, "Failed to create activity row"
        headers = self.activity_sheet.row_values(1)
        try:
            col_index = headers.index(column_name) + 1
        except ValueError:
            self.activity_sheet.update_cell(1, len(headers) + 1, column_name)
            col_index = len(headers) + 1
        current_value = self.activity_sheet.cell(row_num, col_index).value
        if current_value and str(current_value).strip():
            return False, f"{habit_name} already recorded today"
        timestamp = now.strftime("%H:%M")
        self.activity_sheet.update_cell(row_num, col_index, f"✓ ({timestamp})")
        return True, f"✓ {habit_name} recorded at {timestamp}!"

    def find_or_create_consumption_row(self, user_id, date_str, week_number):
        all_data = self.consumption_sheet.get_all_values()
        for i, row in enumerate(all_data[1:], start=2):
            if len(row) > 1 and str(row[0]) == str(user_id) and row[1] == date_str:
                return i
        new_row = [str(user_id), date_str, 0, 0, 0, 0, 0, 0, week_number, ""]
        self.consumption_sheet.append_row(new_row)
        return len(all_data) + 1

    def record_consumption(self, user_id, text):
        now = self.get_moscow_now()
        today_str = now.strftime("%Y-%m-%d")
        week_number = self.get_week_number(now)
        text = text.strip().lower()
        parts = text.split()
        if not parts or parts[0][0] not in ['x', 'y', 'z']:
            return False, "Invalid format. Use: x, xx, xx 150, y 75, z"
        habit_type = parts[0][0]
        count = len(parts[0])
        cost = 0
        if len(parts) > 1 and parts[1].replace('.', '').isdigit():
            cost = int(float(parts[1]))
        col_map = {
            'x': {'count_col': 'Coffee (x)', 'cost_col': 'Coffee Cost', 'name': 'Coffee'},
            'y': {'count_col': 'Sugary (y)', 'cost_col': 'Sugary Cost', 'name': 'Sugary drinks'},
            'z': {'count_col': 'Flour (z)', 'cost_col': 'Flour Cost', 'name': 'Flour products'}
        }
        if habit_type not in col_map:
            return False, "Invalid type. Use x, y, or z"
        config = col_map[habit_type]
        row_num = self.find_or_create_consumption_row(user_id, today_str, week_number)
        if not row_num:
            return False, "Failed to create consumption row"
        headers = self.consumption_sheet.row_values(1)
        try:
            count_col_index = headers.index(config['count_col']) + 1
        except ValueError:
            self.consumption_sheet.update_cell(1, len(headers) + 1, config['count_col'])
            count_col_index = len(headers) + 1
        try:
            cost_col_index = headers.index(config['cost_col']) + 1  # FIXED typo
        except ValueError:
            self.consumption_sheet.update_cell(1, len(headers) + 2, config['cost_col'])
            cost_col_index = len(headers) + 2
        current_count = self.consumption_sheet.cell(row_num, count_col_index).value or 0
        current_cost = self.consumption_sheet.cell(row_num, cost_col_index).value or 0
        new_count = int(current_count) + count
        new_cost = int(current_cost) + cost
        self.consumption_sheet.update_cell(row_num, count_col_index, new_count)
        self.consumption_sheet.update_cell(row_num, cost_col_index, new_cost)
        cost_text = f" ({cost} rub)" if cost > 0 else ""
        return True, f"✓ {config['name']} x{count} recorded{cost_text}! Total today: {new_count}"

    def find_or_create_language_row(self, user_id, date_str, week_number):
        all_data = self.language_sheet.get_all_values()
        for i, row in enumerate(all_data[1:], start=2):
            if len(row) > 1 and str(row[0]) == str(user_id) and row[1] == date_str:
                return i
        new_row = [str(user_id), date_str, 0, 0, 0, week_number, ""]
        self.language_sheet.append_row(new_row)
        return len(all_data) + 1

    def record_language(self, user_id, lang_code):
        now = self.get_moscow_now()
        today_str = now.strftime("%Y-%m-%d")
        week_number = self.get_week_number(now)
        lang_map = {
            'ch': ('Chinese (ch)', 'Chinese'),
            'he': ('Hebrew (he)', 'Hebrew'),
            'ta': ('Tatar (ta)', 'Tatar')
        }
        if lang_code not in lang_map:
            return False, "Invalid language code. Use: ch, he, ta"
        column_name, lang_name = lang_map[lang_code]
        row_num = self.find_or_create_language_row(user_id, today_str, week_number)
        if not row_num:
            return False, "Failed to create language row"
        headers = self.language_sheet.row_values(1)
        try:
            col_index = headers.index(column_name) + 1
        except ValueError:
            self.language_sheet.update_cell(1, len(headers) + 1, column_name)
            col_index = len(headers) + 1
        current_value = self.language_sheet.cell(row_num, col_index).value or 0
        new_sessions = int(current_value) + 1
        timestamp = now.strftime("%H:%M")
        self.language_sheet.update_cell(row_num, col_index, new_sessions)
        return True, f"✓ {lang_name} session #{new_sessions} recorded at {timestamp}!"
