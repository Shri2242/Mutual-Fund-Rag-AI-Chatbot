/* ── app.js — Phase 4 SPA Logic ─────────────────────────────────────────── */
'use strict';

const API_BASE = '';   // same-origin: FastAPI serves both API and SPA

// ── DOM refs ──────────────────────────────────────────────────────────────────
const queryInput    = document.getElementById('query-input');
const sendBtn       = document.getElementById('send-btn');
const answerCard    = document.getElementById('answer-card');
const answerBody    = document.getElementById('answer-body');
const answerSource  = document.getElementById('answer-source');
const answerDate    = document.getElementById('answer-date');
const intentTag     = document.getElementById('intent-tag');
const copyBtn       = document.getElementById('copy-btn');
const thinking      = document.getElementById('thinking');
const conversation  = document.getElementById('conversation');
const welcomeSection = document.getElementById('welcome-section');
const statusFab     = document.getElementById('status-fab');
const sourcesModal  = document.getElementById('sources-modal');
const modalOverlay  = document.getElementById('modal-overlay');
const closeModalBtn = document.getElementById('close-modal-btn');
const sourcesList   = document.getElementById('sources-list');

// ── State ─────────────────────────────────────────────────────────────────────
let inFlight = false;
let lastFullAnswer = '';

// ── Helpers ───────────────────────────────────────────────────────────────────
function setLoading(val) {
  inFlight = val;
  sendBtn.disabled = val || queryInput.value.trim().length === 0;
  if (val) {
    thinking.classList.remove('hidden');
    answerCard.classList.add('hidden');
  } else {
    thinking.classList.add('hidden');
  }
}

function autoResize() {
  queryInput.style.height = 'auto';
  queryInput.style.height = Math.min(queryInput.scrollHeight, 120) + 'px';
}

function scrollToBottom() {
  window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
}

function getIntentLabel(intent) {
  const map = {
    factual:      { label: 'Factual Answer',      cls: 'factual' },
    advisory:     { label: 'Advisory Refusal',    cls: 'advisory' },
    comparison:   { label: 'Comparison Refusal',  cls: 'advisory' },
    prediction:   { label: 'Prediction Refusal',  cls: 'advisory' },
    pii_blocked:  { label: 'PII Blocked',         cls: 'pii' },
    dont_know:    { label: "Don't Know",           cls: 'dont_know' },
  };
  return map[intent] || { label: intent, cls: 'factual' };
}

function buildSourceLink(url) {
  if (!url) return '';
  const clean = url.replace(/\/$/, '');
  return `<a href="${clean}" target="_blank" rel="noopener nofollow">${clean}</a>`;
}

function addUserBubble(text) {
  const div = document.createElement('div');
  div.className = 'msg-bubble user';
  div.textContent = text;
  conversation.appendChild(div);
  scrollToBottom();
}

// ── Render answer from API response ──────────────────────────────────────────
function renderAnswer(data) {
  const { answer, answer_body, source_url, last_updated, intent, post_check_passed } = data;

  lastFullAnswer = answer;

  // Body text
  answerBody.textContent = answer_body || answer;

  // Source link (exactly one URL or none — enforced by backend)
  answerSource.innerHTML = source_url ? buildSourceLink(source_url) : '';

  // Date footer
  answerDate.textContent = last_updated
    ? 'Last updated from sources: ' + last_updated
    : '';

  // Intent tag
  const { label, cls } = getIntentLabel(intent);
  intentTag.textContent = label;
  intentTag.className = 'intent-tag show ' + cls;

  // Card variant styling
  answerCard.className = 'answer-card';
  if (intent === 'pii_blocked') answerCard.classList.add('pii');
  if (['advisory', 'comparison', 'prediction'].includes(intent)) answerCard.classList.add('refusal');

  // Footer visibility
  const hasFooter = source_url || last_updated;
  document.getElementById('answer-footer').style.display = hasFooter ? '' : 'none';

  // Show card
  answerCard.classList.remove('hidden');
  scrollToBottom();
}

