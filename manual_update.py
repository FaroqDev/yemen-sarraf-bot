import firebase_admin
from firebase_admin import credentials, db, messaging
import yfinance as yf
import sys
from datetime import datetime, timedelta

# ==========================================
# 1. إعدادات الاتصال
# ==========================================
DATABASE_URL = "https://yemen-sarraf-default-rtdb.europe-west1.firebasedatabase.app/"
KEY_FILE = "service-account.json"

# تهيئة الاتصال
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(KEY_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
except Exception as e:
    print(f"❌ Error Init: {e}")
    exit(1)

# --- دالة حساب الذهب ---
def calculate_gold(usd_buy_rate):
    try:
        gold_ticker = yf.Ticker("GC=F")
        global_ounce = gold_ticker.history(period="1d")['Close'].iloc[-1]
        gram_24_usd = global_ounce / 31.1035
        
        gram_24 = int(gram_24_usd * usd_buy_rate)
        gram_21 = int((gram_24 * 0.875) / 100) * 100
        gunaih = int((gram_21 * 8) / 100) * 100 
        return {"gram_24": int(gram_24/100)*100, "gram_21": gram_21, "gunaih": gunaih, "global_ounce": round(global_ounce, 2)}
    except: return None

# ==========================================
# 2. التنفيذ الرئيسي
# ==========================================
try:
    # قراءة المدخلات من GitHub Actions
    # الترتيب: [script, city, currency, buy, sell, notify]
    city = sys.argv[1]
    currency = sys.argv[2]
    buy_price = float(sys.argv[3])
    sell_price = float(sys.argv[4])
    should_notify = sys.argv[5].lower() == 'true'
    
    print(f"🔄 التحديث اليدوي: {city} | {currency} | {buy_price}")

    ref = db.reference('/')
    
    # 1. جلب السعر القديم لحساب المؤشر (Trend)
    old_price_snapshot = ref.child(f'rates/{city}/{currency}_buy').get()
    old_price = float(old_price_snapshot) if old_price_snapshot is not None else buy_price
    
    # 2. حساب المؤشر
    trend = 0
    if buy_price > old_price: trend = 1     # صعود
    elif buy_price < old_price: trend = -1  # هبوط
    
    # 3. تجهيز الوقت
    yemen_time = datetime.utcnow() + timedelta(hours=3)
    formatted_time = yemen_time.strftime("%Y-%m-%d %I:%M %p")

    # 4. قائمة التحديثات
    updates = {
        f"rates/{city}/{currency}_buy": buy_price,
        f"rates/{city}/{currency}_sell": sell_price,
        f"rates/{city}/trend": trend,  # 👈 تحديث المؤشر
        "rates/last_update": formatted_time
    }

    # تحديث الذهب إذا كان التغيير في الدولار
    if currency == 'usd':
        gold_data = calculate_gold(buy_price)
        if gold_data:
            updates[f"gold/{city}"] = {
                "gram_24": gold_data['gram_24'],
                "gram_21": gold_data['gram_21'],
                "gunaih": gold_data['gunaih']
            }
            updates["gold/global_ounce_usd"] = gold_data['global_ounce']

    # تنفيذ التحديث في القاعدة
    ref.update(updates)
    print(f"✅ تم تحديث البيانات بنجاح! (Trend: {trend})")

    # 5. إرسال الإشعار (إذا طلب المستخدم)
    if should_notify:
        flag = "🇺🇸" if currency == 'usd' else "🇸🇦"
        curr_name = "دولار" if currency == 'usd' else "سعودي"
        city_name = "صنعاء" if city == 'sanaa' else "عدن"
        
        # تحديد أيقونة السهم للإشعار
        arrow = "➖"
        if trend == 1: arrow = "🔺"
        elif trend == -1: arrow = "🔻"
        
        msg = messaging.Message(
            notification=messaging.Notification(
                title=f"{arrow} تحديث يدوي: {city_name} {flag}",
                body=f"{curr_name}: شراء {buy_price} | بيع {sell_price}"
            ),
            topic='rates',
        )
        messaging.send(msg)
        print("🔔 تم إرسال الإشعار.")
    else:
        print("🔕 تم تخطي الإشعار.")

except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)