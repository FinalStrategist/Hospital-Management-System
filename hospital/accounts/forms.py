from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UserProfile, Receptionist, Patient, Appointment, Doctor, DoctorSchedule, TimeOff, Prescription, PrescriptionItem, Medication, PrescriptionFill
from datetime import date, datetime, timedelta
from django.forms import inlineformset_factory
import re

class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    user_type = forms.ChoiceField(choices=UserProfile.USER_TYPES, required=True)
    phone_number = forms.CharField(max_length=15, required=False)
    address = forms.CharField(widget=forms.Textarea, required=False)
    
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        
        if commit:
            user.save()
            # Update profile
            user.profile.user_type = self.cleaned_data['user_type']
            user.profile.phone_number = self.cleaned_data['phone_number']
            user.profile.address = self.cleaned_data['address']
            user.profile.save()
            
            # Create role-specific profile
            if self.cleaned_data['user_type'] == 'receptionist':
                Receptionist.objects.create(
                    user_profile=user.profile,
                    employee_id=f"REC{user.id:04d}"
                )
            elif self.cleaned_data['user_type'] == 'doctor':
                Doctor.objects.create(
                    user_profile=user.profile,
                    employee_id=f"DOC{user.id:04d}",
                    specialization="General",
                    license_number=f"LIC{user.id:06d}"
                )
            elif self.cleaned_data['user_type'] == 'patient':
                Patient.objects.create(
                    user_profile=user.profile,
                    patient_id=f"PAT{user.id:04d}",
                    emergency_contact="",
                    blood_group="",
                    created_by=None
                )
        
        return user

class PatientCreationForm(forms.ModelForm):
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=30)
    last_name = forms.CharField(max_length=30)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput, required=False)
    phone_number = forms.CharField(max_length=15, required=False)
    address = forms.CharField(widget=forms.Textarea, required=False)
    emergency_contact = forms.CharField(max_length=100)
    blood_group = forms.CharField(max_length=5, required=False)
    
    class Meta:
        model = Patient
        fields = ['emergency_contact', 'blood_group']
    
    def save(self, commit=True, created_by=None):
        # Create user first
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password'] or 'defaultpass123',
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name']
        )
        
        # Update profile
        user.profile.user_type = 'patient'
        user.profile.phone_number = self.cleaned_data['phone_number']
        user.profile.address = self.cleaned_data['address']
        user.profile.save()
        
        # Create patient
        patient = super().save(commit=False)
        patient.user_profile = user.profile
        patient.patient_id = f"PAT{user.id:04d}"
        patient.created_by = created_by
        
        if commit:
            patient.save()
        
        return patient
    
