from django import forms
from .models import DormAccommodation, BookingStatus

class DormAccommodationForm(forms.ModelForm):
    class Meta:
        model = DormAccommodation
        fields = ['dorm_name', 'dorm_loc', 'room_type', 'resident_capacity', 'price', 'description']

class BookingStatusForm(forms.ModelForm):
    class Meta:
        model = BookingStatus
        fields = ['reference_payment']
