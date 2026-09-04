from enum import Enum

class DeclineType(str, Enum):
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    TECHNICAL_DECLINE = "TECHNICAL_DECLINE"
    MANDATE_EXPIRED = "MANDATE_EXPIRED"
    RBI_APPROVAL_REQUIRED = "RBI_APPROVAL_REQUIRED"
    PRE_DEBIT_NOTIFICATION_MISSED = "PRE_DEBIT_NOTIFICATION_MISSED"
    EXECUTION_WINDOW_BLOCKED = "EXECUTION_WINDOW_BLOCKED"

class MandateStatus(str, Enum):
    FAILED = "FAILED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    RECOVERED = "RECOVERED"
    ESCALATED_VOICE = "ESCALATED_VOICE"
    PROMISE_SECURED = "PROMISE_SECURED"
    HARD_STOP_REGULATORY = "HARD_STOP_REGULATORY"
    HARD_STOP_EXPIRED = "HARD_STOP_EXPIRED"
    STOPPING_RULE_MAX_RETRIES = "STOPPING_RULE_MAX_RETRIES"
    LAPSED = "LAPSED"

class RecoveryAction(str, Enum):
    SCHEDULE_RETRY = "SCHEDULE_RETRY"
    RESCHEDULE_BLACKOUT = "RESCHEDULE_BLACKOUT"
    VOICE_ESCALATION = "VOICE_ESCALATION"
    TRIGGER_REREGISTRATION = "TRIGGER_REREGISTRATION"
    REGULATORY_HARD_STOP = "REGULATORY_HARD_STOP"
    AWAIT_PRE_DEBIT_NOTICE = "AWAIT_PRE_DEBIT_NOTICE"
    TERMINATE_MAX_RETRIES = "TERMINATE_MAX_RETRIES"

class ComplianceRule(str, Enum):
    NPCI_MAX_RETRIES_CAP = "NPCI_CIRCULAR_SEC_4_1_MAX_3_RETRIES"
    NPCI_RETRY_WINDOW_24H = "NPCI_CIRCULAR_SEC_4_2_WINDOW_24H"
    NPCI_RETRY_WINDOW_72H = "NPCI_CIRCULAR_SEC_4_2_WINDOW_72H"
    NPCI_RETRY_WINDOW_168H = "NPCI_CIRCULAR_SEC_4_2_WINDOW_168H"
    NPCI_PEAK_BLACKOUT_WINDOW = "NPCI_PEAK_LOAD_DIRECTIVE_10AM_1PM"
    RBI_PRE_DEBIT_NOTIFICATION = "RBI_DPSS_CIRCULAR_24H_PRE_NOTIFICATION"
    RBI_APPROVAL_MANDATORY_STOP = "RBI_REGULATORY_CONDITION_HARD_STOP"
    NPCI_MANDATE_EXPIRY_STOP = "NPCI_AUTOPAY_LAPSED_MANDATE_STOP"

# Descriptive metadata for auditing & UI presentation
DECLINE_METADATA = {
    DeclineType.INSUFFICIENT_FUNDS: {
        "title": "Insufficient Funds",
        "description": "Customer account lacked sufficient balance at debit execution time.",
        "compliance_notes": "Retryable under staggered NPCI windows. Repeat failure triggers voice negotiation.",
        "is_retryable": True,
        "default_action": RecoveryAction.SCHEDULE_RETRY,
    },
    DeclineType.TECHNICAL_DECLINE: {
        "title": "Technical / Bank Switch Decline",
        "description": "Server-side downtime, bank switch timeout, or NPCI connectivity glitch.",
        "compliance_notes": "Immediate retryable in next valid NPCI window without customer friction.",
        "is_retryable": True,
        "default_action": RecoveryAction.SCHEDULE_RETRY,
    },
    DeclineType.MANDATE_EXPIRED: {
        "title": "Mandate Expired",
        "description": "E-mandate end-date has lapsed or validity period exceeded.",
        "compliance_notes": "Hard stop: NPCI explicitly forbids debiting expired UMNs. Trigger re-registration.",
        "is_retryable": False,
        "default_action": RecoveryAction.TRIGGER_REREGISTRATION,
    },
    DeclineType.RBI_APPROVAL_REQUIRED: {
        "title": "RBI Regulatory Approval Required",
        "description": "Non-transient regulatory block (e.g. cross-border mandate limit, AFA re-validation required).",
        "compliance_notes": "Hard stop: Retrying breaches RBI E-Mandate Framework. Flagged for compliance review.",
        "is_retryable": False,
        "default_action": RecoveryAction.REGULATORY_HARD_STOP,
    },
    DeclineType.PRE_DEBIT_NOTIFICATION_MISSED: {
        "title": "Pre-Debit Notice Not Delivered",
        "description": "Mandatory 24-hour pre-debit SMS/email notification was not confirmed.",
        "compliance_notes": "Block debit attempt. Must dispatch pre-notification and wait 24 hours.",
        "is_retryable": False,
        "default_action": RecoveryAction.AWAIT_PRE_DEBIT_NOTICE,
    },
    DeclineType.EXECUTION_WINDOW_BLOCKED: {
        "title": "Peak Window Conflict",
        "description": "Scheduled debit fell between 10:00 AM and 1:00 PM IST (NPCI peak window).",
        "compliance_notes": "Must defer execution to after 1:00 PM IST (e.g. 1:05 PM IST). Not counted as a failure attempt.",
        "is_retryable": True,
        "default_action": RecoveryAction.RESCHEDULE_BLACKOUT,
    },
}
