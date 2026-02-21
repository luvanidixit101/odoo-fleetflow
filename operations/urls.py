from django.contrib.auth import views as auth_views
from django.urls import path

from .forms import ClientLoginForm
from . import views

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(template_name='auth/login.html', authentication_form=ClientLoginForm), name='login'),
    path('register/', views.register, name='register'),
    path('', views.dashboard, name='dashboard'),
    path('vehicles/', views.vehicle_registry, name='vehicle_registry'),
    path('trips/', views.trip_dispatcher, name='trip_dispatcher'),
    path('maintenance/', views.maintenance_logs, name='maintenance_logs'),
    path('expenses/', views.expense_fuel_logs, name='expense_fuel_logs'),
    path('drivers/', views.driver_profiles, name='driver_profiles'),
    path('analytics/', views.analytics_reports, name='analytics_reports'),
]
