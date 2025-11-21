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
# 2. 🕷️ دالة سحب الأسعار من السوق (Scraper)
# ==========================================
def get_market_rates():
    print("🕷️ جاري سحب الأسعار من المصدر...")
    
    # رابط المصدر (موقع خبراء - قسم الأسعار)
    url = "https://khobaraa.net/section/20" 
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # نبحث عن الجداول في الصفحة
        tables = soup.find_all('table')
        
        # قيم افتراضية (للحماية في حال فشل السحب)
        rates = {
            "sanaa": {"usd": 535, "sar": 140}, # قيم تقريبية للطوارئ
            "aden": {"usd": 1650, "sar": 430}
        }
        
        found_new_data = False

        # البحث الذكي داخل النصوص
        text_content = soup.get_text()
        
        # استخراج كل الأرقام من الصفحة لتحليلها
        # نبحث عن نمط الأسعار الشائعة حالياً
        # دولار عدن (بين 1500 و 2500)
        aden_usd_matches = re.findall(r'(1[5-9]\d{2}|2\d{3})', text_content)
        # دولار صنعاء (بين 520 و 560)
        sanaa_usd_matches = re.findall(r'(5[2-6]\d)', text_content)
        
        # تحليل النتائج (نأخذ الرقم الأكثر تكراراً أو الأول)
        if aden_usd_matches:
            # تحويل النصوص لأرقام
            nums = [int(x) for x in aden_usd_matches]
            # نأخذ متوسط منطقي (أو أكبر رقم وجدناه كافتراض آمن)
            detected_aden_usd = max(nums) 
            if 1500 < detected_aden_usd < 3000:
                rates['aden']['usd'] = detected_aden_usd
                rates['aden']['sar'] = int(detected_aden_usd / 3.8) # حساب تقريبي للسعودي إذا لم نجده
                found_new_data = True
                print(f"✅ تم اكتشاف سعر عدن: {detected_aden_usd}")

        if sanaa_usd_matches:
            nums = [int(x) for x in sanaa_usd_matches]
            detected_sanaa_usd = max(nums) # عادة السعر الأعلى هو البيع
            if 520 < detected_sanaa_usd < 600:
                rates['sanaa']['usd'] = detected_sanaa_usd
                rates['sanaa']['sar'] = int(detected_sanaa_usd / 3.78)
                found_new_data = True
                print(f"✅ تم اكتشاف سعر صنعاء: {detected_sanaa_usd}")

        if not found_new_data:
            print("⚠️ لم يتم العثور على أرقام واضحة، سيتم استخدام القيم الاحتياطية.")

        return rates

    except Exception as e:
        print(f"❌ خطأ في السحب: {e}")
        # نرجع قيماً افتراضية حتى لا يتوقف النظام
        return {
            "sanaa": {"usd": 535, "sar": 140},
            "aden": {"usd": 1660, "sar": 435}
        }

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
# 4. التنفيذ الرئيسي
# ==========================================

# 1. جلب الأسعار من الموقع
market_data = get_market_rates()

sanaa_usd_buy = market_data['sanaa']['usd']
aden_usd_buy = market_data['aden']['usd']

# 2. حساب الذهب بناءً على الأسعار المسحوبة
gold_data = calculate_gold_updates(sanaa_usd_buy, aden_usd_buy)

# 3. تجهيز الوقت (اليمن)
yemen_time = datetime.utcnow() + timedelta(hours=3)
formatted_time = yemen_time.strftime("%Y-%m-%d %I:%M %p")

# 4. الرفع
if gold_data:
    updates = {
        "rates/sanaa/usd_buy": sanaa_usd_buy,
        "rates/sanaa/usd_sell": sanaa_usd_buy + 4, # هامش ربح تقديري
        "rates/sanaa/sar_buy": market_data['sanaa']['sar'],
        "rates/sanaa/sar_sell": market_data['sanaa']['sar'] + 2,

        "rates/aden/usd_buy": aden_usd_buy,
        "rates/aden/usd_sell": aden_usd_buy + 15, # هامش عدن أكبر عادة
        "rates/aden/sar_buy": market_data['aden']['sar'],
        "rates/aden/sar_sell": market_data['aden']['sar'] + 5,
        
        "rates/last_update": formatted_time,
        "gold": gold_data
    }

    print(f"🚀 تحديث البيانات: صنعاء={sanaa_usd_buy}, عدن={aden_usd_buy}")
    ref = db.reference('/')
    ref.update(updates)
    print("✅ تم التحديث بنجاح!")