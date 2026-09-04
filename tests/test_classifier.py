import pytest
from app.models.taxonomy import DeclineType
from app.engine.classifier import decline_classifier

def test_classifier_insufficient_funds():
    res = decline_classifier.classify("ZM", "ZM: INSUFFICIENT FUNDS IN CUSTOMER A/C")
    assert res["decline_type"] == DeclineType.INSUFFICIENT_FUNDS
    assert res["confidence"] > 0.8
    assert res["is_regulatory_block"] is False

def test_classifier_technical_decline():
    res = decline_classifier.classify("92", "ROUTING TIMEOUT ON DESTINATION BANK SWITCH")
    assert res["decline_type"] == DeclineType.TECHNICAL_DECLINE

def test_classifier_rbi_regulatory_stop():
    res = decline_classifier.classify("U16", "U16-RISK_DECLINE_RETRY_NOT_PERMITTED_RBI_AFA")
    assert res["decline_type"] == DeclineType.RBI_APPROVAL_REQUIRED
    assert res["is_regulatory_block"] is True

def test_classifier_mandate_expired():
    res = decline_classifier.classify("U30", "U30: MANDATE NOT FOUND OR END DATE EXCEEDED")
    assert res["decline_type"] == DeclineType.MANDATE_EXPIRED
    assert res["is_regulatory_block"] is True

def test_classifier_blackout():
    res = decline_classifier.classify("PEAK_BLOCK", "NPCI PEAK EXECUTION BLACKOUT: 10:00 AM TO 1:00 PM")
    assert res["decline_type"] == DeclineType.EXECUTION_WINDOW_BLOCKED
