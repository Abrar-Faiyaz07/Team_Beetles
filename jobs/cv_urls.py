from django.urls import path
from . import cv_views

urlpatterns = [
    path('upload-cv/', cv_views.upload_cv, name='upload_cv'),
    path('api/query-cv/', cv_views.query_cv_api, name='query_cv_api'),
    path('api/get-cv-text/', cv_views.get_cv_text, name='get_cv_text'),
]