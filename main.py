import os
import asyncio
from collections import OrderedDict
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from youtube_api import YoutubeDataApi
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
AD_MESSAGE = f"""
⭐ به دنبال مهاجرت به آلمان هستید؟ ⭐
ما در کانال یوتیوب خود تمام مراحل را قدم به قدم توضیح داده‌ایم!
از پیدا کردن کار تا گرفتن ویزا.
همین حالا سابسکرایب کنید: {YOUTUBE_CHANNEL_LINK}
"""
FORBIDDEN_WORDS = ['کلاهبردار', 'دروغگو', 'فحش_مثال_۱', 'فحش_مثال_۲']
TRIGGER_WORDS = ['مهاجرت', 'ویزا', 'آلمان', 'اقامت', 'کار', 'سفارت', 'تحصیلی', 'جاب آفر']

# --- بخش هوش مصنوعی و یوتیوب ---
genai.configure(api_key=GEMINI_API_KEY)
yt_api = YoutubeDataApi(YOUTUBE_API_KEY)

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
    شما یک دستیار متخصص در زمینه مهاجرت کاری به آلمان هستید.
    وظیفه شما پاسخ دادن به سوالات کاربران بر اساس اطلاعات معتبر و ویدیوهای یک کانال یوتیوب است.
    سوال کاربر: "{question}"
    لینک کمکی از یوتیوب: {youtube_link}
    وظایف شما:
    1. به سوال کاربر به صورت دقیق، کامل و دوستانه پاسخ دهید.
    2. در انتهای پاسخ خود، لینکی که در بالا به شما داده شده را معرفی کنید.
    3. اگر لینک به یک ویدیوی خاص (شامل "watch?v=") اشاره دارد، آن را به عنوان "ویدیوی مرتبط" معرفی کرده و کاربر را به تماشای آن تشویق کنید.
    4. اگر لینک به صفحه اصلی کانال (شامل "/channel/") اشاره دارد، آن را به عنوان "کانال اصلی یوتیوب" معرفی کنید و بگویید که ویدیوی دقیقی یافت نشده اما کاربر می‌تواند در کانال به دنبال مطالب مشابه بگردد.
    5. پاسخ شما باید فقط در مورد مهاجرت به آلمان باشد. اگر سوال نامرتبط بود، با احترام بگویید که فقط در این زمینه تخصص دارید.
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

    # --- خط تغییر یافته ---
    # اگر کلمه کلیدی در پیام بود یا ربات تگ شده بود، پاسخ بده
    if any(word in text_lower for word in TRIGGER_WORDS) or f"@{bot_username}" in text_lower:
        # اگر ربات تگ شده بود، نام آن را از متن سوال حذف می‌کنیم
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
async def send_scheduled_ad_loop(application: Application) -> None:
    print("Scheduled messages loop started.")
    await asyncio.sleep(10)
    while True:
        print(f"Sending ad to groups: {TARGET_GROUP_IDS}")
        for group_id in TARGET_GROUP_IDS:
            try:
                await application.bot.send_message(chat_id=group_id, text=AD_MESSAGE)
                print(f"Ad message sent successfully to group {group_id}.")
            except Exception as e:
                print(f"Failed to send message to group {group_id}. Error: {e}")
        await asyncio.sleep(4 * 3600)

async def post_init(application: Application) -> None:
    asyncio.create_task(send_scheduled_ad_loop(application))

def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_group_messages))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_private_message))
    print("Multi-group manager bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
