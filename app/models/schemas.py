from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import hashlib
import uuid

from .taxonomy import DeclineType, MandateStatus, RecoveryAction, ComplianceRule

class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:10]}")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    mandate_id: str
    from_status: Optional[str] = None
    to_status: str
    action_taken: RecoveryAction
    rule_cited: ComplianceRule
    reason: str
    signature_hash: str = ""

    def generate_hash(self) -> str:
        payload = f"{self.event_id}:{self.timestamp}:{self.mandate_id}:{self.action_taken}:{self.rule_cited}:{self.reason}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

class CallTurn(BaseModel):
    speaker: str  # "Agent" or "Customer"
    text: str
    timestamp: str

class VoiceCallRecord(BaseModel):
    call_id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:8]}")
    mandate_id: str
    customer_name: str
    customer_phone: str = ""
    language: str = "Hinglish (Hindi + English)"
    turns: List[CallTurn] = []
    audio_data_uri: Optional[str] = None
    outcome: str = "PENDING"  # "PROMISE_SECURED", "CUSTOMER_BUSY", "REFUSED"
    promised_date: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class PromiseToPay(BaseModel):
    promise_id: str = Field(default_factory=lambda: f"ptp_{uuid.uuid4().hex[:8]}")
    mandate_id: str
    customer_name: str
    customer_phone: str
    promised_date: str  # ISO date string
    amount: float
    status: str = "PENDING"  # "PENDING", "FULFILLED", "BROKEN"
    call_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class MandateRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"man_{uuid.uuid4().hex[:10]}")
    umn: str  # Unique Mandate Number
    customer_name: str
    customer_phone: str
    customer_email: str
    merchant_name: str = "Razorpay Merchant"
    subscription_item: str = "SaaS Pro Plan"
    amount: float
    raw_decline_code: str
    raw_decline_message: str
    decline_type: DeclineType
    status: MandateStatus = MandateStatus.FAILED
    attempt_count: int = 0
    max_attempts: int = 3
    pre_debit_notification_sent: bool = True
    pre_debit_notification_ts: Optional[str] = None
    original_failure_ts: str
    last_attempt_ts: Optional[str] = None
    next_retry_ts: Optional[str] = None
    voice_escalated: bool = False
    voice_call: Optional[VoiceCallRecord] = None
    promise_to_pay: Optional[PromiseToPay] = None
    recovered_amount: float = 0.0
    audit_trail: List[AuditEvent] = []
    notes: Optional[str] = None

class BatchRunSummary(BaseModel):
    batch_id: str
    timestamp: str
    total_records: int
    total_at_risk_inr: float
    total_recovered_inr: float
    overall_recovery_rate_pct: float
    compliance_violations: int = 0
    stopping_rules_triggered: int = 0
    breakdown_by_type: Dict[str, Dict[str, Any]] = {}
    active_in_queue: int = 0
    hard_stops_count: int = 0
    voice_escalations_count: int = 0

class TimeSimulationState(BaseModel):
    current_simulated_time: str
    is_in_blackout: bool
    blackout_window_desc: str = "NPCI Peak Window (10:00 AM - 1:00 PM IST)"
    hours_advanced_total: float = 0.0
