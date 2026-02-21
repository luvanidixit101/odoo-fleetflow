from decimal import Decimal
import os
import socket

from django import forms
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm, UserCreationForm
from django.contrib.auth.models import User
from django.core.validators import validate_email
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone

from .models import DriverProfile, FuelLog, ServiceLog, Shipment, SystemSetting, Trip, Vehicle, VehicleStatus


ADMIN_INVITE_CODE_SETTING_KEY = 'admin_registration_token'


class BootstrapModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'form-check-input'
            elif isinstance(field.widget, forms.DateInput):
                field.widget.attrs['class'] = 'form-control'
            elif isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                field.widget.attrs['class'] = 'form-select'
            else:
                field.widget.attrs['class'] = 'form-control'


class VehicleForm(BootstrapModelForm):
    class Meta:
        model = Vehicle
        fields = [
            'name_model',
            'license_plate',
            'vehicle_type',
            'region',
            'max_load_capacity_kg',
            'odometer_km',
            'acquisition_cost',
            'retired',
            'status',
        ]


class DriverProfileForm(BootstrapModelForm):
    class Meta:
        model = DriverProfile
        fields = ['full_name', 'license_number', 'licensed_for', 'license_expiry_date', 'safety_score', 'status']
        widgets = {'license_expiry_date': forms.DateInput(attrs={'type': 'date'})}

    def clean_safety_score(self):
        score = self.cleaned_data['safety_score']
        if score < Decimal('0') or score > Decimal('100'):
            raise forms.ValidationError('Safety score must be between 0 and 100.')
        return score


class ShipmentForm(BootstrapModelForm):
    class Meta:
        model = Shipment
        fields = ['reference_code', 'origin', 'destination', 'cargo_weight_kg', 'status']

    def clean(self):
        data = super().clean()
        if data.get('origin') and data.get('destination') and data['origin'].strip().lower() == data['destination'].strip().lower():
            raise forms.ValidationError('Origin and destination cannot be the same.')
        return data


class TripForm(BootstrapModelForm):
    class Meta:
        model = Trip
        fields = [
            'trip_code',
            'vehicle',
            'driver',
            'shipment',
            'cargo_weight_kg',
            'planned_distance_km',
            'final_odometer_km',
            'revenue',
            'status',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['vehicle'].queryset = Vehicle.objects.exclude(status=VehicleStatus.OUT_OF_SERVICE)
        self.fields['shipment'].required = False


class ServiceLogForm(BootstrapModelForm):
    class Meta:
        model = ServiceLog
        fields = ['vehicle', 'service_type', 'service_date', 'cost', 'notes', 'is_open']
        widgets = {'service_date': forms.DateInput(attrs={'type': 'date'})}


class FuelLogForm(BootstrapModelForm):
    class Meta:
        model = FuelLog
        fields = ['vehicle', 'trip', 'liters', 'cost', 'logged_on', 'odometer_km']
        widgets = {'logged_on': forms.DateInput(attrs={'type': 'date'})}

    def clean_logged_on(self):
        logged_on = self.cleaned_data['logged_on']
        if logged_on > timezone.localdate():
            raise forms.ValidationError('Fuel log date cannot be in the future.')
        return logged_on


class ClientRegistrationForm(UserCreationForm):
    ACCOUNT_ROLE_CHOICES = (
        ('user', 'User'),
        ('admin', 'Admin'),
        ('fleet_manager', 'Fleet Managers'),
        ('dispatcher', 'Dispatchers'),
        ('safety_officer', 'Safety Officers'),
        ('financial_analyst', 'Financial Analysts'),
    )

    register_as = forms.ChoiceField(
        label='Register as',
        choices=ACCOUNT_ROLE_CHOICES,
        initial='user',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    admin_invite_code = forms.CharField(
        label='Admin Invite Code',
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Required only for admin registration'}),
    )
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)

    class Meta:
        model = User
        fields = (
            'register_as',
            'admin_invite_code',
            'username',
            'email',
            'first_name',
            'last_name',
            'password1',
            'password2',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
        self.fields['first_name'].widget.attrs['autocomplete'] = 'off'
        self.fields['last_name'].widget.attrs['autocomplete'] = 'off'

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        try:
            validate_email(email)
        except DjangoValidationError:
            raise forms.ValidationError('Enter a valid email address.')

        if '@' not in email:
            raise forms.ValidationError('Email must contain a valid domain name.')

        domain = email.split('@', 1)[1].strip().lower()
        parts = domain.split('.')
        if len(parts) < 2:
            raise forms.ValidationError('Email domain must include a valid extension (example: company.com).')

        for part in parts:
            if not part or part.startswith('-') or part.endswith('-'):
                raise forms.ValidationError('Email domain format is invalid.')

        # Basic DNS existence check for domain.
        try:
            socket.getaddrinfo(domain, None)
        except socket.gaierror:
            raise forms.ValidationError('Email domain does not appear to exist.')

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('This email is already registered.')
        return email

    def clean_username(self):
        username = self.cleaned_data['username'].strip().lower()
        if len(username) < 4:
            raise forms.ValidationError('Username must be at least 4 characters.')
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('This username is already taken. Please choose another.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('register_as', 'user')
        invite_code = (cleaned_data.get('admin_invite_code') or '').strip()
        expected_code = (
            SystemSetting.get_value(
                ADMIN_INVITE_CODE_SETTING_KEY,
                (os.getenv('ADMIN_REGISTRATION_TOKEN', '') or '').strip(),
            )
            or ''
        ).strip()

        if role == 'admin':
            if not expected_code or invite_code != expected_code:
                raise forms.ValidationError('Authentication failed. Please check your registration details and try again.')
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        role = self.cleaned_data.get('register_as', 'user')
        user.is_staff = role == 'admin'
        user.is_superuser = False
        if commit:
            user.save()
        return user


class ClientLoginForm(AuthenticationForm):
    USER_ROLE_CHOICES = (
        ('user', 'User'),
        ('admin', 'Admin'),
        ('fleet_manager', 'Fleet Managers'),
        ('dispatcher', 'Dispatchers'),
        ('safety_officer', 'Safety Officers'),
        ('financial_analyst', 'Financial Analysts'),
    )

    login_as = forms.ChoiceField(
        label='Login as',
        choices=USER_ROLE_CHOICES,
        initial='user',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    username = forms.CharField(
        label='Email / Username',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter username or email'}),
    )
    password = forms.CharField(
        label='Password',
        strip=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter password'}),
    )


class ForgotPasswordEmailForm(forms.Form):
    email = forms.EmailField(
        label='Registered Email',
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter registered email'}),
    )


class ForgotPasswordOTPForm(forms.Form):
    otp = forms.CharField(
        label='OTP Code',
        min_length=6,
        max_length=6,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter 6-digit OTP'}),
    )

    def clean_otp(self):
        value = (self.cleaned_data.get('otp') or '').strip()
        if not value.isdigit():
            raise forms.ValidationError('OTP must contain only digits.')
        return value


class OTPSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['new_password1'].widget.attrs.update(
            {'class': 'form-control', 'placeholder': 'Enter new password'}
        )
        self.fields['new_password2'].widget.attrs.update(
            {'class': 'form-control', 'placeholder': 'Confirm new password'}
        )
