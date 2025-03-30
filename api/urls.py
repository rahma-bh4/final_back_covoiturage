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
]