from django.urls import path
from . import views

urlpatterns = [
    path('', views.search_view, name='search_jobs'),
    path('recommend/', views.recommend_view, name='recommend_jobs'),
]