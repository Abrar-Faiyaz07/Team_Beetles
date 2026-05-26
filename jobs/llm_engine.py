import json
import os
import time
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))

# Try these models in order
MODELS_TO_TRY = [
    'gemini-2.0-flash',
    'gemini-2.5-flash', 
    'gemini-2.0-flash-lite',
    'gemini-flash-latest',
]

def get_working_model():
    """Find the first available model that works."""
    for model_name in MODELS_TO_TRY:
        try:
            model = genai.GenerativeModel(model_name)
            # Quick test
            response = model.generate_content("test", generation_config={"max_output_tokens": 1})
            print(f"✓ Using model: {model_name}")
            return model_name
        except Exception as e:
            if "429" in str(e):
                print(f"  Rate limited on {model_name}, waiting...")
                time.sleep(5)  # Wait 5 seconds
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content("test", generation_config={"max_output_tokens": 1})
                    print(f"✓ Using model: {model_name}")
                    return model_name
                except:
                    continue
            print(f"✗ {model_name}: {str(e)[:50]}")
            continue
    return None

MODEL_NAME = get_working_model() or 'gemini-2.0-flash'  # Fallback

def build_ranking_prompt(cv_text: str, jobs: list[dict]) -> str:
    jobs_compact = []
    for job in jobs:
        jobs_compact.append({
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
            "skills_required": job.get("skills", ""),
            "description": job.get("description", "")[:300]
        })

    prompt = f"""
You are a Career Intelligence AI. Match jobs to the user's CV and rank them.

USER CV:
{cv_text}

JOB POSTINGS:
{json.dumps(jobs_compact, indent=2)}

TASK:
For each job, calculate a fit_score (0 to 1).
Provide matched_skills, missing_skills, and a reason.
Rank by fit_score from highest to lowest.

Return ONLY a JSON array:
[
  {{
    "title": "Job Title",
    "company": "Company Name",
    "fit_score": 0.85,
    "matched_skills": ["Python", "ML"],
    "missing_skills": ["Docker"],
    "reason": "Strong match in Python and ML"
  }}
]
"""
    return prompt


def rank_and_explain(cv_text: str, jobs: list[dict]) -> list[dict]:
    if not jobs:
        return []
    
    prompt = build_ranking_prompt(cv_text, jobs)

    # Retry up to 3 times for rate limits
    for attempt in range(3):
        try:
            model = genai.GenerativeModel(MODEL_NAME)
            response = model.generate_content(prompt)
            
            raw_text = response.text.strip()
            
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            
            ranked = json.loads(raw_text.strip())
            return ranked
            
        except Exception as e:
            if "429" in str(e) and attempt < 2:
                wait_time = (attempt + 1) * 5
                print(f"Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            print(f"Gemini error: {e}")
            return fallback_response(jobs, str(e))
    
    return fallback_response(jobs, "Rate limit exceeded")


def fallback_response(jobs: list[dict], reason: str) -> list[dict]:
    return [
        {
            "title": job.get("title"),
            "company": job.get("company"),
            "fit_score": job.get("score", 0.5),
            "matched_skills": [],
            "missing_skills": [],
            "reason": reason
        }
        for job in jobs
    ]