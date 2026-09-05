import requests
import logging

from config import BOT_USERNAME, PUBLIC_BASE_URL, QI_API_KEY, QI_BASE_URL, QI_MERCHANT_ID

def create_superqi_invoice(user_id: int, amount: int, order_type: str, order_id: str) -> str:
    """
    تنشئ فاتورة دفع إلكترونية وترجع رابط يفتح تطبيق SuperQi مباشرة للمستخدم.
    - order_type: 'alerts', 'cv', 'portfolio', 'job_single', 'job_monthly'
    """
    logging.info("SuperQi payment gateway is disabled; local payment verification is required.")
    return None

    endpoint = f"{QI_BASE_URL}/payments/create"

    if not QI_MERCHANT_ID or not QI_API_KEY:
        logging.warning("SuperQi credentials are not configured.")
        return None
    
    headers = {
        "Authorization": f"Bearer {QI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # المعرف الفريد للطلب داخل نظامك
    merchant_order_ref = f"{order_type}_{order_id}_{user_id}"

    payload = {
        "merchantId": QI_MERCHANT_ID,
        "amount": amount,                      # المبلغ بالدينار العراقي (1000، 5000، إلخ)
        "currency": "IQD",
        "orderId": merchant_order_ref,
        "description": f"شَدان - تسديد رسوم {order_type} (طلب #{order_id})",
        "webhookUrl": f"{PUBLIC_BASE_URL}/webhook/superqi",
        "redirectUrl": f"https://t.me/{BOT_USERNAME}"
    }

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=10)
        data = response.json()
        
        # التأكد من استجابة السيرفر وتوليد الرابط
        if response.status_code in [200, 201] and data.get("success"):
            return data.get("paymentUrl") or data.get("url")
        else:
            logging.error(f"خطأ في إنشاء فاتورة SuperQi: {data}")
            return None
    except Exception as e:
        logging.error(f"فشل الاتصال بـ API SuperQi: {e}")
        return None
