import os
import json
import datetime
import logging
from aiohttp import web
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Configure logging - MORE VERBOSE
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Changed to DEBUG for more info
)
logger = logging.getLogger(__name__)

# Moscow timezone
MOSCOW_TZ = datetime.timezone(datetime.timedelta(hours=3))

class SamboBot:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.sheet_id = os.getenv("GOOGLE_SHEET_ID")
        self.user_id = os.getenv("TELEGRAM_USER_ID")
        
        logger.info(f"Initializing bot with token: {self.bot_token[:10]}...")
        logger.info(f"Sheet ID: {self.sheet_id}")
        logger.info(f"User ID: {self.user_id}")
        
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set")
            
        self.init_sheets()
    
    def init_sheets(self):
        """Initialize Google Sheets connection"""
        try:
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
            
            logger.info("Google Sheets initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets: {e}")
            raise
    
    def get_moscow_now(self):
        return datetime.datetime.now(MOSCOW_TZ)
    
    def get_week_number(self, date=None):
        if date is None:
            date = self.get_moscow_now()
        days_since_monday = date.weekday()
        week_start = date - datetime.timedelta(days=days_since_monday)
        return week_start.strftime("%Y-%m-%d")

    def record_activity(self, user_id, habit_id):
        try:
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
                return False, f"Invalid habit number. Use 1-5."
            
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
            if current_value and current_value.strip():
                return False, f"{habit_name} already recorded today"
            
            timestamp = now.strftime("%H:%M")
            self.activity_sheet.update_cell(row_num, col_index, f"✓ ({timestamp})")
            logger.info(f"Recorded habit {habit_id} for user {user_id}")
            return True, f"✓ {habit_name} recorded at {timestamp}!"
        except Exception as e:
            logger.error(f"Error recording activity: {e}")
            return False, "Error recording habit"

    def find_or_create_activity_row(self, user_id, date_str, week_number):
        try:
            all_data = self.activity_sheet.get_all_values()
            for i, row in enumerate(all_data[1:], start=2):
                if len(row) > 1 and str(row[0]) == str(user_id) and row[1] == date_str:
                    return i
            new_row = [str(user_id), date_str, "", "", "", "", "", week_number, ""]
            self.activity_sheet.append_row(new_row)
            return len(all_data) + 1
        except Exception as e:
            logger.error(f"Error finding activity row: {e}")
            return None

    def record_consumption(self, user_id, text):
        try:
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
                cost_col_index = headers.index(config['cost_col']) + 1
            except ValueError:
                self.consumption_sheet.update_cell(1, len(headers) + 2, config['cost_col'])
                cost_col_index = len(headers) + 2
            current_count = self.consumption_sheet.cell(row_num, count_col_index).value
            current_cost = self.consumption_sheet.cell(row_num, cost_col_index).value
            new_count = int(current_count or 0) + count
            new_cost = int(current_cost or 0) + cost
            self.consumption_sheet.update_cell(row_num, count_col_index, new_count)
            self.consumption_sheet.update_cell(row_num, cost_col_index, new_cost)
            logger.info(f"Recorded consumption {habit_type} x{count} for user {user_id}")
            cost_text = f" ({cost} rub)" if cost > 0 else ""
            return True, f"✓ {config['name']} x{count} recorded{cost_text}! Total today: {new_count}"
        except Exception as e:
            logger.error(f"Error recording consumption: {e}")
            return False, "Error recording consumption"

    def find_or_create_consumption_row(self, user_id, date_str, week_number):
        try:
            all_data = self.consumption_sheet.get_all_values()
            for i, row in enumerate(all_data[1:], start=2):
                if len(row) > 1 and str(row[0]) == str(user_id) and row[1] == date_str:
                    return i
            new_row = [str(user_id), date_str, 0, 0, 0, 0, 0, 0, week_number, ""]
            self.consumption_sheet.append_row(new_row)
            return len(all_data) + 1
        except Exception as e:
            logger.error(f"Error finding consumption row: {e}")
            return None

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
            try:
                col_index = headers.index(column_name) + 1
            except ValueError:
                self.language_sheet.update_cell(1, len(headers) + 1, column_name)
                col_index = len(headers) + 1
            current_value = self.language_sheet.cell(row_num, col_index).value
            current_sessions = int(current_value or 0)
            new_sessions = current_sessions + 1
            timestamp = now.strftime("%H:%M")
            self.language_sheet.update_cell(row_num, col_index, new_sessions)
            logger.info(f"Recorded language {lang_code} for user {user_id}")
            return True, f"✓ {lang_name} session #{new_sessions} recorded at {timestamp}!"
        except Exception as e:
            logger.error(f"Error recording language: {e}")
            return False, "Error recording language"

    def find_or_create_language_row(self, user_id, date_str, week_number):
        try:
            all_data = self.language_sheet.get_all_values()
            for i, row in enumerate(all_data[1:], start=2):
                if len(row) > 1 and str(row[0]) == str(user_id) and row[1] == date_str:
                    return i
            new_row = [str(user_id), date_str, 0, 0, 0, week_number, ""]
            self.language_sheet.append_row(new_row)
            return len(all_data) + 1
        except Exception as e:
            logger.error(f"Error finding language row: {e}")
            return None


