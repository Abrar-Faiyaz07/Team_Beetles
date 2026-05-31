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
            response = model.generate_content("test", generation_config={"max_output_tokens": 1})
            print(f"Using model: {model_name}")
            return model_name
        except Exception as e:
            if "429" in str(e):
                print(f"Rate limited on {model_name}, waiting...")
                time.sleep(5)
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content("test", generation_config={"max_output_tokens": 1})
                    print(f"Using model: {model_name}")
                    return model_name
                except:
                    continue
            print(f"{model_name}: {str(e)[:50]}")
            continue
    return None

MODEL_NAME = get_working_model() or 'gemini-2.0-flash'

def extract_skills_and_title_from_cv(cv_text: str) -> dict:
    """Use LLM to intelligently extract skills and job title from CV."""
    
    prompt = f"""
You are a CV parsing expert. Extract the following information from this CV.

CV TEXT:
{cv_text[:8000]}

Extract:
1. Professional job title (the person's current or most recent role)
2. Key skills (5-10 concrete, job-relevant skills specific to their field)
3. Domain/industry (what industry they work in)

IMPORTANT RULES:
- Extract EXACTLY what is in the CV, do not invent skills
- If the CV is biomedical, extract biomedical skills (PCR, Cell Culture, ELISA, Flow Cytometry, Clinical Trials, FDA Regulations, Biostatistics, etc.)
- If the CV is finance, extract finance skills (Financial Modeling, Risk Analysis, Excel, SQL, Bloomberg, etc.)
- If the CV is legal, extract legal skills (Contract Law, Legal Research, Compliance, etc.)
- If the CV is software, extract software skills (Python, Java, React, etc.)
- DO NOT include the person's name as a skill
- DO NOT include generic words like "communication", "teamwork" unless they are specifically listed as key skills
- Title should be a standard job role (e.g., "Biomedical Engineer", not "Person who does engineering")

Return ONLY valid JSON in this exact format (no other text):
{{
  "title": "professional job title here",
  "skills": ["skill1", "skill2", "skill3", "skill4", "skill5"],
  "domain": "industry domain here"
}}
"""

    for attempt in range(3):
        try:
            model = genai.GenerativeModel(MODEL_NAME)
            response = model.generate_content(prompt)
            
            raw_text = response.text.strip()
            
            # Clean JSON
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            
            result = json.loads(raw_text.strip())
            
            # Validate result has required fields
            if not result.get('skills'):
                result['skills'] = []
            if not result.get('title'):
                result['title'] = 'Professional'
            if not result.get('domain'):
                result['domain'] = 'General'
                
            return result
            
        except Exception as e:
            print(f"LLM extraction error (attempt {attempt+1}): {e}")
            if attempt < 2:
                time.sleep(2)
                continue
    
    # Fallback - return empty but valid structure
    return {
        "title": "Professional",
        "skills": [],
        "domain": "General"
    }


def generate_search_queries_from_cv(cv_text: str) -> list:
    """Generate intelligent search queries based on CV content."""
    
    prompt = f"""
You are a job search strategist. Based on this CV, generate 5 search queries to find relevant job postings.

CV TEXT:
{cv_text[:6000]}

Generate search queries that would work well on job boards like Greenhouse, Lever, Workable, etc.

RULES:
- Each query should be 2-5 words for best results
- Use job titles and key skills from the CV
- DO NOT include the person's name
- Focus on role + domain or role + key skill
- Mix of broad and specific queries
- For biomedical: "Biomedical Engineer", "Clinical Research Associate", "Medical Device Engineer", "Biotech Research Scientist", "Laboratory Research Associate"
- For finance: "Financial Analyst", "Investment Associate", "Risk Analyst", "Portfolio Manager"
- For software: "Software Engineer", "Python Developer", "Full Stack Engineer"
- For legal: "Legal Associate", "Corporate Counsel", "Compliance Officer"
- For education: "Research Scientist", "Professor", "Postdoctoral Fellow"

Return ONLY a JSON array of strings (no other text):
["query1", "query2", "query3", "query4", "query5"]
"""

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
            
            queries = json.loads(raw_text.strip())
            
            if isinstance(queries, list) and len(queries) >= 3:
                return queries[:5]
            else:
                return ["Professional", "Specialist", "Researcher", "Associate", "Analyst"]
            
        except Exception as e:
            print(f"Query generation error (attempt {attempt+1}): {e}")
            if attempt < 2:
                time.sleep(2)
                continue
    
    return ["Professional", "Specialist", "Researcher", "Associate", "Analyst"]


def build_ranking_prompt(cv_text: str, jobs: list[dict]) -> str:
    """Build prompt for ranking jobs against CV."""
    jobs_compact = []
    for job in jobs[:15]:
        jobs_compact.append({
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "location": job.get("location", ""),
            "skills_required": job.get("skills", ""),
            "description": job.get("description", "")[:300]
        })

    prompt = f"""
You are a Career Intelligence AI. Match jobs to the user's CV and rank them.

USER CV:
{cv_text[:4000]}

JOB POSTINGS:
{json.dumps(jobs_compact, indent=2)}

TASK:
For each job, calculate a fit_score (0 to 1) based on:
- How well the required skills match the CV
- How relevant the domain/industry is to the CV
- Job title alignment with experience

Provide matched_skills (skills from CV that match the job), missing_skills (skills the job requires but CV lacks), and a brief reason.

Return ONLY a JSON array (no other text):
[
  {{
    "title": "Job Title",
    "company": "Company Name",
    "fit_score": 0.85,
    "matched_skills": ["Python", "Machine Learning"],
    "missing_skills": ["Docker"],
    "reason": "Strong match in Python and ML experience"
  }}
]
"""
    return prompt


def rank_and_explain(cv_text: str, jobs: list[dict]) -> list[dict]:
    """Rank jobs using LLM and return explanations."""
    if not jobs:
        return []
    
    prompt = build_ranking_prompt(cv_text, jobs)

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
    """Fallback ranking when LLM fails."""
    return [
        {
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "fit_score": job.get("score", 0.5),
            "matched_skills": [],
            "missing_skills": [],
            "reason": reason
        }
        for job in jobs
    ]