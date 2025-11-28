import firebase_admin
from firebase_admin import credentials, db, messaging
import yfinance as yf
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
import statistics
from datetime import datetime, timedelta
import os
import sys

# ضبط الترميز لويندوز (لحل مشكلة الإيموجي)
sys.stdout.reconfigure(encoding='utf-8')

# ==========================================
# 1. إعدادات الاتصال
# ==========================================
DATABASE_URL = "https://yemen-sarraf-default-rtdb.europe-west1.firebasedatabase.app/" 
KEY_FILE = "service-account.json"
TELEGRAM_BOT_TOKEN = "8583890330:AAFerk3-5YcYeZ95awp9Sf7tBy_Q-djbSZ0" 
TELEGRAM_CHAT_ID = 617150775
SAFETY_THRESHOLD = 50 

try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    key_path = os.path.join(current_dir, KEY_FILE)
    if not firebase_admin._apps:
        cred = credentials.Certificate(key_path)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
except Exception as e:
    print(f"Error Init: {e}")
    exit(1)

# ==========================================
# 2. محرك السحب والتحليل (Async Currencies)
# ==========================================

async def fetch_url(session, url):
    try:
        async with session.get(url, timeout=15) as response:
            if response.status == 200:
                return await response.text()
    except: pass
    return ""

def parse_rates_from_html(html, url_source):
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()
    
    page_data = {
        'sanaa': {'usd': [], 'sar': []},
        'aden': {'usd': [], 'sar': []}
    }

    rows = soup.find_all(['tr', 'div', 'p', 'span']) 
    found_log = [] 

    for row in rows:
        row_text = row.get_text().strip()
        nums = [int(n) for n in re.findall(r'\d{3,4}', row_text)]
        nums = [n for n in nums if n not in list(range(2010, 2031))]
        
        if len(nums) < 1: continue

        currency = None
        if any(x in row_text for x in ['دولار', 'USD', 'أمريكي']): currency = 'usd'
        elif any(x in row_text for x in ['سعودي', 'SAR']): currency = 'sar'
        
        if not currency: continue

        nums.sort()
        buy = nums[0]
        sell = nums[1] if len(nums) >= 2 else 0

        region = None
        if currency == 'usd':
            if 520 <= buy <= 600: region = 'sanaa'
            elif 1600 <= buy <= 2200: region = 'aden'
        elif currency == 'sar':
            if 138 <= buy <= 160: region = 'sanaa'
            elif 400 <= buy <= 580: region = 'aden'

        if region:
            page_data[region][currency].append({'buy': buy, 'sell': sell})
            log_str = f"{region.upper()} {currency.upper()}: {buy}/{sell}"
            if log_str not in found_log: found_log.append(log_str)

    if found_log:
        print(f"   🔹 المصدر: {url_source}")
        print(f"      وجدنا: {', '.join(found_log)}")
    
    return page_data