// ── Main ask function ─────────────────────────────────────────────────────────
async function ask(query) {
  if (inFlight || !query.trim()) return;

  // Hide welcome section after first question
  welcomeSection.style.display = 'none';

  addUserBubble(query);
  setLoading(true);

  try {
    const res = await fetch(API_BASE + '/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || 'Server error ' + res.status);
    }

    const data = await res.json();
    renderAnswer(data);
  } catch (err) {
    answerBody.textContent = 'Something went wrong: ' + err.message + '. Please try again.';
    answerSource.innerHTML = '';
    answerDate.textContent = '';
    intentTag.className = 'intent-tag';
    answerCard.classList.remove('hidden');
    scrollToBottom();
  } finally {
    setLoading(false);
  }
}

// ── Copy answer ───────────────────────────────────────────────────────────────
copyBtn.addEventListener('click', () => {
  if (!lastFullAnswer) return;
  navigator.clipboard.writeText(lastFullAnswer).then(() => {
    copyBtn.classList.add('copied');
    copyBtn.textContent = 'Copied!';
    setTimeout(() => {
      copyBtn.classList.remove('copied');
      copyBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy`;
    }, 2000);
  });
});

// ── Input events ──────────────────────────────────────────────────────────────
queryInput.addEventListener('input', () => {
  autoResize();
  sendBtn.disabled = inFlight || queryInput.value.trim().length === 0;
});

queryInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    const q = queryInput.value.trim();
    if (q && !inFlight) {
      queryInput.value = '';
      autoResize();
      sendBtn.disabled = true;
      ask(q);
    }
  }
});

sendBtn.addEventListener('click', () => {
  const q = queryInput.value.trim();
  if (q && !inFlight) {
    queryInput.value = '';
    autoResize();
    sendBtn.disabled = true;
    ask(q);
  }
});

// ── Example chips ─────────────────────────────────────────────────────────────
document.querySelectorAll('.chip').forEach(chip => {
  chip.addEventListener('click', () => {
    const q = chip.dataset.query;
    if (q && !inFlight) ask(q);
  });
});

// ── Source Freshness Modal ────────────────────────────────────────────────────
async function loadMeta() {
  try {
    const res = await fetch(API_BASE + '/meta');
    const data = await res.json();
    sourcesList.innerHTML = '';

    const header = document.createElement('div');
    header.className = 'scheme-meta';
    header.style.marginBottom = '8px';
    header.innerHTML = `
      <span>Corpus: <strong style="color:var(--text-primary)">${data.corpus_version}</strong></span>
      <span>AMC: <strong style="color:var(--text-primary)">${data.amc}</strong></span>
      <span>Last ingested: <strong style="color:var(--text-primary)">${data.last_ingested ? data.last_ingested.split('T')[0] : 'N/A'}</strong></span>
    `;
    sourcesList.appendChild(header);

    (data.schemes || []).forEach(s => {
      const card = document.createElement('div');
      card.className = 'scheme-card';
      card.innerHTML = `
        <div class="scheme-name">${s.scheme}</div>
        <div class="scheme-meta">
          <span>${s.category}</span>
          <span>Updated: ${s.last_updated_from_source ? s.last_updated_from_source.split('T')[0] : 'N/A'}</span>
          <a href="${s.url}" target="_blank" rel="noopener nofollow">Groww page ↗</a>
        </div>
      `;
      sourcesList.appendChild(card);
    });
  } catch {
    sourcesList.innerHTML = '<p style="color:var(--text-muted);padding:8px 0">Could not load metadata.</p>';
  }
}

function openModal() {
  sourcesModal.classList.remove('hidden');
  modalOverlay.classList.remove('hidden');
  loadMeta();
}
function closeModal() {
  sourcesModal.classList.add('hidden');
  modalOverlay.classList.add('hidden');
}

statusFab.addEventListener('click', openModal);
closeModalBtn.addEventListener('click', closeModal);
modalOverlay.addEventListener('click', closeModal);
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ── Initial focus ─────────────────────────────────────────────────────────────
queryInput.focus();
