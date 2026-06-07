import markdown
from django.shortcuts import render
from .llm_agent import ask_assistant

from django.contrib.auth.decorators import login_required

@login_required
def assistant_view(request):
    chat_history = request.session.get('chat_history', [])
    user_id = request.user.username

    if request.method == 'POST':
        user_msg = request.POST.get('message', '')
        
        if user_msg:
            # Add user message to history
            chat_history.append({"role": "user", "text": user_msg})
            
            # Get AI response grounded in RAG
            ai_response_raw = ask_assistant(user_msg, user_id)
            
            # Parse Markdown to HTML for display
            ai_response_html = markdown.markdown(ai_response_raw)
            chat_history.append({"role": "ai", "text": ai_response_html})
            
            # Save back to session
            request.session['chat_history'] = chat_history

    return render(request, 'assistant/chat.html', {'chat_history': chat_history, 'user_id': user_id})

def clear_chat(request):
    request.session['chat_history'] = []
    return render(request, 'assistant/chat.html', {'chat_history': []})
