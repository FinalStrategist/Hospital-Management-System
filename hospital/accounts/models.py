from datetime import date
import uuid
from django.db import models
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.db.models.signals import post_save
from datetime import datetime, timedelta
from django.dispatch import receiver

class UserProfile(models.Model):
    USER_TYPES = (
        ('admin', 'Admin'),
        ('receptionist', 'Receptionist'),
        ('doctor', 'Doctor'),
        ('patient', 'Patient'),
    )
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    user_type = models.CharField(max_length=20, choices=USER_TYPES, default='patient')
    phone_number = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.get_user_type_display()}"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()

# Receptionist model (extends UserProfile)
class Receptionist(models.Model):
    user_profile = models.OneToOneField(UserProfile, on_delete=models.CASCADE, related_name='receptionist_details')
    employee_id = models.CharField(max_length=20, unique=True)
    hire_date = models.DateField(auto_now_add=True)
    
    def __str__(self):
        return f"Receptionist: {self.user_profile.user.username}"

# Doctor model
class Doctor(models.Model):
    user_profile = models.OneToOneField(UserProfile, on_delete=models.CASCADE, related_name='doctor_details')
    employee_id = models.CharField(max_length=20, unique=True)
    specialization = models.CharField(max_length=100)
    license_number = models.CharField(max_length=50, unique=True)
    
    def __str__(self):
        return f"Dr. {self.user_profile.user.get_full_name()} - {self.specialization}"

# Patient model
class Patient(models.Model):
    user_profile = models.OneToOneField(UserProfile, on_delete=models.CASCADE, related_name='patient_details')
    patient_id = models.CharField(max_length=20, unique=True)
    emergency_contact = models.CharField(max_length=100)
    blood_group = models.CharField(max_length=5, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_patients')
    
    def __str__(self):
        return f"Patient: {self.user_profile.user.get_full_name()}"


class DoctorSchedule(models.Model):
    DAYS_OF_WEEK = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='schedules')
    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK)
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_duration = models.IntegerField(default=30, help_text="Duration in minutes")
    is_available = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['doctor', 'day_of_week']
        ordering = ['day_of_week', 'start_time']
    
    def __str__(self):
        return f"{self.doctor} - {self.get_day_of_week_display()} {self.start_time}-{self.end_time}"

class Appointment(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ]
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='appointments')
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='appointments')
    schedule = models.ForeignKey(DoctorSchedule, on_delete=models.SET_NULL, null=True, related_name='appointments')
    appointment_date = models.DateField()
    start_time = models.TimeField()
    consultation_fee = models.DecimalField(max_digits=10, decimal_places=2, default=1500.00, help_text="Consultation fee in KES")
    end_time = models.TimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_appointments')
    
    class Meta:
        ordering = ['-appointment_date', '-start_time']
        unique_together = ['doctor', 'appointment_date', 'start_time']  # Prevent double booking
    
    def __str__(self):
        return f"{self.patient} with {self.doctor} on {self.appointment_date} at {self.start_time}"
    
    @property
    def is_past(self):
        appointment_datetime = datetime.combine(self.appointment_date, self.start_time)
        return appointment_datetime < timezone.now()
    
    @property
    def can_cancel(self):
        if self.status in ['cancelled', 'completed']:
            return False
        # Can cancel up to 2 hours before appointment
        appointment_datetime = datetime.combine(self.appointment_date, self.start_time)
        appointment_datetime = timezone.make_aware(appointment_datetime)  
        time_diff = appointment_datetime - timezone.now()
        return time_diff.total_seconds() > 7200  # 2 hours in seconds

class TimeOff(models.Model):
    """Doctor's time off (vacation, sick leave, etc.)"""
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='time_offs')
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=200)
    is_approved = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.doctor} - {self.start_date} to {self.end_date}"
    
class Medication(models.Model):
    """Master list of medications"""
    name = models.CharField(max_length=200)
    generic_name = models.CharField(max_length=200, blank=True)
    manufacturer = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    common_dosages = models.CharField(max_length=200, help_text="e.g., 250mg, 500mg", blank=True)
    side_effects = models.TextField(blank=True)
    contraindications = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name

