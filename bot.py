#!/usr/bin/env python3
"""
My Insta Downloader Bot - Full Featured + Log Media Forwarding
Instagram (Photos, Videos, Reels, Stories, Highlights) & TikTok Downloader
Deploy: Koyeb (Free Tier)
"""

import os
import sys
import re
import json
import logging
import tempfile
import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime
from typing import Optional, Tuple, List, Dict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
import yt_dlp
import requests

# ==================== CONFIG ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = [x.strip() for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID", "").strip()
IG_SESSION_ID = os.getenv("IG_SESSION_ID", "").strip()
BAN_LIST: set = set()

if not BOT_TOKEN:
    logging.error("❌ BOT_TOKEN not set! Exiting.")
    sys.exit(1)

# ==================== LOGGING ====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== THREAD POOL ====================
executor = ThreadPoolExecutor(max_workers=4)

# ==================== COOKIES ====================
COOKIE_FILE = "/tmp/ig_cookies.txt"

def init_cookies() -> bool:
    if not IG_SESSION_ID:
        return False
    try:
        with open(COOKIE_FILE, "w") as f:
            f.write(f"""# Netscape HTTP Cookie File
.instagram.com\tTRUE\t/\tTRUE\t0\tcsrftoken\t{IG_SESSION_ID[:16]}
.instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\t{IG_SESSION_ID}
""")
        logger.info("✅ Instagram cookies initialized")
        return True
    except Exception as e:
        logger.error(f"Cookie init error: {e}")
        return False

def cookies_ready() -> bool:
    return os.path.exists(COOKIE_FILE) and os.path.getsize(COOKIE_FILE) > 0

# ==================== HEALTH SERVER ====================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - Bot Running")
    def log_message(self, format, *args):
        pass

def start_health_server():
    try:
        srv = HTTPServer(("0.0.0.0", 8080), HealthHandler)
        Thread(target=srv.serve_forever, daemon=True).start()
        logger.info("🩺 Health server on 0.0.0.0:8080")
    except Exception as e:
        logger.warning(f"Health server failed: {e}")

# ==================== ADMIN / LOG HELPERS ====================
def is_admin(user_id: int) -> bool:
    return str(user_id) in ADMIN_IDS

def is_banned(user_id: int) -> bool:
    return str(user_id) in BAN_LIST

async def send_log_text(context: ContextTypes.DEFAULT_TYPE, text: str):
    if not LOG_CHANNEL_ID:
        return
    try:
        await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Log text error: {e}")

async def send_log_media(context: ContextTypes.DEFAULT_TYPE, filepath: str, caption: str):
    if not LOG_CHANNEL_ID or not os.path.exists(filepath):
        return
    ext = filepath.lower().split(".")[-1] if "." in filepath else ""
    is_video = ext in ("mp4", "mov", "mkv", "webm", "avi")
    try:
        if is_video:
            with open(filepath, "rb") as f:
                await context.bot.send_video(chat_id=LOG_CHANNEL_ID, video=f, caption=caption[:1024], supports_streaming=True)
        elif ext in ("jpg", "jpeg", "png", "webp", "gif"):
            with open(filepath, "rb") as f:
                await context.bot.send_photo(chat_id=LOG_CHANNEL_ID, photo=f, caption=caption[:1024])
        else:
            with open(filepath, "rb") as f:
                await context.bot.send_document(chat_id=LOG_CHANNEL_ID, document=f, caption=caption[:1024])
    except Exception as e:
        logger.warning(f"Log media error: {e}")
        try:
            with open(filepath, "rb") as f:
                await context.bot.send_document(chat_id=LOG_CHANNEL_ID, document=f, caption=f"📎 Log\n{caption[:900]}")
        except Exception as e2:
            logger.error(f"Log fallback failed: {e2}")

async def log_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.effective_message.text if update.effective_message else "[no text]"
    msg = (
        f"📥 <b>New Request</b>\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"👤 {user.first_name} (@{user.username or 'N/A'})\n"
        f"🆔 <code>{user.id}</code>\n"
        f"💬 <code>{text[:500]}</code>"
    )
    await send_log_text(context, msg)

