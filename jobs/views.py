# views.py - Fully fixed with LLM extraction

import os
import re
from django.shortcuts import render
from django.http import JsonResponse
from django.conf import settings
from .search_engine import search_jobs as run_search
from .llm_engine import rank_and_explain, extract_skills_and_title_from_cv, generate_search_queries_from_cv
from .cv_processor import get_full_cv_text, get_or_create_collection

CHROMA_DB_PATH = os.path.join(settings.BASE_DIR, 'careerpilot_db')
CHROMA_COLLECTION = 'cv_chunks'


def clean_query(query: str) -> str:
    """Remove newlines, normalize whitespace, and strip."""
    if not query:
        return ""
    query = query.replace('\n', ' ').replace('\r', ' ').strip()
    query = ' '.join(query.split())
    return query


def search_view(request):
    """Regular job search view."""
    query = clean_query(request.GET.get('q', ''))
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


def recommend_view(request):
    """LLM-powered personalized job recommendations using CV."""
    
    if not request.session.session_key:
        return JsonResponse({"error": "No session found. Please upload a CV first."}, status=400)
    
    user_id = request.session.session_key
    
    # Get the real CV text from ChromaDB
    cv_text = get_full_cv_text(
        CHROMA_DB_PATH,
        CHROMA_COLLECTION,
        user_id
    )
    
    if not cv_text or len(cv_text) < 50:
        return JsonResponse({"error": "No CV found. Please upload your CV first."}, status=400)
    
    num = request.GET.get('num', '12')
    try:
        num = int(num)
        num = max(1, min(num, 30))
    except ValueError:
        num = 12
    
    # Extract skills and title using LLM
    print("Extracting skills and title from CV using LLM...")
    cv_analysis = extract_skills_and_title_from_cv(cv_text)
    print(f"Extracted title: {cv_analysis.get('title')}")
    print(f"Extracted skills: {cv_analysis.get('skills', [])}")
    print(f"Domain: {cv_analysis.get('domain')}")
    
    # Generate search queries from CV using LLM
    search_queries = generate_search_queries_from_cv(cv_text)
    print(f"Generated search queries: {search_queries}")
    
    # Search with each query and combine results
    all_jobs = []
    seen_urls = set()
    
    for search_query in search_queries:
        try:
            jobs = run_search(search_query, num_results=num // len(search_queries) + 3)
            for job in jobs:
                if job.get('apply_link') not in seen_urls:
                    seen_urls.add(job.get('apply_link'))
                    job['search_query_used'] = search_query
                    all_jobs.append(job)
        except Exception as e:
            print(f"Search failed for '{search_query}': {e}")
    
    # Fallback if no jobs found
    if not all_jobs and cv_analysis.get('title'):
        try:
            print(f"Fallback search using title: {cv_analysis['title']}")
            all_jobs = run_search(cv_analysis['title'], num_results=num)
        except Exception as e:
            print(f"Fallback search failed: {e}")
    
    if not all_jobs:
        return JsonResponse([], safe=False)
    
    print(f"Found {len(all_jobs)} total jobs, ranking with LLM...")
    
    # Rank jobs against CV using LLM
    enriched = rank_and_explain(cv_text, all_jobs)
    
    # Add metadata back to results
    for i, job in enumerate(enriched):
        if i < len(all_jobs):
            job['apply_link'] = all_jobs[i].get('apply_link', '')
            job['original_score'] = all_jobs[i].get('score', 0)
            job['search_query'] = all_jobs[i].get('search_query_used', '')
        job['cv_skills'] = cv_analysis.get('skills', [])[:5]
        job['cv_domain'] = cv_analysis.get('domain', '')
    
    # Sort by fit_score descending
    enriched.sort(key=lambda x: x.get('fit_score', 0), reverse=True)
    
    return JsonResponse(enriched[:num], safe=False)