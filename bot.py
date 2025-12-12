import os
import json
import datetime
import logging
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Moscow timezone
MOSCOW_TZ = datetime.timezone(datetime.timedelta(hours=3))

class SamboBot:
    def __init__(self):
        # All variables from Yandex Cloud
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.sheet_id = os.getenv("GOOGLE_SHEET_ID")
        self.user_id = os.getenv("TELEGRAM_USER_ID")
        
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
            
            # Get 3 sheets
            self.activity_sheet = self.spreadsheet.worksheet("Activity")
            self.consumption_sheet = self.spreadsheet.worksheet("Consumption") 
            self.language_sheet = self.spreadsheet.worksheet("Language")
            
            logger.info("Google Sheets initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets: {e}")
            raise
    
    def get_moscow_now(self):
        """Get current time in Moscow timezone"""
        return datetime.datetime.now(MOSCOW_TZ)
    
    def get_week_number(self, date=None):
        """Get week number for tracking (Monday as start)"""
        if date is None:
            date = self.get_moscow_now()
        days_since_monday = date.weekday()
        week_start = date - datetime.timedelta(days=days_since_monday)
        return week_start.strftime("%Y-%m-%d")
    
    # ========== ACTIVITY HABITS (1-5) ==========
    def record_activity(self, user_id, habit_id):
        """Record activity habit (1-5)"""
        try:
            now = self.get_moscow_now()
            today_str = now.strftime("%Y-%m-%d")
            week_number = self.get_week_number(now)
            
            # Mapping habits to columns
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
            
            # Find or create row for today
            row_num = self.find_or_create_activity_row(user_id, today_str, week_number)
            if not row_num:
                return False, "Failed to create activity row"
            
            # Find column index
            headers = self.activity_sheet.row_values(1)
            try:
                col_index = headers.index(column_name) + 1
            except ValueError:
                # Create column if doesn't exist
                self.activity_sheet.update_cell(1, len(headers) + 1, column_name)
                col_index = len(headers) + 1
            
            # Check if already recorded
            current_value = self.activity_sheet.cell(row_num, col_index).value
            if current_value and current_value.strip():
                return False, f"{habit_name} already recorded today"
            
            # Record with timestamp
            timestamp = now.strftime("%H:%M")
            self.activity_sheet.update_cell(row_num, col_index, f"✓ ({timestamp})")
            
            logger.info(f"Recorded habit {habit_id} for user {user_id}")
            return True, f"✓ {habit_name} recorded at {timestamp}!"
            
        except Exception as e:
            logger.error(f"Error recording activity: {e}")
            return False, "Error recording habit"
    
    def find_or_create_activity_row(self, user_id, date_str, week_number):
        """Find or create row in Activity sheet"""
        try:
            # Get all rows
            all_data = self.activity_sheet.get_all_values()
            
            # Look for existing row
            for i, row in enumerate(all_data[1:], start=2):  # Skip header
                if len(row) > 1:
                    if str(row[0]) == str(user_id) and row[1] == date_str:
                        return i
            
            # Create new row
            new_row = [str(user_id), date_str, "", "", "", "", "", week_number, ""]
            self.activity_sheet.append_row(new_row)
            return len(all_data) + 1
            
        except Exception as e:
            logger.error(f"Error finding activity row: {e}")
            return None
    
    # ========== CONSUMPTION HABITS (x, y, z) ==========
    def record_consumption(self, user_id, text):
        """Record consumption (x, y, z)"""
        try:
            now = self.get_moscow_now()
            today_str = now.strftime("%Y-%m-%d")
            week_number = self.get_week_number(now)
            
            # Parse input like "x", "xx", "xxx 150", "y 75"
            text = text.strip().lower()
            parts = text.split()
            
            if not parts or parts[0][0] not in ['x', 'y', 'z']:
                return False, "Invalid format. Use: x, xx, xx 150, y 75, z"
            
            habit_type = parts[0][0]  # First character: x, y, or z
            count = len(parts[0])  # count of letters (x=1, xx=2, xxx=3)
            
            # Parse cost if provided
            cost = 0
            if len(parts) > 1 and parts[1].replace('.', '').isdigit():
                cost = int(float(parts[1]))
            
            # Map to sheet columns
            col_map = {
                'x': {'count_col': 'Coffee (x)', 'cost_col': 'Coffee Cost', 'name': 'Coffee'},
                'y': {'count_col': 'Sugary (y)', 'cost_col': 'Sugary Cost', 'name': 'Sugary drinks'},
                'z': {'count_col': 'Flour (z)', 'cost_col': 'Flour Cost', 'name': 'Flour products'}
            }
            
            if habit_type not in col_map:
                return False, "Invalid type. Use x, y, or z"
            
            config = col_map[habit_type]
            
            # Find or create row for today
            row_num = self.find_or_create_consumption_row(user_id, today_str, week_number)
            if not row_num:
                return False, "Failed to create consumption row"
            
            # Find column indices
            headers = self.consumption_sheet.row_values(1)
            
            try:
                count_col_index = headers.index(config['count_col']) + 1
            except ValueError:
                # Create column if doesn't exist
                self.consumption_sheet.update_cell(1, len(headers) + 1, config['count_col'])
                count_col_index = len(headers) + 1
            
            try:
                cost_col_index = headers.index(config['cost_col']) + 1
            except ValueError:
                self.consumption_sheet.update_cell(1, len(headers) + 2, config['cost_col'])
                cost_col_index = len(headers) + 2
            
            # Get current values
            current_count = self.consumption_sheet.cell(row_num, count_col_index).value
            current_cost = self.consumption_sheet.cell(row_num, cost_col_index).value
            
            # Add to existing values
            new_count = int(current_count or 0) + count
            new_cost = int(current_cost or 0) + cost
            
            # Update cells
            self.consumption_sheet.update_cell(row_num, count_col_index, new_count)
            self.consumption_sheet.update_cell(row_num, cost_col_index, new_cost)
            
            logger.info(f"Recorded consumption {habit_type} x{count} for user {user_id}")
            
            cost_text = f" ({cost} rub)" if cost > 0 else ""
            return True, f"✓ {config['name']} x{count} recorded{cost_text}! Total today: {new_count}"
            
        except Exception as e:
            logger.error(f"Error recording consumption: {e}")
            return False, "Error recording consumption"
    
    def find_or_create_consumption_row(self, user_id, date_str, week_number):
        """Find or create row in Consumption sheet"""
        try:
            all_data = self.consumption_sheet.get_all_values()
            
            # Look for existing row
            for i, row in enumerate(all_data[1:], start=2):
                if len(row) > 1:
                    if str(row[0]) == str(user_id) and row[1] == date_str:
                        return i
            
            # Create new row
            new_row = [str(user_id), date_str, 0, 0, 0, 0, 0, 0, week_number, ""]
            self.consumption_sheet.append_row(new_row)
            return len(all_data) + 1
            
        except Exception as e:
            logger.error(f"Error finding consumption row: {e}")
            return None
    
    # ========== LANGUAGE LEARNING (ch, he, ta) ==========
    def record_language(self, user_id, lang_code):
        """Record language learning session"""
        try:
            now = self.get_moscow_now()
            today_str = now.strftime("%Y-%m-%d")
            week_number = self.get_week_number(now)
            
            # Map language codes to columns
            lang_map = {
                'ch': ('Chinese (ch)', 'Chinese'),
                'he': ('Hebrew (he)', 'Hebrew'),
                'ta': ('Tatar (ta)', 'Tatar')
            }
            
            if lang_code not in lang_map:
                return False, "Invalid language code. Use: ch, he, ta"
            
            column_name, lang_name = lang_map[lang_code]
            
            # Find or create row for today
            row_num = self.find_or_create_language_row(user_id, today_str, week_number)
            if not row_num:
                return False, "Failed to create language row"
            
            # Find column index
            headers = self.language_sheet.row_values(1)
            try:
                col_index = headers.index(column_name) + 1
            except ValueError:
                self.language_sheet.update_cell(1, len(headers) + 1, column_name)
                col_index = len(headers) + 1
            
            # Get current value
            current_value = self.language_sheet.cell(row_num, col_index).value
            current_sessions = int(current_value or 0)
            
            # Increment sessions
            new_sessions = current_sessions + 1
            timestamp = now.strftime("%H:%M")
            self.language_sheet.update_cell(row_num, col_index, new_sessions)
            
            logger.info(f"Recorded language {lang_code} for user {user_id}")
            return True, f"✓ {lang_name} session #{new_sessions} recorded at {timestamp}!"
            
        except Exception as e:
            logger.error(f"Error recording language: {e}")
            return False, "Error recording language"
    
    def find_or_create_language_row(self, user_id, date_str, week_number):
        """Find or create row in Language sheet"""
        try:
            all_data = self.language_sheet.get_all_values()
            
            # Look for existing row
            for i, row in enumerate(all_data[1:], start=2):
                if len(row) > 1:
                    if str(row[0]) == str(user_id) and row[1] == date_str:
                        return i
            
            # Create new row
            new_row = [str(user_id), date_str, 0, 0, 0, week_number, ""]
            self.language_sheet.append_row(new_row)
            return len(all_data) + 1
            
        except Exception as e:
            logger.error(f"Error finding language row: {e}")
            return None

