// MandateGuard Dashboard Logic
const state = {
  status: null,
  analytics: null,
  mandates: [],
  activeFilter: 'ALL',
  selectedDeclineType: null,
  searchQuery: '',
  activeMandate: null,
};

// Formatting helpers
function formatINR(val) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0
  }).format(val || 0);
}

function formatDate(isoStr) {
  if (!isoStr) return '—';
  try {
    const d = new Date(isoStr);
    return d.toLocaleString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
  } catch (e) {
    return isoStr;
  }
}

// Toast notification
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerText = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// API Calls
async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    state.status = await res.json();
    renderStatus();
  } catch (e) {
    console.error('Failed to fetch status:', e);
  }
}

async function fetchAnalytics() {
  try {
    const res = await fetch('/api/analytics');
    state.analytics = await res.json();
    renderAnalytics();
  } catch (e) {
    console.error('Failed to fetch analytics:', e);
  }
}

async function fetchMandates() {
  try {
    const res = await fetch('/api/mandates');
    const data = await res.json();
    state.mandates = data.mandates || [];
    renderTable();
  } catch (e) {
    console.error('Failed to fetch mandates:', e);
  }
}

async function advanceClock(hours) {
  try {
    const res = await fetch('/api/clock/advance', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hours })
    });
    const data = await res.json();
    showToast(data.message, 'info');
    await refreshAll();
  } catch (e) {
    showToast('Failed to advance clock', 'danger');
  }
}

async function jumpToBlackout() {
  try {
    const res = await fetch('/api/clock/jump-blackout', { method: 'POST' });
    const data = await res.json();
    showToast('⚠️ Jumped into NPCI Peak Blackout Window (11:30 AM IST)', 'warning');
    await refreshAll();
  } catch (e) {
    showToast('Failed to jump to blackout', 'danger');
  }
}

async function jumpToCompliant() {
  try {
    const res = await fetch('/api/clock/jump-compliant', { method: 'POST' });
    const data = await res.json();
    showToast('✅ Jumped to Compliant Window (1:15 PM IST)', 'success');
    await refreshAll();
  } catch (e) {
    showToast('Failed to jump to compliant window', 'danger');
  }
}

async function executeDueDebits() {
  try {
    const res = await fetch('/api/execute-due', { method: 'POST' });
    const data = await res.json();
    if (data.is_in_blackout) {
      showToast(data.message, 'warning');
    } else {
      showToast(data.message, data.recovered_count > 0 ? 'success' : 'info');
    }
    await refreshAll();
  } catch (e) {
    showToast('Error executing due debits', 'danger');
  }
}

async function processBatch() {
  try {
    showToast('Running AI classification & compliance engine...', 'info');
    const res = await fetch('/api/batch/process', { method: 'POST' });
    const data = await res.json();
    showToast(data.message, 'success');
    await refreshAll();
  } catch (e) {
    showToast('Failed to process batch', 'danger');
  }
}

async function generateBatch() {
  try {
    const res = await fetch('/api/batch/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ count: 60, seed: Math.floor(Math.random() * 1000) })
    });
    const data = await res.json();
    showToast(data.message, 'success');
    await refreshAll();
  } catch (e) {
    showToast('Failed to generate batch', 'danger');
  }
}

async function resetSystem() {
  if (!confirm('Regenerate fresh synthetic batch and reset compliance orchestrator?')) return;
  try {
    const res = await fetch('/api/reset', { method: 'POST' });
    const data = await res.json();
    showToast(data.message, 'success');
    await refreshAll();
  } catch (e) {
    showToast('Failed to reset system', 'danger');
  }
}

