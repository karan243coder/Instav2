# 🤖 My Insta Downloader Bot

Instagram & TikTok Downloader Telegram Bot with 6 features + Admin Panel.

## ✅ Features

| Feature | Command / Usage |
|---------|----------------|
| 👤 Profile Info | `/profile username` or paste profile link |
| 📸 Latest Posts | `/posts username` |
| 🎬 Latest Reels | `/reels username` |
| 📖 Stories | `/stories username` |
| 🌟 Highlights | `/highlights username` |
| 📊 Analytics | `/analytics username` |
| 📥 Direct Download | Paste any Instagram/TikTok link |
| 📝 Logging | All user activity sent to log channel |
| 👑 Admin Panel | `/stats`, `/ban`, `/unban`, `/broadcast` |

## 🚀 Deploy on Koyeb (Free)

### 1. Get Bot Token
- Open Telegram → search **@BotFather**
- Send `/newbot` → give name → copy **Token**

### 2. Get Instagram Session ID (Important!)
- Login to Instagram in Chrome/Edge on your PC
- Press **F12** → Application → Cookies → instagram.com
- Find `sessionid` and copy its value
- This is required for Profile, Stories, Highlights, and some Posts

### 3. GitHub Upload
- Create new repo on GitHub (Public)
- Upload these 5 files: `bot.py`, `requirements.txt`, `Procfile`, `.python-version`, `README.md`

### 4. Koyeb Setup
- Go to [koyeb.com](https://koyeb.com) → Create App → GitHub source
- Select your repo
- **Important Settings:**
  - **Service Type:** `Worker` (not Web!)
  - **Build Command:** Leave **empty** (Procfile handles everything)
  - **Run Command:** Leave **empty** (Procfile handles everything)
- **Environment Variables:**
  - `BOT_TOKEN` = Your Telegram bot token
  - `IG_SESSION_ID` = Your Instagram sessionid cookie
  - `LOG_CHANNEL_ID` = Telegram channel ID (e.g., `-1001234567890`) for logs
  - `ADMIN_IDS` = Your Telegram user ID (e.g., `123456789`) — comma separated for multiple
- **Deploy!**

### 5. Create Log Channel (Optional)
- Create a Telegram channel
- Add your bot as **Admin**
- Send any message in channel, then forward to **@userinfobot** to get Channel ID
- Paste that ID in Koyeb `LOG_CHANNEL_ID`

## ⚠️ Important Limitations

**Instagram blocks free cloud servers (Koyeb, Railway, Heroku, etc.).**

- TikTok downloads usually work ✅
- Instagram public posts/reels: **Sometimes works** with fresh cookies ✅/❌
- Instagram stories/highlights: **Requires working cookies** ⚠️
- Instagram profile/analytics: **May fail if IP is blocked** ⚠️

**If you get 401/429 errors:**
- Your cookie is expired → Get fresh `sessionid` from browser
- Instagram blocked Koyeb IP → Try after few hours, or use a proxy (not free)
- Run bot on your home PC/laptop (has residential IP) → Works best!

## 🔧 Commands

- `/start` - Start bot
- `/help` - Help
- `/setcookie` - How to set Instagram cookie
- `/profile username` - Profile info
- `/posts username` - Latest posts
- `/reels username` - Latest reels
- `/stories username` - Active stories
- `/highlights username` - Highlights
- `/analytics username` - Analytics
- `/stats` - Admin stats
- `/ban user_id` - Ban user (admin only)
- `/unban user_id` - Unban user (admin only)
- `/broadcast message` - Broadcast (admin only)

## 🛠️ Tech Stack

- python-telegram-bot 20.7 (Async)
- yt-dlp (Downloads)
- requests (Profile API)
- instaloader (Fallback)
- Koyeb Free Tier (Worker)

---

Built for free deployment. If Instagram blocks, it's their anti-bot, not a bug in code!
