from decimal import Decimal

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import DriverProfile, FuelLog, ServiceLog, Shipment, Trip, Vehicle, VehicleStatus


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
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('This email is already registered.')
        return email