// Voice Call Simulation Modal
async function openVoiceCallModal(mandateId) {
  try {
    showToast('Initiating Hinglish Voice Agent call...', 'info');
    const res = await fetch(`/api/voice/call/${mandateId}`, { method: 'POST' });
    const data = await res.json();
    
    const callRecord = data.call_record;
    const promise = data.promise_to_pay;
    const mandate = data.mandate;

    document.getElementById('callCustomerName').innerText = callRecord.customer_name;
    document.getElementById('callCustomerPhone').innerText = callRecord.customer_phone;
    document.getElementById('callMerchantSub').innerText = `${mandate.merchant_name} — ${mandate.subscription_item}`;
    document.getElementById('callAmount').innerText = formatINR(mandate.amount);

    // Audio player
    const audioEl = document.getElementById('callAudioPlayer');
    if (callRecord.audio_data_uri) {
      audioEl.src = callRecord.audio_data_uri;
      audioEl.style.display = 'block';
    } else {
      audioEl.style.display = 'none';
    }

    // Render turns
    const container = document.getElementById('chatBubbleContainer');
    container.innerHTML = '';
    callRecord.turns.forEach(turn => {
      const isAgent = turn.speaker.toLowerCase() === 'agent';
      const div = document.createElement('div');
      div.className = `chat-turn ${isAgent ? 'agent' : 'customer'}`;
      div.innerHTML = `
        <div class="speaker-label">${turn.speaker} ${isAgent ? '• MandateGuard Desk' : ''}</div>
        <div class="bubble">${turn.text}</div>
      `;
      container.appendChild(div);
    });

    // Promise details
    document.getElementById('ptpDateDisplay').innerText = formatDate(promise.promised_date);
    document.getElementById('ptpAmountDisplay').innerText = formatINR(promise.amount);

    // Show modal
    document.getElementById('voiceModal').classList.add('open');
    await refreshAll();
  } catch (e) {
    showToast('Error during voice call simulation', 'danger');
  }
}

function speakVoiceScript() {
  if (!('speechSynthesis' in window)) {
    showToast('Web Speech API not supported in this browser', 'warning');
    return;
  }
  window.speechSynthesis.cancel();
  const bubbles = document.querySelectorAll('.chat-turn.agent .bubble');
  if (bubbles.length === 0) return;

  let textToSpeak = Array.from(bubbles).map(b => b.innerText).join('. ');
  const utterance = new SpeechSynthesisUtterance(textToSpeak);
  utterance.rate = 1.0;
  utterance.pitch = 1.05;
  
  // Try finding Hindi / Indian English voice
  const voices = window.speechSynthesis.getVoices();
  const indianVoice = voices.find(v => v.lang.includes('hi') || v.lang.includes('en-IN') || v.name.includes('India'));
  if (indianVoice) utterance.voice = indianVoice;

  window.speechSynthesis.speak(utterance);
  showToast('Speaking dialogue through browser speech engine...', 'info');
}

// Audit Trail Modal
async function openAuditTrailModal(mandateId = null) {
  try {
    const url = mandateId ? `/api/mandates/${mandateId}` : '/api/audit-trail?limit=50';
    const res = await fetch(url);
    const data = await res.json();
    
    const events = mandateId ? data.audit_trail : data;
    const title = mandateId ? `Cryptographic Audit Trail: Mandate ${mandateId}` : 'Global Compliance Audit Trail';
    document.getElementById('auditModalTitle').innerText = title;

    const list = document.getElementById('auditList');
    list.innerHTML = '';

    if (!events || events.length === 0) {
      list.innerHTML = '<div style="color: var(--text-muted); text-align: center; padding: 2rem;">No audit events recorded yet.</div>';
    } else {
      events.forEach(evt => {
        const item = document.createElement('div');
        item.className = 'audit-item';
        item.innerHTML = `
          <div class="audit-item-header">
            <span>${formatDate(evt.timestamp)}</span>
            <span class="audit-rule">${evt.rule_cited}</span>
          </div>
          <div class="audit-reason">
            <strong>${evt.action_taken}</strong>: ${evt.reason}
          </div>
          <div class="audit-hash">SHA-256 Sig: ${evt.signature_hash || 'verified'} • Transition: ${evt.from_status || 'NEW'} → ${evt.to_status}</div>
        `;
        list.appendChild(item);
      });
    }

    document.getElementById('auditModal').classList.add('open');
  } catch (e) {
    showToast('Failed to load audit trail', 'danger');
  }
}

// Renders
function renderStatus() {
  if (!state.status) return;
  const { simulated_time_ist, is_in_blackout, hours_advanced_total } = state.status;
  
  document.getElementById('simulatedTimeClock').innerText = simulated_time_ist;
  document.getElementById('hoursAdvancedLabel').innerText = `+${hours_advanced_total}h Advanced`;

  const pulseDot = document.getElementById('clockPulseDot');
  const blackoutBadge = document.getElementById('blackoutBadge');

  if (is_in_blackout) {
    pulseDot.className = 'pulse-dot blackout';
    blackoutBadge.className = 'blackout-badge active';
    blackoutBadge.innerHTML = '⚠️ NPCI Peak Blackout (10am–1pm IST)';
  } else {
    pulseDot.className = 'pulse-dot';
    blackoutBadge.className = 'blackout-badge inactive';
    blackoutBadge.innerHTML = '✅ Compliant Window (Ready)';
  }
}

