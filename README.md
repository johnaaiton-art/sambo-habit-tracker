# Sambo Bot - Motivational Image Feature

## Overview
This upgrade adds motivational images to your consumption tracking. When you record coffee/sugar/flour consumption, the bot will:
1. Send a harsh motivational image (obese person with the item)
2. Send the text insult in 3 languages (English, Chinese, Spanish)

## What Changed

### New Files
- `generate_images.py` - Script to generate 42 images using Stable Diffusion
- `images/` folder - Contains 42 JPEG images (21 coffee + 21 sugar/flour)
- `DEPLOYMENT_GUIDE.ps1` - Complete PowerShell instructions
- `README_IMAGES.md` - This file

### Updated Files
- `bot.py` - Now sends images with messages via Telegram
- `messages.json` - Added "picture" field to each entry

## Quick Start

### 1. Generate Images (Windows Desktop)
```powershell
cd "C:\Users\John\YandexDisk\Python\innovative vocab\AI magic\yandex\sambo_bot"
python generate_images.py
```

### 2. Organize & Deploy
```powershell
# Move images
mkdir images -Force
Move-Item "generated_images\*.jpg" "images\" -Force

# Replace messages.json
Remove-Item messages.json
Rename-Item messages_with_images.json messages.json

# Push to GitHub
git add .
git commit -m "Add motivational images"
git push origin main
```

### 3. Update VM
```powershell
# SSH into VM
ssh yc-user@84.252.141.140

# Pull updates
cd ~/sambo-habit-tracker
git pull origin main

# Restart bot
sudo systemctl restart sambo-bot.service
sudo systemctl status sambo-bot.service
exit
```

## File Structure

```
sambo_bot/
├── bot.py                      # Updated with image sending
├── messages.json               # Updated with picture fields
├── generate_images.py          # Image generator script
├── images/                     # 42 motivational images
│   ├── coffee_01.jpg          # ID 1 coffee image
│   ├── coffee_02.jpg          # ID 2 coffee image
│   ├── ...
│   ├── coffee_21.jpg          # ID 21 coffee image
│   ├── sugar_flour_01.jpg     # ID 1 sugar/flour image
│   ├── sugar_flour_02.jpg     # ID 2 sugar/flour image
│   ├── ...
│   └── sugar_flour_21.jpg     # ID 21 sugar/flour image
├── DEPLOYMENT_GUIDE.ps1       # Full instructions
└── README_IMAGES.md           # This file
```

## How It Works

### Image Generation
- Uses Stable Diffusion (RealisticVision v6) on your desktop GPU
- Prompts are simple and precise (Stable Diffusion requirement)
- Each prompt describes: obese person + health problem + item
- Images are 832x512 pixels, JPEG format, ~200-500KB each

### Bot Behavior
1. User sends: `x` or `xx` or `xxx`
2. Bot records in Google Sheets
3. Bot selects random message from category
4. Bot sends image first (if available)
5. Bot sends text message with count and 3-language insult

### Example Telegram Conversation
```
You: x

Bot: [Image: obese tired man with coffee cup]

Bot: ✓ Coffee x1 recorded. Total today: 1

☕💀 You're letting yourself down. How much longer are you gonna keep on the juice, you junkie?
☕💀 你在让自己失望。你这个瘾君子还要喝多久？
☕💀 Te estás decepcionando a ti mismo. ¿Cuánto tiempo más vas a seguir con el jugo, drogadicto?
```

## Image Details

### Coffee Images (21 total)
Each depicts obese person with coffee showing different health problems:
- Exhaustion, dark eye bags, pale skin
- Heart problems, chest pain
- Kidney pain, liver damage
- Anxiety, insomnia, trembling
- High blood pressure, stroke risk
- Bone problems, osteoporosis
- Brain chemistry damage
- Immune system compromise
- Premature aging

### Sugar/Flour Images (21 total)
Each depicts obese person eating sweets/bread showing:
- Joint pain, knee problems
- Diabetes, insulin injections
- Obesity, cannot see feet
- Gluttony, pregnant-looking belly
- Heart drowning in fat
- Scale showing weight gain
- Sleep apnea
- Metabolic syndrome
- Brain fog, Alzheimer's risk
- Inflammation
- Rotten teeth
- Addiction, slave to cravings
- Liver problems
- Early death imagery
- Premature aging

## Technical Details

### Stable Diffusion Settings
- Model: RealisticVision v6.0 B1 (HyperVAE)
- Steps: 50
- Guidance: 7.5
- Size: 832x512
- Seed: 42 (fixed for consistency)
- Format: JPEG quality 90

### Prompt Structure
Good: "Obese tired man with coffee cup. Dark eye bags. Pale skin."
Bad: "An obese tired man holding a coffee cup with dark eye bags"

Stable Diffusion works best with:
- Short sentences
- Simple grammar
- No participles
- Clear priority/focus

### Telegram Integration
- Images sent via `reply_photo()`
- Bot looks for images in `images/` folder
- Falls back to same directory if needed
- Text message sent after image
- Error handling if image not found

## Storage & Deployment

### Windows Desktop
- Images generated locally using GPU
- Stored in `images/` folder
- Total size: ~15-20MB (42 images)

### GitHub Repository
- Images committed to repo
- Well within 100MB limit
- Private repo (safe for personal images)

### Yandex VM
- Images pulled from GitHub
- Stored in `~/sambo-habit-tracker/images/`
- No external hosting needed
- No additional costs

## Troubleshooting

### Images not showing in Telegram
1. Check images exist on VM:
   ```bash
   ls -la ~/sambo-habit-tracker/images/
   ```
2. Verify 42 .jpg files present
3. Check bot logs:
   ```bash
   sudo journalctl -u sambo-bot.service -n 50
   ```
4. Restart bot:
   ```bash
   sudo systemctl restart sambo-bot.service
   ```

### Image generation fails
1. Check GPU availability
2. Verify model path is correct
3. Check CUDA/PyTorch installation
4. Review error messages in console

### Bot crashes after update
1. Check Python dependencies installed
2. Verify messages.json format correct
3. Check file permissions on images/
4. Review bot logs for errors

## Future Improvements

### Possible Enhancements
- Add more images (different variations)
- Create separate sugar vs flour categories
- Add language-specific images
- Generate images on-demand (requires GPU on VM)
- Add image caching for faster loading

### Regenerating Images
If you want to regenerate with different prompts:
1. Edit `COFFEE_PROMPTS` and `SUGAR_FLOUR_PROMPTS` in `generate_images.py`
2. Run `python generate_images.py`
3. Follow deployment steps again

## Credits
- Bot: Sambo Habit Tracker
- Model: RealisticVision v6.0 B1
- Image Generation: Stable Diffusion
- Platform: Telegram Bot API
- Hosting: Yandex Cloud VM

## Support
For issues or questions:
1. Check DEPLOYMENT_GUIDE.ps1 for detailed steps
2. Review bot logs on VM
3. Test image files locally before deploying
4. Verify GitHub push succeeded

---

**Note**: Images are intentionally harsh to match the motivational insult tone. They show obese individuals with health problems to create strong motivation for behavior change.