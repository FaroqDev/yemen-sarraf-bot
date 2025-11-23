import firebase_admin
from firebase_admin import credentials, db, messaging
import yfinance as yf
import os
import sys
from datetime import datetime, timedelta

# إعدادات الاتصال
DATABASE_URL = "https://YOUR-PROJECT-ID-default-rtdb.firebaseio.com/" 
KEY_FILE = "service-account.json"

if not firebase_admin._apps:
    cred = credentials.Certificate(KEY_FILE)
    firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})

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

# --- قراءة المدخلات من GitHub ---
# الترتيب: [اسم الملف, المدينة, العملة, الشراء, البيع]
try:
    city = sys.argv[1]
    currency = sys.argv[2]
    buy_price = float(sys.argv[3])
    sell_price = float(sys.argv[4])
    
    print(f"🔄 جاري التحديث اليدوي: {city} - {currency} - {buy_price}")

    ref = db.reference('/')
    yemen_time = datetime.utcnow() + timedelta(hours=3)
    formatted_time = yemen_time.strftime("%Y-%m-%d %I:%M %p")

    updates = {
        f"rates/{city}/{currency}_buy": buy_price,
        f"rates/{city}/{currency}_sell": sell_price,
        "rates/last_update": formatted_time
    }

    if currency == 'usd':
        gold_data = calculate_gold(buy_price)
        if gold_data:
            updates[f"gold/{city}"] = {
                "gram_24": gold_data['gram_24'],
                "gram_21": gold_data['gram_21'],
                "gunaih": gold_data['gunaih']
            }
            updates["gold/global_ounce_usd"] = gold_data['global_ounce']

    ref.update(updates)
    print("✅ تم تحديث قاعدة البيانات!")

    # إرسال إشعار
    flag = "🇺🇸" if currency == 'usd' else "🇸🇦"
    curr_name = "دولار" if currency == 'usd' else "سعودي"
    city_name = "صنعاء" if city == 'sanaa' else "عدن"
    
    msg = messaging.Message(
        notification=messaging.Notification(
            title=f"تحديث يدوي {city_name} {flag}",
            body=f"{curr_name}: شراء {buy_price} | بيع {sell_price}"
        ),
        topic='rates',
    )
    messaging.send(msg)
    print("🔔 تم إرسال الإشعار.")

except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)