# PACT (Proactive AutoPay Compliance & Tracking)
### A Compliant UPI AutoPay / E-Mandate Recovery Orchestrator
**Razorpay AI Buildathon 2026 — Track 03: AI Revenue Recovery**

---

## 1. One-liner

MandateGuard detects failed UPI AutoPay / e-mandate debits, classifies *why* each one failed, and runs a recovery workflow that is bounded by NPCI's actual retry rules — not a generic "retry 3x and email the customer" bot. Where a human touch is genuinely needed, it hands off to a Hinglish voice agent that negotiates a promise-to-pay and tracks follow-through. Every decision is logged for audit.

---

## 2. Problem statement

UPI AutoPay processes ~1B recurring transactions/month, but AutoPay failure rates run 8–15% (5–7x higher than card mandates). Most "recovery" tooling treats every failure the same way: retry, notify, repeat. That's wrong for two reasons:

1. **It's non-compliant.** NPCI caps retries at 3 attempts within defined windows (24h / 72h / 168h), blocks retries during peak execution windows (10am–1pm), and requires a 24-hour pre-debit notification before any debit attempt. Retrying outside these constraints isn't just bad UX — it can violate the RBI e-mandate framework.
2. **It's the wrong action for the failure type.** A "RBI approval required" decline is a *regulatory hard stop*, not a transient failure — retrying it is a compliance error, not a growth hack. Insufficient-funds failures need time + a nudge. Mandate-expired failures need re-registration, not a retry at all.

**Why this direction over the obvious ones (checkout drop-off, generic subscription dunning):** those are guessable and LLM-wrappable in a weekend, and easy to fake without real domain knowledge. Mandate-aware recovery can't be faked — it requires actually knowing the NPCI/RBI rules, which is exactly the kind of "problem taste" a payments company's panel will notice.

---

## 3. Scope for the buildathon

**In scope:**
- Synthetic batch of 50+ mandate-failure records (Razorpay test-mode style payloads)
- Deterministic compliance/retry engine
- LLM-based decline-reason classifier + root-cause explanation
- Hinglish voice agent for promise-to-pay negotiation (subset of cases)
- Promise-to-pay tracker with follow-up
- Full audit trail + dashboard showing recovered ₹, compliance adherence, and stopping-rule triggers

**Out of scope (state this explicitly in the pitch — shows judgment):**
- Live bank/NPCI integration (test-mode/synthetic only)
- Real telephony (voice agent runs as a simulated call transcript + optional TTS/STT demo, not a live dialer)
- Multi-tenant merchant onboarding

---

## 4. System architecture

```
                         ┌─────────────────────────┐
                         │   Synthetic Batch Feed   │
                         │  (50+ failed-debit recs) │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                       ┌───────────────────────────┐
                       │   1. Decline Classifier    │  ← LLM (Gemini/Groq)
                       │  raw decline code → type   │
                       └────────────┬───────────────┘
                                      │
                                      ▼
                       ┌───────────────────────────┐
                       │ 2. Compliance & Retry      │  ← deterministic rules
                       │    Engine (rules, not AI)  │     engine, no LLM
                       └────────────┬───────────────┘
                          │         │          │
              ┌───────────┘         │          └───────────┐
              ▼                     ▼                       ▼
   ┌───────────────────┐  ┌──────────────────┐   ┌────────────────────┐
   │ Auto-retry queue    │  │ Hard-stop / no    │   │ Escalate to voice   │
   │ (scheduled per      │  │ retry (e.g. RBI   │   │ agent (repeat       │
   │ NPCI window)        │  │ approval req.)    │   │ insufficient-funds) │
   └─────────┬───────────┘  └────────┬──────────┘   └──────────┬──────────┘
              │                       │                          │
              ▼                       ▼                          ▼
      ┌───────────────────────────────────────────────────────────────┐
      │           3. Hinglish Voice Agent (LLM + TTS/STT)              │
      │   negotiates promise-to-pay, logs commitment date/amount       │
      └────────────────────────────┬────────────────────────────────┘
                                    ▼
                       ┌───────────────────────────┐
                       │ 4. Promise-to-Pay Tracker  │
                       │  follow-up + grace period  │
                       └────────────┬───────────────┘
                                      ▼
                       ┌───────────────────────────┐
                       │ 5. Audit Log + Dashboard   │
                       │  ₹ recovered, compliance,  │
                       │  stopping-rule triggers    │
                       └───────────────────────────┘
```

### Component detail

**1. Decline Classifier (LLM)**
Takes a raw decline code/message and merchant context, maps it into a small fixed taxonomy (below). This is the one place an LLM genuinely adds value — decline messages from different banks/PSPs are inconsistent free text, and classification needs judgment.

**2. Compliance & Retry Engine (deterministic — no LLM)**
This is the core of "AI Judgment" — proving you know where *not* to use AI. Pure rules:
- Max 3 retries per NPCI guidance
- Retry windows: 24h → 72h → 168h
- No retries scheduled inside the 10am–1pm blackout window
- 24h pre-debit notification enforced before any attempt
- `RBI_APPROVAL_REQUIRED` and `MANDATE_EXPIRED` → hard stop, routed to a different flow (re-registration ask / compliant escalation), never retried

**3. Hinglish Voice Agent (LLM + voice)**
Only triggered for cases the rules engine flags as "needs human judgment" (e.g., 2nd consecutive insufficient-funds failure). Conversational agent in Hindi-English mix, scripted around: confirm identity → explain the situation → negotiate a promise-to-pay date → log commitment. Guardrailed: no negotiating amount changes, no info beyond what's needed, hangs up gracefully after N failed attempts to book a promise.

