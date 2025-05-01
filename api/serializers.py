# serializers.py
from rest_framework import serializers
from .models import Trajet, Voiture, Driver

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

class TrajetSerializer(serializers.ModelSerializer):
    voiture_details = VoitureSerializer(source='voiture', read_only=True)
    
    class Meta:
        model = Trajet
        fields = [
            'id', 'name', 'owner_id', 'voiture', 'voiture_details', 'phonenumber', 'price', 
            'departure', 'arrival', 'departure_date', 'arrival_date',
            'nb_places', 'created_at', 'status'
        ]
        read_only_fields = ['id', 'created_at']
    
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