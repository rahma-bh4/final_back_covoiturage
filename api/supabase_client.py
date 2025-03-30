from supabase import create_client

SUPABASE_URL = "https://zxozkxeqvikvieodhwmg.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp4b3preGVxdmlrdmllb2Rod21nIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDA5MTE4NzIsImV4cCI6MjA1NjQ4Nzg3Mn0.yCgTkesQ9ad5y5FpsEpr7rYYa4UeM6sUz1jK0-Q8jwM"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
# Add to supabase_client.py
def update_user_role(user_id, role):
    """Update a user's role in Supabase"""
    try:
        # You need admin privileges to update user metadata
        # This may require a different API key with more permissions
        response = supabase.auth.admin.update_user(
            user_id,
            {"user_metadata": {"role": role}}
        )
        return True, response
    except Exception as e:
        return False, str(e)