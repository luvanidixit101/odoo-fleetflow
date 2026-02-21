from decimal import Decimal
from datetime import datetime, timedelta
from functools import wraps
import secrets
import smtplib

from django.contrib import messages
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.models import Group
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone

from .forms import (
    ADMIN_INVITE_CODE_SETTING_KEY,
    ClientLoginForm,
    ClientRegistrationForm,
    DriverProfileForm,
    ForgotPasswordEmailForm,
    ForgotPasswordOTPForm,
    FuelLogForm,
    OTPSetPasswordForm,
    ServiceLogForm,
    ShipmentForm,
    TripForm,
    VehicleForm,
)
from .models import DriverProfile, FuelLog, ServiceLog, Shipment, SystemSetting, Trip, TripStatus, Vehicle, VehicleStatus


ROLE_TO_GROUP_NAME = {
    'fleet_manager': 'Fleet Managers',
    'dispatcher': 'Dispatchers',
    'safety_officer': 'Safety Officers',
    'financial_analyst': 'Financial Analysts',
}
PASSWORD_RESET_OTP_SESSION_KEY = 'password_reset_otp_data'
PASSWORD_RESET_OTP_EXPIRY_MINUTES = 10
PASSWORD_RESET_OTP_MAX_ATTEMPTS = 5


def is_admin(user):
    return user.is_staff or user.is_superuser


def get_user_role(user):
    if is_admin(user):
        return 'admin'
    for role_key, group_name in ROLE_TO_GROUP_NAME.items():
        if user.groups.filter(name=group_name).exists():
            return role_key
    return 'user'


def role_redirect_name(user):
    role = get_user_role(user)
    return 'user_portal' if role == 'user' else 'dashboard'


def registration_redirect_name(role):
    if role == 'admin':
        return 'admin:index'
    if role == 'user':
        return 'user_portal'
    return 'dashboard'


def assign_role_groups(user, role):
    user.groups.clear()
    group_name = ROLE_TO_GROUP_NAME.get(role)
    if group_name:
        group, _ = Group.objects.get_or_create(name=group_name)
        user.groups.add(group)


def roles_required(*allowed_roles):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user_role = get_user_role(request.user)
            if user_role not in allowed_roles:
                messages.error(request, 'Access denied for this page.')
                return redirect(role_redirect_name(request.user))
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


class RoleBasedLoginView(auth_views.LoginView):
    template_name = 'auth/login.html'
    authentication_form = ClientLoginForm
    role_error_message = 'Authentication failed. Please check your login details and try again.'

    def form_valid(self, form):
        selected_role = form.cleaned_data.get('login_as')
        user = form.get_user()
        actual_role = get_user_role(user)

        if selected_role != actual_role:
            form.add_error(None, self.role_error_message)
            return self.form_invalid(form)
        return super().form_valid(form)

    def get_success_url(self):
        selected_role = self.request.POST.get('login_as')
        if selected_role == 'admin':
            return reverse_lazy('admin:index')
        if selected_role == 'user':
            return reverse_lazy('user_portal')
        return reverse_lazy('dashboard')


def _get_otp_session_data(request):
    return request.session.get(PASSWORD_RESET_OTP_SESSION_KEY, {})


def _set_otp_session_data(request, data):
    request.session[PASSWORD_RESET_OTP_SESSION_KEY] = data
    request.session.modified = True


def _clear_otp_session_data(request):
    if PASSWORD_RESET_OTP_SESSION_KEY in request.session:
        del request.session[PASSWORD_RESET_OTP_SESSION_KEY]
        request.session.modified = True


def _otp_is_expired(data):
    expires_at = data.get('expires_at')
    if not expires_at:
        return True
    try:
        expiry_dt = datetime.fromisoformat(expires_at)
    except ValueError:
        return True
    if timezone.is_naive(expiry_dt):
        expiry_dt = timezone.make_aware(expiry_dt, timezone.get_current_timezone())
    return timezone.now() > expiry_dt


def get_admin_invite_code():
    env_value = (getattr(settings, 'ADMIN_REGISTRATION_TOKEN', '') or '').strip()
    return (
        SystemSetting.get_value(ADMIN_INVITE_CODE_SETTING_KEY, env_value)
        or ''
    ).strip()


