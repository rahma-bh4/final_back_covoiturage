import time
from django.db.models import Count, Sum, Avg, F, ExpressionWrapper, fields
from rest_framework import status, viewsets
from django.db.models.functions import TruncMonth
from datetime import timedelta
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny
from .models import DriverStripeAccount, Payment, Trajet, Voiture, Driver
from .serializers import ReservationHistorySerializer, TrajetSerializer, VoitureSerializer, DriverSerializer
from rest_framework.permissions import IsAuthenticated
from .authentication import SupabaseJWTAuthentication
from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.conf import settings
from rest_framework.views import APIView
import stripe
from .serializers import TrajetDetailSerializer
stripe.api_key = settings.STRIPE_SECRET_KEY
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
    return Response(serializer.data)



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
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        """
        API pour récupérer un trajet par son ID pour l'édition
        """
        try:
            trajet = Trajet.objects.get(pk=pk)
            # Serialize the data to return it as JSON
            serializer = TrajetSerializer(trajet)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Trajet.DoesNotExist:
            return Response({"error": "Trajet non trouvé"}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        """
        API pour mettre à jour un trajet existant
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
    

@api_view(['GET'])
@permission_classes([AllowAny])  # Or use IsAuthenticated if you want to restrict access
def trajet_detail(request, trajet_id):
    """
    Get detailed information about a specific trip, including car and owner details
    """
    try:
        trajet = Trajet.objects.get(id=trajet_id)
    except Trajet.DoesNotExist:
        return Response(
            {"error": "Trip not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    serializer = TrajetDetailSerializer(trajet)
    return Response(serializer.data)




@api_view(['POST'])
@permission_classes([IsAuthenticated])
def driver_stripe_onboarding(request):
    """
    Create a Stripe Connect account for a driver and return onboarding URL
    """
    try:
        print("==== DRIVER STRIPE ONBOARDING ====")
        print("Request data:", request.data)
        print("User ID:", request.user.id)
        
        user_id = request.user.id
        
        # Check if user is a driver
        try:
            driver = Driver.objects.get(user_id=user_id)
            print(f"Found driver: {driver.id}")
        except Driver.DoesNotExist:
            print(f"Driver not found for user: {user_id}")
            return Response(
                {"error": "You must be registered as a driver first"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if driver already has a Stripe account
        try:
            existing_account = DriverStripeAccount.objects.get(driver=driver)
            print(f"Found existing account: {existing_account.stripe_account_id}")
            
            # If account exists but not verified, create a new onboarding link
            if not existing_account.is_verified:
                print("Account not verified, creating new onboarding link")
                
                # Initialize Stripe with your secret key
                stripe.api_key = settings.STRIPE_SECRET_KEY
                
                account_link = stripe.AccountLink.create(
                    account=existing_account.stripe_account_id,
                    refresh_url=f"{settings.FRONTEND_URL}/espace-driver/stripe-onboarding/refresh",
                    return_url=f"{settings.FRONTEND_URL}/espace-driver/stripe-onboarding/complete",
                    type="account_onboarding",
                )
                print(f"Created account link: {account_link.url}")
                return Response({"url": account_link.url})
            else:
                print("Account already verified")
                return Response(
                    {"error": "You already have a verified Stripe account"},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except DriverStripeAccount.DoesNotExist:
            print("No existing account, creating new Stripe account")
            
            # Initialize Stripe with your secret key
            stripe.api_key = settings.STRIPE_SECRET_KEY
            
            # Get email from request or user
            email = request.data.get('email')
            if not email:
                print("No email provided")
                return Response(
                    {"error": "Email is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            print(f"Creating account with email: {email}")
            
            # Create a new Stripe Connect account
            try:
                account = stripe.Account.create(
        type="express",
        country="TN",
        email=email,
        capabilities={
            "transfers": {"requested": True},
        },
        business_type="individual",  # Or "company" if appropriate
        settings={
            "payouts": {
                "schedule": {
                    "interval": "manual"  # Optional: Adjust payout schedule as needed
                }
            }
        },
        # Specify the recipient service agreement
        tos_acceptance={
            "service_agreement": "recipient"
        }
    
)
                print(f"Created Stripe account: {account.id}")
                
                # Create account link for onboarding
                account_link = stripe.AccountLink.create(
                    account=account.id,
                    refresh_url=f"{settings.FRONTEND_URL}/espace-driver/stripe-onboarding/refresh",
                    return_url=f"{settings.FRONTEND_URL}/espace-driver/stripe-onboarding/complete",
                    type="account_onboarding",
                )
                print(f"Created account link: {account_link.url}")
                
                # Save the Stripe account ID
                driver_account = DriverStripeAccount.objects.create(
                    driver=driver,
                    stripe_account_id=account.id,
                )
                
                return Response({
                    "account_id": account.id,
                    "url": account_link.url
                })
            except stripe.error.StripeError as e:
                print(f"Stripe error: {str(e)}")
                return Response(
                    {"error": str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
    except Exception as e:
        print(f"Error in driver_stripe_onboarding: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_stripe_account_status(request):
    """
    Check the verification status of a driver's Stripe account
    """
    try:
        user_id = request.user.id
        
        # Check if user is a driver
        try:
            driver = Driver.objects.get(user_id=user_id)
        except Driver.DoesNotExist:
            return Response(
                {"error": "You must be registered as a driver"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if driver has a Stripe account
        try:
            stripe_account = DriverStripeAccount.objects.get(driver=driver)
        except DriverStripeAccount.DoesNotExist:
            return Response({
                "has_account": False,
                "is_verified": False,
                "message": "No Stripe account found"
            })
        
        # Check account status with Stripe
        account = stripe.Account.retrieve(stripe_account.stripe_account_id)
        
        # Check if account is fully onboarded
        is_verified = account.charges_enabled and account.payouts_enabled
        
        # Update account status in database
        stripe_account.is_verified = is_verified
        stripe_account.verification_status = "verified" if is_verified else "pending"
        stripe_account.save()
        
        return Response({
            "has_account": True,
            "is_verified": is_verified,
            "status": "submitted" if account.details_submitted else "incomplete",
            "message": "Your account is fully verified" if is_verified else "Your account is pending verification"
        })
            
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
# api/views.py - Add these methods

# api/views.py - Update create_payment_intent

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_payment_intent(request):
    try:
        data = request.data
        print("Received payment data:", data)
        trajet_id = data.get('trajet_id')
        
        # Get the Trajet
        try:
            trajet = Trajet.objects.get(id=trajet_id)
            print(f"Found trajet with ID {trajet_id}, owner_id: {trajet.owner_id.id if trajet.owner_id else 'None'}")
        except Trajet.DoesNotExist:
            print(f"Trajet with ID {trajet_id} not found")
            return Response(
                {"error": "Trip not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if seats are available
        if trajet.nb_places <= 0:
            print(f"No seats available: nb_places={trajet.nb_places}")
            return Response(
                {"error": "No seats available for this trip"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Get the driver
        driver = trajet.owner_id
        if not driver:
            print("No driver found for this trajet")
            return Response(
                {"error": "This trip has no assigned driver"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        print(f"Driver ID: {driver.id}, User ID: {driver.user_id}")
        
        # First, check if the driver has ANY Stripe account (verified or not)
        any_account = DriverStripeAccount.objects.filter(driver=driver).first()
        if any_account:
            print(f"Found driver Stripe account: {any_account.stripe_account_id}, verified: {any_account.is_verified}")
            if not any_account.is_verified:
                print("Driver account exists but is NOT verified")
        else:
            print("No Stripe account found for this driver")
        
        # Check if driver has a VERIFIED Stripe account
        try:
            driver_stripe_account = DriverStripeAccount.objects.get(driver=driver, is_verified=True)
            print(f"Found verified Stripe account: {driver_stripe_account.stripe_account_id}")
        except DriverStripeAccount.DoesNotExist:
            print("No verified Stripe account found")
            return Response(
                {"error": "The driver has not set up their payment account yet"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Rest of the function continues as before...
        # Check if seats are available
        if trajet.nb_places <= 0:
            return Response(
                {"error": "No seats available for this trip"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Get the driver
        driver = trajet.owner_id
        
        # Check if driver has a Stripe account
        try:
            driver_stripe_account = DriverStripeAccount.objects.get(driver=driver, is_verified=True)
        except DriverStripeAccount.DoesNotExist:
            return Response(
                {"error": "The driver has not set up their payment account yet"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Get amount from the trajet
        amount = int(float(trajet.price) * 100)  # Convert to smallest unit (cents/millimes)
        currency = 'USD'  # Tunisian Dinar
        
        # Calculate platform fee (e.g., 10%)
        platform_fee = int(amount * 0.10)
        
        # Create a payment intent
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=currency,
            application_fee_amount=platform_fee,
            transfer_data={
                "destination": driver_stripe_account.stripe_account_id,
            },
            metadata={
                'trajet_id': str(trajet.id),
                'passenger_id': str(request.user.id),
                'driver_id': str(driver.user_id),
            }
        )
        
        # Create payment record
        payment = Payment.objects.create(
            passenger_id=request.user.id,
            driver_id=driver.user_id,
            driver_stripe_account_id=driver_stripe_account.stripe_account_id,
            trajet=trajet,
            amount=amount,
            platform_fee=platform_fee,
            currency=currency,
            stripe_payment_intent_id=intent.id,
        )
        
        return Response({
            'clientSecret': intent.client_secret,
            'paymentId': str(payment.id),
            'amount': amount / 1000,  # Convert back to TND
            'currency': currency.upper(),
        })
    
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
@api_view(['POST'])
def webhook(request):
    """
    Handle Stripe webhook events
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
        
        # Handle the event
        if event['type'] == 'payment_intent.succeeded':
            payment_intent = event['data']['object']
            handle_payment_success(payment_intent)
            
        elif event['type'] == 'payment_intent.payment_failed':
            payment_intent = event['data']['object']
            handle_payment_failure(payment_intent)
            
        elif event['type'] == 'account.updated':
            account = event['data']['object']
            handle_account_update(account)
        
        return Response({'status': 'success'})
    
    except stripe.error.SignatureVerificationError:
        return Response({'status': 'signature verification failed'}, status=400)
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=400)

