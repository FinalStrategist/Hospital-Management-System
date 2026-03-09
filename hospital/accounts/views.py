from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.contrib.auth.models import User
from .forms import UserRegistrationForm, PatientCreationForm, AppointmentBookingForm, DoctorScheduleForm, TimeOffForm, PrescriptionForm, PrescriptionItemFormSet, MedicationForm, PrescriptionFillForm
from .models import UserProfile, Receptionist, Doctor, Patient, DoctorSchedule, Appointment, TimeOff,Prescription, PrescriptionItem, Medication, PrescriptionFill, MpesaTransaction, Invoice, Payment
from django.db.models import Q
from django.db import transaction
from django.forms import formset_factory
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from datetime import datetime, timedelta, date
import json
from .mpesa_services import MpesaService
import logging


logger = logging.getLogger(__name__)

def home(request):
    return render(request, 'accounts/home.html')

def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Registration successful!')
            return redirect('dashboard')
    else:
        form = UserRegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'accounts/login.html')

def logout_view(request):
    logout(request)
    return redirect('home')

@login_required
def dashboard(request):
    user_type = request.user.profile.user_type
    
    context = {
        'user': request.user,
        'user_type': user_type,
    }
    
    if user_type == 'admin':
        # Admin dashboard with system overview
        total_users = User.objects.count()
        total_doctors = Doctor.objects.count()
        total_receptionists = Receptionist.objects.count()
        total_patients = Patient.objects.count()
        total_appointments = Appointment.objects.count()
        today_appointments = Appointment.objects.filter(appointment_date=date.today()).count()
        pending_timeoffs = TimeOff.objects.filter(is_approved=False).count()
        
        context.update({
            'total_users': total_users,
            'total_doctors': total_doctors,
            'total_receptionists': total_receptionists,
            'total_patients': total_patients,
            'total_appointments': total_appointments,
            'today_appointments': today_appointments,
            'pending_timeoffs': pending_timeoffs,
            'recent_appointments': Appointment.objects.all().order_by('-created_at')[:5],
            'recent_patients': Patient.objects.all().order_by('-user_profile__user__date_joined')[:5],
        })
        return render(request, 'accounts/admin_dashboard.html', context)
        
    elif user_type == 'receptionist':
        # Receptionist dashboard with patient and appointment management
        try:
            receptionist = request.user.profile.receptionist_details
        except:
            receptionist = None
        
        # Get counts (ensure these are integers, not querysets)
        patients_created = Patient.objects.filter(created_by=request.user).count()
        today_appointments = Appointment.objects.filter(appointment_date=date.today()).count()
        upcoming_appointments = Appointment.objects.filter(
            appointment_date__gte=date.today(),
            status__in=['scheduled', 'confirmed']
        ).count()
        
        # Get recent patients created by this receptionist (limit to 5)
        recent_patients = Patient.objects.filter(created_by=request.user).order_by('-user_profile__user__date_joined')[:5]
        
        # Get today's appointments (limit to 10)
        todays_appointments = Appointment.objects.filter(
            appointment_date=date.today()
        ).order_by('start_time')[:10]
        
        # Get all doctors for quick reference (limit to 5)
        doctors = Doctor.objects.all()[:5]
        doctor_data = []
        for doctor in doctors:
            today_schedule = DoctorSchedule.objects.filter(
                doctor=doctor,
                day_of_week=date.today().weekday(),
                is_available=True
            ).first()
            doctor_data.append({
                'doctor': doctor,
                'today_schedule': today_schedule
            })
                    
        # Get pending approvals or tasks
        pending_timeoffs = TimeOff.objects.filter(is_approved=False).count()
        
        context.update({
            'receptionist': receptionist,
            'patients_created': patients_created,
            'today_appointments': today_appointments,
            'upcoming_appointments': upcoming_appointments,
            'recent_patients': recent_patients,  
            'todays_appointments': todays_appointments,  
            'doctors': doctors,  
            'pending_timeoffs': pending_timeoffs,
            'today': date.today(),
            'now': timezone.now(),
        })
        return render(request, 'accounts/receptionist_dashboard.html', context)
        
    elif user_type == 'doctor':
        # Doctor dashboard with appointments and schedule
        try:
            doctor = request.user.profile.doctor_details
        except:
            doctor = None
            messages.error(request, 'Doctor profile not found.')
            return redirect('logout')
        
        
        # Today's appointments
        today_appointments = Appointment.objects.filter(
            doctor=doctor,
            appointment_date=date.today()
        ).order_by('start_time')
        
        # Upcoming appointments (excluding today)
        upcoming_appointments = Appointment.objects.filter(
            doctor=doctor,
            appointment_date__gt=date.today(),
            status__in=['scheduled', 'confirmed']
        ).order_by('appointment_date', 'start_time')[:10]
        
        # Total patients seen
        total_patients_seen = Appointment.objects.filter(
            doctor=doctor,
            status='completed'
        ).count()
        
        # Pending appointments
        pending_appointments = Appointment.objects.filter(
            doctor=doctor,
            status='scheduled',
            appointment_date__gte=date.today()
        ).count()
        
        # Get doctor's schedule for today
        today_schedule = DoctorSchedule.objects.filter(
            doctor=doctor,
            day_of_week=date.today().weekday(),
            is_available=True
        ).first()
        
        # Check if on time off today
        on_time_off = TimeOff.objects.filter(
            doctor=doctor,
            start_date__lte=date.today(),
            end_date__gte=date.today(),
            is_approved=True
        ).exists()
        
        context.update({
            'doctor': doctor,
            'today_appointments': today_appointments,
            'upcoming_appointments': upcoming_appointments,
            'total_patients_seen': total_patients_seen,
            'pending_appointments': pending_appointments,
            'today_schedule': today_schedule,
            'on_time_off': on_time_off,
            'today': date.today(),
        })
        return render(request, 'accounts/doctor_dashboard.html', context)
        
    else:  # patient
        # Patient dashboard with appointments and information
        try:
            patient = request.user.profile.patient_details
        except:
            patient = None
            messages.error(request, 'Patient profile not found.')
            return redirect('logout')        
        # Upcoming appointments
        upcoming_appointments = Appointment.objects.filter(
            patient=patient,
            appointment_date__gte=date.today(),
            status__in=['scheduled', 'confirmed']
        ).order_by('appointment_date', 'start_time')
        
        # Past appointments
        past_appointments = Appointment.objects.filter(
            patient=patient,
            appointment_date__lt=date.today()
        ).order_by('-appointment_date', '-start_time')[:5]
        
        # Total appointments
        total_appointments = Appointment.objects.filter(patient=patient).count()
        
        # Cancelled appointments
        cancelled_appointments = Appointment.objects.filter(
            patient=patient,
            status='cancelled'
        ).count()
        
        # Get favorite/recent doctors (doctors they've visited most)
        from django.db.models import Count
        favorite_doctors = Appointment.objects.filter(
            patient=patient
        ).values('doctor').annotate(
            count=Count('doctor')
        ).order_by('-count')[:3]
        
        favorite_doctor_details = []
        for fav in favorite_doctors:
            doctor = Doctor.objects.get(id=fav['doctor'])
            favorite_doctor_details.append({
                'doctor': doctor,
                'visit_count': fav['count']
            })
        
        context.update({
            'patient': patient,
            'upcoming_appointments': upcoming_appointments,
            'past_appointments': past_appointments,
            'total_appointments': total_appointments,
            'cancelled_appointments': cancelled_appointments,
            'favorite_doctors': favorite_doctor_details,
            'today': date.today(),
        })
        return render(request, 'accounts/patient_dashboard.html', context)
