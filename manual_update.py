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

# دالة الذهب
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
# التشغيل الرئيسي (تحديث شامل)
# ==========================================
try:
    # قراءة المدخلات [script, city, usd_buy, usd_sell, sar_buy, sar_sell, notify]
    city = sys.argv[1]
    usd_buy = float(sys.argv[2])
    usd_sell = float(sys.argv[3])
    sar_buy = float(sys.argv[4])
    sar_sell = float(sys.argv[5])
    should_notify = sys.argv[6].lower() == 'true'
    
    print(f"🔄 تحديث شامل لـ {city}...")

    ref = db.reference('/')
    
    # 1. جلب السعر القديم لحساب المؤشر (نعتمد على الدولار كمقياس)
    old_price_snapshot = ref.child(f'rates/{city}/usd_buy').get()
    old_price = float(old_price_snapshot) if old_price_snapshot is not None else usd_buy
    
    # 2. حساب المؤشر
    trend = 0
    if usd_buy > old_price: trend = 1     # صعود
    elif usd_buy < old_price: trend = -1  # هبوط
    
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
        
        "rates/last_update": formatted_time,       # العام
        f"rates/{city}/last_update": formatted_time # 👈 الخاص بالمدينة
    }

    # 5. تحديث الذهب (يعتمد على الدولار الجديد)
    gold_data = calculate_gold(usd_buy)
    if gold_data:
        updates[f"gold/{city}/gram_24"] = gold_data['gram_24']
        updates[f"gold/{city}/gram_21"] = gold_data['gram_21']
        updates[f"gold/{city}/gunaih"] = gold_data['gunaih']
        updates[f"gold/{city}/last_update"] = formatted_time # 👈 الخاص بذهب المدينة
        
        updates["gold/global_ounce_usd"] = gold_data['global_ounce']

    
    # التنفيذ
    ref.update(updates)
    print(f"✅ تم التحديث الشامل بنجاح! (Trend: {trend})")

    # 6. الإشعار الموحد
    if should_notify:
        arrow = "➖"
        if trend == 1: arrow = "🔺"
        elif trend == -1: arrow = "🔻"
        
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
        print("🔔 تم إرسال الإشعار.")
    else:
        print("🔕 تم تخطي الإشعار.")

except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)