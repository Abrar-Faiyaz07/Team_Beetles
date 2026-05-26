import os
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.contrib import messages
from .cv_processor import run_pipeline, query_cv, get_full_cv_text

# ChromaDB settings
CHROMA_DB_PATH = os.path.join(settings.BASE_DIR, 'careerpilot_db')
CHROMA_COLLECTION = 'cv_chunks'

def upload_cv(request):
    """Handle CV upload and processing."""
    if request.method == 'POST' and request.FILES.get('cv_file'):
        cv_file = request.FILES['cv_file']
        
        # Validate file type
        allowed_types = ['.pdf', '.docx', '.doc']
        ext = os.path.splitext(cv_file.name)[1].lower()
        if ext not in allowed_types:
            messages.error(request, f'Unsupported file type: {ext}. Use PDF or DOCX.')
            return render(request, 'jobs/upload_cv.html')
        
        # Ensure upload directory exists
        upload_dir = os.path.join(settings.MEDIA_ROOT, 'cvs')
        os.makedirs(upload_dir, exist_ok=True)
        
        # Save uploaded file
        fs = FileSystemStorage(location=upload_dir)
        filename = fs.save(cv_file.name, cv_file)
        file_path = fs.path(filename)
        
        # Create session if not exists
        if not request.session.session_key:
            request.session.create()
        user_id = request.session.session_key
        
        try:
            # Process the CV
            result = run_pipeline(
                cv_path=file_path,
                db_path=CHROMA_DB_PATH,
                collection=CHROMA_COLLECTION,
                user_id=user_id,
            )
            
            # Store CV info in session
            request.session['cv_processed'] = True
            request.session['cv_filename'] = cv_file.name
            request.session['cv_user_id'] = user_id
            request.session.save()
            
            messages.success(request, 
                f'CV processed successfully! Found {len(result["sections_found"])} sections, '
                f'{result["chunks_stored"]} chunks stored.')
            
            return redirect('search_jobs')
            
        except Exception as e:
            messages.error(request, f'Error processing CV: {str(e)}')
            return render(request, 'jobs/upload_cv.html')
    
    return render(request, 'jobs/upload_cv.html')


def query_cv_api(request):
    """API endpoint to query CV."""
    query = request.GET.get('q', '')
    if not query:
        return JsonResponse({"error": "Query parameter 'q' is required"}, status=400)
    
    if not request.session.session_key:
        return JsonResponse({"error": "No session found. Please upload CV first."}, status=400)
    
    user_id = request.session.session_key
    
    try:
        results = query_cv(
            query_text=query,
            db_path=CHROMA_DB_PATH,
            collection_name=CHROMA_COLLECTION,
            user_id=user_id,
            top_k=5,
        )
        return JsonResponse(results, safe=False)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def get_cv_text(request):
    """Get the full CV text for the current user."""
    if not request.session.session_key:
        return JsonResponse({
            "cv_text": "",
            "error": "No session found",
            "has_cv": False
        })
    
    user_id = request.session.session_key
    
    try:
        cv_text = get_full_cv_text(CHROMA_DB_PATH, CHROMA_COLLECTION, user_id)
        return JsonResponse({
            "cv_text": cv_text,
            "has_cv": bool(cv_text),
            "user_id": user_id
        })
    except Exception as e:
        return JsonResponse({
            "cv_text": "",
            "error": str(e),
            "has_cv": False
        })