from rest_framework import status, viewsets
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny
from .models import Trajet, Voiture, Driver
from .serializers import TrajetSerializer, VoitureSerializer, DriverSerializer
from rest_framework.permissions import IsAuthenticated
from .authentication import SupabaseJWTAuthentication
from .supabase_client import update_user_role
from django.utils import timezone
from rest_framework.views import APIView
class VoitureViewSet(viewsets.ModelViewSet):
    queryset = Voiture.objects.all()
    serializer_class = VoitureSerializer
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]  # Require authenticated users
    authentication_classes = [SupabaseJWTAuthentication]

    # Optional: Filter voitures by authenticated user
    def get_queryset(self):
        user_id = self.request.user  # user_id from JWT
        return Voiture.objects.filter(driver__user_id=user_id)  # Adjust based on your model relations

class DriverViewSet(viewsets.ModelViewSet):
    queryset = Driver.objects.all()
    serializer_class = DriverSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [SupabaseJWTAuthentication]

    def get_queryset(self):
        user_id = self.request.user  # user_id from JWT
        queryset = Driver.objects.all()
        user_id_param = self.request.query_params.get('user_id')
        if user_id_param:
            queryset = queryset.filter(user_id=user_id_param)
        else:
            queryset = queryset.filter(user_id=user_id)  # Limit to authenticated user
        return queryset
