import os
import json
import datetime
import logging
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Moscow timezone
MOSCOW_TZ = datetime.timezone(datetime.timedelta(hours=3))


class SamboBot:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.sheet_id = os.getenv("GOOGLE_SHEET_ID")
        self.user_id = os.getenv("TELEGRAM_USER_ID")

        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set")
        if not self.sheet_id:
            raise ValueError("GOOGLE_SHEET_ID not set")
        if not self.user_id:
            raise ValueError("TELEGRAM_USER_ID not set")

        self.init_sheets()

    def init_sheets(self):
        """Initialize Google Sheets connection"""
        try:
            creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
            if not creds_path:
                raise ValueError("GOOGLE_CREDENTIALS_PATH not set")

            with open(creds_path, "r") as f:
                creds_dict = json.load(f)

            credentials = Credentials.from_service_account_info(
                creds_dict,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )

            self.gs_client = gspread.authorize(credentials)
            self.spreadsheet = self.gs_client.open_by_key(self.sheet_id)

            self.activity_sheet = self.spreadsheet.worksheet("Activity")
            self.consumption_sheet = self.spreadsheet.worksheet("Consumption")
            self.language_sheet = self.spreadsheet.worksheet("Language")

            logger.info("✅ Google Sheets initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Sheets: {e}")
            raise

    def get_moscow_now(self):
        return datetime.datetime.now(MOSCOW_TZ)

    def get_week_number(self, date=None):
        if date is None:
            date = self.get_moscow_now()
        days_since_monday = date.weekday()
        week_start = date - datetime.timedelta(days=days_since_monday)
        return week_start.strftime("%Y-%m-%d")

    # ===================== ACTIVITY (FIXED) =====================

    def record_activity(self, user_id, habit_id):
        """Record activity habit safely into a single daily row"""
        try:
            now = self.get_moscow_now()
            today_str = now.strftime("%Y-%m-%d")
            week_number = self.get_week_number(now)

            habit_map = {
                1: ("Prayer", "Prayer with first water"),
                2: ("Qi Gong", "Qi Gong routine"),
                3: ("Ball", "Ball freestyling"),
                4: ("Run/Stretch", "20 minute run and stretch"),
                5: ("Strength/Stretch", "Strengthening and stretching")
            }

            if habit_id not in habit_map:
                return False, "Invalid habit number. Use 1-5."

            column_name, habit_name = habit_map[habit_id]

            logger.info(f"📝 Recording {habit_name} for {user_id} on {today_str}")

            row_num = self.find_or_create_activity_row(user_id, today_str, week_number)
            if not row_num:
                return False, "Failed to create activity row"

            headers = [h.strip() for h in self.activity_sheet.row_values(1)]

            if column_name not in headers:
                return False, f"Column '{column_name}' not found in Activity sheet"

            col_index = headers.index(column_name) + 1

            current_value = self.activity_sheet.cell(row_num, col_index).value
            if current_value and str(current_value).strip():
                return False, f"{habit_name} already recorded today"

            self.activity_sheet.update_cell(row_num, col_index, "✓")

            timestamp = now.strftime("%H:%M")
            return True, f"✓ {habit_name} recorded at {timestamp}!"

        except Exception as e:
            logger.error(f"❌ Error recording activity: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, "Error recording habit"

    def find_or_create_activity_row(self, user_id, date_str, week_number):
        """Find or create a full-width row mapped by headers"""
        try:
            all_data = self.activity_sheet.get_all_values()
            headers = [h.strip() for h in self.activity_sheet.row_values(1)]
            col_map = {h: i for i, h in enumerate(headers)}

            for i, row in enumerate(all_data[1:], start=2):
                if len(row) < len(headers):
                    row += [""] * (len(headers) - len(row))

                row_user = str(row[col_map["User ID"]]).strip()
                row_date = str(row[col_map["Date"]]).strip()

                if row_user == str(user_id) and row_date == date_str:
                    logger.info(f"🎯 Found activity row at {i}")
                    return i

            logger.info("📝 Creating new activity row")

            new_row = [""] * len(headers)
            new_row[col_map["User ID"]] = str(user_id)
            new_row[col_map["Date"]] = date_str
            new_row[col_map["Week Number"]] = week_number
            new_row[col_map["Goals"]] = ""

            self.activity_sheet.append_row(new_row)
            return len(all_data) + 1

        except Exception as e:
            logger.error(f"❌ Error finding activity row: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    # ===================== CONSUMPTION =====================

    def record_consumption(self, user_id, text):
        try:
            now = self.get_moscow_now()
            today_str = now.strftime("%Y-%m-%d")
            week_number = self.get_week_number(now)

            text = text.strip().lower()
            parts = text.split()

            if not parts:
                return False, "Invalid format. Use: x, xx, xxx, y, z"

            first_part = parts[0]
            if not first_part or first_part[0] not in ['x', 'y', 'z']:
                return False, "Start with x, y, or z"

            habit_type = first_part[0]
            count = len(first_part)

            if not all(c == habit_type for c in first_part):
                return False, f"Use only '{habit_type}' characters"

            cost = 0
            if len(parts) > 1:
                try:
                    cost = int(float(parts[1]))
                except (ValueError, IndexError):
                    cost = 0

            col_map = {
                'x': {'count_col': 'Coffee (x)', 'cost_col': 'Coffee Cost', 'name': 'Coffee'},
                'y': {'count_col': 'Sugary (y)', 'cost_col': 'Sugary Cost', 'name': 'Sugary drinks'},
                'z': {'count_col': 'Flour (z)', 'cost_col': 'Flour Cost', 'name': 'Flour products'}
            }

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
                headers = self.consumption_sheet.row_values(1)

            try:
                cost_col_index = headers.index(config['cost_col']) + 1
            except ValueError:
                self.consumption_sheet.update_cell(1, len(headers) + 1, config['cost_col'])
                cost_col_index = len(headers) + 1

            current_count_val = self.consumption_sheet.cell(row_num, count_col_index).value
            current_cost_val = self.consumption_sheet.cell(row_num, cost_col_index).value

            try:
                current_count = int(current_count_val) if current_count_val and str(current_count_val).strip() else 0
            except (ValueError, TypeError):
                current_count = 0

            try:
                current_cost = int(current_cost_val) if current_cost_val and str(current_cost_val).strip() else 0
            except (ValueError, TypeError):
                current_cost = 0

            new_count = current_count + count
            new_cost = current_cost + cost

            self.consumption_sheet.update_cell(row_num, count_col_index, new_count)
            if cost > 0:
                self.consumption_sheet.update_cell(row_num, cost_col_index, new_cost)

            cost_text = f" ({cost} rub)" if cost > 0 else ""
            return True, f"✓ {config['name']} x{count} recorded{cost_text}! Total: {new_count}"

        except Exception as e:
            logger.error(f"❌ Error recording consumption: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, "Error recording consumption"

    def find_or_create_consumption_row(self, user_id, date_str, week_number):
        try:
            all_data = self.consumption_sheet.get_all_values()

            for i, row in enumerate(all_data[1:], start=2):
                if len(row) >= 2:
                    row_user = str(row[0]).strip() if row[0] else ""
                    row_date = str(row[1]).strip() if row[1] else ""
                    if row_user == str(user_id) and row_date == date_str:
                        return i

            headers = self.consumption_sheet.row_values(1)
            new_row = [str(user_id), date_str]

            for i in range(2, len(headers)):
                header_name = headers[i]
                if "Cost" in header_name or header_name in ['Coffee (x)', 'Sugary (y)', 'Flour (z)']:
                    new_row.append(0)
                elif header_name == "Week Number":
                    new_row.append(week_number)
                else:
                    new_row.append("")

            self.consumption_sheet.append_row(new_row)
            return len(all_data) + 1

        except Exception as e:
            logger.error(f"Error finding consumption row: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    # ===================== LANGUAGE =====================

    def record_language(self, user_id, lang_code):
        try:
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

            col_index = None
            for idx, header in enumerate(headers, start=1):
                if header.strip() == column_name:
                    col_index = idx
                    break

            if col_index is None:
                self.language_sheet.update_cell(1, len(headers) + 1, column_name)
                col_index = len(headers) + 1

            current_value = self.language_sheet.cell(row_num, col_index).value
            try:
                current_sessions = int(current_value) if current_value and str(current_value).strip() else 0
            except (ValueError, TypeError):
                current_sessions = 0

            new_sessions = current_sessions + 1
            timestamp = now.strftime("%H:%M")

            self.language_sheet.update_cell(row_num, col_index, new_sessions)

            return True, f"✓ {lang_name} session #{new_sessions} recorded at {timestamp}!"

        except Exception as e:
            logger.error(f"❌ Error recording language: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, "Error recording language"

    def find_or_create_language_row(self, user_id, date_str, week_number):
        try:
            all_data = self.language_sheet.get_all_values()

            for i, row in enumerate(all_data[1:], start=2):
                if len(row) >= 2:
                    row_user = str(row[0]).strip() if row[0] else ""
                    row_date = str(row[1]).strip() if row[1] else ""
                    if row_user == str(user_id) and row_date == date_str:
                        return i

            headers = self.language_sheet.row_values(1)
            new_row = [str(user_id), date_str]

            for i in range(2, len(headers)):
                header_name = headers[i]
                if header_name in ['Chinese (ch)', 'Hebrew (he)', 'Tatar (ta)']:
                    new_row.append(0)
                elif header_name == "Week Number":
                    new_row.append(week_number)
                else:
                    new_row.append("")

            self.language_sheet.append_row(new_row)
            return len(all_data) + 1

        except Exception as e:
            logger.error(f"Error finding language row: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None


# ================= TELEGRAM HANDLERS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🥋 Sambo Habit Tracker Bot

📊 ACTIVITY:
/1 Prayer
/2 Qi Gong
/3 Ball
/4 Run/Stretch
/5 Strength/Stretch

🍽 CONSUMPTION:
x, xx, xxx (+ cost)
y, yy, yyy
z, zz, zzz

🌍 LANGUAGES:
ch, he, ta
"""
    await update.message.reply_text(help_text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot = context.bot_data["sambo_bot"]
    user_id = update.effective_user.id

    if user_id != int(bot.user_id):
        await update.message.reply_text("Unauthorized.")
        return

    text = update.message.text.strip().lower()

    if text in ['ch', 'he', 'ta']:
        success, message = bot.record_language(user_id, text)
        await update.message.reply_text(message)
        return

    if text and text[0] in ['x', 'y', 'z']:
        success, message = bot.record_consumption(user_id, text)
        await update.message.reply_text(message)
        return

    await update.message.reply_text("Unknown command. /help")


async def handle_activity(update: Update, context: ContextTypes.DEFAULT_TYPE, habit_id: int):
    bot = context.bot_data["sambo_bot"]
    user_id = update.effective_user.id

    if user_id != int(bot.user_id):
        await update.message.reply_text("Unauthorized.")
        return

    success, message = bot.record_activity(user_id, habit_id)
    await update.message.reply_text(message)


async def habit_1(update: Update, context: ContextTypes.DEFAULT_TYPE): await handle_activity(update, context, 1)
async def habit_2(update: Update, context: ContextTypes.DEFAULT_TYPE): await handle_activity(update, context, 2)
async def habit_3(update: Update, context: ContextTypes.DEFAULT_TYPE): await handle_activity(update, context, 3)
async def habit_4(update: Update, context: ContextTypes.DEFAULT_TYPE): await handle_activity(update, context, 4)
async def habit_5(update: Update, context: ContextTypes.DEFAULT_TYPE): await handle_activity(update, context, 5)


# ===================== MAIN =====================

def main():
    try:
        logger.info("🚀 Starting Sambo Bot...")
        bot = SamboBot()

        application = Application.builder().token(bot.bot_token).build()
        application.bot_data["sambo_bot"] = bot

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("1", habit_1))
        application.add_handler(CommandHandler("2", habit_2))
        application.add_handler(CommandHandler("3", habit_3))
        application.add_handler(CommandHandler("4", habit_4))
        application.add_handler(CommandHandler("5", habit_5))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        logger.error(f"❌ Failed to start: {e}")
        raise


if __name__ == '__main__':
    main()