async def log_download_success(update: Update, context: ContextTypes.DEFAULT_TYPE, original_url: str, filepath: str, info: dict, is_tiktok: bool):
    if not LOG_CHANNEL_ID:
        return
    user = update.effective_user
    ext = filepath.lower().split(".")[-1] if "." in filepath else ""
    is_video = ext in ("mp4", "mov", "mkv", "webm", "avi")
    platform = "🎵 TikTok" if is_tiktok else "📸 Instagram"
    title = (info.get("title", "") or "No title")[:100]
    uploader = (info.get("uploader", "") or "Unknown")[:50]
    size_mb = os.path.getsize(filepath) / (1024 * 1024) if os.path.exists(filepath) else 0
    caption = (
        f"✅ <b>Download Success</b>\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"{platform}\n"
        f"🔗 <b>Original:</b>\n<code>{original_url}</code>\n\n"
        f"📝 {title}\n"
        f"👤 {uploader}\n"
        f"📦 {size_mb:.1f} MB\n\n"
        f"👤 By: {user.first_name} (@{user.username or 'N/A'})\n"
        f"🆔 <code>{user.id}</code>"
    )
    await send_log_media(context, filepath, caption)

async def log_download_failure(update: Update, context: ContextTypes.DEFAULT_TYPE, original_url: str, error: str, is_tiktok: bool):
    if not LOG_CHANNEL_ID:
        return
    user = update.effective_user
    platform = "🎵 TikTok" if is_tiktok else "📸 Instagram"
    msg = (
        f"❌ <b>Download Failed</b>\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"{platform}\n"
        f"🔗 <code>{original_url}</code>\n\n"
        f"⚠️ <code>{error[:1000]}</code>\n\n"
        f"👤 {user.first_name} (@{user.username or 'N/A'})\n"
        f"🆔 <code>{user.id}</code>"
    )
    await send_log_text(context, msg)

# ==================== YT-DLP HELPERS (FIXED FOR PHOTOS) ====================
def get_media_type(filepath: str) -> str:
    ext = filepath.lower().split(".")[-1] if "." in filepath else ""
    if ext in ("mp4", "mov", "mkv", "webm", "avi", "m4v"):
        return "video"
    if ext in ("jpg", "jpeg", "png", "webp", "gif", "bmp"):
        return "photo"
    return "document"

def run_yt_dlp_download(url: str, cookiefile: Optional[str] = None) -> Tuple[Optional[dict], List[str], Optional[str]]:
    """Download media. Returns (info, list_of_files, error)"""
    out_dir = tempfile.mkdtemp()
    opts = {
        "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "format": "best/bestvideo+bestaudio",
        "max_filesize": 50 * 1024 * 1024,
        "merge_output_format": "mp4",
        "playlist_items": "1-10",
    }
    if cookiefile and os.path.exists(cookiefile):
        opts["cookiefile"] = cookiefile
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            media_files = []
            if os.path.exists(out_dir):
                for f in sorted(os.listdir(out_dir)):
                    fpath = os.path.join(out_dir, f)
                    if not os.path.isfile(fpath):
                        continue
                    if f.endswith((".part", ".json", ".description", ".ytdl", ".temp")):
                        continue
                    if os.path.getsize(fpath) > 1024:
                        mtype = get_media_type(fpath)
                        if mtype in ("video", "photo", "document"):
                            media_files.append(fpath)
            return info, media_files, None
    except Exception as e:
        return None, [], str(e)

def run_yt_dlp_info(url: str, cookiefile: Optional[str] = None) -> Tuple[Optional[dict], Optional[str]]:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    if cookiefile and os.path.exists(cookiefile):
        opts["cookiefile"] = cookiefile
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info, None
    except Exception as e:
        return None, str(e)

async def safe_send_media(update: Update, filepath: str, caption: str) -> bool:
    if not os.path.exists(filepath):
        return False
    try:
        mtype = get_media_type(filepath)
        if mtype == "video":
            with open(filepath, "rb") as f:
                await update.message.reply_video(video=f, caption=caption[:1024], supports_streaming=True)
        elif mtype == "photo":
            with open(filepath, "rb") as f:
                await update.message.reply_photo(photo=f, caption=caption[:1024])
        else:
            with open(filepath, "rb") as f:
                await update.message.reply_document(document=f, caption=caption[:1024])
        return True
    except Exception as e:
        logger.error(f"Send error: {e}")
        try:
            with open(filepath, "rb") as f:
                await update.message.reply_document(document=f, caption=caption[:1024])
            return True
        except Exception as e2:
            logger.error(f"Doc fallback error: {e2}")
            return False

# ==================== INSTAGRAM API HELPERS (FIXED) ====================
def instagram_headers() -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "X-IG-App-ID": "936619743392459",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.instagram.com/",
    }

def get_instagram_cookies() -> dict:
    """Return cookies dict for requests."""
    cookies = {}
    if IG_SESSION_ID:
        cookies["sessionid"] = IG_SESSION_ID
    if cookies_ready():
        try:
            with open(COOKIE_FILE) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 7 and parts[5] == "sessionid":
                        cookies["sessionid"] = parts[6]
        except:
            pass
    return cookies

