import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import OrderedDict
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from youtube_api import YoutubeDataApi
import google.generativeai as genai

# --- بخش جدید: سرور سلامت برای Render ---
# این بخش باعث می‌شود Render فکر کند این یک وب‌سایت است و آن را روشن نگه دارد
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"Health check server running on port {port}")
    server.serve_forever()

# شروع سرور در یک رشته (Thread) جداگانه
threading.Thread(target=run_health_check_server, daemon=True).start()
# ---------------------------------------

# --- بخش تنظیمات حافظه پنهان (Cache) ---
response_cache = OrderedDict()
CACHE_MAX_SIZE = 100

# --- بخش تنظیمات اصلی ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
YOUTUBE_CHANNEL_ID = os.getenv('YOUTUBE_CHANNEL_ID')
TARGET_GROUP_IDS_STR = os.getenv('TARGET_GROUP_IDS', '')
TARGET_GROUP_IDS = [int(gid.strip()) for gid in TARGET_GROUP_IDS_STR.split(',') if gid.strip()]

if not all([TELEGRAM_TOKEN, GEMINI_API_KEY, YOUTUBE_API_KEY, YOUTUBE_CHANNEL_ID, TARGET_GROUP_IDS]):
    # در محیط بیلد ممکن است متغیرها نباشند، پس فقط هشدار می‌دهیم تا بیلد فیل نشود
    print("Warning: Environment variables not set properly. Check configuration.")

YOUTUBE_CHANNEL_LINK = f"https://www.youtube.com/channel/{YOUTUBE_CHANNEL_ID}"

# --- تعریف پیام‌های متنوع ---
YOUTUBE_AD_MESSAGE = f"""
📢 آیا می‌دانستید تمام مراحل مهاجرت به آلمان را در کانال یوتیوب ما پیدا می‌کنید؟

از پیدا کردن کار تا گرفتن ویزا و زندگی در آلمان، همه چیز را به صورت ویدیویی و رایگان توضیح داده‌ایم!

👇 همین حالا عضو شوید 👇
{YOUTUBE_CHANNEL_LINK}
"""
SERVICES_AD_MESSAGE = """
✨ آیا برای مهاجرت به کمک تخصصی نیاز دارید؟ ✨

تیم ما خدمات زیر را با بالاترین کیفیت ارائه می‌دهد:
🇩🇪 تدریس خصوصی و گروهی زبان آلمانی (از A1 تا C1)
🇬🇧 تدریس خصوصی و گروهی زبان انگلیسی
📄 نوشتن رزومه (Lebenslauf) و انگیزه‌نامه (Motivationsschreiben) حرفه‌ای

برای مشاوره رایگان با ما در تماس باشید: [آیدی یا لینک تماس شما]
"""
PROMO_MESSAGES = [YOUTUBE_AD_MESSAGE, SERVICES_AD_MESSAGE]
FORBIDDEN_WORDS = ['کلاهبردار', 'دروغگو', 'فحش_مثال_۱', 'فحش_مثال_۲']

# --- بخش هوش مصنوعی و یوتیوب ---
# هندلینگ خطا برای زمانی که کلیدها ست نشده‌اند
try:
    genai.configure(api_key=GEMINI_API_KEY)
    yt_api = YoutubeDataApi(YOUTUBE_API_KEY)
except:
    pass

def search_youtube_video(query: str) -> str:
    try:
        search_result = yt_api.search(q=query, channel_id=YOUTUBE_CHANNEL_ID, max_results=1)
        if search_result:
            video_id = search_result[0]['video_id']
            video_title = search_result[0]['video_title']
            video_link = f"https://www.youtube.com/watch?v={video_id}"
            print(f"Related video found: {video_title}")
            return video_link
    except Exception as e:
        print(f"Error searching YouTube: {e}")
    print("No specific video found. Returning main channel link.")
    return YOUTUBE_CHANNEL_LINK

