import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta


# ==========================================
# 1. إعدادات الاتصال (Config)
# ==========================================

# ⚠️ هام: ضع رابط قاعدة البيانات الخاص بك هنا
DATABASE_URL = "https://yemen-sarraf-default-rtdb.europe-west1.firebasedatabase.app/" 

# اسم ملف المفتاح الذي حملته
KEY_FILE = "service-account.json"

# تهيئة فايربيز
if not firebase_admin._apps:
    cred = credentials.Certificate(KEY_FILE)
    firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})

# ==========================================
# 2. 🕷️ دالة سحب الأسعار (الذكية)
# ==========================================
def get_market_rates():
    print("🕷️ بدء عملية السحب...")
    
    # قائمة مصادر قوية
    sources = [
        "https://ydn.news",
        "https://www.2dec.net/rate.html", # المصدر الذي نجح معك
        "https://economiyemen.net/",
        "https://yemen-exchange.com/"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    rates = {
        "sanaa": {"usd": 535, "sar": 140},
        "aden": {"usd": 1660, "sar": 435}
    }
    
    current_year = datetime.now().year # 2025

    for url in sources:
        try:
            print(f"Trying source: {url} ...")
            response = requests.get(url, headers=headers, timeout=20)
            
            if response.status_code != 200: continue

            soup = BeautifulSoup(response.content, 'html.parser')
            text_content = soup.get_text()
            
            # البحث عن الأرقام
            all_numbers = re.findall(r'\d+', text_content)
            nums = [int(x) for x in all_numbers]

            # --- 🧠 الفلتر الذكي (Anti-Year Logic) ---
            
            # 1. فلتر عدن: (بين 1500 و 3000) ويجب ألا يكون سنة (2024, 2025)
            valid_aden = [
                n for n in nums 
                if 1500 < n < 3000 
                and n != current_year 
                and n != current_year - 1
            ]
            
            # 2. فلتر صنعاء: (بين 520 و 600)
            valid_sanaa = [n for n in nums if 520 < n < 600]
            
            found = False
            
            if valid_aden:
                # نأخذ الأكبر (لأنه عادة سعر البيع)، والآن لن يأخذ 2025
                real_aden_price = max(valid_aden)
                rates['aden']['usd'] = real_aden_price
                rates['aden']['sar'] = int(real_aden_price / 3.8)
                found = True
                print(f"✅ تم التقاط سعر عدن الصحيح: {real_aden_price}")

            if valid_sanaa:
                real_sanaa_price = max(valid_sanaa)
                rates['sanaa']['usd'] = real_sanaa_price
                rates['sanaa']['sar'] = int(real_sanaa_price / 3.78)
                found = True
                print(f"✅ تم التقاط سعر صنعاء: {real_sanaa_price}")

            if found:
                print("✨ نجح السحب وبيانات منطقية!")
                return rates

        except Exception as e:
            print(f"⚠️ خطأ مع {url}: {e}")
            continue

    return rates

# ==========================================
# 3. محرك الذهب
# ==========================================
def calculate_gold_updates(sanaa_usd, aden_usd):
    try:
        gold_ticker = yf.Ticker("GC=F")
        global_ounce = gold_ticker.history(period="1d")['Close'].iloc[-1]
        gram_24_usd = global_ounce / 31.1035
        
        def get_prices(usd_rate):
            gram_24 = int(gram_24_usd * usd_rate)
            gram_21 = int((gram_24 * 0.875) / 100) * 100
            gunaih = int((gram_21 * 8) / 100) * 100 
            return {"gram_24": int(gram_24/100)*100, "gram_21": gram_21, "gunaih": gunaih}

        return {
            "global_ounce_usd": round(global_ounce, 2),
            "sanaa": get_prices(sanaa_usd),
            "aden": get_prices(aden_usd)
        }
    except Exception:
        return None

# ==========================================
# 4. التنفيذ
# ==========================================
market_data = get_market_rates()
sanaa_usd = market_data['sanaa']['usd']
aden_usd = market_data['aden']['usd']

gold_data = calculate_gold_updates(sanaa_usd, aden_usd)

# توقيت اليمن
yemen_time = datetime.utcnow() + timedelta(hours=3)
formatted_time = yemen_time.strftime("%Y-%m-%d %I:%M %p")

if gold_data:
    updates = {
        "rates/sanaa/usd_buy": sanaa_usd,
        "rates/sanaa/usd_sell": sanaa_usd + 4,
        "rates/sanaa/sar_buy": market_data['sanaa']['sar'],
        "rates/sanaa/sar_sell": market_data['sanaa']['sar'] + 2,

        "rates/aden/usd_buy": aden_usd,
        "rates/aden/usd_sell": aden_usd + 15,
        "rates/aden/sar_buy": market_data['aden']['sar'],
        "rates/aden/sar_sell": market_data['aden']['sar'] + 5,
        
        "rates/last_update": formatted_time,
        "gold": gold_data
    }

    print(f"🚀 التحديث النهائي: صنعاء={sanaa_usd} | عدن={aden_usd}")
    ref = db.reference('/')
    ref.update(updates)
    print("DONE")