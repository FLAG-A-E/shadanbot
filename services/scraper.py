import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

# قائمة القنوات العامة (بدون @)
CHANNELS = [
    'forsaaIQ',  # ضع اسم القناة العامة هنا
    'YSPjobs',  # ضع اسم القناة العامة هنا
    'engahmad88',
    'DNAIRAQ',
    'teenwdiefhoom',
    'jobs_wasit',
    'baghdadjobss',
    'medical_job_ads',
    'repiraq',
    'KarbalaJobs',
    'alazawi_jobs',
    'NAJAF_iraqn',
    'najafjobsiq',
    'wadaeefnajaf',
    'mhm123naba',
    'a56s4',
    'wazfnyi',
    'babilcom2',
    'Muhannad_job',
    'thekhana',
    'basra_job',
    'jobbbs',
    'vacancies_training',
    'basrajobs',
    'basrahvacancies',
    'iraq_careers',
    'EAT_2030',
    'jobs_iraq1',
    'iraqi_jobss',
    'mahdi1992lawer',
    'jobs_for_us',
]

def fetch_public_channel_posts(channel_name, days=3):
    url = f"https://t.me/s/{channel_name}"
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; ShadanJobScraper/1.0)"},
        timeout=20,
    )
    
    if response.status_code != 200:
        print(f"فشل الاتصال بالقناة: {channel_name}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    messages = soup.find_all('div', class_='tgme_widget_message')
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    fetched_posts = []

    for msg in messages:
        # استخراج تاريخ المنشور
        time_tag = msg.find('time', class_='time')
        if not time_tag or not time_tag.get('datetime'):
            continue
            
        post_date = datetime.fromisoformat(time_tag['datetime'].replace('Z', '+00:00'))
        
        # التصفية لآخر 3 أيام فقط
        if post_date < cutoff_date:
            continue

        # استخراج نص المنشور
        text_div = msg.find('div', class_='tgme_widget_message_text')
        if text_div:
            text = text_div.get_text(separator="\n").strip()
            fetched_posts.append({
                'channel': f"@{channel_name}",
                'date': post_date.strftime('%Y-%m-%d %H:%M:%S'),
                'text': text
            })

    return fetched_posts

if __name__ == '__main__':
    all_posts = []
    for ch in CHANNELS:
        print(f"جاري جلب المنشورات من @{ch}...")
        posts = fetch_public_channel_posts(ch, days=3)
        all_posts.extend(posts)

    print(f"\nتم جلب {len(all_posts)} منشور من آخر 3 أيام بنجاح!")
    if all_posts:
        print("\nعينة من أول منشور:")
        print(all_posts[0]['text'][:200])
