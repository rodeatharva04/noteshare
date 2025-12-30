from django.contrib import admin
from django.urls import path, re_path
from django.contrib.auth import views as auth_views
from django.conf import settings
# from django.views.static import serve # Required to serve files
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),

    # Auth & Profile
    path('register/', views.register, name='register'),
    path('verify/', views.verify_email, name='verify_email'),
    # Login/Logout use default Django views (Standard Reloads for Security)
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    
    path('profile/', views.profile, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('user/<str:username>/', views.public_profile, name='public_profile'),

    path('verify-change/step-1/', views.verify_email_change_old, name='verify_email_change_old'),
    path('verify-change/step-2/', views.verify_email_change_new, name='verify_email_change_new'),

    # Password & Reset
    path('password-change/', auth_views.PasswordChangeView.as_view(template_name='change_password.html'), name='password_change'),
    path('password-change/done/', auth_views.PasswordChangeDoneView.as_view(template_name='password_change_done.html'), name='password_change_done'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('forgot-password/verify/', views.verify_forgot_code, name='verify_forgot_code'),
    path('forgot-password/reset/', views.reset_new_password, name='reset_new_password'),

    # Note Operations
    path('', views.home, name='home'),
    path('upload/', views.upload_note, name='upload_note'),
    path('note/<int:pk>/', views.note_detail, name='note_detail'),
    path('note/<int:pk>/edit/', views.edit_note, name='edit_note'),
    path('note/<int:pk>/delete/', views.delete_note, name='delete_note'),
    path('note/<int:pk>/rate/', views.rate_note, name='rate_note'),
    path('comment/<int:pk>/delete/', views.delete_comment, name='delete_comment'),

    path('forgot-username/', views.forgot_username, name='forgot_username'),

    path('profile/delete/init/', views.init_delete_account, name='init_delete_account'),
    path('profile/delete/verify/', views.verify_delete_account, name='verify_delete_account'),

    # --- AI CHAT (UPDATED) ---
    path('note/<int:pk>/study/', views.ai_chat_page, name='ai_chat_page'),
    path('api/ai-chat/', views.ai_chat_api, name='ai_chat_api'),

    # --- THE FIX FOR 404 MEDIA FILES ---
    # This keeps your custom inline serving logic working
    re_path(r'^media/(?P<path>.*)$', views.serve_media_inline, name='serve_media'),
]