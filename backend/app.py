from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="TruthGuard API",
    description="Backend API for TruthGuard misinformation detection",
    version="1.0.0"
)


class ClaimRequest(BaseModel):
    text: str


@app.get("/")
def home():
    return {
        "message": "TruthGuard API is running",
        "status": "online"
    }


@app.post("/analyze")
def analyze_claim(request: ClaimRequest):
    text = request.text.strip()

    if not text:
        return {
            "label": "unknown",
            "confidence": 0,
            "message": "No claim provided"
        }

    return {
        "label": "uncertain",
        "confidence": 0.50,
        "claim": text,
        "message": "Claim received successfully"
    }