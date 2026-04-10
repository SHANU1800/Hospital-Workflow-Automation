/* ═══════════════════════════════════════════════════════
   Hospital Workflow Automation — Dashboard Application
   ═══════════════════════════════════════════════════════ */

const API = '';  // Same origin
const TOKEN_STORAGE_KEY = 'hospital_auth_token';
const PATIENT_CONTEXT_KEY = 'patient_portal_patient_id';

// ─── State ────────────────────────────────────────────
let currentPage = 'dashboard';
let executionLogs = [];
let authToken = null;
let currentUser = null;
let authMode = 'signin';
let bookingState = {
    recommendedDepartment: null,
    selectedDoctorId: null,
    selectedSlotId: null,
    selectedAppointmentId: null,
    voiceRecognition: null,
    isListening: false,
};
let admitPatientsCache = [];
let doctorCalendarState = {
    monthCursor: new Date(new Date().getFullYear(), new Date().getMonth(), 1),
    appointments: [],
    selectedDate: null,
};

const roleAccess = {
    super_admin: {
        pages: ['dashboard', 'admit', 'events', 'patients', 'beds', 'billing', 'insurance', 'reports', 'logs', 'agents', 'tools'],
        canQuickActions: true,
    },
    staff: {
        pages: ['dashboard', 'admit', 'events', 'patients', 'beds', 'billing', 'insurance', 'reports', 'agents', 'tools'],
        canQuickActions: true,
    },
    doctor: {
        pages: ['dashboard', 'events', 'appointments', 'agents', 'tools'],
        canQuickActions: false,
    },
    auditor: {
        pages: ['dashboard', 'logs', 'agents', 'tools'],
        canQuickActions: false,
    },
    patient: {
        pages: ['appointments', 'schedule', 'mybilling'],
        canQuickActions: false,
    },
};

// ─── Initialization ───────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    setupNavigation();
    setupClock();
    const authenticated = await ensureAuthenticated();
    if (!authenticated) return;

    postLoginBootstrap();
});

function postLoginBootstrap() {
    loadHealthData();

    if (!currentUser) return;

    if (currentUser.role === 'patient') {
        navigateTo('appointments');
        return;
    }

    loadDashboard();
    loadAgentStatus();
}

async function apiFetch(url, options = {}) {
    const headers = {
        ...(options.headers || {}),
    };

    if (authToken) {
        headers.Authorization = `Bearer ${authToken}`;
    }

    const response = await fetch(url, { ...options, headers });

    if (response.status === 401 || response.status === 403) {
        forceLogout('Your session has expired or your role is not allowed. Please sign in again.');
    }

    return response;
}

async function ensureAuthenticated() {
    authToken = localStorage.getItem(TOKEN_STORAGE_KEY);

    if (!authToken) {
        showAuthOverlay(true);
        setAuthMode('signin');
        return false;
    }

    try {
        await loadCurrentUser();
        showAuthOverlay(false);
        return true;
    } catch (_) {
        forceLogout('Please sign in to continue.');
        return false;
    }
}

async function loadCurrentUser() {
    const res = await apiFetch(`${API}/me`);
    if (!res.ok) {
        throw new Error('Failed to load current user');
    }

    currentUser = await res.json();
    applyRoleUI();
    renderAuthUser();
}

function renderAuthUser() {
    const controls = document.getElementById('auth-controls');
    const label = document.getElementById('auth-user-label');

    if (!currentUser) {
        controls.style.display = 'none';
        label.textContent = '';
        return;
    }

    controls.style.display = 'inline-flex';
    label.textContent = `${currentUser.username} (${currentUser.role})`;
}

function showAuthOverlay(show) {
    document.getElementById('auth-overlay').classList.toggle('active', show);
}

function setAuthMode(mode) {
    authMode = mode === 'signup' ? 'signup' : 'signin';

    const isSignup = authMode === 'signup';
    const title = document.getElementById('auth-title');
    const subtitle = document.getElementById('auth-subtitle');
    const signinBtn = document.getElementById('auth-mode-signin');
    const signupBtn = document.getElementById('auth-mode-signup');
    const loginForm = document.getElementById('login-form');
    const signupForm = document.getElementById('signup-form');

    title.textContent = isSignup ? 'Sign Up' : 'Sign In';
    subtitle.textContent = isSignup
        ? 'Create a patient account to use booking and billing self-service.'
        : 'Authenticate to access workflow actions and logs.';

    signinBtn.classList.toggle('active', !isSignup);
    signupBtn.classList.toggle('active', isSignup);

    loginForm.classList.toggle('auth-form-hidden', isSignup);
    signupForm.classList.toggle('auth-form-hidden', !isSignup);

    document.getElementById('auth-error-login').textContent = '';
    document.getElementById('auth-error-signup').textContent = '';
}

function forceLogout(message = '') {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    authToken = null;
    currentUser = null;
    renderAuthUser();
    showAuthOverlay(true);
    setAuthMode('signin');
    if (message) {
        document.getElementById('auth-error-login').textContent = message;
    }
}

async function login(event) {
    event.preventDefault();
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const loginBtn = document.getElementById('btn-login');
    const errorEl = document.getElementById('auth-error-login');

    errorEl.textContent = '';
    loginBtn.disabled = true;

    try {
        const res = await fetch(`${API}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });

        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.detail || 'Invalid credentials');
        }

        authToken = data.access_token;
        localStorage.setItem(TOKEN_STORAGE_KEY, authToken);

        await loadCurrentUser();
        showAuthOverlay(false);
        postLoginBootstrap();
    } catch (e) {
        errorEl.textContent = e.message || 'Sign-in failed';
    } finally {
        loginBtn.disabled = false;
    }
}

async function signup(event) {
    event.preventDefault();

    const username = document.getElementById('signup-username').value.trim();
    const email = document.getElementById('signup-email').value.trim();
    const password = document.getElementById('signup-password').value;
    const confirmPassword = document.getElementById('signup-confirm-password').value;
    const signupBtn = document.getElementById('btn-signup');
    const errorEl = document.getElementById('auth-error-signup');

    errorEl.textContent = '';

    if (password !== confirmPassword) {
        errorEl.textContent = 'Passwords do not match';
        return;
    }

    signupBtn.disabled = true;

    try {
        const res = await fetch(`${API}/signup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, email, password }),
        });

        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.detail || 'Signup failed');
        }

        authToken = data.access_token;
        localStorage.setItem(TOKEN_STORAGE_KEY, authToken);

        await loadCurrentUser();
        showAuthOverlay(false);
        postLoginBootstrap();
        showToast('Account created successfully', 'success');
    } catch (e) {
        errorEl.textContent = e.message || 'Signup failed';
    } finally {
        signupBtn.disabled = false;
    }
}

function logout() {
    forceLogout('You have been signed out.');
}

function fillDemoCredentials(username, password) {
    setAuthMode('signin');
    document.getElementById('login-username').value = username;
    document.getElementById('login-password').value = password;
    document.getElementById('auth-error-login').textContent = '';
}

function applyRoleUI() {
    const role = currentUser?.role;
    const config = roleAccess[role] || roleAccess.auditor;
    const allowedPages = new Set(config.pages);

    document.querySelectorAll('.nav-item').forEach(item => {
        const page = item.dataset.page;
        const allowed = allowedPages.has(page);
        item.classList.toggle('role-hidden', !allowed);
    });

    document.querySelectorAll('.page').forEach(section => {
        const page = section.id.replace('page-', '');
        const allowed = allowedPages.has(page);
        section.classList.toggle('role-hidden', !allowed);
    });

    const quickActionsCard = document.getElementById('quick-actions-card');
    if (quickActionsCard) {
        quickActionsCard.classList.toggle('role-hidden', !config.canQuickActions);
    }

    const patientBookingCard = document.getElementById('patient-booking-card');
    const doctorDashboardCard = document.getElementById('doctor-dashboard-card');
    if (patientBookingCard) {
        const canUsePatientBooking = ['patient', 'staff', 'super_admin'].includes(role);
        patientBookingCard.classList.toggle('role-hidden', !canUsePatientBooking);
    }
    if (doctorDashboardCard) {
        doctorDashboardCard.classList.toggle('role-hidden', role === 'patient');
    }

    if (!allowedPages.has(currentPage)) {
        const firstAllowed = config.pages[0] || 'dashboard';
        navigateTo(firstAllowed);
    }
}

// ─── Navigation ───────────────────────────────────────
function setupNavigation() {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const page = item.dataset.page;
            navigateTo(page);
        });
    });

    // Mobile menu toggle
    const toggle = document.getElementById('menu-toggle');
    if (toggle) {
        toggle.addEventListener('click', () => {
            document.getElementById('sidebar').classList.toggle('open');
        });
    }
}

function navigateTo(page) {
    if (currentUser) {
        const allowed = roleAccess[currentUser.role]?.pages || [];
        if (!allowed.includes(page)) {
            showToast('You do not have permission to access this page', 'error');
            return;
        }
    }

    // Update nav
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelector(`[data-page="${page}"]`).classList.add('active');

    // Update pages
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(`page-${page}`).classList.add('active');

    // Update title
    const titles = {
        dashboard: 'Dashboard',
        admit: 'Admit Patient',
        events: 'Trigger Event',
        appointments: 'Appointments',
        schedule: 'My Schedule',
        mybilling: 'My Billing',
        patients: 'Patients',
        beds: 'Beds',
        billing: 'Billing',
        insurance: 'Insurance',
        reports: 'Reports',
        logs: 'Execution Logs',
        agents: 'Agent Registry',
        tools: 'MCP Tools',
    };
    document.getElementById('page-title').textContent = titles[page] || page;

    // Load page data
    if (page === 'logs') loadLogs();
    if (page === 'agents') loadAgents();
    if (page === 'tools') loadTools();
    if (page === 'dashboard') loadDashboard();
    if (page === 'appointments') initializeAppointmentsPage();
    if (page === 'schedule') initializeSchedulePage();
    if (page === 'mybilling') initializeMyBillingPage();
    if (page === 'admit') loadAdmitPatients();
    if (page === 'patients') loadStaffPatients();
    if (page === 'beds') loadStaffBeds();
    if (page === 'billing') loadStaffBillingCases();
    if (page === 'insurance') loadStaffInsuranceClaims();
    if (page === 'reports') loadStaffReportsSummary();

    currentPage = page;

    // Close mobile sidebar
    document.getElementById('sidebar').classList.remove('open');
}