def handle_payment_success(payment_intent):
    """
    Update payment status and reduce seats when payment succeeds
    """
    try:
        payment = Payment.objects.get(stripe_payment_intent_id=payment_intent['id'])
        
        # Update payment status
        payment.status = 'completed'
        payment.save()
        
        # Decrease available seats
        trajet = payment.trajet
        # if trajet.nb_places > 0:
        #     trajet.nb_places -= 1
        #     trajet.save()
            
    except Payment.DoesNotExist:
        # Log this error for investigation
        print(f"Payment not found for intent: {payment_intent['id']}")
def handle_payment_failure(payment_intent):
    """
    Update payment status when payment fails
    """
    try:
        payment = Payment.objects.get(stripe_payment_intent_id=payment_intent['id'])
        payment.status = 'failed'
        payment.save()
    except Payment.DoesNotExist:
        # Log this error for investigation
        print(f"Payment not found for intent: {payment_intent['id']}")

def handle_account_update(account):
    """
    Update driver account verification status
    """
    try:
        stripe_account = DriverStripeAccount.objects.get(stripe_account_id=account['id'])
        
        # Update verification status
        is_verified = account['charges_enabled'] and account['payouts_enabled']
        stripe_account.is_verified = is_verified
        stripe_account.verification_status = "verified" if is_verified else "pending"
        stripe_account.save()
        
    except DriverStripeAccount.DoesNotExist:
        # Log this error for investigation
        print(f"Driver Stripe account not found: {account['id']}")


