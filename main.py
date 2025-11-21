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
        
        "https://ydn.news", # موقع يمن ديلي نيوز (غالباً دقيق)
        "https://www.2dec.net/rate.html",
        "https://www.khbr.me/rate.html",
        "https://yemen-exchange.com/",
        "https://www.aden-tm.net/news/351778",
        "http://yemenief.org/Currency.aspx",
        "https://yemen-press.net/news149396.html",
        "https://yemen-press.net"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    rates = {
        "sanaa": {"usd": 535, "sar": 140},
        "aden": {"usd": 1630, "sar": 430} 
    }

    collected_sanaa = []
    collected_aden = []

    # 1. مرحلة الجمع
    for url in sources:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200: continue

            text_content = BeautifulSoup(response.content, 'html.parser').get_text()
            all_numbers = re.findall(r'\d{3,4}', text_content)
            nums = [int(n) for n in all_numbers]

            # الفلاتر الأولية (النطاق الواسع)
            aden_candidates = [n for n in nums if 1600 <= n <= 2200]
            sanaa_candidates = [n for n in nums if 520 <= n <= 600]

            if aden_candidates:
                # نأخذ الرقم الأكثر تكراراً في الصفحة الواحدة
                val = max(set(aden_candidates), key=aden_candidates.count)
                collected_aden.append(val)
                print(f"   🔹 مصدر ({url}): وجدنا لعدن {val}")

            if sanaa_candidates:
                val = max(set(sanaa_candidates), key=sanaa_candidates.count)
                collected_sanaa.append(val)
                print(f"   🔹 مصدر ({url}): وجدنا لصنعاء {val}")

        except Exception:
            continue

    # 2. مرحلة الفلترة الذكية (Outlier Removal) 🧠
    def clean_and_average(numbers_list):
        if not numbers_list: return None
        if len(numbers_list) < 3: 
            # إذا البيانات قليلة، نأخذ المتوسط مباشرة
            return int(sum(numbers_list) / len(numbers_list))
        
        # حساب الوسيط (Median) لأنه لا يتأثر بالقيم الشاذة
        median = statistics.median(numbers_list)
        
        # نسمح بانحراف 10% فقط عن الوسيط
        threshold = 0.10 
        min_val = median * (1 - threshold)
        max_val = median * (1 + threshold)
        
        # نأخذ فقط الأرقام النظيفة
        clean_nums = [x for x in numbers_list if min_val <= x <= max_val]
        
        # إذا حذفنا كل شيء بالغلط، نرجع للأصل
        if not clean_nums: return int(median)
        
        # نرجع متوسط الأرقام النظيفة
        avg = sum(clean_nums) / len(clean_nums)
        return int(avg)

    print("-" * 30)

    # حساب عدن
    final_aden = clean_and_average(collected_aden)
    if final_aden:
        rates['aden']['usd'] = final_aden
        rates['aden']['sar'] = int(final_aden / 3.82)
        print(f"📊 متوسط عدن (بعد التنظيف): {final_aden}")
        if collected_aden: print(f"   (تم استبعاد القيم الشاذة من: {collected_aden})")
    
    # حساب صنعاء
    final_sanaa = clean_and_average(collected_sanaa)
    if final_sanaa:
        rates['sanaa']['usd'] = final_sanaa
        rates['sanaa']['sar'] = int(final_sanaa / 3.78)
        print(f"📊 متوسط صنعاء (بعد التنظيف): {final_sanaa}")

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