def fetch_profile_info(username: str) -> Optional[dict]:
    """Fetch user profile via Instagram web API."""
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
    headers = instagram_headers()
    cookies = get_instagram_cookies()
    try:
        resp = requests.get(url, headers=headers, timeout=15, cookies=cookies)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", {}).get("user", {})
        elif resp.status_code == 401:
            logger.warning(f"Profile API 401 for {username} - cookie expired or blocked")
        elif resp.status_code == 429:
            logger.warning(f"Profile API 429 for {username} - rate limited")
    except Exception as e:
        logger.warning(f"Profile fetch failed: {e}")
    return None

def extract_posts_from_profile(user_data: dict) -> List[dict]:
    """Extract posts from profile data. Returns list of {url, shortcode, is_video, caption}."""
    posts = []
    edges = user_data.get("edge_owner_to_timeline_media", {}).get("edges", [])
    for edge in edges:
        node = edge.get("node", {})
        shortcode = node.get("shortcode")
        if not shortcode:
            continue
        posts.append({
            "url": f"https://www.instagram.com/p/{shortcode}/",
            "shortcode": shortcode,
            "is_video": node.get("is_video", False),
            "caption": (node.get("edge_media_to_caption", {}).get("edges", [{}])[0].get("node", {}).get("text", "") or "")[:100],
            "likes": node.get("edge_liked_by", {}).get("count", 0),
            "comments": node.get("edge_media_to_comment", {}).get("count", 0),
        })
    return posts

def extract_reels_from_profile(user_data: dict) -> List[dict]:
    """Extract reels from profile data (filter by is_video=True)."""
    posts = extract_posts_from_profile(user_data)
    return [p for p in posts if p["is_video"]]

async def download_post_by_shortcode(update: Update, context: ContextTypes.DEFAULT_TYPE, shortcode: str, is_reel: bool = False):
    """Download a single post by shortcode. Returns success bool."""
    url = f"https://www.instagram.com/p/{shortcode}/"
    if is_reel:
        url = f"https://www.instagram.com/reel/{shortcode}/"
    
    info, files, err = await asyncio.get_event_loop().run_in_executor(
        executor, run_yt_dlp_download, url, COOKIE_FILE
    )
    
    if files:
        title = (info.get("title", "") or "")[:200] if info else ""
        uploader = (info.get("uploader", "") or "")[:50] if info else ""
        caption = "✅ Downloaded!"
        if title:
            caption += f"\n📝 {title}"
        if uploader:
            caption += f"\n👤 {uploader}"
        
        sent = 0
        for f in files:
            if await safe_send_media(update, f, caption if sent == 0 else ""):
                sent += 1
        
        if sent > 0 and files:
            await log_download_success(update, context, url, files[0], info or {}, is_tiktok=False)
            return True
    
    return False