// ─── Clock ────────────────────────────────────────────
function setupClock() {
    const update = () => {
        const now = new Date();
        document.getElementById('header-time').textContent =
            now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    };
    update();
    setInterval(update, 1000);
}

// ─── Health Data ──────────────────────────────────────
async function loadHealthData() {
    try {
        const res = await apiFetch(`${API}/health`);
        if (!res.ok) throw new Error('Health request failed');
        const data = await res.json();
        document.getElementById('badge-agents').textContent = data.agents;
        document.getElementById('badge-tools').textContent = data.tools;
        document.getElementById('badge-rules').textContent = data.rules;

        const status = document.getElementById('system-status');
        if (data.status === 'healthy') {
            status.innerHTML = '<div class="status-dot"></div><span>System Online</span>';
        }
    } catch (e) {
        console.error('Health check failed:', e);
        const status = document.getElementById('system-status');
        status.innerHTML = '<div class="status-dot" style="background:var(--accent-danger)"></div><span>Offline</span>';
    }
}

// ─── Dashboard ────────────────────────────────────────
async function loadDashboard() {
    try {
        const res = await apiFetch(`${API}/execution_logs`);
        if (!res.ok) throw new Error('Dashboard request failed');
        const data = await res.json();
        executionLogs = data.executions || [];
        updateDashboardStats();
        updateActivityList();
    } catch (e) {
        console.error('Failed to load dashboard:', e);
    }
}

function updateDashboardStats() {
    const total = executionLogs.length;
    let completed = 0;
    let failed = 0;
    let totalTime = 0;

    executionLogs.forEach(log => {
        if (log.steps) {
            log.steps.forEach(step => {
                if (step.status === 'completed') completed++;
                if (step.status === 'failed') failed++;
            });
        }
        if (log.total_duration_ms) totalTime += log.total_duration_ms;
    });

    document.getElementById('stat-workflows').textContent = total;
    document.getElementById('stat-completed').textContent = completed;
    document.getElementById('stat-failures').textContent = failed;
    document.getElementById('stat-avg-time').textContent =
        total > 0 ? `${(totalTime / total).toFixed(0)}ms` : '0ms';
}

function updateActivityList() {
    const container = document.getElementById('activity-list');
    if (executionLogs.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                <p>No workflow executions yet</p>
                <span>Admit a patient or trigger an event to get started</span>
            </div>`;
        return;
    }

    const items = executionLogs.slice().reverse().slice(0, 10).map(log => {
        const stepCount = log.steps ? log.steps.length : 0;
        const duration = log.total_duration_ms ? `${log.total_duration_ms.toFixed(1)}ms` : '—';
        const time = log.started_at ? new Date(log.started_at).toLocaleTimeString() : '';
        return `
            <div class="activity-item">
                <div class="activity-dot ${log.status}"></div>
                <div class="activity-info">
                    <div class="activity-event">${formatEventName(log.event)}</div>
                    <div class="activity-meta">${stepCount} steps · ${time}</div>
                </div>
                <div class="activity-duration">${duration}</div>
            </div>`;
    }).join('');

    container.innerHTML = items;
}

// ─── Agent Status (dashboard widget) ──────────────────
async function loadAgentStatus() {
    try {
        const res = await apiFetch(`${API}/agents`);
        if (!res.ok) throw new Error('Agents request failed');
        const data = await res.json();
        const container = document.getElementById('agent-status-list');

        const agentColors = { DataAgent: 'data', SchedulerAgent: 'scheduler', AlertAgent: 'alert' };
        const agentLetters = { DataAgent: 'D', SchedulerAgent: 'S', AlertAgent: 'A' };

        container.innerHTML = (data.agents || []).map(agent => `
            <div class="agent-status-item">
                <div class="agent-badge ${agentColors[agent.name] || ''}">${agentLetters[agent.name] || '?'}</div>
                <div class="agent-status-info">
                    <div class="agent-status-name">${agent.name}</div>
                    <div class="agent-status-caps">${(agent.capabilities || []).join(', ')}</div>
                </div>
                <div class="agent-status-dot"></div>
            </div>`).join('');
    } catch (e) {
        console.error('Failed to load agents:', e);
    }
}

// ─── Patient Selection ────────────────────────────────
function selectPatient(id) {
    const numericId = Number(id);
    if (!Number.isFinite(numericId) || numericId < 1) return;

    document.getElementById('admit-patient-id').value = id;
    document.querySelectorAll('.patient-chip').forEach(c => c.classList.remove('selected'));
    const chip = document.querySelector(`.patient-chip[data-patient-id="${numericId}"]`);
    if (chip) chip.classList.add('selected');
}

async function loadAdmitPatients() {
    const container = document.getElementById('patient-quick-select');
    const hint = document.getElementById('admit-patient-hint');
    const input = document.getElementById('admit-patient-id');
    if (!container || !hint || !input) return;

    try {
        const res = await apiFetch(`${API}/patients`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to load patients');

        admitPatientsCache = Array.isArray(data) ? data : [];

        if (!admitPatientsCache.length) {
            container.innerHTML = '<div class="empty-state"><p>No patients found in database</p><span>Create patients first, then admit workflow can run.</span></div>';
            hint.textContent = 'No patient records found in database.';
            input.value = '';
            return;
        }

        container.innerHTML = admitPatientsCache.map(p => `
            <div class="patient-chip" data-patient-id="${p.id}" onclick="selectPatient(${p.id})">
                <span class="chip-id">${p.id}</span>
                <span class="chip-name">${escapeHtml(p.name)}</span>
                <span class="chip-dept">${escapeHtml((p.department || '').toUpperCase())}</span>
            </div>
        `).join('');

        hint.textContent = `Loaded ${admitPatientsCache.length} patient(s) from database.`;

        const currentValue = parseInt(input.value, 10);
        const hasCurrent = admitPatientsCache.some(p => p.id === currentValue);
        if (!hasCurrent) {
            input.value = admitPatientsCache[0].id;
            selectPatient(admitPatientsCache[0].id);
        } else {
            selectPatient(currentValue);
        }
    } catch (e) {
        container.innerHTML = '<div class="empty-state"><p>Unable to load patients</p></div>';
        hint.textContent = 'Failed to load patients from database.';
        showToast(`Error: ${e.message}`, 'error');
    }
}

// ─── Admit Patient ────────────────────────────────────
async function admitPatient() {
    const patientId = parseInt(document.getElementById('admit-patient-id').value);
    if (!patientId || patientId < 1) {
        showToast('Please enter a valid patient ID', 'error');
        return;
    }

    const btn = document.getElementById('btn-admit');
    btn.disabled = true;
    showLoading(true);

    try {
        const res = await apiFetch(`${API}/admit_patient`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ patient_id: patientId }),
        });
        const data = await res.json();

        if (!res.ok) throw new Error(data.detail || 'Request failed');

        showToast(`Workflow completed — ${data.summary?.total_steps || 0} steps executed`, 'success');
        renderWorkflowResult('admit', data);
        loadDashboard();
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    } finally {
        btn.disabled = false;
        showLoading(false);
    }
}

// ─── Trigger Event ────────────────────────────────────
function setEvent(eventType, patientId) {
    document.getElementById('event-type').value = eventType;
    document.getElementById('event-patient-id').value = patientId;
    document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
    event.currentTarget.classList.add('active');
}

async function triggerEvent() {
    const eventType = document.getElementById('event-type').value.trim();
    const patientId = parseInt(document.getElementById('event-patient-id').value);

    if (!eventType) {
        showToast('Please enter an event type', 'error');
        return;
    }

    const btn = document.getElementById('btn-trigger');
    btn.disabled = true;
    showLoading(true);

    try {
        const res = await apiFetch(`${API}/trigger_event`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                event: eventType,
                context: { patient_id: patientId || 101 },
            }),
        });
        const data = await res.json();

        if (!res.ok) throw new Error(data.detail || 'Request failed');

        showToast(`Event "${eventType}" executed — ${data.summary?.total_steps || 0} steps`, 'success');
        renderWorkflowResult('event', data);
        loadDashboard();
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    } finally {
        btn.disabled = false;
        showLoading(false);
    }
}

// ─── Render Workflow Result (Timeline) ────────────────
function renderWorkflowResult(prefix, data) {
    const panel = document.getElementById(`${prefix}-result`);
    const statusEl = document.getElementById(`${prefix}-status`);
    const timeline = document.getElementById(`${prefix}-timeline`);

    panel.style.display = '';

    // Status badge
    statusEl.className = `result-status ${data.status}`;
    statusEl.innerHTML = getStatusBadgeContent(data.status);

    // Timeline steps
    const execution = data.execution || {};
    const steps = execution.steps || [];

    timeline.innerHTML = steps.map((step, i) => {
        const isLast = i === steps.length - 1;
        const toolCalls = step.tool_calls || [];
        const a2aMessages = step.a2a_messages || [];

        let detailsHtml = '';
        toolCalls.forEach(tc => {
            const result = tc.result;
            if (typeof result === 'object' && result !== null) {
                const lines = Object.entries(result)
                    .filter(([k]) => !['found', 'assigned', 'tool_call', 'status'].includes(k))
                    .map(([k, v]) => `
                        <div class="timeline-detail-row">
                            <span class="timeline-detail-label">${formatLabel(k)}</span>
                            <span class="timeline-detail-value">${escapeHtml(String(v))}</span>
                        </div>`).join('');
                detailsHtml += lines;
            }
        });

        let a2aHtml = '';
        if (a2aMessages.length > 0) {
            a2aHtml = a2aMessages.map(msg => `
                <div class="timeline-a2a">
                    <div class="timeline-a2a-label">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                        A2A: ${msg.from_agent} → ${msg.to_agent}
                    </div>
                    <div>Request: ${msg.request}</div>
                    ${msg.response ? `<div>Response: ${JSON.stringify(msg.response).substring(0, 120)}</div>` : ''}
                </div>`).join('');
        }

        const duration = step.duration_ms ? `${step.duration_ms.toFixed(1)}ms` : '';

        return `
            <div class="timeline-step" style="animation-delay: ${i * 100}ms">
                <div class="timeline-marker">
                    <div class="timeline-dot ${step.status}">${i + 1}</div>
                    ${!isLast ? '<div class="timeline-line"></div>' : ''}
                </div>
                <div class="timeline-content">
                    <div class="timeline-title">
                        <span class="timeline-task-name">${formatTaskName(step.task)}</span>
                        <span class="timeline-agent-badge ${step.agent}">${step.agent}</span>
                    </div>
                    <div class="timeline-details">
                        ${detailsHtml}
                        ${step.error ? `<div class="timeline-detail-row"><span class="timeline-detail-label" style="color:var(--accent-danger)">Error</span><span>${escapeHtml(step.error)}</span></div>` : ''}
                    </div>
                    ${a2aHtml}
                    ${duration ? `<div class="timeline-duration">${getDurationContent(duration)}</div>` : ''}
                </div>
            </div>`;
    }).join('');

    // Scroll into view
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ─── Execution Logs Page ──────────────────────────────
async function loadLogs() {
    try {
        const res = await apiFetch(`${API}/execution_logs`);
        if (!res.ok) throw new Error('Logs request failed');
        const data = await res.json();
        const container = document.getElementById('logs-container');
        const logs = data.executions || [];

        if (logs.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <p>No execution logs yet</p>
                    <span>Run a workflow to see logs here</span>
                </div>`;
            return;
        }

        container.innerHTML = logs.slice().reverse().map((log, i) => {
            const steps = log.steps || [];
            const completedSteps = steps.filter(s => s.status === 'completed').length;
            const duration = log.total_duration_ms ? `${log.total_duration_ms.toFixed(1)}ms` : '—';
            const time = log.started_at ? new Date(log.started_at).toLocaleString() : '';

            const statusClass = log.status === 'completed' ? 'completed' :
                                log.status === 'partial_failure' ? 'partial_failure' : 'failed';

            const stepsHtml = steps.map((step, si) => {
                const isLast = si === steps.length - 1;
                const toolCalls = step.tool_calls || [];
                let detailsHtml = '';
                toolCalls.forEach(tc => {
                    const result = tc.result;
                    if (typeof result === 'object' && result !== null) {
                        const lines = Object.entries(result)
                            .filter(([k]) => !['found', 'assigned', 'tool_call', 'status'].includes(k))
                            .slice(0, 5)
                            .map(([k, v]) => `
                                <div class="timeline-detail-row">
                                    <span class="timeline-detail-label">${formatLabel(k)}</span>
                                    <span class="timeline-detail-value">${escapeHtml(String(v)).substring(0, 80)}</span>
                                </div>`).join('');
                        detailsHtml += lines;
                    }
                });

                return `
                    <div class="timeline-step">
                        <div class="timeline-marker">
                            <div class="timeline-dot ${step.status}">${si + 1}</div>
                            ${!isLast ? '<div class="timeline-line"></div>' : ''}
                        </div>
                        <div class="timeline-content">
                            <div class="timeline-title">
                                <span class="timeline-task-name">${formatTaskName(step.task)}</span>
                                <span class="timeline-agent-badge ${step.agent}">${step.agent}</span>
                            </div>
                            <div class="timeline-details">${detailsHtml}</div>
                            ${step.duration_ms ? `<div class="timeline-duration">${getDurationContent(`${step.duration_ms.toFixed(1)}ms`)}</div>` : ''}
                        </div>
                    </div>`;
            }).join('');

            return `
                <div class="log-card" id="log-card-${i}">
                    <div class="log-card-header" onclick="toggleLogCard(${i})">
                        <div class="log-event">
                            <div class="activity-dot ${statusClass}"></div>
                            ${formatEventName(log.event)}
                            <span class="log-event-tag result-status ${statusClass}">${log.status}</span>
                        </div>
                        <div class="log-right">
                            <span class="log-steps-count">${completedSteps}/${steps.length} steps</span>
                            <span class="log-duration">${duration}</span>
                            <span class="log-expand-icon">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
                            </span>
                        </div>
                    </div>
                    <div class="log-card-body">
                        <div class="workflow-timeline">${stepsHtml}</div>
                    </div>
                </div>`;
        }).join('');

    } catch (e) {
        console.error('Failed to load logs:', e);
    }
}

