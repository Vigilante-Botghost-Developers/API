from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

app = FastAPI(
    title="Test API",
    description="A simple test API with basic endpoints",
    docs_url=None,    # Disable Swagger UI
    redoc_url=None,   # Disable ReDoc
    openapi_url=os.getenv("OPENAPI_URL")  # Disable OpenAPI schema
)

class Message(BaseModel):
    content: str

class Number(BaseModel):
    value: float
    decimal_places: Optional[int] = 2

@app.get("/")
def read_root():
    return {"message": "Welcome to the Test API"}

@app.post("/echo")
def echo_message(message: Message):
    return {"echo": message.content}

@app.post("/format-number")
def format_number(number: Number):
    formatted = "{:,.{precision}f}".format(number.value, precision=number.decimal_places)
    return {"formatted": formatted}