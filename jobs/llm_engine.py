import json
import os
import google.generativeai as genai

# Configure Gemini
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

def build_ranking_prompt(cv_text: str, jobs: list[dict]) -> str:
    """Create the prompt that tells Gemini exactly what to do."""
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
You are a Career Intelligence AI.

Your job is to match job postings with a user's CV and recommend the best opportunities.

You MUST:
- Understand the user's CV deeply.
- Compare each job against the CV.
- Rank jobs by relevance (highest fit_score first).
- Explain WHY each job matches or does not match.
- Be strict and realistic (do not over-praise weak matches).

USER CV:
{cv_text}

JOB POSTINGS:
{json.dumps(jobs_compact, indent=2)}

TASK:
For each job, calculate a **fit_score** (0 to 1).
- 0.0 = completely irrelevant
- 1.0 = perfect match

Then provide:
- **matched_skills**: skills from the CV that match the job requirements.
- **missing_skills**: skills mentioned in the job that are NOT in the CV.
- **reason**: 1-2 sentences explaining the overall match quality.

Return ONLY a valid JSON array with this exact structure (no other text):

[
  {{
    "title": "Job Title",
    "company": "Company Name",
    "fit_score": 0.85,
    "matched_skills": ["Python", "ML"],
    "missing_skills": ["Docker"],
    "reason": "Strong Python and ML match. Missing Docker experience."
  }}
]

IMPORTANT: Return ONLY the JSON array. No markdown, no explanations.
"""
    return prompt


def rank_and_explain(cv_text: str, jobs: list[dict]) -> list[dict]:
    """Use Gemini to rank jobs and provide explanations."""
    
    prompt = build_ranking_prompt(cv_text, jobs)

    try:
        # Use Gemini 1.5 Flash (fast and free tier available)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=2000,
            )
        )
        
        raw_text = response.text.strip()
        
        # Clean up - sometimes Gemini wraps in markdown
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        
        ranked = json.loads(raw_text)
        return ranked
        
    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
        print(f"Raw response: {raw_text[:500]}")
        return fallback_response(jobs, "AI response parsing failed")
        
    except Exception as e:
        print(f"Gemini API error: {e}")
        return fallback_response(jobs, f"AI processing failed: {str(e)}")


def fallback_response(jobs: list[dict], reason: str) -> list[dict]:
    """Return a basic response when LLM fails."""
    return [
        {
            "title": job.get("title"),
            "company": job.get("company"),
            "fit_score": job.get("score", 0.5),
            "matched_skills": job.get("skills", "").split(",")[:3] if job.get("skills") else [],
            "missing_skills": [],
            "reason": reason
        }
        for job in jobs
    ]