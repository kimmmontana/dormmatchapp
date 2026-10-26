from django.contrib import admin
from .models import  DormAccommodation, BookingStatus

'''
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'first_name', 'last_name', 'email', 'gender', 'school', 'degree_program')
'''
class DormAccommodationAdmin(admin.ModelAdmin):
    list_display = ('dorm_id', 'dorm_name', 'dorm_loc', 'room_type', 'resident_capacity', 'occupied_status', 'price','num_waitlist', 'image')

class BookingStatusAdmin(admin.ModelAdmin):
    list_display = ('book_id','booking_date', 'booking_time', 'user_id', 'dorm_id', 'amount', 'book_status')


admin.site.register(DormAccommodation, DormAccommodationAdmin)
#admin.site.register(UserProfile, UserProfileAdmin)
admin.site.register(BookingStatus, BookingStatusAdmin)