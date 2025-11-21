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
KEY_FILE = "service-account.json"




# تهيئة الاتصال داخل try لضمان عدم الانهيار في البداية
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(KEY_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
except Exception as e:
    print(f"❌ خطأ في الاتصال: {e}")
    exit(1)

# ==========================================
# 2. 🕷️ دالة السحب والتحليل (مع فلتر السنوات الصارم)
# ==========================================
def get_market_rates():
    print("🕷️ بدء عملية جمع البيانات والفلترة...")
    
    sources = [
        "https://economiyemen.net/", 
        "https://ydn.news",
        "https://yemen-exchange.com/",
        "https://www.2dec.net/rate.html",
        "https://khobaraa.net/section/20",
        "https://www.aden-tm.net/news/351778",
        "http://yemenief.org/Currency.aspx",
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
    
    # 🚫 القائمة السوداء (أرقام ممنوعة تماماً)
    # هذه الأرقام تمثل السنوات الحالية والسابقة التي تظهر في حقوق النشر
    forbidden_numbers = [2022, 2023, 2024, 2025, 2026]

    # 1. مرحلة الجمع
    for url in sources:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200: continue

            text_content = BeautifulSoup(response.content, 'html.parser').get_text()
            all_numbers = re.findall(r'\d{3,4}', text_content)
            nums = [int(n) for n in all_numbers]

            # --- الفلاتر ---
            
            # عدن: بين 1600 و 2200 (مع استبعاد السنوات)
            aden_candidates = [
                n for n in nums 
                if 1600 <= n <= 2200 
                and n not in forbidden_numbers # 👈 الفلتر الحاسم
            ]
            
            # صنعاء: بين 520 و 600
            sanaa_candidates = [n for n in nums if 520 <= n <= 600]

            if aden_candidates:
                # نأخذ الرقم الأكثر تكراراً
                val = max(set(aden_candidates), key=aden_candidates.count)
                collected_aden.append(val)
                print(f"   ✅ مصدر ({url}): وجدنا لعدن {val}")

            if sanaa_candidates:
                val = max(set(sanaa_candidates), key=sanaa_candidates.count)
                collected_sanaa.append(val)
                print(f"   ✅ مصدر ({url}): وجدنا لصنعاء {val}")

        except Exception:
            continue

    # 2. مرحلة الفلترة الذكية (Outlier Removal)
    # حساب الوسيط يدوياً لتفادي أخطاء المكتبات
    def calculate_median(lst):
        n = len(lst)
        if n < 1: return 0
        s_lst = sorted(lst)
        if n % 2 == 1:
            return s_lst[n//2]
        else:
            return (s_lst[n//2 - 1] + s_lst[n//2]) / 2.0

    def clean_and_average(numbers_list):
        if not numbers_list: return None
        
        # تنظيف القائمة مرة أخرى من السنوات (زيادة تأكيد)
        numbers_list = [n for n in numbers_list if n not in forbidden_numbers]
        
        if not numbers_list: return None
        if len(numbers_list) < 3: 
            return int(sum(numbers_list) / len(numbers_list))
        
        median = calculate_median(numbers_list)
        
        threshold = 0.15 
        min_val = median * (1 - threshold)
        max_val = median * (1 + threshold)
        
        clean_nums = [x for x in numbers_list if min_val <= x <= max_val]
        
        if not clean_nums: return int(median)
        return int(sum(clean_nums) / len(clean_nums))

    print("-" * 30)

    final_aden = clean_and_average(collected_aden)
    if final_aden:
        rates['aden']['usd'] = final_aden
        rates['aden']['sar'] = int(final_aden / 3.82)
        print(f"📊 متوسط عدن المعتمد (بدون سنوات): {final_aden}")
    
    final_sanaa = clean_and_average(collected_sanaa)
    if final_sanaa:
        rates['sanaa']['usd'] = final_sanaa
        rates['sanaa']['sar'] = int(final_sanaa / 3.78)
        print(f"📊 متوسط صنعاء المعتمد: {final_sanaa}")

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
        print(f"⚠️ خطأ الذهب: {e}")
        return None

# ==========================================
# 4. التشغيل
# ==========================================
try:
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
        print("✅ DONE Successfully!")

except Exception as e:
    print(f"❌ خطأ قاتل: {e}")