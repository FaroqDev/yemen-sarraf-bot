import firebase_admin
from firebase_admin import credentials, db, messaging
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import re
import statistics
from datetime import datetime, timedelta


# ==========================================
# 1. إعدادات الاتصال (Config)
# ==========================================

# ⚠️ هام: ضع رابط قاعدة البيانات الخاص بك هنا
DATABASE_URL = "https://yemen-sarraf-default-rtdb.europe-west1.firebasedatabase.app/" 
KEY_FILE = "service-account.json"


# 🔐 بيانات تليجرام الخاصة بك (للتحذيرات)
TELEGRAM_BOT_TOKEN = "8583890330:AAFerk3-5YcYeZ95awp9Sf7tBy_Q-djbSZ0" 
TELEGRAM_CHAT_ID = 617150775

# 🛡️ حد الأمان (أي تغيير أكبر من هذا الرقم يعتبر خطراً)
SAFETY_THRESHOLD = 20



try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(KEY_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
except Exception as e:
    print(f"❌ Error Init: {e}")
    exit(1)

# ==========================================
# 2. دوال السحب والتحليل (المحسنة)
# ==========================================
def get_market_rates():
    print("🕷️ بدء عملية السحب والتحليل...")
    
    sources = [
        "https://boqash.com/price-currency/",  # 👈 تمت إعادته كأول مصدر (لأنه موثوق)
        "https://economiyemen.net/", 
        "https://ydn.news",
        "https://yemen-exchange.com/",
        "https://www.2dec.net/rate.html",
        "https://khobaraa.net/section/20",
        "https://www.aden-tm.net/news/351778",
        "http://yemenief.org/Currency.aspx",
        "https://yemen-press.net"
    ]
    
    # ... (بقية الدالة كما هي تماماً دون تغيير)

# ==========================================
# 3. 🟡 محرك الذهب (المصفح ضد الأخطاء)
# ==========================================
def get_global_gold_price():
    print("🟡 جاري جلب سعر الذهب العالمي...")
    
    # المحاولة 1: مصدر API مباشر (GoldPrice.org) - دقيق جداً
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        # هذا الرابط يعيد JSON مباشر للسعر
        r = requests.get("https://data-asg.goldprice.org/dbXRates/USD", headers=headers, timeout=10)
        data = r.json()
        price = data['items'][0]['xauPrice']
        print(f"✅ تم الجلب من GoldPrice: ${price}")
        return float(price)
    except Exception as e:
        print(f"⚠️ فشل المصدر الأول: {e}")

    # المحاولة 2: ياهو فاينانس (العقود الآجلة GC=F)
    try:
        gold_ticker = yf.Ticker("GC=F")
        history = gold_ticker.history(period="1d")
        if not history.empty:
            price = history['Close'].iloc[-1]
            print(f"✅ تم الجلب من Yahoo (GC=F): ${price}")
            return float(price)
    except Exception as e:
        print(f"⚠️ فشل المصدر الثاني: {e}")

    # المحاولة 3: قيمة احتياطية (لمنع توقف التطبيق)
    print("❌ فشلت كل المصادر، استخدام قيمة احتياطية.")
    return 2715.0

def calculate_gold_updates(sanaa_usd, aden_usd):
    try:
        global_ounce = get_global_gold_price()
        
        gram_24_usd = global_ounce / 31.1035
        
        def get_prices(usd_rate):
            gram_24 = int(gram_24_usd * usd_rate)
            return {
                "gram_24": int(gram_24/100)*100, 
                "gram_21": int(gram_24*0.875/100)*100, 
                "gunaih": int(gram_24*0.875*8/100)*100
            }

        return {
            "global_ounce_usd": round(global_ounce, 2),
            "sanaa": get_prices(sanaa_usd),
            "aden": get_prices(aden_usd)
        }
    except Exception as e:
        print(f"❌ خطأ حسابي في الذهب: {e}")
        return None

# ==========================================
# 4. التشغيل الرئيسي
# ==========================================
def send_admin_alert(city, old, new):
    msg = f"🚨 قفزة في {city}: {old} -> {new}"
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except: pass

try:
    ref = db.reference('/')
    old_data = ref.child('rates').get()
    
    old_sanaa = old_data.get('sanaa', {}).get('usd_buy', 535) if old_data else 535
    old_aden = old_data.get('aden', {}).get('usd_buy', 1630) if old_data else 1630

    market = get_market_rates()
    new_sanaa = market['sanaa']['usd']
    new_aden = market['aden']['usd']
    
    # Safety Check
    upd_sanaa = True; upd_aden = True
    if abs(new_sanaa - old_sanaa) > SAFETY_THRESHOLD: send_admin_alert('sanaa', old_sanaa, new_sanaa); upd_sanaa = False; new_sanaa = old_sanaa
    if abs(new_aden - old_aden) > SAFETY_THRESHOLD: send_admin_alert('aden', old_aden, new_aden); upd_aden = False; new_aden = old_aden

    def get_trend(new_p, old_p):
        if new_p > old_p: return 1
        if new_p < old_p: return -1
        return 0

    trend_sanaa = get_trend(new_sanaa, old_sanaa)
    trend_aden = get_trend(new_aden, old_aden)

    gold_data = calculate_gold_updates(new_sanaa, new_aden)
    time_now = (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d %I:%M %p")

    if gold_data:
        old_sar_sanaa = old_data.get('sanaa', {}).get('sar_buy', 140) if old_data else 140
        old_sar_aden = old_data.get('aden', {}).get('sar_buy', 430) if old_data else 430

        updates = {
            "rates/last_update": time_now,
            "gold": gold_data,
            
            "rates/sanaa/usd_buy": new_sanaa,
            "rates/sanaa/usd_sell": new_sanaa + 4,
            "rates/sanaa/sar_buy": market['sanaa']['sar'] if upd_sanaa else old_sar_sanaa,
            "rates/sanaa/sar_sell": (market['sanaa']['sar'] + 2) if upd_sanaa else old_sar_sanaa + 2,
            "rates/sanaa/trend": trend_sanaa,

            "rates/aden/usd_buy": new_aden,
            "rates/aden/usd_sell": new_aden + 15,
            "rates/aden/sar_buy": market['aden']['sar'] if upd_aden else old_sar_aden,
            "rates/aden/sar_sell": (market['aden']['sar'] + 5) if upd_aden else old_sar_aden + 5,
            "rates/aden/trend": trend_aden,
        }

        ref.update(updates)
        print(f"✅ Updated: Sanaa={new_sanaa} | Aden={new_aden}")

        # Notifications
        if (upd_sanaa and trend_sanaa != 0) or (upd_aden and trend_aden != 0):
            arrow = "🔺" if (new_aden > old_aden) else "🔻"
            msg = messaging.Message(notification=messaging.Notification(title=f"{arrow} تحديث أسعار الصرف", body=f"صنعاء: {new_sanaa} | عدن: {new_aden}"), topic='rates')
            try: messaging.send(msg)
            except: pass

except Exception as e:
    print(f"❌ Error: {e}")