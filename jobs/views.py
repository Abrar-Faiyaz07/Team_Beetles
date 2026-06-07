from django.shortcuts import render
from .search_engine import search_live_jobs
from .llm_engine import calculate_fit_score

from django.contrib.auth.decorators import login_required

@login_required
def job_search_view(request):
    results = []
    query = ""
    user_id = request.user.username

    if request.method == 'POST':
        query = request.POST.get('query', '')
        
        if query:
            raw_jobs = search_live_jobs(query, max_results=4)
            
            # Enrich with RAG-based AI Fit Scores
            for job in raw_jobs:
                fit_data = calculate_fit_score(job['title'], job['snippet'], user_id)
                job['fit_score'] = fit_data.get('score', 0)
                job['fit_reasoning'] = fit_data.get('reasoning', 'No reasoning provided.')
            
            # Sort by fit score descending
            results = sorted(raw_jobs, key=lambda x: x.get('fit_score', 0), reverse=True)

    return render(request, 'jobs/search.html', {'results': results, 'query': query, 'user_id': user_id})
