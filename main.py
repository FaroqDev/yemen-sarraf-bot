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
TELEGRAM_CHAT_ID = 617150775شغ

# 🛡️ حد الأمان (أي تغيير أكبر من هذا الرقم يعتبر خطراً)
SAFETY_THRESHOLD = 20



# تهيئة الاتصال داخل try لضمان عدم الانهيار في البداية
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(KEY_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
except Exception as e:
    print(f"❌ خطأ في الاتصال: {e}")
    exit(1)

# ==========================================
# 2. دوال مساعدة (إحصاء وتنظيف)
# ==========================================
def calculate_median(lst):
    n = len(lst)
    if n < 1: return 0
    s_lst = sorted(lst)
    if n % 2 == 1:
        return s_lst[n//2]
    else:
        return (s_lst[n//2 - 1] + s_lst[n//2]) / 2.0

def clean_and_average(numbers_list, forbidden_list):
    # 1. حذف السنوات والأرقام المحظورة
    numbers_list = [n for n in numbers_list if n not in forbidden_list]
    
    if not numbers_list: return None
    if len(numbers_list) < 3: 
        return int(sum(numbers_list) / len(numbers_list))
    
    # 2. حذف القيم الشاذة (Outliers)
    median = calculate_median(numbers_list)
    threshold = 0.15 # سماحية 15%
    min_val = median * (1 - threshold)
    max_val = median * (1 + threshold)
    
    clean_nums = [x for x in numbers_list if min_val <= x <= max_val]
    
    if not clean_nums: return int(median)
    return int(sum(clean_nums) / len(clean_nums))

# ==========================================
# 3. 🕷️ دالة السحب الذكية
# ==========================================
def get_market_rates():
    print("🕷️ بدء عملية السحب والتحليل...")
    
    sources = [
        "https://economiyemen.net/", "https://ydn.news",
        "https://yemen-exchange.com/", "https://www.2dec.net/rate.html",
        "https://khobaraa.net/section/20", "https://www.aden-tm.net/news/351778",
        "http://yemenief.org/Currency.aspx", "https://yemen-press.net"
    ]
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    # قيم افتراضية للطوارئ
    rates = {"sanaa": {"usd": 535, "sar": 140}, "aden": {"usd": 1630, "sar": 430}}
    
    collected_sanaa = []
    collected_aden = []
    
    # 🚫 قائمة السنوات المحظورة (لتجنب الخلط مع السعر)
    forbidden_numbers = list(range(2010, 2031))

    for url in sources:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200: continue

            text_content = BeautifulSoup(response.content, 'html.parser').get_text()
            nums = [int(n) for n in re.findall(r'\d{3,4}', text_content)]

            # فلتر النطاق السعري
            aden_candidates = [n for n in nums if 1600 <= n <= 2200]
            sanaa_candidates = [n for n in nums if 520 <= n <= 600]

            if aden_candidates:
                # نأخذ الرقم الأكثر تكراراً في الصفحة
                val = max(set(aden_candidates), key=aden_candidates.count)
                collected_aden.append(val)

            if sanaa_candidates:
                val = max(set(sanaa_candidates), key=sanaa_candidates.count)
                collected_sanaa.append(val)
        except: continue

    # حساب المتوسطات النهائية
    final_aden = clean_and_average(collected_aden, forbidden_numbers)
    if final_aden:
        rates['aden']['usd'] = final_aden
        rates['aden']['sar'] = int(final_aden / 3.82)
    
    final_sanaa = clean_and_average(collected_sanaa, forbidden_numbers)
    if final_sanaa:
        rates['sanaa']['usd'] = final_sanaa
        rates['sanaa']['sar'] = int(final_sanaa / 3.78)

    return rates

# ==========================================
# 4. محرك الذهب
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
    except: return None

# ==========================================
# 5. 🚨 دالة إرسال التحذير للمدير
# ==========================================
def send_admin_alert(city, old_price, new_price):
    diff = new_price - old_price
    emoji = "📈" if diff > 0 else "📉"
    
    sell_margin = 4 if city == 'sanaa' else 15
    # نرسل الأمر جاهزاً للنسخ
    approval_command = f"`/update {city} usd {new_price} {new_price + sell_margin}`"
    
    message = (
        f"🚨 **نظام الأمان أوقف التحديث التلقائي!**\n\n"
        f"المدينة: {city.upper()}\n"
        f"السعر القديم: {old_price}\n"
        f"السعر الجديد: {new_price} {emoji}\n"
        f"الفرق: {abs(diff)} ريال (أكبر من {SAFETY_THRESHOLD})\n\n"
        f"إذا كان السعر صحيحاً، انسخ الأمر أدناه وأرسله للبوت:\n"
        f"{approval_command}"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})
        print(f"⚠️ تم إرسال تحذير للمدير بخصوص {city}")
    except Exception as e:
        print(f"فشل إرسال التحذير: {e}")

# ==========================================
# 6. التشغيل الرئيسي (Main Logic)
# ==========================================
try:
    # 1. جلب البيانات القديمة للمقارنة
    ref = db.reference('/')
    old_data = ref.child('rates').get()
    
    old_sanaa = old_data.get('sanaa', {}).get('usd_buy', 535) if old_data else 535
    old_aden = old_data.get('aden', {}).get('usd_buy', 1630) if old_data else 1630

    # 2. السحب الجديد
    market_data = get_market_rates()
    new_sanaa = market_data['sanaa']['usd']
    new_aden = market_data['aden']['usd']
    
    # 3. 🛡️ فحص الأمان (Safety Check)
    update_sanaa = True
    update_aden = True
    
    # فحص صنعاء
    if abs(new_sanaa - old_sanaa) > SAFETY_THRESHOLD:
        send_admin_alert('sanaa', old_sanaa, new_sanaa)
        update_sanaa = False 
        new_sanaa = old_sanaa 

    # فحص عدن
    if abs(new_aden - old_aden) > SAFETY_THRESHOLD:
        send_admin_alert('aden', old_aden, new_aden)
        update_aden = False 
        new_aden = old_aden 

    # 4. التحديث
    gold_data = calculate_gold_updates(new_sanaa, new_aden)
    yemen_time = datetime.utcnow() + timedelta(hours=3)
    formatted_time = yemen_time.strftime("%Y-%m-%d %I:%M %p")

    if gold_data:
        updates = {
            "rates/sanaa/usd_buy": new_sanaa,
            "rates/sanaa/usd_sell": new_sanaa + 4,
            # نحدث السعودي فقط إذا كان تحديث الدولار آمناً، وإلا نبقي القديم
            "rates/sanaa/sar_buy": market_data['sanaa']['sar'] if update_sanaa else old_data['sanaa']['sar_buy'],
            "rates/sanaa/sar_sell": (market_data['sanaa']['sar'] + 2) if update_sanaa else old_data['sanaa']['sar_sell'],

            "rates/aden/usd_buy": new_aden,
            "rates/aden/usd_sell": new_aden + 15,
            "rates/aden/sar_buy": market_data['aden']['sar'] if update_aden else old_data['aden']['sar_buy'],
            "rates/aden/sar_sell": (market_data['aden']['sar'] + 5) if update_aden else old_data['aden']['sar_sell'],
            
            "rates/last_update": formatted_time,
            "gold": gold_data
        }

        ref.update(updates)
        print(f"✅ حالة التحديث: صنعاء={update_sanaa} | عدن={update_aden}")

        # 5. إرسال إشعار للمستخدمين (فقط إذا تم التحديث الفعلي)
        should_notify = False
        
        # شرط الإشعار: التغيير أكبر من 2 ريال (تجنب الإزعاج) وأقل من حد الأمان (تم قبوله)
        if update_sanaa and abs(new_sanaa - old_sanaa) > 2: should_notify = True
        if update_aden and abs(new_aden - old_aden) > 2: should_notify = True

        if should_notify:
            print("🔔 إرسال إشعار للمستخدمين...")
            arrow = "🔺" if (new_aden > old_aden) else "🔻"
            if new_aden == old_aden: arrow = "➖"

            message = messaging.Message(
                notification=messaging.Notification(
                    title=f"{arrow} تحديث أسعار الصرف",
                    body=f"صنعاء: {new_sanaa} ريال | عدن: {new_aden} ريال"
                ),
                topic='rates',
            )
            try:
                messaging.send(message)
            except: pass
        else:
            print("🔕 لم يتم إرسال إشعار (لا يوجد تغيير يستحق).")

except Exception as e:
    print(f"❌ خطأ: {e}")