@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAuthenticated])
def register_driver(request):
    user_id = str(request.user.id)  # Ensure string for CharField
    marque = request.data.get('marque')
    matricule = request.data.get('matricule')
    image = request.data.get('image')
    
    if not all([marque, matricule]):
        return Response(
            {"error": "Missing required fields: marque, matricule"}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if Driver.objects.filter(user_id=user_id).exists():
        return Response(
            {"error": "You are already registered as a driver"}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    voiture_data = {'marque': marque, 'matricule': matricule}
    if image:
        voiture_data['image'] = image
    
    voiture_serializer = VoitureSerializer(data=voiture_data)
    if voiture_serializer.is_valid():
        voiture = voiture_serializer.save()
        driver_data = {
            'user_id': user_id,
            'voiture_id': voiture.id_voiture
        }
        print("Driver data:", driver_data)  # Debug log
        driver_serializer = DriverSerializer(data=driver_data)
        if driver_serializer.is_valid():
            driver_serializer.save()
            return Response({
                'voiture': voiture_serializer.data,
                'driver': driver_serializer.data,
                'message': 'Successfully registered as a driver'
            }, status=status.HTTP_201_CREATED)
        else:
            print("Driver serializer errors:", driver_serializer.errors)  # Debug log
            voiture.delete()
            return Response(driver_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    else:
        print("Voiture serializer errors:", voiture_serializer.errors)  # Debug log
        return Response(voiture_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
@api_view(['GET'])
@permission_classes([AllowAny])
def available_trajets(request):
    """
    Get all available trajets (active status and departure time in the future)
    First updates any trajets with passed departure dates to 'completed' status
    This endpoint does not require authentication
    """
    current_time = timezone.now()
    
    # First, update any active trajets with departure time in the past to 'completed'
    Trajet.objects.filter(
        status='active',
        departure_date__lt=current_time
    ).update(status='completed')
    
    # Filter for active trajets with departure time in the future and available seats
    trajets = Trajet.objects.filter(
        status='active',
        departure_date__gt=current_time,
        nb_places__gt=0
    ).order_by('departure_date')
    
    # Apply filters from query params
    departure = request.query_params.get('departure')
    arrival = request.query_params.get('arrival')
    date = request.query_params.get('date')
    
    if departure:
        trajets = trajets.filter(departure__icontains=departure)
    
    if arrival:
        trajets = trajets.filter(arrival__icontains=arrival)
    
    if date:
        trajets = trajets.filter(departure_date__date=date)
    
    serializer = TrajetSerializer(trajets, many=True)
    return Response(serializer.data)
# views.py
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_trajets(request):
    """
    Get all trajets created by the authenticated user (as a driver)
    Updates statuses of trajets based on current time:
    - If departure time is in the past but arrival time is in the future: set to 'ongoing'
    - If arrival time is in the past but status is still active/ongoing: set to 'completed'
    """
    user_id = request.user.id
    current_time = timezone.now()
    
    # First check if the user is a driver
    try:
        driver = Driver.objects.get(user_id=user_id)
    except Driver.DoesNotExist:
        return Response(
            {"error": "You are not registered as a driver"}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Update trajets that should be 'ongoing' (between departure and arrival times)
    Trajet.objects.filter(
        owner_id=driver,
        status='active',
        departure_date__lt=current_time,
        arrival_date__gt=current_time
    ).update(status='ongoing')
    
    # Update trajets that should be 'completed' (past arrival time)
    Trajet.objects.filter(
        owner_id=driver,
        status__in=['active', 'ongoing'],
        arrival_date__lt=current_time
    ).update(status='completed')
    
    # Get all trajets owned by this driver
    trajets = Trajet.objects.filter(owner_id=driver)
    
    # Apply status filter if provided
    status_filter = request.query_params.get('status')
    if status_filter:
        trajets = trajets.filter(status=status_filter)
    
    # Order by status ('active' first, then 'ongoing', then others)
    # Then by departure date (soonest first)
    trajets = trajets.extra(
        select={'status_order': """
            CASE 
                WHEN status = 'active' THEN 0 
                WHEN status = 'ongoing' THEN 1
                ELSE 2
            END
        """}
    ).order_by('status_order', 'departure_date')
    
    serializer = TrajetSerializer(trajets, many=True)


class CreateTrajetView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [SupabaseJWTAuthentication]
    
    def post(self, request):
        user_id = request.user.id
        
        try:
            driver = Driver.objects.get(user_id=user_id)
        except Driver.DoesNotExist:
            return Response(
                {"error": "Vous devez être enregistré comme chauffeur"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Create a new dictionary with the request data
        data = request.data.copy()
        
        # Use the exact field names from your model
        data['owner_id'] = driver.id  # This matches your model field 'owner_id'
        data['voiture'] = driver.voiture.id_voiture  # This matches your model field 'voiture'
        
        serializer = TrajetSerializer(data=data)
        
        if serializer.is_valid():
            trajet = serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            print(f"Serializer errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class DeleteTrajetView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [SupabaseJWTAuthentication]
    
    def delete(self, request, pk):
        """
        API pour supprimer un trajet par son ID.
        Seul le chauffeur qui a créé ce trajet peut le supprimer.
        """
        user_id = request.user.id
        
        try:
            # Get the driver record for the authenticated user
            driver = Driver.objects.get(user_id=user_id)
        except Driver.DoesNotExist:
            return Response(
                {"error": "Vous n'êtes pas enregistré comme chauffeur"},
                status=status.HTTP_403_FORBIDDEN
            )
            
        try:
            trajet = Trajet.objects.get(pk=pk)
            
            # Check if this trajet belongs to the authenticated driver
            if trajet.owner_id.id != driver.id:
                return Response(
                    {"error": "Vous n'êtes pas autorisé à supprimer ce trajet"},
                    status=status.HTTP_403_FORBIDDEN
                )
                
            trajet.delete()
            return Response(
                {"message": "Trajet supprimé avec succès"}, 
                status=status.HTTP_204_NO_CONTENT
            )
            
        except Trajet.DoesNotExist:
            return Response(
                {"error": "Trajet non trouvé"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        

class UpdateTrajetView(APIView):
    def put(self, request, pk):
        """
        API pour mettre à jour un trajet existant.
        """
        try:
            trajet = Trajet.objects.get(pk=pk)
        except Trajet.DoesNotExist:
            return Response({"error": "Trajet non trouvé"}, status=status.HTTP_404_NOT_FOUND)

        serializer = TrajetSerializer(trajet, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)