# ==================== COMMANDS ====================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        return
    text = (
        f"👋 <b>Welcome {user.first_name}!</b>\n\n"
        f"📥 <b>My Insta Downloader Bot</b>\n\n"
        f"<b>Download kaise karein:</b>\n"
        f"1. Instagram/TikTok par post/reel/story kholein\n"
        f"2. Share button → 'Copy Link'\n"
        f"3. Yahan paste karo!\n\n"
        f"✅ <b>Supported:</b>\n"
        f"• Instagram Photos, Videos, Reels, Stories, Highlights\n"
        f"• TikTok Videos (no watermark!)\n\n"
        f"Ya menu se choose karo 👇"
    )
    keyboard = [
        [InlineKeyboardButton("📥 Download Guide", callback_data="help")],
        [InlineKeyboardButton("👤 Profile", callback_data="menu_profile"),
         InlineKeyboardButton("📸 Posts", callback_data="menu_posts")],
        [InlineKeyboardButton("🎬 Reels", callback_data="menu_reels"),
         InlineKeyboardButton("📖 Stories", callback_data="menu_stories")],
        [InlineKeyboardButton("🌟 Highlights", callback_data="menu_highlights"),
         InlineKeyboardButton("📊 Analytics", callback_data="menu_analytics")],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    await send_log_text(context,
        f"🆕 <b>New User</b>\n"
        f"👤 {user.first_name} (@{user.username or 'N/A'})\n"
        f"🆔 <code>{user.id}</code>\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "<b>🤖 My Insta Downloader - Help</b>\n\n"
        "<b>Direct Download:</b>\n"
        "Just paste any Instagram or TikTok link!\n\n"
        "<b>Instagram Link Types:</b>\n"
        "• Post (photo/video): https://instagram.com/p/ABC123/\n"
        "• Reel: https://instagram.com/reel/ABC123/\n"
        "• Story: https://instagram.com/stories/username/123456/\n"
        "• Profile: https://instagram.com/username/\n\n"
        "<b>Commands:</b>\n"
        "/start - Start bot\n"
        "/help - This message\n"
        "/setcookie - How to set Instagram cookie\n"
        "/profile username - Profile info\n"
        "/posts username - Latest 9 posts\n"
        "/reels username - Latest 6 reels\n"
        "/stories username - Active stories\n"
        "/highlights username - Story highlights\n"
        "/analytics username - Profile analytics\n\n"
        "<b>Admin Only:</b>\n"
        "/stats - Bot statistics\n"
        "/broadcast message - Broadcast to all users\n"
        "/ban user_id - Ban a user\n"
        "/unban user_id - Unban a user\n\n"
        "<i>⚠️ Note: Instagram sometimes blocks cloud servers.\n"
        "If downloads fail, set cookie via /setcookie or Koyeb env IG_SESSION_ID.</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def setcookie_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🔑 <b>How to get Instagram Session ID:</b>\n\n"
        "1. Login to Instagram in Chrome/Edge on your PC\n"
        "2. Press F12 → Application → Cookies → instagram.com\n"
        "3. Find 'sessionid' and copy its value\n"
        "4. In Koyeb Dashboard:\n"
        "   • App → Settings → Environment Variables\n"
        "   • Add: Key = <code>IG_SESSION_ID</code>\n"
        "   • Value = your sessionid value\n"
        "5. Redeploy / Restart the app\n\n"
        "⚠️ Without this, Instagram stories, private posts, and profile data won't work!"
    )
    await update.message.reply_text(text, parse_mode="HTML")

def profile_keyboard(username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Profile Info", callback_data=f"profile:{username}"),
         InlineKeyboardButton("📸 Latest Posts", callback_data=f"posts:{username}")],
        [InlineKeyboardButton("🎬 Latest Reels", callback_data=f"reels:{username}"),
         InlineKeyboardButton("📖 Stories", callback_data=f"stories:{username}")],
        [InlineKeyboardButton("🌟 Highlights", callback_data=f"highlights:{username}"),
         InlineKeyboardButton("📊 Analytics", callback_data=f"analytics:{username}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu_main")],
    ])

async def show_profile_menu(update: Update, username: str, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👤 @{username} ke liye options choose karo:",
        reply_markup=profile_keyboard(username)
    )

async def profile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /profile username\nExample: /profile virat.kohli")
        return
    username = context.args[0].strip().replace("@", "")
    await show_profile_menu(update, username, context)

async def posts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /posts username")
        return
    username = context.args[0].strip().replace("@", "")
    await process_posts(update, context, username, is_callback=False)

async def reels_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /reels username")
        return
    username = context.args[0].strip().replace("@", "")
    await process_reels(update, context, username, is_callback=False)

async def stories_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /stories username")
        return
    username = context.args[0].strip().replace("@", "")
    await process_stories(update, context, username, is_callback=False)

async def highlights_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /highlights username")
        return
    username = context.args[0].strip().replace("@", "")
    await process_highlights(update, context, username, is_callback=False)

async def analytics_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /analytics username")
        return
    username = context.args[0].strip().replace("@", "")
    await process_analytics(update, context, username, is_callback=False)

# ==================== FEATURE PROCESSORS (FIXED) ====================
async def process_profile(update: Update, context: ContextTypes.DEFAULT_TYPE, username: str, is_callback: bool):
    msg = await (update.callback_query.edit_message_text if is_callback else update.message.reply_text)(
        f"⏳ @{username} ka profile info fetch ho raha hai..."
    )
    user_data = fetch_profile_info(username)
    if user_data:
        bio = user_data.get("biography", "N/A")
        full_name = user_data.get("full_name", username)
        followers = user_data.get("edge_followed_by", {}).get("count", "N/A")
        following = user_data.get("edge_follow", {}).get("count", "N/A")
        posts = user_data.get("edge_owner_to_timeline_media", {}).get("count", "N/A")
        is_private = user_data.get("is_private", False)
        is_verified = user_data.get("is_verified", False)
        pic_url = user_data.get("profile_pic_url_hd") or user_data.get("profile_pic_url")
        text = (
            f"👤 <b>{full_name}</b> {'✅' if is_verified else ''}\n"
            f"<b>@{username}</b> {'🔒 Private' if is_private else '🌐 Public'}\n\n"
            f"📝 <b>Bio:</b> {bio[:300] if bio else 'N/A'}\n\n"
            f"👥 <b>Followers:</b> {followers}\n"
            f"➡️ <b>Following:</b> {following}\n"
            f"📸 <b>Posts:</b> {posts}"
        )
        if pic_url:
            try:
                await update.effective_chat.send_photo(photo=pic_url, caption=text, parse_mode="HTML")
                if is_callback:
                    try: await msg.delete()
                    except: pass
                return
            except:
                pass
        if is_callback:
            await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=profile_keyboard(username))
        else:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=profile_keyboard(username))
    else:
        err_text = f"❌ @{username} ka profile info nahi mil paya.\nTry: /setcookie"
        if is_callback:
            await update.callback_query.edit_message_text(err_text, reply_markup=profile_keyboard(username))
        else:
            await update.message.reply_text(err_text, reply_markup=profile_keyboard(username))

