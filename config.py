import os

# Environment variables (consider using a more robust configuration method for production)
GROQ_API_KEY = os.environ.get(
    "GROQ_API_KEY",
    "gsk_your_actual_groq_api_key"  # Replace with your actual key or env var
)

# User data (consider a database for a real application)
USER_DATA = {
    "1234567890-98109": {
        "authenticated": True
    },
    "9876543210-12345": {
        "authenticated": True
    },
    "8473236970-98012": {
        "authenticated": True
    },
}
