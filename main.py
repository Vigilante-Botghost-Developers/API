from fastapi import FastAPI, Depends, Request
from pydantic import BaseModel, RootModel
from typing import Optional
import os
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
from auth import UserFlag, get_user_flags, get_api_key, RateLimits
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

async def get_rate_limit():
    """Dynamic rate limiting based on user flags"""
    try:
        request = Request(scope={})  # Create empty request if none available
        api_key = await get_api_key(request)
        user_flags = await get_user_flags(api_key)
        
        if not user_flags:
            return RateLimiter(times=RateLimits.UNAUTHENTICATED_LIMIT, minutes=1)
        
        # Get highest rate limit from user's flags
        rate_limit = RateLimits.UNAUTHENTICATED_LIMIT
        for flag in user_flags:
            flag_limit = RateLimits.FLAG_LIMITS.get(flag, 0)
            if flag_limit == -1:  # Unlimited for ADMINISTRATOR and SYSTEM_OPERATOR
                return None
            rate_limit = max(rate_limit, flag_limit)
        
        return RateLimiter(times=rate_limit, minutes=1)
    except Exception as e:
        print(f"Rate limit error: {e}")
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

# i pray to Tude, our lord 
@app.get("/", dependencies=[Depends(get_rate_limit)])
def read_root():
    return {"message": "Welcome to the Test API"}

@app.post("/echo", dependencies=[Depends(get_rate_limit)])
async def echo_message(message: Optional[Message] = None, params: dict = None):
    response = {}
    if message:
        response["message"] = message.content
    if params:
        response["params"] = params
    return response

@app.post("/format-number", dependencies=[Depends(get_rate_limit)])
def format_number(number: Number):
    formatted = "{:,.{precision}f}".format(number.value, precision=number.decimal_places)
    return {"formatted": formatted}

@app.post("/unformat-number", dependencies=[Depends(get_rate_limit)])
def unformat_number(number: UnformattedNumber):
    # Remove all non-numeric characters except decimal point
    unformatted = ''.join(char for char in number.value if char.isdigit() or char == '.')
    return {"unformatted": unformatted}

@app.post("/webhook", dependencies=[Depends(get_rate_limit)])
async def webhook(request: WebhookRequest):
    variables = []
    
    for var_name, value in request.root.items():
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
