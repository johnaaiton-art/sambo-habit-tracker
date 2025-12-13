import os
import json
import asyncio
import datetime
import logging
import gspread

from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================== LOGGING ==================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== TIMEZONE ==================
MOSCOW_TZ = datetime.timezone(datetime.timedelta(hours=3))

# ================== BOT LOGIC ==================
class SamboBot:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.sheet_id = os.getenv("GOOGLE_SHEET_ID")
        self.user_id = os.getenv("TELEGRAM_USER_ID")

        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set")

        self.init_sheets()

    def init_sheets(self):
        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if not creds_json:
            raise ValueError("GOOGLE_CREDENTIALS_JSON not set")

        creds_dict = json.loads(creds_json)

        credentials = Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )

        self.gs_client = gspread.authorize(credentials)
        self.spreadsheet = self.gs_client.open_by_key(self.sheet_id)

        self.activity_sheet = self.spreadsheet.worksheet("Activity")
        self.consumption_sheet = self.spreadsheet.worksheet("Consumption")
        self.language_sheet = self.spreadsheet.worksheet("Language")

        logger.info("Google Sheets initialized")

    def now(self):
        return datetime.datetime.now(MOSCOW_TZ)

    def week_start(self, date=None):
        date = date or self.now()
        monday = date - datetime.timedelta(days=date.weekday())
        return monday.strftime("%Y-%m-%d")

    # ---------- ACTIVITY ----------
    def record_activity(self, user_id, habit_id):
        habit_map = {
            1: ("Prayer", "Prayer with first water"),
            2: ("Qi Gong", "Qi Gong routine"),
            3: ("Ball", "Ball freestyling"),
            4: ("Run/Stretch", "Run & Stretch"),
            5: ("Strength/Stretch", "Strength & Stretch"),
        }

        if habit_id not in habit_map:
            return False, "Invalid habit"

        now = self.now()
        date_str = now.strftime("%Y-%m-%d")
        week = self.week_start(now)

        col_name, habit_name = habit_map[habit_id]
        row = self._find_or_create(self.activity_sheet, user_id, date_str, week)

        headers = self.activity_sheet.row_values(1)
        if col_name not in headers:
            self.activity_sheet.update_cell(1, len(headers) + 1, col_name)
            headers.append(col_name)

        col = headers.index(col_name) + 1
        current = self.activity_sheet.cell(row, col).value

        if current:
            return False, f"{habit_name} already recorded"

        self.activity_sheet.update_cell(row, col, f"✓ ({now.strftime('%H:%M')})")
        return True, f"✓ {habit_name} recorded"

    # ---------- CONSUMPTION ----------
    def record_consumption(self, user_id, text):
        now = self.now()
        date_str = now.strftime("%Y-%m-%d")
        week = self.week_start(now)

        parts = text.split()
        letter = parts[0][0]
        count = len(parts[0])
        cost = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0

        mapping = {
            "x": ("Coffee (x)", "Coffee Cost", "Coffee"),
            "y": ("Sugary (y)", "Sugary Cost", "Sugary"),
            "z": ("Flour (z)", "Flour Cost", "Flour"),
        }

        if letter not in mapping:
            return False, "Invalid format"

        count_col, cost_col, name = mapping[letter]
        row = self._find_or_create(self.consumption_sheet, user_id, date_str, week)

        headers = self.consumption_sheet.row_values(1)
        for col in (count_col, cost_col):
            if col not in headers:
                self.consumption_sheet.update_cell(1, len(headers) + 1, col)
                headers.append(col)

        ci = headers.index(count_col) + 1
        co = headers.index(cost_col) + 1

        new_count = int(self.consumption_sheet.cell(row, ci).value or 0) + count
        new_cost = int(self.consumption_sheet.cell(row, co).value or 0) + cost

        self.consumption_sheet.update_cell(row, ci, new_count)
        self.consumption_sheet.update_cell(row, co, new_cost)

        return True, f"✓ {name} x{count} recorded"

    # ---------- LANGUAGE ----------
    def record_language(self, user_id, code):
        now = self.now()
        date_str = now.strftime("%Y-%m-%d")
        week = self.week_start(now)

        mapping = {
            "ch": ("Chinese (ch)", "Chinese"),
            "he": ("Hebrew (he)", "Hebrew"),
            "ta": ("Tatar (ta)", "Tatar"),
        }

        if code not in mapping:
            return False, "Invalid language"

        col_name, label = mapping[code]
        row = self._find_or_create(self.language_sheet, user_id, date_str, week)

        headers = self.language_sheet.row_values(1)
        if col_name not in headers:
            self.language_sheet.update_cell(1, len(headers) + 1, col_name)
            headers.append(col_name)

        col = headers.index(col_name) + 1
        current = int(self.language_sheet.cell(row, col).value or 0)
        self.language_sheet.update_cell(row, col, current + 1)

        return True, f"✓ {label} session recorded"

    # ---------- ROW HELPERS ----------
    def _find_or_create(self, sheet, user_id, date_str, week):
        rows = sheet.get_all_values()
        for i, r in enumerate(rows[1:], start=2):
            if r and r[0] == str(user_id) and r[1] == date_str:
                return i
        sheet.append_row([str(user_id), date_str, "", "", "", "", week])
        return len(rows) + 1


# ================== TELEGRAM HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🥋 Sambo Habit Tracker ready")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot: SamboBot = context.bot_data["bot"]
    user_id = update.effective_user.id

    if str(user_id) != bot.user_id:
        return

    text = update.message.text.lower().strip()

    if text in ("ch", "he", "ta"):
        ok, msg = bot.record_language(user_id, text)
    elif text and text[0] in ("x", "y", "z"):
        ok, msg = bot.record_consumption(user_id, text)
    else:
        await update.message.reply_text("Unknown command")
        return

    await update.message.reply_text(msg)

async def habit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot: SamboBot = context.bot_data["bot"]
    user_id = update.effective_user.id

    if str(user_id) != bot.user_id:
        return

    habit_id = int(context.args[0])
    ok, msg = bot.record_activity(user_id, habit_id)
    await update.message.reply_text(msg)


# ================== GLOBAL APP (CRITICAL) ==================
APP: Application | None = None
LOOP = asyncio.get_event_loop()

def init_app():
    global APP
    if APP:
        return APP

    sambo = SamboBot()

    app = ApplicationBuilder().token(sambo.bot_token).build()
    app.bot_data["bot"] = sambo

    app.add_handler(CommandHandler("start", start))
    for i in range(1, 6):
        app.add_handler(CommandHandler(str(i), habit))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    LOOP.run_until_complete(app.initialize())
    APP = app

    logger.info("Telegram app initialized ONCE")
    return APP


# ================== YANDEX WEBHOOK ENTRY ==================
def handler(event, context):
    try:
        if "body" not in event:
            return {"statusCode": 400, "body": ""}

        app = init_app()

        update = Update.de_json(json.loads(event["body"]), app.bot)
        LOOP.run_until_complete(app.process_update(update))

        return {"statusCode": 200, "body": ""}

    except Exception:
        logger.exception("Webhook failure")
        return {"statusCode": 500, "body": ""}
