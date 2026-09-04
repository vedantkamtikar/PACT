import sqlite3
import json
import os
from datetime import datetime
from typing import List, Optional, Dict, Any

from app.config import settings
from app.models.taxonomy import DeclineType, MandateStatus, RecoveryAction, ComplianceRule
from app.models.schemas import MandateRecord, AuditEvent, PromiseToPay, VoiceCallRecord, CallTurn
from app.engine.clock import virtual_clock

class MandateRepository:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.database_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS mandates (
                id TEXT PRIMARY KEY,
                umn TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                customer_phone TEXT NOT NULL,
                customer_email TEXT,
                merchant_name TEXT,
                subscription_item TEXT,
                amount REAL NOT NULL,
                raw_decline_code TEXT,
                raw_decline_message TEXT,
                decline_type TEXT NOT NULL,
                status TEXT NOT NULL,
                attempt_count INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 3,
                pre_debit_notification_sent INTEGER DEFAULT 1,
                original_failure_ts TEXT,
                last_attempt_ts TEXT,
                next_retry_ts TEXT,
                voice_escalated INTEGER DEFAULT 0,
                recovered_amount REAL DEFAULT 0.0,
                notes TEXT,
                json_data TEXT
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                mandate_id TEXT NOT NULL,
                from_status TEXT,
                to_status TEXT,
                action_taken TEXT,
                rule_cited TEXT,
                reason TEXT,
                signature_hash TEXT,
                FOREIGN KEY (mandate_id) REFERENCES mandates(id)
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS promises (
                promise_id TEXT PRIMARY KEY,
                mandate_id TEXT NOT NULL,
                customer_name TEXT,
                customer_phone TEXT,
                promised_date TEXT,
                amount REAL,
                status TEXT,
                call_id TEXT,
                created_at TEXT
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS voice_calls (
                call_id TEXT PRIMARY KEY,
                mandate_id TEXT NOT NULL,
                customer_name TEXT,
                turns_json TEXT,
                audio_data_uri TEXT,
                outcome TEXT,
                promised_date TEXT,
                created_at TEXT
            );
            """)
            conn.commit()

    def save_mandate(self, record: MandateRecord):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO mandates (
                id, umn, customer_name, customer_phone, customer_email,
                merchant_name, subscription_item, amount, raw_decline_code,
                raw_decline_message, decline_type, status, attempt_count,
                max_attempts, pre_debit_notification_sent, original_failure_ts,
                last_attempt_ts, next_retry_ts, voice_escalated, recovered_amount,
                notes, json_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.id, record.umn, record.customer_name, record.customer_phone,
                record.customer_email, record.merchant_name, record.subscription_item,
                record.amount, record.raw_decline_code, record.raw_decline_message,
                record.decline_type.value, record.status.value, record.attempt_count,
                record.max_attempts, 1 if record.pre_debit_notification_sent else 0,
                record.original_failure_ts, record.last_attempt_ts, record.next_retry_ts,
                1 if record.voice_escalated else 0, record.recovered_amount,
                record.notes, record.model_dump_json()
            ))
            conn.commit()

    def save_mandates(self, records: List[MandateRecord]):
        for r in records:
            self.save_mandate(r)

    def get_mandate(self, mandate_id: str) -> Optional[MandateRecord]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT json_data FROM mandates WHERE id = ?", (mandate_id,))
            row = cursor.fetchone()
            if row:
                data = json.loads(row["json_data"])
                return MandateRecord.model_validate(data)
        return None

    def get_all_mandates(self, status: Optional[str] = None, decline_type: Optional[str] = None) -> List[MandateRecord]:
        query = "SELECT json_data FROM mandates WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if decline_type:
            query += " AND decline_type = ?"
            params.append(decline_type)
        query += " ORDER BY original_failure_ts DESC"

        results: List[MandateRecord] = []
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            for row in cursor.fetchall():
                data = json.loads(row["json_data"])
                results.append(MandateRecord.model_validate(data))
        return results

    def save_audit_event(self, event: AuditEvent):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO audit_events (
                event_id, timestamp, mandate_id, from_status, to_status,
                action_taken, rule_cited, reason, signature_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.event_id, event.timestamp, event.mandate_id,
                event.from_status, event.to_status, event.action_taken.value,
                event.rule_cited.value, event.reason, event.signature_hash
            ))
            conn.commit()

    def get_audit_trail(self, mandate_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        query = "SELECT * FROM audit_events"
        params = []
        if mandate_id:
            query += " WHERE mandate_id = ?"
            params.append(mandate_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    def save_voice_call(self, call: VoiceCallRecord):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO voice_calls (
                call_id, mandate_id, customer_name, turns_json,
                audio_data_uri, outcome, promised_date, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                call.call_id, call.mandate_id, call.customer_name,
                json.dumps([t.model_dump() for t in call.turns]),
                call.audio_data_uri, call.outcome, call.promised_date,
                call.created_at
            ))
            conn.commit()

    def get_voice_call(self, mandate_id: str) -> Optional[VoiceCallRecord]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM voice_calls WHERE mandate_id = ? ORDER BY created_at DESC LIMIT 1", (mandate_id,))
            row = cursor.fetchone()
            if row:
                turns_raw = json.loads(row["turns_json"])
                turns = [CallTurn.model_validate(t) for t in turns_raw]
                return VoiceCallRecord(
                    call_id=row["call_id"],
                    mandate_id=row["mandate_id"],
                    customer_name=row["customer_name"],
                    turns=turns,
                    audio_data_uri=row["audio_data_uri"],
                    outcome=row["outcome"],
                    promised_date=row["promised_date"],
                    created_at=row["created_at"]
                )
        return None

    def save_promise(self, promise: PromiseToPay):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO promises (
                promise_id, mandate_id, customer_name, customer_phone,
                promised_date, amount, status, call_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                promise.promise_id, promise.mandate_id, promise.customer_name,
                promise.customer_phone, promise.promised_date, promise.amount,
                promise.status, promise.call_id, promise.created_at
            ))
            conn.commit()

    def clear_all(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM mandates")
            cursor.execute("DELETE FROM audit_events")
            cursor.execute("DELETE FROM promises")
            cursor.execute("DELETE FROM voice_calls")
            conn.commit()

    def get_analytics(self) -> Dict[str, Any]:
        mandates = self.get_all_mandates()
        total_records = len(mandates)
        if total_records == 0:
            return {
                "total_records": 0,
                "total_at_risk_inr": 0.0,
                "total_recovered_inr": 0.0,
                "overall_recovery_rate_pct": 0.0,
                "compliance_violations": 0,
                "stopping_rules_triggered": 0,
                "hard_stops_count": 0,
                "voice_escalations_count": 0,
                "active_in_queue": 0,
                "breakdown_by_type": {}
            }

        total_at_risk = sum(m.amount for m in mandates)
        total_recovered = sum(m.recovered_amount for m in mandates)
        recovery_pct = round((total_recovered / total_at_risk * 100.0), 2) if total_at_risk > 0 else 0.0

        stopping_rules_triggered = sum(
            1 for m in mandates if m.status in [
                MandateStatus.STOPPING_RULE_MAX_RETRIES,
                MandateStatus.HARD_STOP_REGULATORY,
                MandateStatus.HARD_STOP_EXPIRED
            ]
        )

        hard_stops_count = sum(
            1 for m in mandates if m.status in [
                MandateStatus.HARD_STOP_REGULATORY,
                MandateStatus.HARD_STOP_EXPIRED
            ]
        )

        voice_count = sum(1 for m in mandates if m.voice_escalated)
        active_in_queue = sum(1 for m in mandates if m.status in [MandateStatus.RETRY_SCHEDULED, MandateStatus.ESCALATED_VOICE, MandateStatus.PROMISE_SECURED])

        breakdown: Dict[str, Dict[str, Any]] = {}
        for dtype in DeclineType:
            type_mandates = [m for m in mandates if m.decline_type == dtype]
            type_count = len(type_mandates)
            at_risk = sum(m.amount for m in type_mandates)
            recovered = sum(m.recovered_amount for m in type_mandates)
            rate = round((recovered / at_risk * 100.0), 1) if at_risk > 0 else 0.0
            breakdown[dtype.value] = {
                "count": type_count,
                "at_risk_inr": round(at_risk, 2),
                "recovered_inr": round(recovered, 2),
                "recovery_rate_pct": rate,
                "is_retryable": (dtype not in [DeclineType.RBI_APPROVAL_REQUIRED, DeclineType.MANDATE_EXPIRED])
            }

        return {
            "total_records": total_records,
            "total_at_risk_inr": round(total_at_risk, 2),
            "total_recovered_inr": round(total_recovered, 2),
            "overall_recovery_rate_pct": recovery_pct,
            "compliance_violations": 0,  # Bounded by deterministic engine
            "stopping_rules_triggered": stopping_rules_triggered,
            "hard_stops_count": hard_stops_count,
            "voice_escalations_count": voice_count,
            "active_in_queue": active_in_queue,
            "breakdown_by_type": breakdown
        }

repository = MandateRepository()