async def process_posts(update: Update, context: ContextTypes.DEFAULT_TYPE, username: str, is_callback: bool):
    msg = await (update.callback_query.edit_message_text if is_callback else update.message.reply_text)(
        f"⏳ @{username} ki latest posts fetch ho rahi hain..."
    )
    
    # FIX: Use Instagram web API instead of yt-dlp for user profile posts
    user_data = fetch_profile_info(username)
    if not user_data:
        err_text = (
            f"❌ @{username} ki posts nahi mil payi.\n\n"
            f"Reasons:\n"
            f"• Instagram ne server IP block kiya ho\n"
            f"• Cookie expire ho gayi ho\n"
            f"• Username galat ho\n\n"
            f"💡 Try: /setcookie\n"
            f"💡 Direct post link paste karo for better results!"
        )
        if is_callback:
            await update.callback_query.edit_message_text(err_text, reply_markup=profile_keyboard(username))
        else:
            await update.message.reply_text(err_text, reply_markup=profile_keyboard(username))
        return
    
    posts = extract_posts_from_profile(user_data)
    if not posts:
        err_text = f"❌ @{username} ki koi posts nahi mili ya account private hai.\n\n/setcookie try karo!"
        if is_callback:
            await update.callback_query.edit_message_text(err_text, reply_markup=profile_keyboard(username))
        else:
            await update.message.reply_text(err_text, reply_markup=profile_keyboard(username))
        return
    
    # Try to download the first post automatically, show links for rest
    text = f"📸 <b>@{username}</b> ki Latest Posts:\n\n"
    for i, post in enumerate(posts[:9], 1):
        media_type = "🎬 Video" if post["is_video"] else "🖼️ Photo"
        text += f"{i}. {media_type} | ❤️ {post['likes']} | 💬 {post['comments']}\n"
        if post["caption"]:
            text += f"   <i>{post['caption'][:80]}...</i>\n"
        text += f"   🔗 <code>{post['url']}</code>\n\n"
    
    text += "💡 <b>Direct download ke liye koi bhi link copy karke bot me paste karo!</b>"
    
    if is_callback:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=profile_keyboard(username), disable_web_page_preview=True)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=profile_keyboard(username), disable_web_page_preview=True)
    
    # Try downloading first 2 posts automatically in background
    if posts:
        await (update.callback_query.edit_message_text if is_callback else update.message.reply_text)(
            "⏳ Pehli 2 posts auto-download ho rahi hain..."
        )
        for post in posts[:2]:
            try:
                await download_post_by_shortcode(update, context, post["shortcode"], is_reel=False)
            except Exception as e:
                logger.warning(f"Auto-download post failed: {e}")

async def process_reels(update: Update, context: ContextTypes.DEFAULT_TYPE, username: str, is_callback: bool):
    msg = await (update.callback_query.edit_message_text if is_callback else update.message.reply_text)(
        f"⏳ @{username} ki latest reels fetch ho rahi hain..."
    )
    
    # FIX: Use Instagram web API instead of yt-dlp
    user_data = fetch_profile_info(username)
    if not user_data:
        err_text = (
            f"❌ @{username} ki reels nahi mil payi.\n\n"
            f"💡 Try: /setcookie\n"
            f"💡 Direct reel link paste karo for better results!"
        )
        if is_callback:
            await update.callback_query.edit_message_text(err_text, reply_markup=profile_keyboard(username))
        else:
            await update.message.reply_text(err_text, reply_markup=profile_keyboard(username))
        return
    
    reels = extract_reels_from_profile(user_data)
    if not reels:
        err_text = f"❌ @{username} ki koi reels nahi mili.\n\n/setcookie try karo!"
        if is_callback:
            await update.callback_query.edit_message_text(err_text, reply_markup=profile_keyboard(username))
        else:
            await update.message.reply_text(err_text, reply_markup=profile_keyboard(username))
        return
    
    text = f"🎬 <b>@{username}</b> ki Latest Reels:\n\n"
    for i, reel in enumerate(reels[:6], 1):
        text += f"{i}. ❤️ {reel['likes']} | 💬 {reel['comments']}\n"
        if reel["caption"]:
            text += f"   <i>{reel['caption'][:80]}...</i>\n"
        text += f"   🔗 <code>{reel['url']}</code>\n\n"
    
    text += "💡 <b>Direct download ke liye koi bhi link copy karke bot me paste karo!</b>"
    
    if is_callback:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=profile_keyboard(username), disable_web_page_preview=True)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=profile_keyboard(username), disable_web_page_preview=True)
    
    # Auto-download first 2 reels
    if reels:
        for reel in reels[:2]:
            try:
                await download_post_by_shortcode(update, context, reel["shortcode"], is_reel=True)
            except Exception as e:
                logger.warning(f"Auto-download reel failed: {e}")

