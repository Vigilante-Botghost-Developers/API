from enum import Enum
import firebase_admin
from firebase_admin import credentials, firestore
from fastapi import Request, HTTPException, Depends
from functools import wraps
import os
from typing import List, Optional, Dict
import redis.asyncio as redis
import json
import secrets
import time

# Initialize Firebase Admin with environment variables
cred = credentials.Certificate({
    "type": "service_account",
    "project_id": os.environ.get("FIREBASE_PROJECT_ID"),
    "private_key": os.environ.get("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n"),
    "client_email": os.environ.get("FIREBASE_CLIENT_EMAIL"),
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{os.environ.get('FIREBASE_CLIENT_EMAIL', '').replace('@', '%40')}"
})
firebase_admin.initialize_app(cred)
db = firestore.client()

# Initialize Redis with environment variables
redis_url = os.environ.get("REDIS_URL")
if not redis_url:
    raise ValueError("REDIS_URL environment variable is not set")

try:
    redis_client = redis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=5,  # Reduce timeout
        socket_keepalive=True      # Keep connection alive
    )
    # Test the connection
    redis_client.ping()
except Exception as e:
    print(f"Failed to initialize Redis client: {e}")
    raise

class UserFlag(str, Enum):
    USER = "USER"
    ELEVATED_USER = "ELEVATED_USER"
    ADMINISTRATOR = "ADMINISTRATOR"
    SYSTEM_OPERATOR = "SYSTEM_OPERATOR"

class RateLimits:
    FLAG_LIMITS = {
        UserFlag.USER: 100,            # 100 requests per minute
        UserFlag.ELEVATED_USER: 2500,   # 2500 requests per minute
        UserFlag.ADMINISTRATOR: -1,    # Unlimited
        UserFlag.SYSTEM_OPERATOR: -1   # Unlimited
    }
    UNAUTHENTICATED_LIMIT = 10        # 10 requests per minute

async def create_api_key(user_id: str, expires_in_days: int = 30) -> str:
    """Create a new API key for a user."""
    try:
        api_key = f"key_{secrets.token_urlsafe(32)}"
        expires_at = int(time.time()) + (expires_in_days * 24 * 60 * 60)
        
        # Store API key in Redis with user_id and expiration
        key_data = {
            "user_id": user_id,
            "created_at": int(time.time()),
            "expires_at": expires_at
        }
        
        await redis_client.set(
            f"apikey:{api_key}",
            json.dumps(key_data),
            ex=expires_in_days * 24 * 60 * 60
        )
        
        return api_key
    except Exception as e:
        print(f"Error creating API key: {e}")
        raise HTTPException(status_code=500, detail="Failed to create API key")

async def get_api_key(request: Request) -> Optional[str]:
    """Extract API key from request header."""
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return None
    return api_key

async def get_user_flags(api_key: Optional[str] = None) -> List[UserFlag]:
    """Get user flags based on API key."""
    if not api_key:
        return []
        
    user_id = await validate_api_key(api_key)
    if not user_id:
        return []
    
    # Get user flags from Firestore
    user_doc = db.collection('users').document(user_id).get()
    if not user_doc.exists:
        return []
        
    user_data = user_doc.to_dict()
    return [UserFlag(flag) for flag in user_data.get('flags', [])]

async def validate_api_key(api_key: str) -> Optional[str]:
    """Validate API key and return user_id if valid."""
    if not api_key:
        return None
        
    key_data = await redis_client.get(f"apikey:{api_key}")
    if not key_data:
        return None
        
    key_data = json.loads(key_data)
    
    # Check if key has expired
    if int(time.time()) > key_data["expires_at"]:
        await redis_client.delete(f"apikey:{api_key}")
        return None
        
    return key_data["user_id"]

async def revoke_api_key(api_key: str):
    """Revoke an API key."""
    await redis_client.delete(f"apikey:{api_key}")

async def list_user_api_keys(user_id: str) -> List[dict]:
    """List all API keys for a user."""
    keys = []
    async for key in redis_client.scan_iter(match="apikey:*"):
        key_data = await redis_client.get(key)
        if key_data:
            key_data = json.loads(key_data)
            if key_data["user_id"] == user_id:
                keys.append({
                    "key": key.split(":", 1)[1],
                    **key_data
                })
    return keys

async def create_test_users() -> Dict[str, str]:
    """Create test users with different flags and API keys."""
    try:
        # Start with just one test user
        test_user = {
            "id": "test_admin",
            "flags": [UserFlag.USER, UserFlag.ADMINISTRATOR],
            "email": "admin@example.com"
        }
        
        # Create or update user in Firestore
        db.collection('users').document(test_user['id']).set({
            'email': test_user['email'],
            'flags': [flag.value for flag in test_user['flags']]
        })
        
        # Create API key
        api_key = await create_api_key(test_user['id'], expires_in_days=365)
        
        return {test_user['id']: api_key}
    except Exception as e:
        print(f"Error in create_test_users: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def requires_flags(required_flags: List[UserFlag], any_of: bool = False):
    """Decorator to require specific user flags."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get('request')
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            
            api_key = await get_api_key(request)
            user_flags = await get_user_flags(api_key)
            
            if any_of:
                if not any(flag in user_flags for flag in required_flags):
                    raise HTTPException(
                        status_code=403,
                        detail=f"This endpoint requires any of these flags: {[flag.value for flag in required_flags]}"
                    )
            else:
                if not all(flag in user_flags for flag in required_flags):
                    raise HTTPException(
                        status_code=403,
                        detail=f"This endpoint requires all these flags: {[flag.value for flag in required_flags]}"
                    )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator
