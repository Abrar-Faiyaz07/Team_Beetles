import os
from django.shortcuts import render, redirect
from django.conf import settings
from .models import UserProfile
from .cv_processor import run_pipeline

from django.contrib.auth.decorators import login_required

@login_required
def upload_cv(request):
    user_id = request.user.username
    if request.method == 'POST':
        cv_file = request.FILES.get('cv_file')

        if cv_file:
            profile, created = UserProfile.objects.get_or_create(user_id=user_id)
            profile.cv_file = cv_file
            profile.is_processed = False
            profile.save()

            # Process the CV
            file_path = profile.cv_file.path
            db_path = os.path.join(settings.BASE_DIR, 'careerpilot_db')
            
            try:
                run_pipeline(
                    cv_path=file_path,
                    db_path=db_path,
                    user_id=user_id
                )
                profile.is_processed = True
                profile.save()
                return render(request, 'rag_core/success.html', {'user_id': user_id})
            except Exception as e:
                return render(request, 'rag_core/upload.html', {'error': str(e)})

    return render(request, 'rag_core/upload.html')
