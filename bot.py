# bot.py
import os
import logging
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio
from sambo_core import SamboBot

# Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)

# Telegram handlers
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
    user_id = str(update.effective_user.id)
    if user_id != bot.user_id:
        await update.message.reply_text("🔒 Access denied.")
        return
    text = update.message.text.strip().lower()
    if text in ['ch', 'he', 'ta']:
        success, msg = bot.record_language(user_id, text)
        await update.message.reply_text(msg)
        return
    if text and text[0] in ['x', 'y', 'z']:
        success, msg = bot.record_consumption(user_id, text)
        await update.message.reply_text(msg)
        return
    await update.message.reply_text("❓ Unknown command. Type /help.")

async def handle_activity(update: Update, context: ContextTypes.DEFAULT_TYPE, habit_id: int):
    bot = context.bot_data["sambo_bot"]
    user_id = str(update.effective_user.id)
    if user_id != bot.user_id:
        await update.message.reply_text("🔒 Access denied.")
        return
    success, msg = bot.record_activity(user_id, habit_id)
    await update.message.reply_text(msg)

# Define command handlers
async def habit_1(u, c): await handle_activity(u, c, 1)
async def habit_2(u, c): await handle_activity(u, c, 2)
async def habit_3(u, c): await handle_activity(u, c, 3)
async def habit_4(u, c): await handle_activity(u, c, 4)
async def habit_5(u, c): await handle_activity(u, c, 5)

# Global Telegram app
_telegram_app = None

def get_telegram_app():
    global _telegram_app
    if _telegram_app is None:
        bot = SamboBot()
        _telegram_app = ApplicationBuilder().token(bot.bot_token).build()
        _telegram_app.bot_data["sambo_bot"] = bot
        _telegram_app.add_handler(CommandHandler("start", start))
        _telegram_app.add_handler(CommandHandler("help", help_command))
        _telegram_app.add_handler(CommandHandler("1", habit_1))
        _telegram_app.add_handler(CommandHandler("2", habit_2))
        _telegram_app.add_handler(CommandHandler("3", habit_3))
        _telegram_app.add_handler(CommandHandler("4", habit_4))
        _telegram_app.add_handler(CommandHandler("5", habit_5))
        _telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        asyncio.run(_telegram_app.initialize())
        logger.info("Telegram app ready")
    return _telegram_app

# Flask routes
@app.route('/webhook', methods=['POST'])
def webhook():
    if not request.is_json:
        return jsonify({'error': 'Invalid JSON'}), 400
    update_data = request.get_json()
    try:
        update = Update.de_json(update_data, get_telegram_app().bot)
        asyncio.run(get_telegram_app().process_update(update))
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'}), 200

# Entry point
if __name__ == '__main__':
    get_telegram_app()
    app.run(host='0.0.0.0', port=8080)
