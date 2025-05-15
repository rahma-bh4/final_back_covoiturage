# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views



router = DefaultRouter()
router.register(r'voitures', views.VoitureViewSet)
router.register(r'drivers', views.DriverViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('register-driver/', views.register_driver, name='register-driver'),
    # path('check-driver-status/<str:user_id>/', views.check_driver_status, name='check-driver-status'),
    path('available-trajets/', views.available_trajets, name='available-trajets'),
    path('user-trajets/', views.user_trajets, name='user-trajets'),
    path('create-trajet/', views.CreateTrajetView.as_view(), name='create-trajet'),
    path('delete-trajet/<int:pk>/', views.DeleteTrajetView.as_view(), name='delete-trajet'),
    path('trajet/update/<int:pk>/', views.UpdateTrajetView.as_view(), name='update_trajet'),
    path('trajet/<int:pk>/', views.UpdateTrajetView.as_view(), name='get_trajet'),
    path('trajets/<int:trajet_id>/', views.trajet_detail, name='trajet_detail'),
    path('driver-stripe-onboarding/', views.driver_stripe_onboarding, name='driver-stripe-onboarding'),
    path('check-stripe-account-status/', views.check_stripe_account_status, name='check-stripe-account-status'),
    
    # Payment endpoints
    path('create-payment-intent/', views.create_payment_intent, name='create-payment-intent'),
    # path('driver-earnings/', views.driver_earnings, name='driver-earnings'),
    # path('passenger-bookings/', views.passenger_bookings, name='passenger-bookings'),
    
    # Webhook
    path('webhook/', views.webhook, name='webhook'),

 path('trajets/<int:trajet_id>/', views.trajet_detail, name='trajet_detail'),
    path('reservations/creer/', views.creer_reservation, name='creer_reservation'),
    path('reservations/history/', views.ReservationHistoryView.as_view(), name='reservation-history'),
    path('driver-stats/', views.driver_stats, name='driver-stats'),
    path('driver-reservations/', views.driver_reservations, name='driver-reservations'),
    path('driver-earnings/', views.driver_earnings, name='driver-earnings'),
    path('update-status/', views.update_reservation_status, name='update-reservation-status'),
   


]
