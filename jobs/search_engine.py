"""
CareerPilot - Job Search Engine
Optimized for finding real, live job postings
"""
import re
import json
import time
import requests
from datetime import datetime, timezone
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# Import DuckDuckGo search
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

# ─────────────────────────────────────────────
# SEARCH QUERIES - Optimized for job boards
# ─────────────────────────────────────────────

QUERY_TEMPLATES = [
    'site:greenhouse.io "{job}"',
    'site:lever.co "{job}"',
    'site:workable.com "{job}"',
    'site:jobs.ashbyhq.com "{job}"',
    'site:myworkdayjobs.com "{job}"',
    '"{job}" "apply now" job',
    '"{job}" "job description" "qualifications"',
]

def build_queries(job_title: str) -> list[str]:
    """Build search queries targeting real job boards."""
    job_title = job_title.strip()
    return [template.format(job=job_title) for template in QUERY_TEMPLATES]


def search_ddg(query: str, total: int = 30) -> list[dict]:
    """Search DuckDuckGo with error handling."""
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
    except Exception as e:
        print(f"DDG search error for '{query[:50]}': {str(e)[:50]}")
    
    return results


# ─────────────────────────────────────────────
# FETCH PAGE - Robust with retry
# ─────────────────────────────────────────────

def fetch_page(url: str) -> str | None:
    """Download a page with retry logic and better error handling."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
            
            # Accept more status codes
            if resp.status_code not in [200, 201, 202]:
                return None
            
            # Accept HTML and plain text
            ct = resp.headers.get("content-type", "")
            if "text/html" not in ct and "text/plain" not in ct:
                return None
            
            html = resp.text
            
            # Quick dead-page check
            low = html[:3000].lower()
            dead_phrases = [
                "page not found", "404", "no longer available",
                "access denied", "not found", "sorry, the page"
            ]
            if any(phrase in low for phrase in dead_phrases):
                return None
            
            # Strip script/style tags and HTML
            text = re.sub(r"<(script|style|noscript|iframe)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"&[a-z]+;", " ", text)  # Remove HTML entities
            text = re.sub(r"\s+", " ", text).strip()
            
            # Accept shorter pages (job listings can be brief)
            if len(text) < 50:
                return None
            
            return text[:15000]  # Increased limit
            
        except requests.Timeout:
            if attempt == 0:
                time.sleep(1)
                continue
            return None
        except Exception:
            if attempt == 0:
                time.sleep(1)
                continue
            return None
    
    return None


# ─────────────────────────────────────────────
# JOB-PAGE VALIDATION
# ─────────────────────────────────────────────

def extract_jsonld_job(html: str) -> dict | None:
    """Try to extract a JobPosting schema.org object from JSON-LD."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                # Handle array wrapping
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("@type") == "JobPosting":
                            return item
                elif isinstance(data, dict) and data.get("@type") == "JobPosting":
                    return data
            except (json.JSONDecodeError, AttributeError):
                continue
    except Exception:
        pass
    return None


# Broader job signals for better detection
JOB_SIGNALS = [
    "apply now", "apply here", "apply for this job",
    "full-time", "part-time", "remote", "hybrid",
    "salary", "benefits", "compensation",
    "job description", "requirements", "qualifications",
    "responsibilities", "we are looking for",
    "about the role", "about this position",
    "hiring", "join our team", "join us",
    "position", "role", "opportunity",
    "posted", "deadline", "apply by",
    "equal opportunity", "diversity",
]

def job_page_score(text: str) -> float:
    """Heuristic score: how likely is this text a real job posting?"""
    low = text[:5000].lower()
    hits = sum(1 for phrase in JOB_SIGNALS if phrase in low)
    # Anti-signals (non-job content)
    anti = sum(1 for phrase in [
        "search results", "all jobs", "no jobs found",
        "job alerts", "sign in to apply", "wikipedia",
        "tutorial", "blog", "news"
    ] if phrase in low)
    return max(0.0, (hits - anti) / len(JOB_SIGNALS))


# ─────────────────────────────────────────────
# SMARTER EXTRACTORS
# ─────────────────────────────────────────────

def extract_company_smart(url: str, domain: str) -> str:
    """Extract company name from URL patterns."""
    # Greenhouse: greenhouse.io/companyname/...
    if "greenhouse.io" in domain:
        path = urlparse(url).path.strip("/")
        parts = path.split("/")
        if parts and parts[0].lower() not in ["jobs", "job", "careers", "pages"]:
            return parts[0].replace("-", " ").replace("_", " ").title()
    
    # Lever: jobs.lever.co/companyname or company.lever.co
    if "lever.co" in domain:
        path = urlparse(url).path.strip("/")
        if path and path.split("/")[0].lower() not in ["jobs", "job"]:
            return path.split("/")[0].replace("-", " ").replace("_", " ").title()
        sub = domain.replace("jobs.lever.co", "").replace(".lever.co", "")
        if sub:
            return sub.replace("-", " ").title()
    
    # Workable: apply.workable.com/companyname or company.workable.com
    if "workable.com" in domain:
        path = urlparse(url).path.strip("/")
        if path:
            return path.split("/")[0].replace("-", " ").replace("_", " ").title()
        sub = domain.replace(".workable.com", "")
        if sub and sub != "apply":
            return sub.replace("-", " ").title()
    
    # Ashby: jobs.ashbyhq.com/companyname
    if "ashbyhq.com" in domain:
        path = urlparse(url).path.strip("/")
        if path:
            return path.split("/")[0].replace("-", " ").replace("_", " ").title()
    
    # MyWorkdayJobs: company.wd5.myworkdayjobs.com
    if "myworkdayjobs.com" in domain:
        sub = domain.split(".")[0]
        if sub:
            return sub.replace("-", " ").title()
    
    # Generic: try to extract from domain
    parts = domain.split(".")
    if len(parts) >= 2:
        name = parts[-2] if parts[-2] not in ["co", "com", "org", "net", "io"] else parts[-3] if len(parts) >= 3 else parts[-2]
        return name.replace("-", " ").replace("_", " ").title()
    
    return domain.replace("-", " ").title()