# Receptionist views for patient CRUD
@login_required
def patient_list(request):
    if request.user.profile.user_type != 'receptionist':
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    patients = Patient.objects.filter(created_by=request.user)
    return render(request, 'accounts/patient_list.html', {'patients': patients})

@login_required
def patient_create(request):
    if request.user.profile.user_type != 'receptionist':
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = PatientCreationForm(request.POST)
        if form.is_valid():
            patient = form.save(created_by=request.user)
            messages.success(request, f'Patient {patient.user_profile.user.get_full_name()} created successfully!')
            return redirect('patient_list')
    else:
        form = PatientCreationForm()
    
    return render(request, 'accounts/patient_form.html', {'form': form, 'action': 'Create'})

@login_required
def patient_update(request, pk):
    if request.user.profile.user_type != 'receptionist':
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    patient = get_object_or_404(Patient, pk=pk, created_by=request.user)
    
    if request.method == 'POST':
        # Update user fields
        patient.user_profile.user.first_name = request.POST.get('first_name')
        patient.user_profile.user.last_name = request.POST.get('last_name')
        patient.user_profile.user.email = request.POST.get('email')
        patient.user_profile.user.save()
        
        # Update profile fields
        patient.user_profile.phone_number = request.POST.get('phone_number')
        patient.user_profile.address = request.POST.get('address')
        patient.user_profile.save()
        
        # Update patient fields
        patient.emergency_contact = request.POST.get('emergency_contact')
        patient.blood_group = request.POST.get('blood_group')
        patient.save()
        
        messages.success(request, 'Patient updated successfully!')
        return redirect('patient_list')
    
    return render(request, 'accounts/patient_form.html', {
        'patient': patient,
        'action': 'Update'
    })

@login_required
def patient_delete(request, pk):
    if request.user.profile.user_type != 'receptionist':
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    patient = get_object_or_404(Patient, pk=pk, created_by=request.user)
    
    if request.method == 'POST':
        user = patient.user_profile.user
        patient.delete()
        user.delete()  # This will cascade delete profile
        messages.success(request, 'Patient deleted successfully!')
        return redirect('patient_list')
    
    return render(request, 'accounts/patient_confirm_delete.html', {'patient': patient})

