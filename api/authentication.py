from urllib.parse import urlparse
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.conf import settings
import jwt
from types import SimpleNamespace

class SupabaseJWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return None

        token = auth_header.split(' ')[1]

        try:
            parsed_url = urlparse(settings.SUPABASE_URL)
            if not parsed_url.scheme or not parsed_url.netloc:
                raise ValueError("SUPABASE_URL is invalid. It must include a protocol (e.g., 'https://') and domain.")

            issuer = f'{parsed_url.scheme}://{parsed_url.netloc}/auth/v1'

            payload = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=['HS256'],
                audience='authenticated',
                issuer=issuer
            )

            user_id = payload.get('sub')
            if not user_id:
                raise AuthenticationFailed('Invalid token: No user ID found')

            # Create a minimal user object
            user = SimpleNamespace(
                id=user_id,
                is_authenticated=True,
                is_anonymous=False
            )

            return (user, token)

        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Token has expired')
        except jwt.InvalidTokenError:
            raise AuthenticationFailed('Invalid token')
        except ValueError as e:
            raise AuthenticationFailed(str(e))