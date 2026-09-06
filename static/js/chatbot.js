/* ============================================================
   Aarogya Connect — AI triage chatbot widget
   ============================================================ */

(function () {
  const toggle = document.getElementById('chatToggle');
  const panel = document.getElementById('chatPanel');
  if (!toggle || !panel) return;

  const USER = window.CURRENT_USER;
  if (toggle.dataset.role && toggle.dataset.role !== USER.role) {
    toggle.style.display = 'none';
    return;
  }

  const body = document.getElementById('chatBody');
  const form = document.getElementById('chatForm');
  const input = document.getElementById('chatInput');
  const closeBtn = document.getElementById('chatClose');

  let chatId = null;
  let opened = false;

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  function timeOf(ts) {
    if (!ts) return '';
    const dt = new Date(ts.includes('T') ? ts : ts.replace(' ', 'T') + 'Z');
    if (isNaN(dt)) return '';
    return dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function bubble(msg) {
    if (msg.messageType === 'doctor_suggestion') return doctorSuggestionCard(msg);
    const el = document.createElement('div');
    el.className = `msg ${msg.senderType}`;
    el.innerHTML = `${escapeHtml(msg.message)}<span class="meta">${msg.senderType === 'ai' ? 'Assistant' : 'You'} · ${timeOf(msg.timestamp)}</span>`;
    body.appendChild(el);
    body.scrollTop = body.scrollHeight;
  }

  function doctorSuggestionCard(msg) {
    let doctors = [];
    try { doctors = JSON.parse(msg.message); } catch (e) { return; }
    const wrap = document.createElement('div');
    wrap.className = 'msg ai';
    wrap.style.maxWidth = '92%';
    wrap.style.padding = '10px';
    wrap.innerHTML = doctors.map(d => `
      <div style="display:flex; align-items:center; gap:10px; padding:8px; border:1px solid var(--border); border-radius:10px; margin-bottom:6px; background:var(--surface);">
        <span class="avatar" style="width:34px;height:34px;font-size:11px;">${(d.name||'?').split(' ').map(p=>p[0]).slice(0,2).join('').toUpperCase()}</span>
        <div style="flex:1; min-width:0;">
          <div style="font-weight:600; font-size:12.5px;">${escapeHtml(d.name)}</div>
          <div style="font-size:11px; color:var(--ink-soft);">${escapeHtml(d.specialization)} · ★ ${d.rating}</div>
        </div>
        <div style="display:flex; flex-direction:column; gap:4px;">
          <button class="btn btn-ghost btn-sm" style="padding:4px 8px; font-size:11px;" data-msg-doctor="${d.doctorId}">Message</button>
          <button class="btn btn-primary btn-sm" style="padding:4px 8px; font-size:11px;" data-book-doctor="${d.doctorId}">Book</button>
        </div>
      </div>
    `).join('');
    body.appendChild(wrap);
    Array.from(wrap.querySelectorAll('[data-msg-doctor]')).forEach(btn =>
      btn.addEventListener('click', () => {
        panel.classList.remove('open');
        window.AarogyaBridge && window.AarogyaBridge.messageDoctor(btn.dataset.msgDoctor);
      }));
    Array.from(wrap.querySelectorAll('[data-book-doctor]')).forEach(btn =>
      btn.addEventListener('click', () => {
        panel.classList.remove('open');
        window.AarogyaBridge && window.AarogyaBridge.bookDoctor(btn.dataset.bookDoctor);
      }));
    body.scrollTop = body.scrollHeight;
  }

  async function openChat() {
    if (opened) return;
    opened = true;
    try {
      const res = await fetch('/api/chat');
      const data = await res.json();
      chatId = data.chatId;
      body.innerHTML = '';
      data.messages.forEach(bubble);
    } catch (err) {
      body.innerHTML = `<div class="empty-state">Couldn't load the assistant right now.</div>`;
    }
  }

  toggle.addEventListener('click', () => {
    panel.classList.toggle('open');
    if (panel.classList.contains('open')) {
      openChat();
      input.focus();
    }
  });
  closeBtn.addEventListener('click', () => panel.classList.remove('open'));

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || !chatId) return;
    input.value = '';

    bubble({ senderType: USER.role, message: text, timestamp: new Date().toISOString() });
    const typingEl = document.createElement('div');
    typingEl.className = 'msg ai';
    typingEl.textContent = '…';
    body.appendChild(typingEl);
    body.scrollTop = body.scrollHeight;

    try {
      const res = await fetch(`/api/chat/${chatId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      typingEl.remove();
      if (!res.ok) throw new Error(data.error);
      // messages includes the user's own echoed message first — skip it, render the rest
      data.messages.filter(m => m.senderType === 'ai').forEach(bubble);
    } catch (err) {
      typingEl.remove();
      bubble({ senderType: 'ai', message: "Sorry, I couldn't process that — please try again.", timestamp: new Date().toISOString() });
    }
  });
})();
