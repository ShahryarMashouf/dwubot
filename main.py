import os
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from youtube_api import YoutubeDataApi
import google.generativeai as genai

# --- بخش تنظیمات اصلی ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
YOUTUBE_CHANNEL_ID = os.getenv('YOUTUBE_CHANNEL_ID')
TARGET_GROUP_ID = int(os.getenv('TARGET_GROUP_ID', 0))

if not all([TELEGRAM_TOKEN, GEMINI_API_KEY, YOUTUBE_API_KEY, YOUTUBE_CHANNEL_ID, TARGET_GROUP_ID]):
    raise ValueError("One or more environment variables are not set!")

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
        if response.candidates:
            return response.text
        else:
            return "پاسخ توسط فیلترهای ایمنی مسدود شد. لطفاً سوال دیگری بپرسید."
    except Exception as e:
        print(f"Error connecting to Gemini: {e}")
        return "متاسفانه در ارتباط با هوش مصنوعی مشکلی پیش آمده است."

# --- بخش مدیریت گروه و پیام خصوصی (بدون تغییر) ---
async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    message = update.message
    text = message.text.lower()
    if any(word in text for word in FORBIDDEN_WORDS):
        try:
            await message.delete()
            print(f"Forbidden word message from user {message.from_user.username} deleted.")
            return
        except Exception as e:
            print(f"Error deleting message: {e}")
    if any(word in text for word in TRIGGER_WORDS):
        print(f"Keyword triggered by message from {message.from_user.username}")
        thinking_message = await message.reply_text("🧠 در حال بررسی سوال شما...")
        ai_response = get_ai_response(message.text)
        await thinking_message.edit_text(ai_response)

async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text
    print(f"New private message from user {update.message.from_user.username}: {user_message}")
    thinking_message = await update.message.reply_text("🧠 در حال فکر کردن...")
    ai_response = get_ai_response(user_message)
    await thinking_message.edit_text(ai_response)

# --- بخش جدید: حلقه زمان‌بندی با asyncio ---
async def send_scheduled_ad_loop(application: Application) -> None:
    """یک حلقه بی‌نهایت که در پس‌زمینه اجرا شده و پیام تبلیغاتی ارسال می‌کند."""
    print("Scheduled messages loop started.")
    # 10 ثانیه صبر اولیه قبل از شروع حلقه
    await asyncio.sleep(10)
    while True:
        try:
            await application.bot.send_message(chat_id=TARGET_GROUP_ID, text=AD_MESSAGE)
            print("Scheduled ad message sent successfully.")
        except Exception as e:
            print(f"Error sending scheduled message: {e}")
        # برای 4 ساعت می‌خوابد (4 * 3600 ثانیه)
        await asyncio.sleep(4 * 3600)

async def post_init(application: Application) -> None:
    """این تابع پس از راه‌اندازی ربات، حلقه زمان‌بندی را در پس‌زمینه اجرا می‌کند."""
    asyncio.create_task(send_scheduled_ad_loop(application))

def main() -> None:
    """راه‌اندازی و اجرای ربات."""
    # --- بخش جدید: اضافه کردن post_init به سازنده ---
    application = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    # تعریف دستورها و پردازشگرها
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_group_messages))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_private_message))

    print("Group manager and private message bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
