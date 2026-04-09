/* ═══════════════════════════════════════════════════════
   Hospital Workflow Automation — Dashboard Application
   ═══════════════════════════════════════════════════════ */

const API = '';  // Same origin
const TOKEN_STORAGE_KEY = 'hospital_auth_token';

// ─── State ────────────────────────────────────────────
let currentPage = 'dashboard';
let executionLogs = [];
let authToken = null;
let currentUser = null;

const roleAccess = {
    super_admin: {
        pages: ['dashboard', 'admit', 'events', 'logs', 'agents', 'tools'],
        canQuickActions: true,
    },
    staff: {
        pages: ['dashboard', 'admit', 'events', 'logs', 'agents', 'tools'],
        canQuickActions: true,
    },
    doctor: {
        pages: ['dashboard', 'events', 'logs', 'agents', 'tools'],
        canQuickActions: false,
    },
    auditor: {
        pages: ['dashboard', 'logs', 'agents', 'tools'],
        canQuickActions: false,
    },
};

// ─── Initialization ───────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    setupNavigation();
    setupClock();
    const authenticated = await ensureAuthenticated();
    if (!authenticated) return;

    loadHealthData();
    loadDashboard();
    loadAgentStatus();
});

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

function forceLogout(message = '') {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    authToken = null;
    currentUser = null;
    renderAuthUser();
    showAuthOverlay(true);
    if (message) {
        document.getElementById('auth-error').textContent = message;
    }
}

async function login(event) {
    event.preventDefault();
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const loginBtn = document.getElementById('btn-login');
    const errorEl = document.getElementById('auth-error');

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
        loadHealthData();
        loadDashboard();
        loadAgentStatus();
    } catch (e) {
        errorEl.textContent = e.message || 'Sign-in failed';
    } finally {
        loginBtn.disabled = false;
    }
}

function logout() {
    forceLogout('You have been signed out.');
}

function fillDemoCredentials(username, password) {
    document.getElementById('login-username').value = username;
    document.getElementById('login-password').value = password;
    document.getElementById('auth-error').textContent = '';
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
    document.getElementById('admit-patient-id').value = id;
    document.querySelectorAll('.patient-chip').forEach(c => c.classList.remove('selected'));
    event.currentTarget.classList.add('selected');
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
    document.getElementById('admit-patient-id').value = 101;
    setTimeout(() => admitPatient(), 300);
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