async def process_stories(update: Update, context: ContextTypes.DEFAULT_TYPE, username: str, is_callback: bool):
    msg = await (update.callback_query.edit_message_text if is_callback else update.message.reply_text)(
        f"⏳ @{username} ki stories fetch ho rahi hain..."
    )
    if not cookies_ready():
        err_text = "❌ Stories ke liye Instagram login cookie chahiye!\n\n/setcookie se setup karo."
        if is_callback:
            await update.callback_query.edit_message_text(err_text, reply_markup=profile_keyboard(username))
        else:
            await update.message.reply_text(err_text, reply_markup=profile_keyboard(username))
        return
    
    # Use yt-dlp for stories (no direct API for this easily)
    url = f"https://instagram.com/stories/{username}"
    info, files, err = await asyncio.get_event_loop().run_in_executor(
        executor, run_yt_dlp_download, url, COOKIE_FILE
    )
    
    if files:
        text = f"📖 <b>@{username}</b> ki Stories:\n\n"
        caption = f"✅ Story Downloaded!\n👤 @{username}"
        sent = 0
        for f in files:
            if await safe_send_media(update, f, caption if sent == 0 else ""):
                sent += 1
        if sent > 0 and files:
            await log_download_success(update, context, url, files[0], info or {}, is_tiktok=False)
    else:
        # Fallback: try to get story info
        info2, err2 = await asyncio.get_event_loop().run_in_executor(
            executor, run_yt_dlp_info, url, COOKIE_FILE
        )
        if info2 and info2.get("entries"):
            entries = list(info2["entries"])
            text = f"📖 <b>@{username}</b> ki Active Stories ({len(entries)}):\n\n"
            for i, entry in enumerate(entries, 1):
                text += f"{i}. {entry.get('title', 'Story')}\n🔗 {entry.get('url', 'N/A')}\n\n"
            if is_callback:
                await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=profile_keyboard(username), disable_web_page_preview=True)
            else:
                await update.message.reply_text(text, parse_mode="HTML", reply_markup=profile_keyboard(username), disable_web_page_preview=True)
        else:
            err_text = f"❌ Stories nahi mil payi.\n\nError: {err or 'No active stories / IP blocked'}\n\nCookie fresh hai check karo!"
            if is_callback:
                await update.callback_query.edit_message_text(err_text, reply_markup=profile_keyboard(username))
            else:
                await update.message.reply_text(err_text, reply_markup=profile_keyboard(username))

async def process_highlights(update: Update, context: ContextTypes.DEFAULT_TYPE, username: str, is_callback: bool):
    msg = await (update.callback_query.edit_message_text if is_callback else update.message.reply_text)(
        f"⏳ @{username} ke highlights fetch ho rahe hain..."
    )
    if not cookies_ready():
        err_text = "❌ Highlights ke liye Instagram login cookie chahiye!\n\n/setcookie se setup karo."
        if is_callback:
            await update.callback_query.edit_message_text(err_text, reply_markup=profile_keyboard(username))
        else:
            await update.message.reply_text(err_text, reply_markup=profile_keyboard(username))
        return
    
    # Highlights need direct links - show instructions
    text = (
        f"🌟 <b>@{username}</b> Highlights:\n\n"
        f"Highlights download ke liye <b>direct highlight link</b> paste karo.\n\n"
        f"Steps:\n"
        f"1. @{username} ki profile kholo\n"
        f"2. Koi highlight open karo\n"
        f"3. 'Copy Link' karo\n"
        f"4. Yahan paste karo!\n\n"
        f"Format: <code>https://instagram.com/s/...</code>"
    )
    if is_callback:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=profile_keyboard(username))
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=profile_keyboard(username))