def get_ai_response(question: str) -> str:
    cache_key = question.lower().strip()
    if cache_key in response_cache:
        print(f"CACHE HIT: Found response for question: '{question}'")
        return response_cache[cache_key]
    
    print(f"CACHE MISS: No response found for: '{question}'. Calling APIs.")
    youtube_link = search_youtube_video(question)
    prompt = f"""
    You are an expert assistant on work-based immigration to Germany. Your task is to answer user questions based on reliable information and videos from a specific YouTube channel.
    User's question: "{question}"
    A helpful link from the YouTube channel: {youtube_link}
    Your tasks:
    1. Answer the user's question accurately, completely, and in a friendly tone, in Persian.
    2. At the end of your response, introduce the link provided above with an encouraging sentence for the user to watch it.
    3. If the link points to a specific video (containing "watch?v="), introduce it as a "related video".
    4. If the link points to the main channel page (containing "/channel/"), introduce it as the "main YouTube channel" and mention that while a specific video was not found, the user can search for similar topics on the channel.
    5. Your response must only be about immigration to Germany. If the question is unrelated, politely state that you only specialize in this area.
    """
    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content(prompt)
        ai_response = "پاسخ توسط فیلترهای ایمنی مسدود شد. لطفاً سوال دیگری بپرسید."
        if response.candidates:
            ai_response = response.text
        if len(response_cache) >= CACHE_MAX_SIZE:
            response_cache.popitem(last=False)
        response_cache[cache_key] = ai_response
        return ai_response
    except Exception as e:
        print(f"Error connecting to Gemini: {e}")
        return "متاسفانه در ارتباط با هوش مصنوعی مشکلی پیش آمده است."

# --- بخش مدیریت گروه و پیام خصوصی ---
async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    message = update.message
    text = message.text
    bot_username = context.bot.username.lower()
    text_lower = text.lower()
    if any(word in text_lower for word in FORBIDDEN_WORDS):
        try:
            await message.delete()
            print(f"Forbidden word message from user {message.from_user.username} deleted.")
            return
        except Exception as e:
            print(f"Error deleting message: {e}")

    # فقط اگر ربات تگ شده بود، پاسخ بده
    if f"@{bot_username}" in text_lower:
        question = text.replace(f"@{context.bot.username}", "").strip()
        print(f"Bot triggered by mention from {message.from_user.username}")
        
        if not question:
            await message.reply_text("سلام! لطفاً سوال خود را بعد از نام من بپرسید تا پاسخ دهم.", quote=True)
            return

        thinking_message = await message.reply_text("🧠 در حال بررسی سوال شما...")
        ai_response = get_ai_response(question)
        await thinking_message.edit_text(ai_response)

async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text
    print(f"New private message from user {update.message.from_user.username}: {user_message}")
    thinking_message = await update.message.reply_text("🧠 در حال فکر کردن...")
    ai_response = get_ai_response(user_message)
    await thinking_message.edit_text(ai_response)

# --- بخش زمان‌بندی با asyncio ---
async def send_promo_messages_loop(application: Application) -> None:
    """هر 10 ساعت یک بار، یکی از پیام‌های تبلیغاتی را به صورت متناوب ارسال می‌کند."""
    print("Promotional messages loop started.")
    promo_index = 0
    await asyncio.sleep(15)
    while True:
        message_to_send = PROMO_MESSAGES[promo_index]
        print(f"Sending promo message #{promo_index + 1} to groups: {TARGET_GROUP_IDS}")
        for group_id in TARGET_GROUP_IDS:
            try:
                await application.bot.send_message(chat_id=group_id, text=message_to_send)
                print(f"Promo message sent successfully to group {group_id}.")
            except Exception as e:
                print(f"Failed to send promo message to group {group_id}. Error: {e}")
        promo_index = (promo_index + 1) % len(PROMO_MESSAGES)
        await asyncio.sleep(10 * 3600)

async def post_init(application: Application) -> None:
    asyncio.create_task(send_promo_messages_loop(application))

# --- بخش اصلی برنامه ---
def main() -> None:
    """راه‌اندازی و اجرای ربات."""
    application = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_group_messages))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_private_message))
    print("Multi-group manager bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
