import time
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny
from .models import DriverStripeAccount, Payment, Trajet, Voiture, Driver
from .serializers import TrajetSerializer, VoitureSerializer, DriverSerializer
from rest_framework.permissions import IsAuthenticated
from .authentication import SupabaseJWTAuthentication
from django.utils import timezone

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
        trajet_id = data.get('trajet_id')
        
        # Get the Trajet
        try:
            trajet = Trajet.objects.get(id=trajet_id)
        except Trajet.DoesNotExist:
            return Response(
                {"error": "Trip not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
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
        if trajet.nb_places > 0:
            trajet.nb_places -= 1
            trajet.save()
            
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