from django.urls import path
from . import views

urlpatterns = [
    path('', views.assistant_view, name='assistant'),
    path('clear/', views.clear_chat, name='clear_chat'),
]
