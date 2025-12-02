import logging
import os
import firebase_admin
from firebase_admin import credentials, db, messaging
import yfinance as yf
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# ==========================================
# إعداد نظام Logging
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('manual_update.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==========================================
# 1. إعدادات الاتصال
# ==========================================
load_dotenv()

DATABASE_URL = os.getenv('FIREBASE_DATABASE_URL', 'https://yemen-sarraf-default-rtdb.europe-west1.firebasedatabase.app/')
KEY_FILE = "service-account.json"

# تهيئة الاتصال
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(KEY_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
        logger.info("✅ تم الاتصال بـ Firebase")
except Exception as e:
    logger.error(f"❌ Error Init: {e}")
    print(f"❌ Error Init: {e}")
    exit(1)

# ==========================================
# 2. دالة حساب الذهب
# ==========================================
def calculate_gold(usd_buy_rate):
    """
    يحسب أسعار الذهب بناءً على السعر العالمي وسعر الدولار
    """
    try:
        gold_ticker = yf.Ticker("GC=F")
        global_ounce = gold_ticker.history(period="1d")['Close'].iloc[-1]
        
        if global_ounce <= 0:
            logger.error("❌ سعر الذهب غير صحيح")
            return None
            
        gram_24_usd = global_ounce / 31.1035
        
        gram_24 = int(gram_24_usd * usd_buy_rate)
        gram_21 = int((gram_24 * 0.875) / 100) * 100
        gunaih = int((gram_21 * 8) / 100) * 100
        
        return {
            "gram_24": int(gram_24/100)*100,
            "gram_21": gram_21,
            "gunaih": gunaih,
            "global_ounce": round(global_ounce, 2)
        }
    except Exception as e:
        logger.error(f"❌ خطأ في حساب الذهب: {e}")
        return None

# ==========================================
# 3. التشغيل الرئيسي (تحديث شامل)
# ==========================================
try:
    # التحقق من المدخلات
    if len(sys.argv) < 7:
        print("❌ الاستخدام: python manual_update.py [city] [usd_buy] [usd_sell] [sar_buy] [sar_sell] [notify]")
        print("مثال: python manual_update.py sanaa 535 538 142 143 true")
        logger.error("❌ مدخلات ناقصة")
        exit(1)
    
    # قراءة المدخلات
    city = sys.argv[1].lower()
    
    try:
        usd_buy = float(sys.argv[2])
        usd_sell = float(sys.argv[3])
        sar_buy = float(sys.argv[4])
        sar_sell = float(sys.argv[5])
    except ValueError:
        print("❌ الأسعار يجب أن تكون أرقاماً")
        logger.error("❌ أسعار غير صحيحة")
        exit(1)
    
    should_notify = sys.argv[6].lower() == 'true'
    
    # التحقق من صحة البيانات
    if city not in ['sanaa', 'aden']:
        print("❌ المدينة يجب أن تكون: sanaa أو aden")
        logger.error(f"❌ مدينة غير صحيحة: {city}")
        exit(1)
    
    if usd_buy <= 0 or usd_sell <= 0 or sar_buy <= 0 or sar_sell <= 0:
        print("❌ جميع الأسعار يجب أن تكون أكبر من صفر")
        logger.error("❌ أسعار سالبة")
        exit(1)
    
    if usd_sell <= usd_buy or sar_sell <= sar_buy:
        print("❌ سعر البيع يجب أن يكون أكبر من سعر الشراء")
        logger.error("❌ سعر بيع أقل من شراء")
        exit(1)
    
    logger.info(f"🔄 بدء تحديث شامل لـ {city}")
    print(f"🔄 تحديث شامل لـ {city}...")

    ref = db.reference('/')
    
    # 1. جلب السعر القديم لحساب المؤشر (نعتمد على الدولار كمقياس)
    old_price_snapshot = ref.child(f'rates/{city}/usd_buy').get()
    old_price = float(old_price_snapshot) if old_price_snapshot is not None else usd_buy
    
    # 2. حساب المؤشر
    trend = 0
    if usd_buy > old_price:
        trend = 1     # صعود
    elif usd_buy < old_price:
        trend = -1    # هبوط
    
    # 3. الوقت
    yemen_time = datetime.utcnow() + timedelta(hours=3)
    formatted_time = yemen_time.strftime("%Y-%m-%d %I:%M %p")

    # 4. تجهيز البيانات (دولار + سعودي + وقت + مؤشر)
    updates = {
        f"rates/{city}/usd_buy": usd_buy,
        f"rates/{city}/usd_sell": usd_sell,
        f"rates/{city}/sar_buy": sar_buy,
        f"rates/{city}/sar_sell": sar_sell,
        f"rates/{city}/trend": trend,
        "rates/last_update": formatted_time,
        f"rates/{city}/last_update": formatted_time
    }

    # 5. تحديث الذهب (يعتمد على الدولار الجديد)
    gold_data = calculate_gold(usd_buy)
    if gold_data:
        updates[f"gold/{city}/gram_24"] = gold_data['gram_24']
        updates[f"gold/{city}/gram_21"] = gold_data['gram_21']
        updates[f"gold/{city}/gunaih"] = gold_data['gunaih']
        updates[f"gold/{city}/last_update"] = formatted_time
        updates["gold/global_ounce_usd"] = gold_data['global_ounce']
        logger.info(f"✅ تم حساب الذهب: جرام 21 = {gold_data['gram_21']:,}")

    # 6. التنفيذ
    ref.update(updates)
    logger.info(f"✅ تم التحديث بنجاح! (Trend: {trend})")
    print(f"✅ تم التحديث الشامل بنجاح! (Trend: {trend})")

    # 7. الإشعار الموحد
    if should_notify:
        try:
            arrow = "➖"
            if trend == 1:
                arrow = "🔺"
            elif trend == -1:
                arrow = "🔻"
            
            city_name = "صنعاء" if city == 'sanaa' else "عدن"
            
            msg_body = (
                f"🇺🇸 دولار: {usd_buy} - {usd_sell}\n"
                f"🇸🇦 سعودي: {sar_buy} - {sar_sell}"
            )
            
            msg = messaging.Message(
                notification=messaging.Notification(
                    title=f"{arrow} تحديث أسعار {city_name}",
                    body=msg_body
                ),
                topic='rates',
            )
            messaging.send(msg)
            logger.info("✅ تم إرسال الإشعار")
            print("🔔 تم إرسال الإشعار.")
        except Exception as e:
            logger.error(f"❌ فشل إرسال الإشعار: {e}")
            print(f"⚠️ فشل إرسال الإشعار: {e}")
    else:
        logger.info("تم تخطي الإشعار")
        print("🔕 تم تخطي الإشعار.")

except KeyboardInterrupt:
    logger.info("تم إيقاف البرنامج بواسطة المستخدم")
    print("\n❌ تم إيقاف البرنامج.")
    exit(1)
except Exception as e:
    logger.error(f"❌ خطأ غير متوقع: {e}", exc_info=True)
    print(f"❌ Error: {e}")
    exit(1)