def _smtp_configuration_error():
    backend = (getattr(settings, 'EMAIL_BACKEND', '') or '').strip()
    if backend != 'django.core.mail.backends.smtp.EmailBackend':
        return 'Email backend must be SMTP. Set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend.'

    required = {
        'EMAIL_HOST': getattr(settings, 'EMAIL_HOST', ''),
        'EMAIL_HOST_USER': getattr(settings, 'EMAIL_HOST_USER', ''),
        'EMAIL_HOST_PASSWORD': getattr(settings, 'EMAIL_HOST_PASSWORD', ''),
        'DEFAULT_FROM_EMAIL': getattr(settings, 'DEFAULT_FROM_EMAIL', ''),
    }
    missing = [key for key, value in required.items() if not str(value).strip()]
    if missing:
        return f'Missing email settings: {", ".join(missing)}.'

    port = int(getattr(settings, 'EMAIL_PORT', 0) or 0)
    if port <= 0:
        return 'EMAIL_PORT must be a valid positive number.'
    return ''


def forgot_password_request(request):
    if request.user.is_authenticated:
        return redirect(role_redirect_name(request.user))

    form = ForgotPasswordEmailForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        smtp_error = _smtp_configuration_error()
        if smtp_error:
            messages.error(request, f'SMTP is not configured: {smtp_error}')
            return render(request, 'auth/forgot_password_request.html', {'form': form})

        email = form.cleaned_data['email'].strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            form.add_error('email', 'No registered account found for this email.')
            return render(request, 'auth/forgot_password_request.html', {'form': form})

        otp = f'{secrets.randbelow(1000000):06d}'
        expiry_dt = timezone.now() + timedelta(minutes=PASSWORD_RESET_OTP_EXPIRY_MINUTES)
        _set_otp_session_data(
            request,
            {
                'user_id': user.id,
                'email': email,
                'otp': otp,
                'verified': False,
                'attempts': 0,
                'expires_at': expiry_dt.isoformat(),
            },
        )

        try:
            send_mail(
                subject='Fleet Hub Password Reset OTP',
                message=(
                    f'Your Fleet Hub OTP is {otp}. '
                    f'This code is valid for {PASSWORD_RESET_OTP_EXPIRY_MINUTES} minutes.'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
        except (smtplib.SMTPException, OSError, TimeoutError):
            _clear_otp_session_data(request)
            messages.error(request, 'Email service is currently unavailable. Please try again later.')
            return render(request, 'auth/forgot_password_request.html', {'form': form})
        messages.success(request, 'OTP sent to your email. Please verify to reset password.')
        return redirect('forgot_password_verify')

    return render(request, 'auth/forgot_password_request.html', {'form': form})


def forgot_password_verify(request):
    if request.user.is_authenticated:
        return redirect(role_redirect_name(request.user))

    otp_data = _get_otp_session_data(request)
    if not otp_data:
        messages.error(request, 'Start password reset by entering your registered email.')
        return redirect('forgot_password')

    if _otp_is_expired(otp_data):
        _clear_otp_session_data(request)
        messages.error(request, 'OTP expired. Please request a new OTP.')
        return redirect('forgot_password')

    form = ForgotPasswordOTPForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        entered_otp = form.cleaned_data['otp']
        if entered_otp != otp_data.get('otp'):
            otp_data['attempts'] = int(otp_data.get('attempts', 0)) + 1
            if otp_data['attempts'] >= PASSWORD_RESET_OTP_MAX_ATTEMPTS:
                _clear_otp_session_data(request)
                messages.error(request, 'Too many invalid attempts. Request a new OTP.')
                return redirect('forgot_password')
            _set_otp_session_data(request, otp_data)
            form.add_error('otp', 'Invalid OTP. Please try again.')
            return render(request, 'auth/forgot_password_verify.html', {'form': form, 'email': otp_data.get('email', '')})

        otp_data['verified'] = True
        _set_otp_session_data(request, otp_data)
        messages.success(request, 'OTP verified. Set your new password.')
        return redirect('forgot_password_reset')

    return render(request, 'auth/forgot_password_verify.html', {'form': form, 'email': otp_data.get('email', '')})


def forgot_password_reset(request):
    if request.user.is_authenticated:
        return redirect(role_redirect_name(request.user))

    otp_data = _get_otp_session_data(request)
    if not otp_data or not otp_data.get('verified'):
        messages.error(request, 'Verify OTP first to reset password.')
        return redirect('forgot_password')
    if _otp_is_expired(otp_data):
        _clear_otp_session_data(request)
        messages.error(request, 'OTP expired. Please request a new OTP.')
        return redirect('forgot_password')

    user_id = otp_data.get('user_id')
    user = User.objects.filter(id=user_id).first()
    if not user:
        _clear_otp_session_data(request)
        messages.error(request, 'Account not found. Please try again.')
        return redirect('forgot_password')

    form = OTPSetPasswordForm(user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        _clear_otp_session_data(request)
        messages.success(request, 'Password reset successful. Please login with your new password.')
        return redirect('login')

    return render(request, 'auth/forgot_password_reset.html', {'form': form, 'email': otp_data.get('email', '')})


@roles_required('admin')
def send_test_email(request):
    if request.method == 'POST':
        smtp_error = _smtp_configuration_error()
        if smtp_error:
            messages.error(request, f'SMTP is not configured: {smtp_error}')
            return redirect('dashboard')

        target_email = (request.user.email or '').strip()
        if not target_email:
            messages.error(request, 'Set your admin account email first, then retry test email.')
            return redirect('dashboard')
        try:
            send_mail(
                subject='Fleet Hub SMTP Test',
                message='SMTP is configured correctly. This is a Fleet Hub test email.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[target_email],
                fail_silently=False,
            )
            messages.success(request, f'Test email sent to {target_email}.')
        except (smtplib.SMTPException, OSError, TimeoutError):
            messages.error(request, 'SMTP test failed. Check email host/port/user/password/TLS settings.')
    return redirect('dashboard')


@roles_required('admin')
def manage_admin_invite_code(request):
    if request.method == 'POST':
        new_code = secrets.token_urlsafe(24)
        SystemSetting.set_value(ADMIN_INVITE_CODE_SETTING_KEY, new_code)
        messages.success(request, f'New admin invite code generated: {new_code}')
        return redirect('manage_admin_invite_code')

    current_code = get_admin_invite_code()
    if not current_code:
        current_code = secrets.token_urlsafe(24)
        SystemSetting.set_value(ADMIN_INVITE_CODE_SETTING_KEY, current_code)
    return render(
        request,
        'operations/manage_admin_invite_code.html',
        {'current_code': current_code},
    )


def register(request):
    if request.user.is_authenticated:
        return redirect(role_redirect_name(request.user))

    form = ClientRegistrationForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            user = form.save()
            role = form.cleaned_data.get('register_as', 'user')
            assign_role_groups(user, role)
            login(request, user)
            messages.success(request, 'Registration successful. Welcome to Fleet Hub.')
            return redirect(registration_redirect_name(role))
    return render(request, 'auth/register.html', {'form': form})


@roles_required('user')
def user_portal(request):
    active_trips = Trip.objects.filter(status=TripStatus.DISPATCHED).count()
    pending_shipments = Shipment.objects.filter(status='pending').count()
    return render(
        request,
        'operations/user_portal.html',
        {
            'active_trips': active_trips,
            'pending_shipments': pending_shipments,
        },
    )


@roles_required('admin', 'fleet_manager', 'dispatcher', 'safety_officer', 'financial_analyst')
def dashboard(request):
    vehicle_type = request.GET.get('vehicle_type')
    status = request.GET.get('status')
    region = request.GET.get('region')

    vehicles = Vehicle.objects.all()
    if vehicle_type:
        vehicles = vehicles.filter(vehicle_type=vehicle_type)
    if status:
        vehicles = vehicles.filter(status=status)
    if region:
        vehicles = vehicles.filter(region__iexact=region)

    total_fleet = vehicles.count()
    active_fleet = vehicles.filter(status=VehicleStatus.ON_TRIP).count()
    maintenance_alerts = vehicles.filter(status=VehicleStatus.IN_SHOP).count()
    utilization_rate = (Decimal(active_fleet) / Decimal(total_fleet) * Decimal('100')) if total_fleet else Decimal('0')
    pending_cargo = Shipment.objects.filter(status='pending').count()

    return render(
        request,
        'operations/dashboard.html',
        {
            'active_fleet': active_fleet,
            'maintenance_alerts': maintenance_alerts,
            'utilization_rate': round(utilization_rate, 2),
            'pending_cargo': pending_cargo,
            'vehicles': vehicles[:10],
            'vehicle_types': Vehicle._meta.get_field('vehicle_type').choices,
            'statuses': Vehicle._meta.get_field('status').choices,
        },
    )


@roles_required('admin', 'fleet_manager')
def vehicle_registry(request):
    form = VehicleForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'Vehicle saved successfully.')
            return redirect('vehicle_registry')
        messages.error(request, 'Please correct the highlighted vehicle form errors.')
    return render(request, 'operations/vehicle_registry.html', {'vehicles': Vehicle.objects.all(), 'vehicle_form': form})


@roles_required('admin', 'fleet_manager', 'dispatcher')
def trip_dispatcher(request):
    shipment_form = ShipmentForm(prefix='shipment')
    trip_form = TripForm(prefix='trip')
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_shipment':
            shipment_form = ShipmentForm(request.POST, prefix='shipment')
            if shipment_form.is_valid():
                shipment_form.save()
                messages.success(request, 'Shipment created successfully.')
                return redirect('trip_dispatcher')
            messages.error(request, 'Please correct shipment form errors.')
        elif action == 'create_trip':
            trip_form = TripForm(request.POST, prefix='trip')
            if trip_form.is_valid():
                trip_form.save()
                messages.success(request, 'Trip created successfully.')
                return redirect('trip_dispatcher')
            messages.error(request, 'Please correct trip form errors.')

    return render(
        request,
        'operations/trip_dispatcher.html',
        {
            'trips': Trip.objects.select_related('vehicle', 'driver').all(),
            'available_vehicles': Vehicle.objects.filter(status=VehicleStatus.AVAILABLE),
            'available_drivers': DriverProfile.objects.exclude(status='suspended'),
            'trip_form': trip_form,
            'shipment_form': shipment_form,
        },
    )


@roles_required('admin', 'fleet_manager')
def maintenance_logs(request):
    form = ServiceLogForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'Service log saved. Vehicle status auto-synced.')
            return redirect('maintenance_logs')
        messages.error(request, 'Please correct maintenance form errors.')
    return render(
        request,
        'operations/maintenance_logs.html',
        {'service_logs': ServiceLog.objects.select_related('vehicle').all(), 'service_form': form},
    )


@roles_required('admin', 'financial_analyst')
def expense_fuel_logs(request):
    form = FuelLogForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'Fuel log saved successfully.')
            return redirect('expense_fuel_logs')
        messages.error(request, 'Please correct fuel log form errors.')

    fuel_total = FuelLog.objects.aggregate(total=Sum('cost')).get('total') or Decimal('0.00')
    maintenance_total = ServiceLog.objects.aggregate(total=Sum('cost')).get('total') or Decimal('0.00')
    total_operational_cost = fuel_total + maintenance_total
    return render(
        request,
        'operations/expense_fuel_logs.html',
        {
            'fuel_logs': FuelLog.objects.select_related('vehicle', 'trip').all(),
            'fuel_total': fuel_total,
            'maintenance_total': maintenance_total,
            'total_operational_cost': total_operational_cost,
            'fuel_form': form,
        },
    )