# Patient Views for Booking
@login_required
def available_doctors(request):
    """View to show all available doctors"""
    if request.user.profile.user_type != 'patient':
        messages.error(request, 'Access denied. Only patients can view available doctors.')
        return redirect('dashboard')
    
    doctors = Doctor.objects.all()
    
    # Filter by specialization if provided
    specialization = request.GET.get('specialization')
    if specialization:
        doctors = doctors.filter(specialization__icontains=specialization)
    
    # Get today's day of week (0=Monday, 6=Sunday)
    today = date.today()
    day_of_week = today.weekday()
    
    doctor_availability = []
    for doctor in doctors:
        # Check if doctor has schedule for today
        today_schedule = DoctorSchedule.objects.filter(
            doctor=doctor,
            day_of_week=day_of_week,
            is_available=True
        ).first()
        
        # Check if doctor is on time off
        on_time_off = TimeOff.objects.filter(
            doctor=doctor,
            start_date__lte=today,
            end_date__gte=today,
            is_approved=True
        ).exists()
        
        doctor_availability.append({
            'doctor': doctor,
            'available_today': today_schedule is not None and not on_time_off,
            'schedule': today_schedule,
            'specialization': doctor.specialization,
        })
    
    return render(request, 'accounts/available_doctors.html', {
        'doctor_availability': doctor_availability,
        'today': today,
    })

