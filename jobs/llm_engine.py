import os
import google.generativeai as genai
from django.conf import settings
from rag_core.cv_processor import query_cv

def configure_gemini():
    # Attempt to load from env or hardcode a fallback for the hackathon (NOT recommended for prod)
    # Ideally, this should be in a .env file.
    api_key = os.environ.get("GOOGLE_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
    genai.configure(api_key=api_key)

def calculate_fit_score(job_title: str, job_snippet: str, user_id: str) -> dict:
    """
    1. Query the ChromaDB RAG store for user's CV sections related to the job title.
    2. Feed the CV chunks and the Job Snippet into Gemini to compute a % fit score and reasoning.
    """
    db_path = os.path.join(settings.BASE_DIR, 'careerpilot_db')
    
    # 1. RAG Retrieval
    try:
        cv_context_chunks = query_cv(
            query_text=job_title,
            db_path=db_path,
            collection_name="cv_chunks",
            user_id=user_id,
            top_k=3
        )
        context_str = "\n\n".join([f"[{c['section']}] {c['text']}" for c in cv_context_chunks])
    except Exception as e:
        print(f"RAG Error: {e}")
        context_str = "No CV data available."

    # 2. LLM Prompting
    configure_gemini()
    prompt = f"""
    You are an expert Career AI Agent. 
    Analyze the user's CV context against the Job Posting snippet and compute a fit score.

    USER CV CONTEXT:
    {context_str}

    JOB POSTING:
    Title: {job_title}
    Description: {job_snippet}

    Return EXACTLY a JSON string with no markdown blocks, formatted like this:
    {{"score": 85, "reasoning": "A 1-sentence explanation of why they fit or don't fit based ON THEIR CV."}}
    """

    model = genai.GenerativeModel('gemini-2.5-flash')
    try:
        response = model.generate_content(prompt)
        text = response.text.replace('```json', '').replace('```', '').strip()
        import json
        return json.loads(text)
    except Exception as e:
        print(f"LLM Error: {e}")
        return {"score": 0, "reasoning": "Could not compute score due to API error or missing CV."}
