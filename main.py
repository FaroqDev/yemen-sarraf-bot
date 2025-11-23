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
# 2. دوال السحب (العملات)
# ==========================================
def get_market_rates():
    print("🕷️ بدء عملية سحب العملات...")
    
    # القيم الافتراضية للطوارئ
    default_rates = {
        "sanaa": {"usd": 535, "sar": 140},
        "aden": {"usd": 1630, "sar": 430}
    }

    sources = [
        "https://boqash.com/price-currency/",
        "https://economiyemen.net/", 
        "https://ydn.news",
        "https://yemen-exchange.com/",
        "https://www.2dec.net/rate.html",
        "https://khobaraa.net/section/20",
        "https://www.aden-tm.net/news/351778",
        "http://yemenief.org/Currency.aspx",
        "https://yemen-press.net"
    ]
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    collected_sanaa = []
    collected_aden = []
    forbidden_numbers = list(range(2010, 2031)) 

    for url in sources:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200: continue
            
            text = BeautifulSoup(response.content, 'html.parser').get_text()
            nums = [int(n) for n in re.findall(r'\d{3,4}', text)]
            
            ac = [n for n in nums if 1600 <= n <= 2200 and n not in forbidden_numbers]
            sc = [n for n in nums if 520 <= n <= 600]

            if ac: collected_aden.append(max(set(ac), key=ac.count))
            if sc: collected_sanaa.append(max(set(sc), key=sc.count))
        except: continue

    def clean_average(lst):
        lst = [n for n in lst if n not in forbidden_numbers]
        if not lst: return None
        if len(lst) < 3: return int(sum(lst)/len(lst))
        lst.sort()
        mid = len(lst)//2
        median = lst[mid] if len(lst)%2!=0 else (lst[mid-1]+lst[mid])/2
        clean = [x for x in lst if median*0.85 <= x <= median*1.15]
        return int(sum(clean)/len(clean)) if clean else int(median)

    fa = clean_average(collected_aden)
    if fa: 
        default_rates['aden']['usd'] = fa
        default_rates['aden']['sar'] = int(fa/3.82)
    
    fs = clean_average(collected_sanaa)
    if fs: 
        default_rates['sanaa']['usd'] = fs
        default_rates['sanaa']['sar'] = int(fs/3.78)
    
    return default_rates

# ==========================================
# 3. 🟡 محرك الذهب (متعدد المصادر - Multi-Source)
# ==========================================
def get_gold_price_live():
    print("🟡 محاولة جلب سعر الذهب...")

    # المصدر 1: GoldPrice.org API (الأدق والأسرع)
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://goldprice.org/'
        }
        r = requests.get("https://data-asg.goldprice.org/dbXRates/USD", headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            price = float(data['items'][0]['xauPrice'])
            print(f"✅ المصدر 1 (GoldPrice): ${price}")
            return price
    except Exception as e:
        print(f"⚠️ فشل المصدر 1: {e}")

    # المصدر 2: Yahoo Finance (GC=F - العقود الآجلة)
    try:
        ticker = yf.Ticker("GC=F")
        hist = ticker.history(period="1d")
        if not hist.empty:
            price = float(hist['Close'].iloc[-1])
            print(f"✅ المصدر 2 (Yahoo GC=F): ${price}")
            return price
    except Exception as e:
        print(f"⚠️ فشل المصدر 2: {e}")

    # المصدر 3: الاحتياطي الأخير (تثبيت السعر لتجنب الانهيار)
    print("❌ فشلت كل المصادر، استخدام القيمة الاحتياطية.")
    return 2715.0

def calculate_gold_updates(sanaa_usd, aden_usd):
    try:
        global_ounce = get_gold_price_live()
        
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
    except: return None

# ==========================================
# 4. إدارة التحديثات والتحذيرات
# ==========================================
def send_admin_alert(city, old, new):
    msg = f"🚨 قفزة في {city}: {old} -> {new}"
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except: pass

# ==========================================
# 5. التشغيل الرئيسي
# ==========================================
try:
    ref = db.reference('/')
    old_data = ref.child('rates').get()
    
    old_sanaa = old_data.get('sanaa', {}).get('usd_buy', 535) if old_data else 535
    old_aden = old_data.get('aden', {}).get('usd_buy', 1630) if old_data else 1630

    # 1. جلب العملات
    market_data = get_market_rates()
    new_sanaa = market_data['sanaa']['usd']
    new_aden = market_data['aden']['usd']
    
    # 2. فحص الأمان
    upd_sanaa = True; upd_aden = True
    if abs(new_sanaa - old_sanaa) > SAFETY_THRESHOLD: 
        send_admin_alert('sanaa', old_sanaa, new_sanaa)
        upd_sanaa = False
        new_sanaa = old_sanaa # تجميد السعر
    
    if abs(new_aden - old_aden) > SAFETY_THRESHOLD: 
        send_admin_alert('aden', old_aden, new_aden)
        upd_aden = False
        new_aden = old_aden # تجميد السعر

    # 3. حساب المؤشر
    def get_trend(new_p, old_p):
        if new_p > old_p: return 1
        if new_p < old_p: return -1
        return 0

    trend_sanaa = get_trend(new_sanaa, old_sanaa)
    trend_aden = get_trend(new_aden, old_aden)

    # 4. حساب الذهب والوقت
    gold_data = calculate_gold_updates(new_sanaa, new_aden)
    time_now = (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d %I:%M %p")

    if gold_data:
        sar_sanaa = market_data['sanaa']['sar'] if upd_sanaa else old_data['sanaa']['sar_buy']
        sar_aden = market_data['aden']['sar'] if upd_aden else old_data['aden']['sar_buy']

        updates = {
            "rates/last_update": time_now,
            "gold": gold_data,
            
            "rates/sanaa/usd_buy": new_sanaa,
            "rates/sanaa/usd_sell": new_sanaa + 4,
            "rates/sanaa/sar_buy": sar_sanaa,
            "rates/sanaa/sar_sell": sar_sanaa + 2,
            "rates/sanaa/trend": trend_sanaa,

            "rates/aden/usd_buy": new_aden,
            "rates/aden/usd_sell": new_aden + 15,
            "rates/aden/sar_buy": sar_aden,
            "rates/aden/sar_sell": sar_aden + 5,
            "rates/aden/trend": trend_aden,
        }

        ref.update(updates)
        print(f"✅ Updated: Sanaa={new_sanaa} | Aden={new_aden}")

        # 5. الإشعارات
        if (upd_sanaa and trend_sanaa != 0) or (upd_aden and trend_aden != 0):
            arrow = "🔺" if (new_aden > old_aden) else "🔻"
            msg = messaging.Message(notification=messaging.Notification(title=f"{arrow} تحديث أسعار الصرف", body=f"صنعاء: {new_sanaa} | عدن: {new_aden}"), topic='rates')
            try: messaging.send(msg)
            except: pass

except Exception as e:
    print(f"❌ Error: {e}")