from datetime import datetime, timedelta
from typing import Dict, Optional, List
from app.models.schemas import PromiseToPay, MandateRecord
from app.models.taxonomy import MandateStatus, RecoveryAction, ComplianceRule
from app.engine.clock import virtual_clock, IST

class PromiseTracker:
    def __init__(self):
        self._promises: Dict[str, PromiseToPay] = {}

    def register_promise(self, promise: PromiseToPay) -> None:
        self._promises[promise.mandate_id] = promise

    def get_promise(self, mandate_id: str) -> Optional[PromiseToPay]:
        return self._promises.get(mandate_id)

    def check_status(self, mandate_id: str, current_time: Optional[datetime] = None) -> tuple[str, str]:
        """
        Evaluates promise status against simulated current time.
        Returns: (status: "AWAITING_DATE" | "DUE_FOR_EXECUTION" | "GRACE_EXPIRED", message)
        """
        promise = self.get_promise(mandate_id)
        if not promise:
            return "NOT_FOUND", "No promise-to-pay registered."

        now = (current_time or virtual_clock.get_now()).astimezone(IST)
        p_date = datetime.fromisoformat(promise.promised_date).astimezone(IST)

        if now < p_date:
            hours_left = int((p_date - now).total_seconds() / 3600)
            return "AWAITING_DATE", f"Customer commitment active: {hours_left} hours until promised date ({p_date.strftime('%d %b %Y')})."
        
        # Within 48 hours of promised date: due for debit attempt
        grace_deadline = p_date + timedelta(hours=48)
        if now <= grace_deadline:
            return "DUE_FOR_EXECUTION", "Promised date reached. Mandate is in prime execution window."

        return "GRACE_EXPIRED", "Grace period (48h post-promise) expired without successful fulfillment."

promise_tracker = PromiseTracker()