async def scrape_market_data():
    print("\n🕷️ --- تقرير سحب المواقع ---")
    
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
    
    data_pool = {
        'sanaa': {'usd_buy': [], 'usd_sell': [], 'sar_buy': [], 'sar_sell': []},
        'aden': {'usd_buy': [], 'usd_sell': [], 'sar_buy': [], 'sar_sell': []}
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        tasks = [fetch_url(session, url) for url in sources]
        results = await asyncio.gather(*tasks)

    for url, html in zip(sources, results):
        if not html: continue
        extracted = parse_rates_from_html(html, url)
        
        for region in ['sanaa', 'aden']:
            for curr in ['usd', 'sar']:
                for item in extracted[region][curr]:
                    data_pool[region][f'{curr}_buy'].append(item['buy'])
                    if item['sell'] > item['buy']:
                        data_pool[region][f'{curr}_sell'].append(item['sell'])

    return data_pool

def calculate_final_rate(values_list, label=""):
    if not values_list: 
        print(f"   ⚠️ {label}: لا توجد بيانات.")
        return None
    
    values_list.sort()
    if len(values_list) < 3: 
        avg = int(sum(values_list)/len(values_list))
        print(f"   📊 {label}: {values_list} -> المتوسط: {avg}")
        return avg
    
    mid = len(values_list)//2
    median = values_list[mid]
    clean = [x for x in values_list if median*0.85 <= x <= median*1.15]
    final_val = int(sum(clean)/len(clean)) if clean else int(median)
    
    print(f"   📊 {label}:")
    print(f"      - الكل: {values_list}")
    print(f"      - النتيجة: {final_val}")
    
    return final_val

# ==========================================
# 3. محرك الذهب (Yahoo Finance - GC=F) 🟡
# ==========================================
def get_gold_price_live():
    print("\n🟡 جاري سحب الذهب من Yahoo Finance (GC=F)...")
    try:
        # استخدام yfinance مباشرة للحصول على السعر المرتفع (~4189)
        ticker = yf.Ticker("GC=F")
        data = ticker.history(period="1d", interval="1m")
        
        if not data.empty:
            price = float(data['Close'].iloc[-1])
            print(f"✅ تم السحب بنجاح: {price:,.2f} USD")
            return price
        else:
            print("⚠️ لم يتم استلام بيانات من Yahoo.")
    except Exception as e:
        print(f"⚠️ خطأ في اتصال Yahoo: {e}")

    # سعر احتياطي (آخر سعر ناجح رأيناه)
    print("❌ استخدام السعر الاحتياطي.")
    return 4189.60 

def calculate_gold_updates(sanaa_usd, aden_usd):
    try:
        # 1. الحصول على السعر العالمي المعتمد
        global_ounce = get_gold_price_live()
        
        # 2. حساب الجرامات
        # الأونصة = 31.1035 جرام
        gram_24_usd = global_ounce / 31.1035
        
        def get_prices(usd_rate):
            gram_24 = int(gram_24_usd * usd_rate)
            gram_21 = int((gram_24 * 0.875) / 100) * 100
            gunaih = int((gram_21 * 8) / 100) * 100 
            return {
                "gram_24": int(gram_24/100)*100, 
                "gram_21": gram_21, 
                "gunaih": gunaih
            }

        return {
            "global_ounce_usd": round(global_ounce, 2), 
            "sanaa": get_prices(sanaa_usd), 
            "aden": get_prices(aden_usd)
        }
    except Exception as e: 
        print(f"❌ خطأ في حسابات الذهب: {e}")
        return None

# ==========================================
# 4. التنفيذ الرئيسي
# ==========================================
try:
    # 1. سحب البيانات
    raw_data = asyncio.run(scrape_market_data())
    
    print("\n🧮 --- تقرير الحساب النهائي ---")

    SPREAD_SANAA_USD = 3
    SPREAD_SANAA_SAR = 1
    SPREAD_ADEN_USD = 12
    SPREAD_ADEN_SAR = 4

    def get_rate(region, key, default, name):
        val = calculate_final_rate(raw_data[region][key], name)
        return val if val else default

    # حسابات صنعاء
    new_sanaa_usd_buy = get_rate('sanaa', 'usd_buy', 535, "صنعاء $ شراء")
    new_sanaa_usd_sell = get_rate('sanaa', 'usd_sell', new_sanaa_usd_buy + SPREAD_SANAA_USD, "صنعاء $ بيع")
    if not raw_data['sanaa']['usd_sell']: new_sanaa_usd_sell = new_sanaa_usd_buy + SPREAD_SANAA_USD

    new_sanaa_sar_buy = get_rate('sanaa', 'sar_buy', int(new_sanaa_usd_buy/3.78), "صنعاء SAR شراء")
    new_sanaa_sar_sell = get_rate('sanaa', 'sar_sell', new_sanaa_sar_buy + SPREAD_SANAA_SAR, "صنعاء SAR بيع")
    if not raw_data['sanaa']['sar_sell']: new_sanaa_sar_sell = new_sanaa_sar_buy + SPREAD_SANAA_SAR

    # حسابات عدن
    new_aden_usd_buy = get_rate('aden', 'usd_buy', 1630, "عدن $ شراء")
    new_aden_usd_sell = get_rate('aden', 'usd_sell', new_aden_usd_buy + SPREAD_ADEN_USD, "عدن $ بيع")
    if not raw_data['aden']['usd_sell']: new_aden_usd_sell = new_aden_usd_buy + SPREAD_ADEN_USD

    new_aden_sar_buy = get_rate('aden', 'sar_buy', int(new_aden_usd_buy/3.82), "عدن SAR شراء")
    new_aden_sar_sell = get_rate('aden', 'sar_sell', new_aden_sar_buy + SPREAD_ADEN_SAR, "عدن SAR بيع")
    if not raw_data['aden']['sar_sell']: new_aden_sar_sell = new_aden_sar_buy + SPREAD_ADEN_SAR

    # تصحيح معكوس
    if new_sanaa_usd_sell <= new_sanaa_usd_buy: new_sanaa_usd_sell = new_sanaa_usd_buy + SPREAD_SANAA_USD
    if new_sanaa_sar_sell <= new_sanaa_sar_buy: new_sanaa_sar_sell = new_sanaa_sar_buy + SPREAD_SANAA_SAR
    if new_aden_usd_sell <= new_aden_usd_buy: new_aden_usd_sell = new_aden_usd_buy + SPREAD_ADEN_USD
    if new_aden_sar_sell <= new_aden_sar_buy: new_aden_sar_sell = new_aden_sar_buy + SPREAD_ADEN_SAR

    # جلب القديم للمؤشر (عملات + ذهب)
    ref = db.reference('/')
    old_data = ref.child('rates').get()
    old_gold = ref.child('gold').get() # 👈 جلب بيانات الذهب القديمة

    old_sanaa = old_data.get('sanaa', {}).get('usd_buy', 535) if old_data else 535
    old_aden = old_data.get('aden', {}).get('usd_buy', 1630) if old_data else 1630
    
    # جلب سعر الأونصة القديم
    old_ounce = old_gold.get('global_ounce_usd', 4189) if old_gold else 4189

    # حساب مؤشرات العملات
    trend_sanaa = 1 if new_sanaa_usd_buy > old_sanaa else (-1 if new_sanaa_usd_buy < old_sanaa else 0)
    trend_aden = 1 if new_aden_usd_buy > old_aden else (-1 if new_aden_usd_buy < old_aden else 0)
    
    # حساب الذهب والوقت
    gold_data = calculate_gold_updates(new_sanaa_usd_buy, new_aden_usd_buy)
    time_now = (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d %I:%M %p")

    # التحديث
    if gold_data:
        # 👇 حساب مؤشر الذهب (Gold Trend)
        new_ounce = gold_data['global_ounce_usd']
        gold_trend = 0
        if new_ounce > old_ounce: gold_trend = 1
        elif new_ounce < old_ounce: gold_trend = -1
        
        # إضافة التواريخ والمؤشر للذهب
        gold_data['sanaa']['last_update'] = time_now
        gold_data['sanaa']['trend'] = gold_trend # 👈 مؤشر ذهب صنعاء
        
        gold_data['aden']['last_update'] = time_now
        gold_data['aden']['trend'] = gold_trend  # 👈 مؤشر ذهب عدن

        updates = {
            "rates/last_update": time_now,
            "gold": gold_data,

            "rates/sanaa/usd_buy": new_sanaa_usd_buy,
            "rates/sanaa/usd_sell": new_sanaa_usd_sell,
            "rates/sanaa/sar_buy": new_sanaa_sar_buy,
            "rates/sanaa/sar_sell": new_sanaa_sar_sell,
            "rates/sanaa/trend": trend_sanaa,
            "rates/sanaa/last_update": time_now,

            "rates/aden/usd_buy": new_aden_usd_buy,
            "rates/aden/usd_sell": new_aden_usd_sell,
            "rates/aden/sar_buy": new_aden_sar_buy,
            "rates/aden/sar_sell": new_aden_sar_sell,
            "rates/aden/trend": trend_aden,
            "rates/aden/last_update": time_now,
        }

        ref.update(updates)
        print(f"\n✅ تم التحديث بنجاح! (Gold Trend: {gold_trend})")

        # ==========================================
        # 🆕 7. حفظ السجل التاريخي (History) 📈
        # ==========================================
        # نستخدم التاريخ فقط (بدون الوقت) كمفتاح، لنحفظ سعراً واحداً لكل يوم (سعر الإغلاق)
        today_date = (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d")
        
        history_updates = {
            # سجل صنعاء
            f"history/sanaa/usd/{today_date}": new_sanaa_usd_buy,
            f"history/sanaa/sar/{today_date}": new_sanaa_sar_buy,
            f"history/sanaa/gold21/{today_date}": gold_data['sanaa']['gram_21'],
            
            # سجل عدن
            f"history/aden/usd/{today_date}": new_aden_usd_buy,
            f"history/aden/sar/{today_date}": new_aden_sar_buy,
            f"history/aden/gold21/{today_date}": gold_data['aden']['gram_21'],
        }
        
        # نستخدم update لكي لا نحذف الأيام السابقة
        ref.update(history_updates)
        print(f"📈 تم حفظ سجل الأسعار ليوم: {today_date}")

        # الإشعارات
        if abs(new_aden_usd_buy - old_aden) > 2 or abs(new_sanaa_usd_buy - old_sanaa) > 1:
            arrow = "🔺" if (new_aden_usd_buy > old_aden) else "🔻"
            msg = messaging.Message(
                notification=messaging.Notification(
                    title=f"{arrow} تحديث أسعار الصرف", 
                    body=f"صنعاء: {new_sanaa_usd_buy} | عدن: {new_aden_usd_buy}"
                ), 
                topic='rates'
            )
            try: messaging.send(msg)
            except: pass

except Exception as e:
    print(f"❌ Error: {e}")