class AppointmentBookingForm(forms.ModelForm):
    doctor = forms.ModelChoiceField(
        queryset=Doctor.objects.all(),
        empty_label="Select a Doctor",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    appointment_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        help_text="Select a date"
    )
    time_slot = forms.ChoiceField(
        choices=[],  # Will be populated dynamically
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=True,  # Should be required!
        help_text="Select available time slot"
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        required=False,
        help_text="Reason for visit (optional)"
    )
    
    class Meta:
        model = Appointment
        fields = ['doctor', 'appointment_date', 'time_slot', 'reason']
    
    def __init__(self, *args, **kwargs):
        self.patient = kwargs.pop('patient', None)
        super().__init__(*args, **kwargs)
        
        # Make time_slot required
        self.fields['time_slot'].required = True
        
        # If this is a POST request, try to populate choices from the submitted data
        if self.data.get('doctor') and self.data.get('appointment_date'):
            try:
                doctor_id = int(self.data.get('doctor'))
                appointment_date = datetime.strptime(self.data.get('appointment_date'), '%Y-%m-%d').date()
                
                # Fetch available slots for this doctor and date
                available_slots = self.get_available_slots(doctor_id, appointment_date)
                self.fields['time_slot'].choices = available_slots
            except (ValueError, TypeError):
                self.fields['time_slot'].choices = []
        
        # If editing an existing appointment, populate time_slot
        elif self.instance.pk:
            self.fields['time_slot'].choices = [
                (f"{self.instance.start_time}", 
                 f"{self.instance.start_time.strftime('%I:%M %p')} - {self.instance.end_time.strftime('%I:%M %p')}")
            ]
    
    def get_available_slots(self, doctor_id, appointment_date):
        """Helper method to fetch available slots"""
        from .models import Doctor, DoctorSchedule, TimeOff, Appointment
        
        try:
            doctor = Doctor.objects.get(id=doctor_id)
            day_of_week = appointment_date.weekday()
            
            # Get doctor's schedule for that day
            schedules = DoctorSchedule.objects.filter(
                doctor=doctor,
                day_of_week=day_of_week,
                is_available=True
            )
            
            if not schedules.exists():
                return [('', 'Doctor not available on this day')]
            
            # Check if doctor is on time off
            on_time_off = TimeOff.objects.filter(
                doctor=doctor,
                start_date__lte=appointment_date,
                end_date__gte=appointment_date,
                is_approved=True
            ).exists()
            
            if on_time_off:
                return [('', 'Doctor is on time off on this date')]
            
            # Get all booked appointments for this doctor on this date
            booked_appointments = Appointment.objects.filter(
                doctor=doctor,
                appointment_date=appointment_date,
                status__in=['scheduled', 'confirmed']
            ).values_list('start_time', flat=True)
            
            # Generate available time slots
            available_slots = [('', '-- Select a time slot --')]
            
            for schedule in schedules:
                current_time = datetime.combine(appointment_date, schedule.start_time)
                end_time = datetime.combine(appointment_date, schedule.end_time)
                slot_duration = timedelta(minutes=schedule.slot_duration)
                
                while current_time + slot_duration <= end_time:
                    start_time = current_time.time()
                    
                    # Check if slot is not booked
                    if start_time not in booked_appointments:
                        # Don't show past slots for today
                        if appointment_date == date.today() and current_time <= datetime.now():
                            current_time += slot_duration
                            continue
                        
                        end_time_slot = (current_time + slot_duration).time()
                        slot_value = start_time.strftime('%H:%M:%S')
                        slot_display = f"{start_time.strftime('%I:%M %p')} - {end_time_slot.strftime('%I:%M %p')}"
                        available_slots.append((slot_value, slot_display))
                    
                    current_time += slot_duration
            
            if len(available_slots) == 1:  # Only the placeholder
                return [('', 'No available slots for this date')]
            
            return available_slots
            
        except Doctor.DoesNotExist:
            return [('', 'Doctor not found')]
    
    def clean(self):
        cleaned_data = super().clean()
        doctor = cleaned_data.get('doctor')
        appointment_date = cleaned_data.get('appointment_date')
        time_slot_str = cleaned_data.get('time_slot')
        
        # Check if all required fields are present
        if not doctor:
            raise forms.ValidationError("Please select a doctor.")
        if not appointment_date:
            raise forms.ValidationError("Please select a date.")
        if not time_slot_str:
            raise forms.ValidationError("Please select a time slot.")
        
        if doctor and appointment_date and time_slot_str:
            # Parse time slot
            try:
                start_time = datetime.strptime(time_slot_str, '%H:%M:%S').time()
                
                # Check if date is in the past
                if appointment_date < date.today():
                    raise forms.ValidationError("Cannot book appointments in the past.")
                
                # Check if slot is available (double-check to prevent race conditions)
                if Appointment.objects.filter(
                    doctor=doctor,
                    appointment_date=appointment_date,
                    start_time=start_time,
                    status__in=['scheduled', 'confirmed']
                ).exists():
                    raise forms.ValidationError("This time slot was just booked by someone else. Please select another slot.")
                
                # Check if doctor is available on this day/time
                day_of_week = appointment_date.weekday()
                schedule_exists = DoctorSchedule.objects.filter(
                    doctor=doctor,
                    day_of_week=day_of_week,
                    start_time__lte=start_time,
                    end_time__gt=start_time,
                    is_available=True
                ).exists()
                
                if not schedule_exists:
                    raise forms.ValidationError("Doctor is not available at this time.")
                
                # Check if doctor is on time off
                on_time_off = TimeOff.objects.filter(
                    doctor=doctor,
                    start_date__lte=appointment_date,
                    end_date__gte=appointment_date,
                    is_approved=True
                ).exists()
                
                if on_time_off:
                    raise forms.ValidationError("Doctor is on time off on this date.")
                
                cleaned_data['start_time'] = start_time
                
            except ValueError:
                raise forms.ValidationError("Invalid time slot format.")
        
        return cleaned_data
    
    def save(self, commit=True):
        appointment = super().save(commit=False)
        appointment.patient = self.patient
        appointment.start_time = self.cleaned_data['start_time']
        
        # Calculate end time based on doctor's schedule or default to 30 min
        try:
            schedule = DoctorSchedule.objects.get(
                doctor=appointment.doctor,
                day_of_week=appointment.appointment_date.weekday(),
                is_available=True
            )
            slot_duration = schedule.slot_duration
        except DoctorSchedule.DoesNotExist:
            slot_duration = 30  # Default
        
        appointment.end_time = (datetime.combine(date.today(), appointment.start_time) + 
                               timedelta(minutes=slot_duration)).time()
        appointment.status = 'scheduled'
        
        if commit:
            appointment.save()
        return appointment
    
