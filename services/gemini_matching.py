import json
import logging

from services.gemini_client import generate_json


def extract_search_keywords(query):
    result = generate_json(
        f"طلب المستخدم: {query}",
        "استخرج كلمات البحث المهمة من طلب بحث عن وظيفة. أعد JSON حصرياً بالشكل "
        '{"keywords": ["كلمة1", "كلمة2"]}. لا تضف شرحاً.',
        temperature=0.1,
    )
    return [str(keyword).strip() for keyword in result.get("keywords", []) if str(keyword).strip()] if isinstance(result, dict) else []


def score_jobs_for_profile(profile, jobs):
    if not jobs:
        return {}

    profile_text = json.dumps(profile, ensure_ascii=False)
    jobs_text = json.dumps(
        [
            {
                "id": job["id"],
                "job_title": job.get("job_title"),
                "location": job.get("location"),
                "requirements": job.get("requirements"),
                "raw_text": job.get("raw_text"),
            }
            for job in jobs
        ],
        ensure_ascii=False,
    )

    try:
        payload = generate_json(
            f"ملف الباحث: {profile_text}\nالوظائف: {jobs_text}",
            _matching_instruction(),
            temperature=0.1,
        )
        results = payload if isinstance(payload, list) else payload.get("matches", [])
        return {
            int(item["id"]): max(0, min(100, int(item["score"])))
            for item in results
            if "id" in item and "score" in item and item.get("relevant", True)
        }
    except Exception as error:
        logging.warning("تعذر تقييم الوظائف عبر Gemini: %s", error)
        return {}


def _matching_instruction():
    return (
        "أنت محرك مطابقة وظائف عربي صارم. لا تعتمد على تطابق كلمة واحدة فقط، بل افهم "
        "المجال المهني والمهام والمتطلبات. ميّز بين المختبرات الطبية والتحاليل الطبية "
        "وبين المختبرات البيئية وتحليل التربة والزراعة والمياه. إذا كان ملف الباحث طبيًا، "
        "فلا تعتبر وظيفة بيئية مناسبة لمجرد وجود كلمة مختبر أو تحليل. افهم أيضًا أن "
        "تقني مختبر وتقني تحليلات قد تكون وظائف طبية إذا دعمتها كلمات مثل مرضى، عينات، "
        "تحاليل مرضية، أحياء، كيمياء سريرية أو مستشفى. أعد JSON حصريًا بالشكل "
        '[{"id": 1, "score": 85, "relevant": true, "reason": "سبب مختصر"}]. '
        "الدرجة: 0-100. اجعل relevant=false والدرجة أقل من 40 إذا اختلف التخصص أو "
        "كانت الوظيفة في محافظة لا تناسب المستخدم، إلا إذا كانت عن بعد أو كل المحافظات. "
        "قارن الراتب المعروض بالحد الأدنى الذي يطلبه المستخدم إذا كان الراتب مذكورًا؛ "
        "واجعل relevant=false إذا كان أقل بوضوح. لا ترسل وظيفة لمجرد أنها وظيفة عامة. "
        "يجب أن تتطابق الوظيفة مع اختصاص المستخدم أو مسماه أو المجالات المقبولة، مع "
        "مراعاة المنطقة والراتب قبل رفع الدرجة."
    )


def score_jobs_for_search(query, jobs):
    if not jobs:
        return {}

    jobs_text = json.dumps(
        [
            {
                "id": job["id"],
                "job_title": job.get("job_title"),
                "company": job.get("company"),
                "location": job.get("location"),
                "requirements": job.get("requirements"),
                "raw_text": job.get("raw_text"),
            }
            for job in jobs
        ],
        ensure_ascii=False,
    )
    try:
        payload = generate_json(
            f"طلب البحث: {query}\nالوظائف المرشحة: {jobs_text}",
            _matching_instruction(),
            temperature=0.1,
        )
        results = payload if isinstance(payload, list) else payload.get("matches", [])
        return {
            int(item["id"]): {
                "score": max(0, min(100, int(item["score"]))),
                "relevant": bool(item.get("relevant", True)),
                "reason": str(item.get("reason", "")),
            }
            for item in results
            if "id" in item and "score" in item
        }
    except Exception as error:
        logging.warning("تعذر تقييم نتائج البحث عبر Gemini: %s", error)
        return {}
