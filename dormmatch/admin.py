from django.contrib import admin, messages
from .models import  DormAccommodation, BookingStatus
from . import stellar

'''
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'first_name', 'last_name', 'email', 'gender', 'school', 'degree_program')
'''
class DormAccommodationAdmin(admin.ModelAdmin):
    list_display = ('dorm_id', 'dorm_name', 'dorm_loc', 'room_type', 'resident_capacity', 'occupied_status', 'price','num_waitlist', 'image', 'price_xlm', 'chain_dorm_id')
    actions = ['list_on_stellar']

    @admin.action(description="List selected dorms on Stellar")
    def list_on_stellar(self, request, queryset):
        for dorm in queryset:
            if dorm.chain_dorm_id is not None:
                self.message_user(request, f"{dorm} is already on-chain (#{dorm.chain_dorm_id}).", messages.WARNING)
                continue
            if not dorm.price_xlm:
                self.message_user(request, f"Set a price in XLM for {dorm} first.", messages.ERROR)
                continue
            try:
                dorm.chain_dorm_id = stellar.list_dorm(dorm)
            except stellar.StellarError as exc:
                self.message_user(request, f"{dorm}: {exc}", messages.ERROR)
                continue
            dorm.save(update_fields=['chain_dorm_id'])
            self.message_user(request, f"{dorm} listed on-chain as dorm #{dorm.chain_dorm_id}.", messages.SUCCESS)


class BookingStatusAdmin(admin.ModelAdmin):
    list_display = ('book_id','booking_date', 'booking_time', 'user_id', 'dorm_id', 'amount', 'book_status', 'chain_booking_id')
    readonly_fields = ('chain_booking_id', 'wallet_address', 'tx_hash')
    actions = ['approve_on_stellar', 'waitlist_on_stellar', 'decline_on_stellar']

    def _run_on_chain(self, request, queryset, contract_call, new_status):
        """Call the contract for each on-chain booking, then mirror the status in the database."""
        for booking in queryset:
            if booking.chain_booking_id is None:
                self.message_user(request, f"{booking} was not paid on Stellar.", messages.WARNING)
                continue
            try:
                contract_call(booking.chain_booking_id)
            except stellar.StellarError as exc:
                self.message_user(request, f"{booking}: {exc}", messages.ERROR)
                continue

            was_waitlisted = booking.book_status == 'Waitlisted'
            booking.book_status = new_status
            booking.save()
            if was_waitlisted and new_status == 'Declined':
                booking.dorm_id.update_num_waitlist_occupied_status_shared()
            self.message_user(request, f"{booking} set to {new_status} on-chain.", messages.SUCCESS)

    @admin.action(description="Approve on Stellar (solo rooms)")
    def approve_on_stellar(self, request, queryset):
        self._run_on_chain(request, queryset.filter(dorm_id__room_type='Solo'), stellar.approve_solo, 'Approved')

    @admin.action(description="Waitlist on Stellar (shared rooms)")
    def waitlist_on_stellar(self, request, queryset):
        self._run_on_chain(request, queryset.filter(dorm_id__room_type='Shared'), stellar.waitlist, 'Waitlisted')

    @admin.action(description="Decline and refund on Stellar")
    def decline_on_stellar(self, request, queryset):
        self._run_on_chain(request, queryset, stellar.decline, 'Declined')


admin.site.register(DormAccommodation, DormAccommodationAdmin)
#admin.site.register(UserProfile, UserProfileAdmin)
admin.site.register(BookingStatus, BookingStatusAdmin)