class DoctorScheduleForm(forms.ModelForm):
    class Meta:
        model = DoctorSchedule
        fields = ['day_of_week', 'start_time', 'end_time', 'slot_duration', 'is_available']
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'day_of_week': forms.Select(attrs={'class': 'form-control'}),
            'slot_duration': forms.NumberInput(attrs={'class': 'form-control', 'min': 15, 'step': 15}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        
        if start_time and end_time and start_time >= end_time:
            raise forms.ValidationError("End time must be after start time.")
        
        return cleaned_data

class TimeOffForm(forms.ModelForm):
    class Meta:
        model = TimeOff
        fields = ['start_date', 'end_date', 'reason']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'reason': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and start_date > end_date:
            raise forms.ValidationError("End date must be after or equal to start date.")
        
        if start_date and start_date < date.today():
            raise forms.ValidationError("Cannot set time off in the past.")
        
        return cleaned_data
    
class MedicationForm(forms.ModelForm):
    class Meta:
        model = Medication
        fields = ['name', 'generic_name', 'manufacturer', 'description', 'common_dosages', 'side_effects', 'contraindications']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'generic_name': forms.TextInput(attrs={'class': 'form-control'}),
            'manufacturer': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'common_dosages': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 250mg, 500mg'}),
            'side_effects': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'contraindications': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

class PrescriptionItemForm(forms.ModelForm):
    class Meta:
        model = PrescriptionItem
        fields = ['medication', 'medication_name', 'dosage', 'dosage_form', 'frequency', 
                 'custom_frequency', 'duration', 'quantity', 'refills', 'instructions', 'route']
        widgets = {
            'medication': forms.Select(attrs={'class': 'form-control', 'id': 'id_medication_select'}),
            'medication_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter medication name'}),
            'dosage': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 500mg'}),
            'dosage_form': forms.Select(attrs={'class': 'form-control'}),
            'frequency': forms.Select(attrs={'class': 'form-control', 'id': 'id_frequency_select'}),
            'custom_frequency': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Every Monday and Thursday'}),
            'duration': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 7 days, 2 weeks'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'refills': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'instructions': forms.Textarea(attrs={'rows': 2, 'class': 'form-control', 'placeholder': 'Special instructions'}),
            'route': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Oral'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['medication'].required = False
        self.fields['medication_name'].required = True
        self.fields['custom_frequency'].required = False
        
        # Add help text
        self.fields['medication'].help_text = "Select from existing medications or enter new one below"
        self.fields['medication_name'].help_text = "Enter medication name if not in list"
    
    def clean(self):
        cleaned_data = super().clean()
        medication = cleaned_data.get('medication')
        medication_name = cleaned_data.get('medication_name')
        frequency = cleaned_data.get('frequency')
        custom_frequency = cleaned_data.get('custom_frequency')
        
        # Either medication or medication_name must be provided
        if not medication and not medication_name:
            raise forms.ValidationError("Please select a medication or enter a new one.")
        
        # If frequency is OTHER, custom_frequency is required
        if frequency == 'OTHER' and not custom_frequency:
            raise forms.ValidationError("Please specify the custom frequency.")
        
        return cleaned_data

class PrescriptionForm(forms.ModelForm):
    class Meta:
        model = Prescription
        fields = ['diagnosis', 'notes', 'valid_until', 'refills_allowed', 'is_emergency']
        widgets = {
            'diagnosis': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Diagnosis or reason for prescription'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Additional notes'}),
            'valid_until': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'refills_allowed': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'is_emergency': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.patient = kwargs.pop('patient', None)
        self.doctor = kwargs.pop('doctor', None)
        super().__init__(*args, **kwargs)
    
    def save(self, commit=True):
        prescription = super().save(commit=False)
        prescription.patient = self.patient
        prescription.doctor = self.doctor
        prescription.created_by = self.doctor.user_profile.user
        
        if commit:
            prescription.save()
        return prescription

# Create formset for prescription items
PrescriptionItemFormSet = inlineformset_factory(
    Prescription, 
    PrescriptionItem, 
    form=PrescriptionItemForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True
)

class PrescriptionFillForm(forms.ModelForm):
    class Meta:
        model = PrescriptionFill
        fields = ['quantity', 'pharmacy_name', 'pharmacy_phone', 'notes']
        widgets = {
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'pharmacy_name': forms.TextInput(attrs={'class': 'form-control'}),
            'pharmacy_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }