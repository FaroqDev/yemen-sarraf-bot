import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
import yfinance as yf
from datetime import datetime, timedelta  # 👈 تأكد أن هذا السطر موجود هكذا
# ==========================================
# 1. إعدادات الاتصال (Config)
# ==========================================

# ⚠️ هام: ضع رابط قاعدة البيانات الخاص بك هنا
DATABASE_URL = "https://yemen-sarraf-default-rtdb.europe-west1.firebasedatabase.app/" 

# اسم ملف المفتاح الذي حملته
KEY_FILE = "service-account.json"

# ==========================================
# 2. تهيئة الاتصال (Setup)
# ==========================================
print("🔌 جاري الاتصال بـ Firebase...")

if not firebase_admin._apps:
    cred = credentials.Certificate(KEY_FILE)
    firebase_admin.initialize_app(cred, {
        'databaseURL': DATABASE_URL
    })

print("✅ تم الاتصال بنجاح!")

# ==========================================
# 3. محرك الذهب (Gold Engine)
# ==========================================
def calculate_gold_updates(sanaa_usd, aden_usd):
    print("🟡 جاري جلب سعر الذهب العالمي...")
    try:
        # جلب سعر الأونصة لايف
        gold_ticker = yf.Ticker("GC=F")
        global_ounce = gold_ticker.history(period="1d")['Close'].iloc[-1]
        print(f"💰 سعر الأونصة العالمي: ${global_ounce:.2f}")

        # معادلات الذهب
        gram_24_usd = global_ounce / 31.1035
        
        def get_prices(usd_rate):
            gram_24 = int(gram_24_usd * usd_rate) # السعر الخام لعيار 24
            
            # تقريب لأقرب 100 ريال
            gram_21 = int((gram_24 * 0.875) / 100) * 100
            gunaih = int((gram_21 * 8) / 100) * 100 
            
            # 👇 هنا كان النقص: الآن نرجع جرام 24 أيضاً
            return {
                "gram_24": int(gram_24 / 100) * 100, 
                "gram_21": gram_21, 
                "gunaih": gunaih
            }

        return {
            "global_ounce_usd": round(global_ounce, 2),
            "sanaa": get_prices(sanaa_usd),
            "aden": get_prices(aden_usd)
        }
    except Exception as e:
        print(f"❌ خطأ في الذهب: {e}")
        return None
# ==========================================
# 4. التنفيذ والتحديث (Execution)
# ==========================================

# لنفترض أن الروبوت سحب هذه الأسعار (سنجعلها ثابتة للتجربة الآن)
NEW_SANAA_USD = 537
NEW_ADEN_USD = 1680

# حساب الذهب بناءً على هذه الأسعار
gold_data = calculate_gold_updates(NEW_SANAA_USD, NEW_ADEN_USD)

if gold_data:
    # تجهيز البيانات للإرسال
    # حساب توقيت اليمن (UTC + 3)
    yemen_time = datetime.utcnow() + timedelta(hours=3)
    formatted_time = yemen_time.strftime("%Y-%m-%d %I:%M %p")

    updates = {
        "rates/sanaa/usd_buy": NEW_SANAA_USD,
        "rates/sanaa/usd_sell": NEW_SANAA_USD + 5, 
        "rates/aden/usd_buy": NEW_ADEN_USD,
        "rates/aden/usd_sell": NEW_ADEN_USD + 10,
        "rates/last_update": formatted_time, # 👈 استخدام المتغير الجديد
        "gold": gold_data
    }

    print("🚀 جاري رفع البيانات للسيرفر...")
    ref = db.reference('/')
    ref.update(updates)
    print("✨ تم التحديث! اذهب لمتصفحك وشاهد الأرقام تتغير.")