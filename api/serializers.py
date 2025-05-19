# serializers.py
from rest_framework import serializers
from .models import Reservation, Trajet, Voiture, Driver ,Payment, DriverStripeAccount

class VoitureSerializer(serializers.ModelSerializer):
    car_image_id = serializers.SerializerMethodField()
    
    class Meta:
        model = Voiture
        fields = ['id_voiture', 'marque', 'matricule', 'image', 'car_image_id']
    
    def get_car_image_id(self, obj):
        if obj.image:
            return obj.image.name
        return None

class DriverSerializer(serializers.ModelSerializer):
    voiture = VoitureSerializer(read_only=True)
    voiture_id = serializers.PrimaryKeyRelatedField(
        queryset=Voiture.objects.all(), 
        source='voiture', 
        write_only=True
    )
    
    class Meta:
        model = Driver
        fields = ['id', 'user_id', 'voiture', 'voiture_id']
        read_only_fields = ['id']

# api/serializers.py - Update TrajetSerializer to include available_seats

class TrajetSerializer(serializers.ModelSerializer):
    voiture_details = VoitureSerializer(source='voiture', read_only=True)
    available_seats = serializers.SerializerMethodField()
    
    class Meta:
        model = Trajet
        fields = [
            'id', 'name', 'owner_id', 'voiture', 'voiture_details', 'phonenumber', 'price', 
            'departure', 'arrival', 'departure_date', 'arrival_date',
            'nb_places', 'reserved_seats', 'available_seats', 'created_at', 'status'
        ]
        read_only_fields = ['id', 'created_at', 'reserved_seats']
    
    def get_available_seats(self, obj):
        return max(0, obj.nb_places - obj.reserved_seats)  
class TrajetDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed trip information, including car and driver details
    """
    # Get car details
    car_details = serializers.SerializerMethodField()
    
    # Get owner details
    owner_details = serializers.SerializerMethodField()
    
    class Meta:
        model = Trajet
        fields = [
            'id', 'name', 'phonenumber', 'price', 
            'departure', 'arrival', 'departure_date', 'arrival_date',
            'nb_places', 'created_at', 'status',
            'car_details', 'owner_details'
        ]
    
    def get_car_details(self, obj):
        """Return detailed car information including image ID"""
        if not obj.voiture:
            return None
            
        car = obj.voiture
        return {
            'id': car.id_voiture,
            'marque': car.marque,
            'matricule': car.matricule,
            'image': car.image.url if car.image else None,
            'car_image_id': car.image.name if car.image else None
        }
    
    def get_owner_details(self, obj):
        """Return driver/owner information"""
        if not obj.owner_id:
            return None
            
        driver = obj.owner_id
        # Include car details for the driver too
        car_data = None
        if driver.voiture:
            car_data = {
                'id': driver.voiture.id_voiture,
                'marque': driver.voiture.marque,
                'matricule': driver.voiture.matricule,
                'image': driver.voiture.image.url if driver.voiture.image else None,
                'car_image_id': driver.voiture.image.name if driver.voiture.image else None
            }
            
        return {
            'id': driver.id,
            'user_id': driver.user_id,
            'car': car_data
        }


class DriverStripeAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverStripeAccount
        fields = ['id', 'stripe_account_id', 'is_verified', 'verification_status', 'created_at']
        read_only_fields = ['id', 'created_at']

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            'id', 'passenger_id', 'driver_id', 'trajet', 'amount', 
            'platform_fee', 'currency', 'status', 'created_at'
        ]
        read_only_fields = ['id', 'status', 'created_at', 'stripe_payment_intent_id']

class ReservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reservation
        fields = [
            'id', 'trajet', 'passenger_id', 'nom', 'prenom', 'tel', 'adresse',
            'payment_method', 'payment', 'status', 'created_at', 'notes'
        ]
        read_only_fields = ['id', 'passenger_id', 'created_at']
    

class ReservationHistorySerializer(serializers.ModelSerializer):
    trajet_depart = serializers.CharField(source='trajet.departure', read_only=True)
    trajet_arrivee = serializers.CharField(source='trajet.arrival', read_only=True)
    trajet_date_depart = serializers.DateTimeField(source='trajet.departure_date', read_only=True)
    trajet_date_arrivee = serializers.DateTimeField(source='trajet.arrival_date', read_only=True)
    payment_status = serializers.CharField(source='payment.status', read_only=True)
    trajet_id = serializers.ReadOnlyField(source='trajet.id')  # Using ReadOnlyField instead
    
    class Meta:
        model = Reservation
        fields = [
            'id', 'nom', 'prenom', 'tel', 'status',
            'payment_method', 'payment_status',
            'trajet_depart', 'trajet_arrivee', 
            'trajet_date_depart', 'trajet_date_arrivee',
            'trajet_id', 'created_at'
        ]

# class ReservationHistorySerializer(serializers.ModelSerializer):
#     trajet_depart = serializers.CharField(source='trajet.departure', read_only=True)
#     trajet_arrivee = serializers.CharField(source='trajet.arrival', read_only=True)
#     trajet_date_depart = serializers.DateTimeField(source='trajet.departure_date', read_only=True)
#     trajet_date_arrivee = serializers.DateTimeField(source='trajet.arrival_date', read_only=True)
#     payment_status = serializers.CharField(source='payment.status', read_only=True)

#     class Meta:
#         model = Reservation
#         fields = [
#             'id', 'nom', 'prenom', 'tel', 'status',
#             'payment_method', 'payment_status',
#             'trajet_depart', 'trajet_arrivee',
#             'trajet_date_depart', 'trajet_date_arrivee',
#             'created_at'
#         ]