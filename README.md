# Test FastAPI Application

A simple FastAPI application with basic endpoints for testing.

## Endpoints

1. `/echo` - Returns the message sent to it
2. `/format-number` - Converts a number into human-readable format

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
uvicorn main:app --reload
```

3. Access the API documentation at: http://localhost:8000/docs
