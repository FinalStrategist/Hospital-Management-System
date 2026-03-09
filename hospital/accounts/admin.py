from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import UserProfile, Receptionist, Doctor, Patient, DoctorSchedule, Appointment, TimeOff

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False

class CustomUserAdmin(UserAdmin):
    inlines = [UserProfileInline]
    list_display = ('username', 'email', 'first_name', 'last_name', 'get_user_type')
    
    def get_user_type(self, obj):
        return obj.profile.get_user_type_display()
    get_user_type.short_description = 'User Type'

@admin.register(DoctorSchedule)
class DoctorScheduleAdmin(admin.ModelAdmin):
    list_display = ['doctor', 'day_of_week', 'start_time', 'end_time', 'is_available']
    list_filter = ['doctor', 'day_of_week', 'is_available']
    search_fields = ['doctor__user_profile__user__username']

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['patient', 'doctor', 'appointment_date', 'start_time', 'status']
    list_filter = ['status', 'appointment_date', 'doctor']
    search_fields = ['patient__user_profile__user__username', 'doctor__user_profile__user__username']
    date_hierarchy = 'appointment_date'

@admin.register(TimeOff)
class TimeOffAdmin(admin.ModelAdmin):
    list_display = ['doctor', 'start_date', 'end_date', 'reason', 'is_approved']
    list_filter = ['doctor', 'is_approved']
    search_fields = ['doctor__user_profile__user__username']


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
admin.site.register(Receptionist)
admin.site.register(Doctor)
admin.site.register(Patient)