class Prescription(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('discontinued', 'Discontinued'),
        ('expired', 'Expired'),
    ]
    
    prescription_id = models.CharField(max_length=20, unique=True, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='prescriptions')
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='prescriptions')
    diagnosis = models.TextField(help_text="Diagnosis or reason for prescription")
    notes = models.TextField(blank=True, help_text="Additional instructions or notes")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    valid_until = models.DateField(null=True, blank=True, help_text="Prescription expiry date")
    refills_allowed = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    refills_used = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    is_emergency = models.BooleanField(default=False, help_text="Emergency prescription")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_prescriptions')
    
    class Meta:
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        if not self.prescription_id:
            # Generate prescription ID: PRES-YYYYMMDD-XXXX
            date_str = date.today().strftime('%Y%m%d')
            last_prescription = Prescription.objects.filter(
                prescription_id__startswith=f"PRES-{date_str}"
            ).order_by('prescription_id').last()
            
            if last_prescription:
                last_num = int(last_prescription.prescription_id.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            
            self.prescription_id = f"PRES-{date_str}-{new_num:04d}"
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.prescription_id} - {self.patient} - Dr. {self.doctor}"
    
    @property
    def is_active(self):
        if self.status != 'active':
            return False
        if self.valid_until and self.valid_until < date.today():
            return False
        if self.refills_used >= self.refills_allowed:
            return False
        return True
    
    @property
    def remaining_refills(self):
        return max(0, self.refills_allowed - self.refills_used)

class PrescriptionItem(models.Model):
    DOSAGE_FORM_CHOICES = [
        ('tablet', 'Tablet'),
        ('capsule', 'Capsule'),
        ('liquid', 'Liquid'),
        ('injection', 'Injection'),
        ('cream', 'Cream'),
        ('ointment', 'Ointment'),
        ('drops', 'Drops'),
        ('inhaler', 'Inhaler'),
        ('other', 'Other'),
    ]
    
    FREQUENCY_CHOICES = [
        ('OD', 'Once daily'),
        ('BD', 'Twice daily'),
        ('TID', 'Three times daily'),
        ('QID', 'Four times daily'),
        ('QHS', 'At bedtime'),
        ('Q4H', 'Every 4 hours'),
        ('Q6H', 'Every 6 hours'),
        ('Q8H', 'Every 8 hours'),
        ('PRN', 'As needed'),
        ('STAT', 'Immediately'),
        ('OTHER', 'Other'),
    ]
    
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name='items')
    medication = models.ForeignKey(Medication, on_delete=models.PROTECT, related_name='prescriptions')
    medication_name = models.CharField(max_length=200, help_text="Custom medication name if not in master list")
    dosage = models.CharField(max_length=100, help_text="e.g., 500mg")
    dosage_form = models.CharField(max_length=20, choices=DOSAGE_FORM_CHOICES, default='tablet')
    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES, default='OD')
    custom_frequency = models.CharField(max_length=100, blank=True, help_text="Custom frequency if OTHER selected")
    duration = models.CharField(max_length=100, help_text="e.g., 7 days, 2 weeks, 1 month")
    quantity = models.IntegerField(validators=[MinValueValidator(1)], help_text="Total quantity to dispense")
    refills = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    instructions = models.TextField(blank=True, help_text="Special instructions for taking this medication")
    route = models.CharField(max_length=50, default="Oral", help_text="e.g., Oral, Topical, Intravenous")
    
    class Meta:
        ordering = ['id']
    
    def __str__(self):
        return f"{self.medication_name} - {self.dosage} {self.get_frequency_display()}"

class PrescriptionFill(models.Model):
    """Track when prescriptions are filled"""
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name='fills')
    filled_date = models.DateField(auto_now_add=True)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    pharmacy_name = models.CharField(max_length=200, blank=True)
    pharmacy_phone = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    filled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='prescription_fills')
    
    class Meta:
        ordering = ['-filled_date']
    
    def __str__(self):
        return f"{self.prescription.prescription_id} - Fill on {self.filled_date}"
    

