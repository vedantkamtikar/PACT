import random
from datetime import datetime, timedelta
from typing import List
import uuid

from app.models.taxonomy import DeclineType, MandateStatus
from app.models.schemas import MandateRecord
from app.engine.clock import virtual_clock, IST

INDIAN_CUSTOMERS = [
    ("Rahul Verma", "+919820147281", "rahul.verma@example.com"),
    ("Priya Sharma", "+919871239845", "priya.sharma@example.com"),
    ("Amit Patel", "+919930491823", "amit.patel@example.com"),
    ("Sneha Kulkarni", "+919769283419", "sneha.k@example.com"),
    ("Rohan Iyer", "+919845019283", "rohan.iyer@example.com"),
    ("Ananya Sen", "+919830291845", "ananya.sen@example.com"),
    ("Vikram Malhotra", "+919920194857", "vikram.m@example.com"),
    ("Divya Nair", "+919847102938", "divya.nair@example.com"),
    ("Karthik Raman", "+919840192834", "karthik.r@example.com"),
    ("Pooja Mehta", "+919821495820", "pooja.mehta@example.com"),
    ("Siddharth Rao", "+919980192837", "siddharth.rao@example.com"),
    ("Neha Gupta", "+919811029384", "neha.gupta@example.com"),
    ("Arjun Reddy", "+919849019283", "arjun.reddy@example.com"),
    ("Deepika Deshmukh", "+919822019283", "deepika.d@example.com"),
    ("Manish Tiwari", "+919415019283", "manish.tiwari@example.com"),
    ("Swati Agarwal", "+919839019283", "swati.a@example.com"),
    ("Gaurav Kapoor", "+919810019283", "gaurav.k@example.com"),
    ("Meera Nambiar", "+919447019283", "meera.n@example.com"),
    ("Tarun Bhatia", "+919814019283", "tarun.b@example.com"),
    ("Shreya Chatterjee", "+919831019283", "shreya.c@example.com"),
]

MERCHANTS_SUBSCRIPTIONS = [
    ("StreamFlix India", "Ultra 4K Family Plan", 799.0),
    ("QuickFlow CRM", "Pro SaaS Workspace Monthly", 2499.0),
    ("CultFit Gym", "Annual Fitness Membership", 12500.0),
    ("Razorpay Capital", "Term Loan EMI Recurrence", 8450.0),
    ("Times Prime", "VIP Annual Pass", 1199.0),
    ("HealthFirst Care", "Family Medical Floater", 3650.0),
    ("SkillForge LMS", "FullStack Career Track", 4999.0),
    ("CloudSecure Backup", "1TB Enterprise Cloud", 999.0),
    ("Bharat Broadband", "Gigabit Fiber Monthly", 1499.0),
    ("UrbanClean Club", "Bi-Weekly Home Service", 1850.0),
]

BANKS = [
    ("HDFC", "okhdfcbank"),
    ("ICIC", "icici"),
    ("SBIN", "sbi"),
    ("UTIB", "axisbank"),
    ("KKBK", "kotak"),
    ("PUNB", "pnb"),
]

DECLINE_TEMPLATES = {
    DeclineType.INSUFFICIENT_FUNDS: [
        ("ZM", "ZM: INSUFFICIENT FUNDS IN CUSTOMER A/C"),
        ("U19", "U19 - BALANCE CHECK FAILED AT REMITTER CBS"),
        ("51", "51: DECLINED DUE TO LOW AVAILABLE BALANCE"),
        ("NC01", "NC01: ACCOUNT BALANCE BELOW DEBIT THRESHOLD"),
    ],
    DeclineType.TECHNICAL_DECLINE: [
        ("92", "92: ROUTING TIMEOUT ON DESTINATION BANK SWITCH"),
        ("U31", "U31 - NPCI HOST OFFLINE OR TIMED OUT"),
        ("91", "91: ISSUER SWITCH NOT REACHABLE"),
        ("96", "96: SYSTEM MALFUNCTION AT BENEFICIARY BANK"),
    ],
    DeclineType.MANDATE_EXPIRED: [
        ("U30", "U30: MANDATE NOT FOUND OR END DATE EXCEEDED"),
        ("ME01", "ME01: MANDATE VALIDITY EXPIRED IN NPCI MMS"),
        ("EXP99", "EXP99 - RECURRING MANDATE PERIOD LAPSED"),
    ],
    DeclineType.RBI_APPROVAL_REQUIRED: [
        ("U16", "U16-RISK_DECLINE_RETRY_NOT_PERMITTED_RBI_AFA"),
        ("RB99", "RB99: NON-TRANSIENT REGULATORY BLOCK: AFA RE-VALIDATION REQUIRED"),
        ("REG05", "REG05: TRANSACTION REQUIRES MANDATORY RBI COMPLIANCE AUDIT"),
    ],
    DeclineType.PRE_DEBIT_NOTIFICATION_MISSED: [
        ("NO_NOTIF", "PRE-DEBIT NOTIFICATION LOG MISSING OR LESS THAN 24H"),
        ("PDN_FAIL", "PDN_FAIL: 24-HOUR ADVANCE NOTICE NOT DELIVERED TO USER"),
    ],
    DeclineType.EXECUTION_WINDOW_BLOCKED: [
        ("PEAK_BLOCK", "NPCI PEAK EXECUTION BLACKOUT: 10:00 AM TO 1:00 PM RESTRICTION"),
        ("WIN_ERR", "WIN_ERR: DEBIT REJECTED DURING HIGH-LOAD MORNING WINDOW"),
    ],
}

