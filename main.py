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
# 2. 🕷️ دالة سحب الأسعار (مع فلتر السنوات القوي)
# ==========================================
def get_market_rates():
    print("🕷️ بدء عملية السحب...")
    
    sources = [
        "https://www.aden-tm.net/news/351778",
        "https://ydn.news", # موقع يمن ديلي نيوز (غالباً دقيق)
        "https://www.2dec.net/rate.html",
        "https://yemen-exchange.com/"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    # القيم الافتراضية (آخر أسعار معروفة تقريباً لتفادي الأصفار)
    rates = {
        "sanaa": {"usd": 538, "sar": 140},
        "aden": {"usd": 2040, "sar": 535} # تحديث القيم الافتراضية لتقارب الواقع
    }

    for url in sources:
        try:
            print(f"Trying source: {url} ...")
            response = requests.get(url, headers=headers, timeout=20)
            if response.status_code != 200: continue

            soup = BeautifulSoup(response.content, 'html.parser')
            
            # نبحث عن جميع صفوف الجداول في الصفحة
            rows = soup.find_all('tr')
            
            found_sanaa = False
            found_aden = False

            for row in rows:
                text = row.get_text(strip=True) # نص الصف كاملاً
                
                # استخراج الأرقام من هذا الصف فقط
                numbers = re.findall(r'\d+', text)
                nums = [int(n) for n in numbers if len(n) >= 3] # نأخذ الأرقام من 3 خانات فأكثر

                if not nums: continue

                # --- تحليل صف صنعاء ---
                # إذا الصف يحتوي على (صنعاء) و (دولار)
                if ("صنعاء" in text or "Sanaa" in text) and ("دولار" in text or "USD" in text):
                    # نبحث عن رقم منطقي لصنعاء (520 - 600)
                    valid = [n for n in nums if 520 <= n <= 600]
                    if valid:
                        rates['sanaa']['usd'] = max(valid) # البيع
                        rates['sanaa']['sar'] = int(rates['sanaa']['usd'] / 3.75)
                        found_sanaa = True
                        print(f"✅ صنعاء (من الجدول): {rates['sanaa']['usd']}")

                # --- تحليل صف عدن ---
                # إذا الصف يحتوي على (عدن) و (دولار)
                elif ("عدن" in text or "Aden" in text) and ("دولار" in text or "USD" in text):
                    # نبحث عن رقم منطقي لعدن (1600 - 3000)
                    valid = [n for n in nums if 1600 <= n <= 3000]
                    if valid:
                        rates['aden']['usd'] = max(valid)
                        rates['aden']['sar'] = int(rates['aden']['usd'] / 3.8)
                        found_aden = True
                        print(f"✅ عدن (من الجدول): {rates['aden']['usd']}")

            # إذا وجدنا البيانات في هذا الموقع، نتوقف ولا داعي لتجربة الموقع التالي
            if found_sanaa and found_aden:
                print("✨ تم العثور على البيانات بدقة!")
                return rates

        except Exception as e:
            print(f"⚠️ تجاوز المصدر بسبب: {e}")
            continue

    return rates

# ==========================================
# 3. محرك الذهب (كما هو)
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