class Invoice(models.Model):
    """Invoice for appointments/services"""
    INVOICE_STATUS = [
        ('draft', 'Draft'),
        ('pending', 'Pending Payment'),
        ('paid', 'Paid'),
        ('partially_paid', 'Partially Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]
    
    invoice_number = models.CharField(max_length=20, unique=True, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='invoices')
    appointment = models.ForeignKey(Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_invoices')
    
    # Invoice details
    issue_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=INVOICE_STATUS, default='pending')
    
    # Amounts
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="VAT/TAX amount")
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Notes
    notes = models.TextField(blank=True)
    payment_instructions = models.TextField(blank=True, default="Pay via M-Pesa Paybill: 174379, Account: [Invoice Number]")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-issue_date', '-created_at']
    
    def save(self, *args, **kwargs):
        if not self.invoice_number:
            # Generate invoice number: INV-YYYYMMDD-XXXX
            date_str = timezone.now().strftime('%Y%m%d')
            last_invoice = Invoice.objects.filter(
                invoice_number__startswith=f"INV-{date_str}"
            ).order_by('invoice_number').last()
            
            if last_invoice:
                last_num = int(last_invoice.invoice_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            
            self.invoice_number = f"INV-{date_str}-{new_num:04d}"
        
        # Calculate balance
        self.balance = self.total_amount - self.amount_paid
        
        # Update status based on payment
        if self.amount_paid >= self.total_amount:
            self.status = 'paid'
        elif self.amount_paid > 0:
            self.status = 'partially_paid'
        elif self.due_date < timezone.now().date() and self.status == 'pending':
            self.status = 'overdue'
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.invoice_number} - {self.patient} - KES {self.total_amount}"
    
    @property
    def is_paid(self):
        return self.status == 'paid'
    
    @property
    def payment_progress(self):
        if self.total_amount == 0:
            return 0
        return int((self.amount_paid / self.total_amount) * 100)

class InvoiceItem(models.Model):
    """Individual line items on an invoice"""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=255)
    quantity = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    
    def save(self, *args, **kwargs):
        self.total = self.quantity * self.unit_price
        super().save(*args, **kwargs)
        # Update invoice totals
        self.update_invoice_totals()
    
    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self.update_invoice_totals()
    
    def update_invoice_totals(self):
        """Update the parent invoice totals"""
        invoice = self.invoice
        items = invoice.items.all()
        invoice.subtotal = sum(item.total for item in items)
        invoice.total_amount = invoice.subtotal + invoice.tax - invoice.discount
        invoice.save()
    
    def __str__(self):
        return f"{self.description} - KES {self.total}"

class MpesaTransaction(models.Model):
    """Track M-Pesa transactions"""
    TRANSACTION_STATUS = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Transaction identifiers
    merchant_request_id = models.CharField(max_length=100, unique=True)
    checkout_request_id = models.CharField(max_length=100, unique=True)
    transaction_id = models.CharField(max_length=50, blank=True, null=True, unique=True)  # M-Pesa receipt number
    
    # Transaction details
    phone_number = models.CharField(max_length=15)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    account_reference = models.CharField(max_length=50)  # Invoice number or reference
    transaction_desc = models.CharField(max_length=200)
    
    # Status
    status = models.CharField(max_length=20, choices=TRANSACTION_STATUS, default='pending')
    result_code = models.IntegerField(null=True, blank=True)
    result_desc = models.TextField(blank=True)
    
    # Related invoice (optional)
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='mpesa_transactions')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.transaction_id or 'Pending'} - KES {self.amount} - {self.phone_number}"

class Payment(models.Model):
    """Record of payments received"""
    PAYMENT_METHODS = [
        ('mpesa', 'M-Pesa'),
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('bank', 'Bank Transfer'),
        ('insurance', 'Insurance'),
        ('other', 'Other'),
    ]
    
    payment_number = models.CharField(max_length=20, unique=True, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    mpesa_transaction = models.OneToOneField(MpesaTransaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='payment')
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='mpesa')
    reference = models.CharField(max_length=100, blank=True, help_text="Payment reference (M-Pesa receipt, cheque number, etc.)")
    
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='received_payments')
    notes = models.TextField(blank=True)
    
    payment_date = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-payment_date']
    
    def save(self, *args, **kwargs):
        if not self.payment_number:
            # Generate payment number: PAY-YYYYMMDD-XXXX
            date_str = timezone.now().strftime('%Y%m%d')
            last_payment = Payment.objects.filter(
                payment_number__startswith=f"PAY-{date_str}"
            ).order_by('payment_number').last()
            
            if last_payment:
                last_num = int(last_payment.payment_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            
            self.payment_number = f"PAY-{date_str}-{new_num:04d}"
        
        super().save(*args, **kwargs)
        
        # Update invoice paid amount
        invoice = self.invoice
        invoice.amount_paid = invoice.payments.aggregate(total=models.Sum('amount'))['total'] or 0
        invoice.save()
    
    def __str__(self):
        return f"{self.payment_number} - KES {self.amount} - {self.payment_method}"