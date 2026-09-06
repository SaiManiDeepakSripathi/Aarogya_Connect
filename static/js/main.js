/* ============================================================
   Aarogya Connect — shared + dashboard JS
   ============================================================ */

// ---------------------------------------------------------- theme
(function initTheme() {
  const root = document.documentElement;
  const saved = localStorage.getItem('hc-theme');
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  const theme = saved || (prefersDark ? 'dark' : 'light');
  root.setAttribute('data-theme', theme);

  const btn = document.getElementById('themeToggle');
  if (btn) {
    btn.addEventListener('click', () => {
      const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      localStorage.setItem('hc-theme', next);
    });
  }
})();

function toast(message) {
  const stack = document.getElementById('toastStack');
  if (!stack) return;
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = message;
  stack.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

// Only run the dashboard logic on pages that have the app shell
if (document.getElementById('panel-overview')) {

  const USER = window.CURRENT_USER;
  const $ = (sel, ctx) => (ctx || document).querySelector(sel);
  const $$ = (sel, ctx) => Array.from((ctx || document).querySelectorAll(sel));

  async function api(path, options = {}) {
    const res = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'Something went wrong');
    return data;
  }

  const initials = (name) => (name || '?').split(' ').map(p => p[0]).slice(0, 2).join('').toUpperCase();
  const money = (n) => `₹${Number(n || 0).toLocaleString('en-IN')}`;
  const fmtDate = (d) => {
    if (!d) return '—';
    const dt = new Date(d);
    if (isNaN(dt)) return d;
    return dt.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
  };
  const fmtTime = (ts) => {
    if (!ts) return '';
    const dt = new Date(ts.replace(' ', 'T') + 'Z');
    if (isNaN(dt)) return '';
    return dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };
  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }
  function escapeAttr(str) {
    return (str || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // -------------------------------------------------- nav / rail
  const navButtons = $$('#navButtons button');
  navButtons.forEach(btn => {
    const roleLock = btn.dataset.role;
    if (roleLock && !roleLock.split(',').includes(USER.role)) btn.style.display = 'none';
  });

  function showPanel(name) {
    $$('.panel').forEach(p => p.classList.remove('active'));
    const target = document.getElementById(`panel-${name}`);
    if (target) target.classList.add('active');
    navButtons.forEach(b => b.classList.toggle('active', b.dataset.panel === name));
    const titles = {
      overview: 'Overview', patients: 'Patients', doctors: 'Find a doctor',
      appointments: 'Appointments', messages: 'Messages', prescriptions: 'Prescriptions',
      records: 'Medical records', pharmacyRequests: 'Pharmacy requests', orders: 'Incoming orders',
      profile: 'Your profile',
    };
    document.getElementById('panelTitle').textContent = titles[name] || 'Overview';
    closeRailOnMobile();
    loadPanel(name);
  }

  navButtons.forEach(btn => btn.addEventListener('click', () => showPanel(btn.dataset.panel)));

  // mobile rail
  const rail = document.getElementById('rail');
  const railScrim = document.getElementById('railScrim');
  const railToggle = document.getElementById('railToggle');
  function mqCheck() {
    railToggle.style.display = window.innerWidth <= 900 ? 'flex' : 'none';
  }
  mqCheck();
  window.addEventListener('resize', mqCheck);
  railToggle.addEventListener('click', () => {
    rail.classList.add('open');
    railScrim.classList.add('show');
  });
  railScrim.addEventListener('click', closeRailOnMobile);
  function closeRailOnMobile() {
    rail.classList.remove('open');
    railScrim.classList.remove('show');
  }

  // -------------------------------------------------- avatar
  function paintAvatar(el, name, imagePath) {
    if (imagePath) {
      el.outerHTML = `<img src="${imagePath}" alt="${name}" id="${el.id}" class="${el.className}">`;
    } else {
      el.textContent = initials(name);
    }
  }
  paintAvatar(document.getElementById('railAvatar'), USER.name, USER.profileImage);
  paintAvatar(document.getElementById('profileAvatar'), USER.name, USER.profileImage);

  // -------------------------------------------------- availability toggle (doctor)
  const availWrap = document.getElementById('availabilityToggleWrap');
  const availBtn = document.getElementById('availabilityToggle');
  const availLabel = document.getElementById('availabilityLabel');
  let isAvailable = true;

  async function initAvailability() {
    if (USER.role !== 'doctor') return;
    availWrap.style.display = 'block';
    const me = await api('/api/me');
    isAvailable = !!(me.profile && me.profile.isAvailable);
    paintAvailability();
  }
  function paintAvailability() {
    availBtn.classList.toggle('on', isAvailable);
    availLabel.textContent = isAvailable ? 'Available to patients' : 'Currently offline';
  }
  if (availBtn) {
    availBtn.addEventListener('click', async () => {
      try {
        const res = await api(`/api/doctors/${USER.userId}/status`, {
          method: 'PUT',
          body: JSON.stringify({ isAvailable: !isAvailable }),
        });
        isAvailable = res.isAvailable;
        paintAvailability();
        toast(isAvailable ? "You're marked available." : "You're marked offline.");
      } catch (err) { toast(err.message); }
    });
  }
  initAvailability();

  // -------------------------------------------------- data cache
  let cache = { doctors: null, patients: null, appointments: null, records: null, me: null, pharmacies: null };

  async function loadPanel(name) {
    try {
      if (name === 'overview') return renderOverview();
      if (name === 'patients' && USER.role === 'doctor') return renderPatients();
      if (name === 'doctors' && USER.role === 'patient') return renderDoctors();
      if (name === 'appointments') return renderAppointments();
      if (name === 'messages') return renderMessagesPanel();
      if (name === 'prescriptions') return renderPrescriptions();
      if (name === 'records') return renderRecords();
      if (name === 'pharmacyRequests' && USER.role === 'doctor') return renderPharmacyRequests();
      if (name === 'orders' && USER.role === 'pharmacy') return renderOrders();
      if (name === 'profile') return renderProfile();
    } catch (err) {
      toast(err.message);
    }
  }

  // -------------------------------------------------- overview
  async function renderOverview() {
    if (USER.role === 'pharmacy') return renderPharmacyOverview();

    const [appointments] = await Promise.all([api('/api/appointments')]);
    cache.appointments = appointments;

    const statsWrap = document.getElementById('overviewStats');
    let stats;
    if (USER.role === 'patient') {
      const upcoming = appointments.filter(a => ['pending', 'confirmed'].includes(a.status)).length;
      const completed = appointments.filter(a => a.status === 'completed').length;
      stats = [
        { num: appointments.length, label: 'Total appointments' },
        { num: upcoming, label: 'Upcoming' },
        { num: completed, label: 'Completed' },
      ];
    } else {
      const pending = appointments.filter(a => a.status === 'pending').length;
      const confirmed = appointments.filter(a => a.status === 'confirmed').length;
      stats = [
        { num: appointments.length, label: 'Total appointments' },
        { num: pending, label: 'Awaiting confirmation' },
        { num: confirmed, label: 'Confirmed' },
      ];
    }
    statsWrap.innerHTML = stats.map(s => `
      <div class="card stat-card"><div class="num">${s.num}</div><div class="label">${s.label}</div></div>
    `).join('');

    const upcomingList = appointments
      .filter(a => ['pending', 'confirmed'].includes(a.status))
      .slice(0, 5);
    const listWrap = document.getElementById('overviewAppointments');
    if (!upcomingList.length) {
      listWrap.innerHTML = `<div class="empty-state">${vitalSVG()}<p>Nothing on the horizon yet.</p></div>`;
      return;
    }
    listWrap.innerHTML = upcomingList.map(a => `
      <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 0; border-bottom:1px solid var(--border);">
        <div>
          <div style="font-weight:600; font-size:13.5px;">${USER.role === 'patient' ? a.doctorName : a.patientName}</div>
          <div class="muted" style="font-size:12px;">${fmtDate(a.appointmentDate)} · ${a.slot || 'time TBD'} · ${a.mode}</div>
        </div>
        <span class="badge badge-${a.status}">${a.status}</span>
      </div>
    `).join('');
  }

  async function renderPharmacyOverview() {
    document.getElementById('overviewAppointmentsCard').style.display = 'none';
    const orders = await api('/api/orders');
    cache.orders = orders;
    const placed = orders.filter(o => o.status === 'placed').length;
    const fulfilled = orders.filter(o => o.status === 'fulfilled').length;
    const statsWrap = document.getElementById('overviewStats');
    statsWrap.innerHTML = [
      { num: orders.length, label: 'Total orders' },
      { num: placed, label: 'Awaiting action' },
      { num: fulfilled, label: 'Fulfilled' },
    ].map(s => `<div class="card stat-card"><div class="num">${s.num}</div><div class="label">${s.label}</div></div>`).join('');
  }

  function vitalSVG() {
    return `<svg class="vital-line" viewBox="0 0 200 32" preserveAspectRatio="none">
      <path d="M0 16 H40 L48 16 L56 4 L64 28 L72 16 L80 16 L88 8 L96 24 L104 16 H200"/>
    </svg>`;
  }

  // -------------------------------------------------- patients (doctor)
  async function renderPatients() {
    const patients = await api('/api/patients');
    cache.patients = patients;
    const tbody = $('#patientsTable tbody');
    if (!patients.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No patients yet.</td></tr>`;
      return;
    }
    tbody.innerHTML = patients.map(p => `
      <tr>
        <td style="display:flex; align-items:center; gap:10px;">
          <span class="avatar" style="width:32px;height:32px;font-size:12px;">${initials(p.name)}</span>
          ${p.name}
        </td>
        <td>${p.gender || '—'}</td>
        <td>${p.bloodGroup || '—'}</td>
        <td>${p.city || '—'}</td>
        <td class="mono" style="font-size:12px;">${p.phone || p.email}</td>
      </tr>
    `).join('');
  }

  // -------------------------------------------------- doctors (patient)
  async function renderDoctors() {
    const doctors = await api('/api/doctors');
    cache.doctors = doctors;
    const grid = document.getElementById('doctorsGrid');
    grid.innerHTML = doctors.map(d => `
      <div class="card doctor-card">
        <div class="top">
          <span class="avatar">${initials(d.name)}</span>
          <div>
            <div class="name">
              ${d.name}
              ${d.verificationStatus === 'verified' ? '<span class="verify-badge verified" title="' + escapeAttr(d.verificationNotes || '') + '">✓ Verified</span>' : ''}
            </div>
            <div class="spec">${d.specialization} · ${d.hospitalName || '—'}</div>
          </div>
        </div>
        <span class="status-pill ${d.isAvailable ? 'online' : ''}">
          <span class="status-dot ${d.isAvailable ? 'online' : ''}"></span>
          ${d.isAvailable ? 'Online now' : 'Offline'}
        </span>
        <div class="details">
          <span>★ ${d.rating}</span>
          <span>${d.experience} yrs exp</span>
          <span>${d.availability.map(a => a.day.slice(0,3)).join(', ') || 'No slots set'}</span>
        </div>
        <div class="footer-row">
          <span class="fee">${money(d.consultationFee)}</span>
          <div style="display:flex; gap:6px;">
            <button class="btn btn-ghost btn-sm" data-msg="${d.doctorId}">Message</button>
            <button class="btn btn-primary btn-sm" data-book="${d.doctorId}">Book</button>
          </div>
        </div>
      </div>
    `).join('');

    $$('[data-book]', grid).forEach(btn => btn.addEventListener('click', () => openBookModal(btn.dataset.book)));
    $$('[data-msg]', grid).forEach(btn => btn.addEventListener('click', async () => {
      try {
        const res = await api(`/api/chat/doctor/${btn.dataset.msg}`, { method: 'POST' });
        showPanel('messages');
        openThread(res.chatId);
      } catch (err) { toast(err.message); }
    }));
  }

  // booking modal
  const bookBackdrop = document.getElementById('bookModalBackdrop');
  function openBookModal(doctorId) {
    document.getElementById('bookDoctorId').value = doctorId;
    document.getElementById('bookDate').value = '';
    document.getElementById('bookSlot').value = '';
    bookBackdrop.classList.add('show');
  }
  document.getElementById('bookCancelBtn').addEventListener('click', () => bookBackdrop.classList.remove('show'));
  document.getElementById('bookForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api('/api/appointments', {
        method: 'POST',
        body: JSON.stringify({
          doctorId: document.getElementById('bookDoctorId').value,
          appointmentDate: document.getElementById('bookDate').value,
          slot: document.getElementById('bookSlot').value,
          mode: document.getElementById('bookMode').value,
        }),
      });
      bookBackdrop.classList.remove('show');
      toast('Appointment requested — awaiting confirmation.');
      showPanel('appointments');
    } catch (err) {
      toast(err.message);
    }
  });

  // -------------------------------------------------- appointments
  async function renderAppointments() {
    const appointments = await api('/api/appointments');
    cache.appointments = appointments;
    const head = document.getElementById('appointmentsHead');
    const tbody = $('#appointmentsTable tbody');

    if (USER.role === 'patient') {
      head.innerHTML = `<th>Doctor</th><th>Date</th><th>Mode</th><th>Status</th><th>Payment</th><th></th>`;
      if (!appointments.length) {
        tbody.innerHTML = `<tr><td colspan="6" class="empty-state">You haven't booked any appointments yet.</td></tr>`;
        return;
      }
      tbody.innerHTML = appointments.map(a => `
        <tr>
          <td>${a.doctorName}<div class="muted" style="font-size:11.5px;">${a.specialization}</div></td>
          <td>${fmtDate(a.appointmentDate)}<div class="muted" style="font-size:11.5px;">${a.slot || ''}</div></td>
          <td style="text-transform:capitalize;">${a.mode}</td>
          <td><span class="badge badge-${a.status}">${a.status}</span></td>
          <td><span class="badge badge-${a.paymentStatus}">${a.paymentStatus}</span></td>
          <td>
            ${a.paymentStatus === 'unpaid' && a.status !== 'cancelled' ? `<button class="btn btn-ghost btn-sm" data-pay="${a.appointmentId}">Pay</button>` : ''}
            ${['pending','confirmed'].includes(a.status) ? `<button class="btn btn-danger btn-sm" data-cancel="${a.appointmentId}">Cancel</button>` : ''}
          </td>
        </tr>
      `).join('');
    } else {
      head.innerHTML = `<th>Patient</th><th>Date</th><th>Mode</th><th>Status</th><th></th>`;
      if (!appointments.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No appointments booked with you yet.</td></tr>`;
        return;
      }
      tbody.innerHTML = appointments.map(a => `
        <tr>
          <td>${a.patientName}</td>
          <td>${fmtDate(a.appointmentDate)}<div class="muted" style="font-size:11.5px;">${a.slot || ''}</div></td>
          <td style="text-transform:capitalize;">${a.mode}</td>
          <td><span class="badge badge-${a.status}">${a.status}</span></td>
          <td>
            ${a.status === 'pending' ? `<button class="btn btn-ghost btn-sm" data-confirm="${a.appointmentId}">Confirm</button>` : ''}
            ${a.status === 'confirmed' ? `<button class="btn btn-ghost btn-sm" data-complete="${a.appointmentId}">Mark complete</button>` : ''}
            ${['pending','confirmed'].includes(a.status) ? `<button class="btn btn-danger btn-sm" data-cancel="${a.appointmentId}">Cancel</button>` : ''}
          </td>
        </tr>
      `).join('');
    }

    $$('[data-pay]', tbody).forEach(b => b.addEventListener('click', () => openPayModal(b.dataset.pay)));
    $$('[data-cancel]', tbody).forEach(b => b.addEventListener('click', () => updateAppt(b.dataset.cancel, { status: 'cancelled', cancellationReason: 'Cancelled from dashboard' })));
    $$('[data-confirm]', tbody).forEach(b => b.addEventListener('click', () => updateAppt(b.dataset.confirm, { status: 'confirmed' })));
    $$('[data-complete]', tbody).forEach(b => b.addEventListener('click', () => updateAppt(b.dataset.complete, { status: 'completed' })));
  }

  async function updateAppt(id, payload) {
    try {
      await api(`/api/appointments/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
      toast('Appointment updated.');
      renderAppointments();
      renderOverview();
    } catch (err) {
      toast(err.message);
    }
  }

  // payment modal
  const payBackdrop = document.getElementById('payModalBackdrop');
  const payMethod = document.getElementById('payMethod');
  const payCardField = document.getElementById('payCardField');
  payMethod.addEventListener('change', () => {
    payCardField.style.display = payMethod.value === 'card' ? 'flex' : 'none';
  });
  function openPayModal(appointmentId) {
    document.getElementById('payAppointmentId').value = appointmentId;
    document.getElementById('payCard').value = '';
    payBackdrop.classList.add('show');
  }
  document.getElementById('payCancelBtn').addEventListener('click', () => payBackdrop.classList.remove('show'));
  document.getElementById('payForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const res = await api('/api/payments', {
        method: 'POST',
        body: JSON.stringify({
          appointmentId: document.getElementById('payAppointmentId').value,
          paymentMethod: payMethod.value,
          cardNumber: document.getElementById('payCard').value.replace(/\s/g, ''),
        }),
      });
      payBackdrop.classList.remove('show');
      toast(res.status === 'success' ? `Payment successful — ${res.transactionId}` : 'Payment failed, please try again.');
      renderAppointments();
    } catch (err) {
      toast(err.message);
    }
  });

  // -------------------------------------------------- messages (doctor chat)
  let activeThreadChatId = null;
  let threadPollTimer = null;

  async function renderMessagesPanel() {
    const chats = await api('/api/chats');
    const list = document.getElementById('messagesList');
    document.getElementById('messagesDot').style.display = chats.length ? 'block' : 'none';

    if (!chats.length) {
      list.innerHTML = `<div class="empty-state">No conversations yet — message a doctor from the Doctors tab.</div>`;
      return;
    }
    list.innerHTML = chats.map(c => `
      <div class="conv-row ${c.chatId === activeThreadChatId ? 'active' : ''}" data-chat="${c.chatId}">
        <span class="avatar" style="width:36px;height:36px;font-size:12px;">${initials(c.otherName)}</span>
        <div class="conv-meta">
          <div class="conv-name">
            ${c.otherName}
            ${c.isAvailable === true ? '<span class="status-dot online"></span>' : ''}
            ${c.isAvailable === false ? '<span class="status-dot"></span>' : ''}
          </div>
          <div class="conv-last">${c.lastMessage || 'Say hello 👋'}</div>
        </div>
      </div>
    `).join('');
    $$('.conv-row', list).forEach(row => row.addEventListener('click', () => openThread(Number(row.dataset.chat))));

    if (activeThreadChatId && chats.some(c => c.chatId === activeThreadChatId)) {
      openThread(activeThreadChatId, true);
    }
  }

  async function openThread(chatId, silent) {
    activeThreadChatId = chatId;
    document.getElementById('threadEmpty').style.display = 'none';
    const view = document.getElementById('threadView');
    view.style.display = 'flex';
    $$('.conv-row', document.getElementById('messagesList')).forEach(r =>
      r.classList.toggle('active', Number(r.dataset.chat) === chatId));

    try {
      const data = await api(`/api/chat/${chatId}`);
      const head = document.getElementById('threadHead');
      const chatRow = $$('.conv-row').find(r => Number(r.dataset.chat) === chatId);
      head.innerHTML = chatRow ? chatRow.querySelector('.conv-name').innerHTML : 'Conversation';
      const body = document.getElementById('threadBody');
      body.innerHTML = data.messages.map(m => `
        <div class="msg ${m.senderType}">${escapeHtml(m.message)}<span class="meta">${fmtTime(m.timestamp)}</span></div>
      `).join('') || `<div class="empty-state">Say hello 👋</div>`;
      body.scrollTop = body.scrollHeight;
    } catch (err) {
      if (!silent) toast(err.message);
    }

    if (threadPollTimer) clearInterval(threadPollTimer);
    threadPollTimer = setInterval(() => {
      if (document.getElementById('panel-messages').classList.contains('active') && activeThreadChatId === chatId) {
        openThread(chatId, true);
      } else {
        clearInterval(threadPollTimer);
      }
    }, 5000);
  }

  document.getElementById('threadForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = document.getElementById('threadInput');
    const text = input.value.trim();
    if (!text || !activeThreadChatId) return;
    input.value = '';
    try {
      await api(`/api/chat/${activeThreadChatId}/messages`, { method: 'POST', body: JSON.stringify({ message: text }) });
      openThread(activeThreadChatId, true);
      renderMessagesPanel();
    } catch (err) {
      toast(err.message);
    }
  });

  // -------------------------------------------------- prescriptions
  async function renderPrescriptions() {
    const prescriptions = await api('/api/prescriptions');
    cache.prescriptions = prescriptions;
    document.getElementById('prescriptionsLede').textContent = USER.role === 'patient'
      ? 'Medicines prescribed by your doctors, ready to send to a pharmacy.'
      : 'Prescriptions you have written.';

    const wrap = document.getElementById('prescriptionsList');
    if (!prescriptions.length) {
      wrap.innerHTML = `<div class="empty-state" style="grid-column:1/-1;">${vitalSVG()}<p>No prescriptions yet.</p></div>`;
    } else {
      wrap.innerHTML = prescriptions.map(rx => `
        <div class="card rx-card">
          <img src="${rx.imagePath}" alt="Prescription ${rx.prescriptionId}" data-view="${rx.imagePath}">
          <div>
            <div style="font-weight:600; font-size:13.5px;">
              ${USER.role === 'patient' ? `Dr. ${rx.doctorName} · ${rx.specialization}` : rx.patientName}
            </div>
            <div class="meds-summary">${rx.medicines.map(m => m.name).join(', ')}</div>
            <div class="muted" style="font-size:11.5px; margin-top:2px;">${fmtDate(rx.createdAt)}</div>
          </div>
          ${USER.role === 'patient' ? `<button class="btn btn-primary btn-sm" data-order="${rx.prescriptionId}">Order medicines</button>` : ''}
        </div>
      `).join('');
    }

    $$('[data-view]', wrap).forEach(img => img.addEventListener('click', () => {
      document.getElementById('rxImagePreview').src = img.dataset.view;
      document.getElementById('rxImageBackdrop').classList.add('show');
    }));
    $$('[data-order]', wrap).forEach(btn => btn.addEventListener('click', () => openOrderModal(btn.dataset.order)));

    const addBtn = document.getElementById('addPrescriptionBtn');
    if (USER.role === 'doctor') {
      addBtn.style.display = 'inline-flex';
      const patients = cache.patients || await api('/api/patients');
      cache.patients = patients;
      document.getElementById('rxPatient').innerHTML = patients.map(p => `<option value="${p.patientId}">${p.name}</option>`).join('');
      const pharmacies = await api('/api/pharmacies?mine=1');
      const allPharmacies = await api('/api/pharmacies');
      const sel = document.getElementById('rxPharmacy');
      const mineOptions = pharmacies.map(p => `<option value="${p.pharmacyId}">${p.pharmacyName} (my pharmacy)</option>`).join('');
      const otherOptions = allPharmacies.filter(p => !pharmacies.some(m => m.pharmacyId === p.pharmacyId))
        .map(p => `<option value="${p.pharmacyId}">${p.pharmacyName}</option>`).join('');
      sel.innerHTML = `<option value="">Let the patient choose</option>${mineOptions}${otherOptions}`;
    }
  }
  document.getElementById('rxImageCloseBtn').addEventListener('click', () => document.getElementById('rxImageBackdrop').classList.remove('show'));

  // medicine rows builder
  function addMedicineRow(values = {}) {
    const wrap = document.getElementById('rxMedicines');
    const row = document.createElement('div');
    row.className = 'rx-med-row';
    row.innerHTML = `
      <input placeholder="Medicine" class="med-name" value="${values.name || ''}">
      <input placeholder="Dosage" class="med-dosage" value="${values.dosage || ''}">
      <input placeholder="Frequency" class="med-frequency" value="${values.frequency || ''}">
      <input placeholder="Duration" class="med-duration" value="${values.duration || ''}">
      <button type="button" title="Remove">✕</button>
    `;
    row.querySelector('button').addEventListener('click', () => row.remove());
    wrap.appendChild(row);
  }
  document.getElementById('rxAddMedicine').addEventListener('click', () => addMedicineRow());

  const rxBackdrop = document.getElementById('rxModalBackdrop');
  const addPrescriptionBtn = document.getElementById('addPrescriptionBtn');
  if (addPrescriptionBtn) addPrescriptionBtn.addEventListener('click', () => {
    document.getElementById('rxMedicines').innerHTML = '';
    addMedicineRow();
    document.getElementById('rxNotes').value = '';
    rxBackdrop.classList.add('show');
  });
  document.getElementById('rxCancelBtn').addEventListener('click', () => rxBackdrop.classList.remove('show'));
  document.getElementById('rxForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const medicines = $$('.rx-med-row', document.getElementById('rxMedicines')).map(row => ({
      name: row.querySelector('.med-name').value.trim(),
      dosage: row.querySelector('.med-dosage').value.trim(),
      frequency: row.querySelector('.med-frequency').value.trim(),
      duration: row.querySelector('.med-duration').value.trim(),
    })).filter(m => m.name);
    if (!medicines.length) { toast('Add at least one medicine.'); return; }
    try {
      await api('/api/prescriptions', {
        method: 'POST',
        body: JSON.stringify({
          patientId: document.getElementById('rxPatient').value,
          medicines,
          notes: document.getElementById('rxNotes').value,
          pharmacyId: document.getElementById('rxPharmacy').value || null,
        }),
      });
      rxBackdrop.classList.remove('show');
      toast('Prescription generated.');
      renderPrescriptions();
    } catch (err) { toast(err.message); }
  });

  // order-from-pharmacy modal (patient)
  const orderBackdrop = document.getElementById('orderModalBackdrop');
  async function openOrderModal(prescriptionId) {
    document.getElementById('orderPrescriptionId').value = prescriptionId;
    const pharmacies = await api('/api/pharmacies');
    const rx = (cache.prescriptions || []).find(r => String(r.prescriptionId) === String(prescriptionId));
    const suggestedId = rx ? rx.suggestedPharmacyId : null;
    const sel = document.getElementById('orderPharmacy');
    sel.innerHTML = pharmacies.map(p => `
      <option value="${p.pharmacyId}" ${p.pharmacyId === suggestedId ? 'selected' : ''}>
        ${p.pharmacyName}${p.pharmacyId === suggestedId ? ' (doctor suggested)' : ''}
      </option>
    `).join('');
    orderBackdrop.classList.add('show');
  }
  document.getElementById('orderCancelBtn').addEventListener('click', () => orderBackdrop.classList.remove('show'));
  document.getElementById('orderForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api(`/api/prescriptions/${document.getElementById('orderPrescriptionId').value}/order`, {
        method: 'POST',
        body: JSON.stringify({ pharmacyId: document.getElementById('orderPharmacy').value }),
      });
      orderBackdrop.classList.remove('show');
      toast('Order placed with the pharmacy.');
    } catch (err) { toast(err.message); }
  });

  // -------------------------------------------------- records
  async function renderRecords() {
    const records = await api('/api/records');
    cache.records = records;
    const wrap = document.getElementById('recordsList');
    if (!records.length) {
      wrap.innerHTML = `<div class="empty-state" style="grid-column:1/-1;">${vitalSVG()}<p>No records yet.</p></div>`;
    } else {
      wrap.innerHTML = records.map(r => `
        <div class="card" style="padding:16px;">
          <div style="font-weight:600; font-size:14.5px;">${r.diagnosis || 'General consult'}</div>
          <div class="muted" style="font-size:12px; margin:2px 0 10px;">
            ${USER.role === 'patient' ? `Dr. ${r.doctorName} · ${r.specialization}` : r.patientName} · ${fmtDate(r.createdAt)}
          </div>
          ${r.prescription ? `<div style="font-size:13px; margin-bottom:6px;"><strong>Rx:</strong> ${r.prescription}</div>` : ''}
          ${r.notes ? `<div style="font-size:13px; color:var(--ink-soft);">${r.notes}</div>` : ''}
          ${r.followUpDate ? `<div class="badge badge-pending" style="margin-top:10px;">Follow-up ${fmtDate(r.followUpDate)}</div>` : ''}
        </div>
      `).join('');
    }

    const addBtn = document.getElementById('addRecordBtn');
    if (USER.role === 'doctor') {
      addBtn.style.display = 'inline-flex';
      const patients = cache.patients || await api('/api/patients');
      cache.patients = patients;
      const select = document.getElementById('recordPatient');
      select.innerHTML = patients.map(p => `<option value="${p.patientId}">${p.name}</option>`).join('');
    }
  }

  const recordBackdrop = document.getElementById('recordModalBackdrop');
  const addRecordBtn = document.getElementById('addRecordBtn');
  if (addRecordBtn) addRecordBtn.addEventListener('click', () => recordBackdrop.classList.add('show'));
  document.getElementById('recordCancelBtn').addEventListener('click', () => recordBackdrop.classList.remove('show'));
  document.getElementById('recordForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api('/api/records', {
        method: 'POST',
        body: JSON.stringify({
          patientId: document.getElementById('recordPatient').value,
          diagnosis: document.getElementById('recordDiagnosis').value,
          prescription: document.getElementById('recordPrescription').value,
          notes: document.getElementById('recordNotes').value,
          followUpDate: document.getElementById('recordFollowUp').value,
        }),
      });
      recordBackdrop.classList.remove('show');
      toast('Record saved.');
      document.getElementById('recordForm').reset();
      renderRecords();
    } catch (err) {
      toast(err.message);
    }
  });

  // -------------------------------------------------- pharmacy approval requests (doctor)
  async function renderPharmacyRequests() {
    const requests = await api('/api/pharmacy/requests');
    document.getElementById('pharmacyReqDot').style.display = requests.length ? 'block' : 'none';
    const wrap = document.getElementById('pharmacyRequestsList');
    if (!requests.length) {
      wrap.innerHTML = `<div class="empty-state" style="grid-column:1/-1;">${vitalSVG()}<p>No pending pharmacy requests.</p></div>`;
      return;
    }
    wrap.innerHTML = requests.map(p => `
      <div class="card" style="padding:16px;">
        <div style="font-weight:600; font-size:14.5px;">${p.pharmacyName}</div>
        <div class="muted" style="font-size:12.5px; margin:4px 0 10px;">
          License ${p.licenseNumber || '—'} · ${p.address || 'No address on file'}<br>
          ${p.email} · ${p.phone || ''}
        </div>
        <div style="display:flex; gap:8px;">
          <button class="btn btn-primary btn-sm" data-approve="${p.pharmacyId}">Approve</button>
          <button class="btn btn-danger btn-sm" data-reject="${p.pharmacyId}">Reject</button>
        </div>
      </div>
    `).join('');
    $$('[data-approve]', wrap).forEach(b => b.addEventListener('click', () => reviewPharmacy(b.dataset.approve, true)));
    $$('[data-reject]', wrap).forEach(b => b.addEventListener('click', () => reviewPharmacy(b.dataset.reject, false)));
  }
  async function reviewPharmacy(pharmacyId, approve) {
    try {
      await api(`/api/pharmacy/requests/${pharmacyId}`, { method: 'PUT', body: JSON.stringify({ approve }) });
      toast(approve ? 'Pharmacy approved.' : 'Pharmacy request rejected.');
      renderPharmacyRequests();
    } catch (err) { toast(err.message); }
  }

  // -------------------------------------------------- orders (pharmacy)
  const ORDER_STEPS = ['placed', 'processing', 'ready', 'fulfilled'];
  async function renderOrders() {
    const orders = await api('/api/orders');
    const wrap = document.getElementById('ordersList');
    if (!orders.length) {
      wrap.innerHTML = `<div class="empty-state" style="grid-column:1/-1;">${vitalSVG()}<p>No orders yet.</p></div>`;
      return;
    }
    wrap.innerHTML = orders.map(o => {
      const nextIdx = ORDER_STEPS.indexOf(o.status) + 1;
      const nextStatus = ORDER_STEPS[nextIdx];
      return `
      <div class="card" style="padding:16px;">
        <div style="display:flex; justify-content:space-between; align-items:flex-start;">
          <div style="font-weight:600; font-size:14.5px;">${o.patientName}</div>
          <span class="badge badge-${o.status === 'fulfilled' ? 'completed' : o.status === 'cancelled' ? 'cancelled' : 'pending'}">${o.status}</span>
        </div>
        <div class="meds-summary" style="margin:6px 0;">${o.medicines.map(m => m.name).join(', ')}</div>
        <img src="${o.imagePath}" alt="Prescription" style="width:100%; border-radius:8px; border:1px solid var(--border); cursor:pointer; margin-bottom:10px;" data-view="${o.imagePath}">
        <div style="display:flex; gap:8px;">
          ${nextStatus && o.status !== 'cancelled' ? `<button class="btn btn-primary btn-sm" data-next="${o.orderId}" data-status="${nextStatus}">Mark ${nextStatus}</button>` : ''}
          ${!['fulfilled','cancelled'].includes(o.status) ? `<button class="btn btn-danger btn-sm" data-cancel-order="${o.orderId}">Cancel</button>` : ''}
        </div>
      </div>`;
    }).join('');

    $$('[data-view]', wrap).forEach(img => img.addEventListener('click', () => {
      document.getElementById('rxImagePreview').src = img.dataset.view;
      document.getElementById('rxImageBackdrop').classList.add('show');
    }));
    $$('[data-next]', wrap).forEach(btn => btn.addEventListener('click', () => updateOrder(btn.dataset.next, btn.dataset.status)));
    $$('[data-cancel-order]', wrap).forEach(btn => btn.addEventListener('click', () => updateOrder(btn.dataset.cancelOrder, 'cancelled')));
  }
  async function updateOrder(orderId, status) {
    try {
      await api(`/api/orders/${orderId}`, { method: 'PUT', body: JSON.stringify({ status }) });
      toast('Order updated.');
      renderOrders();
    } catch (err) { toast(err.message); }
  }

  // -------------------------------------------------- profile
  async function renderProfile() {
    const data = await api('/api/me');
    cache.me = data;
    const form = document.getElementById('profileForm');
    const p = data.profile || {};

    if (USER.role === 'patient') {
      form.innerHTML = `
        <div class="grid-2" style="display:grid; grid-template-columns:1fr 1fr; gap:0 12px;">
          <div class="field"><label>Blood group</label><input id="pf_bloodGroup" value="${p.bloodGroup || ''}"></div>
          <div class="field"><label>Gender</label><input id="pf_gender" value="${p.gender || ''}"></div>
          <div class="field"><label>Height (cm)</label><input id="pf_height" type="number" value="${p.height || ''}"></div>
          <div class="field"><label>Weight (kg)</label><input id="pf_weight" type="number" value="${p.weight || ''}"></div>
        </div>
        <div class="field"><label>Allergies</label><input id="pf_allergies" value="${p.allergies || ''}"></div>
        <div class="field"><label>Chronic conditions</label><input id="pf_chronicDiseases" value="${p.chronicDiseases || ''}"></div>
        <div class="grid-2" style="display:grid; grid-template-columns:1fr 1fr; gap:0 12px;">
          <div class="field"><label>Emergency contact name</label><input id="pf_emergencyContactName" value="${p.emergencyContactName || ''}"></div>
          <div class="field"><label>Emergency contact phone</label><input id="pf_emergencyContactPhone" value="${p.emergencyContactPhone || ''}"></div>
        </div>
        <div class="field"><label>City</label><input id="pf_city" value="${p.city || ''}"></div>
        <button class="btn btn-primary btn-sm" type="submit">Save changes</button>
      `;
      form.onsubmit = async (e) => {
        e.preventDefault();
        try {
          await api(`/api/patients/${USER.userId}`, {
            method: 'PUT',
            body: JSON.stringify({
              bloodGroup: val('pf_bloodGroup'), gender: val('pf_gender'),
              height: val('pf_height'), weight: val('pf_weight'),
              allergies: val('pf_allergies'), chronicDiseases: val('pf_chronicDiseases'),
              emergencyContactName: val('pf_emergencyContactName'),
              emergencyContactPhone: val('pf_emergencyContactPhone'),
              city: val('pf_city'),
            }),
          });
          toast('Profile updated.');
        } catch (err) { toast(err.message); }
      };
    } else if (USER.role === 'doctor') {
      const statusLabel = { verified: '✓ Verified', pending: 'Pending review', rejected: 'Not verified', unverified: 'Not uploaded yet' };
      form.innerHTML = `
        <div class="field"><label>Specialization</label><input value="${p.specialization || ''}" disabled></div>
        <div class="field"><label>Hospital</label><input value="${p.hospitalName || ''}" disabled></div>
        <div class="field"><label>Bio</label><textarea disabled>${p.bio || ''}</textarea></div>
        <p class="muted" style="font-size:12.5px; margin-bottom:16px;">Doctor profile editing coming soon — use the availability toggle in the sidebar to control your online status.</p>

        <div class="field">
          <label>Medical certificate</label>
          <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
            <span class="verify-badge ${p.verificationStatus || 'unverified'}">${statusLabel[p.verificationStatus || 'unverified']}</span>
            ${p.certificateImage ? `<img src="${p.certificateImage}" alt="Certificate" style="width:70px; height:70px; object-fit:cover; border-radius:8px; border:1px solid var(--border); cursor:pointer;" id="certThumb">` : ''}
          </div>
          ${p.verificationNotes ? `<p class="muted" style="font-size:12px; margin-top:8px;">${p.verificationNotes}</p>` : ''}
          <label class="btn btn-ghost btn-sm" for="certificateInput" style="cursor:pointer; margin-top:10px; display:inline-flex;">
            ${p.certificateImage ? 'Re-upload certificate' : 'Upload certificate'}
          </label>
          <input type="file" id="certificateInput" accept="image/*" class="visually-hidden">
          <p class="muted" style="font-size:11.5px; margin-top:6px;">Our system automatically reads the certificate and matches it against your name and recognized medical qualifications — this is an automated screening step, not a legal credential check.</p>
        </div>
      `;
      const certThumb = document.getElementById('certThumb');
      if (certThumb) certThumb.addEventListener('click', () => {
        document.getElementById('rxImagePreview').src = certThumb.src;
        document.getElementById('rxImageBackdrop').classList.add('show');
      });
      document.getElementById('certificateInput').addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const fd = new FormData();
        fd.append('certificate', file);
        toast('Scanning certificate…');
        try {
          const res = await fetch(`/api/doctors/${USER.userId}/certificate`, { method: 'POST', body: fd });
          const data = await res.json();
          if (!res.ok) throw new Error(data.error);
          toast(data.verificationStatus === 'verified' ? 'Certificate verified automatically.' : 'Certificate uploaded — ' + data.verificationStatus + '.');
          renderProfile();
        } catch (err) { toast(err.message); }
      });
    } else {
      form.innerHTML = `
        <div class="field"><label>Pharmacy name</label><input value="${p.pharmacyName || ''}" disabled></div>
        <div class="field"><label>License number</label><input value="${p.licenseNumber || ''}" disabled></div>
        <div class="field"><label>Address</label><input value="${p.address || ''}" disabled></div>
        <div class="field"><label>Approval status</label><input value="${p.approvalStatus || ''}" disabled style="text-transform:capitalize;"></div>
      `;
    }
  }
  function val(id) { return document.getElementById(id).value; }

  document.getElementById('profileImageInput').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('image', file);
    try {
      const res = await fetch('/api/profile/upload', { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      toast('Photo updated.');
      document.getElementById('profileAvatar').outerHTML = `<img src="${data.profileImage}" id="profileAvatar" style="width:64px;height:64px;border-radius:50%;object-fit:cover;">`;
      document.getElementById('railAvatar').outerHTML = `<img src="${data.profileImage}" id="railAvatar" style="width:34px;height:34px;border-radius:50%;object-fit:cover;">`;
    } catch (err) {
      toast(err.message);
    }
  });

  // -------------------------------------------------- kick off
  renderOverview();

  // Bridge so the floating AI assistant (chatbot.js) can act on doctor
  // suggestions without re-implementing booking/messaging logic.
  window.AarogyaBridge = {
    messageDoctor: async (doctorId) => {
      try {
        const res = await api(`/api/chat/doctor/${doctorId}`, { method: 'POST' });
        showPanel('messages');
        openThread(res.chatId);
      } catch (err) { toast(err.message); }
    },
    bookDoctor: (doctorId) => openBookModal(doctorId),
  };
}
