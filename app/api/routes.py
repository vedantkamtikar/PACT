import random
from datetime import datetime
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.models.taxonomy import DeclineType, MandateStatus, RecoveryAction, ComplianceRule
from app.models.schemas import MandateRecord, AuditEvent, PromiseToPay, VoiceCallRecord
from app.engine.clock import virtual_clock, IST
from app.engine.compliance import compliance_engine
from app.engine.synthetic import generate_synthetic_batch
from app.engine.classifier import decline_classifier
from app.voice.agent import voice_agent
from app.voice.promise import promise_tracker
from app.db.repository import repository

router = APIRouter(prefix="/api")

class AdvanceClockRequest(BaseModel):
    hours: float

class GenerateBatchRequest(BaseModel):
    count: int = 60
    seed: Optional[int] = 42

@router.get("/status")
def get_system_status():
    now = virtual_clock.get_now()
    is_blackout = virtual_clock.is_in_blackout(now)
    return {
        "status": "online",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "simulated_time_ist": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "simulated_time_iso": now.isoformat(),
        "is_in_blackout": is_blackout,
        "blackout_rule": "10:00 AM - 1:00 PM IST (NPCI Peak Load Directives)",
        "has_gemini_key": bool(settings.gemini_api_key),
        "has_groq_key": bool(settings.groq_api_key),
        "has_sarvam_key": bool(settings.sarvam_api_key),
        "hours_advanced_total": round(virtual_clock.total_hours_advanced(), 1),
    }

@router.post("/batch/generate")
def generate_batch(req: GenerateBatchRequest):
    records = generate_synthetic_batch(count=req.count, seed=req.seed or 42)
    repository.save_mandates(records)
    return {
        "message": f"Successfully generated and stored {len(records)} synthetic mandate failure records.",
        "count": len(records),
        "analytics": repository.get_analytics()
    }

@router.post("/batch/process")
def process_batch():
    """
    Orchestrates ingestion:
    1. Classifies raw bank decline strings using LLM/Heuristic Classifier.
    2. Runs deterministic compliance rules to evaluate stopping rules, NPCI windows, and blackout checks.
    3. Logs cryptographic audit events for every decision.
    """
    mandates = repository.get_all_mandates()
    if not mandates:
        # Generate default batch if empty
        records = generate_synthetic_batch(count=60)
        repository.save_mandates(records)
        mandates = records

    processed_count = 0
    now = virtual_clock.get_now()

    for record in mandates:
        # 1. AI Classification step
        classification = decline_classifier.classify(record.raw_decline_code, record.raw_decline_message)
        classified_type = classification.get("decline_type", record.decline_type)
        record.decline_type = classified_type

        # 2. Deterministic Compliance Evaluation
        decision = compliance_engine.evaluate(record, current_time=now)
        
        # 3. Apply Decision & Record Signed Audit Event
        event = compliance_engine.apply_decision(record, decision, current_time=now)
        repository.save_audit_event(event)

        repository.save_mandate(record)
        processed_count += 1

    return {
        "message": f"Processed {processed_count} mandates through compliance rules engine.",
        "analytics": repository.get_analytics()
    }

@router.get("/mandates")
def list_mandates(
    status: Optional[str] = Query(None),
    decline_type: Optional[str] = Query(None)
):
    mandates = repository.get_all_mandates(status=status, decline_type=decline_type)
    return {
        "total": len(mandates),
        "mandates": [m.model_dump() for m in mandates]
    }

@router.get("/mandates/{mandate_id}")
def get_mandate_details(mandate_id: str):
    record = repository.get_mandate(mandate_id)
    if not record:
        raise HTTPException(status_code=404, detail="Mandate not found")

    voice_call = repository.get_voice_call(mandate_id)
    audit_events = repository.get_audit_trail(mandate_id=mandate_id)
    promise = promise_tracker.get_promise(mandate_id)

    return {
        "mandate": record.model_dump(),
        "voice_call": voice_call.model_dump() if voice_call else None,
        "promise_to_pay": promise.model_dump() if promise else None,
        "audit_trail": audit_events
    }

