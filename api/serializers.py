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
            'id', 'name', 'owner_id', 'voiture_id', 'phonenumber', 'price', 
            'departure', 'arrival', 'departure_date', 'arrival_date', 
            'nb_places', 'created_at', 'status'
        ]
    
    # If your model field is actually named differently, add this override
    def create(self, validated_data):
        # Ensure we have the necessary data
        if 'owner_id' not in validated_data or 'voiture_id' not in validated_data:
            raise serializers.ValidationError("Missing required fields: owner_id and voiture_id are required")
        
        # Create and return the trajet
        return Trajet.objects.create(**validated_data)