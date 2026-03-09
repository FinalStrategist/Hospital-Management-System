from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Patient CRUD (for receptionists)
    path('patients/', views.patient_list, name='patient_list'),
    path('patients/create/', views.patient_create, name='patient_create'),
    path('patients/<int:pk>/update/', views.patient_update, name='patient_update'),
    path('patients/<int:pk>/delete/', views.patient_delete, name='patient_delete'),
    
    # Booking URLs
    path('available-doctors/', views.available_doctors, name='available_doctors'),
    path('get-available-slots/', views.get_available_slots, name='get_available_slots'),
    path('book-appointment/', views.book_appointment, name='book_appointment'),
    path('my-appointments/', views.my_appointments, name='my_appointments'),
    path('cancel-appointment/<int:appointment_id>/', views.cancel_appointment, name='cancel_appointment'),
    
    # Doctor appointment management
    path('doctor-appointments/', views.doctor_appointments, name='doctor_appointments'),
    path('update-appointment-status/<int:appointment_id>/', views.update_appointment_status, name='update_appointment_status'),
    
    # Receptionist appointment views
    path('all-appointments/', views.all_appointments, name='all_appointments'),
    
    # Schedule management
    path('manage-schedule/', views.manage_schedule, name='manage_schedule'),
    path('delete-schedule/<int:schedule_id>/', views.delete_schedule, name='delete_schedule'),
    
    # Prescription URLs
    path('doctor/prescriptions/', views.doctor_prescriptions, name='doctor_prescriptions'),
    path('doctor/prescriptions/create/', views.create_prescription, name='create_prescription'),
    path('doctor/prescriptions/create/<int:patient_id>/', views.create_prescription, name='create_prescription_for_patient'),
    path('prescription/<int:prescription_id>/', views.prescription_detail, name='prescription_detail'),
    path('prescription/<int:prescription_id>/update-status/', views.update_prescription_status, name='update_prescription_status'),
    path('prescription/<int:prescription_id>/record-fill/', views.record_prescription_fill, name='record_prescription_fill'),

    # Patient prescription views
    path('my-prescriptions/', views.my_prescriptions, name='my_prescriptions'),

    # Medication management
    path('medications/', views.medication_list, name='medication_list'),
    path('medications/create/', views.medication_create, name='medication_create'),
    path('medications/<int:pk>/update/', views.medication_update, name='medication_update'),
    path('medications/<int:pk>/delete/', views.medication_delete, name='medication_delete'),

    # M-Pesa URLs
    path('mpesa/callback/', views.mpesa_callback, name='mpesa_callback'),
    path('payment/initiate/<int:invoice_id>/', views.initiate_payment, name='initiate_payment'),
    path('payment/status/<str:checkout_id>/', views.payment_status, name='payment_status'),

    # Invoice URLs
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoice/<int:invoice_id>/', views.invoice_detail, name='invoice_detail'),
    path('invoice/create/', views.create_invoice, name='create_invoice'),
    path('invoice/create/<int:appointment_id>/', views.create_invoice, name='create_invoice_for_appointment'),
    path('invoice/generate/<int:appointment_id>/', views.auto_generate_invoice, name='auto_generate_invoice'),
]