function renderAnalytics() {
  if (!state.analytics) return;
  const a = state.analytics;

  document.getElementById('kpiAtRisk').innerText = formatINR(a.total_at_risk_inr);
  document.getElementById('kpiRecovered').innerText = formatINR(a.total_recovered_inr);
  document.getElementById('kpiRate').innerText = `${a.overall_recovery_rate_pct}%`;
  document.getElementById('kpiViolations').innerText = `${a.compliance_violations} / 0`;
  document.getElementById('kpiStoppingRules').innerText = a.stopping_rules_triggered;
  document.getElementById('kpiVoiceCount').innerText = `${a.voice_escalations_count} calls`;

  // Render Category Breakdown Cards
  const container = document.getElementById('categoryGrid');
  container.innerHTML = '';

  const tagClasses = {
    'INSUFFICIENT_FUNDS': 'tag-insufficient',
    'TECHNICAL_DECLINE': 'tag-technical',
    'EXECUTION_WINDOW_BLOCKED': 'tag-blackout',
    'MANDATE_EXPIRED': 'tag-expired',
    'RBI_APPROVAL_REQUIRED': 'tag-rbi',
    'PRE_DEBIT_NOTIFICATION_MISSED': 'tag-prenotif',
  };

  const readableTitles = {
    'INSUFFICIENT_FUNDS': 'Insufficient Funds',
    'TECHNICAL_DECLINE': 'Technical Decline',
    'EXECUTION_WINDOW_BLOCKED': 'Peak Blackout',
    'MANDATE_EXPIRED': 'Mandate Expired',
    'RBI_APPROVAL_REQUIRED': 'RBI Approval Req.',
    'PRE_DEBIT_NOTIFICATION_MISSED': 'Pre-Debit Notice',
  };

  for (const [type, data] of Object.entries(a.breakdown_by_type || {})) {
    const card = document.createElement('div');
    const isSelected = state.selectedDeclineType === type;
    card.className = `category-card ${isSelected ? 'active' : ''}`;
    card.onclick = () => {
      state.selectedDeclineType = (state.selectedDeclineType === type) ? null : type;
      renderAnalytics();
      renderTable();
    };

    const tagClass = tagClasses[type] || 'tag-insufficient';
    card.innerHTML = `
      <span class="category-tag ${tagClass}">${data.is_retryable ? 'Retryable' : 'Hard Stop'}</span>
      <div class="category-name">${readableTitles[type] || type}</div>
      <div class="category-stats">
        <span>${data.count} records</span>
        <span class="category-recovered">${formatINR(data.recovered_inr)}</span>
      </div>
      <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 0.25rem;">
        Recovery: <strong>${data.recovery_rate_pct}%</strong> of ${formatINR(data.at_risk_inr)}
      </div>
    `;
    container.appendChild(card);
  }
}

