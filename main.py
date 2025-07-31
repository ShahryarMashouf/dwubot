import os
import asyncio
import random
from collections import OrderedDict
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from youtube_api import YouTubeDataAPI
import google.generativeai as genai

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
    raise ValueError("One or more environment variables are not set or TARGET_GROUP_IDS is empty!")

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

برای مشاوره رایگان با ما در تماس باشید: [https://t.me/shahryarmsf]
"""
PROMO_MESSAGES = [YOUTUBE_AD_MESSAGE, SERVICES_AD_MESSAGE]
FORBIDDEN_WORDS = ['کلاهبردار', 'دروغگو', 'کص', 'کیر']
TRIGGER_WORDS = ['مهاجرت',"آوسبیلدونگ", 'ویزا', 'آلمان', 'اقامت', 'کار', 'سفارت', 'تحصیلی', 'جاب آفر']

# --- بخش هوش مصنوعی و یوتیوب ---
genai.configure(api_key=GEMINI_API_KEY)
yt_api = YouTubeDataAPI(YOUTUBE_API_KEY)

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

def get_germany_fact() -> str:
    """با استفاده از Gemini یک فکت جالب و کوتاه درباره آلمان تولید می‌کند."""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        prompt = "به زبان فارسی، یک حقیقت جالب، کوتاه و کمتر شنیده شده درباره کشور آلمان بگو. (فقط خود فکت را بگو، بدون هیچ جمله اضافه‌ای)"
        response = model.generate_content(prompt)
        if response.candidates:
            return response.text
        return "مشکلی در تولید فکت پیش آمد."
    except Exception as e:
        print(f"Error generating Germany fact: {e}")
        return "امروز فکتی برای گفتن ندارم!"

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
    if any(word in text_lower for word in TRIGGER_WORDS) or f"@{bot_username}" in text_lower:
        question = text.replace(f"@{context.bot.username}", "").strip()
        print(f"Bot triggered by message from {message.from_user.username}")
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
    """هر 4 ساعت یک بار، یکی از پیام‌های تبلیغاتی را به صورت متناوب ارسال می‌کند."""
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
        await asyncio.sleep(4 * 3600)

async def send_germany_fact_loop(application: Application) -> None:
    """هر 2 ساعت یک بار، یک فکت جالب درباره آلمان ارسال می‌کند."""
    print("Germany facts loop started.")
    await asyncio.sleep(10)
    while True:
        fact = get_germany_fact()
        message_to_send = f"🇩🇪 آیا می‌دانستید؟\n\n{fact}"
        print(f"Sending Germany fact to groups: {TARGET_GROUP_IDS}")
        for group_id in TARGET_GROUP_IDS:
            try:
                await application.bot.send_message(chat_id=group_id, text=message_to_send)
                print(f"Germany fact sent successfully to group {group_id}.")
            except Exception as e:
                print(f"Failed to send fact to group {group_id}. Error: {e}")
        await asyncio.sleep(2 * 3600)

async def post_init(application: Application) -> None:
    """پس از راه‌اندازی ربات، هر دو حلقه زمان‌بندی را در پس‌زمینه اجرا می‌کند."""
    asyncio.create_task(send_promo_messages_loop(application))
    asyncio.create_task(send_germany_fact_loop(application))

# --- بخش اصلی برنامه (تغییر یافته) ---
async def main() -> None:
    """راه‌اندازی و اجرای ربات با خاموش شدن صحیح."""
    application = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    # تعریف دستورها و پردازشگرها
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_group_messages))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_private_message))

    # اجرای ربات با استفاده از context manager برای خاموش شدن صحیح
    print("Multi-group manager bot is running...")
    async with application:
        await application.start()
        await application.updater.start_polling()
        # برنامه را تا زمان دریافت سیگنال خاموش شدن، در حال اجرا نگه می‌دارد
        await asyncio.Future()

if __name__ == "__main__":
    # اجرای برنامه اصلی به صورت آسنکرون
    asyncio.run(main())