function toggleLogCard(index) {
    document.getElementById(`log-card-${index}`).classList.toggle('expanded');
}

// ─── Agents Page ──────────────────────────────────────
async function loadAgents() {
    try {
        const res = await apiFetch(`${API}/agents`);
        if (!res.ok) throw new Error('Agents request failed');
        const data = await res.json();
        const grid = document.getElementById('agents-grid');

        const agentMeta = {
            DataAgent: {
                color: 'var(--agent-data)',
                glow: 'rgba(6, 182, 212, 0.1)',
                icon: 'D',
                desc: 'Handles all patient data retrieval and lookup operations. Acts as the system\'s data gateway — other agents request data via A2A messaging.',
            },
            SchedulerAgent: {
                color: 'var(--agent-scheduler)',
                glow: 'rgba(139, 92, 246, 0.1)',
                icon: 'S',
                desc: 'Manages doctor assignments and scheduling. Demonstrates inter-agent collaboration by requesting patient data from DataAgent via A2A.',
            },
            AlertAgent: {
                color: 'var(--agent-alert)',
                glow: 'rgba(249, 115, 22, 0.1)',
                icon: 'A',
                desc: 'Sends notifications and alerts. Dynamically constructs messages from execution context built by previous agents.',
            },
        };

        grid.innerHTML = (data.agents || []).map(agent => {
            const meta = agentMeta[agent.name] || { color: 'var(--accent-primary)', glow: 'transparent', icon: '?', desc: '' };
            const mcpTools = agent.mcp_tools || [];
            return `
                <div class="agent-card" style="--glow: ${meta.glow}">
                    <div class="agent-card-icon" style="background: ${meta.glow}; color: ${meta.color}">${meta.icon}</div>
                    <div class="agent-card-name">${agent.name}</div>
                    <div class="agent-card-type">${agent.type || 'BaseAgent'}</div>
                    <p class="tool-description">${meta.desc}</p>
                    <div class="agent-capabilities">
                        <h4>Capabilities</h4>
                        ${(agent.capabilities || []).map(c => `<span class="capability-tag">${c}</span>`).join('')}
                    </div>
                    <div class="agent-capabilities" style="margin-top:10px;">
                        <h4>MCP Tools Used</h4>
                        ${mcpTools.length
                            ? mcpTools.map(t => `<span class="capability-tag">${t}</span>`).join('')
                            : '<span class="capability-tag">No direct tool usage</span>'}
                    </div>
                </div>`;
        }).join('');
    } catch (e) {
        console.error('Failed to load agents:', e);
    }
}

// ─── Tools Page ───────────────────────────────────────
async function loadTools() {
    try {
        const res = await apiFetch(`${API}/tools`);
        if (!res.ok) throw new Error('Tools request failed');
        const data = await res.json();
        const grid = document.getElementById('tools-grid');

        grid.innerHTML = (data.tools || []).map(tool => {
            const params = tool.parameters || {};
            const paramsHtml = Object.entries(params).map(([name, desc]) => `
                <div class="param-item">
                    <span class="param-name">${name}</span>
                    <span class="param-desc">— ${desc}</span>
                </div>`).join('');

            return `
                <div class="tool-card">
                    <div class="tool-card-header">
                        <div class="tool-icon">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
                        </div>
                        <div class="tool-name">${tool.name}</div>
                    </div>
                    <div class="tool-description">${tool.description || 'No description'}</div>
                    ${paramsHtml ? `<div class="tool-params"><h4>Parameters</h4>${paramsHtml}</div>` : ''}
                </div>`;
        }).join('');
    } catch (e) {
        console.error('Failed to load tools:', e);
    }
}

// ─── Quick Actions ────────────────────────────────────
function quickAdmit() {
    navigateTo('admit');
    const pickAndAdmit = () => {
        const input = document.getElementById('admit-patient-id');
        const firstPatient = admitPatientsCache[0];
        if (firstPatient) {
            input.value = firstPatient.id;
            selectPatient(firstPatient.id);
            admitPatient();
            return;
        }
        showToast('No database patients available for quick admit', 'error');
    };

    if (admitPatientsCache.length) {
        setTimeout(pickAndAdmit, 200);
        return;
    }

    setTimeout(async () => {
        await loadAdmitPatients();
        pickAndAdmit();
    }, 250);
}

function quickEmergency() {
    navigateTo('events');
    setEventDirect('emergency_code_blue', 103);
    setTimeout(() => triggerEvent(), 300);
}

function quickDischarge() {
    navigateTo('events');
    setEventDirect('patient_discharged', 101);
    setTimeout(() => triggerEvent(), 300);
}

function quickLabResults() {
    navigateTo('events');
    setEventDirect('lab_results_ready', 102);
    setTimeout(() => triggerEvent(), 300);
}

function setEventDirect(eventType, patientId) {
    document.getElementById('event-type').value = eventType;
    document.getElementById('event-patient-id').value = patientId;
}

// ─── Appointments Page ──────────────────────────────
function initializeAppointmentsPage() {
    const dateInput = document.getElementById('booking-date');
    const filterDateInput = document.getElementById('doctor-dashboard-date');
    const doctorIdInput = document.getElementById('doctor-dashboard-id');
    const today = new Date().toISOString().slice(0, 10);

    if (dateInput && !dateInput.value) dateInput.value = today;
    if (filterDateInput && !filterDateInput.value) filterDateInput.value = today;

    const doctorSelect = document.getElementById('booking-doctor-select');
    if (doctorSelect && doctorSelect.options.length === 0) {
        doctorSelect.innerHTML = '<option value="">Select a doctor</option>';
    }
    if (doctorSelect) {
        doctorSelect.onchange = () => loadSelectedDoctorSlots();
    }
    if (dateInput) {
        dateInput.onchange = () => {
            if (bookingState.selectedDoctorId) {
                loadSelectedDoctorSlots();
            }
        };
    }

    if (doctorIdInput) {
        doctorIdInput.onchange = () => {
            loadDoctorAppointmentCalendar();
        };
    }

    if (filterDateInput) {
        filterDateInput.onchange = () => {
            const selectedDate = filterDateInput.value;
            if (selectedDate) {
                doctorCalendarState.selectedDate = selectedDate;
                const selected = new Date(selectedDate);
                doctorCalendarState.monthCursor = new Date(selected.getFullYear(), selected.getMonth(), 1);
                renderDoctorAppointmentCalendar();
            }
        };
    }

    const contextPatientId = getPatientContextId();
    if (contextPatientId) {
        const bookingIdInput = document.getElementById('booking-patient-id');
        if (bookingIdInput && !bookingIdInput.value) {
            bookingIdInput.value = contextPatientId;
        }
    }

    setupVoiceInput();
    renderDoctorAppointmentCalendar();
    if (doctorIdInput?.value) {
        loadDoctorAppointmentCalendar();
    }

    if (currentUser?.role === 'doctor') {
        initializeDoctorDashboardContext();
    }
}