**4. Promise-to-Pay Tracker**
Stores commitments, checks follow-through against the next scheduled retry, and triggers a grace-period reminder before final escalation/lapse.

**5. Audit Log + Dashboard**
Every state transition (classified as X, retried at time T because Y, stopped because Z, escalated to voice because W) is logged with a reason string. Dashboard shows: batch-level ₹ recovered, recovery rate by decline type, compliance adherence (0 violations of retry-window/blackout rules), and stopping-rule trigger counts.

---

## 5. Decline taxonomy (core IP of the project)

| Code (synthetic) | Meaning | Action |
|---|---|---|
| `INSUFFICIENT_FUNDS` | Low balance at debit time | Retry per window; escalate to voice agent after 2nd failure |
| `TECHNICAL_DECLINE` | Bank/NPCI server-side issue | Retry immediately at next valid window (not user's fault) |
| `MANDATE_EXPIRED` | Mandate lapsed | No retry — trigger re-registration flow |
| `RBI_APPROVAL_REQUIRED` | Regulatory condition, not transient | Hard stop — never retried, flagged for manual compliance review |
| `PRE_DEBIT_NOTIFICATION_MISSED` | 24h notice wasn't sent | Block the attempt entirely until notice sent — compliance-critical |
| `EXECUTION_WINDOW_BLOCKED` | Falls in NPCI peak blackout (10am–1pm) | Reschedule to next valid window, not a failure per se |

---

## 6. Agent workflow (LangGraph state graph)

```
StateGraph nodes:
  ingest_batch → classify_decline → check_compliance_rules
      ├─ (retryable + in window) → schedule_retry → await_outcome → [loop back]
      ├─ (hard stop) → log_hard_stop → end
      └─ (needs_human_judgment) → voice_agent_negotiate → log_promise
                                        → track_promise → [grace period] → end/escalate

Shared state (Pydantic model):
  mandate_id, decline_code, decline_type, attempt_count,
  last_attempt_ts, next_valid_window, promise_to_pay (date, amount),
  status, audit_trail: List[AuditEvent]
```

---

## 7. Tech stack

Matches your existing agent-building stack, so build velocity should be high:

- **Orchestration:** LangGraph (Python) — same pattern as your lead-gen agent
- **LLM:** Gemini or Groq/Llama (classifier + voice-agent dialogue generation)
- **Voice:** Sarvam AI (or equivalent) for Hinglish TTS/STT — worth using given your existing interest there; if time-boxed, simulate as text transcripts with optional audio demo
- **State/validation:** Pydantic v2 models for mandate state
- **Backend:** FastAPI
- **Storage:** SQLite (buildathon) / Postgres (if extended)
- **Dashboard:** Vanilla HTML/JS or lightweight React, same style as your lead-gen dashboard
- **Synthetic data generator:** script to produce 50+ realistic mandate-failure records across the taxonomy above, with randomized timing so retry-window logic is actually exercised

---

## 8. Synthetic batch design (for "measured ₹ recovered")

Generate 50–100 synthetic failed-debit records with:
- Mixed decline types (weighted realistically: insufficient funds most common, RBI-approval-required rare but present)
- Randomized original debit amounts (₹99–₹15,000 range to also exercise the AFA threshold)
- Randomized failure timestamps (some landing inside the blackout window, to prove the engine handles it)

Run the batch through the full pipeline and report:
- **₹ recovered** vs. total ₹ at risk
- **Recovery rate by decline type** (shows insufficient-funds recovers well, RBI-approval-required correctly recovers 0% because it's correctly never retried — this is a *feature*, not a gap, and worth calling out explicitly in the pitch)
- **Zero compliance violations** (no retry outside window, no retry during blackout, no retry on hard-stop codes)
- **Stopping-rule triggers** (how many hit max-retry and were correctly abandoned)

---

## 9. Mapping to "the bar" and judging criteria

| Requirement | How MandateGuard satisfies it |
|---|---|
| Measured money recovered | Batch-level ₹ recovered / at-risk, per decline type |
| Compliant escalation | Rules engine enforces NPCI windows, blackout, AFA thresholds |
| Stopping rules | Max-3-retry cap + hard-stop codes, both logged |
| Audit trail | Every state transition logged with a reason |
| Problem Taste | Mandate-specific regulatory nuance, not generic dunning |
| AI Judgment | LLM only for classification/dialogue; retry logic is deterministic |
| Failure Recovery narrative | Document the blackout-window edge case and how the synthetic data caught it |

---

## 10. Suggested build order (time-boxed)

1. Decline taxonomy + Pydantic state models + synthetic data generator
2. Deterministic compliance/retry engine (get this fully correct first — it's your differentiator)
3. LLM decline classifier
4. Audit log + dashboard (get ₹-recovered metrics visible early, iterate on top)
5. Promise-to-pay tracker
6. Hinglish voice agent (last — highest effort-to-differentiation ratio is actually the rules engine, not the voice layer; don't let voice eat the whole timeline)
7. Record the 5-min pitch: lead with the blackout-window / RBI-approval-required insight, since that's the "problem taste" moment

---

## 11. What could go wrong (pre-empt for the "Failure Recovery" criterion)

- **LLM misclassifies decline codes** → mitigate with a confidence threshold; low-confidence classifications fall back to a conservative default (treat as retryable-with-caution, never as hard-stop, to avoid wrongly blocking a recoverable payment)
- **Voice agent negotiates something it shouldn't** (e.g., implies a discount) → hard system-prompt guardrails + a fixed script skeleton, not free-form negotiation
- **Synthetic data too clean, doesn't exercise blackout/edge cases** → explicitly force a percentage of records into edge conditions rather than pure random generation
