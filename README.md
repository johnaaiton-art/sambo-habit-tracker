# Sambo Habit Tracker Bot 🥋

A Telegram bot for tracking daily habits with automatic weekly AI-powered feedback.

## Features

### Activity Habits (Commands: /1-5)
1. Prayer with first water
2. Qi Gong routine  
3. Ball freestyling
4. 20 minute run and stretch
5. Strengthening and stretching

### Consumption Tracking
- **x** - Coffee (with optional cost)
- **y** - Sugary drinks (with optional cost)  
- **z** - Flour products (with optional cost)

Example: `xx 150` = 2 coffees, 150 rubles

### Language Learning
- **ch** - Chinese session
- **he** - Hebrew session
- **ta** - Tatar session

## Architecture

- **Bot (bot.py)**: Runs 24/7 on Yandex Cloud Serverless Container
- **Weekly Feedback**: Separate Cloud Function analyzes data weekly using DeepSeek AI
- **Storage**: Google Sheets with tabs for Activity, Consumption, and Language

## Deployment

Automatically deploys to Yandex Cloud via GitHub Actions when you push to main branch.

## Environment Variables

Set these in GitHub Secrets and Yandex Cloud:
- `TELEGRAM_BOT_TOKEN`
- `GOOGLE_SHEET_ID`
- `TELEGRAM_USER_ID`
- `DEEPSEEK_API_KEY`
- `GOOGLE_CREDENTIALS_JSON`