# aviews not tested 

# @api_view(['GET'])
# @permission_classes([IsAuthenticated])
# def passenger_bookings(request):
#     """
#     Get all bookings for the authenticated passenger
#     """
#     try:
#         user_id = request.user.id
        
#         # Get all payments made by this passenger
#         payments = Payment.objects.filter(
#             passenger_id=user_id
#         ).select_related('trajet').order_by('-created_at')
        
#         # Format bookings for response
#         bookings_data = []
#         for payment in payments:
#             bookings_data.append({
#                 'id': payment.id,
#                 'amount': payment.amount / 1000,  # Convert to TND
#                 'currency': payment.currency,
#                 'status': payment.status,
#                 'created_at': payment.created_at,
#                 'trajet': {
#                     'id': payment.trajet.id,
#                     'driver_name': payment.trajet.name,
#                     'departure': payment.trajet.departure,
#                     'arrival': payment.trajet.arrival,
#                     'departure_date': payment.trajet.departure_date,
#                     'arrival_date': payment.trajet.arrival_date,
#                 }
#             })
        
#         return Response(bookings_data)
#     except Exception as e:
#         return Response(
#             {"error": str(e)},
#             status=status.HTTP_400_BAD_REQUEST
#         )
    
# api/views.py - Add this method

# @api_view(['GET'])
# @permission_classes([IsAuthenticated])
# def driver_earnings(request):
#     """
#     Get earnings for the authenticated driver
#     """
#     try:
#         user_id = request.user.id
        