def generate_synthetic_batch(count: int = 60, seed: int = 42) -> List[MandateRecord]:
    """
    Generates a realistic synthetic batch of failed UPI AutoPay / e-mandate debits.
    Weighted realistically:
    - ~50% INSUFFICIENT_FUNDS
    - ~20% TECHNICAL_DECLINE
    - ~15% EXECUTION_WINDOW_BLOCKED
    - ~8% MANDATE_EXPIRED
    - ~5% RBI_APPROVAL_REQUIRED
    - ~2% PRE_DEBIT_NOTIFICATION_MISSED
    """
    random.seed(seed)
    records: List[MandateRecord] = []
    
    # Base timestamp relative to virtual clock
    now = virtual_clock.get_now()
    
    weights = [
        (DeclineType.INSUFFICIENT_FUNDS, 0.48),
        (DeclineType.TECHNICAL_DECLINE, 0.20),
        (DeclineType.EXECUTION_WINDOW_BLOCKED, 0.15),
        (DeclineType.MANDATE_EXPIRED, 0.08),
        (DeclineType.RBI_APPROVAL_REQUIRED, 0.06),
        (DeclineType.PRE_DEBIT_NOTIFICATION_MISSED, 0.03),
    ]
    types, probs = zip(*weights)

    for i in range(count):
        cust_name, cust_phone, cust_email = random.choice(INDIAN_CUSTOMERS)
        merchant, sub_item, base_amt = random.choice(MERCHANTS_SUBSCRIPTIONS)
        bank_code, upi_handle = random.choice(BANKS)
        
        # 12 digit UMN (Unique Mandate Number)
        umn_num = f"{random.randint(100000000000, 999999999999)}"
        umn = f"{bank_code}{umn_num}@{upi_handle}"

        # Jitter amount slightly to simulate taxes or custom tiers (₹99 to ₹14,999)
        amount = round(base_amt + random.choice([0.0, 49.0, 99.0, 18.0]), 2)
        if random.random() < 0.1:
            amount = random.choice([99.0, 199.0, 499.0])  # Micro subscriptions

        # Pick decline type
        decline_type = random.choices(types, weights=probs, k=1)[0]
        raw_code, raw_msg = random.choice(DECLINE_TEMPLATES[decline_type])

        # Randomized initial failure time: past 1 to 48 hours
        # If decline_type is EXECUTION_WINDOW_BLOCKED, explicitly force failure time to 10:30am - 12:30pm
        hours_ago = random.uniform(1.0, 48.0)
        failure_dt = now - timedelta(hours=hours_ago)
        
        if decline_type == DeclineType.EXECUTION_WINDOW_BLOCKED:
            # Force hour to 10, 11, or 12
            failure_dt = failure_dt.replace(hour=random.choice([10, 11, 12]), minute=random.randint(5, 55))

        # Initial attempt count: 0 for most, 1 for some insufficient funds (to test voice escalation immediately!)
        attempt_count = 0
        if decline_type == DeclineType.INSUFFICIENT_FUNDS and random.random() < 0.35:
            attempt_count = 1  # Will trigger voice escalation!
        elif random.random() < 0.05:
            attempt_count = 2

        pre_debit_sent = (decline_type != DeclineType.PRE_DEBIT_NOTIFICATION_MISSED)
        pre_debit_ts = (failure_dt - timedelta(hours=25)).isoformat() if pre_debit_sent else None

        record = MandateRecord(
            id=f"man_{uuid.uuid4().hex[:10]}",
            umn=umn,
            customer_name=cust_name,
            customer_phone=cust_phone,
            customer_email=cust_email,
            merchant_name=merchant,
            subscription_item=sub_item,
            amount=amount,
            raw_decline_code=raw_code,
            raw_decline_message=raw_msg,
            decline_type=decline_type,
            status=MandateStatus.FAILED,
            attempt_count=attempt_count,
            max_attempts=3,
            pre_debit_notification_sent=pre_debit_sent,
            pre_debit_notification_ts=pre_debit_ts,
            original_failure_ts=failure_dt.isoformat(),
            last_attempt_ts=failure_dt.isoformat() if attempt_count > 0 else None,
            notes=f"Synthetic payload generated for {merchant} AutoPay."
        )
        records.append(record)

    return records
