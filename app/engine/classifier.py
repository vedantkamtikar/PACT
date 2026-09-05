import re
import json
import logging
from typing import Dict, Any, Optional
import httpx

from app.config import settings
from app.models.taxonomy import DeclineType

logger = logging.getLogger(__name__)

CLASSIFICATION_PROMPT = """You are an expert Indian UPI AutoPay & RBI E-Mandate Compliance System.
Given a raw banking decline code and error message from an issuer bank or NPCI switch, classify it into exactly one of these 6 categories:

1. INSUFFICIENT_FUNDS: Customer has insufficient balance or credit limit.
2. TECHNICAL_DECLINE: Bank switch timeout, server error, network glitch, or NPCI internal failure.
3. MANDATE_EXPIRED: Mandate end date has lapsed or UMN is no longer valid in NPCI MMS.
4. RBI_APPROVAL_REQUIRED: Regulatory hard-stop, Additional Factor of Authentication (AFA) required, cross-border restriction, or RBI mandate limit breach.
5. PRE_DEBIT_NOTIFICATION_MISSED: 24-hour advance SMS/email pre-debit notice was missing or unconfirmed.
6. EXECUTION_WINDOW_BLOCKED: Scheduled debit rejected due to peak blackout window (10:00 AM - 1:00 PM IST).

Input:
Raw Code: {raw_code}
Raw Message: {raw_message}

Return ONLY a JSON object with this exact structure:
{{
  "decline_type": "<ONE OF THE 6 EXACT CODES>",
  "confidence": <float between 0.0 and 1.0>,
  "root_cause_explanation": "<one sentence explaining the root cause>",
  "is_regulatory_block": <true or false>
}}
"""

class DeclineClassifier:
    def __init__(self):
        self.gemini_api_key = settings.gemini_api_key
        self.groq_api_key = settings.groq_api_key

    def classify(self, raw_code: str, raw_message: str) -> Dict[str, Any]:
        """
        Classifies raw decline code/message.
        Uses Gemini or Groq if configured, else falls back to robust regex/keyword engine.
        """
        if self.gemini_api_key:
            try:
                res = self._classify_gemini(raw_code, raw_message)
                if res:
                    return res
            except Exception as e:
                logger.warning(f"Gemini classification failed: {e}. Falling back.")

        if self.groq_api_key:
            try:
                res = self._classify_groq(raw_code, raw_message)
                if res:
                    return res
            except Exception as e:
                logger.warning(f"Groq classification failed: {e}. Falling back.")

        return self._heuristic_fallback(raw_code, raw_message)

    def _heuristic_fallback(self, raw_code: str, raw_message: str) -> Dict[str, Any]:
        """Deterministic heuristic classifier with domain patterns."""
        combined = f"{raw_code} {raw_message}".upper()

        if any(w in combined for w in ["U16", "RBI", "AFA", "REGULATORY", "REG05", "RB99"]):
            return {
                "decline_type": DeclineType.RBI_APPROVAL_REQUIRED,
                "confidence": 0.98,
                "root_cause_explanation": "Mandatory RBI regulatory condition or AFA re-validation required.",
                "is_regulatory_block": True,
                "model_used": "heuristic-rules-engine"
            }

        if any(w in combined for w in ["U30", "EXPIRED", "END DATE", "ME01", "EXP99", "LAPSED"]):
            return {
                "decline_type": DeclineType.MANDATE_EXPIRED,
                "confidence": 0.96,
                "root_cause_explanation": "Mandate validity period lapsed in NPCI Mandate Management System.",
                "is_regulatory_block": True,
                "model_used": "heuristic-rules-engine"
            }

        if any(w in combined for w in ["NO_NOTIF", "PRE-DEBIT", "PDN_FAIL", "24-HOUR ADVANCE"]):
            return {
                "decline_type": DeclineType.PRE_DEBIT_NOTIFICATION_MISSED,
                "confidence": 0.95,
                "root_cause_explanation": "Mandatory 24h pre-debit notice was not logged or delivered.",
                "is_regulatory_block": True,
                "model_used": "heuristic-rules-engine"
            }

        if any(w in combined for w in ["PEAK_BLOCK", "PEAK", "10:00", "BLACKOUT", "WIN_ERR"]):
            return {
                "decline_type": DeclineType.EXECUTION_WINDOW_BLOCKED,
                "confidence": 0.99,
                "root_cause_explanation": "Debit attempt conflicted with NPCI morning peak blackout (10am-1pm IST).",
                "is_regulatory_block": False,
                "model_used": "heuristic-rules-engine"
            }

        if any(w in combined for w in ["92", "91", "96", "U31", "SWITCH", "TIMEOUT", "OFFLINE", "MALFUNCTION"]):
            return {
                "decline_type": DeclineType.TECHNICAL_DECLINE,
                "confidence": 0.94,
                "root_cause_explanation": "Transient bank switch timeout or NPCI connectivity failure.",
                "is_regulatory_block": False,
                "model_used": "heuristic-rules-engine"
            }

        # Default to insufficient funds
        return {
            "decline_type": DeclineType.INSUFFICIENT_FUNDS,
            "confidence": 0.92,
            "root_cause_explanation": "Customer account balance below required subscription debit amount.",
            "is_regulatory_block": False,
            "model_used": "heuristic-rules-engine"
        }

    def _classify_gemini(self, raw_code: str, raw_message: str) -> Optional[Dict[str, Any]]:
        prompt = CLASSIFICATION_PROMPT.format(raw_code=raw_code, raw_message=raw_message)
        model = settings.gemini_model or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.gemini_api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "response_mime_type": "application/json"}
        }
        with httpx.Client(timeout=6.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text)
                parsed["model_used"] = model
                return parsed
        return None

    def _classify_groq(self, raw_code: str, raw_message: str) -> Optional[Dict[str, Any]]:
        prompt = CLASSIFICATION_PROMPT.format(raw_code=raw_code, raw_message=raw_message)
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.groq_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "You output strictly valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }
        with httpx.Client(timeout=6.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                parsed = json.loads(text)
                parsed["model_used"] = "groq-llama-3.3"
                return parsed
        return None

decline_classifier = DeclineClassifier()
