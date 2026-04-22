import asyncio, re
from typing import Optional
from datetime import datetime
from playwright.async_api import async_playwright

AI_ROLE_KEYWORDS = ["machine learning","ml engineer","applied scientist","llm","ai engineer",
    "data scientist","nlp","computer vision","deep learning","ai product","data platform",
    "mlops","model","inference","vector","embedding"]
ENGINEERING_KEYWORDS = ["engineer","developer","architect","devops","sre","platform","backend",
    "frontend","fullstack","data","infra","cloud","python","go","java"]
STACK_KEYWORDS = {
    "python": ["python","django","fastapi","flask"],
    "go": ["golang","go "],
    "data": ["spark","dbt","snowflake","databricks","airflow","kafka"],
    "ml": ["pytorch","tensorflow","ray","vllm","weights & biases","wandb","mlflow"],
    "infra": ["kubernetes","terraform","aws","gcp","azure","docker"],
}

async def scrape_jobs(company_name: str, careers_url: Optional[str] = None) -> dict:
    result = {"company": company_name, "scraped_at": datetime.utcnow().isoformat(),
        "total_open_roles": 0, "ai_roles": 0, "engineering_roles": 0,
        "detected_stack": [], "raw_titles": [], "source_url": careers_url or "", "error": None}
    slug = company_name.lower().replace(" ", "-")
    urls_to_try = []
    if careers_url:
        urls_to_try.append(careers_url)
    urls_to_try += [f"https://www.builtin.com/company/{slug}/jobs", f"https://wellfound.com/company/{slug}/jobs"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(extra_http_headers={"Accept-Language": "en-US,en;q=0.9"})
        for url in urls_to_try[:2]:
            try:
                await page.goto(url, timeout=15000, wait_until="domcontentloaded")
                await asyncio.sleep(2)
                text = await page.inner_text("body")
                titles = _extract_titles(text)
                if titles:
                    result["raw_titles"] = titles[:30]
                    result["total_open_roles"] = len(titles)
                    result["ai_roles"] = sum(1 for t in titles if any(k in t.lower() for k in AI_ROLE_KEYWORDS))
                    result["engineering_roles"] = sum(1 for t in titles if any(k in t.lower() for k in ENGINEERING_KEYWORDS))
                    result["detected_stack"] = _detect_stack(text)
                    result["source_url"] = url
                    break
            except Exception as e:
                result["error"] = str(e)
                continue
        await browser.close()
    return result

def _extract_titles(text):
    lines = [l.strip() for l in text.split("\n") if 20 < len(l.strip()) < 120]
    role_words = ENGINEERING_KEYWORDS + AI_ROLE_KEYWORDS + ["manager","director","lead"]
    return [l for l in lines if any(w in l.lower() for w in role_words)][:100]

def _detect_stack(text):
    text_lower = text.lower()
    return [cat for cat, kws in STACK_KEYWORDS.items() if any(k in text_lower for k in kws)]

def scrape_jobs_sync(company_name: str, careers_url: Optional[str] = None) -> dict:
    return asyncio.run(scrape_jobs(company_name, careers_url))