@roles_required('admin', 'safety_officer')
def driver_profiles(request):
    form = DriverProfileForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'Driver profile saved successfully.')
            return redirect('driver_profiles')
        messages.error(request, 'Please correct driver form errors.')
    return render(request, 'operations/driver_profiles.html', {'drivers': DriverProfile.objects.all(), 'driver_form': form})


@roles_required('admin', 'financial_analyst')
def analytics_reports(request):
    completed_trips = Trip.objects.filter(status=TripStatus.COMPLETED)
    total_distance = completed_trips.aggregate(total=Sum('planned_distance_km')).get('total') or 0
    total_liters = FuelLog.objects.aggregate(total=Sum('liters')).get('total') or Decimal('0.00')
    fuel_efficiency = (Decimal(total_distance) / total_liters) if total_liters else Decimal('0.00')

    vehicles = Vehicle.objects.all()
    vehicle_rows = []
    for vehicle in vehicles:
        revenue = vehicle.trips.filter(status=TripStatus.COMPLETED).aggregate(total=Sum('revenue')).get('total') or Decimal('0.00')
        costs = vehicle.total_operational_cost
        acq = vehicle.acquisition_cost or Decimal('0.00')
        roi = ((revenue - costs) / acq) if acq else Decimal('0.00')
        vehicle_rows.append({'vehicle': vehicle, 'revenue': revenue, 'costs': costs, 'roi': round(roi, 4)})

    return render(request, 'operations/analytics_reports.html', {'fuel_efficiency': round(fuel_efficiency, 4), 'vehicle_rows': vehicle_rows})