@login_required
def get_available_slots(request):
    """AJAX view to get available time slots for a doctor on a specific date"""
    if request.user.profile.user_type != 'patient':
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    doctor_id = request.GET.get('doctor_id')
    appointment_date_str = request.GET.get('date')
    
    if not doctor_id or not appointment_date_str:
        return JsonResponse({'error': 'Missing parameters'}, status=400)
    
    try:
        doctor = Doctor.objects.get(id=doctor_id)
        appointment_date = datetime.strptime(appointment_date_str, '%Y-%m-%d').date()
        day_of_week = appointment_date.weekday()
        
        # Get doctor's schedule for that day
        schedules = DoctorSchedule.objects.filter(
            doctor=doctor,
            day_of_week=day_of_week,
            is_available=True
        )
        
        if not schedules.exists():
            return JsonResponse({'slots': [], 'message': 'Doctor is not available on this day'})
        
        # Check if doctor is on time off
        on_time_off = TimeOff.objects.filter(
            doctor=doctor,
            start_date__lte=appointment_date,
            end_date__gte=appointment_date,
            is_approved=True
        ).exists()
        
        if on_time_off:
            return JsonResponse({'slots': [], 'message': 'Doctor is on time off on this date'})
        
        # Get all booked appointments for this doctor on this date
        booked_appointments = Appointment.objects.filter(
            doctor=doctor,
            appointment_date=appointment_date,
            status__in=['scheduled', 'confirmed']
        ).values_list('start_time', flat=True)
        
        # Generate available time slots
        available_slots = []
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
                    available_slots.append({
                        'start': start_time.strftime('%H:%M:%S'),
                        'display': f"{start_time.strftime('%I:%M %p')} - {end_time_slot.strftime('%I:%M %p')}"
                    })
                
                current_time += slot_duration
        
        return JsonResponse({'slots': available_slots})
        
    except Doctor.DoesNotExist:
        return JsonResponse({'error': 'Doctor not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def book_appointment(request):
    """View for patients to book an appointment"""
    if request.user.profile.user_type != 'patient':
        messages.error(request, 'Access denied. Only patients can book appointments.')
        return redirect('dashboard')
    
    patient = request.user.profile.patient_details
    
    if request.method == 'POST':
        form = AppointmentBookingForm(request.POST, patient=patient)
        if form.is_valid():
            appointment = form.save()
            messages.success(request, f'Appointment booked successfully with Dr. {appointment.doctor.user_profile.user.get_full_name()} on {appointment.appointment_date} at {appointment.start_time.strftime("%I:%M %p")}')
            return redirect('my_appointments')
    else:
        form = AppointmentBookingForm(patient=patient)
    
    # Get all doctors for the template
    doctors = Doctor.objects.all()
    
    return render(request, 'accounts/book_appointment.html', {
        'form': form,
        'doctors': doctors,
    })

@login_required
def my_appointments(request):
    """View for patients to see their appointments"""
    if request.user.profile.user_type != 'patient':
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    patient = request.user.profile.patient_details
    
    # Get filter from request
    status_filter = request.GET.get('status', 'all')
    
    appointments = Appointment.objects.filter(patient=patient)
    
    if status_filter == 'upcoming':
        appointments = appointments.filter(
            appointment_date__gte=date.today(),
            status__in=['scheduled', 'confirmed']
        )
    elif status_filter == 'past':
        appointments = appointments.filter(
            Q(appointment_date__lt=date.today()) | 
            Q(status__in=['completed', 'cancelled', 'no_show'])
        )
    elif status_filter != 'all':
        appointments = appointments.filter(status=status_filter)
    
    appointments = appointments.order_by('-appointment_date', '-start_time')
    
    return render(request, 'accounts/my_appointments.html', {
        'appointments': appointments,
        'status_filter': status_filter,
        'today': date.today(),
    })

@login_required
def cancel_appointment(request, appointment_id):
    """View for patients to cancel their appointment"""
    if request.user.profile.user_type != 'patient':
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    patient = request.user.profile.patient_details
    appointment = get_object_or_404(Appointment, id=appointment_id, patient=patient)
    
    if request.method == 'POST':
        if appointment.can_cancel:
            appointment.status = 'cancelled'
            appointment.save()
            messages.success(request, 'Appointment cancelled successfully.')
        else:
            messages.error(request, 'This appointment cannot be cancelled (too close to appointment time or already completed/cancelled).')
        
        return redirect('my_appointments')
    
    return render(request, 'accounts/cancel_appointment.html', {
        'appointment': appointment
    })

# Doctor Views for managing appointments
@login_required
def doctor_appointments(request):
    """View for doctors to see their appointments"""
    if request.user.profile.user_type != 'doctor':
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    doctor = request.user.profile.doctor_details
    
    # Get date filter
    filter_date = request.GET.get('date')
    if filter_date:
        try:
            filter_date = datetime.strptime(filter_date, '%Y-%m-%d').date()
        except ValueError:
            filter_date = date.today()
    else:
        filter_date = date.today()
    
    appointments = Appointment.objects.filter(
        doctor=doctor,
        appointment_date=filter_date
    ).order_by('start_time')
    
    # Get upcoming appointments
    upcoming = Appointment.objects.filter(
        doctor=doctor,
        appointment_date__gte=date.today(),
        status__in=['scheduled', 'confirmed']
    ).order_by('appointment_date', 'start_time')[:10]
    
    return render(request, 'accounts/doctor_appointments.html', {
        'appointments': appointments,
        'upcoming': upcoming,
        'filter_date': filter_date,
        'doctor': doctor,
    })

@login_required
def update_appointment_status(request, appointment_id):
    """View for doctors to update appointment status"""
    if request.user.profile.user_type != 'doctor':
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    doctor = request.user.profile.doctor_details
    appointment = get_object_or_404(Appointment, id=appointment_id, doctor=doctor)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in ['confirmed', 'completed', 'no_show', 'cancelled']:
            appointment.status = new_status
            appointment.save()
            messages.success(request, f'Appointment status updated to {new_status}.')
        else:
            messages.error(request, 'Invalid status.')
    
    return redirect('doctor_appointments')

# Receptionist Views for managing appointments
@login_required
def all_appointments(request):
    """View for receptionists to see all appointments"""
    if request.user.profile.user_type != 'receptionist':
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    # Get filters
    doctor_id = request.GET.get('doctor')
    status = request.GET.get('status')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    appointments = Appointment.objects.all()
    
    if doctor_id:
        appointments = appointments.filter(doctor_id=doctor_id)
    if status:
        appointments = appointments.filter(status=status)
    if date_from:
        appointments = appointments.filter(appointment_date__gte=date_from)
    if date_to:
        appointments = appointments.filter(appointment_date__lte=date_to)
    
    appointments = appointments.order_by('-appointment_date', '-start_time')
    
    doctors = Doctor.objects.all()
    
    return render(request, 'accounts/all_appointments.html', {
        'appointments': appointments,
        'doctors': doctors,
        'filters': {
            'doctor': doctor_id,
            'status': status,
            'date_from': date_from,
            'date_to': date_to,
        }
    })

# Doctor Schedule Management (for admins and doctors)
@login_required
def manage_schedule(request):
    """View for doctors to manage their schedule"""
    if request.user.profile.user_type not in ['doctor', 'admin']:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    if request.user.profile.user_type == 'doctor':
        doctor = request.user.profile.doctor_details
    else:
        # Admin can select doctor
        doctor_id = request.GET.get('doctor')
        if doctor_id:
            doctor = get_object_or_404(Doctor, id=doctor_id)
        else:
            doctors = Doctor.objects.all()
            return render(request, 'accounts/select_doctor.html', {'doctors': doctors})
    
    schedules = DoctorSchedule.objects.filter(doctor=doctor).order_by('day_of_week')
    time_offs = TimeOff.objects.filter(doctor=doctor).order_by('-start_date')
    
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        
        if form_type == 'schedule':
            form = DoctorScheduleForm(request.POST)
            if form.is_valid():
                schedule = form.save(commit=False)
                schedule.doctor = doctor
                schedule.save()
                messages.success(request, 'Schedule added successfully.')
                return redirect('manage_schedule')
        elif form_type == 'timeoff':
            form = TimeOffForm(request.POST)
            if form.is_valid():
                timeoff = form.save(commit=False)
                timeoff.doctor = doctor
                timeoff.save()
                messages.success(request, 'Time off request submitted for approval.')
                return redirect('manage_schedule')
    
    schedule_form = DoctorScheduleForm()
    timeoff_form = TimeOffForm()
    
    return render(request, 'accounts/manage_schedule.html', {
        'doctor': doctor,
        'schedules': schedules,
        'time_offs': time_offs,
        'schedule_form': schedule_form,
        'timeoff_form': timeoff_form,
    })

@login_required
def delete_schedule(request, schedule_id):
    """Delete a doctor's schedule"""
    if request.user.profile.user_type not in ['doctor', 'admin']:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    schedule = get_object_or_404(DoctorSchedule, id=schedule_id)
    
    # Check if user has permission to delete this schedule
    if request.user.profile.user_type == 'doctor' and schedule.doctor != request.user.profile.doctor_details:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        schedule.delete()
        messages.success(request, 'Schedule deleted successfully.')
    
    return redirect('manage_schedule')

# Doctor Views for Prescriptions
@login_required
def doctor_prescriptions(request):
    """View for doctors to see all prescriptions they've written"""
    if request.user.profile.user_type != 'doctor':
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    doctor = request.user.profile.doctor_details
    
    # Get filter parameters
    status = request.GET.get('status', 'all')
    patient_id = request.GET.get('patient')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    prescriptions = Prescription.objects.filter(doctor=doctor)
    
    if status != 'all':
        prescriptions = prescriptions.filter(status=status)
    if patient_id:
        prescriptions = prescriptions.filter(patient_id=patient_id)
    if date_from:
        prescriptions = prescriptions.filter(created_at__date__gte=date_from)
    if date_to:
        prescriptions = prescriptions.filter(created_at__date__lte=date_to)
    
    prescriptions = prescriptions.order_by('-created_at')
    
    # Get all patients this doctor has prescribed to
    patients = Patient.objects.filter(prescriptions__doctor=doctor).distinct()
    
    return render(request, 'accounts/doctor_prescriptions.html', {
        'prescriptions': prescriptions,
        'patients': patients,
        'filters': {
            'status': status,
            'patient': patient_id,
            'date_from': date_from,
            'date_to': date_to,
        }
    })

@login_required
def create_prescription(request, patient_id=None):
    """View for doctors to create a new prescription"""
    if request.user.profile.user_type != 'doctor':
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    doctor = request.user.profile.doctor_details
    
    # If patient_id is provided, pre-select that patient
    initial_patient = None
    if patient_id:
        try:
            initial_patient = Patient.objects.get(id=patient_id)
        except Patient.DoesNotExist:
            pass
    
    if request.method == 'POST':
        prescription_form = PrescriptionForm(
            request.POST, 
            patient=initial_patient, 
            doctor=doctor
        )
        
        if prescription_form.is_valid():
            try:
                with transaction.atomic():
                    prescription = prescription_form.save()
                    
                    # Handle the formset
                    formset = PrescriptionItemFormSet(request.POST, instance=prescription)
                    
                    if formset.is_valid():
                        formset.save()
                        messages.success(request, f'Prescription {prescription.prescription_id} created successfully!')
                        return redirect('prescription_detail', prescription_id=prescription.id)
                    else:
                        # If formset is invalid, delete the prescription
                        prescription.delete()
                        for error in formset.errors:
                            for field, error_list in error.items():
                                for error_msg in error_list:
                                    messages.error(request, f"{field}: {error_msg}")
            except Exception as e:
                messages.error(request, f'Error creating prescription: {str(e)}')
        else:
            for field, errors in prescription_form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        prescription_form = PrescriptionForm(
            patient=initial_patient,
            doctor=doctor,
            initial={'patient': initial_patient}
        )
    
    # Get all medications for the dropdown
    medications = Medication.objects.all().order_by('name')
    
    # Get all patients for selection
    patients = Patient.objects.all().order_by('user_profile__user__last_name')
    
    return render(request, 'accounts/create_prescription.html', {
        'prescription_form': prescription_form,
        'medications': medications,
        'patients': patients,
        'selected_patient': initial_patient,
        'formset': PrescriptionItemFormSet(instance=Prescription()),
    })

@login_required
def prescription_detail(request, prescription_id):
    """View prescription details"""
    prescription = get_object_or_404(Prescription, id=prescription_id)
    
    # Check access rights
    user_type = request.user.profile.user_type
    if user_type == 'doctor' and prescription.doctor.user_profile.user != request.user:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    elif user_type == 'patient' and prescription.patient.user_profile.user != request.user:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    elif user_type not in ['doctor', 'patient', 'receptionist']:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    # Get prescription items
    items = prescription.items.all()
    
    # Get fill history
    fills = prescription.fills.all().order_by('-filled_date')
    
    return render(request, 'accounts/prescription_detail.html', {
        'prescription': prescription,
        'items': items,
        'fills': fills,
    })

@login_required
def update_prescription_status(request, prescription_id):
    """Update prescription status"""
    if request.user.profile.user_type != 'doctor':
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    prescription = get_object_or_404(Prescription, id=prescription_id, doctor=request.user.profile.doctor_details)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in ['active', 'completed', 'discontinued', 'expired']:
            prescription.status = new_status
            prescription.save()
            messages.success(request, f'Prescription status updated to {new_status}.')
        else:
            messages.error(request, 'Invalid status.')
    
    return redirect('prescription_detail', prescription_id=prescription.id)

@login_required
def record_prescription_fill(request, prescription_id):
    """Record that a prescription was filled"""
    if request.user.profile.user_type not in ['doctor', 'receptionist']:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    prescription = get_object_or_404(Prescription, id=prescription_id)
    
    # Check if user has access
    if request.user.profile.user_type == 'doctor' and prescription.doctor.user_profile.user != request.user:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = PrescriptionFillForm(request.POST)
        if form.is_valid():
            fill = form.save(commit=False)
            fill.prescription = prescription
            fill.filled_by = request.user
            
            # Update refills used
            if prescription.refills_used < prescription.refills_allowed:
                prescription.refills_used += 1
                prescription.save()
            else:
                messages.warning(request, 'No refills remaining. Prescription marked as expired.')
                prescription.status = 'expired'
                prescription.save()
            
            fill.save()
            messages.success(request, 'Prescription fill recorded successfully.')
            return redirect('prescription_detail', prescription_id=prescription.id)
    else:
        form = PrescriptionFillForm()
    
    return render(request, 'accounts/record_fill.html', {
        'prescription': prescription,
        'form': form,
    })

# Patient Views for Prescriptions
@login_required
def my_prescriptions(request):
    """View for patients to see their prescriptions"""
    if request.user.profile.user_type != 'patient':
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    patient = request.user.profile.patient_details
    
    # Get filter
    status = request.GET.get('status', 'all')
    
    prescriptions = Prescription.objects.filter(patient=patient)
    
    if status == 'active':
        prescriptions = [p for p in prescriptions if p.is_active]
    elif status != 'all':
        prescriptions = prescriptions.filter(status=status)
    
    # Separate active and past prescriptions
    active_prescriptions = [p for p in prescriptions if p.is_active]
    past_prescriptions = [p for p in prescriptions if not p.is_active]
    
    return render(request, 'accounts/my_prescriptions.html', {
        'active_prescriptions': active_prescriptions,
        'past_prescriptions': past_prescriptions,
        'status_filter': status,
    })

# Medication Management (for admins and doctors)
@login_required
def medication_list(request):
    """View all medications in the system"""
    if request.user.profile.user_type not in ['admin', 'doctor']:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    medications = Medication.objects.all().order_by('name')
    
    # Search
    search = request.GET.get('search')
    if search:
        medications = medications.filter(
            Q(name__icontains=search) | 
            Q(generic_name__icontains=search) |
            Q(manufacturer__icontains=search)
        )
    
    return render(request, 'accounts/medication_list.html', {
        'medications': medications,
        'search': search,
    })

@login_required
def medication_create(request):
    """Create a new medication"""
    if request.user.profile.user_type not in ['admin', 'doctor']:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = MedicationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Medication added successfully.')
            return redirect('medication_list')
    else:
        form = MedicationForm()
    
    return render(request, 'accounts/medication_form.html', {
        'form': form,
        'action': 'Add'
    })

@login_required
def medication_update(request, pk):
    """Update a medication"""
    if request.user.profile.user_type not in ['admin', 'doctor']:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    medication = get_object_or_404(Medication, pk=pk)
    
    if request.method == 'POST':
        form = MedicationForm(request.POST, instance=medication)
        if form.is_valid():
            form.save()
            messages.success(request, 'Medication updated successfully.')
            return redirect('medication_list')
    else:
        form = MedicationForm(instance=medication)
    
    return render(request, 'accounts/medication_form.html', {
        'form': form,
        'action': 'Update',
        'medication': medication
    })

@login_required
def medication_delete(request, pk):
    """Delete a medication"""
    if request.user.profile.user_type not in ['admin']:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    medication = get_object_or_404(Medication, pk=pk)
    
    if request.method == 'POST':
        # Check if medication is used in any prescriptions
        if PrescriptionItem.objects.filter(medication=medication).exists():
            messages.error(request, 'Cannot delete medication that is used in prescriptions.')
            return redirect('medication_list')
        
        medication.delete()
        messages.success(request, 'Medication deleted successfully.')
        return redirect('medication_list')
    
    return render(request, 'accounts/medication_confirm_delete.html', {
        'medication': medication
    })
    
    
    
    # M-Pesa Views
@login_required
def initiate_payment(request, invoice_id):
    """Initiate M-Pesa payment for an invoice"""
    try:
        invoice = Invoice.objects.get(id=invoice_id)
        
        # Check permissions (patient can pay their own invoice, staff can pay any)
        if request.user.profile.user_type == 'patient':
            if invoice.patient.user_profile.user != request.user:
                messages.error(request, 'Access denied.')
                return redirect('dashboard')
        
        if request.method == 'POST':
            phone_number = request.POST.get('phone_number')
            
            if not phone_number:
                messages.error(request, 'Phone number is required.')
                return redirect('initiate_payment', invoice_id=invoice_id)
            
            # Initiate STK push
            service = MpesaService()
            account_ref = invoice.invoice_number
            transaction_desc = f"Payment for {invoice.invoice_number}"
            
            # Build callback URL
            callback_url = request.build_absolute_uri(reverse('mpesa_callback'))
            
            try:
                response = service.stk_push(
                    phone_number=phone_number,
                    amount=float(invoice.balance),
                    account_reference=account_ref,
                    transaction_desc=transaction_desc,
                    callback_url=callback_url
                )
                
                # Save transaction record
                transaction = MpesaTransaction.objects.create(
                    merchant_request_id=response['MerchantRequestID'],
                    checkout_request_id=response['CheckoutRequestID'],
                    phone_number=phone_number,
                    amount=invoice.balance,
                    account_reference=account_ref,
                    transaction_desc=transaction_desc,
                    invoice=invoice,
                    status='pending'
                )
                
                messages.success(request, 'STK push sent. Please check your phone and enter your PIN.')
                
                # Redirect to payment status page
                return redirect('payment_status', checkout_id=response['CheckoutRequestID'])
                
            except Exception as e:
                messages.error(request, f'Payment failed: {str(e)}')
                return redirect('invoice_detail', invoice_id=invoice_id)
        
        return render(request, 'accounts/initiate_payment.html', {
            'invoice': invoice
        })
        
    except Invoice.DoesNotExist:
        messages.error(request, 'Invoice not found.')
        return redirect('dashboard')

@csrf_exempt
def mpesa_callback(request):
    """
    Callback URL for M-Pesa STK push results
    This is called by Safaricom API
    """
    if request.method == 'POST':
        try:
            # Get callback data
            callback_data = json.loads(request.body)
            logger.info(f"M-Pesa Callback received: {callback_data}")
            
            # Extract relevant data
            body = callback_data.get('Body', {})
            stk_callback = body.get('stkCallback', {})
            
            checkout_request_id = stk_callback.get('CheckoutRequestID')
            result_code = stk_callback.get('ResultCode')
            result_desc = stk_callback.get('ResultDesc')
            
            # Find the transaction
            try:
                transaction = MpesaTransaction.objects.get(checkout_request_id=checkout_request_id)
            except MpesaTransaction.DoesNotExist:
                logger.error(f"Transaction not found: {checkout_request_id}")
                return HttpResponse(status=404)
            
            # Update transaction status
            transaction.result_code = result_code
            transaction.result_desc = result_desc
            
            if result_code == 0:
                # Success - extract transaction details
                callback_metadata = stk_callback.get('CallbackMetadata', {})
                items = callback_metadata.get('Item', [])
                
                # Extract M-Pesa receipt number
                for item in items:
                    if item.get('Name') == 'MpesaReceiptNumber':
                        transaction.transaction_id = item.get('Value')
                        break
                
                transaction.status = 'completed'
                transaction.save()
                
                # Create payment record
                if transaction.invoice:
                    payment = Payment.objects.create(
                        invoice=transaction.invoice,
                        mpesa_transaction=transaction,
                        amount=transaction.amount,
                        payment_method='mpesa',
                        reference=transaction.transaction_id,
                        notes=f"Auto-created from M-Pesa callback. Receipt: {transaction.transaction_id}"
                    )
                    
                    # Update invoice status
                    transaction.invoice.save()  # This recalculates balance and status
                    
                    logger.info(f"Payment recorded: {payment.payment_number}")
            else:
                # Failed transaction
                transaction.status = 'failed'
                transaction.save()
                logger.warning(f"Transaction failed: {result_code} - {result_desc}")
            
            return HttpResponse(status=200)
            
        except Exception as e:
            logger.error(f"Error processing callback: {str(e)}")
            return HttpResponse(status=500)
    
    return HttpResponse(status=405)

@login_required
def payment_status(request, checkout_id):
    """Check payment status"""
    try:
        transaction = MpesaTransaction.objects.get(checkout_request_id=checkout_id)
        
        # Check permissions
        if request.user.profile.user_type == 'patient':
            if transaction.invoice and transaction.invoice.patient.user_profile.user != request.user:
                messages.error(request, 'Access denied.')
                return redirect('dashboard')
        
        # Query current status from M-Pesa if pending
        if transaction.status == 'pending':
            try:
                service = MpesaService()
                status_response = service.query_status(checkout_id)
                
                # Update based on response
                if status_response.get('ResultCode') == 0:
                    transaction.status = 'completed'
                    transaction.save()
                elif status_response.get('ResultCode'):
                    transaction.status = 'failed'
                    transaction.save()
                    
            except Exception as e:
                logger.error(f"Error querying status: {str(e)}")
        
        return render(request, 'accounts/payment_status.html', {
            'transaction': transaction
        })
        
    except MpesaTransaction.DoesNotExist:
        messages.error(request, 'Transaction not found.')
        return redirect('dashboard')

# Invoice Views
@login_required
def invoice_list(request):
    """List invoices based on user role"""
    user_type = request.user.profile.user_type
    
    if user_type == 'patient':
        # Patients see their own invoices
        patient = request.user.profile.patient_details
        invoices = Invoice.objects.filter(patient=patient)
    elif user_type == 'receptionist':
        # Receptionists see all invoices
        invoices = Invoice.objects.all()
    elif user_type == 'doctor':
        # Doctors see invoices for their patients
        doctor = request.user.profile.doctor_details
        invoices = Invoice.objects.filter(
            appointment__doctor=doctor
        ).distinct()
    else:  # admin
        invoices = Invoice.objects.all()
    
    # Apply filters
    status = request.GET.get('status')
    if status:
        invoices = invoices.filter(status=status)
    
    patient_id = request.GET.get('patient')
    if patient_id and user_type != 'patient':
        invoices = invoices.filter(patient_id=patient_id)
    
    invoices = invoices.order_by('-issue_date')
    
    # Get patients for filter (for staff)
    patients = Patient.objects.all() if user_type != 'patient' else []
    
    return render(request, 'accounts/invoice_list.html', {
        'invoices': invoices,
        'patients': patients,
        'current_status': status,
        'user_type': user_type
    })

@login_required
def invoice_detail(request, invoice_id):
    """View invoice details"""
    try:
        invoice = Invoice.objects.get(id=invoice_id)
        
        # Check permissions
        if request.user.profile.user_type == 'patient':
            if invoice.patient.user_profile.user != request.user:
                messages.error(request, 'Access denied.')
                return redirect('dashboard')
        
        # Get related transactions and payments
        transactions = invoice.mpesa_transactions.all()
        payments = invoice.payments.all()
        
        return render(request, 'accounts/invoice_detail.html', {
            'invoice': invoice,
            'transactions': transactions,
            'payments': payments
        })
        
    except Invoice.DoesNotExist:
        messages.error(request, 'Invoice not found.')
        return redirect('invoice_list')

@login_required
def create_invoice(request, appointment_id=None):
    """Create a new invoice (for receptionists/admins)"""
    if request.user.profile.user_type not in ['receptionist', 'admin']:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        # Get form data
        patient_id = request.POST.get('patient')
        appointment_id = request.POST.get('appointment')
        due_date = request.POST.get('due_date')
        notes = request.POST.get('notes')
        
        try:
            patient = Patient.objects.get(id=patient_id)
            appointment = Appointment.objects.get(id=appointment_id) if appointment_id else None
            
            # Create invoice
            invoice = Invoice.objects.create(
                patient=patient,
                appointment=appointment,
                created_by=request.user,
                due_date=due_date,
                notes=notes,
                subtotal=0,
                total_amount=0
            )
            
            # Add items from form
            descriptions = request.POST.getlist('item_description[]')
            quantities = request.POST.getlist('item_quantity[]')
            prices = request.POST.getlist('item_price[]')
            
            for desc, qty, price in zip(descriptions, quantities, prices):
                if desc and qty and price:
                    InvoiceItem.objects.create(
                        invoice=invoice,
                        description=desc,
                        quantity=int(qty),
                        unit_price=Decimal(price)
                    )
            
            messages.success(request, f'Invoice {invoice.invoice_number} created successfully.')
            return redirect('invoice_detail', invoice_id=invoice.id)
            
        except Exception as e:
            messages.error(request, f'Error creating invoice: {str(e)}')
    
    # GET request - show form
    patients = Patient.objects.all()
    appointments = Appointment.objects.filter(status__in=['scheduled', 'confirmed'])
    
    # Pre-select appointment if provided
    selected_appointment = None
    if appointment_id:
        try:
            selected_appointment = Appointment.objects.get(id=appointment_id)
        except Appointment.DoesNotExist:
            pass
    
    return render(request, 'accounts/create_invoice.html', {
        'patients': patients,
        'appointments': appointments,
        'selected_appointment': selected_appointment
    })

@login_required
def auto_generate_invoice(request, appointment_id):
    """Auto-generate invoice from appointment"""
    if request.user.profile.user_type not in ['receptionist', 'admin']:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    try:
        appointment = Appointment.objects.get(id=appointment_id)
        
        # Check if invoice already exists
        if Invoice.objects.filter(appointment=appointment).exists():
            messages.warning(request, 'Invoice already exists for this appointment.')
            return redirect('invoice_detail', invoice_id=appointment.invoices.first().id)
        
        # Calculate consultation fee (you can customize this)
        consultation_fee = 1500  # KES - you can make this configurable
        
        # Create invoice
        invoice = Invoice.objects.create(
            patient=appointment.patient,
            appointment=appointment,
            created_by=request.user,
            due_date=timezone.now().date() + timedelta(days=7),  # Due in 7 days
            notes=f"Auto-generated from appointment on {appointment.appointment_date}"
        )
        
        # Add consultation item
        InvoiceItem.objects.create(
            invoice=invoice,
            description=f"Consultation fee - Dr. {appointment.doctor.user_profile.user.get_full_name()}",
            quantity=1,
            unit_price=consultation_fee
        )
        
        messages.success(request, f'Invoice {invoice.invoice_number} generated from appointment.')
        return redirect('invoice_detail', invoice_id=invoice.id)
        
    except Appointment.DoesNotExist:
        messages.error(request, 'Appointment not found.')
        return redirect('dashboard')