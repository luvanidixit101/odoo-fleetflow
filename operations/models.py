from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class VehicleType(models.TextChoices):
    TRUCK = 'truck', 'Truck'
    VAN = 'van', 'Van'
    BIKE = 'bike', 'Bike'


class VehicleStatus(models.TextChoices):
    AVAILABLE = 'available', 'Available'
    ON_TRIP = 'on_trip', 'On Trip'
    IN_SHOP = 'in_shop', 'In Shop'
    OUT_OF_SERVICE = 'out_of_service', 'Out of Service'


class DriverStatus(models.TextChoices):
    ON_DUTY = 'on_duty', 'On Duty'
    OFF_DUTY = 'off_duty', 'Off Duty'
    ON_TRIP = 'on_trip', 'On Trip'
    SUSPENDED = 'suspended', 'Suspended'


class TripStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    DISPATCHED = 'dispatched', 'Dispatched'
    COMPLETED = 'completed', 'Completed'
    CANCELLED = 'cancelled', 'Cancelled'


class ShipmentStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    ASSIGNED = 'assigned', 'Assigned'
    DELIVERED = 'delivered', 'Delivered'
    CANCELLED = 'cancelled', 'Cancelled'


class Vehicle(models.Model):
    name_model = models.CharField(max_length=120)
    license_plate = models.CharField(
        max_length=25,
        unique=True,
        validators=[RegexValidator(r'^[A-Za-z0-9-]+$', 'License plate can contain letters, numbers, and hyphen only.')],
    )
    vehicle_type = models.CharField(max_length=10, choices=VehicleType.choices)
    region = models.CharField(max_length=80, blank=True)
    max_load_capacity_kg = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    odometer_km = models.PositiveIntegerField(default=0)
    acquisition_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    retired = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=VehicleStatus.choices, default=VehicleStatus.AVAILABLE)

    class Meta:
        ordering = ['license_plate']

    def __str__(self):
        return f'{self.license_plate} - {self.name_model}'

    def save(self, *args, **kwargs):
        if self.retired:
            self.status = VehicleStatus.OUT_OF_SERVICE
        super().save(*args, **kwargs)

    @property
    def total_fuel_cost(self):
        value = self.fuel_logs.aggregate(total=Sum('cost')).get('total')
        return value or Decimal('0.00')

    @property
    def total_maintenance_cost(self):
        value = self.service_logs.aggregate(total=Sum('cost')).get('total')
        return value or Decimal('0.00')

    @property
    def total_operational_cost(self):
        return self.total_fuel_cost + self.total_maintenance_cost


class DriverProfile(models.Model):
    full_name = models.CharField(max_length=120)
    license_number = models.CharField(max_length=60, unique=True)
    licensed_for = models.CharField(max_length=10, choices=VehicleType.choices)
    license_expiry_date = models.DateField()
    safety_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('100.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
    )
    status = models.CharField(max_length=20, choices=DriverStatus.choices, default=DriverStatus.OFF_DUTY)

    class Meta:
        ordering = ['full_name']

    def __str__(self):
        return self.full_name

    def is_license_valid_for(self, vehicle_type):
        today = timezone.localdate()
        return self.license_expiry_date >= today and self.licensed_for == vehicle_type

    @property
    def completion_rate(self):
        total = self.trips.count()
        if not total:
            return Decimal('0.00')
        completed = self.trips.filter(status=TripStatus.COMPLETED).count()
        return (Decimal(completed) / Decimal(total)) * Decimal('100.00')


class Shipment(models.Model):
    reference_code = models.CharField(max_length=40, unique=True)
    origin = models.CharField(max_length=120)
    destination = models.CharField(max_length=120)
    cargo_weight_kg = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    status = models.CharField(max_length=20, choices=ShipmentStatus.choices, default=ShipmentStatus.PENDING)

    class Meta:
        ordering = ['reference_code']

    def __str__(self):
        return self.reference_code


class Trip(models.Model):
    trip_code = models.CharField(max_length=40, unique=True)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name='trips')
    driver = models.ForeignKey(DriverProfile, on_delete=models.PROTECT, related_name='trips')
    shipment = models.ForeignKey(Shipment, on_delete=models.SET_NULL, null=True, blank=True, related_name='trips')
    cargo_weight_kg = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    planned_distance_km = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    final_odometer_km = models.PositiveIntegerField(null=True, blank=True)
    revenue = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    status = models.CharField(max_length=20, choices=TripStatus.choices, default=TripStatus.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.trip_code

    def clean(self):
        if not self.vehicle_id or not self.driver_id:
            return

        if self.cargo_weight_kg > self.vehicle.max_load_capacity_kg:
            raise ValidationError('Trip cannot be created: cargo exceeds vehicle max capacity.')

        if not self.driver.is_license_valid_for(self.vehicle.vehicle_type):
            raise ValidationError('Driver license is expired or not valid for this vehicle type.')

        if self.driver.status == DriverStatus.SUSPENDED:
            raise ValidationError('Suspended drivers cannot be assigned.')

        if self.status == TripStatus.DISPATCHED:
            if self.vehicle.status != VehicleStatus.AVAILABLE:
                raise ValidationError('Vehicle must be available to dispatch.')
            if self.driver.status not in [DriverStatus.ON_DUTY, DriverStatus.OFF_DUTY]:
                raise ValidationError('Driver is not available for dispatch.')

        if self.status == TripStatus.COMPLETED and self.final_odometer_km is None:
            raise ValidationError('Final odometer is required to complete a trip.')

        if self.final_odometer_km is not None and self.final_odometer_km < self.vehicle.odometer_km:
            raise ValidationError('Final odometer cannot be less than the current vehicle odometer.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        self.sync_statuses()

    def sync_statuses(self):
        if self.status == TripStatus.DISPATCHED:
            Vehicle.objects.filter(pk=self.vehicle_id).update(status=VehicleStatus.ON_TRIP)
            DriverProfile.objects.filter(pk=self.driver_id).update(status=DriverStatus.ON_TRIP)
            if self.shipment_id:
                Shipment.objects.filter(pk=self.shipment_id).update(status=ShipmentStatus.ASSIGNED)

        if self.status in [TripStatus.COMPLETED, TripStatus.CANCELLED]:
            if self.final_odometer_km and self.final_odometer_km > self.vehicle.odometer_km:
                Vehicle.objects.filter(pk=self.vehicle_id).update(odometer_km=self.final_odometer_km)

            has_open_service = self.vehicle.service_logs.filter(is_open=True).exists()
            if self.vehicle.status != VehicleStatus.OUT_OF_SERVICE and not has_open_service:
                Vehicle.objects.filter(pk=self.vehicle_id).update(status=VehicleStatus.AVAILABLE)

            if self.driver.status != DriverStatus.SUSPENDED:
                DriverProfile.objects.filter(pk=self.driver_id).update(status=DriverStatus.ON_DUTY)

            if self.shipment_id:
                shipment_status = ShipmentStatus.DELIVERED if self.status == TripStatus.COMPLETED else ShipmentStatus.CANCELLED
                Shipment.objects.filter(pk=self.shipment_id).update(status=shipment_status)

            if self.status == TripStatus.COMPLETED and not self.completed_at:
                self.completed_at = timezone.now()
                Trip.objects.filter(pk=self.pk).update(completed_at=self.completed_at)


class ServiceLog(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='service_logs')
    service_type = models.CharField(max_length=120)
    service_date = models.DateField(default=timezone.localdate)
    cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    notes = models.TextField(blank=True)
    is_open = models.BooleanField(default=True)

    class Meta:
        ordering = ['-service_date']

    def __str__(self):
        return f'{self.vehicle.license_plate} - {self.service_type}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.sync_vehicle_status()

    def sync_vehicle_status(self):
        if self.vehicle.status == VehicleStatus.OUT_OF_SERVICE:
            return

        if self.is_open:
            Vehicle.objects.filter(pk=self.vehicle_id).update(status=VehicleStatus.IN_SHOP)
            return

        has_open_logs = self.vehicle.service_logs.filter(is_open=True).exclude(pk=self.pk).exists()
        has_active_trip = self.vehicle.trips.filter(status=TripStatus.DISPATCHED).exists()
        if not has_open_logs and not has_active_trip:
            Vehicle.objects.filter(pk=self.vehicle_id).update(status=VehicleStatus.AVAILABLE)


class FuelLog(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='fuel_logs')
    trip = models.ForeignKey(Trip, on_delete=models.SET_NULL, null=True, blank=True, related_name='fuel_logs')
    liters = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    cost = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    logged_on = models.DateField(default=timezone.localdate)
    odometer_km = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-logged_on']

    def __str__(self):
        return f'{self.vehicle.license_plate} fuel {self.logged_on}'

    def clean(self):
        if self.trip_id and self.trip.vehicle_id != self.vehicle_id:
            raise ValidationError('Fuel log vehicle must match trip vehicle.')


class SystemSetting(models.Model):
    key = models.CharField(max_length=120, unique=True)
    value = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['key']

    def __str__(self):
        return self.key

    @classmethod
    def get_value(cls, key, default=''):
        record = cls.objects.filter(key=key).first()
        if record:
            return record.value
        return default

    @classmethod
    def set_value(cls, key, value):
        obj, _ = cls.objects.update_or_create(key=key, defaults={'value': value})
        return obj
