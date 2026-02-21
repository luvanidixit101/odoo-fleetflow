from django.urls import path

from . import views

urlpatterns = [
    path('login/', views.RoleBasedLoginView.as_view(), name='login'),
    path('forgot-password/', views.forgot_password_request, name='forgot_password'),
    path('forgot-password/verify/', views.forgot_password_verify, name='forgot_password_verify'),
    path('forgot-password/reset/', views.forgot_password_reset, name='forgot_password_reset'),
    path('register/', views.register, name='register'),
    path('email/test/', views.send_test_email, name='send_test_email'),
    path('settings/admin-invite-code/', views.manage_admin_invite_code, name='manage_admin_invite_code'),
    path('user/', views.user_portal, name='user_portal'),
    path('', views.dashboard, name='dashboard'),
    path('vehicles/', views.vehicle_registry, name='vehicle_registry'),
    path('trips/', views.trip_dispatcher, name='trip_dispatcher'),
    path('maintenance/', views.maintenance_logs, name='maintenance_logs'),
    path('expenses/', views.expense_fuel_logs, name='expense_fuel_logs'),
    path('drivers/', views.driver_profiles, name='driver_profiles'),
    path('analytics/', views.analytics_reports, name='analytics_reports'),
]
