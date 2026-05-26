# careerpilot/jobs/views.py
from django.shortcuts import render
from django.http import JsonResponse
from .search_engine import search_jobs as run_search
from .llm_engine import rank_and_explain
from django.conf import settings
from .cv_processor import get_full_cv_text
import os



DUMMY_CV = """
Computer Science graduate with 1 year internship experience.
Skills: Python, Machine Learning, NLP, TensorFlow, Scikit-learn, SQL.
Projects: fraud detection system using logistic regression and random forest,
         chatbot using transformers (BERT), recommendation engine.
Education: B.Sc. in Computer Science, CGPA 3.8.
Interests: ML engineer, data scientist, AI research.
Location preference: Dhaka, remote.
"""

def search_view(request):
    # Your existing search view code
    query = request.GET.get('q', '')
    num = request.GET.get('num', '10')
    jobs = []
    error = None
    searched = False

    if query:
        searched = True
        try:
            num = int(num)
            if num < 1:
                num = 10
            elif num > 30:
                num = 30
        except ValueError:
            num = 10

        try:
            jobs = run_search(query, num_results=num)
            if not jobs:
                error = "No valid job postings found. Try a different search term."
        except Exception as e:
            error = f"Search failed: {str(e)}"

    context = {
        'query': query,
        'num': num,
        'jobs': jobs,
        'error': error,
        'searched': searched,
    }
    return render(request, 'jobs/search.html', context)


CHROMA_DB_PATH = os.path.join(settings.BASE_DIR, 'careerpilot_db')
CHROMA_COLLECTION = 'cv_chunks'

def recommend_view(request):
    """LLM-powered personalized job recommendations using real CV."""
    query = request.GET.get('q', '')
    num = request.GET.get('num', '10')
    
    if not query:
        return JsonResponse({"error": "Query parameter 'q' is required."}, status=400)

    try:
        num = int(num)
        num = max(1, min(num, 30))
    except ValueError:
        num = 10

    try:
        raw_jobs = run_search(query, num_results=num)
        
        if not raw_jobs:
            return JsonResponse([], safe=False)
        
        # Try to get real CV text from ChromaDB
        cv_text = DUMMY_CV  # Default fallback
        if request.session.session_key:
            try:
                real_cv = get_full_cv_text(
                    CHROMA_DB_PATH, 
                    CHROMA_COLLECTION, 
                    request.session.session_key
                )
                if real_cv:
                    cv_text = real_cv
            except Exception:
                pass
        
        enriched = rank_and_explain(cv_text, raw_jobs)
        
        for i, job in enumerate(enriched):
            if i < len(raw_jobs):
                job['apply_link'] = raw_jobs[i].get('apply_link', '')
                job['original_score'] = raw_jobs[i].get('score', 0)
        
        return JsonResponse(enriched, safe=False)
        
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)