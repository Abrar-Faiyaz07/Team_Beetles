import os
import re
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.contrib import messages
from .cv_processor import run_pipeline, query_cv, get_full_cv_text, get_or_create_collection
from .llm_engine import extract_skills_and_title_from_cv

CHROMA_DB_PATH = os.path.join(settings.BASE_DIR, 'careerpilot_db')
CHROMA_COLLECTION = 'cv_chunks'


def extract_name_from_cv(cv_text: str) -> str:
    """Extract person's name from CV text using regex patterns."""
    if not cv_text:
        return "Professional"
    
    # Common name patterns at the beginning of CVs
    lines = cv_text.split('\n')[:20]  # Check first 20 lines
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Pattern: Two words, both capitalized (First Last)
        match = re.match(r'^([A-Z][a-z]+)\s+([A-Z][a-z]+)(?:\s+([A-Z][a-z]+))?$', line)
        if match:
            first = match.group(1)
            last = match.group(2)
            if len(first) > 1 and len(last) > 1:
                return f"{first} {last}"
        
        # Pattern: First Last (with possible middle initial)
        match = re.match(r'^([A-Z][a-z]+)\s+([A-Z]\.?\s+)?([A-Z][a-z]+)', line)
        if match:
            first = match.group(1)
            last = match.group(3) if match.group(3) else match.group(2)
            if isinstance(last, str) and len(last) > 1:
                return f"{first} {last}".strip()
    
    return "Professional"


def upload_cv(request):
    """Handle CV upload, vector compilation, and dashboard presentation."""
    if not request.session.session_key:
        request.session.create()
    user_id = request.session.session_key

    if request.method == 'POST':
        # Handle CV Removal
        if request.POST.get('action') == 'remove':
            try:
                import chromadb
                client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
                collection = client.get_or_create_collection(name=CHROMA_COLLECTION)
                collection.delete(where={"user_id": user_id})
            except Exception:
                pass
            for key in ['cv_processed', 'cv_filename', 'cv_user_id', 'cv_full_text', 'cv_person_name']:
                request.session.pop(key, None)
            request.session.save()
            messages.success(request, 'CV removed from vector profile.')
            return redirect('upload_cv')

        # Handle CV Upload
        if request.FILES.get('cv_file'):
            cv_file = request.FILES['cv_file']
            ext = os.path.splitext(cv_file.name)[1].lower()
            if ext not in ['.pdf', '.docx', '.doc']:
                messages.error(request, f'Unsupported file type: {ext}. Use PDF or DOCX.')
                return render(request, 'jobs/upload_cv.html')

            upload_dir = os.path.join(settings.MEDIA_ROOT, 'cvs')
            os.makedirs(upload_dir, exist_ok=True)
            fs = FileSystemStorage(location=upload_dir)
            filename = fs.save(cv_file.name, cv_file)
            file_path = fs.path(filename)

            try:
                result = run_pipeline(
                    cv_path=file_path,
                    db_path=CHROMA_DB_PATH,
                    collection=CHROMA_COLLECTION,
                    user_id=user_id,
                )
                request.session['cv_processed'] = True
                request.session['cv_filename'] = cv_file.name
                request.session['cv_user_id'] = user_id
                
                # Get full CV text for LLM extraction
                full_text = get_full_cv_text(CHROMA_DB_PATH, CHROMA_COLLECTION, user_id)
                if full_text:
                    request.session['cv_full_text'] = full_text[:10000]
                    # Extract person's name
                    person_name = extract_name_from_cv(full_text)
                    request.session['cv_person_name'] = person_name
                else:
                    request.session['cv_person_name'] = "Professional"
                    
                request.session.save()
                
                messages.success(request, f'CV parsed successfully! Stored {result["chunks_stored"]} vector chunks.')
                return redirect('upload_cv')
            except Exception as e:
                messages.error(request, f'Error processing CV: {str(e)}')
                return render(request, 'jobs/upload_cv.html')

    # GET: Build dashboard context
    context = {}
    if request.session.get('cv_processed'):
        try:
            # Get the full CV text
            cv_full_text = request.session.get('cv_full_text', '')
            
            if not cv_full_text:
                cv_full_text = get_full_cv_text(CHROMA_DB_PATH, CHROMA_COLLECTION, user_id)
                if cv_full_text:
                    request.session['cv_full_text'] = cv_full_text[:10000]
            
            # Get person's name from session or extract it
            person_name = request.session.get('cv_person_name', '')
            if not person_name and cv_full_text:
                person_name = extract_name_from_cv(cv_full_text)
                request.session['cv_person_name'] = person_name
                request.session.save()
            
            # Use LLM to extract skills and title
            print("Extracting skills and title using LLM...")
            llm_result = extract_skills_and_title_from_cv(cv_full_text)
            
            skills_list = llm_result.get('skills', [])
            job_title = llm_result.get('title', 'Professional')
            domain = llm_result.get('domain', 'General')
            
            print(f"Person name: {person_name}")
            print(f"Job title: {job_title}")
            print(f"Skills: {skills_list}")
            
            # Get experience sections from chunks for display
            collection = get_or_create_collection(CHROMA_DB_PATH, CHROMA_COLLECTION)
            results = collection.get(
                where={"user_id": user_id},
                include=["documents", "metadatas"]
            )
            
            experience_display = ""
            if results and results["documents"]:
                for doc, meta in zip(results["documents"], results["metadatas"]):
                    if meta.get("section") == "experience":
                        # Take first 500 chars of experience
                        exp_preview = doc[:500]
                        experience_display += exp_preview + "\n\n"
            
            if not experience_display:
                experience_display = "Professional experience extracted from CV. Click 'Match CV with Jobs' to find relevant positions."
            
            context['cv_data'] = {
                'name': person_name if person_name else request.session.get('cv_filename', 'CV').replace('.pdf', '').replace('.docx', '').replace('.doc', ''),
                'title': job_title,
                'experience': experience_display,
                'skills': skills_list if skills_list else ["No skills extracted yet"],
                'domain': domain
            }

        except Exception as e:
            print(f"Error building CV context: {e}")
            context['cv_data'] = {
                'name': request.session.get('cv_person_name', request.session.get('cv_filename', 'Professional')),
                'title': 'Professional',
                'experience': "CV loaded successfully. Click 'Match CV with Jobs' to analyze and find opportunities.",
                'skills': ["Ready for analysis"],
                'domain': "General"
            }

    return render(request, 'jobs/upload_cv.html', context)


def query_cv_api(request):
    """API endpoint to query CV."""
    query = request.GET.get('q', '')
    if not query:
        return JsonResponse({"error": "Query parameter 'q' is required"}, status=400)
    if not request.session.session_key:
        return JsonResponse({"error": "No session found. Please upload CV first."}, status=400)

    try:
        results = query_cv(query, CHROMA_DB_PATH, CHROMA_COLLECTION, request.session.session_key, top_k=5)
        return JsonResponse(results, safe=False)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def get_cv_text(request):
    """Get full CV text."""
    if not request.session.session_key:
        return JsonResponse({"cv_text": "", "has_cv": False})

    try:
        cv_text = get_full_cv_text(CHROMA_DB_PATH, CHROMA_COLLECTION, request.session.session_key)
        person_name = extract_name_from_cv(cv_text)
        return JsonResponse({"cv_text": cv_text, "has_cv": bool(cv_text), "person_name": person_name})
    except Exception as e:
        return JsonResponse({"cv_text": "", "error": str(e), "has_cv": False})