from pathlib import Path
import json

import joblib
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Model loading
# --------------------------------------------------------------------------- #

MODEL_DIR = Path(__file__).resolve().parent / "model"
VECTORIZER_PATH = MODEL_DIR / "vectorizer.pkl"
CLASSIFIER_PATH = MODEL_DIR / "classifier.pkl"
LABELS_PATH = MODEL_DIR / "labels.json"

TOP_K_CLUES = 8  # how many positive / negative clues to return

app = FastAPI(title="TruthGuard API", version="1.2.0")

# The browser extension calls this API from a chrome-extension:// origin,
# which is why permissive CORS is needed for local development.
# Tighten this before any public deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

vectorizer = None
classifier = None
labels = []
model_error = None

try:
    vectorizer = joblib.load(VECTORIZER_PATH)
    classifier = joblib.load(CLASSIFIER_PATH)
    with open(LABELS_PATH, "r", encoding="utf-8") as fh:
        labels = json.load(fh)
except Exception as exc:  # noqa: BLE001 - report any load failure to the client
    model_error = f"{type(exc).__name__}: {exc}"

# The classifier stores classes in its own order; that order defines the rows
# of classifier.coef_. Use it so index alignment in the explanation is exact.
MODEL_CLASSES = [str(c) for c in classifier.classes_] if classifier is not None else []


# --------------------------------------------------------------------------- #
# Request / response models
# --------------------------------------------------------------------------- #


class AnalyzeRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        # Generous limit: a full news article is commonly ~25,000-30,000
        # characters. A tighter cap made "Analyze Page" fail with HTTP 422 on
        # ordinary articles. The bound exists only to reject abusive payloads.
        max_length=200000,
        description="Claim or page text to analyse.",
    )


# --------------------------------------------------------------------------- #
# Explanation logic
# --------------------------------------------------------------------------- #


def build_explanation(text: str, class_index: int, top_k: int = TOP_K_CLUES) -> dict:
    """
    Return the strongest positive and negative feature contributions to the
    linear score of `class_index`.

    Only features actually present in `text` are considered, so every clue
    listed is a real term from the input.
    """
    if vectorizer is None or classifier is None:
        return {
            "available": False,
            "positive_clues": [],
            "negative_clues": [],
            "note": "Model not loaded, so no explanation is available.",
        }

    matrix = vectorizer.transform([text])

    if matrix.nnz == 0:
        return {
            "available": False,
            "positive_clues": [],
            "negative_clues": [],
            "note": (
                "None of the words in this text appear in the model's training "
                "vocabulary, so no feature-level explanation could be produced."
            ),
        }

    vocabulary = vectorizer.get_feature_names_out()
    coefficients = classifier.coef_[class_index]

    contributions = []
    for feature_index, tfidf_value in zip(matrix.indices, matrix.data):
        contribution = float(tfidf_value) * float(coefficients[feature_index])
        contributions.append((str(vocabulary[feature_index]), contribution))

    contributions.sort(key=lambda pair: pair[1], reverse=True)

    positive_clues = [
        {"term": term, "contribution": round(value, 5)}
        for term, value in contributions
        if value > 0
    ][:top_k]

    negative_clues = [
        {"term": term, "contribution": round(value, 5)}
        for term, value in reversed(contributions)
        if value < 0
    ][:top_k]

    return {
        "available": True,
        "predicted_class": MODEL_CLASSES[class_index],
        "positive_clues": positive_clues,
        "negative_clues": negative_clues,
        "note": (
            "These are model feature contributions, not verified evidence. "
            "They show which words raised or lowered the model's score for this "
            "class, and say nothing about whether the claim is factually true."
        ),
    }


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@app.get("/")
def health():
    """Health / status endpoint used by the extension's connection indicator."""
    return {
        "status": "ok",
        "service": "TruthGuard API",
        "version": app.version,
        "model_loaded": classifier is not None and vectorizer is not None,
        "classes": labels or MODEL_CLASSES,
        "model_error": model_error,
    }


@app.post("/analyze")
def analyze(request: AnalyzeRequest):
    text = request.text.strip()

    if not text:
        return {
            "claim": request.text,
            "label": "uncertain",
            "confidence": 0.0,
            "class_probabilities": {},
            "explanation": {
                "available": False,
                "positive_clues": [],
                "negative_clues": [],
                "note": "No text was provided to analyse.",
            },
            "caution": "No text was provided, so no analysis was performed.",
        }

    if classifier is None or vectorizer is None:
        return {
            "claim": text,
            "label": "unavailable",
            "confidence": 0.0,
            "class_probabilities": {},
            "explanation": {
                "available": False,
                "positive_clues": [],
                "negative_clues": [],
                "note": "The trained model could not be loaded on the server.",
            },
            "caution": f"Model unavailable: {model_error}",
        }

    matrix = vectorizer.transform([text])
    probabilities = classifier.predict_proba(matrix)[0]
    class_index = int(probabilities.argmax())

    class_probabilities = {
        label: round(float(probabilities[i]), 4)
        for i, label in enumerate(MODEL_CLASSES)
    }

    # The model was trained on short claims (~25 words). Longer text is far
    # outside that distribution, so say so plainly instead of silently
    # returning a confident-looking number.
    word_count = len(text.split())
    input_warning = None
    if word_count > 100:
        input_warning = (
            f"This text is about {word_count} words long. The model was trained on "
            "short claims of roughly 25 words, so a prediction on text this long is "
            "outside its intended use and should not be read as a fact-check."
        )

    return {
        "claim": text,
        "label": MODEL_CLASSES[class_index],
        "confidence": round(float(probabilities[class_index]), 4),
        "class_probabilities": class_probabilities,
        "explanation": build_explanation(text, class_index),
        "word_count": word_count,
        "input_warning": input_warning,
        "caution": (
            "This is a machine-learning prediction from a six-class model trained "
            "on short political claims. The confidence value is NOT the probability "
            "that the text is true or false, and this output is not a fact-check."
        ),
    }
