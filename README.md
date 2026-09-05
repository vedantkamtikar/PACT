# PACT (Proactive AutoPay Compliance & Tracking)
### A Compliant UPI AutoPay / E-Mandate Recovery Orchestrator
**Razorpay AI Buildathon 2026 — Track 03: AI Revenue Recovery**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Python 3.13](https://img.shields.io/badge/Python-3.13+-3776AB.svg?style=flat&logo=python)](https://python.org)
[![Compliance](https://img.shields.io/badge/NPCI%20%26%20RBI-100%25%20Compliant-10B981.svg?style=flat)](#)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## Executive Summary

UPI AutoPay processes approximately **1 billion recurring debits monthly**, yet experiences failure rates between **8% and 15%** (5–7x higher than card mandates). Naive recovery systems rely on aggressive "retry and email" loops, which:
1. Violate **NPCI guidelines** (capping retries at 3 attempts and strictly prohibiting execution during the 10:00 AM – 1:00 PM IST morning peak blackout).
2. Breach the **RBI E-Mandate Framework** by ignoring mandatory 24-hour pre-debit notifications and retrying regulatory hard-stop declines.

**PACT** solves this through **AI Judgment**:
- **Probabilistic AI (LLMs)** is used exclusively where unstructured data exists: normalizing noisy, free-text bank decline messages into a standardized taxonomy, and conducting natural, guardrailed Hinglish voice dialogue.
- **Deterministic Compliance Engine (Pure Code, No LLMs)** enforces regulatory rules: NPCI cooldown windows (24h $\rightarrow$ 72h $\rightarrow$ 168h), morning peak blackout protection (10am–1pm IST), 24h pre-debit notices, and hard stops for non-transient regulatory blocks (`RBI_APPROVAL_REQUIRED`, `MANDATE_EXPIRED`).

---

## System Architecture

```
                         ┌─────────────────────────┐
                         │   Synthetic Batch Feed   │
                         │ (50-100 failed debits)  │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                       ┌───────────────────────────┐
                       │   1. Decline Classifier   │  ← LLM (Gemini / Groq / Fallback)
                       │  raw decline code → type  │
                       └────────────┬───────────────┘
                                      │
                                      ▼
                       ┌───────────────────────────┐
                       │ 2. Compliance & Rules     │  ← Deterministic Engine
                       │    (NPCI & RBI Bounds)    │     (Pure rules, 0 Hallucinations)
                       └────────────┬───────────────┘
                          │         │          │
              ┌───────────┘         │          └───────────┐
              ▼                     ▼                      ▼
   ┌───────────────────┐  ┌──────────────────┐  ┌────────────────────┐
   │ Auto-Retry Queue  │  │ Regulatory Stop  │  │ Escalate to Voice  │
   │ (NPCI 24/72/168h  │  │ (RBI / Expired   │  │ (Repeat Low        │
   │ + Blackout Shift) │  │  Hard-Stop)      │  │  Balance Debits)   │
   └─────────┬─────────┘  └────────┬─────────┘  └──────────┬─────────┘
             │                     │                       │
             ▼                     ▼                       ▼
      ┌────────────────────────────────────────────────────────────┐
      │          3. Hinglish Voice Agent (Sarvam AI / TTS)         │
      │  Negotiates Promise-to-Pay, guardrailed against discounts  │
      └────────────────────────────┬───────────────────────────────┘
                                   ▼
                      ┌───────────────────────────┐
                      │ 4. Promise-to-Pay Tracker │
                      │  Grace period & retry sync│
                      └────────────┬──────────────┘
                                   ▼
                      ┌───────────────────────────┐
                      │ 5. Audit Log & Dashboard  │
                      │  ₹ recovered, 0-violation │
                      │  proof, SHA-256 signatures│
                      └───────────────────────────┘
```

---

## Decline Taxonomy & Recovery Actions

| Decline Category | Meaning | Recovery Action | Compliance Rule Cited |
|---|---|---|---|
| `INSUFFICIENT_FUNDS` | Low customer balance | Staggered NPCI retry windows; escalates to Hinglish voice agent after repeat failure | `NPCI_CIRCULAR_SEC_4_2_WINDOW_24H` |
| `TECHNICAL_DECLINE` | Bank switch/NPCI downtime | Immediate retry at next compliant window | `NPCI_CIRCULAR_SEC_4_2_WINDOW_24H` |
| `EXECUTION_WINDOW_BLOCKED` | Debits scheduled 10am–1pm IST | Defer execution to 1:05 PM IST | `NPCI_PEAK_LOAD_DIRECTIVE_10AM_1PM` |
| `MANDATE_EXPIRED` | Mandate end date elapsed | **Hard Stop** — triggers re-registration flow | `NPCI_AUTOPAY_LAPSED_MANDATE_STOP` |
| `RBI_APPROVAL_REQUIRED` | Regulatory AFA / compliance condition | **Hard Stop** — never retried, flagged for manual review | `RBI_REGULATORY_CONDITION_HARD_STOP` |
| `PRE_DEBIT_NOTIFICATION_MISSED` | 24h SMS/email notice missing | Block debit attempt until notice is dispatched and 24h elapsed | `RBI_DPSS_CIRCULAR_24H_PRE_NOTIFICATION` |

---

## Key Features

1. **Deterministic Compliance Engine**:
   - Strictly enforces cooldown windows: 1st retry $\ge 24\text{h}$, 2nd retry $\ge 72\text{h}$, 3rd retry $\ge 168\text{h}$.
   - Intercepts executions inside the 10:00 AM – 1:00 PM IST blackout window and defers them to 1:05 PM IST.
   - Max 3-retry attempt cap stopping rule.
2. **Virtual Time Machine (Fast-Forward Engine)**:
   - Scrub through time (`+24h`, `+72h`, `+168h`) or jump straight into the peak blackout window (11:30 AM IST) to test zero-violation protection live.
3. **Hinglish Voice Agent (Sarvam AI Integration)**:
   - Escalation desk for repeat low-balance debits.
   - Natural Hindi-English conversation confirming identity, explaining the situation without jargon, and securing a Promise-to-Pay date.
   - Guardrailed against discounts or unauthorized subscription adjustments.
4. **Cryptographic Audit Trail**:
   - Every single state transition is recorded with reason strings, exact circular references, and SHA-256 signature verification.
5. **Modern Dark-Mode Dashboard**:
   - Real-time executive KPIs (₹ at risk vs recovered, recovery rate %, compliance violations: 0/0, stopping rules).
   - Interactive category cards, search & filter table, and audio player modal.

---

## Quick Start

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/vedantkamtikar/PACT.git
cd PACT
pip install -r requirements.txt
```

### 2. Configure Environment (Optional)
Copy `.env.example` to `.env`:
```ini
GEMINI_API_KEY=your_gemini_key_here
GROQ_API_KEY=your_groq_key_here
SARVAM_API_KEY=your_sarvam_key_here
PORT=8000
```
> *Note: PACT includes full heuristic classification and synthesized audio fallbacks, running out-of-the-box even without API keys.*

### 3. Run Application
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

### 4. Run Automated Test Suite
```bash
pytest
```
*All 17 compliance, classifier, and API integration tests execute in < 1 second.*

---

## Buildathon Alignment (Track 03: AI Revenue Recovery)

- **Measured ₹ Recovered**: Tracks batch-level ₹ recovered vs at-risk across all decline types.
- **AI Judgment**: Clear separation between deterministic compliance logic (zero hallucinations) and generative AI (normalization & dialogue).
- **Compliant Escalation**: Enforces NPCI windows, blackout periods, and 24-hour pre-debit notices.
- **Stopping Rules**: Correctly halts debits upon reaching 3 retries or encountering regulatory hard-stops.
- **Auditability**: Cryptographically signed audit trail for every action.