async function initializeDoctorDashboardContext() {
    const doctorIdInput = document.getElementById('doctor-dashboard-id');
    if (!doctorIdInput) return;
    if (doctorIdInput.value) return;

    try {
        const res = await apiFetch(`${API}/doctor/dashboard/context`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to resolve doctor profile');

        if (data.doctor_id) {
            doctorIdInput.value = data.doctor_id;
            showToast(`Doctor profile loaded automatically: ${data.doctor_name || `#${data.doctor_id}`}`, 'info');
            await loadDoctorAppointmentCalendar();
            await loadDoctorDashboardAppointments();
        }
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

function formatDateInputValue(dateObj) {
    const y = dateObj.getFullYear();
    const m = String(dateObj.getMonth() + 1).padStart(2, '0');
    const d = String(dateObj.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

function getDoctorAppointmentsCountByDate() {
    const byDate = new Map();
    (doctorCalendarState.appointments || []).forEach(appt => {
        const start = new Date(appt.appointment_start);
        if (Number.isNaN(start.getTime())) return;
        const key = formatDateInputValue(start);
        byDate.set(key, (byDate.get(key) || 0) + 1);
    });
    return byDate;
}

function renderDoctorAppointmentCalendar() {
    const grid = document.getElementById('doctor-calendar-grid');
    const monthLabel = document.getElementById('doctor-calendar-month-label');
    const hint = document.getElementById('doctor-calendar-hint');
    if (!grid || !monthLabel || !hint) return;

    const month = doctorCalendarState.monthCursor;
    const year = month.getFullYear();
    const monthIndex = month.getMonth();

    monthLabel.textContent = month.toLocaleDateString([], {
        month: 'long',
        year: 'numeric',
    });

    const firstDay = new Date(year, monthIndex, 1);
    const lastDay = new Date(year, monthIndex + 1, 0);
    const daysInMonth = lastDay.getDate();
    const leadingBlanks = firstDay.getDay();

    const counts = getDoctorAppointmentsCountByDate();
    const todayKey = formatDateInputValue(new Date());

    const cells = [];
    for (let i = 0; i < leadingBlanks; i++) {
        cells.push('<div class="doctor-calendar-cell is-empty"></div>');
    }

    for (let day = 1; day <= daysInMonth; day++) {
        const dateObj = new Date(year, monthIndex, day);
        const dateKey = formatDateInputValue(dateObj);
        const count = counts.get(dateKey) || 0;
        const isSelected = doctorCalendarState.selectedDate === dateKey;
        const isToday = dateKey === todayKey;

        const classes = [
            'doctor-calendar-cell',
            'doctor-calendar-day',
            count > 0 ? 'has-appointments' : '',
            isSelected ? 'is-selected' : '',
            isToday ? 'is-today' : '',
        ].filter(Boolean).join(' ');

        cells.push(`
            <button class="${classes}" type="button" onclick="selectDoctorCalendarDate('${dateKey}')">
                <span class="day-number">${day}</span>
                ${count > 0 ? `<span class="day-count">${count}</span>` : '<span class="day-count day-count-empty">•</span>'}
            </button>
        `);
    }

    grid.innerHTML = cells.join('');

    const apptDates = counts.size;
    hint.textContent = apptDates
        ? `This month view shows appointments by date. ${apptDates} date(s) currently have appointments loaded.`
        : 'No loaded appointments yet. Enter Doctor ID to fetch and mark dates.';
}

function shiftDoctorCalendarMonth(offset) {
    const cursor = doctorCalendarState.monthCursor;
    doctorCalendarState.monthCursor = new Date(cursor.getFullYear(), cursor.getMonth() + offset, 1);
    renderDoctorAppointmentCalendar();
}

function selectDoctorCalendarDate(dateValue) {
    doctorCalendarState.selectedDate = dateValue;
    const dateInput = document.getElementById('doctor-dashboard-date');
    if (dateInput) {
        dateInput.value = dateValue;
    }
    renderDoctorAppointmentCalendar();
    loadDoctorDashboardAppointments();
}

async function loadDoctorAppointmentCalendar() {
    const doctorId = parseInt(document.getElementById('doctor-dashboard-id')?.value, 10);
    const hint = document.getElementById('doctor-calendar-hint');

    if (!doctorId) {
        doctorCalendarState.appointments = [];
        if (hint) hint.textContent = 'Enter Doctor ID to load appointment dates.';
        renderDoctorAppointmentCalendar();
        return;
    }

    try {
        const res = await apiFetch(`${API}/doctors/${doctorId}/appointments`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to load calendar appointments');

        doctorCalendarState.appointments = Array.isArray(data) ? data : [];

        const explicitDate = document.getElementById('doctor-dashboard-date')?.value;
        if (explicitDate) {
            doctorCalendarState.selectedDate = explicitDate;
            const selected = new Date(explicitDate);
            doctorCalendarState.monthCursor = new Date(selected.getFullYear(), selected.getMonth(), 1);
        } else if (!doctorCalendarState.selectedDate && doctorCalendarState.appointments.length) {
            const firstApptDate = formatDateInputValue(new Date(doctorCalendarState.appointments[0].appointment_start));
            doctorCalendarState.selectedDate = firstApptDate;
        }

        renderDoctorAppointmentCalendar();
    } catch (e) {
        doctorCalendarState.appointments = [];
        renderDoctorAppointmentCalendar();
        showToast(`Error: ${e.message}`, 'error');
    }
}

function initializeSchedulePage() {
    const dateInput = document.getElementById('schedule-date');
    if (dateInput && !dateInput.value) {
        dateInput.value = new Date().toISOString().slice(0, 10);
    }

    const patientInput = document.getElementById('schedule-patient-id');
    const contextPatientId = getPatientContextId();
    if (patientInput && contextPatientId) {
        patientInput.value = contextPatientId;
    }
}

function initializeMyBillingPage() {
    const patientInput = document.getElementById('billing-patient-id');
    const contextPatientId = getPatientContextId();
    if (patientInput && contextPatientId) {
        patientInput.value = contextPatientId;
        loadPatientInsuranceProfile(contextPatientId);
    }

    if (patientInput) {
        patientInput.onchange = () => {
            const pid = parseInt(patientInput.value, 10);
            if (pid) loadPatientInsuranceProfile(pid);
        };
    }
}

function setPatientContextId(patientId) {
    if (!patientId || Number.isNaN(Number(patientId))) return;
    localStorage.setItem(PATIENT_CONTEXT_KEY, String(patientId));
}

function getPatientContextId() {
    const stored = localStorage.getItem(PATIENT_CONTEXT_KEY);
    if (stored && !Number.isNaN(Number(stored))) return Number(stored);

    const fromBooking = document.getElementById('booking-patient-id')?.value;
    if (fromBooking && !Number.isNaN(Number(fromBooking))) return Number(fromBooking);

    return null;
}

function setupVoiceInput() {
    const voiceButton = document.getElementById('btn-voice-input');
    const voiceStatus = document.getElementById('voice-status');
    if (!voiceButton || !voiceStatus) return;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        voiceButton.disabled = true;
        voiceStatus.textContent = 'Voice input not supported in this browser';
        return;
    }

    if (!bookingState.voiceRecognition) {
        const recognition = new SpeechRecognition();
        recognition.lang = 'en-US';
        recognition.interimResults = true;
        recognition.continuous = true;

        recognition.onstart = () => {
            bookingState.isListening = true;
            voiceButton.textContent = '🛑 Stop Voice Input';
            voiceStatus.textContent = 'Listening... speak your symptoms';
        };

        recognition.onresult = (event) => {
            let transcript = '';
            for (let i = event.resultIndex; i < event.results.length; i++) {
                transcript += event.results[i][0].transcript;
            }
            const symptomsEl = document.getElementById('booking-symptoms');
            if (!symptomsEl) return;

            const previous = symptomsEl.value.trim();
            const merged = previous ? `${previous} ${transcript.trim()}` : transcript.trim();
            symptomsEl.value = merged.trim();
            document.getElementById('booking-audio-note').value = 'voice-dictation-captured';
        };

        recognition.onerror = (event) => {
            voiceStatus.textContent = `Voice input error: ${event.error}`;
            bookingState.isListening = false;
            voiceButton.textContent = '🎤 Start Voice Input';
        };

        recognition.onend = () => {
            bookingState.isListening = false;
            voiceButton.textContent = '🎤 Start Voice Input';
            if (voiceStatus.textContent.startsWith('Listening')) {
                voiceStatus.textContent = 'Voice input idle';
            }
        };

        bookingState.voiceRecognition = recognition;
    }

    voiceStatus.textContent = 'Voice input ready';
}

function toggleVoiceInput() {
    const recognition = bookingState.voiceRecognition;
    if (!recognition) {
        showToast('Voice input is not available in this browser', 'error');
        return;
    }

    try {
        if (bookingState.isListening) {
            recognition.stop();
        } else {
            recognition.start();
        }
    } catch (e) {
        showToast(`Voice input error: ${e.message}`, 'error');
    }
}

async function resolvePatientIdentity() {
    const patientIdRaw = document.getElementById('booking-patient-id').value;
    const patientName = document.getElementById('booking-patient-name').value.trim();
    const ageRaw = document.getElementById('booking-patient-age').value;
    const identityBox = document.getElementById('identity-box');

    const payload = {
        patient_id: patientIdRaw ? parseInt(patientIdRaw, 10) : null,
        name: patientName || null,
        age: ageRaw ? parseInt(ageRaw, 10) : null,
    };

    try {
        showLoading(true);
        const res = await apiFetch(`${API}/patient/resolve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to resolve patient identity');

        document.getElementById('booking-patient-id').value = data.patient_id;
        document.getElementById('booking-patient-name').value = data.patient_name || patientName;
        setPatientContextId(data.patient_id);

        identityBox.style.display = '';
        identityBox.innerHTML = `
            <h3>Patient Identity</h3>
            <div><strong>Status:</strong> ${data.registered ? 'Registered Patient ✅' : 'Not Registered → Created ✅'}</div>
            <div><strong>Patient ID:</strong> ${data.patient_id}</div>
            <div><strong>Name:</strong> ${escapeHtml(data.patient_name)}</div>
            <div><strong>Message:</strong> ${escapeHtml(data.message)}</div>
        `;

        appendPatientAgentStep(
            'DataAgent',
            data.registered
                ? `Validated registered patient #${data.patient_id}`
                : `Created new patient profile #${data.patient_id}`
        );

        showToast(data.message, data.registered ? 'info' : 'success');
        return data.patient_id;
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
        return null;
    } finally {
        showLoading(false);
    }
}

async function analyzeSymptomsAndRecommend() {
    const symptoms = document.getElementById('booking-symptoms').value.trim();
    const ageRaw = document.getElementById('booking-patient-age').value;
    const audioNote = document.getElementById('booking-audio-note').value.trim();

    if (!symptoms) {
        showToast('Please enter symptoms first', 'error');
        return;
    }

    resetPatientAgentWorkflow();

    const resolvedPatientId = await resolvePatientIdentity();
    if (!resolvedPatientId) return;

    const payload = {
        symptoms,
        patient_id: resolvedPatientId,
        age: ageRaw ? parseInt(ageRaw) : null,
        vitals: {},
        audio_note: audioNote || null,
    };

    try {
        showLoading(true);
        const res = await apiFetch(`${API}/patient/intake`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to analyze symptoms');

        bookingState.recommendedDepartment = data.recommended_department;
        bookingState.selectedDoctorId = null;
        bookingState.selectedSlotId = null;

        const box = document.getElementById('recommendation-box');
        box.style.display = '';
        box.innerHTML = `
            <h3>Recommendation</h3>
            <div><strong>Department:</strong> ${data.recommended_department}</div>
            <div><strong>Urgency:</strong> ${data.urgency_level}</div>
            <div><strong>Triage Score:</strong> ${data.triage_score}</div>
            <div><strong>Why:</strong> ${escapeHtml(data.explanation)}</div>
            <div><strong>Next:</strong> ${escapeHtml(data.suggested_next_step)}</div>
        `;

        appendPatientAgentStep('TriageAgent', `Detected department: ${data.recommended_department} (urgency: ${data.urgency_level}, score: ${data.triage_score})`);
        await loadDoctorsForRecommendation();
        showToast('Department recommendation generated', 'success');
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    } finally {
        showLoading(false);
    }
}

async function loadDoctorsForRecommendation() {
    if (!bookingState.recommendedDepartment) {
        showToast('Analyze symptoms first to get a department recommendation', 'error');
        return;
    }

    try {
        showLoading(true);
        const res = await apiFetch(`${API}/departments/${bookingState.recommendedDepartment}/doctors`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to load doctors');

        const select = document.getElementById('booking-doctor-select');
        const recommended = String(bookingState.recommendedDepartment || '').toLowerCase();
        const filteredDoctors = (data || []).filter(d => String(d.department || '').toLowerCase() === recommended);

        if (!filteredDoctors.length) {
            select.innerHTML = '<option value="">No available doctors</option>';
            bookingState.selectedDoctorId = null;
            showToast('No doctors currently available in that department', 'error');
            appendPatientAgentStep('SchedulerAgent', `No doctors available for ${bookingState.recommendedDepartment}`);
            return;
        }

        select.innerHTML = '<option value="">Select a doctor</option>' + filteredDoctors.map(d => (
            `<option value="${d.id}">${d.name} — ${d.specialization || d.department}</option>`
        )).join('');

        const defaultDoctor = filteredDoctors.find(d => d.available) || filteredDoctors[0];
        if (defaultDoctor) {
            select.value = String(defaultDoctor.id);
            bookingState.selectedDoctorId = defaultDoctor.id;
            appendPatientAgentStep('SchedulerAgent', `Loaded ${filteredDoctors.length} doctors for ${bookingState.recommendedDepartment}; selected Dr. ${defaultDoctor.name}`);
            await loadSelectedDoctorSlots();
        }

        showToast(`Loaded ${filteredDoctors.length} suitable doctor(s) for ${bookingState.recommendedDepartment}`, 'success');
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    } finally {
        showLoading(false);
    }
}

async function loadSelectedDoctorSlots() {
    const doctorId = parseInt(document.getElementById('booking-doctor-select').value);
    const date = document.getElementById('booking-date').value;

    if (!doctorId) {
        showToast('Please select a doctor first', 'error');
        return;
    }
    if (!date) {
        showToast('Please choose an appointment date', 'error');
        return;
    }

    bookingState.selectedDoctorId = doctorId;
    bookingState.selectedSlotId = null;

    try {
        showLoading(true);
        const res = await apiFetch(`${API}/doctors/${doctorId}/slots?date=${encodeURIComponent(date)}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to load slots');

        const container = document.getElementById('slots-box');
        if (!data.length) {
            container.innerHTML = '<div class="empty-state"><p>No available slots for this doctor/date</p></div>';
            document.getElementById('btn-book-appointment').disabled = true;
            appendPatientAgentStep('SchedulerAgent', 'No slots available for selected doctor/date');
            return;
        }

        container.innerHTML = data.map(slot => `
            <label class="slot-card">
                <input type="radio" name="appointment-slot" value="${slot.slot_id}" onchange="selectAppointmentSlot(${slot.slot_id})">
                <span>${new Date(slot.slot_start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - ${new Date(slot.slot_end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
            </label>
        `).join('');

        document.getElementById('btn-book-appointment').disabled = true;
        appendPatientAgentStep('SchedulerAgent', `Loaded ${data.length} available slots for doctor #${doctorId} on ${date}`);
        showToast(`Loaded ${data.length} slot(s)`, 'success');
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    } finally {
        showLoading(false);
    }
}

function selectAppointmentSlot(slotId) {
    bookingState.selectedSlotId = slotId;
    document.getElementById('btn-book-appointment').disabled = false;
}

async function bookAppointmentFlow() {
    const resolvedPatientId = await resolvePatientIdentity();
    const patientId = resolvedPatientId ? parseInt(resolvedPatientId, 10) : NaN;
    const symptoms = document.getElementById('booking-symptoms').value.trim();

    if (!patientId) {
        showToast('Patient ID is required for booking', 'error');
        return;
    }
    if (!bookingState.selectedDoctorId || !bookingState.selectedSlotId) {
        showToast('Please select doctor and slot before booking', 'error');
        return;
    }

    try {
        showLoading(true);
        const bookRes = await apiFetch(`${API}/appointments/book`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                patient_id: patientId,
                doctor_id: bookingState.selectedDoctorId,
                slot_id: bookingState.selectedSlotId,
                symptoms,
            }),
        });
        const bookData = await bookRes.json();
        if (!bookRes.ok) throw new Error(bookData.detail || 'Booking failed');

        bookingState.selectedAppointmentId = bookData.id;

        const confirmRes = await apiFetch(`${API}/appointments/${bookData.id}/confirmation`);
        const confirmData = await confirmRes.json();
        if (!confirmRes.ok) throw new Error(confirmData.detail || 'Failed to fetch confirmation');

        const confirmBox = document.getElementById('confirmation-box');
        confirmBox.style.display = '';
        confirmBox.innerHTML = `
            <h3>Appointment Confirmed ✅</h3>
            <div><strong>Appointment ID:</strong> ${confirmData.appointment.id}</div>
            <div><strong>Confirmation Code:</strong> ${confirmData.appointment.confirmation_code}</div>
            <div><strong>Patient:</strong> ${escapeHtml(confirmData.patient_name)}</div>
            <div><strong>Doctor:</strong> ${escapeHtml(confirmData.doctor_name)}</div>
            <div><strong>Department:</strong> ${escapeHtml(confirmData.appointment.department)}</div>
            <div><strong>Time:</strong> ${new Date(confirmData.appointment.appointment_start).toLocaleString()} - ${new Date(confirmData.appointment.appointment_end).toLocaleTimeString()}</div>
            <a class="btn btn-ghost" style="margin-top:12px;" href="${API}/appointments/${confirmData.appointment.id}/letter" target="_blank" rel="noopener">Download Appointment Letter (PDF)</a>
        `;

        showToast('Appointment booked successfully', 'success');
        await loadDoctorDashboardAppointments();
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    } finally {
        showLoading(false);
    }
}

async function loadDoctorDashboardAppointments() {
    const doctorId = parseInt(document.getElementById('doctor-dashboard-id').value);
    const date = document.getElementById('doctor-dashboard-date').value;

    if (!doctorId) {
        document.getElementById('doctor-appointments-list').innerHTML = `
            <div class="empty-state">
                <p>Enter doctor ID to load appointments</p>
                <span>Calendar dates will highlight automatically after loading.</span>
            </div>
        `;
        return;
    }

    try {
        const query = date ? `?date=${encodeURIComponent(date)}` : '';
        const res = await apiFetch(`${API}/doctors/${doctorId}/appointments${query}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to load doctor appointments');

        if (date) {
            doctorCalendarState.selectedDate = date;
            const selected = new Date(date);
            doctorCalendarState.monthCursor = new Date(selected.getFullYear(), selected.getMonth(), 1);
            renderDoctorAppointmentCalendar();
        }

        const container = document.getElementById('doctor-appointments-list');
        if (!data.length) {
            container.innerHTML = `
                <div class="empty-state">
                    <p>No appointments found for selected date</p>
                    <span>Try another highlighted date in the calendar or clear date filter.</span>
                </div>
            `;
            await loadDoctorAppointmentCalendar();
            return;
        }

        container.innerHTML = data.map(appt => `
            <div class="appointment-panel">
                <div><strong>Appointment #${appt.id}</strong> — ${new Date(appt.appointment_start).toLocaleString()}</div>
                <div>Status: <strong>${appt.status}</strong></div>
                <div>Patient ID: ${appt.patient_id}</div>
                <div>Notes: ${escapeHtml(appt.notes || '-')}</div>
                <div class="appointment-actions">
                    <button class="btn btn-sm btn-ghost" onclick="updateAppointmentStatus(${appt.id}, 'completed')">Mark Completed</button>
                    <button class="btn btn-sm btn-ghost" onclick="updateAppointmentStatus(${appt.id}, 'cancelled')">Cancel</button>
                    <button class="btn btn-sm btn-ghost" onclick="addAppointmentNote(${appt.id})">Add Note</button>
                    <button class="btn btn-sm btn-primary" onclick="runDoctorMultiAgentWorkflow(${appt.id}, ${appt.patient_id})">Run Multi-Agent Flow</button>
                </div>
            </div>
        `).join('');

        await loadDoctorAppointmentCalendar();
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

async function updateAppointmentStatus(appointmentId, statusValue) {
    try {
        const res = await apiFetch(`${API}/appointments/${appointmentId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: statusValue }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to update appointment status');

        showToast(`Appointment ${appointmentId} updated to ${statusValue}`, 'success');
        await loadDoctorDashboardAppointments();
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

async function addAppointmentNote(appointmentId) {
    const note = window.prompt('Enter note for this appointment:');
    if (note === null) return;

    try {
        const res = await apiFetch(`${API}/appointments/${appointmentId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notes: note }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to save note');

        showToast(`Note saved for appointment ${appointmentId}`, 'success');
        await loadDoctorDashboardAppointments();
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

async function runDoctorMultiAgentWorkflow(appointmentId, patientId) {
    const workflowReason = window.prompt(
        'Optional workflow reason (leave blank for default):',
        'Doctor follow-up review'
    );
    if (workflowReason === null) return;

    const testName = window.prompt('Lab test name for this workflow:', 'CBC');
    if (testName === null) return;

    const priority = window.prompt('Lab priority (stat, urgent, routine):', 'urgent');
    if (priority === null) return;

    try {
        showLoading(true);
        const res = await apiFetch(`${API}/doctors/appointments/${appointmentId}/multi-agent-workflow`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                workflow_reason: workflowReason?.trim() || null,
                chief_complaint: workflowReason?.trim() || null,
                test_name: testName?.trim() || 'CBC',
                priority: priority?.trim() || 'urgent',
            }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to run doctor multi-agent workflow');

        renderWorkflowResult('doctor-workflow', data);
        showToast(
            `Multi-agent flow completed for patient ${patientId} — ${data.summary?.completed || 0}/${data.summary?.total_steps || 0} steps`,
            data.status === 'completed' ? 'success' : 'info'
        );

        await loadDoctorDashboardAppointments();
        await loadDashboard();
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    } finally {
        showLoading(false);
    }
}

// ─── Staff Pages ────────────────────────────────────
async function loadStaffPatients() {
    const q = (document.getElementById('patients-search')?.value || '').trim();
    const container = document.getElementById('patients-list');
    if (!container) return;

    try {
        const query = q ? `?q=${encodeURIComponent(q)}` : '';
        const res = await apiFetch(`${API}/staff/patients${query}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to load patients');

        if (!data.length) {
            container.innerHTML = '<div class="empty-state"><p>No patients found</p></div>';
            return;
        }

        container.innerHTML = data.map(p => `
            <div class="appointment-panel" style="margin-bottom:10px;">
                <div><strong>#${p.id} ${escapeHtml(p.name)}</strong> · ${escapeHtml(p.department)} · Age ${p.age}</div>
                <div>Registration: <strong>Registered</strong></div>
                <div>Condition: ${escapeHtml(p.condition || '-')}</div>
                <div>Admitted: <strong>${p.admitted ? 'Yes' : 'No'}</strong> · Bed: ${p.bed_id || '-'}</div>
                <div class="appointment-actions">
                    <button class="btn btn-sm btn-ghost" onclick="viewStaffPatientDetail(${p.id})">View Detail</button>
                    <button class="btn btn-sm btn-ghost" onclick="editStaffPatient(${p.id})">Edit</button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

async function viewStaffPatientDetail(patientId) {
    try {
        const res = await apiFetch(`${API}/staff/patients/${patientId}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to load patient detail');

        const appts = data.appointments?.length || 0;
        const bills = data.billing_cases?.length || 0;
        const claims = data.insurance_claims?.length || 0;
        showToast(`Patient ${patientId}: ${appts} appointments, ${bills} billing cases, ${claims} claims`, 'info');
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

async function editStaffPatient(patientId) {
    const department = window.prompt('New department (leave blank to skip):', 'general');
    const condition = window.prompt('Condition (leave blank to skip):', '');
    const admittedRaw = window.prompt('Admitted? yes/no (leave blank to skip):', '');
    const bedIdRaw = window.prompt('Bed ID (leave blank to skip):', '');

    const payload = {};
    if (department !== null && department.trim()) payload.department = department.trim();
    if (condition !== null && condition.trim()) payload.condition = condition.trim();
    if (admittedRaw !== null && admittedRaw.trim()) payload.admitted = admittedRaw.trim().toLowerCase() === 'yes';
    if (bedIdRaw !== null && bedIdRaw.trim()) payload.bed_id = parseInt(bedIdRaw, 10);
    if (!Object.keys(payload).length) return;

    try {
        const res = await apiFetch(`${API}/staff/patients/${patientId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to update patient');

        showToast(`Patient ${patientId} updated`, 'success');
        await loadStaffPatients();
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

async function loadStaffBeds() {
    const ward = (document.getElementById('beds-ward-filter')?.value || '').trim();
    const statusValue = (document.getElementById('beds-status-filter')?.value || '').trim();
    const container = document.getElementById('beds-list');
    const summary = document.getElementById('beds-summary');
    if (!container) return;

    try {
        const params = new URLSearchParams();
        if (ward) params.set('ward', ward);
        if (statusValue) params.set('status', statusValue);
        const qs = params.toString() ? `?${params.toString()}` : '';

        const res = await apiFetch(`${API}/staff/beds${qs}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to load beds');

        if (!data.length) {
            if (summary) summary.innerHTML = '';
            container.innerHTML = '<div class="empty-state"><p>No beds found</p></div>';
            return;
        }

        const availableCount = data.filter(b => String(b.status).toLowerCase() === 'available').length;
        const occupiedCount = data.filter(b => String(b.status).toLowerCase() === 'occupied').length;
        const reservedCount = data.filter(b => String(b.status).toLowerCase() === 'reserved').length;
        const cleaningCount = data.filter(b => String(b.status).toLowerCase() === 'cleaning').length;

        if (summary) {
            summary.innerHTML = `
                <div class="ops-mini-card"><div class="ops-mini-value">${data.length}</div><div class="ops-mini-label">Total Beds</div></div>
                <div class="ops-mini-card"><div class="ops-mini-value">${availableCount}</div><div class="ops-mini-label">Available</div></div>
                <div class="ops-mini-card"><div class="ops-mini-value">${occupiedCount}</div><div class="ops-mini-label">Occupied</div></div>
                <div class="ops-mini-card"><div class="ops-mini-value">${reservedCount}</div><div class="ops-mini-label">Reserved</div></div>
                <div class="ops-mini-card"><div class="ops-mini-value">${cleaningCount}</div><div class="ops-mini-label">Cleaning</div></div>
            `;
        }

        container.innerHTML = `
            <div class="data-table-wrap">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Bed</th>
                            <th>Ward</th>
                            <th>Status</th>
                            <th>Patient</th>
                            <th>Reserved For</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.map(b => `
                            <tr>
                                <td><strong>${escapeHtml(b.bed_number)}</strong></td>
                                <td>${escapeHtml((b.ward || '').toUpperCase())}</td>
                                <td><span class="status-badge ${escapeHtml(String(b.status || '').toLowerCase())}">${escapeHtml(b.status || '-')}</span></td>
                                <td>${b.patient_id ?? '-'}</td>
                                <td>${b.reserved_for_patient_id ?? '-'}</td>
                                <td>
                                    <div class="table-actions">
                                        <button class="btn btn-sm btn-ghost" onclick='editStaffBed(${b.id}, ${JSON.stringify(b.status || "")})'>Update</button>
                                    </div>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

async function editStaffBed(bedId, currentStatus) {
    const statusValue = window.prompt('New bed status:', currentStatus || 'available');
    const patientIdRaw = window.prompt('Patient ID (leave blank to keep unchanged):', '');
    const reservedRaw = window.prompt('Reserved-for patient ID (leave blank to keep unchanged):', '');
    if (statusValue === null && patientIdRaw === null && reservedRaw === null) return;

    const payload = {};
    if (statusValue !== null && statusValue.trim()) payload.status = statusValue.trim();
    if (patientIdRaw !== null && patientIdRaw.trim()) payload.patient_id = parseInt(patientIdRaw, 10);
    if (reservedRaw !== null && reservedRaw.trim()) payload.reserved_for_patient_id = parseInt(reservedRaw, 10);

    try {
        const res = await apiFetch(`${API}/staff/beds/${bedId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to update bed');

        showToast(`Bed ${bedId} updated`, 'success');
        await loadStaffBeds();
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

async function loadStaffBillingCases() {
    const statusValue = (document.getElementById('billing-status-filter')?.value || '').trim();
    const container = document.getElementById('billing-list');
    const summary = document.getElementById('billing-summary');
    if (!container) return;

    try {
        const query = statusValue ? `?status=${encodeURIComponent(statusValue)}` : '';
        const res = await apiFetch(`${API}/staff/billing/cases${query}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to load billing cases');

        if (!data.length) {
            if (summary) summary.innerHTML = '';
            container.innerHTML = '<div class="empty-state"><p>No billing cases found</p></div>';
            return;
        }

        const openCount = data.filter(c => String(c.status).toLowerCase() === 'open').length;
        const submittedCount = data.filter(c => String(c.status).toLowerCase() === 'submitted').length;
        const paidCount = data.filter(c => String(c.status).toLowerCase() === 'paid').length;
        const totalEstimated = data.reduce((sum, c) => sum + (Number(c.estimated_total) || 0), 0);

        if (summary) {
            summary.innerHTML = `
                <div class="ops-mini-card"><div class="ops-mini-value">${data.length}</div><div class="ops-mini-label">Total Cases</div></div>
                <div class="ops-mini-card"><div class="ops-mini-value">${openCount}</div><div class="ops-mini-label">Open</div></div>
                <div class="ops-mini-card"><div class="ops-mini-value">${submittedCount}</div><div class="ops-mini-label">Submitted</div></div>
                <div class="ops-mini-card"><div class="ops-mini-value">${paidCount}</div><div class="ops-mini-label">Paid</div></div>
                <div class="ops-mini-card"><div class="ops-mini-value">${totalEstimated.toFixed(2)}</div><div class="ops-mini-label">Est. Total</div></div>
            `;
        }

        container.innerHTML = `
            <div class="data-table-wrap">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Case ID</th>
                            <th>Patient ID</th>
                            <th>Status</th>
                            <th>Estimated Total</th>
                            <th>Invoice Number</th>
                            <th>Created At</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.map(c => `
                            <tr>
                                <td><strong>#${c.id}</strong></td>
                                <td>${c.patient_id}</td>
                                <td><span class="status-badge ${escapeHtml(String(c.status || '').toLowerCase())}">${escapeHtml(c.status || '-')}</span></td>
                                <td>${(Number(c.estimated_total) || 0).toFixed(2)}</td>
                                <td>${escapeHtml(c.invoice_number || '-')}</td>
                                <td>${c.created_at ? new Date(c.created_at).toLocaleString() : '-'}</td>
                                <td>
                                    <div class="table-actions">
                                        <button class="btn btn-sm btn-ghost" onclick='editStaffBillingCase(${c.id}, ${JSON.stringify(c.status || "")})'>Update</button>
                                        <button class="btn btn-sm btn-primary" onclick='runBillingA2AWorkflow(${c.id}, ${c.patient_id})'>Run A2A Flow</button>
                                    </div>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

async function editStaffBillingCase(caseId, currentStatus) {
    const statusValue = window.prompt('New billing status:', currentStatus || 'open');
    const totalRaw = window.prompt('Estimated total (leave blank to skip):', '');
    const invoiceNumber = window.prompt('Invoice number (leave blank to skip):', '');

    const payload = {};
    if (statusValue !== null && statusValue.trim()) payload.status = statusValue.trim();
    if (totalRaw !== null && totalRaw.trim()) payload.estimated_total = parseFloat(totalRaw);
    if (invoiceNumber !== null && invoiceNumber.trim()) payload.invoice_number = invoiceNumber.trim();
    if (!Object.keys(payload).length) return;

    try {
        const res = await apiFetch(`${API}/staff/billing/cases/${caseId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to update billing case');

        showToast(`Billing case ${caseId} updated`, 'success');
        await loadStaffBillingCases();
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

async function runBillingA2AWorkflow(caseId, patientId) {
    try {
        showLoading(true);
        const res = await apiFetch(`${API}/staff/billing/cases/${caseId}/a2a-workflow`, {
            method: 'POST',
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to run billing workflow');

        renderWorkflowResult('billing-workflow', data);

        const decision = data.insurance_decision || {};
        const decisionStatus = String(decision.status || 'unknown').toLowerCase();
        if (decisionStatus === 'accepted') {
            const coverage = Number(decision.coverage_percentage || 0);
            showToast(`Billing A2A complete: insurance accepted (${coverage}% coverage)`, 'success');
        } else if (decisionStatus === 'rejected') {
            const issues = Array.isArray(decision.issues) && decision.issues.length
                ? ` [${decision.issues.join(', ')}]`
                : '';
            showToast(`Billing A2A complete: insurance rejected${issues}`, 'info');
        } else {
            showToast(
                `Billing A2A complete: ${data.summary?.completed || 0}/${data.summary?.total_steps || 0} steps`,
                data.status === 'completed' ? 'success' : 'info'
            );
        }

        await loadStaffBillingCases();
        await loadStaffInsuranceClaims();
        await loadDashboard();
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    } finally {
        showLoading(false);
    }
}

async function loadStaffInsuranceClaims() {
    const statusValue = (document.getElementById('claims-status-filter')?.value || '').trim();
    const container = document.getElementById('claims-list');
    const summary = document.getElementById('claims-summary');
    if (!container) return;

    try {
        const query = statusValue ? `?status=${encodeURIComponent(statusValue)}` : '';
        const res = await apiFetch(`${API}/staff/insurance/claims${query}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to load claims');

        if (!data.length) {
            if (summary) summary.innerHTML = '';
            container.innerHTML = '<div class="empty-state"><p>No insurance claims found</p></div>';
            return;
        }

        const pendingCount = data.filter(c => String(c.status).toLowerCase() === 'pending').length;
        const submittedCount = data.filter(c => String(c.status).toLowerCase() === 'submitted').length;
        const approvedCount = data.filter(c => String(c.status).toLowerCase() === 'approved').length;
        const rejectedCount = data.filter(c => String(c.status).toLowerCase() === 'rejected').length;

        if (summary) {
            summary.innerHTML = `
                <div class="ops-mini-card"><div class="ops-mini-value">${data.length}</div><div class="ops-mini-label">Total Claims</div></div>
                <div class="ops-mini-card"><div class="ops-mini-value">${pendingCount}</div><div class="ops-mini-label">Pending</div></div>
                <div class="ops-mini-card"><div class="ops-mini-value">${submittedCount}</div><div class="ops-mini-label">Submitted</div></div>
                <div class="ops-mini-card"><div class="ops-mini-value">${approvedCount}</div><div class="ops-mini-label">Approved</div></div>
                <div class="ops-mini-card"><div class="ops-mini-value">${rejectedCount}</div><div class="ops-mini-label">Rejected</div></div>
            `;
        }

        let profileSection = '';
        try {
            const pRes = await apiFetch(`${API}/staff/insurance/profiles`);
            const pData = await pRes.json();
            if (pRes.ok && Array.isArray(pData) && pData.length) {
                profileSection = `
                    <div style="margin-top:12px;">
                        <h3 style="margin:0 0 8px; font-size:0.9rem; color:var(--text-secondary);">Saved Patient Insurance Details</h3>
                        <div class="data-table-wrap">
                            <table class="data-table">
                                <thead>
                                    <tr>
                                        <th>Patient ID</th>
                                        <th>Provider</th>
                                        <th>Plan</th>
                                        <th>Member ID</th>
                                        <th>Policy No.</th>
                                        <th>Group No.</th>
                                        <th>Updated</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${pData.map(p => `
                                        <tr>
                                            <td>${p.patient_id}</td>
                                            <td>${escapeHtml(p.insurance_provider || '-')}</td>
                                            <td>${escapeHtml(p.plan_type || '-')}</td>
                                            <td>${escapeHtml(p.member_id || '-')}</td>
                                            <td>${escapeHtml(p.policy_number || '-')}</td>
                                            <td>${escapeHtml(p.group_number || '-')}</td>
                                            <td>${p.updated_at ? new Date(p.updated_at).toLocaleString() : '-'}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                `;
            }
        } catch (_) {
            // Keep claims page usable even if profiles call fails.
        }

        container.innerHTML = `
            <div class="data-table-wrap">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Claim ID</th>
                            <th>Patient ID</th>
                            <th>Status</th>
                            <th>Provider</th>
                            <th>Plan</th>
                            <th>Member ID</th>
                            <th>Claim Amount</th>
                            <th>Approved Amount</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.map(c => `
                            <tr>
                                <td><strong>#${c.id}</strong></td>
                                <td>${c.patient_id}</td>
                                <td><span class="status-badge ${escapeHtml(String(c.status || '').toLowerCase())}">${escapeHtml(c.status || '-')}</span></td>
                                <td>${escapeHtml(c.insurance_provider || '-')}</td>
                                <td>${escapeHtml(c.plan_type || '-')}</td>
                                <td>${escapeHtml(c.member_id || '-')}</td>
                                <td>${(Number(c.claim_amount) || 0).toFixed(2)}</td>
                                <td>${(Number(c.approved_amount) || 0).toFixed(2)}</td>
                                <td>
                                    <div class="table-actions">
                                        <button class="btn btn-sm btn-ghost" onclick='editStaffInsuranceClaim(${c.id}, ${JSON.stringify(c.status || "")})'>Update</button>
                                    </div>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
            ${profileSection}
        `;
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

async function editStaffInsuranceClaim(claimId, currentStatus) {
    const statusValue = window.prompt('New claim status:', currentStatus || 'pending');
    const claimAmountRaw = window.prompt('Claim amount (leave blank to skip):', '');
    const approvedAmountRaw = window.prompt('Approved amount (leave blank to skip):', '');
    const rejectionReason = window.prompt('Rejection reason (optional):', '');

    const payload = {};
    if (statusValue !== null && statusValue.trim()) payload.status = statusValue.trim();
    if (claimAmountRaw !== null && claimAmountRaw.trim()) payload.claim_amount = parseFloat(claimAmountRaw);
    if (approvedAmountRaw !== null && approvedAmountRaw.trim()) payload.approved_amount = parseFloat(approvedAmountRaw);
    if (rejectionReason !== null && rejectionReason.trim()) payload.rejection_reason = rejectionReason.trim();
    if (!Object.keys(payload).length) return;

    try {
        const res = await apiFetch(`${API}/staff/insurance/claims/${claimId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to update claim');

        showToast(`Insurance claim ${claimId} updated`, 'success');
        await loadStaffInsuranceClaims();
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

async function loadStaffReportsSummary() {
    const container = document.getElementById('reports-kpi-grid');
    if (!container) return;

    try {
        const res = await apiFetch(`${API}/staff/reports/summary`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to load reports');

        const metrics = [
            ['Total Patients', data.total_patients],
            ['Admitted Patients', data.admitted_patients],
            ['Total Beds', data.total_beds],
            ['Occupied Beds', data.occupied_beds],
            ['Available Beds', data.available_beds],
            ['Open Billing Cases', data.open_billing_cases],
            ['Submitted Claims', data.submitted_claims],
            ['Pending Claims', data.pending_claims],
            ['Confirmed Appointments', data.confirmed_appointments],
            ['Completed Appointments', data.completed_appointments],
            ['Cancelled Appointments', data.cancelled_appointments],
            ['Est. Billing Total', data.total_estimated_billing],
        ];

        container.innerHTML = metrics.map(([label, value]) => `
            <div class="stat-card stat-primary">
                <div class="stat-info">
                    <span class="stat-value">${value}</span>
                    <span class="stat-label">${label}</span>
                </div>
            </div>
        `).join('');
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

function appendPatientAgentStep(agentName, message) {
    const panel = document.getElementById('booking-agent-workflow');
    if (!panel) return;

    if (panel.dataset.initialized !== 'true') {
        panel.dataset.initialized = 'true';
        panel.style.display = '';
        panel.innerHTML = '<h3>Agent Workflow (Patient Journey)</h3><div id="booking-agent-steps"></div>';
    }

    const list = document.getElementById('booking-agent-steps');
    if (!list) return;

    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const row = document.createElement('div');
    row.className = 'timeline-a2a';
    row.innerHTML = `
        <div class="timeline-a2a-label">${escapeHtml(agentName)} · ${timestamp}</div>
        <div>${escapeHtml(message)}</div>
    `;
    list.prepend(row);
}

function resetPatientAgentWorkflow() {
    const panel = document.getElementById('booking-agent-workflow');
    if (!panel) return;
    panel.dataset.initialized = 'false';
    panel.style.display = 'none';
    panel.innerHTML = '';
}

async function loadPatientSchedule() {
    const container = document.getElementById('schedule-list');
    const patientIdRaw = document.getElementById('schedule-patient-id')?.value || '';
    const date = document.getElementById('schedule-date')?.value || '';
    const patientId = parseInt(patientIdRaw, 10);

    if (!container) return;
    if (!patientId) {
        container.innerHTML = '<div class="empty-state"><p>Enter your patient ID to view schedule</p></div>';
        return;
    }

    try {
        setPatientContextId(patientId);
        const params = new URLSearchParams({ patient_id: String(patientId) });
        if (date) params.set('date', date);

        const res = await apiFetch(`${API}/patient/appointments?${params.toString()}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to load schedule');

        if (!data.length) {
            container.innerHTML = '<div class="empty-state"><p>No appointments found for selected date.</p></div>';
            return;
        }

        container.innerHTML = `
            <div class="data-table-wrap">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Appointment ID</th>
                            <th>Date</th>
                            <th>Time</th>
                            <th>Doctor ID</th>
                            <th>Department</th>
                            <th>Status</th>
                            <th>Confirmation Code</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.map(a => {
                            const start = new Date(a.appointment_start);
                            const end = new Date(a.appointment_end);
                            return `
                                <tr>
                                    <td><strong>#${a.id}</strong></td>
                                    <td>${start.toLocaleDateString()}</td>
                                    <td>${start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - ${end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</td>
                                    <td>${a.doctor_id}</td>
                                    <td>${escapeHtml(a.department || '-')}</td>
                                    <td><span class="status-badge ${escapeHtml(String(a.status || '').toLowerCase())}">${escapeHtml(a.status || '-')}</span></td>
                                    <td>${escapeHtml(a.confirmation_code || '-')}</td>
                                </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            </div>
        `;
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
        container.innerHTML = '<div class="empty-state"><p>Unable to load schedule</p></div>';
    }
}

async function loadPatientBilling() {
    const container = document.getElementById('mybilling-list');
    const summary = document.getElementById('mybilling-summary');
    const patientIdRaw = document.getElementById('billing-patient-id')?.value || '';
    const patientId = parseInt(patientIdRaw, 10);

    if (!container || !summary) return;
    if (!patientId) {
        summary.innerHTML = '';
        container.innerHTML = '<div class="empty-state"><p>Enter your patient ID to view billing</p></div>';
        return;
    }

    try {
        setPatientContextId(patientId);
        await loadPatientInsuranceProfile(patientId);
        const res = await apiFetch(`${API}/patient/billing?patient_id=${patientId}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to load billing overview');

        const records = data.records || [];
        const claimable = records.filter(r => r.can_claim_insurance).length;
        const billed = records.reduce((sum, r) => sum + (Number(r.billing_case?.estimated_total) || 0), 0);
        const approved = records.reduce((sum, r) => sum + (Number(r.insurance_claim?.approved_amount) || 0), 0);

        summary.innerHTML = `
            <div class="ops-mini-card"><div class="ops-mini-value">${records.length}</div><div class="ops-mini-label">Total Bills</div></div>
            <div class="ops-mini-card"><div class="ops-mini-value">${claimable}</div><div class="ops-mini-label">Can Claim Insurance</div></div>
            <div class="ops-mini-card"><div class="ops-mini-value">${billed.toFixed(2)}</div><div class="ops-mini-label">Total Billed</div></div>
            <div class="ops-mini-card"><div class="ops-mini-value">${approved.toFixed(2)}</div><div class="ops-mini-label">Insurance Approved</div></div>
        `;

        if (!records.length) {
            container.innerHTML = '<div class="empty-state"><p>No billing records found</p></div>';
            return;
        }

        container.innerHTML = `
            <div class="data-table-wrap">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Billing Case</th>
                            <th>Bill Status</th>
                            <th>Estimated Total</th>
                            <th>Invoice</th>
                            <th>Insurance Status</th>
                            <th>Claim Amount</th>
                            <th>Approved Amount</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${records.map(row => {
                            const caseData = row.billing_case || {};
                            const claim = row.insurance_claim || null;
                            return `
                                <tr>
                                    <td><strong>#${caseData.id ?? '-'}</strong></td>
                                    <td><span class="status-badge ${escapeHtml(String(caseData.status || '').toLowerCase())}">${escapeHtml(caseData.status || '-')}</span></td>
                                    <td>${(Number(caseData.estimated_total) || 0).toFixed(2)}</td>
                                    <td>${escapeHtml(caseData.invoice_number || '-')}</td>
                                    <td><span class="status-badge ${escapeHtml(String(row.insurance_status || '').toLowerCase())}">${escapeHtml(row.insurance_status || 'not_claimed')}</span></td>
                                    <td>${claim ? (Number(claim.claim_amount) || 0).toFixed(2) : '-'}</td>
                                    <td>${claim ? (Number(claim.approved_amount) || 0).toFixed(2) : '-'}</td>
                                    <td>
                                        <div class="table-actions">
                                            ${row.can_claim_insurance
                                                ? `<button class="btn btn-sm btn-ghost" onclick="claimInsuranceForCase(${caseData.id}, ${data.patient_id})">Claim Insurance</button>`
                                                : '<span style="color:var(--text-muted); font-size:0.76rem;">Claimed</span>'}
                                        </div>
                                    </td>
                                </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            </div>
        `;
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
        summary.innerHTML = '';
        container.innerHTML = '<div class="empty-state"><p>Unable to load billing records</p></div>';
    }
}

async function claimInsuranceForCase(caseId, patientId) {
    const insurance_provider = (document.getElementById('insurance-provider')?.value || '').trim();
    const plan_type = (document.getElementById('insurance-plan')?.value || '').trim();
    const member_id = (document.getElementById('insurance-member-id')?.value || '').trim();

    if (!insurance_provider || !plan_type || !member_id) {
        showToast('Please save insurance details first (provider, plan, member ID)', 'error');
        return;
    }

    try {
        const res = await apiFetch(`${API}/patient/billing/${caseId}/claim-insurance?patient_id=${patientId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                insurance_provider: insurance_provider || null,
                plan_type: plan_type || null,
                member_id: member_id || null,
            }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to create insurance claim');

        showToast(`Insurance claim ready: #${data.id} (${data.status})`, 'success');
        await loadPatientBilling();
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

async function loadPatientInsuranceProfile(patientId) {
    const statusEl = document.getElementById('insurance-profile-status');
    if (!patientId) {
        if (statusEl) statusEl.textContent = 'Enter patient ID to load insurance details.';
        return;
    }

    try {
        const res = await apiFetch(`${API}/patient/insurance/profile?patient_id=${patientId}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to load insurance profile');

        const setValue = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.value = value || '';
        };

        setValue('insurance-provider', data.insurance_provider);
        setValue('insurance-plan', data.plan_type);
        setValue('insurance-member-id', data.member_id);
        setValue('insurance-policy-number', data.policy_number);
        setValue('insurance-group-number', data.group_number);

        if (statusEl) {
            statusEl.textContent = data.updated_at
                ? `Insurance profile loaded (updated ${new Date(data.updated_at).toLocaleString()}).`
                : 'No saved profile yet. Add details and save.';
        }
    } catch (e) {
        if (statusEl) statusEl.textContent = 'Unable to load insurance details.';
        showToast(`Error: ${e.message}`, 'error');
    }
}

async function savePatientInsuranceProfile() {
    const patientId = parseInt(document.getElementById('billing-patient-id')?.value || '', 10);
    const statusEl = document.getElementById('insurance-profile-status');

    if (!patientId) {
        showToast('Enter patient ID before saving insurance details', 'error');
        return;
    }

    const payload = {
        insurance_provider: (document.getElementById('insurance-provider')?.value || '').trim() || null,
        plan_type: (document.getElementById('insurance-plan')?.value || '').trim() || null,
        member_id: (document.getElementById('insurance-member-id')?.value || '').trim() || null,
        policy_number: (document.getElementById('insurance-policy-number')?.value || '').trim() || null,
        group_number: (document.getElementById('insurance-group-number')?.value || '').trim() || null,
    };

    try {
        const res = await apiFetch(`${API}/patient/insurance/profile?patient_id=${patientId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to save insurance profile');

        if (statusEl) {
            statusEl.textContent = data.updated_at
                ? `Insurance profile saved (${new Date(data.updated_at).toLocaleString()}).`
                : 'Insurance profile saved.';
        }
        showToast('Insurance details saved', 'success');
        setPatientContextId(patientId);
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

// ─── Toast Notifications ─────────────────────────────
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const icons = {
        success: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
        error: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
    };

    toast.innerHTML = `${icons[type] || icons.info}<span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'toastOut 0.3s ease-in forwards';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ─── Loading ──────────────────────────────────────────
function showLoading(show) {
    document.getElementById('loading-overlay').classList.toggle('active', show);
}

function getStatusBadgeContent(status) {
    const items = {
        completed: {
            label: 'Completed',
            icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>',
        },
        partial_failure: {
            label: 'Partial',
            icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.4L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.4a2 2 0 0 0-3.4 0z"/></svg>',
        },
        failed: {
            label: 'Failed',
            icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
        },
    };

    const selected = items[status] || items.failed;
    return `<span class="result-status-content">${selected.icon}<span>${selected.label}</span></span>`;
}

function getDurationContent(value) {
    return `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></svg><span>${value}</span>`;
}

// ─── Helpers ──────────────────────────────────────────
function formatEventName(event) {
    if (!event) return 'Unknown';
    return event.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

function formatTaskName(task) {
    if (!task) return 'Unknown';
    return task.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

function formatLabel(key) {
    return key.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
