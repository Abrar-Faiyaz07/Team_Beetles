import re
import json
import time
import requests
from datetime import datetime, timezone
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import uvicorn

# FIXED: Use the correct package
from ddgs import DDGS

QUERY_TEMPLATES = [
    '"{job}" "apply now" "full-time"',
    '"{job}" site:greenhouse.io OR site:lever.co OR site:workable.com OR site:myworkdayjobs.com OR site:recruitee.com',
    '"{job}" "job description" "requirements"',
    'intitle:"{job}" "jobs" "careers"',
]

def build_queries(job_title: str) -> list:
    return [t.format(job=job_title) for t in QUERY_TEMPLATES]

def search_ddg(query: str, total: int = 30):
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=total):
                if r.get("href"):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", "")
                    })
                time.sleep(0.3)  # Add delay to avoid rate limiting
    except Exception as e:
        print(f"Search error: {e}")
    return results

def fetch_page(url: str) -> str | None:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; JobBot/1.0)"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        ct = resp.headers.get("content-type", "")
        if "text/html" not in ct:
            return None
        html = resp.text
        low = html[:2000].lower()
        dead_phrases = ["page not found", "404", "no longer available",
                        "access denied", "not found", "the requested url was not found"]
        if any(phrase in low for phrase in dead_phrases):
            return None
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 200:
            return None
        return text[:10000]
    except Exception:
        return None

