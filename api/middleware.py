import requests
from django.http import JsonResponse

CLERK_SECRET_KEY = "sk_test_ZwEgLiPUjkw43KGwuNzxATzBrKj89HG5TKVbKO5lSt"

def verify_clerk_token(token):
    headers = {"Authorization": f"Bearer {CLERK_SECRET_KEY}"}
    response = requests.get("https://api.clerk.dev/v1/me", headers=headers)

    if response.status_code == 200:
        return response.json()  # User details
    return None

class ClerkAuthenticationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            user_data = verify_clerk_token(token)
            if user_data:
                request.clerk_user = user_data
            else:
                return JsonResponse({"error": "Invalid token"}, status=401)
        return self.get_response(request)
