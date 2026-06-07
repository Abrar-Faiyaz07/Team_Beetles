from django.shortcuts import render, redirect
from .models import Application, Goal

from django.contrib.auth.decorators import login_required

@login_required
def tracker_dashboard(request):
    user_id = request.user.username
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_app':
            Application.objects.create(
                user_id=user_id,
                company=request.POST.get('company'),
                role=request.POST.get('role'),
                status=request.POST.get('status')
            )
        elif action == 'add_goal':
            Goal.objects.create(
                user_id=user_id,
                title=request.POST.get('title'),
                deadline=request.POST.get('deadline')
            )
        return redirect(f'/tracker/?user_id={user_id}')

    apps = Application.objects.filter(user_id=user_id).order_by('-applied_date')
    goals = Goal.objects.filter(user_id=user_id).order_by('deadline')
    
    return render(request, 'tracker/dashboard.html', {'apps': apps, 'goals': goals, 'user_id': user_id})