# ========== Telegram Handlers ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🥋 Sambo Habit Tracker Bot

📊 ACTIVITY HABITS:
/1 - Prayer with first water
/2 - Qi Gong routine
/3 - Ball freestyling
/4 - Run/Stretch (20 min)
/5 - Strength/Stretch

🍽 CONSUMPTION (text message):
x, xx, xxx - Coffee (+ optional cost)
y, yy, yyy - Sugary drinks
z, zz, zzz - Flour products
Example: "xx 150" = 2 coffees, 150 rub

🌍 LANGUAGE LEARNING:
ch - Chinese session
he - Hebrew session
ta - Tatar session

Type /help to see this message again.
"""
    await update.message.reply_text(help_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot = context.bot_data["sambo_bot"]
    user_id = update.effective_user.id
    
    if user_id != int(bot.user_id):
        await update.message.reply_text("Sorry, this bot is for authorized users only.")
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
    
    await update.message.reply_text("Unknown command. Type /help for instructions.")

async def handle_activity(update: Update, context: ContextTypes.DEFAULT_TYPE, habit_id: int):
    bot = context.bot_data["sambo_bot"]
    user_id = update.effective_user.id
    
    if user_id != int(bot.user_id):
        await update.message.reply_text("Sorry, this bot is for authorized users only.")
        return
    
    success, message = bot.record_activity(user_id, habit_id)
    await update.message.reply_text(message)

async def habit_1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_activity(update, context, 1)

async def habit_2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_activity(update, context, 2)

async def habit_3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_activity(update, context, 3)

async def habit_4(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_activity(update, context, 4)

async def habit_5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_activity(update, context, 5)


# ========== GLOBAL BOT INSTANCE ==========
# Initialize ONCE at module level, not per request
logger.info("Creating global bot instance...")
sambo_bot = SamboBot()
app = ApplicationBuilder().token(sambo_bot.bot_token).build()
app.bot_data["sambo_bot"] = sambo_bot

# Register all handlers
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("1", habit_1))
app.add_handler(CommandHandler("2", habit_2))
app.add_handler(CommandHandler("3", habit_3))
app.add_handler(CommandHandler("4", habit_4))
app.add_handler(CommandHandler("5", habit_5))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

logger.info("Bot handlers registered")


# ========== WEBHOOK HTTP SERVER ==========
async def webhook_handler(request):
    """Handle incoming webhook POST requests from Telegram"""
    try:
        logger.info("=" * 60)
        logger.info("WEBHOOK REQUEST RECEIVED")
        logger.info(f"Method: {request.method}")
        logger.info(f"Path: {request.path}")
        logger.info(f"Headers: {dict(request.headers)}")
        
        # Read raw body
        raw_body = await request.read()
        logger.info(f"Raw body (first 500 chars): {raw_body[:500]}")
        
        # Parse JSON
        try:
            update_data = json.loads(raw_body)
            logger.info(f"Parsed JSON successfully: {json.dumps(update_data, indent=2)[:500]}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return web.Response(text="Invalid JSON", status=400)
        
        # Check if this is a valid Telegram update
        if 'update_id' not in update_data:
            logger.error(f"No update_id in request. Keys present: {list(update_data.keys())}")
            return web.Response(text="Not a Telegram update", status=400)
        
        # Convert to Telegram Update object
        update = Update.de_json(update_data, app.bot)
        logger.info(f"Created Update object: {update}")
        
        # Process the update
        await app.initialize()
        await app.process_update(update)
        await app.shutdown()
        
        logger.info("✅ Update processed successfully")
        logger.info("=" * 60)
        return web.Response(text="OK", status=200)
        
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}", exc_info=True)
        logger.info("=" * 60)
        return web.Response(text="Internal error", status=500)


async def health_check(request):
    """Health check endpoint for Yandex Cloud"""
    return web.Response(text="OK", status=200)


# ========== START HTTP SERVER ==========
if __name__ == "__main__":
    logger.info("Starting webhook server...")
    
    # Create aiohttp web app
    web_app = web.Application()
    web_app.router.add_post('/', webhook_handler)  # Telegram webhook
    web_app.router.add_get('/health', health_check)  # Health check
    
    # Get port from environment (Yandex uses PORT env var)
    port = int(os.getenv('PORT', 8080))
    logger.info(f"Server will listen on port {port}")
    
    # Run server
    web.run_app(web_app, host='0.0.0.0', port=port)