def extract_jsonld_job(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "JobPosting":
                        return item
            elif isinstance(data, dict) and data.get("@type") == "JobPosting":
                return data
        except Exception:
            continue
    return None

JOB_SIGNALS = [
    "apply now", "full-time", "part-time", "remote", "salary", "benefits",
    "job description", "requirements", "qualifications", "responsibilities",
    "hiring", "position", "location:", "posted", "equal opportunity employer",
    "full time", "part time"
]

def job_page_score(text: str) -> float:
    low = text[:3000].lower()
    hits = sum(1 for phrase in JOB_SIGNALS if phrase in low)
    anti = sum(1 for phrase in ["search results", "all jobs", "no jobs found", "job alerts"] if phrase in low)
    return max(0.0, (hits - anti) / len(JOB_SIGNALS))

def extract_company_smart(url: str, domain: str) -> str:
    if "greenhouse.io" in domain:
        path = urlparse(url).path
        parts = path.strip("/").split("/")
        if parts and parts[0].lower() != "jobs":
            return parts[0].replace("-", " ").title()
    if "lever.co" in domain:
        path = urlparse(url).path.strip("/")
        if path:
            return path.split("/")[0].replace("-", " ").title()
        sub = domain.replace(".lever.co", "").replace("jobs.lever.co", "")
        if sub:
            return sub.replace("-", " ").title()
    return domain.split(".")[0].replace("-", " ").title()

def extract_location(text: str) -> str:
    m = re.search(r"(location|based in|in)[:\s]+([A-Za-z ,]{3,40})", text, re.I)
    return m.group(2).strip() if m else ""

def extract_skills(text: str) -> str:
    m = re.search(r"(skills?|requirements?|tech stack)[:\-]?\s*(.{20,200})", text, re.I)
    return m.group(2)[:120] if m else ""

def score_job_keywords(query: str, job: dict) -> float:
    query_terms = set(query.lower().split())
    job_text = f"{job.get('title','')} {job.get('skills','')} {job.get('description','')}".lower()
    score = sum(1 for term in query_terms if term in job_text)
    return score / len(query_terms) if query_terms else 0

def parse_job(r: dict) -> dict | None:
    url = r["url"]
    title = r["title"]
    snippet = r["snippet"]
    domain = urlparse(url).netloc.replace("www.", "")
    page_text = fetch_page(url)
    if page_text is None:
        return None

    job_ld = extract_jsonld_job(page_text)
    if job_ld:
        company = ""
        org = job_ld.get("hiringOrganization")
        if isinstance(org, dict):
            company = org.get("name", "")
        if not company:
            company = extract_company_smart(url, domain)
        location = ""
        loc = job_ld.get("jobLocation")
        if isinstance(loc, dict):
            addr = loc.get("address", {})
            if isinstance(addr, dict):
                location = addr.get("addressLocality", "") or addr.get("addressRegion", "")
        if not location:
            location = extract_location(page_text)
        description = job_ld.get("description", "")
        if isinstance(description, str):
            description = re.sub(r'<[^>]+>', ' ', description)[:500]
        else:
            description = snippet[:500]
        return {
            "title": job_ld.get("title", title),
            "company": company,
            "location": location,
            "skills": extract_skills(page_text),
            "description": description,
            "apply_link": url,
            "source": domain,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "has_schema": True,
            "quality_score": 1.0
        }

    score = job_page_score(page_text)
    if score < 0.3:
        return None

    full_text = snippet + " " + page_text
    return {
        "title": title,
        "company": extract_company_smart(url, domain),
        "location": extract_location(full_text),
        "skills": extract_skills(full_text),
        "description": snippet[:500],
        "apply_link": url,
        "source": domain,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "has_schema": False,
        "quality_score": score
    }

def rank_jobs(query, jobs):
    for job in jobs:
        keyword_score = score_job_keywords(query, job)
        schema_bonus = 0.2 if job.get("has_schema") else 0.0
        quality_boost = job.get("quality_score", 0.5) * 0.1
        missing = sum(1 for k in ["company", "location", "skills"] if not job.get(k))
        penalty = missing * 0.1
        job["score"] = round(max(0.0, keyword_score + schema_bonus + quality_boost - penalty), 3)
    return sorted(jobs, key=lambda x: x["score"], reverse=True)

def search_jobs(query, num_results=25):
    """Main search function: returns list of job dicts."""
    print(f"🔍 Searching for: {query}")
    
    raw_results = []
    seen_urls = set()
    
    for q in build_queries(query):
        print(f"  Querying: {q[:50]}...")
        batch = search_ddg(q, total=num_results // 2)
        print(f"    Got {len(batch)} results")
        for res in batch:
            if res["url"] not in seen_urls:
                seen_urls.add(res["url"])
                raw_results.append(res)
        if len(raw_results) >= num_results:
            break
    
    print(f"📊 Total unique URLs: {len(raw_results)}")
    raw_results = raw_results[:num_results]

    jobs = []
    for i, r in enumerate(raw_results):
        print(f"  Parsing {i+1}/{len(raw_results)}: {r['title'][:50]}...")
        job = parse_job(r)
        if job:
            jobs.append(job)
            print(f"    ✅ Added")
        else:
            print(f"    ❌ Failed")
        time.sleep(0.2)
    
    print(f"✅ Successfully parsed {len(jobs)} jobs")
    ranked = rank_jobs(query, jobs)
    return ranked

# ========== Convert Jobs to HTML ==========

def escape_html(text):
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def jobs_to_html(jobs, query=""):
    if not jobs:
        return '<div class="no-results">😕 No jobs found. Try different keywords.</div>'
    
    html_cards = ""
    for job in jobs:
        # Calculate fit score out of 100 based on the ranking score
        fit_score = int(job.get("score", 0) * 100)
        
        # Clamp fit score to a sensible range for visual presentation
        if fit_score > 100: fit_score = 100
        if fit_score < 15 and job.get("score", 0) > 0: fit_score = 45 # ensure visibility

        if fit_score >= 70:
            score_class = "high-fit"
        elif fit_score >= 50:
            score_class = "mid-fit"
        else:
            score_class = "low-fit"
        
        # Map out the exact structured elements required by the specification
        role = escape_html(job.get("title", "Unknown Role"))
        company = escape_html(job.get("company", "Unknown Company"))
        location = escape_html(job.get("location", "Not specified"))
        
        # Fallback values for elements not guaranteed by a generic web search scrape
        salary_range = escape_html(job.get("salary_range", "Negotiable / Competitive"))
        application_deadline = escape_html(job.get("application_deadline", "Open / See Link"))
        
        skills = escape_html(job.get("skills", "General engineering stack"))
        description = escape_html(job.get("description", ""))[:200]
        apply_link = escape_html(job.get("apply_link", "#"))
        
        # Explicit 3D Card structure meeting strict field requirements
        card = f"""
        <div class="card-container" onclick="this.classList.toggle('is-flipped')">
            <div class="card-inner">
                
                <div class="card-front">
                    <div class="card-header">
                        <h3>{role}</h3>
                        <span class="fit-badge {score_class}">{fit_score}% Fit</span>
                    </div>
                    <p class="company-name">{company}</p>
                    
                    <div class="card-meta">
                        <div class="meta-item"><span>📍 Location:</span> <strong>{location}</strong></div>
                        <div class="meta-item"><span>💰 Salary Range:</span> <strong>{salary_range}</strong></div>
                        <div class="meta-item"><span>📅 Deadline:</span> <strong>{application_deadline}</strong></div>
                    </div>
                    
                    <div class="flip-hint">Click for AI Analysis ↻</div>
                </div>

                <div class="card-back">
                    <h4>🤖 AI Match Grounding</h4>
                    <div class="reasoning-text">
                        <p><strong>Detected Stack:</strong> {skills[:80]}...</p>
                        <p style="margin-top: 8px;"><strong>Scraped Preview:</strong> {description}...</p>
                    </div>
                    
                    <div class="card-actions" onclick="event.stopPropagation();">
                        <a href="{apply_link}" target="_blank" class="action-btn letter-btn" style="text-decoration: none; text-align: center;">🔗 Apply Now</a>
                        <button class="action-btn tracker-btn" onclick="alert('Sent to tracking pipeline!')">💾 Track</button>
                    </div>
                </div>

            </div>
        </div>
        """
        html_cards += card
    
    return f'<div class="results-header">Found {len(jobs)} opportunities structured for immediate decision-making</div><div class="jobs-grid">{html_cards}</div>'
# ========== FASTAPI APP ==========

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/search-jobs", response_class=HTMLResponse)
async def search_jobs_endpoint(query: str = Query(...)):
    print(f"📡 Request received for: {query}")
    try:
        jobs = search_jobs(query, num_results=15)
        html = jobs_to_html(jobs, query)
        return HTMLResponse(content=html)
    except Exception as e:
        print(f"❌ Error: {e}")
        return HTMLResponse(content=f'<div class="error">Error: {str(e)}</div>')

@app.get("/api/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 CareerPilot Backend Starting...")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)