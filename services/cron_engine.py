import json
import time
import hashlib
import threading
import sys
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apscheduler.schedulers.blocking import BlockingScheduler
from config import GEMINI_API_KEY
from database.connection import DatabaseError, get_connection
from database.db import init_db
from services.gemini_client import generate_json
from services.scraper import fetch_public_channel_posts, CHANNELS
from services.notifications import notify_subscribed_users

# --- 1. إعداد قاعدة البيانات ---
def init_db():
    from database.db import init_db as init_shared_db
    init_shared_db()

# توليد بصمة فريدة لكل منشور لمنع التكرار
def generate_post_hash(text, channel):
    raw_str = f"{channel}_{text.strip()}"
    return hashlib.md5(raw_str.encode('utf-8')).hexdigest()

# التحقق مما إذا كان المنشور مخزناً سابقاً
def is_post_exists(post_hash):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM jobs WHERE post_hash = ?", (post_hash,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

# --- 2. دالة تحليل Gemini ---
def process_new_posts_with_gemini(posts):
    if not posts:
        return []
    if not GEMINI_API_KEY:
        print("لم يتم ضبط GEMINI_API_KEY، تم تخطي التحليل الذكي.")
        return []

    system_instruction = """
    أنت مساعد متخصص في تحليل إعلانات الوظائف.
    قم بمراجعة المنشورات واستخراج الوظائف الفعلية فقط (تجاهل الإعلانات التجارية غير الوظيفية).
    قم بإرجاع النتيجة بصيغة JSON Array حصرية تحتوي على العناصر التالية:
    [
      {
        "job_title": "المسمى الوظيفي",
        "company": "اسم الشركة أو غير متاح",
        "location": "المحافظة أو المنطقة",
        "requirements": "ملخص الشروط",
        "contact": "رقم الهاتف أو المعرف أو الإيميل",
        "channel": "اسم القناة",
                "date": "تاريخ المنشور",
                "source_post": 1
      }
    ]
        أعد source_post برقم المنشور الذي استخرجت منه الوظيفة، ولا تخترع وظيفة من منشور غير وظيفي.
    """

    prompt_content = "استخرج الوظائف من المنشورات التالية:\n\n"
    for idx, post in enumerate(posts):
        prompt_content += f"--- منشور {idx+1} ({post['channel']}) ---\n{post['text']}\n\n"

    result = generate_json(prompt_content, system_instruction, temperature=0.2)
    return result if isinstance(result, list) else []

# --- 3. حفظ الوظائف وتنظيف القديم ---
def save_jobs_and_cleanup(jobs_data, posts_map):
    conn = get_connection()
    cursor = conn.cursor()
    saved_count = 0

    for job in jobs_data:
        # ربط الوظيفة ببصمة المنشور الأصلية
        post_hash = job.get('post_hash', '')
        job_title = str(job.get('job_title', '')).strip()
        if not post_hash or len(job_title) < 3 or job_title in {'.', '-', 'غير محدد'}:
            continue
        
        try:
            cursor.execute('''
                INSERT INTO jobs (post_hash, job_title, company, location, requirements, contact_info, channel, raw_text, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                post_hash,
                job_title,
                job.get('company', 'غير متاح'),
                job.get('location', 'غير محدد'),
                job.get('requirements', ''),
                job.get('contact', ''),
                job.get('channel', ''),
                posts_map.get(post_hash, {}).get('text', ''),
                datetime.now()
            ))
            saved_count += 1
        except DatabaseError.IntegrityError:
            pass # المنشور مكرر

    # **حذف الوظائف التي مر عليها أكثر من 3 أيام (72 ساعة)**
    three_days_ago = datetime.now() - timedelta(days=3)
    cursor.execute("DELETE FROM jobs WHERE created_at < ?", (three_days_ago,))
    deleted_count = cursor.rowcount

    conn.commit()
    conn.close()
    print(f" تم حفظ {saved_count} وظيفة جديدة. تم تنظيف {deleted_count} وظيفة قديمة.")

# --- 4. المهمة المجدولة (ساعة بساعة) ---
def hourly_job_sync():
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] بدء جولة الكشط والتحديث الدوري...")
    
    # 1. جلب المنشورات من التليجرام
    raw_posts = []
    for ch in CHANNELS:
        try:
            posts = fetch_public_channel_posts(ch, days=3) # جلب منشورات آخر 3 أيام
            raw_posts.extend(posts)
        except Exception as error:
            print(f"فشل جلب القناة @{ch}: {error}")

    # 2. تصفية المنشورات الجديدة فقط لم تفرز من قبل
    new_posts = []
    posts_map = {}
    
    for p in raw_posts:
        p_hash = generate_post_hash(p['text'], p['channel'])
        if not is_post_exists(p_hash):
            p['post_hash'] = p_hash
            new_posts.append(p)
            posts_map[p_hash] = p

    print(f"إجمالي المنشورات المجلوبة: {len(raw_posts)} | المنشورات الجديدة فعلياً: {len(new_posts)}")

    if not new_posts:
        print("لا توجد منشورات جديدة لمعالجتها.")
        save_jobs_and_cleanup([], {})
        return

    # 3. معالجة المنشورات الجديدة على دفعات بحجم 10
    batch_size = 10
    all_extracted_jobs = []
    
    for i in range(0, len(new_posts), batch_size):
        batch = new_posts[i:i + batch_size]
        extracted = process_new_posts_with_gemini(batch)
        
        # ربط الوظيفة بالمنشور المصدر الذي حدده Gemini.
        for job in extracted:
            try:
                source_index = int(job.get('source_post')) - 1
            except (TypeError, ValueError):
                source_index = -1
            if 0 <= source_index < len(batch):
                source_post = batch[source_index]
                job['post_hash'] = source_post['post_hash']
                job['channel'] = source_post['channel']
                job['raw_text'] = source_post['text']
        
        all_extracted_jobs.extend(extracted)

    # 4. حفظ البيانات وتنظيف الأرشيف القديم
    save_jobs_and_cleanup(all_extracted_jobs, posts_map)
    notify_subscribed_users(all_extracted_jobs)


def start_background_scraper():
    scraper_thread = threading.Thread(target=_run_scraper_loop, daemon=True)
    scraper_thread.start()
    return scraper_thread


def _run_scraper_loop():
    init_db()
    hourly_job_sync()
    scheduler = BlockingScheduler()
    scheduler.add_job(hourly_job_sync, 'interval', hours=1)
    scheduler.start()

# --- 5. تشغيل المحرك ---
if __name__ == '__main__':
    print("\n المحرك السحابي يعمل الآن تلقائياً (سيتم التحديث كل 60 دقيقة)... اضغط Ctrl+C للإيقاف.")
    try:
        _run_scraper_loop()
    except (KeyboardInterrupt, SystemExit):
        print("تم إيقاف المحرك.")
