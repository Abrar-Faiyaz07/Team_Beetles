import os
import google.generativeai as genai
from django.conf import settings
from rag_core.cv_processor import query_cv

def ask_assistant(user_message: str, user_id: str) -> str:
    """
    RAG-grounded AI assistant.
    Answers queries like: "Am I ready for a data engineer role?"
    """
    db_path = os.path.join(settings.BASE_DIR, 'careerpilot_db')
    
    # RAG Retrieval
    try:
        cv_context_chunks = query_cv(
            query_text=user_message,
            db_path=db_path,
            collection_name="cv_chunks",
            user_id=user_id,
            top_k=5
        )
        context_str = "\n\n".join([f"[{c['section']}] {c['text']}" for c in cv_context_chunks])
    except Exception as e:
        context_str = "No CV data available."

    api_key = os.environ.get("GOOGLE_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
    genai.configure(api_key=api_key)

    prompt = f"""
    You are CareerPilot, an expert Career AI Assistant.
    You must answer the user's query based strictly on their real CV context below.
    If they ask to write a cover letter, draft it using their specific experience.
    If they ask for a roadmap, give actionable weekly steps based on their current skill gap.

    USER CV CONTEXT:
    {context_str}

    USER QUERY:
    {user_message}
    """

    model = genai.GenerativeModel('gemini-2.5-flash')
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return "Sorry, I am facing an issue connecting to my brain."
