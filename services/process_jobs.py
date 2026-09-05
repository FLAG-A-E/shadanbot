import json
from config import GEMINI_API_KEY
from services.gemini_client import generate_json
from services.scraper import fetch_public_channel_posts, CHANNELS

def extract_jobs_from_batch(posts_batch, system_instruction):
    if not posts_batch:
        return []

    prompt_content = "إليك مجموعة من المنشورات. استخرج الوظائف المتاحة فقط منها وصنفها على شكل JSON Array احترافي:\n\n"
    for idx, post in enumerate(posts_batch):
        prompt_content += f"--- منشور {idx+1} ({post['channel']} | {post['date']}) ---\n{post['text']}\n\n"

    result = generate_json(prompt_content, system_instruction, temperature=0.2)
    return result if isinstance(result, list) else []

def extract_job_details(posts, batch_size=10):
    if not posts:
        return []
    if not GEMINI_API_KEY:
        print("لم يتم ضبط GEMINI_API_KEY.")
        return []

    system_instruction = """
    أنت مساعد متخصص في تحليل إعلانات الوظائف.
    قم بمراجعة المنشورات واستخراج الوظائف الفعلية فقط (تجاهل الإعلانات التجارية غير الوظيفية).
    قم بإرجاع النتيجة بصيغة JSON حصرية تحتوي على قائمة الأغراض التالية:
    [
      {
        "job_title": "المسمى الوظيفي",
        "company": "اسم الشركة أو الجهة أو غير متاح",
        "location": "المحافظة أو المنطقة",
        "requirements": "ملخص الشروط والمهارات المطلوبة",
        "contact": "رقم الهاتف، المعرف، أو الإيميل للتواصل",
        "channel": "اسم القناة المصدر",
        "date": "تاريخ المنشور"
      }
    ]
    إذا لم تجد وظيفة في المنشور، لا تدرجه في النتيجة.
    """

    all_jobs = []
    # تقسيم المنشورات إلى دفعات بحجم 10 منشورات بكل دفعة
    total_posts = len(posts)
    for i in range(0, total_posts, batch_size):
        batch = posts[i:i + batch_size]
        print(f"جاري معالجة الدفعة ({i // batch_size + 1} من {-(total_posts // -batch_size)})...")
        batch_jobs = extract_jobs_from_batch(batch, system_instruction)
        all_jobs.extend(batch_jobs)

    return all_jobs

if __name__ == '__main__':
    print("1. جاري جلب المنشورات من تليجرام...")
    all_posts = []
    for ch in CHANNELS:
        posts = fetch_public_channel_posts(ch, days=3)
        all_posts.extend(posts)

    print(f"تم جلب {len(all_posts)} منشور. 2. جاري تحليل الوظائف على دفعات سريعة...")
    
    extracted_jobs = extract_job_details(all_posts, batch_size=10)
    
    print(f"\n--- تم استخراج {len(extracted_jobs)} وظيفة بنجاح! ---")
    print(json.dumps(extracted_jobs, ensure_ascii=False, indent=2))
