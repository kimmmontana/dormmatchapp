from django.views.generic import TemplateView, ListView, DetailView
from django.views.generic.edit import FormMixin
from django.urls import reverse
from .models import DormAccommodation, BookingStatus
from .forms import BookingStatusForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from . import stellar
import json
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


def _bookable_on_chain(dorm):
    return stellar.is_enabled() and dorm.chain_dorm_id is not None and dorm.occupied_status != 'Yes'


def _read_json(request):
    try:
        return json.loads(request.body)
    except ValueError:
        return {}


@login_required
@require_POST
def stellar_prepare_booking(request, pk):
    """Build the unsigned `book` transaction for the student's wallet to sign."""
    dorm = get_object_or_404(DormAccommodation, pk=pk)
    address = _read_json(request).get('address')
    if not _bookable_on_chain(dorm):
        return JsonResponse({'error': 'This dorm cannot be booked with Stellar.'}, status=400)
    if not stellar.is_valid_address(address):
        return JsonResponse({'error': 'Invalid Stellar wallet address.'}, status=400)

    try:
        xdr = stellar.build_booking_transaction(address, dorm.chain_dorm_id)
    except stellar.StellarError as exc:
        logger.warning("Preparing Stellar booking failed: %s", exc)
        return JsonResponse({'error': 'Could not prepare the transaction. Check that your wallet is funded and has no open booking for this dorm.'}, status=400)
    return JsonResponse({'xdr': xdr})


@login_required
@require_POST
def stellar_submit_booking(request, pk):
    """Submit the wallet-signed transaction and record the confirmed booking."""
    dorm = get_object_or_404(DormAccommodation, pk=pk)
    data = _read_json(request)
    address, signed_xdr = data.get('address'), data.get('signed_xdr')
    if not _bookable_on_chain(dorm):
        return JsonResponse({'error': 'This dorm cannot be booked with Stellar.'}, status=400)
    if not stellar.is_valid_address(address) or not signed_xdr:
        return JsonResponse({'error': 'Missing wallet address or signed transaction.'}, status=400)

    try:
        chain_booking_id, tx_hash = stellar.submit_booking_transaction(signed_xdr, address, dorm.chain_dorm_id)
    except stellar.StellarError as exc:
        logger.warning("Submitting Stellar booking failed: %s", exc)
        return JsonResponse({'error': str(exc)}, status=400)

    booking, _ = BookingStatus.objects.get_or_create(
        chain_booking_id=chain_booking_id,
        defaults={
            'user_id': request.user,
            'dorm_id': dorm,
            'amount': dorm.price,
            'reference_payment': tx_hash[:6].upper(),
            'wallet_address': address,
            'tx_hash': tx_hash,
        },
    )
    messages.success(request, "Payment received on Stellar! Your booking is under review.")
    return JsonResponse({'redirect': reverse('success'), 'tx_hash': tx_hash})