# ========== TELEGRAM HANDLERS ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
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
    """Help command"""
    await start(update, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages for consumption and language"""
    bot = context.bot_data['sambo_bot']
    user_id = str(update.effective_user.id)
    text = update.message.text.strip().lower()
    
    # Check if authorized user
    if user_id != bot.user_id:
        await update.message.reply_text("Sorry, this bot is for authorized users only.")
        return
    
    # Language codes
    if text in ['ch', 'he', 'ta']:
        success, message = bot.record_language(user_id, text)
        await update.message.reply_text(message)
        return
    
    # Consumption patterns (x, y, z)
    if text[0] in ['x', 'y', 'z']:
        success, message = bot.record_consumption(user_id, text)
        await update.message.reply_text(message)
        return
    
    await update.message.reply_text("Unknown command. Type /help for instructions.")

async def handle_activity(update: Update, context: ContextTypes.DEFAULT_TYPE, habit_id: int):
    """Handle activity habit commands (1-5)"""
    bot = context.bot_data['sambo_bot']
    user_id = str(update.effective_user.id)
    
    # Check if authorized user
    if user_id != bot.user_id:
        await update.message.reply_text("Sorry, this bot is for authorized users only.")
        return
    
    success, message = bot.record_activity(user_id, habit_id)
    await update.message.reply_text(message)

# Individual command handlers
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

def main():
    """Main function to run the bot"""
    try:
        # Initialize bot
        bot = SamboBot()
        logger.info("SamboBot initialized successfully")
        
        # Create application
        application = Application.builder().token(bot.bot_token).build()
        
        # Store bot instance in bot_data for access in handlers
        application.bot_data['sambo_bot'] = bot
        
        # Add command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("1", habit_1))
        application.add_handler(CommandHandler("2", habit_2))
        application.add_handler(CommandHandler("3", habit_3))
        application.add_handler(CommandHandler("4", habit_4))
        application.add_handler(CommandHandler("5", habit_5))
        
        # Add message handler for text messages
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        logger.info("Bot is starting...")
        
        # Start the bot
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise

if __name__ == '__main__':
    main()