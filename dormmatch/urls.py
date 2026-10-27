from django.urls import path
from .views import stellar_prepare_booking, stellar_submit_booking, HomePageView, WaitlistPageView, SolodormPageView, AboutusPageView, SoloDormDetailView, SuccessPageView, BookingStatusListView, WaitlistDormDetailView
 # Correct import statement

urlpatterns = [
    path("", HomePageView.as_view(), name="home"),
    path("waitlist/", WaitlistPageView.as_view(), name="waitlist"),
    path("waitlist/<int:pk>/", WaitlistDormDetailView.as_view(), name="waitlist_detail"),
    path("solodorm/", SolodormPageView.as_view(), name="solodorm"), 
    path("aboutus/", AboutusPageView.as_view(), name="aboutus"), 
    path('solodorm/<int:pk>/', SoloDormDetailView.as_view(), name='solo_detail'),
    path("success/", SuccessPageView.as_view(template_name="success.html"), name="success"),
    path('booking-status/', BookingStatusListView.as_view(), name='booking-status'),
    path('stellar/book/<int:pk>/prepare/', stellar_prepare_booking, name='stellar_prepare_booking'),
    path('stellar/book/<int:pk>/submit/', stellar_submit_booking, name='stellar_submit_booking'),
]

