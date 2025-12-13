import os
import json
import datetime
import logging
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Configure logging for Yandex Cloud
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Moscow timezone
MOSCOW_TZ = datetime.timezone(datetime.timedelta(hours=3))

class SamboBot:
    def __init__(self):
        # Critical: Validate ALL required env vars at initialization
        required_vars = [
            "TELEGRAM_BOT_TOKEN", 
            "TELEGRAM_USER_ID",
            "GOOGLE_SHEET_ID",
            "GOOGLE_CREDENTIALS_JSON"
        ]
        missing = [var for var in required_vars if not os.getenv(var)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.sheet_id = os.getenv("GOOGLE_SHEET_ID")
        self.user_id = os.getenv("TELEGRAM_USER_ID")  # This is a string
        
        # Lazy initialization of sheets - connect only when needed
        self.gs_client = None
        self.spreadsheet = None
        self.activity_sheet = None
        self.consumption_sheet = None
        self.language_sheet = None

    def ensure_sheets_connection(self):
        """Initialize Google Sheets connection only when first needed"""
        if self.gs_client is not None:
            return
        
        try:
            creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
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
            logger.info("Google Sheets connection established")
        except Exception as e:
            logger.error(f"Google Sheets initialization failed: {str(e)}")
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
            self.ensure_sheets_connection()  # Connect only when needed
            
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
            logger.error(f"Error recording activity: {str(e)}")
            return False, "Error recording habit. Please try again."

    def find_or_create_activity_row(self, user_id, date_str, week_number):
        try:
            all_data = self.activity_sheet.get_all_values()
            for i, row in enumerate(all_data[1:], start=2):
                if len(row) > 1 and str(row[0]) == str(user_id) and row[1] == date_str:
                    return i
            
            # Create new row with proper structure
            new_row = [
                str(user_id), 
                date_str, 
                "",  # Prayer
                "",  # Qi Gong
                "",  # Ball
                "",  # Run/Stretch
                "",  # Strength/Stretch
                week_number,
                ""   # Notes
            ]
            self.activity_sheet.append_row(new_row)
            return len(all_data) + 1
        except Exception as e:
            logger.error(f"Error finding activity row: {str(e)}")
            return None

    def record_consumption(self, user_id, text):
        try:
            self.ensure_sheets_connection()  # Connect only when needed
            
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
                cost_col_index = headers.index(config['cost_col']) + 1  # FIXED: handlers -> headers
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
            logger.error(f"Error recording consumption: {str(e)}")
            return False, "Error recording consumption. Please try again."

    def find_or_create_consumption_row(self, user_id, date_str, week_number):
        try:
            all_data = self.consumption_sheet.get_all_values()
            for i, row in enumerate(all_data[1:], start=2):
                if len(row) > 1 and str(row[0]) == str(user_id) and row[1] == date_str:
                    return i
            
            # Create new row with proper structure
            new_row = [
                str(user_id),
                date_str,
                0,  # Coffee count
                0,  # Coffee cost
                0,  # Sugary count
                0,  # Sugary cost
                0,  # Flour count
                0,  # Flour cost
                week_number,
                ""  # Notes
            ]
            self.consumption_sheet.append_row(new_row)
            return len(all_data) + 1
        except Exception as e:
            logger.error(f"Error finding consumption row: {str(e)}")
            return None

    def record_language(self, user_id, lang_code):
        try:
            self.ensure_sheets_connection()  # Connect only when needed
            
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
            logger.error(f"Error recording language: {str(e)}")
            return False, "Error recording language. Please try again."

    def find_or_create_language_row(self, user_id, date_str, week_number):
        try:
            all_data = self.language_sheet.get_all_values()
            for i, row in enumerate(all_data[1:], start=2):
                if len(row) > 1 and str(row[0]) == str(user_id) and row[1] == date_str:
                    return i
            
            # Create new row with proper structure
            new_row = [
                str(user_id),
                date_str,
                0,  # Chinese
                0,  # Hebrew
                0,  # Tatar
                week_number,
                ""  # Notes
            ]
            self.language_sheet.append_row(new_row)
            return len(all_data) + 1
        except Exception as e:
            logger.error(f"Error finding language row: {str(e)}")
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
    user_id = str(update.effective_user.id)  # Convert to string for comparison
    
    # STRICT authorization check - compare as strings
    if user_id != bot.user_id:
        logger.warning(f"Unauthorized access attempt by user ID: {user_id}")
        await update.message.reply_text("🔒 Access denied. This bot is for authorized users only.")
        return
    
    text = update.message.text.strip().lower()
    
    # Handle language codes
    if text in ['ch', 'he', 'ta']:
        success, message = bot.record_language(user_id, text)
        await update.message.reply_text(message)
        return
    
    # Handle consumption tracking
    if text and text[0] in ['x', 'y', 'z']:
        success, message = bot.record_consumption(user_id, text)
        await update.message.reply_text(message)
        return
    
    await update.message.reply_text("❓ Unknown command. Type /help for instructions.")

async def handle_activity(update: Update, context: ContextTypes.DEFAULT_TYPE, habit_id: int):
    bot = context.bot_data["sambo_bot"]
    user_id = str(update.effective_user.id)  # Convert to string
    
    if user_id != bot.user_id:
        logger.warning(f"Unauthorized access attempt by user ID: {user_id}")
        await update.message.reply_text("🔒 Access denied. This bot is for authorized users only.")
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

# ========== YANDEX SERVERLESS CONTAINER WEBHOOK HANDLER ==========
def handler(event, context):
    """
    Yandex Cloud Serverless Container webhook handler.
    Receives Telegram updates via HTTP POST and processes them.
    """
    import asyncio
    
    # Validate request method and body
    if event.get('httpMethod', '').upper() != 'POST':
        logger.warning(f"Invalid method: {event.get('httpMethod')}")
        return {'statusCode': 405, 'body': 'Method Not Allowed'}
    
    if 'body' not in event:
        logger.warning("Received event without body")
        return {'statusCode': 400, 'body': 'Bad Request: Missing body'}
    
    try:
        # Parse Telegram update JSON
        update_data = json.loads(event['body'])
        logger.info(f"Received update: {update_data.get('update_id', 'unknown')}")
        
        async def process_update():
            bot_instance = None
            app = None
            
            try:
                # Initialize bot with lazy Google Sheets connection
                bot_instance = SamboBot()
                logger.info("Bot initialized successfully")
                
                # Build and initialize Telegram Application
                app = ApplicationBuilder().token(bot_instance.bot_token).build()
                app.bot_data["sambo_bot"] = bot_instance
                
                # Register handlers
                app.add_handler(CommandHandler("start", start))
                app.add_handler(CommandHandler("help", help_command))
                app.add_handler(CommandHandler("1", habit_1))
                app.add_handler(CommandHandler("2", habit_2))
                app.add_handler(CommandHandler("3", habit_3))
                app.add_handler(CommandHandler("4", habit_4))
                app.add_handler(CommandHandler("5", habit_5))
                app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
                
                await app.initialize()
                update = Update.de_json(update_data, app.bot)
                await app.process_update(update)
                logger.info("Update processed successfully")
                
            except Exception as e:
                logger.error(f"Processing error: {str(e)}", exc_info=True)
                # We can't send messages here since we don't have context
                raise
            finally:
                # Ensure proper cleanup even on errors
                if app:
                    await app.shutdown()
                # Explicitly close Google Sheets connections
                if bot_instance and bot_instance.gs_client:
                    try:
                        bot_instance.gs_client.session.close()
                    except:
                        pass
        
        # Run async processing with timeout protection
        asyncio.run(asyncio.wait_for(process_update(), timeout=28.0))
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'status': 'ok'})
        }
    
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {str(e)}")
        return {'statusCode': 400, 'body': 'Invalid JSON'}
    except asyncio.TimeoutError:
        logger.error("Processing timed out after 28 seconds")
        return {'statusCode': 504, 'body': 'Gateway Timeout'}
    except Exception as e:
        logger.error(f"Critical error: {str(e)}", exc_info=True)
        return {'statusCode': 500, 'body': f'Internal Server Error: {str(e)}'}