@router.post("/clock/advance")
def advance_clock(req: AdvanceClockRequest):
    new_time = virtual_clock.advance_hours(req.hours)
    now = virtual_clock.get_now()
    return {
        "message": f"Clock advanced by {req.hours} hours.",
        "current_time_ist": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "is_in_blackout": virtual_clock.is_in_blackout(now),
        "total_hours_advanced": round(virtual_clock.total_hours_advanced(), 1)
    }

@router.post("/clock/jump-blackout")
def jump_to_blackout():
    new_time = virtual_clock.jump_to_blackout()
    return {
        "message": "Jumped virtual clock directly into NPCI Peak Blackout Window (11:30 AM IST).",
        "current_time_ist": new_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "is_in_blackout": True
    }

@router.post("/clock/jump-compliant")
def jump_after_blackout():
    new_time = virtual_clock.jump_after_blackout()
    return {
        "message": "Jumped virtual clock to compliant window (1:15 PM IST).",
        "current_time_ist": new_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "is_in_blackout": False
    }

@router.post("/clock/reset")
def reset_clock():
    virtual_clock.set_time(datetime.now(IST))
    return {
        "message": "Reset virtual clock to real time.",
        "current_time_ist": virtual_clock.get_now().strftime("%Y-%m-%d %H:%M:%S %Z")
    }

@router.post("/execute-due")
def execute_due_retries():
    """
    Finds all mandates whose next_retry_ts is <= current virtual time,
    validates compliance (guaranteeing 0 blackout executions), and simulates bank outcomes.
    """
    now = virtual_clock.get_now()
    is_blackout = virtual_clock.is_in_blackout(now)

    mandates = repository.get_all_mandates()
    due_mandates: List[MandateRecord] = []

    for m in mandates:
        if m.status in [MandateStatus.RETRY_SCHEDULED, MandateStatus.PROMISE_SECURED, MandateStatus.ESCALATED_VOICE]:
            if m.next_retry_ts:
                try:
                    retry_dt = datetime.fromisoformat(m.next_retry_ts).astimezone(IST)
                    if now >= retry_dt:
                        due_mandates.append(m)
                except Exception:
                    pass

    if not due_mandates:
        return {
            "message": "No mandates currently due for execution at current simulated time.",
            "due_count": 0,
            "executed_count": 0,
            "is_in_blackout": is_blackout,
            "current_time_ist": now.strftime("%Y-%m-%d %H:%M:%S %Z")
        }

    # CRITICAL COMPLIANCE CHECK: If currently in blackout, DO NOT EXECUTE ANY!
    if is_blackout:
        deferred_count = 0
        for m in due_mandates:
            # Shift to 1:05 PM IST
            adjusted, _ = virtual_clock.adjust_for_blackout(now)
            m.next_retry_ts = adjusted.isoformat()
            
            event = AuditEvent(
                mandate_id=m.id,
                from_status=m.status.value,
                to_status=m.status.value,
                action_taken=RecoveryAction.RESCHEDULE_BLACKOUT,
                rule_cited=ComplianceRule.NPCI_PEAK_BLACKOUT_WINDOW,
                reason="BLOCKED: Execution attempt intercepted inside 10:00 AM - 1:00 PM IST peak blackout window. Deferred to 1:05 PM IST.",
                timestamp=now.isoformat()
            )
            event.signature_hash = event.generate_hash()
            repository.save_audit_event(event)
            repository.save_mandate(m)
            deferred_count += 1

        return {
            "message": f"NPCI Blackout Protected: {deferred_count} debits due now were blocked and safely rescheduled to 1:05 PM IST. Compliance violations: 0.",
            "due_count": len(due_mandates),
            "executed_count": 0,
            "deferred_count": deferred_count,
            "is_in_blackout": True,
            "current_time_ist": now.strftime("%Y-%m-%d %H:%M:%S %Z")
        }

    # In compliant window: execute retries
    recovered_count = 0
    failed_again_count = 0

    for m in due_mandates:
        # Determine success probability based on context
        if m.decline_type == DeclineType.TECHNICAL_DECLINE:
            prob = 0.90  # Bank switch usually recovers quickly
        elif m.status == MandateStatus.PROMISE_SECURED:
            prob = 0.85  # User promised and agreed
        elif m.decline_type == DeclineType.INSUFFICIENT_FUNDS:
            prob = 0.55  # Without explicit promise, 50/50
        else:
            prob = 0.70

        success = (random.random() < prob)

        if success:
            from_status = m.status.value
            m.status = MandateStatus.RECOVERED
            m.recovered_amount = m.amount
            m.last_attempt_ts = now.isoformat()
            m.next_retry_ts = None
            
            event = AuditEvent(
                mandate_id=m.id,
                from_status=from_status,
                to_status=MandateStatus.RECOVERED.value,
                action_taken=RecoveryAction.SCHEDULE_RETRY,
                rule_cited=ComplianceRule.NPCI_RETRY_WINDOW_24H,
                reason=f"REVENUE RECOVERED: AutoPay debit of ₹{m.amount:,.2f} successfully settled through issuer switch.",
                timestamp=now.isoformat()
            )
            event.signature_hash = event.generate_hash()
            repository.save_audit_event(event)
            recovered_count += 1
        else:
            m.attempt_count += 1
            m.last_attempt_ts = now.isoformat()
            decision = compliance_engine.evaluate(m, current_time=now)
            event = compliance_engine.apply_decision(m, decision, current_time=now)
            repository.save_audit_event(event)
            failed_again_count += 1

        repository.save_mandate(m)

    return {
        "message": f"Executed {len(due_mandates)} due retries. {recovered_count} recovered, {failed_again_count} rescheduled or stopped.",
        "due_count": len(due_mandates),
        "recovered_count": recovered_count,
        "failed_again_count": failed_again_count,
        "analytics": repository.get_analytics()
    }