async def process_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE, username: str, is_callback: bool):
    msg = await (update.callback_query.edit_message_text if is_callback else update.message.reply_text)(
        f"⏳ @{username} ke analytics calculate ho rahe hain..."
    )
    user_data = fetch_profile_info(username)
    if user_data:
        followers = user_data.get("edge_followed_by", {}).get("count", 0)
        following = user_data.get("edge_follow", {}).get("count", 0)
        posts_count = user_data.get("edge_owner_to_timeline_media", {}).get("count", 0)
        media = user_data.get("edge_owner_to_timeline_media", {}).get("edges", [])
        total_likes = 0
        total_comments = 0
        video_count = 0
        image_count = 0
        for edge in media[:12]:
            node = edge.get("node", {})
            total_likes += node.get("edge_liked_by", {}).get("count", 0)
            total_comments += node.get("edge_media_to_comment", {}).get("count", 0)
            if node.get("is_video", False):
                video_count += 1
            else:
                image_count += 1
        avg_likes = total_likes / len(media) if media else 0
        avg_comments = total_comments / len(media) if media else 0
        engagement = ((avg_likes + avg_comments) / followers * 100) if followers else 0
        text = (
            f"📊 <b>@{username} Analytics</b>\n\n"
            f"👥 <b>Followers:</b> {followers:,}\n"
            f"📸 <b>Total Posts:</b> {posts_count:,}\n"
            f"📈 <b>Avg Likes:</b> {avg_likes:,.0f}\n"
            f"💬 <b>Avg Comments:</b> {avg_comments:,.0f}\n"
            f"🔥 <b>Engagement Rate:</b> {engagement:.2f}%\n\n"
            f"🎬 <b>Videos:</b> {video_count}\n"
            f"🖼️ <b>Images:</b> {image_count}"
        )
    else:
        text = (
            f"📊 <b>@{username} Analytics</b>\n\n"
            f"❌ Profile data nahi mil paya.\n"
            f"Cloud IP block ho sakta hai.\n\n"
            f"Try karo: /setcookie"
        )
    if is_callback:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=profile_keyboard(username))
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=profile_keyboard(username))

# ==================== CALLBACKS ====================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "help":
        await help_cmd(update, context)
        return
    if data == "menu_main":
        await query.edit_message_text(
            "Username bhejo ya Instagram/TikTok link paste karo!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 Download Guide", callback_data="help")]])
        )
        return
    if data.startswith("menu_"):
        await query.edit_message_text("Username bhejo ya profile link paste karo!")
        return
    if data.startswith("profile:"):
        await process_profile(update, context, data.split(":", 1)[1], is_callback=True)
        return
    if data.startswith("posts:"):
        await process_posts(update, context, data.split(":", 1)[1], is_callback=True)
        return
    if data.startswith("reels:"):
        await process_reels(update, context, data.split(":", 1)[1], is_callback=True)
        return
    if data.startswith("stories:"):
        await process_stories(update, context, data.split(":", 1)[1], is_callback=True)
        return
    if data.startswith("highlights:"):
        await process_highlights(update, context, data.split(":", 1)[1], is_callback=True)
        return
    if data.startswith("analytics:"):
        await process_analytics(update, context, data.split(":", 1)[1], is_callback=True)
        return

