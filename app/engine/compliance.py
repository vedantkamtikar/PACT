from datetime import datetime, timedelta
from typing import Optional, Tuple
from app.models.taxonomy import DeclineType, MandateStatus, RecoveryAction, ComplianceRule
from app.models.schemas import MandateRecord, AuditEvent
from app.engine.clock import virtual_clock, IST

class ComplianceDecision:
    def __init__(
        self,
        action: RecoveryAction,
        to_status: MandateStatus,
        rule_cited: ComplianceRule,
        reason: str,
        next_retry_ts: Optional[datetime] = None,
        blackout_adjusted: bool = False,
        voice_escalated: bool = False
    ):
        self.action = action
        self.to_status = to_status
        self.rule_cited = rule_cited
        self.reason = reason
        self.next_retry_ts = next_retry_ts
        self.blackout_adjusted = blackout_adjusted
        self.voice_escalated = voice_escalated

class ComplianceEngine:
    """
    Deterministic Rules Engine for NPCI / RBI E-Mandate Compliance.
    No LLM hallucinations: pure rule-based evaluation.
    """

    # NPCI minimum cooldown hours by attempt sequence
    COOLDOWN_HOURS = {
        0: 24,   # 1st retry: >= 24h from original failure
        1: 72,   # 2nd retry: >= 72h from 1st retry
        2: 168,  # 3rd retry: >= 168h (7 days) from 2nd retry
    }

    def evaluate(self, record: MandateRecord, current_time: Optional[datetime] = None) -> ComplianceDecision:
        now = (current_time or virtual_clock.get_now()).astimezone(IST)

        # 1. HARD STOP: RBI Regulatory Requirement
        if record.decline_type == DeclineType.RBI_APPROVAL_REQUIRED:
            return ComplianceDecision(
                action=RecoveryAction.REGULATORY_HARD_STOP,
                to_status=MandateStatus.HARD_STOP_REGULATORY,
                rule_cited=ComplianceRule.RBI_APPROVAL_MANDATORY_STOP,
                reason="RBI E-Mandate Framework: Regulatory condition requires manual merchant/customer intervention. Prohibited from automatic retries.",
                next_retry_ts=None
            )

        # 2. HARD STOP: Mandate Expired
        if record.decline_type == DeclineType.MANDATE_EXPIRED:
            return ComplianceDecision(
                action=RecoveryAction.TRIGGER_REREGISTRATION,
                to_status=MandateStatus.HARD_STOP_EXPIRED,
                rule_cited=ComplianceRule.NPCI_MANDATE_EXPIRY_STOP,
                reason="NPCI AutoPay Guidelines: E-Mandate validity has expired. Debiting an expired UMN is non-compliant. Customer re-registration required.",
                next_retry_ts=None
            )

        # 3. STOPPING RULE: Max Retry Attempts Cap (NPCI Max 3)
        if record.attempt_count >= record.max_attempts:
            return ComplianceDecision(
                action=RecoveryAction.TERMINATE_MAX_RETRIES,
                to_status=MandateStatus.STOPPING_RULE_MAX_RETRIES,
                rule_cited=ComplianceRule.NPCI_MAX_RETRIES_CAP,
                reason=f"NPCI Cap Enforcement: Mandate reached maximum allowable {record.max_attempts} retries ({record.attempt_count}/{record.max_attempts}). Debit permanently halted to protect consumer rights.",
                next_retry_ts=None
            )

        # 4. PRE-DEBIT NOTIFICATION CHECK (RBI 24-Hour Notice Rule)
        if not record.pre_debit_notification_sent or record.decline_type == DeclineType.PRE_DEBIT_NOTIFICATION_MISSED:
            # Must simulate sending pre-notification and enforce 24h wait
            notice_time = now
            earliest_retry = notice_time + timedelta(hours=24)
            earliest_retry, blackout_adj = virtual_clock.adjust_for_blackout(earliest_retry)
            reason = "RBI DPSS E-Mandate Circular: Pre-debit notification (SMS/email) mandatory 24h prior to debit. Notification queued; debit scheduled after mandatory 24h cooldown."
            if blackout_adj:
                reason += " Deferral applied: Scheduled outside NPCI 10am-1pm blackout window to 1:05 PM IST."

            return ComplianceDecision(
                action=RecoveryAction.AWAIT_PRE_DEBIT_NOTICE,
                to_status=MandateStatus.RETRY_SCHEDULED,
                rule_cited=ComplianceRule.RBI_PRE_DEBIT_NOTIFICATION,
                reason=reason,
                next_retry_ts=earliest_retry,
                blackout_adjusted=blackout_adj
            )

        # 5. VOICE AGENT ESCALATION CHECK (Insufficient funds repeat failure)
        # If already failed once or twice with insufficient funds, escalate before next blind retry
        if (record.decline_type == DeclineType.INSUFFICIENT_FUNDS 
            and record.attempt_count >= 1 
            and not record.voice_escalated):
            
            # Calculate next retry window based on cooldown
            cooldown = self.COOLDOWN_HOURS.get(record.attempt_count, 72)
            base_ref = self._get_base_timestamp(record, now)
            scheduled_time = base_ref + timedelta(hours=cooldown)
            scheduled_time, blackout_adj = virtual_clock.adjust_for_blackout(scheduled_time)

            return ComplianceDecision(
                action=RecoveryAction.VOICE_ESCALATION,
                to_status=MandateStatus.ESCALATED_VOICE,
                rule_cited=ComplianceRule.NPCI_RETRY_WINDOW_72H,
                reason=f"AI Judgment Trigger: Repeat insufficient funds detected on attempt #{record.attempt_count}. Escalating to Hinglish Voice Agent for Promise-to-Pay negotiation before attempting final retry.",
                next_retry_ts=scheduled_time,
                blackout_adjusted=blackout_adj,
                voice_escalated=True
            )

        # 6. STANDARD NPCI COMPLIANT RETRY SCHEDULING
        cooldown_hours = self.COOLDOWN_HOURS.get(record.attempt_count, 24)
        rule_cited = (
            ComplianceRule.NPCI_RETRY_WINDOW_24H if record.attempt_count == 0
            else ComplianceRule.NPCI_RETRY_WINDOW_72H if record.attempt_count == 1
            else ComplianceRule.NPCI_RETRY_WINDOW_168H
        )

        base_ref = self._get_base_timestamp(record, now)
        scheduled_time = base_ref + timedelta(hours=cooldown_hours)
        scheduled_time, blackout_adj = virtual_clock.adjust_for_blackout(scheduled_time)

        reason = f"NPCI Rule Adherence: Cooldown of {cooldown_hours}h enforced for attempt #{record.attempt_count + 1}."
        if blackout_adj:
            reason += " Window conflict detected: Shifted to 1:05 PM IST to comply with 10am-1pm blackout directive."

        return ComplianceDecision(
            action=RecoveryAction.RESCHEDULE_BLACKOUT if blackout_adj else RecoveryAction.SCHEDULE_RETRY,
            to_status=MandateStatus.RETRY_SCHEDULED,
            rule_cited=ComplianceRule.NPCI_PEAK_BLACKOUT_WINDOW if blackout_adj else rule_cited,
            reason=reason,
            next_retry_ts=scheduled_time,
            blackout_adjusted=blackout_adj
        )

    def can_execute_now(self, record: MandateRecord, current_time: Optional[datetime] = None) -> Tuple[bool, str, Optional[ComplianceRule]]:
        """
        Validates if the scheduled retry can safely be executed right now.
        Guarantees 0 compliance violations.
        """
        now = (current_time or virtual_clock.get_now()).astimezone(IST)

        # Blackout window check: NEVER execute during 10am - 1pm
        if virtual_clock.is_in_blackout(now):
            return (
                False,
                "BLOCKED: Current time falls in NPCI Peak Load Blackout Window (10:00 AM - 1:00 PM IST). Debit blocked to maintain 0-violation compliance.",
                ComplianceRule.NPCI_PEAK_BLACKOUT_WINDOW
            )

        if not record.next_retry_ts:
            return False, "No retry scheduled for this mandate.", None

        # Parse next_retry_ts
        try:
            next_ts = datetime.fromisoformat(record.next_retry_ts).astimezone(IST)
        except Exception:
            return False, "Invalid next_retry_ts format.", None

        if now < next_ts:
            remaining_mins = int((next_ts - now).total_seconds() / 60)
            return (
                False,
                f"NPCI Window Active: {remaining_mins} minutes remaining in mandatory cooldown period.",
                None
            )

        return True, "Compliant: Window is active and outside peak blackout.", None

    def apply_decision(self, record: MandateRecord, decision: ComplianceDecision, current_time: Optional[datetime] = None) -> AuditEvent:
        """
        Applies compliance decision to the mandate record and creates a signed AuditEvent.
        """
        now = (current_time or virtual_clock.get_now()).astimezone(IST)
        from_status = record.status.value if record.status else "NEW"
        record.status = decision.to_status

        if decision.next_retry_ts:
            record.next_retry_ts = decision.next_retry_ts.isoformat()
        else:
            record.next_retry_ts = None

        if decision.voice_escalated:
            record.voice_escalated = True

        event = AuditEvent(
            mandate_id=record.id,
            from_status=from_status,
            to_status=decision.to_status.value,
            action_taken=decision.action,
            rule_cited=decision.rule_cited,
            reason=decision.reason,
            timestamp=now.isoformat()
        )
        event.signature_hash = event.generate_hash()
        record.audit_trail.append(event)
        return event

    def _get_base_timestamp(self, record: MandateRecord, fallback: datetime) -> datetime:
        ref_str = record.last_attempt_ts or record.original_failure_ts
        if ref_str:
            try:
                return datetime.fromisoformat(ref_str).astimezone(IST)
            except Exception:
                pass
        return fallback

compliance_engine = ComplianceEngine()
