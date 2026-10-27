from django.views.generic import TemplateView, ListView, DetailView
from django.views.generic.edit import FormMixin
from django.urls import reverse
from .models import DormAccommodation, BookingStatus
from .forms import BookingStatusForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
import logging

logger = logging.getLogger(__name__)

class HomePageView(TemplateView):
    template_name = "home.html"

class WaitlistPageView(ListView):
    model = DormAccommodation
    template_name = "waitlist.html"
    queryset = DormAccommodation.objects.filter(room_type='Shared').exclude(occupied_status='Yes')

class WaitlistDormDetailView(LoginRequiredMixin, FormMixin, DetailView):
    model = DormAccommodation
    template_name = 'details_waitlist.html'
    context_object_name = 'dorm'
    form_class = BookingStatusForm

    def get_success_url(self):
        return reverse('success')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch all users who have booked the same dorm
        context['users_with_same_dorm'] = BookingStatus.objects.filter(dorm_id=self.object, book_status= "Waitlisted").select_related('user_id')
        context['form'] = self.get_form()
        return context
    
    def post(self, request, *args, **kwargs):
        
        self.object = self.get_object()  # Fetch the dorm object
        form = self.get_form()

        if form.is_valid():
            try:
                booking = form.save(commit=False)
                booking.dorm_id = self.object 
                booking.user_id = request.user 
                booking.amount = self.object.price  # Set the amount to the dorm price
                booking.save()
                messages.success(request, "Booking submitted and under review! You have been redirected to the homepage.")
                return self.form_valid(form)
            except Exception:
                logger.exception("Error saving booking for dorm %s", self.object.pk)
            return self.form_invalid(form)
        else:
            logger.info("Invalid booking form: %s", form.errors.as_json())
            return self.form_invalid(form)
        

class SolodormPageView(ListView):
    model = DormAccommodation
    template_name = 'solodorm.html'
    queryset = DormAccommodation.objects.filter(room_type='Solo').exclude(occupied_status='Yes')

class SoloDormDetailView(LoginRequiredMixin, FormMixin, DetailView):
    model = DormAccommodation
    template_name = 'details_solo.html'
    context_object_name = 'dorm'
    form_class = BookingStatusForm
    
    
    def get_success_url(self):
        return reverse('success')

    def get_context_data(self, **kwargs):
        # Add the form to the template context
        context = super().get_context_data(**kwargs)
        context['form'] = self.get_form()
        return context

    def post(self, request, *args, **kwargs):
        # Handle the form submission
        self.object = self.get_object()  # Fetch the dorm object
        form = self.get_form()
        if form.is_valid():
            try:
                booking = form.save(commit=False)
                booking.dorm_id = self.object 
                booking.user_id = request.user 
                booking.amount = self.object.price  # Set the amount to the dorm price
                booking.save()
                return self.form_valid(form)
            except Exception:
                logger.exception("Error saving booking for dorm %s", self.object.pk)
            return self.form_invalid(form)
        else:
            logger.info("Invalid booking form: %s", form.errors.as_json())
            return self.form_invalid(form)
        
class BookingStatusListView(LoginRequiredMixin, ListView):
    model = BookingStatus
    template_name = 'booking_status.html'
    context_object_name = 'booking_status'

    def get_queryset(self):
        # Filter bookings by the logged-in user
        return BookingStatus.objects.filter(user_id=self.request.user)



class AboutusPageView(TemplateView):
    template_name = 'aboutus.html'


class SuccessPageView(TemplateView):
    template_name = 'success.html'