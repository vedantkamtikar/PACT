import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.repository import repository

client = TestClient(app)

def test_api_status():
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "PACT" in data["app_name"]
    assert "simulated_time_ist" in data
    assert "is_in_blackout" in data

def test_batch_generate_and_analytics():
    resp = client.post("/api/batch/generate", json={"count": 25, "seed": 99})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 25

    analytics_resp = client.get("/api/analytics")
    assert analytics_resp.status_code == 200
    analytics = analytics_resp.json()
    assert analytics["total_records"] >= 25
    assert analytics["compliance_violations"] == 0

def test_clock_jump_blackout_and_execute_interception():
    # Jump into blackout (11:30 AM IST)
    resp = client.post("/api/clock/jump-blackout")
    assert resp.status_code == 200
    assert resp.json()["is_in_blackout"] is True

    # Try to execute due debits inside blackout
    exec_resp = client.post("/api/execute-due")
    assert exec_resp.status_code == 200
    exec_data = exec_resp.json()
    assert exec_data["is_in_blackout"] is True
    # If any were due, they should be deferred and executed_count must be 0!
    assert exec_data["executed_count"] == 0

def test_voice_call_trigger_and_ptp():
    mandates = repository.get_all_mandates()
    # Pick first mandate
    m_id = mandates[0].id
    resp = client.post(f"/api/voice/call/{m_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "call_record" in data
    assert "promise_to_pay" in data
    assert data["call_record"]["outcome"] == "PROMISE_SECURED"
    assert len(data["call_record"]["turns"]) >= 4

def test_audit_trail():
    resp = client.get("/api/audit-trail?limit=50")
    assert resp.status_code == 200
    events = resp.json()
    assert isinstance(events, list)
    assert len(events) > 0
    assert "signature_hash" in events[0]