# ==================== MESSAGE HANDLER (FIXED) ====================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (update.message.text or "").strip()
    if is_banned(user.id) or not text:
        return
    
    await log_user_message(update, context)
    
    # TikTok
    if "tiktok.com" in text.lower() or "tiktok" in text.lower():
        await update.message.reply_chat_action("upload_video")
        await update.message.reply_text("⏳ TikTok video download ho raha hai...")
        info, files, err = await asyncio.get_event_loop().run_in_executor(
            executor, run_yt_dlp_download, text, None
        )
        if files:
            caption = f"✅ TikTok Downloaded!\n🎵 {(info.get('title', '') or 'No title')[:100]}\n👤 {(info.get('uploader', '') or 'Unknown')[:50]}"
            sent = 0
            for f in files:
                if await safe_send_media(update, f, caption if sent == 0 else ""):
                    sent += 1
            if sent > 0 and files:
                await log_download_success(update, context, text, files[0], info or {}, is_tiktok=True)
            else:
                await update.message.reply_text("❌ File send nahi ho payi.")
                await log_download_failure(update, context, text, "Send failed", is_tiktok=True)
        else:
            await update.message.reply_text(f"❌ TikTok download failed.\n<code>{err or 'Unknown'}</code>", parse_mode="HTML")
            await log_download_failure(update, context, text, err or "Unknown", is_tiktok=True)
        return
    
    # Instagram
    if "instagram.com" in text.lower() or "instagr.am" in text.lower():
        # Profile URL detection
        profile_re = re.compile(r"https?://(?:www\.)?instagram\.com/([a-zA-Z0-9_.]{1,30})/?")
        match = profile_re.match(text)
        if match:
            username = match.group(1)
            if username not in ("p", "reel", "reels", "stories", "tv", "explore", "direct", "s"):
                await show_profile_menu(update, username, context)
                return
        
        await update.message.reply_chat_action("upload_video")
        
        # Check for story link
        is_story = "/stories/" in text.lower()
        if is_story and not cookies_ready():
            await update.message.reply_text(
                "❌ <b>Instagram Story</b> download ke liye cookie chahiye!\n\n"
                "/setcookie se setup karo ya Koyeb env mein IG_SESSION_ID add karo.",
                parse_mode="HTML"
            )
            await log_download_failure(update, context, text, "Story without cookies", is_tiktok=False)
            return
        
        await update.message.reply_text("⏳ Instagram download ho raha hai...")
        info, files, err = await asyncio.get_event_loop().run_in_executor(
            executor, run_yt_dlp_download, text, COOKIE_FILE
        )
        
        if files:
            title = (info.get("title", "") or "")[:200] if info else ""
            uploader = (info.get("uploader", "") or "")[:50] if info else ""
            caption = "✅ Instagram Downloaded!"
            if title:
                caption += f"\n📝 {title}"
            if uploader:
                caption += f"\n👤 {uploader}"
            if len(files) > 1:
                caption += f"\n📦 {len(files)} items"
            
            sent = 0
            for f in files:
                if await safe_send_media(update, f, caption if sent == 0 else ""):
                    sent += 1
            
            if sent > 0 and files:
                await log_download_success(update, context, text, files[0], info or {}, is_tiktok=False)
            else:
                await update.message.reply_text("❌ File send nahi ho payi.")
                await log_download_failure(update, context, text, "Telegram send failed", is_tiktok=False)
        else:
            err_msg = (
                "❌ Download nahi hua.\n\n"
                "Possible reasons:\n"
                "• Instagram ne server IP block kiya ho\n"
                "• Content private ho\n"
                "• Link expired / invalid\n\n"
            )
            if not cookies_ready():
                err_msg += "💡 Cookie set karo: /setcookie"
            else:
                err_msg += f"💡 Cookie expire ho gayi ho sakti hai. Update karo!\n📝 Error: <code>{err or 'Unknown'}</code>"
            await update.message.reply_text(err_msg, parse_mode="HTML")
            await log_download_failure(update, context, text, err or "Unknown", is_tiktok=False)
        return
    
    # If just a username
    if re.match(r"^[a-zA-Z0-9_.]{1,30}$", text):
        await show_profile_menu(update, text, context)
        return
    
    await update.message.reply_text("❌ Sirf Instagram ya TikTok links support hain!\n\n/help dekho for guide.")

# ==================== ADMIN COMMANDS ====================
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    uptime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cookie_status = "✅ Set" if cookies_ready() else "❌ Not Set"
    log_status = "✅ Active" if LOG_CHANNEL_ID else "❌ Not Set"
    text = (
        f"📊 <b>Bot Statistics</b>\n\n"
        f"🕒 Uptime: {uptime}\n"
        f"🍪 Cookie: {cookie_status}\n"
        f"📢 Log Channel: {log_status}\n"
        f"👑 Admins: {len(ADMIN_IDS)}\n"
        f"🚫 Banned: {len(BAN_LIST)}\n"
        f"🤖 Python: {sys.version.split()[0]}"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast message")
        return
    message = " ".join(context.args)
    await update.message.reply_text(f"Broadcast feature requires database. Message:\n{message}")

async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /ban user_id")
        return
    user_id = context.args[0]
    BAN_LIST.add(user_id)
    await update.message.reply_text(f"🚫 User {user_id} banned.")
    await send_log_text(context, f"🚫 <b>User banned</b> by admin {update.effective_user.id}: <code>{user_id}</code>")

async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /unban user_id")
        return
    user_id = context.args[0]
    BAN_LIST.discard(user_id)
    await update.message.reply_text(f"✅ User {user_id} unbanned.")
    await send_log_text(context, f"✅ <b>User unbanned</b> by admin {update.effective_user.id}: <code>{user_id}</code>")

# ==================== MAIN ====================
def main():
    init_cookies()
    start_health_server()
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("setcookie", setcookie_cmd))
    app.add_handler(CommandHandler("profile", profile_cmd))
    app.add_handler(CommandHandler("posts", posts_cmd))
    app.add_handler(CommandHandler("reels", reels_cmd))
    app.add_handler(CommandHandler("stories", stories_cmd))
    app.add_handler(CommandHandler("highlights", highlights_cmd))
    app.add_handler(CommandHandler("analytics", analytics_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    logger.info("🚀 Bot started! Waiting for messages...")
    app.run_polling()

if __name__ == "__main__":
    main()