@router.post("/voice/call/{mandate_id}")
def trigger_voice_call(mandate_id: str):
    record = repository.get_mandate(mandate_id)
    if not record:
        raise HTTPException(status_code=404, detail="Mandate not found")

    call_record, promise = voice_agent.conduct_call(record)
    repository.save_voice_call(call_record)
    repository.save_promise(promise)
    promise_tracker.register_promise(promise)

    # Transition mandate to PROMISE_SECURED and align next retry with promise date
    now = virtual_clock.get_now()
    from_status = record.status.value
    record.status = MandateStatus.PROMISE_SECURED
    record.voice_call = call_record
    record.promise_to_pay = promise
    record.next_retry_ts = promise.promised_date

    event = AuditEvent(
        mandate_id=record.id,
        from_status=from_status,
        to_status=MandateStatus.PROMISE_SECURED.value,
        action_taken=RecoveryAction.VOICE_ESCALATION,
        rule_cited=ComplianceRule.NPCI_RETRY_WINDOW_72H,
        reason=f"Hinglish Voice Agent successfully negotiated Promise-to-Pay for {promise.promised_date}. Auto-debit scheduled for promised window.",
        timestamp=now.isoformat()
    )
    event.signature_hash = event.generate_hash()
    repository.save_audit_event(event)
    repository.save_mandate(record)

    return {
        "message": "Voice call completed and Promise-to-Pay secured.",
        "call_record": call_record.model_dump(),
        "promise_to_pay": promise.model_dump(),
        "mandate": record.model_dump()
    }

@router.get("/analytics")
def get_analytics():
    return repository.get_analytics()

@router.get("/audit-trail")
def get_audit_trail(limit: int = Query(100)):
    return repository.get_audit_trail(limit=limit)

@router.post("/reset")
def reset_system():
    repository.clear_all()
    records = generate_synthetic_batch(count=60, seed=random.randint(1, 1000))
    repository.save_mandates(records)
    # Process initial rules
    now = virtual_clock.get_now()
    for record in records:
        classification = decline_classifier.classify(record.raw_decline_code, record.raw_decline_message)
        record.decline_type = classification.get("decline_type", record.decline_type)
        decision = compliance_engine.evaluate(record, current_time=now)
        event = compliance_engine.apply_decision(record, decision, current_time=now)
        repository.save_audit_event(event)
        repository.save_mandate(record)

    return {
        "message": "System reset with fresh 60-record synthetic batch and processed rules.",
        "analytics": repository.get_analytics()
    }