#         # Check if user is a driver
#         try:
#             driver = Driver.objects.get(user_id=user_id)
#         except Driver.DoesNotExist:
#             return Response(
#                 {"error": "You must be registered as a driver"},
#                 status=status.HTTP_403_FORBIDDEN
#             )
        
#         # Get completed payments where this driver is the recipient
#         payments = Payment.objects.filter(
#             driver_id=user_id,
#             status='completed'
#         ).select_related('trajet').order_by('-created_at')
        
#         # Calculate total earnings
#         total_earnings = sum([(payment.amount - payment.platform_fee) for payment in payments]) / 1000
        
#         # Format earnings for response
#         earnings_data = []
#         for payment in payments:
#             earnings_data.append({
#                 'id': payment.id,
#                 'amount': payment.amount,
#                 'platform_fee': payment.platform_fee,
#                 'net_amount': payment.amount - payment.platform_fee,
#                 'currency': payment.currency,
#                 'created_at': payment.created_at,
#                 'passenger_id': payment.passenger_id,
#                 'trajet': {
#                     'id': payment.trajet.id,
#                     'departure': payment.trajet.departure,
#                     'arrival': payment.trajet.arrival,
#                 }
#             })
        
#         return Response({
#             'earnings': earnings_data,
#             'total': total_earnings
#         })
#     except Exception as e:
#         return Response(
#             {"error": str(e)},
#             status=status.HTTP_400_BAD_REQUEST
#         )




from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
import json
from .models import Trajet, Payment, Reservation

# api/views.py - Update reservation creation view

# api/views.py - Update reservation creation view

