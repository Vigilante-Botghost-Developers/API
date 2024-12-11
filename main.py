from fastapi import FastAPI, Depends, Request, HTTPException
from pydantic import BaseModel, RootModel
from typing import Optional
import os
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
from auth import UserFlag, get_user_flags, get_api_key, RateLimits, create_api_key, db
import redis.asyncio as redis

app = FastAPI(
    title="Test API",
    description="A simple test API with basic endpoints",
    docs_url=None,    # Disable Swagger UI
    redoc_url=None,   # Disable ReDoc
    openapi_url=None  # Disable OpenAPI schema
)

# Initialize rate limiter on startup
@app.on_event("startup")
async def startup():
    redis_url = f"redis://default:QFwgvvKladQiQsrsjYLtvTYLlmzPxyqS@redis.railway.internal:6379"
    
    try:
        redis_instance = redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=10
        )
        # Test the connection
        await redis_instance.ping()
        await FastAPILimiter.init(redis_instance)
    except Exception as e:
        print(f"Failed to connect to Redis: {e}")
        raise

async def get_rate_limit(request: Request):
    """Dynamic rate limiting based on user flags"""
    try:
        api_key = await get_api_key(request)
        user_flags = await get_user_flags(api_key)
        
        # Get highest rate limit from user's flags
        rate_limit = RateLimits.UNAUTHENTICATED_LIMIT
        for flag in user_flags:
            flag_limit = RateLimits.FLAG_LIMITS.get(flag, 0)
            if flag_limit == -1:  # Unlimited for ADMINISTRATOR and SYSTEM_OPERATOR
                return None
            rate_limit = max(rate_limit, flag_limit)
        
        return RateLimiter(times=rate_limit, minutes=1)
    except Exception as e:
        print(f"Rate limit error: {str(e)}")
        # Default to most restrictive limit on error
        return RateLimiter(times=RateLimits.UNAUTHENTICATED_LIMIT, minutes=1)

class Message(BaseModel):
    content: str

class Number(BaseModel):
    value: float
    decimal_places: Optional[int] = 2

class UnformattedNumber(BaseModel):
    value: str

class WebhookRequest(RootModel):
    root: dict

@app.get("/")
async def read_root(request: Request, _=Depends(get_rate_limit)):
    return {"message": "Welcome to the Test API"}

@app.post("/echo")
async def echo_message(request: Request, message: Optional[Message] = None, params: dict = None, _=Depends(get_rate_limit)):
    response = {}
    if message:
        response["message"] = message.content
    if params:
        response["params"] = params
    return response

@app.post("/format-number")
async def format_number(request: Request, number: Number, _=Depends(get_rate_limit)):
    formatted = "{:,.{precision}f}".format(number.value, precision=number.decimal_places)
    return {"formatted": formatted}

@app.post("/unformat-number")
async def unformat_number(request: Request, number: UnformattedNumber, _=Depends(get_rate_limit)):
    # Remove all non-numeric characters except decimal point
    unformatted = ''.join(char for char in number.value if char.isdigit() or char == '.')
    return {"unformatted": unformatted}

@app.post("/webhook")
async def webhook(request: Request, webhook_request: WebhookRequest, _=Depends(get_rate_limit)):
    variables = []
    
    for var_name, value in webhook_request.root.items():
        # Check if variable name is surrounded by curly brackets
        if not (var_name.startswith("{") and var_name.endswith("}")):
            return {"error": f"Variable name '{var_name}' must be surrounded by curly brackets"}
        
        # Strip the curly brackets to get the clean variable name
        clean_var_name = var_name[1:-1]
        
        variable_obj = {
            "name": clean_var_name,
            "variable": var_name,
            "value": value
        }
        variables.append(variable_obj)
        
        # Print the variable object to console
        print(f"Processed variable: {variable_obj}")
    
    return {"variables": variables}

@app.post("/create-test-users")
async def create_test_users_endpoint():
    """Create test users with different flags and return their API keys."""
    api_keys = await create_api_key()
    return {
        "message": "Test users created successfully",
        "api_keys": api_keys
    }

@app.post("/setup-test-data")
async def setup_test_data():
    """Create test users in Firestore and return their API keys."""
    try:
        # Create test users in Firestore
        test_users = [
            {
                "id": "test_user",
                "email": "test@example.com",
                "flags": [UserFlag.USER]
            },
            {
                "id": "test_elevated",
                "email": "elevated@example.com",
                "flags": [UserFlag.USER, UserFlag.ELEVATED_USER]
            },
            {
                "id": "test_admin",
                "email": "admin@example.com",
                "flags": [UserFlag.USER, UserFlag.ADMINISTRATOR]
            },
            {
                "id": "test_sysop",
                "email": "sysop@example.com",
                "flags": [UserFlag.USER, UserFlag.SYSTEM_OPERATOR]
            }
        ]
        
        api_keys = {}
        for user in test_users:
            # Create user in Firestore
            db.collection('users').document(user['id']).set({
                'email': user['email'],
                'flags': [flag.value for flag in user['flags']]  # Store enum values as strings
            })
            
            # Generate API key
            api_key = await create_api_key(user['id'], expires_in_days=365)
            api_keys[user['id']] = api_key
            
        return {
            "message": "Test data created successfully",
            "api_keys": api_keys,
            "rate_limits": {
                "test_user": "100 requests/minute",
                "test_elevated": "2500 requests/minute",
                "test_admin": "unlimited",
                "test_sysop": "unlimited",
                "unauthenticated": "10 requests/minute"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create test data: {str(e)}")
