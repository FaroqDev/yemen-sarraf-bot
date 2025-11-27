import firebase_admin
from firebase_admin import credentials, db, messaging
import yfinance as yf
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta

# ==========================================
# 1. إعدادات الاتصال (Config)
# ==========================================
DATABASE_URL = "https://yemen-sarraf-default-rtdb.europe-west1.firebasedatabase.app/" 
KEY_FILE = "service-account.json"
TELEGRAM_BOT_TOKEN = "8583890330:AAFerk3-5YcYeZ95awp9Sf7tBy_Q-djbSZ0" 
TELEGRAM_CHAT_ID = 617150775
SAFETY_THRESHOLD = 50 # رفعنا حد الأمان قليلاً لعدن

try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(KEY_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
except Exception as e:
    print(f"❌ Error Init: {e}")
    exit(1)

# ==========================================
# 2. محرك السحب الذكي (Smart Scraper)
# ==========================================

async def fetch_url(session, url):
    try:
        async with session.get(url, timeout=15) as response:
            if response.status == 200:
                return await response.text()
    except: pass
    return ""

def parse_rates_from_html(html):
    """
    تحليل HTML للبحث عن أزواج أسعار (شراء وبيع) داخل الجداول
    """
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()
    
    # نتائج مؤقتة لهذه الصفحة
    page_data = {
        'sanaa': {'usd': [], 'sar': []},
        'aden': {'usd': [], 'sar': []}
    }

    # 1. تنظيف النص والبحث عن الأرقام العامة (للتصنيف)
    # نستخدم هذا لتحديد هل الصفحة تتحدث عن صنعاء أم عدن بشكل عام
    all_nums = [int(n) for n in re.findall(r'\d{3,4}', text)]
    has_sanaa_range = any(520 <= n <= 600 for n in all_nums)
    has_aden_range = any(1600 <= n <= 2200 for n in all_nums)

    # 2. البحث الذكي داخل سطور الجداول
    rows = soup.find_all(['tr', 'div', 'p']) # نبحث في الأماكن المحتملة
    
    for row in rows:
        row_text = row.get_text().strip()
        # استخراج الأرقام من السطر
        nums = [int(n) for n in re.findall(r'\d{3,4}', row_text)]
        nums = [n for n in nums if n not in list(range(2010, 2031))] # استبعاد التواريخ
        
        if len(nums) < 1: continue

        # تحديد العملة
        currency = None
        if 'دولار' in row_text or 'USD' in row_text or 'أمريكي' in row_text:
            currency = 'usd'
        elif 'سعودي' in row_text or 'SAR' in row_text:
            currency = 'sar'
        
        if not currency: continue

        # تحليل الأرقام (شراء/بيع)
        # عادة الرقم الأصغر شراء، والأكبر بيع
        nums.sort()
        
        buy = nums[0]
        sell = nums[1] if len(nums) >= 2 else 0 # إذا وجد رقم واحد فقط

        # تصنيف المنطقة بناءً على قيمة السعر
        region = None
        if currency == 'usd':
            if 520 <= buy <= 600: region = 'sanaa'
            elif 1600 <= buy <= 2200: region = 'aden'
        elif currency == 'sar':
            if 138 <= buy <= 160: region = 'sanaa'
            elif 400 <= buy <= 580: region = 'aden'

        # الحفظ
        if region:
            page_data[region][currency].append({'buy': buy, 'sell': sell})

    return page_data

async def scrape_market_data():
    print("🕷️ بدء السحب المتوازي وتحليل البيع/الشراء...")
    
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
    
    # مصفوفات التجميع
    data_pool = {
        'sanaa': {'usd_buy': [], 'usd_sell': [], 'sar_buy': [], 'sar_sell': []},
        'aden': {'usd_buy': [], 'usd_sell': [], 'sar_buy': [], 'sar_sell': []}
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        tasks = [fetch_url(session, url) for url in sources]
        results = await asyncio.gather(*tasks)

    for html in results:
        if not html: continue
        extracted = parse_rates_from_html(html)
        
        for region in ['sanaa', 'aden']:
            for curr in ['usd', 'sar']:
                for item in extracted[region][curr]:
                    # إضافة سعر الشراء
                    data_pool[region][f'{curr}_buy'].append(item['buy'])
                    # إضافة سعر البيع (فقط إذا كان موجوداً ومنطقياً)
                    if item['sell'] > item['buy']:
                        data_pool[region][f'{curr}_sell'].append(item['sell'])

    return data_pool

def calculate_final_rate(values_list):
    """حساب المتوسط النظيف لقائمة أرقام"""
    if not values_list: return None
    if len(values_list) < 3: return int(sum(values_list)/len(values_list))
    
    values_list.sort()
    mid = len(values_list)//2
    median = values_list[mid]
    
    # تنظيف القيم الشاذة
    clean = [x for x in values_list if median*0.85 <= x <= median*1.15]
    return int(sum(clean)/len(clean)) if clean else int(median)

# ==========================================
# 3. محرك الذهب (كما هو)
# ==========================================
def get_gold_price_live():
    # ... (نفس كود الذهب السابق، لم يتغير) ...
    try:
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://goldprice.org/'}
        r = requests.get("https://data-asg.goldprice.org/dbXRates/USD", headers=headers, timeout=5)
        if r.status_code == 200: return float(r.json()['items'][0]['xauPrice'])
    except: pass
    
    try:
        ticker = yf.Ticker("GC=F")
        return float(ticker.history(period="1d")['Close'].iloc[-1])
    except: return 2715.0

def calculate_gold_updates(sanaa_usd, aden_usd):
    # ... (نفس الدالة السابقة) ...
    try:
        global_ounce = get_gold_price_live()
        gram_24_usd = global_ounce / 31.1035
        def get_prices(usd_rate):
            gram_24 = int(gram_24_usd * usd_rate)
            return {"gram_24": int(gram_24/100)*100, "gram_21": int(gram_24*0.875/100)*100, "gunaih": int(gram_24*0.875*8/100)*100}
        return {"global_ounce_usd": round(global_ounce, 2), "sanaa": get_prices(sanaa_usd), "aden": get_prices(aden_usd)}
    except: return None

# ==========================================
# 4. التنفيذ الرئيسي
# ==========================================
try:
    # 1. سحب البيانات الخام
    raw_data = asyncio.run(scrape_market_data())
    
    # 2. القيم الافتراضية (للحماية من الفشل)
    # ملاحظة: فارق الصرف الافتراضي (Spread)
    SPREAD_SANAA_USD = 3
    SPREAD_SANAA_SAR = 1
    SPREAD_ADEN_USD = 12
    SPREAD_ADEN_SAR = 4

    # 3. حساب المتوسطات النهائية
    def get_rate_or_default(region, key, default_val):
        val = calculate_final_rate(raw_data[region][key])
        return val if val else default_val

    # --- صنعاء ---
    new_sanaa_usd_buy = get_rate_or_default('sanaa', 'usd_buy', 535)
    # محاولة سحب البيع، إذا فشل نستخدم (الشراء + الفارق)
    new_sanaa_usd_sell = get_rate_or_default('sanaa', 'usd_sell', new_sanaa_usd_buy + SPREAD_SANAA_USD)
    
    new_sanaa_sar_buy = get_rate_or_default('sanaa', 'sar_buy', int(new_sanaa_usd_buy/3.78))
    new_sanaa_sar_sell = get_rate_or_default('sanaa', 'sar_sell', new_sanaa_sar_buy + SPREAD_SANAA_SAR)

    # --- عدن ---
    new_aden_usd_buy = get_rate_or_default('aden', 'usd_buy', 1630)
    new_aden_usd_sell = get_rate_or_default('aden', 'usd_sell', new_aden_usd_buy + SPREAD_ADEN_USD)
    
    new_aden_sar_buy = get_rate_or_default('aden', 'sar_buy', int(new_aden_usd_buy/3.82))
    new_aden_sar_sell = get_rate_or_default('aden', 'sar_sell', new_aden_sar_buy + SPREAD_ADEN_SAR)

    # 4. جلب القديم للمقارنة
    ref = db.reference('/')
    old_data = ref.child('rates').get()
    old_sanaa = old_data.get('sanaa', {}).get('usd_buy', 535) if old_data else 535
    old_aden = old_data.get('aden', {}).get('usd_buy', 1630) if old_data else 1630

    # 5. حساب المؤشر والذهب والوقت
    trend_sanaa = 1 if new_sanaa_usd_buy > old_sanaa else (-1 if new_sanaa_usd_buy < old_sanaa else 0)
    trend_aden = 1 if new_aden_usd_buy > old_aden else (-1 if new_aden_usd_buy < old_aden else 0)
    
    gold_data = calculate_gold_updates(new_sanaa_usd_buy, new_aden_usd_buy)
    time_now = (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d %I:%M %p")

    # 6. التحديث
    if gold_data:
        # إضافة التواريخ للذهب
        gold_data['sanaa']['last_update'] = time_now
        gold_data['aden']['last_update'] = time_now

        updates = {
            "rates/last_update": time_now,
            "gold": gold_data,

            # صنعاء
            "rates/sanaa/usd_buy": new_sanaa_usd_buy,
            "rates/sanaa/usd_sell": new_sanaa_usd_sell,
            "rates/sanaa/sar_buy": new_sanaa_sar_buy,
            "rates/sanaa/sar_sell": new_sanaa_sar_sell,
            "rates/sanaa/trend": trend_sanaa,
            "rates/sanaa/last_update": time_now,

            # عدن
            "rates/aden/usd_buy": new_aden_usd_buy,
            "rates/aden/usd_sell": new_aden_usd_sell,
            "rates/aden/sar_buy": new_aden_sar_buy,
            "rates/aden/sar_sell": new_aden_sar_sell,
            "rates/aden/trend": trend_aden,
            "rates/aden/last_update": time_now,
        }

        ref.update(updates)
        print(f"✅ تم التحديث: صنعاء (شراء {new_sanaa_usd_buy}/بيع {new_sanaa_usd_sell}) | عدن (شراء {new_aden_usd_buy}/بيع {new_aden_usd_sell})")

        # 7. الإشعارات
        if abs(new_aden_usd_buy - old_aden) > 2 or abs(new_sanaa_usd_buy - old_sanaa) > 1:
            arrow = "🔺" if (new_aden_usd_buy > old_aden) else "🔻"
            msg = messaging.Message(
                notification=messaging.Notification(
                    title=f"{arrow} تحديث أسعار الصرف", 
                    body=f"صنعاء: {new_sanaa_usd_buy} - {new_sanaa_usd_sell}\nعدن: {new_aden_usd_buy} - {new_aden_usd_sell}"
                ), 
                topic='rates'
            )
            try: messaging.send(msg)
            except: pass

except Exception as e:
    print(f"❌ Error: {e}")