@csrf_exempt
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def creer_reservation(request):
    try:
        # Get user ID from authenticated request
        user_id = request.user.id
        
        # Parse data - either from request.body (JSON) or request.data (parsed by DRF)
        if hasattr(request, 'data') and request.data:
            data = request.data
        else:
            data = json.loads(request.body)
        
        # Validate required fields
        required_fields = ['trajet_id', 'nom', 'prenom', 'tel']
        for field in required_fields:
            if not data.get(field):
                return Response({
                    'error': f'Field {field} is required'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Get and validate trajet
        try:
            trajet = Trajet.objects.get(id=data.get('trajet_id'))
        except Trajet.DoesNotExist:
            return Response({
                'error': 'Trip not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Check if there are available seats by calculating directly
        available_seats = max(0, trajet.nb_places - trajet.reserved_seats)
        if available_seats <= 0:
            return Response({
                'error': 'No seats available for this trip'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get optional fields with defaults
        adresse = data.get('adresse', '')
        notes = data.get('notes', '')
        payment_method = data.get('payment_method', 'cash')

        # Validate payment method
        if payment_method not in ['cash', 'online']:
            return Response({
                'error': 'Invalid payment method'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Handle payment if provided
        payment = None
        if payment_method == 'online':
            payment_id = data.get('payment_id')
            if payment_id:
                try:
                    payment = Payment.objects.get(id=payment_id)
                except Payment.DoesNotExist:
                    return Response({
                        'error': 'Payment not found'
                    }, status=status.HTTP_404_NOT_FOUND)

        # Check if reservation already exists for this user and trajet
        if Reservation.objects.filter(trajet=trajet, passenger_id=user_id).exists():
            return Response({
                'error': 'You already have a reservation for this trip'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Create reservation
        reservation = Reservation.objects.create(
            trajet=trajet,
            passenger_id=user_id,
            nom=data.get('nom'),
            prenom=data.get('prenom'),
            tel=data.get('tel'),
            adresse=adresse,
            payment_method=payment_method,
            payment=payment,
            notes=notes,
            status='pending'
        )

        # Update reserved seats counter
        trajet.reserved_seats += 1
        trajet.save()

        return Response({
            'message': 'Reservation created successfully',
            'reservation_id': str(reservation.id),
            'reservation': {
                'id': str(reservation.id),
                'trajet_id': trajet.id,
                'passenger_id': user_id,
                'nom': reservation.nom,
                'prenom': reservation.prenom,
                'status': reservation.status,
                'created_at': reservation.created_at.isoformat()
            }
        }, status=status.HTTP_201_CREATED)

    except json.JSONDecodeError:
        return Response({
            'error': 'Invalid JSON format'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'error': f'Error creating reservation: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)   
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_stats(request):
    """
    Get comprehensive statistics for a driver
    """
    user_id = request.user.id
    current_time = timezone.now()
    
    try:
        # Get the driver
        driver = Driver.objects.get(user_id=user_id)
    except Driver.DoesNotExist:
        return Response(
            {"error": "You are not registered as a driver"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Base query for all trips by this driver
    all_trips = Trajet.objects.filter(owner_id=driver)
    
    # Calculate basic statistics
    total_trips = all_trips.count()
    completed_trips = all_trips.filter(status='completed').count()
    active_trips = all_trips.filter(status='active', departure_date__gt=current_time).count()
    ongoing_trips = all_trips.filter(
        status='active',
        departure_date__lt=current_time,
        arrival_date__gt=current_time
    ).count()
    
    # Calculate earnings from payments
    total_earnings = Payment.objects.filter(
        driver_id=user_id,
        status='completed'
    ).aggregate(
        total=Sum(ExpressionWrapper(
            F('amount') - F('platform_fee'),
            output_field=fields.IntegerField()
        ))
    )['total'] or 0
    
    # Convert from millimes to TND
    total_earnings_tnd = total_earnings / 1000
    
    # Get passenger count
    reservations = Reservation.objects.filter(
        trajet__owner_id=driver
    )
    total_passengers = reservations.count()
    
    # Calculate average rating (if you have a rating model)
    # For demonstration, we'll use a fixed value since ratings aren't implemented yet
    average_rating = 4.7
    
    # Monthly trips data (past 12 months)
    twelve_months_ago = current_time - timedelta(days=365)
    monthly_trips = (
        all_trips
        .filter(departure_date__gte=twelve_months_ago)
        .annotate(month=TruncMonth('departure_date'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )
    
    # Format monthly data
    formatted_monthly_trips = []
    for month_data in monthly_trips:
        month_name = month_data['month'].strftime('%b')
        formatted_monthly_trips.append({
            'month': month_name,
            'trips': month_data['count']
        })
    
    # Calculate monthly earnings
    monthly_earnings = []
    for month_data in monthly_trips:
        month_date = month_data['month']
        month_name = month_date.strftime('%b')
        
        # Get earnings for this month
        month_earnings = Payment.objects.filter(
            driver_id=user_id,
            status='completed',
            created_at__year=month_date.year,
            created_at__month=month_date.month
        ).aggregate(
            total=Sum(ExpressionWrapper(
                F('amount') - F('platform_fee'),
                output_field=fields.IntegerField()
            ))
        )['total'] or 0
        
        monthly_earnings.append({
            'month': month_name,
            'amount': month_earnings / 1000  # Convert to TND
        })
    
    # Top destinations
    top_destinations = (
        all_trips
        .values('arrival')
        .annotate(count=Count('id'))
        .order_by('-count')
        [:5]
    )
    
    # Format destinations data
    formatted_destinations = []
    for dest in top_destinations:
        formatted_destinations.append({
            'city': dest['arrival'],
            'count': dest['count']
        })
    
    # Vehicle information
    vehicle = Voiture.objects.filter(id_voiture=driver.voiture.id_voiture).first()
    vehicle_info = {
        'id': vehicle.id_voiture,
        'model': vehicle.marque,
        'licensePlate': vehicle.matricule,
        'image': vehicle.image.url if vehicle.image else None
    } if vehicle else None
    
    # Compile all statistics
    stats = {
        'totalTrips': total_trips,
        'completedTrips': completed_trips,
        'activeTrips': active_trips,
        'ongoingTrips': ongoing_trips,
        'upcomingTrips': active_trips,
        'totalPassengers': total_passengers,
        'totalEarnings': total_earnings_tnd,
        'averageRating': average_rating,
        'monthlyTrips': formatted_monthly_trips,
        'monthlyEarnings': monthly_earnings,
        'topDestinations': formatted_destinations,
        'vehicle': vehicle_info,
        # Placeholder for ratings distribution
        'ratings': [
            {'rating': 5, 'count': int(total_passengers * 0.62)},
            {'rating': 4, 'count': int(total_passengers * 0.28)},
            {'rating': 3, 'count': int(total_passengers * 0.06)},
            {'rating': 2, 'count': int(total_passengers * 0.03)},
            {'rating': 1, 'count': int(total_passengers * 0.01)},
        ]
    }
    
    return Response(stats)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_reservations(request):
    """
    Get all reservations for trips created by this driver
    """
    user_id = request.user.id
    
    try:
        # Get the driver
        driver = Driver.objects.get(user_id=user_id)
    except Driver.DoesNotExist:
        return Response(
            {"error": "You are not registered as a driver"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get reservations for this driver's trips
    reservations = Reservation.objects.filter(
        trajet__owner_id=driver
    ).select_related('trajet', 'payment').order_by('-created_at')
    
    # Format reservation data
    formatted_reservations = []
    for res in reservations:
        formatted_reservations.append({
            'id': str(res.id),
            'passenger': {
                'id': res.passenger_id,
                'name': f"{res.prenom} {res.nom}",
                'phone': res.tel
            },
            'trip': {
                'id': res.trajet.id,
                'departure': res.trajet.departure,
                'arrival': res.trajet.arrival,
                'departure_date': res.trajet.departure_date,
                'status': res.trajet.status
            },
            'status': res.status,
            'payment_method': res.payment_method,
            'payment_status': res.payment.status if res.payment else None,
            'created_at': res.created_at
        })
    
    return Response(formatted_reservations)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_earnings(request):
    """
    Get earnings details for a driver
    """
    user_id = request.user.id
    
    try:
        # Get the driver
        driver = Driver.objects.get(user_id=user_id)
    except Driver.DoesNotExist:
        return Response(
            {"error": "You are not registered as a driver"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get completed payments for this driver
    payments = Payment.objects.filter(
        driver_id=user_id,
        status='completed'
    ).select_related('trajet').order_by('-created_at')
    
    # Calculate total earnings
    total_earnings = sum([(payment.amount - payment.platform_fee) for payment in payments]) / 1000
    
    # Format payments data
    formatted_payments = []
    for payment in payments:
        net_amount = (payment.amount - payment.platform_fee) / 1000  # Convert to TND
        formatted_payments.append({
            'id': str(payment.id),
            'date': payment.created_at,
            'passenger_id': payment.passenger_id,
            'trip': {
                'id': payment.trajet.id,
                'departure': payment.trajet.departure,
                'arrival': payment.trajet.arrival,
                'departure_date': payment.trajet.departure_date
            },
            'amount': payment.amount / 1000,  # Convert to TND
            'platform_fee': payment.platform_fee / 1000,  # Convert to TND
            'net_amount': net_amount,
            'currency': payment.currency.upper()
        })
    
    # Compile earnings data
    earnings_data = {
        'total': total_earnings,
        'transactions': formatted_payments
    }
    
    return Response(earnings_data)

# api/views.py - Update the update_reservation_status function

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_reservation_status(request):
    """
    Update the status of a reservation (accept or reject)
    Only the driver of the associated trip can update the status
    """
    try:
        user_id = request.user.id
        data = request.data
        
        # Validate required fields
        if not data.get('reservation_id') or not data.get('status'):
            return Response({
                'error': 'Reservation ID and status are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate status value
        new_status = data.get('status')
        if new_status not in ['accepted', 'rejected']:
            return Response({
                'error': 'Status must be either "accepted" or "rejected"'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the reservation
        try:
            reservation = Reservation.objects.get(id=data.get('reservation_id'))
        except Reservation.DoesNotExist:
            return Response({
                'error': 'Reservation not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user is the driver of this trip
        try:
            driver = Driver.objects.get(user_id=user_id)
        except Driver.DoesNotExist:
            return Response({
                'error': 'You are not registered as a driver'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check if the trip belongs to this driver
        if reservation.trajet.owner_id.id != driver.id:
            return Response({
                'error': 'You do not have permission to update this reservation'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Only update if current status is 'pending'
        if reservation.status != 'pending':
            return Response({
                'error': f'Cannot update reservation with status "{reservation.status}"'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Handle seat count based on status change
        trajet = reservation.trajet
        
        # Update reservation status
        reservation.status = new_status
        reservation.save()
        
        # If rejected, decrease reserved seats counter
        if new_status == 'rejected':
            trajet.reserved_seats = max(0, trajet.reserved_seats - 1)
            trajet.save()
            message = 'Reservation rejected successfully'
        else:
            # Keep reserved_seats as is for accepted status
            message = 'Reservation accepted successfully'
        
        # Calculate available seats directly instead of using a non-existent attribute
        available_seats = max(0, trajet.nb_places - trajet.reserved_seats)
        
        return Response({
            'message': message,
            'reservation': {
                'id': str(reservation.id),
                'status': reservation.status,
                'trajet': {
                    'id': trajet.id,
                    'reserved_seats': trajet.reserved_seats,
                    'available_seats': available_seats  # Use calculated value here
                }
            }
        })
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)     
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
# api/views.py - Add reservation cancellation endpoint

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_reservation(request):
    """
    Cancel a reservation - only the passenger who made the reservation can cancel it
    """
    try:
        user_id = request.user.id
        data = request.data
        
        # Validate input
        if not data.get('reservation_id'):
            return Response({
                'error': 'Reservation ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the reservation
        try:
            reservation = Reservation.objects.get(
                id=data.get('reservation_id'),
                passenger_id=user_id  # Ensure the user owns this reservation
            )
        except Reservation.DoesNotExist:
            return Response({
                'error': 'Reservation not found or not authorized'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if reservation can be cancelled
        if reservation.status not in ['pending', 'accepted']:
            return Response({
                'error': f'Cannot cancel reservation with status "{reservation.status}"'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update reservation status
        reservation.status = 'cancelled'
        reservation.save()
        
        # Update reserved seats counter
        trajet = reservation.trajet
        trajet.reserved_seats = max(0, trajet.reserved_seats - 1)
        trajet.save()
        
        return Response({
            'message': 'Reservation cancelled successfully',
            'trajet': {
                'id': trajet.id,
                'reserved_seats': trajet.reserved_seats,
                'available_seats': trajet.available_seats
            }
        })
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
class ReservationHistoryView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [SupabaseJWTAuthentication]
    def get(self, request):
        user = request.user
        reservations = Reservation.objects.filter(passenger_id=user.id).order_by('-created_at')
        serializer = ReservationHistorySerializer(reservations, many=True)
        return Response(serializer.data)


@api_view(['PUT'])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAuthenticated])
def update_driver_vehicle(request):
    """
    Update a driver's vehicle information
    """
    user_id = request.user.id
    
    print(f"update_driver_vehicle called for user_id: {user_id}")
    print(f"Request data: {request.data}")
    
    try:
        # Get the driver and associated vehicle
        try:
            driver = Driver.objects.get(user_id=user_id)
            print(f"Found driver with id: {driver.id}")
        except Driver.DoesNotExist:
            print(f"No driver found for user_id: {user_id}")
            return Response({
                'error': 'You are not registered as a driver'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get the vehicle
        try:
            voiture = driver.voiture
            print(f"Found vehicle: {voiture.id_voiture} - {voiture.marque}")
        except Exception as e:
            print(f"Error getting vehicle for driver: {str(e)}")
            return Response({
                'error': f'Error getting vehicle: {str(e)}'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Update the vehicle with provided data
        if 'marque' in request.data:
            voiture.marque = request.data['marque']
            print(f"Updated marque to: {voiture.marque}")
            
        if 'matricule' in request.data:
            voiture.matricule = request.data['matricule']
            print(f"Updated matricule to: {voiture.matricule}")
            
        if 'image' in request.FILES:
            print(f"New image provided, filename: {request.FILES['image'].name}")
            # If there was an old image, delete it if needed
            # (Django will handle replacing the file)
            voiture.image = request.FILES['image']
        
        # Save changes
        voiture.save()
        print(f"Vehicle {voiture.id_voiture} updated successfully")
        
        # Serialize and return updated vehicle
        serializer = VoitureSerializer(voiture)
        return Response({
            'message': 'Vehicle updated successfully',
            'vehicle': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"Unexpected error in update_driver_vehicle: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({
            'error': f'Error updating vehicle: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)  

    
class VoitureViewSet(viewsets.ModelViewSet):
    queryset = Voiture.objects.all()
    serializer_class = VoitureSerializer
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]  # Require authenticated users
    authentication_classes = [SupabaseJWTAuthentication]

    def get_queryset(self):
        user_id = self.request.user.id  # user_id from JWT
        
        # Log for debugging
        print(f"Fetching vehicles for user_id: {user_id}")
        
        # First, check if this user is a driver
        try:
            driver = Driver.objects.get(user_id=user_id)
            print(f"Found driver with id: {driver.id}, fetching vehicle with id: {driver.voiture.id_voiture}")
            
            # Return specifically this driver's vehicle
            return Voiture.objects.filter(id_voiture=driver.voiture.id_voiture)
        except Driver.DoesNotExist:
            print(f"No driver found for user_id: {user_id}")
            return Voiture.objects.none()  # Return empty queryset if not a driver
        except Exception as e:
            print(f"Error in VoitureViewSet.get_queryset: {str(e)}")
            return Voiture.objects.none()
    
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def debug_driver_vehicle(request):
    """
    Debug endpoint to verify driver vehicle association
    """
    user_id = request.user.id
    
    print(f"debug_driver_vehicle called for user_id: {user_id}")
    
    response_data = {
        "user_id": user_id,
        "driver_found": False,
        "vehicle_found": False,
        "details": {}
    }
    
    try:
        # Try to get the driver
        try:
            driver = Driver.objects.get(user_id=user_id)
            response_data["driver_found"] = True
            response_data["details"]["driver"] = {
                "id": driver.id,
                "user_id": driver.user_id
            }
            
            # Try to get the vehicle
            try:
                vehicle = driver.voiture
                response_data["vehicle_found"] = True
                response_data["details"]["vehicle"] = {
                    "id": vehicle.id_voiture,
                    "marque": vehicle.marque,
                    "matricule": vehicle.matricule,
                    "has_image": bool(vehicle.image)
                }
            except Exception as e:
                response_data["details"]["vehicle_error"] = str(e)
                
        except Driver.DoesNotExist:
            response_data["details"]["driver_error"] = "Driver not found for this user"
            
    except Exception as e:
        response_data["details"]["error"] = str(e)
    
    return Response(response_data)