def extract_location(text: str) -> str:
    """Extract location from job text."""
    patterns = [
        r"(location|based in|located in|city|region)[:\s]+([A-Za-z ,\-]{3,40})",
        r"(remote|onsite|hybrid)(?:\s+in\s+([A-Za-z ,\-]{3,40}))?",
        r"([A-Za-z]+,\s*[A-Z]{2})",  # City, ST
        r"([A-Za-z]+,\s*[A-Za-z]+)",   # City, Country
    ]
    
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            # Return the longest match group
            groups = [g for g in m.groups() if g]
            if groups:
                return groups[-1].strip()[:50]
    return ""


def extract_skills(text: str) -> str:
    """Extract skills/requirements from job text."""
    patterns = [
        r"(skills?|requirements?|qualifications?|tech stack|you have|you'll need|what you need)[:\-]?\s*(.{20,300})",
        r"(we are looking for|you should have|must have|nice to have)[:\-]?\s*(.{20,300})",
    ]
    
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            # Get the skills part
            skills_text = m.group(2) if len(m.groups()) > 1 else m.group(1)
            # Clean up
            skills_text = re.sub(r'<[^>]+>', ' ', skills_text)
            skills_text = re.sub(r'\s+', ' ', skills_text).strip()
            return skills_text[:200]
    return ""


# ─────────────────────────────────────────────
# JOB PARSER
# ─────────────────────────────────────────────

def parse_job(r: dict) -> dict | None:
    """Convert a search result into a job entry, or None if not valid."""
    url = r["url"]
    title = r["title"]
    snippet = r["snippet"]
    domain = urlparse(url).netloc.replace("www.", "")

    page_text = fetch_page(url)
    if page_text is None:
        return None

    # 1) Try structured data (most reliable)
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

    # 2) Fallback: heuristic validation (lenient)
    full_text = f"{snippet} {page_text[:3000]}"
    score = job_page_score(full_text)
    
    # More lenient - accept if score > 0 or page has any job signals
    if score <= 0 and not any(signal in full_text.lower() for signal in ["apply", "job", "hiring", "position"]):
        return None

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
        "quality_score": max(score, 0.1)
    }


# ─────────────────────────────────────────────
# SCORING FUNCTIONS
# ─────────────────────────────────────────────

def score_job_keywords(query: str, job: dict) -> float:
    """Score a job based on keyword overlap with the query."""
    query_terms = set(query.lower().split())
    job_text = f"{job.get('title','')} {job.get('skills','')} {job.get('description','')}".lower()
    
    score = 0.0
    for term in query_terms:
        if term in job_text:
            score += 1.0
    
    return score / len(query_terms) if query_terms else 0.0


def rank_jobs(query: str, jobs: list[dict]) -> list[dict]:
    """Rank jobs by relevance score."""
    for job in jobs:
        keyword_score = score_job_keywords(query, job)
        schema_bonus = 0.2 if job.get("has_schema") else 0.0
        quality_boost = job.get("quality_score", 0.5) * 0.1
        missing = sum(1 for k in ["company", "location", "skills"] if not job.get(k))
        penalty = missing * 0.1
        
        job["score"] = round(max(0.0, keyword_score + schema_bonus + quality_boost - penalty), 3)
    
    return sorted(jobs, key=lambda x: x["score"], reverse=True)


# ─────────────────────────────────────────────
# MAIN SEARCH FUNCTION
# ─────────────────────────────────────────────

def search_jobs(query: str, num_results: int = 25) -> list[dict]:
    """Main search function: returns ranked list of job dicts."""
    raw_results = []
    seen_urls = set()
    
    queries = build_queries(query)
    
    for q in queries:
        batch = search_ddg(q, total=max(10, num_results // len(queries)))
        for res in batch:
            if res["url"] not in seen_urls:
                seen_urls.add(res["url"])
                raw_results.append(res)
        if len(raw_results) >= num_results * 2:  # Collect extra for filtering
            break
    
    # Limit and deduplicate
    raw_results = raw_results[:num_results * 2]
    
    jobs = []
    for i, r in enumerate(raw_results):
        job = parse_job(r)
        if job:
            jobs.append(job)
        time.sleep(0.15)  # Be polite to servers
    
    # Rank and return
    ranked = rank_jobs(query, jobs)
    return ranked[:num_results]