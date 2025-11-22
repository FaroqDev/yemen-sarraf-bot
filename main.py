import firebase_admin
from firebase_admin import credentials, db, messaging # 👈 أضفنا messaging
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




# تهيئة الاتصال داخل try لضمان عدم الانهيار في البداية
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(KEY_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
except Exception as e:
    print(f"❌ خطأ في الاتصال: {e}")
    exit(1)

# ==========================================
# 2. دوال السحب (كما هي)
# ==========================================
def calculate_median(lst):
    n = len(lst)
    if n < 1: return 0
    s_lst = sorted(lst)
    if n % 2 == 1:
        return s_lst[n//2]
    else:
        return (s_lst[n//2 - 1] + s_lst[n//2]) / 2.0

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
            text_content = BeautifulSoup(response.content, 'html.parser').get_text()
            nums = [int(n) for n in re.findall(r'\d{3,4}', text_content)]
            
            aden_candidates = [n for n in nums if 1600 <= n <= 2200 and n not in forbidden_numbers]
            sanaa_candidates = [n for n in nums if 520 <= n <= 600]

            if aden_candidates: collected_aden.append(max(set(aden_candidates), key=aden_candidates.count))
            if sanaa_candidates: collected_sanaa.append(max(set(sanaa_candidates), key=sanaa_candidates.count))
        except: continue

    def clean_list(numbers_list):
        numbers_list = [n for n in numbers_list if n not in forbidden_numbers]
        if not numbers_list: return None
        if len(numbers_list) < 3: return int(sum(numbers_list) / len(numbers_list))
        median = calculate_median(numbers_list)
        clean_nums = [x for x in numbers_list if median * 0.85 <= x <= median * 1.15]
        if not clean_nums: return int(median)
        return int(sum(clean_nums) / len(clean_nums))

    final_aden = clean_list(collected_aden)
    if final_aden:
        rates['aden']['usd'] = final_aden
        rates['aden']['sar'] = int(final_aden / 3.82)
    
    final_sanaa = clean_list(collected_sanaa)
    if final_sanaa:
        rates['sanaa']['usd'] = final_sanaa
        rates['sanaa']['sar'] = int(final_sanaa / 3.78)

    return rates

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
    except: return None

# ==========================================
# 4. التشغيل والإشعارات 🔔
# ==========================================
try:
    # 1. جلب السعر القديم من القاعدة (للمقارنة)
    ref = db.reference('/')
    old_data = ref.child('rates').get()
    
    old_sanaa = 0
    old_aden = 0
    
    if old_data:
        old_sanaa = old_data.get('sanaa', {}).get('usd_buy', 0)
        old_aden = old_data.get('aden', {}).get('usd_buy', 0)

    # 2. جلب السعر الجديد
    market_data = get_market_rates()
    new_sanaa = market_data['sanaa']['usd']
    new_aden = market_data['aden']['usd']
    
    gold_data = calculate_gold_updates(new_sanaa, new_aden)
    yemen_time = datetime.utcnow() + timedelta(hours=3)
    formatted_time = yemen_time.strftime("%Y-%m-%d %I:%M %p")

    if gold_data:
        updates = {
            "rates/sanaa/usd_buy": new_sanaa,
            "rates/sanaa/usd_sell": new_sanaa + 4,
            "rates/sanaa/sar_buy": market_data['sanaa']['sar'],
            "rates/sanaa/sar_sell": market_data['sanaa']['sar'] + 2,

            "rates/aden/usd_buy": new_aden,
            "rates/aden/usd_sell": new_aden + 15,
            "rates/aden/sar_buy": market_data['aden']['sar'],
            "rates/aden/sar_sell": market_data['aden']['sar'] + 5,
            
            "rates/last_update": formatted_time,
            "gold": gold_data
        }
        
        ref.update(updates)
        print("✅ Data Updated!")

        # 3. منطق الإشعار 🔔
        # نرسل إشعاراً فقط إذا تغير السعر بأكثر من 2 ريال
        change_sanaa = abs(new_sanaa - old_sanaa)
        change_aden = abs(new_aden - old_aden)

        if change_sanaa > 2 or change_aden > 2:
            print("🔔 Price changed! Sending Notification...")
            
            # تحديد اتجاه السهم
            arrow = "🔺" if (new_aden > old_aden) else "🔻"
            if new_aden == old_aden: arrow = "➖"

            message = messaging.Message(
                notification=messaging.Notification(
                    title=f"{arrow} تحديث أسعار الصرف",
                    body=f"صنعاء: {new_sanaa} ريال | عدن: {new_aden} ريال"
                ),
                topic='rates', # إرسال لكل المشتركين
            )
            response = messaging.send(message)
            print('Successfully sent message:', response)
        else:
            print("🔕 No significant change, skipping notification.")

except Exception as e:
    print(f"❌ Error: {e}")