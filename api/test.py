import jwt
import requests
from jwt import PyJWKClient

TOKEN = "eyJhbGciOiJSUzI1NiIsImNhdCI6ImNsX0I3ZDRQRDExMUFBQSIsImtpZCI6Imluc18ydGxkVkRXMXVJSWkza0ROQ1VOZXhERWFIYjkiLCJ0eXAiOiJKV1QifQ.eyJleHAiOjE3NDIyMTM2NzYsImZ2YSI6Wzk5OTk5LC0xXSwiaWF0IjoxNzQyMTIzNjc2LCJpc3MiOiJodHRwczovL2Z1bi1ncnViLTUxLmNsZXJrLmFjY291bnRzLmRldiIsIm5iZiI6MTc0MjEyMzY2Niwic2lkIjoic2Vzc18ydU9kYjV1STQ0a0NzZ3ZJNFllQ3Q0b0ZIaWgiLCJzdWIiOiJ1c2VyXzJ1TkVSMmtvRnNOcjdwaGNURVlrbThLVUQ3cCJ9.D4iilVne90dE38hHgk2XAy31VzPygtok8vk61IaZ0tMr2YB2Hrc2VUesIysToAbFONDOgT83laub4NfjjUMngPJuUtA8IjCwOP8gxBKSScF4Me05ZGAj-YK4m_6Vde-Tu8rAyiD39nOwgj6VdxU-PokQnHul_xX_slGHhrt3i1ulE7mjs3NQlXWtdmSJg8Zwc1t7pu2wpPUdb8iRKj7zuxsMw3MCxcUuwl-4Bp9pRiKnjvoFxCqN_EWMQyodw6xavejgYaLV1aGzkfz4v3ZF93UL7EXuxYwEACCkNyYN4gf5QiHrSwOagPTTxJSrUwEejg1zrkbQ4WTYSI-IrtRk6A"
CLERK_DOMAIN = "fun-grub-51.clerk.accounts.dev"

# Use PyJWKClient to fetch and manage JWKS keys
jwks_url = f"https://{CLERK_DOMAIN}/.well-known/jwks.json"
jwks_client = PyJWKClient(jwks_url)

# Extract public key using PyJWKClient
signing_key = jwks_client.get_signing_key_from_jwt(TOKEN).key

try:
    # Decode JWT
    decoded = jwt.decode(
        TOKEN,
        signing_key,
        algorithms=["RS256"],
        issuer=f"https://{CLERK_DOMAIN}",
        options={"verify_exp": True},  # Ensure expiration check
    )
    print("Decoded Token:", decoded)
except jwt.ExpiredSignatureError:
    print("Token expired!")
except jwt.InvalidTokenError as e:
    print(f"Invalid token: {e}")
