import yfinance as yf
import sys

# 👇 هذا السطر هو الحل (يضبط الترميز ليدعم الإيموجي والعربية في ويندوز)
sys.stdout.reconfigure(encoding='utf-8')

def test_yahoo_gold():
    print("🟡 جاري الاتصال بـ Yahoo Finance (GC=F)...")
    
    try:
        # الرمز الموجود في صورتك
        ticker = yf.Ticker("GC=F")
        
        # سحب بيانات اليوم
        data = ticker.history(period="1d")
        
        if not data.empty:
            # نأخذ آخر سعر تم تسجيله (Close للآخر دقيقة)
            price = float(data['Close'].iloc[-1])
            print(f"✅ السعر المستلم: {price:,.2f} USD")
            
            if price > 4000:
                print("👍 النتيجة: مطابق للصورة!")
            else:
                print("🤔 النتيجة: السعر مختلف.")
        else:
            print("❌ لم يتم استلام بيانات.")
            
    except Exception as e:
        print(f"❌ حدث خطأ: {e}")

if __name__ == "__main__":
    test_yahoo_gold()