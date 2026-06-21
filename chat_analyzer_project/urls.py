from django.urls import path
from analyzer import views

urlpatterns = [
    path('', views.dropzone, name='dropzone'),
    path('upload/', views.upload_and_analyze, name='upload'),
    path('filter/', views.filter_analysis, name='filter'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('analytics/', views.analytics, name='analytics'),
    path('processing/', views.processing, name='processing'),
    path('how-to-export/', views.how_to_export, name='how_to_export'),
    path('card/', views.share_card, name='share_card'),
]