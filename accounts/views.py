from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from rag_core.models import UserProfile
from tracker.models import Application, Goal

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('/accounts/profile/')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})

@login_required
def profile_dashboard(request):
    user = request.user
    
    # 1. Get CV/RAG Status
    try:
        cv_profile = UserProfile.objects.get(user_id=user.username)
        has_cv = cv_profile.is_processed
        cv_name = cv_profile.cv_file.name.split('/')[-1]
    except UserProfile.DoesNotExist:
        has_cv = False
        cv_name = None

    # 2. Get Tracker Stats
    applications = Application.objects.filter(user_id=user.username).order_by('-applied_date')[:5] # Last 5
    total_apps = Application.objects.filter(user_id=user.username).count()
    active_apps = Application.objects.filter(user_id=user.username).exclude(status='rejected').count()
    
    goals = Goal.objects.filter(user_id=user.username).order_by('deadline')[:5] # Next 5
    completed_goals = Goal.objects.filter(user_id=user.username, is_completed=True).count()
    total_goals = Goal.objects.filter(user_id=user.username).count()
    
    goal_progress = int((completed_goals / total_goals * 100)) if total_goals > 0 else 0

    context = {
        'has_cv': has_cv,
        'cv_name': cv_name,
        'total_apps': total_apps,
        'active_apps': active_apps,
        'recent_applications': applications,
        'goal_progress': goal_progress,
        'upcoming_goals': goals,
    }
    
    return render(request, 'accounts/profile.html', context)
