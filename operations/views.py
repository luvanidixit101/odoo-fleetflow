from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import redirect, render

from .forms import ClientRegistrationForm, DriverProfileForm, FuelLogForm, ServiceLogForm, ShipmentForm, TripForm, VehicleForm
from .models import DriverProfile, FuelLog, ServiceLog, Shipment, Trip, TripStatus, Vehicle, VehicleStatus


def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    form = ClientRegistrationForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Registration successful. Welcome to Fleet Hub.')
            return redirect('dashboard')
        messages.error(request, 'Please correct the registration form errors.')
    return render(request, 'auth/register.html', {'form': form})


@login_required
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


@login_required
def vehicle_registry(request):
    form = VehicleForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'Vehicle saved successfully.')
            return redirect('vehicle_registry')
        messages.error(request, 'Please correct the highlighted vehicle form errors.')
    return render(request, 'operations/vehicle_registry.html', {'vehicles': Vehicle.objects.all(), 'vehicle_form': form})


@login_required
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


@login_required
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


@login_required
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


@login_required
def driver_profiles(request):
    form = DriverProfileForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'Driver profile saved successfully.')
            return redirect('driver_profiles')
        messages.error(request, 'Please correct driver form errors.')
    return render(request, 'operations/driver_profiles.html', {'drivers': DriverProfile.objects.all(), 'driver_form': form})


@login_required
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
