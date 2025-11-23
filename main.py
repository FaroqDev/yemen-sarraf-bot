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
SAFETY_THRESHOLD = 2



try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(KEY_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
except Exception as e:
    print(f"❌ Error Init: {e}")
    exit(1)

# ==========================================
# 2. دوال السحب والتنظيف
# ==========================================
def calculate_median(lst):
    n = len(lst)
    if n < 1: return 0
    s_lst = sorted(lst)
    if n % 2 == 1: return s_lst[n//2]
    else: return (s_lst[n//2 - 1] + s_lst[n//2]) / 2.0

def clean_and_average(numbers_list, forbidden_list):
    numbers_list = [n for n in numbers_list if n not in forbidden_list]
    if not numbers_list: return None
    if len(numbers_list) < 3: return int(sum(numbers_list) / len(numbers_list))
    median = calculate_median(numbers_list)
    clean_nums = [x for x in numbers_list if median * 0.85 <= x <= median * 1.15]
    if not clean_nums: return int(median)
    return int(sum(clean_nums) / len(clean_nums))

def get_market_rates():
    print("🕷️ Start Scraping...")
    sources = [
        "https://economiyemen.net/", "https://ydn.news",
        "https://yemen-exchange.com/", "https://www.2dec.net/rate.html",
        "https://khobaraa.net/section/20", "https://www.aden-tm.net/news/351778",
        "http://yemenief.org/Currency.aspx", "https://yemen-press.net"
    ]
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    rates = {"sanaa": {"usd": 535, "sar": 140}, "aden": {"usd": 1630, "sar": 430}}
    collected_sanaa = []
    collected_aden = []
    forbidden_numbers = list(range(2010, 2031)) 

    for url in sources:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200: continue
            text = BeautifulSoup(response.content, 'html.parser').get_text()
            nums = [int(n) for n in re.findall(r'\d{3,4}', text)]
            
            ac = [n for n in nums if 1600 <= n <= 2200]
            sc = [n for n in nums if 520 <= n <= 600]

            if ac: collected_aden.append(max(set(ac), key=ac.count))
            if sc: collected_sanaa.append(max(set(sc), key=sc.count))
        except: continue

    fa = clean_and_average(collected_aden, forbidden_numbers)
    if fa: rates['aden']['usd'] = fa; rates['aden']['sar'] = int(fa/3.82)
    
    fs = clean_and_average(collected_sanaa, forbidden_numbers)
    if fs: rates['sanaa']['usd'] = fs; rates['sanaa']['sar'] = int(fs/3.78)

    return rates

def calculate_gold_updates(sanaa_usd, aden_usd):
    try:
        gold_ticker = yf.Ticker("GC=F")
        global_ounce = gold_ticker.history(period="1d")['Close'].iloc[-1]
        gram_24_usd = global_ounce / 31.1035
        def get_prices(usd_rate):
            gram_24 = int(gram_24_usd * usd_rate)
            return {"gram_24": int(gram_24/100)*100, "gram_21": int(gram_24*0.875/100)*100, "gunaih": int(gram_24*0.875*8/100)*100}
        return {"global_ounce_usd": round(global_ounce, 2), "sanaa": get_prices(sanaa_usd), "aden": get_prices(aden_usd)}
    except: return None

def send_admin_alert(city, old, new):
    msg = f"🚨 قفزة سعرية في {city}!\nقديم: {old} | جديد: {new}\nراجع الأمر يدوياً."
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except: pass

# ==========================================
# 4. التشغيل الذكي (مع حساب المؤشر Trend) 📈
# ==========================================
try:
    ref = db.reference('/')
    old_data = ref.child('rates').get()
    
    old_sanaa = old_data.get('sanaa', {}).get('usd_buy', 535) if old_data else 535
    old_aden = old_data.get('aden', {}).get('usd_buy', 1630) if old_data else 1630

    market = get_market_rates()
    new_sanaa = market['sanaa']['usd']
    new_aden = market['aden']['usd']
    
    # فحص الأمان
    upd_sanaa = True; upd_aden = True
    if abs(new_sanaa - old_sanaa) > SAFETY_THRESHOLD: send_admin_alert('sanaa', old_sanaa, new_sanaa); upd_sanaa = False; new_sanaa = old_sanaa
    if abs(new_aden - old_aden) > SAFETY_THRESHOLD: send_admin_alert('aden', old_aden, new_aden); upd_aden = False; new_aden = old_aden

    # --- 🧠 حساب المؤشر (Trend Calculation) ---
    # 1 = صعود (ارتفاع السعر) | -1 = هبوط (انخفاض السعر) | 0 = استقرار
    def get_trend(new_p, old_p):
        if new_p > old_p: return 1
        if new_p < old_p: return -1
        return 0

    trend_sanaa = get_trend(new_sanaa, old_sanaa)
    trend_aden = get_trend(new_aden, old_aden)

    gold_data = calculate_gold_updates(new_sanaa, new_aden)
    time_now = (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d %I:%M %p")

    if gold_data:
        updates = {
            "rates/last_update": time_now,
            "gold": gold_data,
            
            # تحديث صنعاء مع المؤشر
            "rates/sanaa/usd_buy": new_sanaa,
            "rates/sanaa/usd_sell": new_sanaa + 4,
            "rates/sanaa/sar_buy": market['sanaa']['sar'] if upd_sanaa else old_data['sanaa']['sar_buy'],
            "rates/sanaa/sar_sell": (market['sanaa']['sar'] + 2) if upd_sanaa else old_data['sanaa']['sar_sell'],
            "rates/sanaa/trend": trend_sanaa, # 👈 الحقل الجديد

            # تحديث عدن مع المؤشر
            "rates/aden/usd_buy": new_aden,
            "rates/aden/usd_sell": new_aden + 15,
            "rates/aden/sar_buy": market['aden']['sar'] if upd_aden else old_data['aden']['sar_buy'],
            "rates/aden/sar_sell": (market['aden']['sar'] + 5) if upd_aden else old_data['aden']['sar_sell'],
            "rates/aden/trend": trend_aden, # 👈 الحقل الجديد
        }

        ref.update(updates)
        print(f"✅ Updated: Sanaa={new_sanaa}({trend_sanaa}) | Aden={new_aden}({trend_aden})")

        # الإشعارات
        if (upd_sanaa and trend_sanaa != 0) or (upd_aden and trend_aden != 0):
            arrow = "🔺" if (new_aden > old_aden) else "🔻"
            msg = messaging.Message(notification=messaging.Notification(title=f"{arrow} تحديث أسعار الصرف", body=f"صنعاء: {new_sanaa} | عدن: {new_aden}"), topic='rates')
            try: messaging.send(msg)
            except: pass

except Exception as e:
    print(f"❌ Error: {e}")