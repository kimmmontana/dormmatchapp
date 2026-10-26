from django.urls import path
from . import views
from .views import SignUpView
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path("signup/", SignUpView.as_view(), name="signup"),  # Add this line for login
    path("logout/", LogoutView.as_view(), name="logout"),
]
