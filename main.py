from fastapi import FastAPI
from pydantic import BaseModel, RootModel
from typing import Optional
import os

app = FastAPI(
    title="Test API",
    description="A simple test API with basic endpoints",
    docs_url=None,    # Disable Swagger UI
    redoc_url=None,   # Disable ReDoc
    openapi_url=None  # Disable OpenAPI schema
)

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
@app.get("/")
def read_root():
    return {"message": "Welcome to the Test API"}

@app.post("/echo")
async def echo_message(message: Optional[Message] = None, params: dict = None):
    response = {}
    if message:
        response["message"] = message.content
    if params:
        response["params"] = params
    return response

@app.post("/format-number")
def format_number(number: Number):
    formatted = "{:,.{precision}f}".format(number.value, precision=number.decimal_places)
    return {"formatted": formatted}

@app.post("/unformat-number")
def unformat_number(number: UnformattedNumber):
    # Remove all non-numeric characters except decimal point
    unformatted = ''.join(char for char in number.value if char.isdigit() or char == '.')
    return {"unformatted": unformatted}

@app.post("/webhook")
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
