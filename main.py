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
# 2. 🕷️ دالة سحب الأسعار (متعددة المصادر)
# ==========================================
def get_market_rates():
    print("🕷️ بدء عملية السحب...")
    
    # قائمة مصادر (إذا فشل الأول نجرب الثاني)
    sources = [
        #"https://www.2dec.net/rate.html",
        "http://yemenief.org/Currency.aspx",
        "https://ydn.news/"
    ]
    
    # تمويه الروبوت (كأنه متصفح كروم حقيقي)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'ar-SA,ar;q=0.9,en;q=0.8',
        'Referer': 'https://www.google.com/'
    }

    rates = {
        "sanaa": {"usd": 535, "sar": 140}, # قيم احتياطية
        "aden": {"usd": 1660, "sar": 435}
    }

    for url in sources:
        try:
            print(f"Trying source: {url} ...")
            response = requests.get(url, headers=headers, timeout=20)
            
            if response.status_code != 200:
                print(f"❌ المصدر رفض الاتصال: {response.status_code}")
                continue # جرب الموقع التالي

            soup = BeautifulSoup(response.content, 'html.parser')
            text_content = soup.get_text()
            
            # البحث عن الأنماط (Regex)
            # دولار عدن (1500-2500)
            aden_matches = re.findall(r'(1[5-9]\d{2}|2\d{3})', text_content)
            # دولار صنعاء (520-600)
            sanaa_matches = re.findall(r'(5[2-6]\d)', text_content)
            
            found = False
            
            if aden_matches:
                nums = [int(x) for x in aden_matches]
                # نأخذ الرقم الأكثر تكراراً أو المنطقي
                valid_aden = [n for n in nums if 1500 < n < 3000]
                if valid_aden:
                    # نأخذ الوسيط أو الأكبر لضمان أنه سعر البيع
                    rates['aden']['usd'] = max(valid_aden)
                    rates['aden']['sar'] = int(rates['aden']['usd'] / 3.8) 
                    found = True
                    print(f"✅ تم التقاط سعر عدن: {rates['aden']['usd']}")

            if sanaa_matches:
                nums = [int(x) for x in sanaa_matches]
                valid_sanaa = [n for n in nums if 520 < n < 600]
                if valid_sanaa:
                    rates['sanaa']['usd'] = max(valid_sanaa)
                    rates['sanaa']['sar'] = int(rates['sanaa']['usd'] / 3.78)
                    found = True
                    print(f"✅ تم التقاط سعر صنعاء: {rates['sanaa']['usd']}")

            if found:
                print("✨ نجح السحب!")
                return rates # نخرج من الدالة فوراً لأننا وجدنا بيانات

        except Exception as e:
            print(f"⚠️ فشل مع هذا المصدر: {e}")
            continue # جرب اللي بعده

    print("❌ فشلت كل المصادر، سيتم استخدام القيم الاحتياطية.")
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
    except Exception as e:
        print(f"Error Gold: {e}")
        return None

# ==========================================
# 4. التنفيذ
# ==========================================

# 1. السحب
market_data = get_market_rates()
sanaa_usd = market_data['sanaa']['usd']
aden_usd = market_data['aden']['usd']

# 2. الذهب
gold_data = calculate_gold_updates(sanaa_usd, aden_usd)

# 3. الوقت
yemen_time = datetime.utcnow() + timedelta(hours=3)
formatted_time = yemen_time.strftime("%Y-%m-%d %I:%M %p")

# 4. الرفع
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

    print(f"🚀 جاري التحديث: صنعاء={sanaa_usd} | عدن={aden_usd}")
    ref = db.reference('/')
    ref.update(updates)
    print("DONE")