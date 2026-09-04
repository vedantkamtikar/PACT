import pytest
from datetime import datetime, timezone, timedelta
from app.models.taxonomy import DeclineType, MandateStatus, RecoveryAction, ComplianceRule
from app.models.schemas import MandateRecord
from app.engine.clock import VirtualClock, IST
from app.engine.compliance import ComplianceEngine

def create_sample_mandate(decline_type: DeclineType, attempt_count: int = 0, failure_dt: datetime = None) -> MandateRecord:
    dt_str = (failure_dt or datetime(2026, 9, 1, 9, 0, 0, tzinfo=IST)).isoformat()
    return MandateRecord(
        id="test_mandate_01",
        umn="HDFC000123456789@okhdfcbank",
        customer_name="Rahul Verma",
        customer_phone="+919876543210",
        customer_email="rahul@example.com",
        amount=1499.0,
        raw_decline_code="ZM",
        raw_decline_message="ZM: Insufficient funds in account",
        decline_type=decline_type,
        attempt_count=attempt_count,
        original_failure_ts=dt_str,
        last_attempt_ts=dt_str,
        pre_debit_notification_sent=True
    )

def test_rbi_approval_required_hard_stop():
    engine = ComplianceEngine()
    record = create_sample_mandate(DeclineType.RBI_APPROVAL_REQUIRED)
    decision = engine.evaluate(record)

    assert decision.action == RecoveryAction.REGULATORY_HARD_STOP
    assert decision.to_status == MandateStatus.HARD_STOP_REGULATORY
    assert decision.rule_cited == ComplianceRule.RBI_APPROVAL_MANDATORY_STOP
    assert decision.next_retry_ts is None

def test_mandate_expired_hard_stop():
    engine = ComplianceEngine()
    record = create_sample_mandate(DeclineType.MANDATE_EXPIRED)
    decision = engine.evaluate(record)

    assert decision.action == RecoveryAction.TRIGGER_REREGISTRATION
    assert decision.to_status == MandateStatus.HARD_STOP_EXPIRED
    assert decision.rule_cited == ComplianceRule.NPCI_MANDATE_EXPIRY_STOP
    assert decision.next_retry_ts is None

def test_max_attempts_cap_stopping_rule():
    engine = ComplianceEngine()
    record = create_sample_mandate(DeclineType.INSUFFICIENT_FUNDS, attempt_count=3)
    decision = engine.evaluate(record)

    assert decision.action == RecoveryAction.TERMINATE_MAX_RETRIES
    assert decision.to_status == MandateStatus.STOPPING_RULE_MAX_RETRIES
    assert decision.rule_cited == ComplianceRule.NPCI_MAX_RETRIES_CAP
    assert decision.next_retry_ts is None

def test_npci_24h_retry_window():
    engine = ComplianceEngine()
    # 9:00 AM IST failure + 24h = 9:00 AM IST next day (outside blackout)
    base_time = datetime(2026, 9, 1, 9, 0, 0, tzinfo=IST)
    record = create_sample_mandate(DeclineType.TECHNICAL_DECLINE, attempt_count=0, failure_dt=base_time)
    decision = engine.evaluate(record, current_time=base_time)

    assert decision.action == RecoveryAction.SCHEDULE_RETRY
    assert decision.to_status == MandateStatus.RETRY_SCHEDULED
    assert decision.next_retry_ts is not None
    assert decision.next_retry_ts == base_time + timedelta(hours=24)
    assert decision.blackout_adjusted is False

def test_blackout_window_deferral():
    engine = ComplianceEngine()
    # 11:30 AM IST failure + 24h = 11:30 AM IST next day (INSIDE blackout!)
    base_time = datetime(2026, 9, 1, 11, 30, 0, tzinfo=IST)
    record = create_sample_mandate(DeclineType.TECHNICAL_DECLINE, attempt_count=0, failure_dt=base_time)
    decision = engine.evaluate(record, current_time=base_time)

    assert decision.action == RecoveryAction.RESCHEDULE_BLACKOUT
    assert decision.rule_cited == ComplianceRule.NPCI_PEAK_BLACKOUT_WINDOW
    assert decision.blackout_adjusted is True
    # Should be shifted to 1:05 PM IST on the next day
    expected = datetime(2026, 9, 2, 13, 5, 0, tzinfo=IST)
    assert decision.next_retry_ts == expected

def test_execution_blocked_during_blackout():
    clock = VirtualClock(datetime(2026, 9, 2, 11, 45, 0, tzinfo=IST))
    engine = ComplianceEngine()
    
    # Even if retry was scheduled earlier, attempting execution inside 10am-1pm is strictly blocked
    record = create_sample_mandate(DeclineType.TECHNICAL_DECLINE)
    record.next_retry_ts = datetime(2026, 9, 2, 10, 0, 0, tzinfo=IST).isoformat()
    
    can_exec, reason, rule = engine.can_execute_now(record, current_time=clock.get_now())
    assert can_exec is False
    assert rule == ComplianceRule.NPCI_PEAK_BLACKOUT_WINDOW
    assert "NPCI Peak Load Blackout Window" in reason

def test_voice_escalation_on_repeat_insufficient_funds():
    engine = ComplianceEngine()
    base_time = datetime(2026, 9, 1, 9, 0, 0, tzinfo=IST)
    # 2nd failure (attempt_count = 1)
    record = create_sample_mandate(DeclineType.INSUFFICIENT_FUNDS, attempt_count=1, failure_dt=base_time)
    decision = engine.evaluate(record, current_time=base_time)

    assert decision.action == RecoveryAction.VOICE_ESCALATION
    assert decision.to_status == MandateStatus.ESCALATED_VOICE
    assert decision.voice_escalated is True
