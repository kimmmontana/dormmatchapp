from django.db import models
#from accounts.models import CustomUser
from django.contrib.auth import get_user_model 
from django.core.exceptions import ValidationError
from django.utils.timezone import now


class DormAccommodation(models.Model):

    ROOM_TYPE_CHOICES = [
        ('Solo', 'Solo'),
        ('Shared', 'Shared'),
    ]

    OCCUPIED_STATUS_CHOICES = [
        ('No', 'No'),
        ('Yes', 'Yes'),
        ('Waiting', 'Waiting'),
        
    ]

    dorm_id = models.AutoField( primary_key=True, unique=True)
    dorm_name = models.CharField(max_length=20)
    dorm_loc = models.CharField(max_length=150)
    room_type = models.CharField(max_length=6, choices=ROOM_TYPE_CHOICES)
    resident_capacity = models.IntegerField()
    occupied_status = models.CharField(max_length=10, choices=OCCUPIED_STATUS_CHOICES, default="No")
    price = models.DecimalField(max_digits=8, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    num_waitlist = models.CharField(max_length=6, editable= False, default="0")
    image = models.ImageField(upload_to='dorm_images/', blank=True, null=True)
    # Stellar escrow: the dorm's ID in the DormMatchBooking contract and its price in XLM.
    chain_dorm_id = models.PositiveIntegerField(unique=True, blank=True, null=True)
    price_xlm = models.DecimalField(max_digits=14, decimal_places=7, blank=True, null=True)

    def __str__(self):
        # Define the string representation for the admin panel
        return f"{self.dorm_id}-DORM-{self.room_type.upper()}"
    
    @property
    def price_xlm_display(self):
        """XLM price without trailing zeros, e.g. 0.5 instead of 0.5000000."""
        if self.price_xlm is None:
            return ""
        return f"{self.price_xlm:f}".rstrip("0").rstrip(".")

    def get_waitlisted_count(self):
        #Calculate the number of waitlisted users for this dorm.
        return BookingStatus.objects.filter(dorm_id=self,book_status='Waitlisted').count()
    
    def update_occupied_status_solo(self,occupied_status_yes_no):
        #Check if the dorm should be marked as occupied and update the status.
        self.occupied_status = occupied_status_yes_no 
        self.save()

    def update_num_waitlist_occupied_status_shared(self):
        self.num_waitlist = str(self.get_waitlisted_count())
        if self.get_waitlisted_count() == self.resident_capacity:
            self.occupied_status = 'Yes'
        elif self.get_waitlisted_count() < self.resident_capacity and self.get_waitlisted_count() > 0:
            self.occupied_status = 'Waiting'
        else:
            self.occupied_status = 'No'
        self.save()
    
    def clean(self):
        """
        Custom validation to check if the combination of room_type and resident_capacity is valid.
        """
        if self.room_type == 'Solo' and self.resident_capacity != 1:
            raise ValidationError({'resident_capacity': 'Solo rooms can only have a capacity of 1.'})
        if self.room_type == 'Solo' and self.occupied_status == 'Waiting':
            raise ValidationError({'occupied_status': 'Waiting is not valid for Solo'})

            

    def save(self, *args, **kwargs):
        if self.room_type == 'Solo':
            self.num_waitlist = "NOT APPLICABLE"
        super().save(*args, **kwargs)
        

class BookingStatus(models.Model):
    BOOKING_STATUS_CHOICES = [
        ('Verify', 'Verify'),
        ('Waitlisted', 'Waitlisted'),
        ('Approved', 'Approved'),
        ('Declined', 'Declined'),
    ]

    book_id = models.AutoField(primary_key=True, unique=True)
    booking_date = models.DateField(default=now)
    booking_time = models.TimeField(default=now)

    user_id = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    dorm_id = models.ForeignKey(DormAccommodation, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=8, decimal_places=2)  # Amount based on the price in DormAccommodation
    book_status = models.CharField(max_length=10, choices=BOOKING_STATUS_CHOICES, default='Verify')
    reference_payment =  models.CharField(max_length=6)
    # Set when the booking was paid through the Stellar contract.
    chain_booking_id = models.PositiveBigIntegerField(unique=True, blank=True, null=True)
    wallet_address = models.CharField(max_length=56, blank=True)
    tx_hash = models.CharField(max_length=64, blank=True)

    def __str__(self):
        # Define the string representation for the admin panel
        return f"{self.book_id}-BOOK-{self.dorm_id.room_type.upper()}"
    
 
    def clean(self):
        """
        Custom validation to check if the combination of room_type and resident_capacity is valid.
        """
        if self.pk:
            if self.dorm_id.room_type == 'Solo' and self.book_status == 'Waitlisted':
                raise ValidationError({'book_status': 'Solo room is not applicable for waitlisting.'})

            if self.dorm_id.room_type == 'Shared' and self.book_status == 'Approved':
                raise ValidationError({'book_status': 'Admin could only set this to Waitlisted when shared. Approved is automatically set when number of waitlisted reached Dorms Capacity.'})
 
            # Validate that the dormitory doesn't exceed its capacity
            if  self.book_status == 'Approved' or self.book_status == 'Waitlisted':
                current_bookings = BookingStatus.objects.filter(dorm_id=self.dorm_id, book_status= 'Approved').count()
                if current_bookings >= self.dorm_id.resident_capacity:
                    raise ValidationError({'dorm_id': 'The dormitory has reached its maximum booking capacity.'})

    
    def save(self, *args, **kwargs):
        """
        Override save method to update the dorm's occupied status after saving.
        """
        self.full_clean()
        super().save(*args, **kwargs)

        #update occupied_status and book_status when booked.
        if self.dorm_id.room_type == 'Shared' and self.book_status == 'Waitlisted':
            self.dorm_id.update_num_waitlist_occupied_status_shared()
            if self.dorm_id.occupied_status == 'Yes':
                BookingStatus.objects.filter(dorm_id=self.dorm_id, book_status='Waitlisted').update(book_status='Approved')

         #update occupied_status: No->Yes when approved.       
        if  self.dorm_id.room_type == 'Solo' and self.book_status == 'Approved':
            self.dorm_id.update_occupied_status_solo('Yes')

        
       
        
    def delete(self, *args, **kwargs):
        """
        Override delete to ensure the num_waitlist is updated when a booking is deleted.
        """
        super().delete(*args, **kwargs)
        # Revert from Approved to Waitlisted only for Shared room types
        if self.dorm_id.room_type == 'Shared':
            BookingStatus.objects.filter(dorm_id=self.dorm_id, book_status='Approved').update(book_status='Waitlisted')
            self.dorm_id.update_num_waitlist_occupied_status_shared()
        
        #Revert occupied_status (yes->no) when deleted
        if self.dorm_id.room_type == 'Solo':
            self.dorm_id.update_occupied_status_solo('No')

     