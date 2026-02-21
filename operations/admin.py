from django.contrib import admin

from .models import SystemSetting


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'updated_at')
    search_fields = ('key',)

from .models import DriverProfile, FuelLog, ServiceLog, Shipment, Trip, Vehicle


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('license_plate', 'name_model', 'vehicle_type', 'status', 'max_load_capacity_kg', 'odometer_km')
    list_filter = ('vehicle_type', 'status', 'region', 'retired')
    search_fields = ('license_plate', 'name_model')


@admin.register(DriverProfile)
class DriverProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'license_number', 'licensed_for', 'license_expiry_date', 'status', 'safety_score')
    list_filter = ('licensed_for', 'status')
    search_fields = ('full_name', 'license_number')


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ('reference_code', 'origin', 'destination', 'cargo_weight_kg', 'status')
    list_filter = ('status',)
    search_fields = ('reference_code', 'origin', 'destination')


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ('trip_code', 'vehicle', 'driver', 'cargo_weight_kg', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('trip_code', 'vehicle__license_plate', 'driver__full_name')


@admin.register(ServiceLog)
class ServiceLogAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'service_type', 'service_date', 'cost', 'is_open')
    list_filter = ('is_open', 'service_date')
    search_fields = ('vehicle__license_plate', 'service_type')


@admin.register(FuelLog)
class FuelLogAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'trip', 'liters', 'cost', 'logged_on')
    list_filter = ('logged_on',)
