# serializers.py
from rest_framework import serializers
from .models import Trajet, Voiture, Driver

class VoitureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Voiture
        fields = ['id_voiture', 'marque', 'matricule', 'image']

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
    class Meta:
        model = Trajet
        fields = [
            'id', 'name', 'owner_id', 'voiture', 'phonenumber', 'price', 
            'departure', 'arrival', 'departure_date', 'arrival_date', 
            'nb_places', 'created_at', 'status'
        ]
        read_only_fields = ['id', 'created_at']