function renderTable() {
  const tbody = document.getElementById('mandatesTableBody');
  tbody.innerHTML = '';

  let filtered = state.mandates;

  // Filter tab
  if (state.activeFilter === 'RETRY_SCHEDULED') {
    filtered = filtered.filter(m => m.status === 'RETRY_SCHEDULED');
  } else if (state.activeFilter === 'ESCALATED_VOICE') {
    filtered = filtered.filter(m => m.status === 'ESCALATED_VOICE' || m.voice_escalated);
  } else if (state.activeFilter === 'PROMISE_SECURED') {
    filtered = filtered.filter(m => m.status === 'PROMISE_SECURED');
  } else if (state.activeFilter === 'RECOVERED') {
    filtered = filtered.filter(m => m.status === 'RECOVERED');
  } else if (state.activeFilter === 'HARD_STOP') {
    filtered = filtered.filter(m => ['HARD_STOP_REGULATORY', 'HARD_STOP_EXPIRED', 'STOPPING_RULE_MAX_RETRIES'].includes(m.status));
  }

  // Filter category card
  if (state.selectedDeclineType) {
    filtered = filtered.filter(m => m.decline_type === state.selectedDeclineType);
  }

  // Filter search
  if (state.searchQuery) {
    const q = state.searchQuery.toLowerCase();
    filtered = filtered.filter(m =>
      m.customer_name.toLowerCase().includes(q) ||
      m.umn.toLowerCase().includes(q) ||
      m.customer_phone.includes(q) ||
      m.merchant_name.toLowerCase().includes(q)
    );
  }

  document.getElementById('tableCountDisplay').innerText = `Showing ${filtered.length} of ${state.mandates.length} mandates`;

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2.5rem;">No mandates match the selected criteria.</td></tr>`;
    return;
  }

  filtered.forEach(m => {
    const tr = document.createElement('tr');

    // Status pill
    let pillClass = 'pill-scheduled';
    let pillText = m.status;
    if (m.status === 'RECOVERED') {
      pillClass = 'pill-recovered';
      pillText = '✅ RECOVERED';
    } else if (m.status === 'ESCALATED_VOICE') {
      pillClass = 'pill-voice';
      pillText = '🎧 VOICE CALL';
    } else if (m.status === 'PROMISE_SECURED') {
      pillClass = 'pill-promise';
      pillText = '🤝 PROMISE GIVEN';
    } else if (m.status.includes('HARD_STOP') || m.status.includes('STOPPING_RULE')) {
      pillClass = 'pill-hardstop';
      pillText = '🛑 HARD STOP';
    } else if (m.status === 'RETRY_SCHEDULED') {
      pillClass = 'pill-scheduled';
      pillText = '⏳ SCHEDULED';
    }

    // Action button
    let actionBtn = `<button class="btn btn-secondary btn-sm" onclick="openAuditTrailModal('${m.id}')">Audit</button>`;
    if (m.status === 'ESCALATED_VOICE' || (m.decline_type === 'INSUFFICIENT_FUNDS' && m.status !== 'RECOVERED')) {
      actionBtn = `
        <button class="btn btn-purple btn-sm" onclick="openVoiceCallModal('${m.id}')" title="Trigger Hinglish voice call">
          🎧 Call
        </button>
        <button class="btn btn-secondary btn-sm" onclick="openAuditTrailModal('${m.id}')">Audit</button>
      `;
    }

    tr.innerHTML = `
      <td>
        <div class="customer-cell">
          <span class="customer-name">${m.customer_name}</span>
          <span class="customer-phone">${m.customer_phone}</span>
        </div>
      </td>
      <td>
        <div>${m.merchant_name}</div>
        <span class="umn-tag">${m.umn}</span>
      </td>
      <td>
        <span class="amount-cell">${formatINR(m.amount)}</span>
      </td>
      <td>
        <div style="font-weight: 600; font-size: 0.75rem;">${m.decline_type}</div>
        <div style="font-size: 0.68rem; color: var(--text-muted); font-family: var(--font-mono);">${m.raw_decline_code}</div>
      </td>
      <td>
        <span class="status-pill ${pillClass}">${pillText}</span>
        <div style="font-size: 0.68rem; color: var(--text-muted); margin-top: 0.2rem;">Attempts: ${m.attempt_count}/${m.max_attempts}</div>
      </td>
      <td>
        <div style="font-size: 0.75rem; font-family: var(--font-mono);">${formatDate(m.next_retry_ts)}</div>
      </td>
      <td style="text-align: right; white-space: nowrap;">
        ${actionBtn}
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// Tab click handler
function setFilter(filter) {
  state.activeFilter = filter;
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.filter === filter);
  });
  renderTable();
}

function closeModal(modalId) {
  document.getElementById(modalId).classList.remove('open');
  if (modalId === 'voiceModal' && 'speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }
}

async function refreshAll() {
  await Promise.all([fetchStatus(), fetchAnalytics(), fetchMandates()]);
}

// Initial setup
window.addEventListener('DOMContentLoaded', async () => {
  // Search input listener
  const searchEl = document.getElementById('tableSearch');
  if (searchEl) {
    searchEl.addEventListener('input', (e) => {
      state.searchQuery = e.target.value;
      renderTable();
    });
  }

  // Load voices for Web Speech
  if ('speechSynthesis' in window) {
    window.speechSynthesis.onvoiceschanged = () => {
      window.speechSynthesis.getVoices();
    };
  }

  await refreshAll();

  // Polling every 5 seconds to keep clock live
  setInterval(fetchStatus, 5000);
});
