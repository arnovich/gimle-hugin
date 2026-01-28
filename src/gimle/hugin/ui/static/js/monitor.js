/* Agent Monitor - Main Page JavaScript */

let currentAgentId = null;
let currentSessionId = null;
let agentsData = {};
let interactionsData = {};
let currentAgentDetails = null;
let activeFilter = 'all';
let activeBranchFilter = 'all';
let currentView = 'timeline';
let autoScrollEnabled = true;
let lastAgentsList = [];
let sidebarQuery = '';
let isInitialLoad = true;

// Cache for lazy-loaded interaction details (keyed by interaction ID)
let interactionDetailCache = {};

// Track current artifact for modal actions
let currentArtifactId = null;
let currentInteractionId = null;

// ==========================================================================
// Initialization
// ==========================================================================

window.addEventListener('DOMContentLoaded', function() {
    initializeTheme();
    initializeSearch();
    initializeSidebar();
    initializeAutoScroll();
    refreshAgents();
    // SSE live updates disabled due to connection issues causing hangs
    // Use manual refresh button instead, or enable polling below
    // setupLiveUpdates();
    setupPollingRefresh();  // Simple polling as alternative to SSE
});

// ==========================================================================
// Theme Management
// ==========================================================================

function initializeTheme() {
    const savedTheme = localStorage.getItem('monitor-theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);
}

function toggleTheme() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('monitor-theme', newTheme);
    updateThemeIcon(newTheme);
}

function updateThemeIcon(theme) {
    const lightIcon = document.getElementById('theme-icon-light');
    const darkIcon = document.getElementById('theme-icon-dark');
    if (lightIcon && darkIcon) {
        lightIcon.style.display = theme === 'light' ? 'block' : 'none';
        darkIcon.style.display = theme === 'dark' ? 'block' : 'none';
    }
}

// ==========================================================================
// Search Functionality
// ==========================================================================

function initializeSearch() {
    const searchInput = document.getElementById('global-search');
    if (searchInput) {
        searchInput.addEventListener('input', debounce(handleSearch, 200));
        searchInput.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                searchInput.value = '';
                handleSearch();
                searchInput.blur();
            }
        });
    }

    // Global keyboard shortcut
    document.addEventListener('keydown', function(e) {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            const searchInput = document.getElementById('global-search');
            if (searchInput) {
                searchInput.focus();
                searchInput.select();
            }
        }
    });
}

// ==========================================================================
// Sidebar (Sessions / Agents List)
// ==========================================================================

function initializeSidebar() {
    const panel = document.getElementById('left-panel');
    const savedCollapsed = localStorage.getItem('monitor-left-panel-collapsed');
    if (panel && savedCollapsed === 'true') {
        panel.classList.add('collapsed');
    }

    const input = document.getElementById('sidebar-search');
    if (input) {
        input.addEventListener('input', debounce(() => {
            sidebarQuery = input.value.toLowerCase().trim();
            renderAgentsList(lastAgentsList);
        }, 150));

        input.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                input.value = '';
                sidebarQuery = '';
                renderAgentsList(lastAgentsList);
                input.blur();
            }
        });
    }
}

function handleSearch() {
    const searchInput = document.getElementById('global-search');
    const query = searchInput ? searchInput.value.toLowerCase().trim() : '';

    if (!query) {
        // Clear search - show all (respecting current filter)
        document.querySelectorAll('.flowchart-item, .timeline-item, .timeline-node, .interaction-row').forEach(el => {
            el.style.display = '';
            el.classList.remove('search-match');
        });
        applyFilter(activeFilter);
        return;
    }

    // Search through interactions
    const searchableFields = ['type', 'tool', 'tool_name', 'summary'];

    document.querySelectorAll('.flowchart-item, .timeline-item, .timeline-node, .interaction-row').forEach(el => {
        const interactionId = el.dataset.interactionId || el.getAttribute('data-interaction-id');
        const interaction = interactionsData[interactionId];

        if (!interaction) {
            el.style.display = 'none';
            return;
        }

        // Build searchable text
        let searchText = searchableFields
            .map(field => interaction[field])
            .filter(Boolean)
            .join(' ')
            .toLowerCase();

        // Also search in args and result
        if (interaction.args) {
            searchText += ' ' + JSON.stringify(interaction.args).toLowerCase();
        }
        if (interaction.result) {
            searchText += ' ' + JSON.stringify(interaction.result).toLowerCase();
        }

        if (searchText.includes(query)) {
            el.style.display = '';
            el.classList.add('search-match');
        } else {
            el.style.display = 'none';
            el.classList.remove('search-match');
        }
    });
}

// ==========================================================================
// Filter Functionality
// ==========================================================================

const FILTER_GROUPS = {
    all: () => true,
    oracle: (i) => ['AskOracle', 'OracleResponse'].includes(i.type),
    tool: (i) => ['ToolCall', 'ToolResult'].includes(i.type),
    task: (i) => ['TaskDefinition', 'TaskResult', 'TaskChain', 'AgentCall', 'AgentResult'].includes(i.type),
    human: (i) => ['AskHuman', 'HumanResponse', 'ExternalInput'].includes(i.type),
    errors: (i) => i.is_error === true
};

function applyFilter(filterName) {
    activeFilter = filterName;

    // Update pill states
    document.querySelectorAll('.filter-pill').forEach(pill => {
        pill.classList.toggle('active', pill.dataset.filter === filterName);
    });

    // Apply all filters (type + branch)
    applyAllFilters();
}

// ==========================================================================
// Branch Filter Functionality
// ==========================================================================

function updateBranchFilter() {
    // Extract unique branches from interactions
    const branches = new Set();
    Object.values(interactionsData).forEach(interaction => {
        if (interaction.branch) {
            branches.add(interaction.branch);
        }
    });

    const container = document.getElementById('branch-filter-container');
    const select = document.getElementById('branch-filter');

    if (branches.size === 0) {
        // No branches, hide the filter
        if (container) container.style.display = 'none';
        activeBranchFilter = 'all';
        return;
    }

    // Show the filter and populate options
    if (container) container.style.display = 'flex';

    // Build options
    let options = '<option value="all">All branches</option>';
    options += '<option value="main">Main (no branch)</option>';

    // Sort branches alphabetically
    const sortedBranches = Array.from(branches).sort();
    sortedBranches.forEach(branch => {
        const escaped = escapeHtml(branch);
        const selected = activeBranchFilter === branch ? ' selected' : '';
        options += `<option value="${escaped}"${selected}>${escaped}</option>`;
    });

    if (select) {
        select.innerHTML = options;
        select.value = activeBranchFilter;
    }
}

function applyBranchFilter(branchName) {
    activeBranchFilter = branchName;
    applyAllFilters();
}

function applyAllFilters() {
    const typeFilterFn = FILTER_GROUPS[activeFilter] || FILTER_GROUPS.all;

    document.querySelectorAll('.flowchart-item, .timeline-item, .timeline-node, .interaction-row').forEach(el => {
        const interactionId = el.dataset.interactionId || el.getAttribute('data-interaction-id');
        const interaction = interactionsData[interactionId];

        if (!interaction) return;

        // Check type filter
        const matchesTypeFilter = typeFilterFn(interaction);

        // Check branch filter
        let matchesBranchFilter = true;
        if (activeBranchFilter !== 'all') {
            if (activeBranchFilter === 'main') {
                // Show only interactions without a branch
                matchesBranchFilter = !interaction.branch;
            } else {
                // Show only interactions with matching branch
                matchesBranchFilter = interaction.branch === activeBranchFilter;
            }
        }

        el.style.display = (matchesTypeFilter && matchesBranchFilter) ? '' : 'none';
    });

    // Re-apply search if active
    const searchInput = document.getElementById('global-search');
    if (searchInput && searchInput.value.trim()) {
        handleSearch();
    }
}

// ==========================================================================
// View Toggle
// ==========================================================================

function setView(viewName) {
    currentView = viewName;

    // Update button states
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === viewName);
    });

    // Toggle visibility of view sections
    const stackViz = document.querySelector('.stack-visualization');
    const timelineSection = document.querySelector('.timeline-section');

    if (viewName === 'flowchart') {
        if (stackViz) {
            stackViz.style.display = 'block';
            const flowchart = stackViz.querySelector('.flowchart');
            const header = stackViz.querySelector('h2');
            if (flowchart) flowchart.classList.add('expanded');
            if (header) header.classList.add('expanded');
        }
        if (timelineSection) {
            timelineSection.style.display = 'none';
        }
    } else {
        if (stackViz) {
            stackViz.style.display = 'none';
        }
        if (timelineSection) {
            timelineSection.style.display = 'block';
            const timeline = timelineSection.querySelector('.timeline-view');
            const header = timelineSection.querySelector('h2');
            if (timeline) timeline.classList.add('expanded');
            if (header) header.classList.add('expanded');
        }
    }
}

// ==========================================================================
// Auto-scroll
// ==========================================================================

function initializeAutoScroll() {
    const checkbox = document.getElementById('auto-scroll');
    if (checkbox) {
        checkbox.addEventListener('change', function() {
            autoScrollEnabled = this.checked;
        });
    }
}

// ==========================================================================
// Live Updates (Polling-based, more reliable than SSE)
// ==========================================================================

let pollingInterval = null;
let autoRefreshEnabled = false;
const POLLING_INTERVAL_MS = 3000;  // 3 seconds

function setupPollingRefresh() {
    // Auto-refresh is OFF by default - user can enable it
    updateAutoRefreshIndicator(false);
}

function toggleAutoRefresh() {
    autoRefreshEnabled = !autoRefreshEnabled;

    if (autoRefreshEnabled) {
        console.log('Auto-refresh enabled');
        pollingInterval = setInterval(() => {
            if (!isRefreshing) {
                refreshAgents();
            }
        }, POLLING_INTERVAL_MS);
    } else {
        console.log('Auto-refresh disabled');
        if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
        }
    }

    updateAutoRefreshIndicator(autoRefreshEnabled);
}

function updateAutoRefreshIndicator(enabled) {
    const indicator = document.getElementById('live-indicator');
    if (indicator) {
        indicator.classList.toggle('disconnected', !enabled);
        const label = indicator.querySelector('span:last-child');
        if (label) {
            label.textContent = enabled ? 'Auto-refresh ON' : 'Auto-refresh OFF';
        }
    }
}

// Legacy SSE function (disabled due to connection hanging issues)
function setupLiveUpdates() {
    const eventSource = new EventSource('/api/updates');

    eventSource.onopen = function() {
        console.log('Live updates connected');
        updateLiveIndicator(true);
    };

    eventSource.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'update') {
                console.log(`Storage update: ${data.object_type} ${data.object_id}`);
                handleStorageUpdate(data.object_type, data.object_id);
            }
        } catch (error) {
            console.error('Error parsing SSE data:', error);
        }
    };

    eventSource.onerror = function(error) {
        console.error('SSE error:', error);
        updateLiveIndicator(false);
    };
}

function updateLiveIndicator(connected) {
    // SSE connection status - we track this but don't always show it
    // The indicator now shows agent running status when viewing an agent
    const indicator = document.getElementById('live-indicator');
    if (indicator && !currentAgentId) {
        // Only show SSE status when not viewing an agent
        indicator.style.display = 'flex';
        indicator.classList.toggle('disconnected', !connected);
        indicator.classList.remove('completed');
        const label = indicator.querySelector('span:last-child');
        if (label) {
            label.textContent = connected ? 'Connected' : 'Disconnected';
        }
    }
}

function updateAgentStatusIndicator(agentData) {
    const indicator = document.getElementById('live-indicator');
    if (!indicator) return;

    indicator.style.display = 'flex';

    // Check if agent was recently modified (within 45 seconds = likely running)
    const nowSeconds = Date.now() / 1000;
    const lastModified = agentData?.last_modified || 0;
    const isRunning = lastModified && (nowSeconds - lastModified) < 45;

    // Check if there's a TaskResult indicating completion
    const hasTaskResult = Object.values(interactionsData || {}).some(
        i => i.type === 'TaskResult'
    );

    const dot = indicator.querySelector('.live-dot');
    const label = indicator.querySelector('span:last-child');

    if (isRunning) {
        indicator.classList.remove('disconnected', 'completed');
        if (label) label.textContent = 'Running';
    } else if (hasTaskResult) {
        indicator.classList.remove('disconnected');
        indicator.classList.add('completed');
        if (label) label.textContent = 'Completed';
    } else {
        indicator.classList.remove('completed');
        indicator.classList.add('disconnected');
        if (label) label.textContent = 'Idle';
    }
}

// Debounce mechanism for refresh operations
let refreshTimeout = null;
let isRefreshing = false;

function handleStorageUpdate(objectType, objectId) {
    // Be permissive here: depending on how storage writes happen, we may see
    // artifact updates (affects counts) or "unknown" (older storage formats).
    if (objectType === 'session' || objectType === 'agent' || objectType === 'interaction' || objectType === 'artifact' || objectType === 'unknown') {
        // Don't schedule refresh if one is already in progress or pending
        if (isRefreshing || refreshTimeout) {
            return;
        }
        refreshTimeout = setTimeout(() => {
            refreshTimeout = null;
            refreshAgents();
        }, 500);  // 500ms debounce
    }
}

// ==========================================================================
// Agent List Management
// ==========================================================================

async function refreshAgents() {
    if (isRefreshing) {
        console.log('Refresh already in progress, skipping');
        return;
    }

    isRefreshing = true;
    const refreshButton = document.querySelector('.refresh-button');
    if (refreshButton) {
        refreshButton.classList.add('refreshing');
    }

    let shouldAutoSelectSession = false;
    let latestSessionId = null;

    try {
        // Add timeout to prevent hanging forever (30s for initial, 10s for subsequent)
        const controller = new AbortController();
        const timeout = isInitialLoad ? 30000 : 10000;
        const timeoutId = setTimeout(() => controller.abort(), timeout);

        const response = await fetch('/api/agents', { signal: controller.signal });
        clearTimeout(timeoutId);
        const agents = await response.json();
        lastAgentsList = agents;
        agentsData = {};
        agents.forEach(agent => {
            agentsData[agent.id] = agent;
        });
        renderAgentsList(agents);

        // Refresh current view if one is selected
        if (currentAgentId && agentsData[currentAgentId]) {
            // Clear cache so we get fresh data
            interactionDetailCache = {};
            // Reload the current agent view
            await loadAgent(currentAgentId);
        } else if (currentSessionId) {
            // Reload the current session view
            await loadSession(currentSessionId);
        }

        // Check if we should auto-select the latest session on initial load
        if (isInitialLoad && !currentAgentId && !currentSessionId && agents.length > 0) {
            // Group agents by session to find the most recent session
            const sessionGroups = {};
            agents.forEach(agent => {
                const sessionId = agent.session_id || 'unknown';
                if (!sessionGroups[sessionId]) {
                    sessionGroups[sessionId] = {
                        last_modified: agent.last_modified
                    };
                }
            });

            // Sort sessions by last_modified (newest first)
            const sortedSessions = Object.entries(sessionGroups)
                .sort((a, b) => b[1].last_modified - a[1].last_modified);

            if (sortedSessions.length > 0) {
                latestSessionId = sortedSessions[0][0];
                shouldAutoSelectSession = true;
            }
        }
        isInitialLoad = false;
    } catch (error) {
        if (error.name === 'AbortError') {
            console.warn('Refresh timed out');
            document.getElementById('agents-list').innerHTML =
                '<div class="loading">Refresh timed out<br><button class="btn" onclick="refreshAgents()" style="margin-top: 8px;">Retry</button></div>';
        } else {
            console.error('Error loading agents:', error);
            document.getElementById('agents-list').innerHTML =
                '<div class="loading">Error: ' + escapeHtml(error.message) + '<br><button class="btn" onclick="refreshAgents()" style="margin-top: 8px;">Retry</button></div>';
        }
    } finally {
        isRefreshing = false;
        isInitialLoad = false;  // Ensure this is set even on error
        const refreshButton = document.querySelector('.refresh-button');
        if (refreshButton) {
            refreshButton.classList.remove('refreshing');
        }
    }

    // Auto-select session AFTER refresh is complete (isRefreshing = false)
    if (shouldAutoSelectSession && latestSessionId) {
        await loadSession(latestSessionId);
    }
}

function renderAgentsList(agents) {
    const listElement = document.getElementById('agents-list');
    if (listElement) {
        listElement.classList.remove('loading');
    }

    if (agents.length === 0) {
        listElement.innerHTML = '<div class="loading">No agents found</div>';
        return;
    }

    // Apply sidebar filter (session id / agent name / agent id)
    const filteredAgents = sidebarQuery
        ? agents.filter(agent => {
            const configName = (agent.config_name || '').toLowerCase();
            const agentId = (agent.id || '').toLowerCase();
            const sessionId = (agent.session_id || '').toLowerCase();
            return (
                configName.includes(sidebarQuery) ||
                agentId.includes(sidebarQuery) ||
                sessionId.includes(sidebarQuery)
            );
        })
        : agents;

    if (filteredAgents.length === 0) {
        listElement.innerHTML = '<div class="loading">No matches</div>';
        return;
    }

    // Group agents by session
    const sessionGroups = {};
    filteredAgents.forEach(agent => {
        const sessionId = agent.session_id || 'unknown';
        if (!sessionGroups[sessionId]) {
            sessionGroups[sessionId] = {
                agents: [],
                created_at: agent.session_created_at,
                last_modified: agent.last_modified
            };
        }
        sessionGroups[sessionId].agents.push(agent);
    });

    // Sort sessions by last_modified (newest first)
    const sortedSessions = Object.entries(sessionGroups)
        .sort((a, b) => b[1].last_modified - a[1].last_modified);

    let html = '';
    sortedSessions.forEach(([sessionId, sessionData]) => {
        const sessionLabel = sessionId === 'unknown' ? 'Unknown Session' : `Session ${sessionId.substring(0, 8)}...`;
        const sessionTime = sessionData.created_at ? formatTimestamp(sessionData.created_at) : '';
        const agentCount = sessionData.agents.length;
        const sessionUpdated = sessionData.last_modified ? formatRelativeTimeFromEpochSeconds(sessionData.last_modified) : '';
        const sessionUpdatedTitle = sessionData.last_modified ? formatTimestamp(new Date(sessionData.last_modified * 1000).toISOString()) : '';
        const sessionCreatedTitle = sessionTime ? `Created ${sessionTime}` : '';

        html += `
            <div class="session-group" data-session-id="${sessionId}">
                <div class="session-header" onclick="loadSession('${sessionId}', event)" title="Open session">
                    <div class="session-header-left">
                        <button class="session-toggle-btn" onclick="toggleSession('${sessionId}', event)" title="Collapse/expand session" aria-label="Collapse/expand session">
                            <span class="session-toggle" id="toggle-${sessionId}">
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="6 9 12 15 18 9"></polyline>
                            </svg>
                            </span>
                        </button>
                        <button class="session-open-btn" onclick="loadSession('${sessionId}', event)" title="Open session" aria-label="Open session">
                            <span class="session-name" title="${escapeHtml(sessionCreatedTitle)}">${escapeHtml(sessionLabel)}</span>
                            <span class="session-info">(${agentCount})</span>
                        </button>
                    </div>
                    <div class="session-header-right">
                        ${sessionUpdated ? `<span class="session-time" title="${escapeHtml(sessionUpdatedTitle)}">Updated ${escapeHtml(sessionUpdated)}</span>` : ''}
                        <button class="session-delete-btn" onclick="deleteSession('${sessionId}', event)" title="Delete session">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="3 6 5 6 21 6"></polyline>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                            </svg>
                        </button>
                    </div>
                </div>
                <div class="session-agents" id="session-${sessionId}" style="display: block;">
                    ${sessionData.agents.map(agent => {
                        const nowSeconds = Date.now() / 1000;
                        const lm = agent.last_modified || 0;
                        const isHot = lm && (nowSeconds - lm) < 45;
                        const updated = lm ? formatRelativeTimeFromEpochSeconds(lm) : '';
                        const updatedTitle = lm ? formatTimestamp(new Date(lm * 1000).toISOString()) : '';

                        const taskName = agent.task_name ? escapeHtml(agent.task_name) : null;
                        return `
                            <div class="agent-item" data-agent-id="${agent.id}" onclick="loadAgent('${agent.id}')">
                                <div class="agent-item-top">
                                    <div class="agent-item-name">${escapeHtml(agent.config_name)}${taskName ? `<span class="agent-task-name">${taskName}</span>` : ''}</div>
                                    <span class="agent-status-dot ${isHot ? 'hot' : ''}" title="${escapeHtml(updatedTitle)}"></span>
                                </div>
                                <div class="agent-item-details">
                                    <span class="agent-meta mono">${escapeHtml(agent.id.substring(0, 8))}</span>
                                    <span class="agent-meta">${agent.num_interactions} interactions</span>
                                    <span class="agent-meta">${agent.num_artifacts} artifacts</span>
                                    ${updated ? `<span class="agent-meta" title="${escapeHtml(updatedTitle)}">Updated ${escapeHtml(updated)}</span>` : ''}
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `;
    });

    listElement.innerHTML = html;

    if (currentAgentId) {
        const currentItem = listElement.querySelector(`[data-agent-id="${currentAgentId}"]`);
        if (currentItem) {
            currentItem.classList.add('active');
        }
    }
    if (currentSessionId) {
        const currentSession = listElement.querySelector(`[data-session-id="${currentSessionId}"]`);
        if (currentSession) {
            currentSession.classList.add('active');
        }
    }
}

function toggleSession(sessionId, event) {
    if (event) event.stopPropagation();
    const sessionAgents = document.getElementById(`session-${sessionId}`);
    const toggle = document.getElementById(`toggle-${sessionId}`);
    if (sessionAgents.style.display === 'none') {
        sessionAgents.style.display = 'block';
        toggle.classList.remove('collapsed');
    } else {
        sessionAgents.style.display = 'none';
        toggle.classList.add('collapsed');
    }
}

async function deleteSession(sessionId, event) {
    event.stopPropagation();

    const sessionGroup = document.querySelector(`[data-session-id="${sessionId}"]`);
    const sessionName = sessionGroup.querySelector('.session-name').textContent;

    if (!confirm(`Delete ${sessionName}?\n\nThis will permanently delete all agents, interactions, and artifacts in this session.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/session?id=${encodeURIComponent(sessionId)}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const error = await response.text();
            throw new Error(`Failed to delete session: ${error}`);
        }

        // Get agent IDs before removing from DOM
        const deletedAgentIds = [];
        const deletedAgents = sessionGroup.querySelectorAll('.agent-item');
        deletedAgents.forEach(agentItem => {
            const agentId = agentItem.getAttribute('data-agent-id');
            deletedAgentIds.push(agentId);
            if (agentId === currentAgentId) {
                currentAgentId = null;
                currentSessionId = null;
                document.getElementById('main-content-body').innerHTML =
                    '<div class="main-content-empty"><p>Select an agent from the left panel</p></div>';
                document.getElementById('agent-details-section').style.display = 'none';
                document.getElementById('filter-bar').style.display = 'none';
            }
        });

        // Remove from DOM
        sessionGroup.remove();

        // Update frontend data state (no refresh needed)
        deletedAgentIds.forEach(agentId => {
            delete agentsData[agentId];
        });
        lastAgentsList = lastAgentsList.filter(agent => !deletedAgentIds.includes(agent.id));

        // Clear current session if it was the deleted one
        if (currentSessionId === sessionId) {
            currentSessionId = null;
        }

        console.log(`Session ${sessionId} deleted with ${deletedAgentIds.length} agents`);
    } catch (error) {
        console.error('Error deleting session:', error);
        alert(`Error deleting session: ${error.message}`);
    }
}

// ==========================================================================
// Agent Loading
// ==========================================================================

async function loadAgent(agentId) {
    currentSessionId = null;
    currentAgentId = agentId;

    // Clear interaction detail cache for new agent
    interactionDetailCache = {};

    // Update active state
    document.querySelectorAll('.agent-item').forEach(item => {
        item.classList.remove('active');
    });
    document.querySelectorAll('.session-group').forEach(el => {
        el.classList.remove('active');
    });
    const item = document.querySelector(`[data-agent-id="${agentId}"]`);
    if (item) {
        item.classList.add('active');
    }

    // Show loading state
    document.getElementById('main-content-body').innerHTML =
        '<div class="loading"><span class="loading-spinner"></span>Loading agent...</div>';
    document.getElementById('main-title').textContent =
        `Agent: ${agentsData[agentId]?.config_name || 'Unknown'}`;
    document.getElementById('agent-details-section').style.display = 'none';
    document.getElementById('filter-bar').style.display = 'none';

    try {
        const response = await fetch(`/api/agent?id=${encodeURIComponent(agentId)}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        const html = data.html;
        const artifacts = data.artifacts;
        const interactions = data.interactions;
        const agentDetails = data.agent_details;

        // Store data globally
        window.artifactsData = artifacts;
        interactionsData = interactions;
        currentAgentDetails = agentDetails;

        // Reset and update branch filter for new agent
        activeBranchFilter = 'all';
        updateBranchFilter();

        // Display agent details bar
        displayAgentDetails(agentDetails);

        // Update status indicator for this agent
        updateAgentStatusIndicator(agentsData[agentId]);

        // Show filter bar
        document.getElementById('filter-bar').style.display = 'flex';

        // Extract and inject content
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        const container = doc.querySelector('.container');

        if (container) {
            const mainContentWrapper = container.querySelector('.main-content-wrapper');
            const mainContent = mainContentWrapper ? mainContentWrapper.querySelector('.main-content') : null;

            if (mainContent) {
                document.getElementById('main-content-body').innerHTML = mainContent.innerHTML;
            } else {
                document.getElementById('main-content-body').innerHTML = container.innerHTML;
            }

            // Initialize handlers and set default view
            initializeInteractionHandlers();
            setView(currentView);
        } else {
            document.getElementById('main-content-body').innerHTML = html;
        }
    } catch (error) {
        console.error('Error loading agent:', error);
        document.getElementById('main-content-body').innerHTML =
            '<div class="loading">Error loading agent: ' + escapeHtml(error.message) + '</div>';
    }
}

// ==========================================================================
// Session Loading
// ==========================================================================

async function loadSession(sessionId, event) {
    if (event) event.stopPropagation();

    currentAgentId = null;
    currentSessionId = sessionId;

    // Update active state
    document.querySelectorAll('.agent-item').forEach(item => {
        item.classList.remove('active');
    });
    document.querySelectorAll('.session-group').forEach(el => {
        el.classList.remove('active');
    });
    const sessionEl = document.querySelector(`[data-session-id="${sessionId}"]`);
    if (sessionEl) {
        sessionEl.classList.add('active');
    }

    // Show loading state
    document.getElementById('main-content-body').innerHTML =
        '<div class="loading"><span class="loading-spinner"></span>Loading session...</div>';
    document.getElementById('main-title').textContent =
        sessionId === 'unknown' ? 'Session: Unknown' : `Session: ${sessionId.substring(0, 8)}...`;
    document.getElementById('agent-details-section').style.display = 'none';
    document.getElementById('filter-bar').style.display = 'none';

    try {
        const response = await fetch(`/api/session?id=${encodeURIComponent(sessionId)}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        renderSessionView(data);

        // Hide status indicator for session view
        const indicator = document.getElementById('live-indicator');
        if (indicator) {
            indicator.style.display = 'none';
        }
    } catch (error) {
        console.error('Error loading session:', error);
        document.getElementById('main-content-body').innerHTML =
            '<div class="loading">Error loading session: ' + escapeHtml(error.message) + '</div>';
    }
}

function renderSessionView(session) {
    const sessionId = session.id || 'unknown';
    const createdAt = session.created_at ? formatTimestamp(session.created_at) : '';
    const updated = session.last_modified ? formatRelativeTimeFromEpochSeconds(session.last_modified) : '';
    const updatedTitle = session.last_modified ? formatTimestamp(new Date(session.last_modified * 1000).toISOString()) : '';
    const agents = Array.isArray(session.agents) ? session.agents : [];

    const agentsHtml = agents.length
        ? agents.map(agent => {
            const lm = agent.last_modified || 0;
            const agentUpdated = lm ? formatRelativeTimeFromEpochSeconds(lm) : '';
            const agentUpdatedTitle = lm ? formatTimestamp(new Date(lm * 1000).toISOString()) : '';
            return `
                <div class="session-agent-card">
                    <div class="session-agent-card-header">
                        <div class="session-agent-card-title">
                            <div class="session-agent-name">${escapeHtml(agent.config_name || 'Unknown')}</div>
                            <div class="session-agent-id mono">${escapeHtml((agent.id || '').substring(0, 12))}</div>
                        </div>
                        <button class="btn" onclick="loadAgent('${agent.id}')">Open</button>
                    </div>
                    <div class="session-agent-card-meta">
                        <span class="agent-meta">${agent.num_interactions || 0} interactions</span>
                        <span class="agent-meta">${agent.num_artifacts || 0} artifacts</span>
                        ${agentUpdated ? `<span class="agent-meta" title="${escapeHtml(agentUpdatedTitle)}">Updated ${escapeHtml(agentUpdated)}</span>` : ''}
                    </div>
                </div>
            `;
        }).join('')
        : '<div class="loading">No agents in this session</div>';

    document.getElementById('main-content-body').innerHTML = `
        <div class="session-view">
            <div class="session-view-header">
                <div>
                    <div class="session-view-title">Session ${escapeHtml(sessionId)}</div>
                    <div class="session-view-subtitle">
                        ${createdAt ? `<span>Created ${escapeHtml(createdAt)}</span>` : ''}
                        ${updated ? `<span title="${escapeHtml(updatedTitle)}">Updated ${escapeHtml(updated)}</span>` : ''}
                        <span>${agents.length} agent(s)</span>
                    </div>
                </div>
            </div>
            <div class="session-agent-grid">
                ${agentsHtml}
            </div>
        </div>
    `;
}

function displayAgentDetails(details) {
    if (!details) return;

    const detailsSection = document.getElementById('agent-details-section');
    const detailsContent = document.getElementById('agent-details-content');

    let html = '';

    html += `<div class="agent-detail-item">
        <span class="agent-detail-label">Config:</span>
        <span class="agent-detail-value">${escapeHtml(details.config_name)}</span>
    </div>`;

    html += `<div class="agent-detail-item">
        <span class="agent-detail-label">Interactions:</span>
        <span class="agent-detail-value">${details.num_interactions}</span>
    </div>`;

    html += `<div class="agent-detail-item">
        <span class="agent-detail-label">Artifacts:</span>
        <span class="agent-detail-value">${details.num_artifacts}</span>
    </div>`;

    if (details.config) {
        if (details.config.llm_model) {
            html += `<div class="agent-detail-item">
                <span class="agent-detail-label">Model:</span>
                <span class="agent-detail-value">${escapeHtml(details.config.llm_model)}</span>
            </div>`;
        }

        if (details.config.tools && Array.isArray(details.config.tools)) {
            html += `<div class="agent-detail-item">
                <span class="agent-detail-label">Tools:</span>
                <span class="agent-detail-value">${details.config.tools.length}</span>
            </div>`;
        }
    }

    if (details.created_at) {
        html += `<div class="agent-detail-item">
            <span class="agent-detail-label">Created:</span>
            <span class="agent-detail-value">${formatTimestamp(details.created_at)}</span>
        </div>`;
    }

    detailsContent.innerHTML = html;
    detailsSection.style.display = 'block';
}

// ==========================================================================
// Interaction Handlers
// ==========================================================================

function initializeInteractionHandlers() {
    // Make flowchart boxes clickable
    document.querySelectorAll('.flowchart-box').forEach(box => {
        box.style.cursor = 'pointer';
        box.onclick = function(e) {
            e.stopPropagation();
            const flowchartItem = box.closest('.flowchart-item');
            const interactionId = flowchartItem?.getAttribute('data-interaction-id');
            if (interactionId) {
                selectInteraction(interactionId);
                showInteractionDetails(interactionId);
            }
        };
    });

    // Handle artifact badges
    document.querySelectorAll('.flowchart-box-artifacts-badge').forEach(badge => {
        badge.style.cursor = 'pointer';
        badge.onclick = function(e) {
            e.stopPropagation();
            const flowchartItem = badge.closest('.flowchart-item');
            const interactionId = flowchartItem?.getAttribute('data-interaction-id');
            if (interactionId) {
                showInteractionDetails(interactionId, true);
            }
        };
    });

    // Make Timeline section EXPANDED by default
    const timelineSection = document.querySelector('.timeline-section');
    if (timelineSection) {
        const header = timelineSection.querySelector('h2');
        const content = timelineSection.querySelector('.timeline-view');
        if (header && content) {
            header.classList.add('expanded');
            content.classList.add('expanded');
            header.onclick = function(e) {
                e.stopPropagation();
                header.classList.toggle('expanded');
                content.classList.toggle('expanded');
            };
        }
    }

    // Make Stack Flow section COLLAPSED by default (flowchart less useful)
    const stackViz = document.querySelector('.stack-visualization');
    if (stackViz) {
        const header = stackViz.querySelector('h2');
        const flowchart = stackViz.querySelector('.flowchart');
        if (header && flowchart) {
            header.classList.remove('expanded');
            flowchart.classList.remove('expanded');
            header.onclick = function(e) {
                e.stopPropagation();
                header.classList.toggle('expanded');
                flowchart.classList.toggle('expanded');
            };
        }
    }

    // Make Artifacts List section EXPANDED by default
    const artifactsSection = document.querySelector('.artifacts-list-section');
    if (artifactsSection) {
        const header = artifactsSection.querySelector('h2');
        const content = artifactsSection.querySelector('.artifacts-list-content');
        if (header && content) {
            header.classList.add('expanded');
            content.classList.add('expanded');
            header.onclick = function(e) {
                e.stopPropagation();
                header.classList.toggle('expanded');
                content.classList.toggle('expanded');
            };
        }

        // Artifact item click handlers are now directly in HTML via onclick attribute
        // The onclick calls openArtifactModal(artifactId, interactionId)
        // The nested interaction link has stopPropagation to prevent modal from opening
    }

    // Make timeline items clickable
    document.querySelectorAll('.timeline-item').forEach(item => {
        item.style.cursor = 'pointer';
        item.onclick = function(e) {
            e.stopPropagation();
            const interactionId = item.getAttribute('data-interaction-id');
            if (interactionId) {
                selectInteraction(interactionId);
                showInteractionDetails(interactionId);
            }
        };
    });

    // Apply current view
    setView(currentView);
}

function selectInteraction(interactionId) {
    // Remove previous selection
    document.querySelectorAll('.flowchart-box-selected, .timeline-item.selected').forEach(el => {
        el.classList.remove('flowchart-box-selected', 'selected');
    });

    // Add selection to flowchart
    const flowchartItem = document.querySelector(`.flowchart-item[data-interaction-id="${interactionId}"]`);
    if (flowchartItem) {
        const box = flowchartItem.querySelector('.flowchart-box');
        if (box) box.classList.add('flowchart-box-selected');
    }

    // Add selection to timeline
    const timelineItem = document.querySelector(`.timeline-item[data-interaction-id="${interactionId}"]`);
    if (timelineItem) {
        timelineItem.classList.add('selected');
    }
}

// ==========================================================================
// Interaction Details Panel
// ==========================================================================

async function showInteractionDetails(interactionId, showArtifacts = false) {
    let interaction = interactionsData[interactionId];
    let artifacts = window.artifactsData?.[interactionId] || [];

    if (!interaction) {
        return;
    }

    // If interaction details are minimal (lazy loading mode), load full details
    if (needsInteractionDetailLoading(interaction)) {
        await ensureInteractionDetailsLoaded(interactionId);
        interaction = interactionsData[interactionId];
        artifacts = window.artifactsData?.[interactionId] || [];
    }
    // Otherwise just load artifacts if needed
    else if (needsArtifactLoading(interactionId)) {
        await ensureArtifactsLoaded(interactionId);
        artifacts = window.artifactsData?.[interactionId] || [];
    }

    const panel = document.getElementById('right-panel');
    const content = document.getElementById('right-panel-content');
    const title = document.getElementById('right-panel-title');

    let html = '';

    // Interaction details
    html += `<div class="artifact-panel-item">
        <div class="artifact-panel-item-header">
            <h4>${escapeHtml(interaction.type)}</h4>
            <span class="artifact-panel-item-id">${escapeHtml(interaction.id.substring(0, 12))}...</span>
        </div>
        <div class="artifact-panel-item-content">
            <div style="margin-bottom: 12px;">
                <strong>Type:</strong> ${escapeHtml(interaction.type)}<br>
                <strong>ID:</strong> <code style="font-size: 0.75rem;">${escapeHtml(interaction.id)}</code>`;

    if (interaction.created_at) {
        html += `<br><strong>Created:</strong> ${escapeHtml(formatTimestamp(interaction.created_at))}`;
    }

    html += `</div>`;

    // Branch info
    if (interaction.branch) {
        html += `<div class="badge badge-warning" style="margin-bottom: 12px;">
            Branch: ${escapeHtml(interaction.branch)}
        </div>`;
    }

    // Type-specific details (all fields now in colored boxes)
    html += renderInteractionTypeDetails(interaction);

    // Reason (shown last for any interaction that has it, except ToolCall which shows it in the box)
    if (interaction.reason && interaction.type !== 'ToolCall') {
        html += `<div style="margin-bottom: 12px; margin-top: 12px; padding: 8px 12px; background: var(--bg-tertiary); border-radius: var(--radius-md);">
            <strong>Reason:</strong> <em>${escapeHtml(interaction.reason)}</em>
        </div>`;
    }

    // Error status
    if (interaction.is_error !== undefined) {
        const badgeClass = interaction.is_error ? 'badge-error' : 'badge-success';
        html += `<div class="badge ${badgeClass}">${interaction.is_error ? 'Error' : 'Success'}</div>`;
    }

    html += `</div></div>`;

    // Artifacts section
    if (artifacts.length > 0) {
        html += `<div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border-light);">
            <h4 style="margin-bottom: 12px; font-size: 0.875rem;">Artifacts (${artifacts.length})</h4>`;

        artifacts.forEach((artifact, index) => {
            html += renderArtifactPill(artifact, interactionId, { interaction: interaction });
        });

        html += `</div>`;
    }

    content.innerHTML = html;
    title.textContent = showArtifacts && artifacts.length > 0 ? 'Details & Artifacts' : 'Interaction Details';
    panel.classList.remove('collapsed');
}

function renderInteractionTypeDetails(interaction) {
    let html = '';

    // TaskDefinition details
    if (interaction.type === 'TaskDefinition') {
        html += `<div style="margin-bottom: 12px; padding: 12px; background: var(--interaction-task); border-left: 3px solid var(--interaction-task-border); border-radius: var(--radius-md);">
            <strong>Task Definition</strong>`;
        if (interaction.task) {
            html += `<div style="margin-top: 8px;"><strong>Name:</strong> ${escapeHtml(interaction.task.name || 'Unknown')}</div>`;
            if (interaction.task.description) {
                html += `<div style="margin-top: 4px; color: var(--text-secondary);">${escapeHtml(interaction.task.description)}</div>`;
            }
            if (interaction.task.prompt) {
                html += `<div style="margin-top: 8px;">
                    <strong>Prompt:</strong>
                    <pre class="detail-code" style="margin-top: 4px; max-height: 150px; overflow-y: auto;">${escapeHtml(interaction.task.prompt)}</pre>
                </div>`;
            }
            if (interaction.task.parameters && Object.keys(interaction.task.parameters).length > 0) {
                const visibleParams = Object.fromEntries(
                    Object.entries(interaction.task.parameters).filter(([key]) => !key.startsWith('_'))
                );
                if (Object.keys(visibleParams).length > 0) {
                    html += `<div style="margin-top: 8px;">
                        <strong>Parameters:</strong>
                        <pre class="detail-code" style="margin-top: 4px; max-height: 150px; overflow-y: auto;">${escapeHtml(JSON.stringify(visibleParams, null, 2))}</pre>
                    </div>`;
                }
            }
        }
        html += `</div>`;
    }

    // AskOracle details
    if (interaction.type === 'AskOracle') {
        html += `<div style="margin-bottom: 12px; padding: 12px; background: var(--interaction-oracle); border-left: 3px solid var(--interaction-oracle-border); border-radius: var(--radius-md);">
            <strong>Oracle Request (LLM)</strong>`;
        if (interaction.prompt) {
            const prompt = interaction.prompt;
            if (prompt.type) {
                html += `<div style="margin-top: 8px;"><strong>Prompt Type:</strong> ${escapeHtml(prompt.type)}</div>`;
            }
            if (prompt.template_name) {
                html += `<div style="margin-top: 4px;"><strong>Template:</strong> ${escapeHtml(prompt.template_name)}</div>`;
            }
            if (prompt.tool_use_id) {
                html += `<div style="margin-top: 4px;"><strong>Tool Use ID:</strong> <code style="font-size: 0.75rem;">${escapeHtml(prompt.tool_use_id)}</code></div>`;
            }
            if (prompt.tool_name) {
                html += `<div style="margin-top: 4px;"><strong>Tool Name:</strong> ${escapeHtml(prompt.tool_name)}</div>`;
            }
            if (prompt.text) {
                html += `<div style="margin-top: 8px;">
                    <strong>Prompt Text:</strong>
                    <pre class="detail-code" style="margin-top: 4px; max-height: 200px; overflow-y: auto;">${escapeHtml(prompt.text)}</pre>
                </div>`;
            }
        }
        if (interaction.template_inputs && Object.keys(interaction.template_inputs).length > 0) {
            html += `<div style="margin-top: 8px;">
                <strong>Template Inputs:</strong>
                <pre class="detail-code" style="margin-top: 4px; max-height: 150px; overflow-y: auto;">${escapeHtml(JSON.stringify(interaction.template_inputs, null, 2))}</pre>
            </div>`;
        }
        if (interaction.include_in_context === false) {
            html += `<div style="margin-top: 8px;"><span class="badge badge-warning">Excluded from context</span></div>`;
        }
        html += `</div>`;
    }

    // OracleResponse details
    if (interaction.type === 'OracleResponse') {
        html += `<div style="margin-bottom: 12px; padding: 12px; background: var(--interaction-oracle); border-left: 3px solid var(--interaction-oracle-border); border-radius: var(--radius-md);">
            <strong>Oracle Response (LLM)</strong>`;
        if (interaction.response) {
            if (interaction.response.tool_call) {
                html += `<div style="margin-top: 8px;"><strong>Tool Call:</strong> <code>${escapeHtml(interaction.response.tool_call)}</code></div>`;
            }
            if (interaction.response.tool_call_id) {
                html += `<div style="margin-top: 4px;"><strong>Tool Call ID:</strong> <code style="font-size: 0.75rem;">${escapeHtml(interaction.response.tool_call_id)}</code></div>`;
            }
            if (interaction.response.content) {
                let displayContent = interaction.response.content;
                if (typeof displayContent === 'object' && displayContent.reason) {
                    html += `<div style="margin-top: 8px;"><strong>Reason:</strong> <em>${escapeHtml(displayContent.reason)}</em></div>`;
                    displayContent = Object.fromEntries(Object.entries(displayContent).filter(([k]) => k !== 'reason'));
                }
                if (Object.keys(displayContent).length > 0 || typeof displayContent === 'string') {
                    const contentStr = typeof displayContent === 'string' ? displayContent : JSON.stringify(displayContent, null, 2);
                    html += `<div style="margin-top: 8px;">
                        <strong>Content:</strong>
                        <pre class="detail-code" style="margin-top: 4px; max-height: 200px; overflow-y: auto;">${escapeHtml(contentStr)}</pre>
                    </div>`;
                }
            }
            // Show any other keys in the response not already handled
            const knownKeys = ['tool_call', 'tool_call_id', 'content'];
            const extraKeys = Object.keys(interaction.response).filter(k => !knownKeys.includes(k));
            for (const key of extraKeys) {
                const val = interaction.response[key];
                if (val === null || val === undefined) continue;
                const valStr = typeof val === 'object'
                    ? JSON.stringify(val, null, 2)
                    : String(val);
                html += `<div style="margin-top: 8px;">
                    <strong>${escapeHtml(key)}:</strong>
                    <pre class="detail-code" style="margin-top: 4px; max-height: 200px; overflow-y: auto;">${escapeHtml(valStr)}</pre>
                </div>`;
            }
        } else {
            html += `<div style="margin-top: 8px; color: var(--text-secondary);"><em>No response data</em></div>`;
        }
        html += `</div>`;
    }

    // ToolCall details
    if (interaction.type === 'ToolCall') {
        html += `<div style="margin-bottom: 12px; padding: 12px; background: var(--interaction-tool); border-left: 3px solid var(--interaction-tool-border); border-radius: var(--radius-md);">
            <strong>Tool Call</strong>`;
        if (interaction.tool) {
            html += `<div style="margin-top: 8px;"><strong>Tool:</strong> <code>${escapeHtml(interaction.tool)}</code></div>`;
        }
        if (interaction.tool_call_id) {
            html += `<div style="margin-top: 4px;"><strong>Tool Call ID:</strong> <code style="font-size: 0.75rem;">${escapeHtml(interaction.tool_call_id)}</code></div>`;
        }
        if (interaction.args) {
            const displayArgs = Object.fromEntries(
                Object.entries(interaction.args).filter(([key]) => !['stack', 'branch', 'reason'].includes(key))
            );
            if (Object.keys(displayArgs).length > 0) {
                html += `<div style="margin-top: 8px;">
                    <strong>Arguments:</strong>
                    <pre class="detail-code" style="margin-top: 4px; max-height: 200px; overflow-y: auto;">${escapeHtml(JSON.stringify(displayArgs, null, 2))}</pre>
                </div>`;
            }
        }
        if (interaction.reason) {
            html += `<div style="margin-top: 8px;"><strong>Reason:</strong> <em>${escapeHtml(interaction.reason)}</em></div>`;
        }
        html += `</div>`;
    }

    // ToolResult details
    if (interaction.type === 'ToolResult') {
        html += `<div style="margin-bottom: 12px; padding: 12px; background: var(--interaction-tool); border-left: 3px solid var(--interaction-tool-border); border-radius: var(--radius-md);">
            <strong>Tool Result</strong>`;
        if (interaction.tool_name) {
            html += `<div style="margin-top: 8px;"><strong>Tool:</strong> <code>${escapeHtml(interaction.tool_name)}</code></div>`;
        }
        if (interaction.tool_call_id) {
            html += `<div style="margin-top: 4px;"><strong>Tool Call ID:</strong> <code style="font-size: 0.75rem;">${escapeHtml(interaction.tool_call_id)}</code></div>`;
        }
        if (interaction.is_error) {
            html += `<div style="margin-top: 8px;"><span class="badge badge-error">Error</span></div>`;
        }
        if (interaction.result) {
            const resultStr = typeof interaction.result === 'object'
                ? JSON.stringify(interaction.result, null, 2)
                : String(interaction.result);
            html += `<div style="margin-top: 8px;">
                <strong>Result:</strong>
                <pre class="detail-code" style="margin-top: 4px; max-height: 200px; overflow-y: auto;">${escapeHtml(resultStr)}</pre>
            </div>`;
        }
        if (interaction.next_tool) {
            html += `<div style="margin-top: 8px;"><strong>Next Tool:</strong> <code>${escapeHtml(interaction.next_tool)}</code></div>`;
        }
        if (interaction.next_tool_args) {
            const argsStr = typeof interaction.next_tool_args === 'object'
                ? JSON.stringify(interaction.next_tool_args, null, 2)
                : String(interaction.next_tool_args);
            html += `<div style="margin-top: 8px;">
                <strong>Next Tool Args:</strong>
                <pre class="detail-code" style="margin-top: 4px; max-height: 150px; overflow-y: auto;">${escapeHtml(argsStr)}</pre>
            </div>`;
        }
        if (interaction.response_interaction) {
            const respStr = typeof interaction.response_interaction === 'object'
                ? JSON.stringify(interaction.response_interaction, null, 2)
                : String(interaction.response_interaction);
            html += `<div style="margin-top: 8px;"><strong>Response Interaction:</strong> <code>${escapeHtml(respStr)}</code></div>`;
        }
        if (interaction.include_in_context !== undefined) {
            const badge = interaction.include_in_context
                ? '<span class="badge badge-success">Yes</span>'
                : '<span class="badge badge-warning">No</span>';
            html += `<div style="margin-top: 8px;"><strong>Include in Context:</strong> ${badge}</div>`;
        }
        html += `</div>`;
    }

    // TaskResult details
    if (interaction.type === 'TaskResult') {
        const isSuccess = interaction.finish_type === 'success';
        const bgColor = isSuccess ? 'var(--interaction-result)' : 'var(--interaction-error)';
        const borderColor = isSuccess ? 'var(--interaction-result-border)' : 'var(--interaction-error-border)';
        html += `<div style="margin-bottom: 12px; padding: 12px; background: ${bgColor}; border-left: 3px solid ${borderColor}; border-radius: var(--radius-md);">
            <strong>Task ${isSuccess ? 'Completed' : 'Failed'}</strong>`;
        if (interaction.summary) {
            html += `<div style="margin-top: 8px;"><strong>Summary:</strong> ${escapeHtml(interaction.summary)}</div>`;
        }
        if (interaction.result) {
            const resultStr = typeof interaction.result === 'object'
                ? JSON.stringify(interaction.result, null, 2)
                : String(interaction.result);
            html += `<div style="margin-top: 8px;">
                <strong>Result:</strong>
                <pre class="detail-code" style="margin-top: 4px; max-height: 200px; overflow-y: auto;">${escapeHtml(resultStr)}</pre>
            </div>`;
        }
        html += `</div>`;
    }

    // TaskChain details
    if (interaction.type === 'TaskChain') {
        html += `<div style="margin-bottom: 12px; padding: 12px; background: var(--interaction-task); border-left: 3px solid var(--interaction-task-border); border-radius: var(--radius-md);">
            <strong>Task Chain</strong>`;
        if (interaction.next_task_name) {
            html += `<div style="margin-top: 8px;"><strong>Next Task:</strong> ${escapeHtml(interaction.next_task_name)}</div>`;
        }
        if (interaction.task_sequence && interaction.task_sequence.length > 0) {
            const seqIdx = interaction.sequence_index || 0;
            html += `<div style="margin-top: 8px;"><strong>Sequence:</strong> ${escapeHtml(interaction.task_sequence.join(' → '))}</div>`;
            html += `<div style="margin-top: 4px;"><strong>Current Index:</strong> ${seqIdx}</div>`;
        }
        if (interaction.chain_config) {
            html += `<div style="margin-top: 8px;"><strong>Chain Config:</strong> ${escapeHtml(interaction.chain_config)}</div>`;
        }
        if (interaction.previous_result) {
            const resultStr = typeof interaction.previous_result === 'object'
                ? JSON.stringify(interaction.previous_result, null, 2)
                : String(interaction.previous_result);
            html += `<div style="margin-top: 8px;">
                <strong>Previous Result:</strong>
                <pre class="detail-code" style="margin-top: 4px; max-height: 200px; overflow-y: auto;">${escapeHtml(resultStr)}</pre>
            </div>`;
        }
        html += `</div>`;
    }

    // AgentCall details
    if (interaction.type === 'AgentCall') {
        html += `<div style="margin-bottom: 12px; padding: 12px; background: var(--interaction-task); border-left: 3px solid var(--interaction-task-border); border-radius: var(--radius-md);">
            <strong>Agent Call</strong>`;
        // Config info - check both formats
        const configName = interaction.config_name || (interaction.config && interaction.config.name);
        if (configName) {
            html += `<div style="margin-top: 8px;"><strong>Config:</strong> ${escapeHtml(configName)}</div>`;
        }
        // Task info
        if (interaction.task) {
            if (interaction.task.name) {
                html += `<div style="margin-top: 4px;"><strong>Task:</strong> ${escapeHtml(interaction.task.name)}</div>`;
            }
            if (interaction.task.description) {
                html += `<div style="margin-top: 4px;"><strong>Description:</strong> ${escapeHtml(interaction.task.description)}</div>`;
            }
            // Show task prompt (truncated)
            if (interaction.task.prompt) {
                const promptPreview = interaction.task.prompt.length > 200
                    ? interaction.task.prompt.substring(0, 200) + '...'
                    : interaction.task.prompt;
                html += `<div style="margin-top: 8px;">
                    <strong>Prompt:</strong>
                    <pre class="detail-code" style="margin-top: 4px; max-height: 150px; overflow-y: auto; font-size: 0.75rem;">${escapeHtml(promptPreview)}</pre>
                </div>`;
            }
        }
        // Agent ID with view button
        if (interaction.agent_id) {
            html += `<div style="margin-top: 8px;"><strong>Agent ID:</strong> <code style="font-size: 0.75rem;">${escapeHtml(interaction.agent_id)}</code></div>`;
            html += `<button class="btn" style="margin-top: 8px;" onclick="loadAgent('${escapeHtml(interaction.agent_id)}')">View Child Agent</button>`;
        }
        html += `</div>`;
    }

    // AgentResult details
    if (interaction.type === 'AgentResult') {
        const placeholderId = 'agent-result-' + (interaction.id || interaction.task_result_id || Math.random().toString(36).slice(2));
        html += `<div id="${placeholderId}" style="margin-bottom: 12px; padding: 12px; background: var(--interaction-task); border-left: 3px solid var(--interaction-task-border); border-radius: var(--radius-md);">
            <strong>Agent Result</strong>
            <div style="margin-top: 8px; color: #888; font-style: italic;">Loading result...</div>
        </div>`;
        // Caller ID (legacy support)
        if (interaction.caller_id) {
            html += `<div style="margin-top: 8px;"><strong>Caller ID:</strong> <code style="font-size: 0.75rem;">${escapeHtml(interaction.caller_id)}</code></div>`;
        }
        // Fetch the referenced TaskResult asynchronously
        if (interaction.task_result_id) {
            loadInteractionDetail(interaction.task_result_id).then(function(data) {
                const el = document.getElementById(placeholderId);
                if (!el) return;
                const tr = data && data.interaction ? (data.interaction.data || data.interaction) : null;
                if (!tr) {
                    el.innerHTML = '<strong>Agent Result</strong><div style="margin-top: 8px; color: #888;">Could not load task result.</div>';
                    return;
                }
                const isSuccess = tr.finish_type === 'success';
                const bgColor = isSuccess ? 'var(--interaction-result)' : 'var(--interaction-error)';
                const borderColor = isSuccess ? 'var(--interaction-result-border)' : 'var(--interaction-error-border)';
                el.style.background = bgColor;
                el.style.borderLeftColor = borderColor;
                let inner = '<strong>Agent ' + (isSuccess ? 'Completed' : 'Failed') + '</strong>';
                if (tr.summary) {
                    inner += '<div style="margin-top: 8px;"><strong>Summary:</strong> ' + escapeHtml(tr.summary) + '</div>';
                }
                if (tr.result) {
                    const resultStr = typeof tr.result === 'object'
                        ? JSON.stringify(tr.result, null, 2)
                        : String(tr.result);
                    inner += '<div style="margin-top: 8px;"><strong>Result:</strong>' +
                        '<pre class="detail-code" style="margin-top: 4px; max-height: 200px; overflow-y: auto;">' + escapeHtml(resultStr) + '</pre></div>';
                }
                el.innerHTML = inner;
            }).catch(function() {
                const el = document.getElementById(placeholderId);
                if (el) {
                    el.innerHTML = '<strong>Agent Result</strong><div style="margin-top: 8px; color: #888;">Could not load task result.</div>';
                }
            });
        }
    }

    // AskHuman details
    if (interaction.type === 'AskHuman') {
        html += `<div style="margin-bottom: 12px; padding: 12px; background: var(--interaction-human); border-left: 3px solid var(--interaction-human-border); border-radius: var(--radius-md);">
            <strong>Ask Human</strong>`;
        if (interaction.question) {
            html += `<div style="margin-top: 8px;">
                <strong>Question:</strong>
                <pre class="detail-code" style="margin-top: 4px; max-height: 200px; overflow-y: auto;">${escapeHtml(interaction.question)}</pre>
            </div>`;
        }
        html += `</div>`;
    }

    // HumanResponse details
    if (interaction.type === 'HumanResponse') {
        html += `<div style="margin-bottom: 12px; padding: 12px; background: var(--interaction-human); border-left: 3px solid var(--interaction-human-border); border-radius: var(--radius-md);">
            <strong>Human Response</strong>`;
        if (interaction.response) {
            html += `<div style="margin-top: 8px;">
                <strong>Response:</strong>
                <pre class="detail-code" style="margin-top: 4px; max-height: 200px; overflow-y: auto;">${escapeHtml(typeof interaction.response === 'object' ? JSON.stringify(interaction.response, null, 2) : interaction.response)}</pre>
            </div>`;
        }
        html += `</div>`;
    }

    // ExternalInput details
    if (interaction.type === 'ExternalInput') {
        html += `<div style="margin-bottom: 12px; padding: 12px; background: var(--interaction-human); border-left: 3px solid var(--interaction-human-border); border-radius: var(--radius-md);">
            <strong>External Input</strong>`;
        if (interaction.input) {
            html += `<div style="margin-top: 8px;">
                <strong>Input:</strong>
                <pre class="detail-code" style="margin-top: 4px; max-height: 200px; overflow-y: auto;">${escapeHtml(interaction.input)}</pre>
            </div>`;
        }
        html += `</div>`;
    }

    // Waiting details
    if (interaction.type === 'Waiting') {
        html += `<div style="margin-bottom: 12px; padding: 12px; background: var(--bg-tertiary); border-left: 3px solid var(--border-light); border-radius: var(--radius-md);">
            <strong>Waiting</strong>`;
        if (interaction.status) {
            html += `<div style="margin-top: 8px;"><strong>Status:</strong> ${escapeHtml(interaction.status)}</div>`;
        }
        if (interaction.condition) {
            html += `<div style="margin-top: 8px;"><strong>Condition:</strong> <code>${escapeHtml(interaction.condition.evaluator)}</code></div>`;
            if (interaction.condition.parameters && Object.keys(interaction.condition.parameters).length > 0) {
                html += `<div style="margin-top: 4px;">
                    <strong>Condition Parameters:</strong>
                    <pre class="detail-code" style="margin-top: 4px; max-height: 150px; overflow-y: auto;">${escapeHtml(JSON.stringify(interaction.condition.parameters, null, 2))}</pre>
                </div>`;
            }
        }
        if (interaction.next_tool) {
            html += `<div style="margin-top: 8px;"><strong>Next Tool:</strong> <code>${escapeHtml(interaction.next_tool)}</code></div>`;
        }
        if (interaction.next_tool_args && Object.keys(interaction.next_tool_args).length > 0) {
            html += `<div style="margin-top: 4px;">
                <strong>Next Tool Args:</strong>
                <pre class="detail-code" style="margin-top: 4px; max-height: 150px; overflow-y: auto;">${escapeHtml(JSON.stringify(interaction.next_tool_args, null, 2))}</pre>
            </div>`;
        }
        html += `</div>`;
    }

    return html;
}

function closeRightPanel() {
    document.getElementById('right-panel').classList.add('collapsed');
}

// ==========================================================================
// Artifact Modal
// ==========================================================================

async function openArtifactModal(artifactId, interactionId) {
    // Track current artifact for modal actions (fullscreen, new tab)
    currentArtifactId = artifactId;
    currentInteractionId = interactionId;

    const artifacts = window.artifactsData?.[interactionId] || [];
    const artifact = artifacts.find(a => a.id === artifactId);
    const interaction = interactionsData[interactionId];

    // If artifact doesn't have full HTML content, load it on demand
    if (!artifact || !artifact.html) {
        await loadAndOpenArtifact(artifactId, interactionId);
        return;
    }

    const modal = document.getElementById('artifact-modal');
    const typeEl = document.getElementById('modal-artifact-type');
    const idEl = document.getElementById('modal-artifact-id');
    const metaEl = document.getElementById('modal-artifact-meta');
    const contentEl = document.getElementById('modal-artifact-content');

    // Set header
    typeEl.textContent = artifact.type;
    idEl.textContent = artifactId.substring(0, 12) + '...';

    // Build metadata
    let metaHtml = '';

    // Parent interaction info
    if (interaction) {
        const shortInteractionId = interactionId.substring(0, 12) + '...';
        metaHtml += `
            <div class="modal-meta-item">
                <span class="modal-meta-label">Parent:</span>
                <span class="modal-meta-value clickable" onclick="closeArtifactModal(); showInteractionDetails('${interactionId}')">
                    ${escapeHtml(interaction.type)}
                    <code>${shortInteractionId}</code>
                </span>
            </div>
        `;

        // Tool name if applicable
        if (interaction.tool_name || interaction.tool) {
            metaHtml += `
                <div class="modal-meta-item">
                    <span class="modal-meta-label">Tool:</span>
                    <span class="modal-meta-value">${escapeHtml(interaction.tool_name || interaction.tool)}</span>
                </div>
            `;
        }

        // Timestamp
        if (interaction.created_at) {
            metaHtml += `
                <div class="modal-meta-item">
                    <span class="modal-meta-label">Created:</span>
                    <span class="modal-meta-value">${formatTimestamp(interaction.created_at)}</span>
                </div>
            `;
        }
    }

    // Full artifact ID for reference
    metaHtml += `
        <div class="modal-meta-item">
            <span class="modal-meta-label">ID:</span>
            <span class="modal-meta-value"><code>${escapeHtml(artifactId)}</code></span>
        </div>
    `;

    metaEl.innerHTML = metaHtml;

    // Set content - use the pre-rendered HTML from the server
    contentEl.innerHTML = `<div class="artifact-content">${artifact.html}</div>`;

    // Show modal
    modal.classList.add('visible');

    // Add keyboard listener for Escape
    document.addEventListener('keydown', handleModalEscape);
}

function closeArtifactModal(event) {
    // If called from backdrop click, check if target is the modal backdrop
    if (event && event.target !== document.getElementById('artifact-modal')) {
        return;
    }

    const modal = document.getElementById('artifact-modal');
    modal.classList.remove('visible');
    modal.classList.remove('fullscreen');

    // Clear current artifact tracking
    currentArtifactId = null;
    currentInteractionId = null;

    // Reset fullscreen button icon
    resetFullscreenButton();

    // Remove keyboard listener
    document.removeEventListener('keydown', handleModalEscape);
}

function handleModalEscape(e) {
    if (e.key === 'Escape') {
        closeArtifactModal();
    } else if (e.key === 'f' || e.key === 'F') {
        // Don't trigger if user is typing in an input
        if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
            toggleArtifactFullscreen();
        }
    } else if (e.key === 'd' || e.key === 'D') {
        // Don't trigger if user is typing in an input
        if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
            downloadArtifact();
        }
    }
}

function toggleArtifactFullscreen() {
    const modal = document.getElementById('artifact-modal');
    const btn = document.getElementById('modal-fullscreen-btn');

    modal.classList.toggle('fullscreen');

    const isFullscreen = modal.classList.contains('fullscreen');

    // Update button icon and title
    if (isFullscreen) {
        btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 14h6m0 0v6m0-6L3 21M20 10h-6m0 0V4m0 6l7-7"/>
        </svg>`;
        btn.title = 'Exit Fullscreen (F)';
    } else {
        resetFullscreenButton();
    }
}

function resetFullscreenButton() {
    const btn = document.getElementById('modal-fullscreen-btn');
    if (btn) {
        btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
        </svg>`;
        btn.title = 'Toggle Fullscreen (F)';
    }
}

function openArtifactInNewTab() {
    if (!currentArtifactId) return;
    const url = `/artifact-viewer?id=${encodeURIComponent(currentArtifactId)}`;
    window.open(url, '_blank');
}

function downloadArtifact() {
    if (!currentArtifactId) return;
    // Create a temporary link and trigger download
    const url = `/api/artifact-download?id=${encodeURIComponent(currentArtifactId)}`;
    const link = document.createElement('a');
    link.href = url;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// ==========================================================================
// Lazy Artifact Loading
// ==========================================================================

/**
 * Load full interaction details (with artifacts) on demand.
 * Uses cache to avoid re-fetching already loaded interactions.
 */
async function loadInteractionDetail(interactionId) {
    // Check cache first
    if (interactionDetailCache[interactionId]) {
        return interactionDetailCache[interactionId];
    }

    try {
        const response = await fetch(`/api/interaction?id=${encodeURIComponent(interactionId)}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();

        // Cache the result
        interactionDetailCache[interactionId] = data;

        // Update artifactsData with loaded artifacts
        if (data.artifacts && data.artifacts.length > 0) {
            window.artifactsData = window.artifactsData || {};
            window.artifactsData[interactionId] = data.artifacts;
        }

        // Update interactionsData with full interaction details
        if (data.interaction) {
            const fullInteraction = data.interaction.data || data.interaction;
            fullInteraction.id = interactionId;
            fullInteraction.type = data.interaction.type || fullInteraction.type;
            // Merge with existing data (preserve any fields not in the response)
            interactionsData[interactionId] = {
                ...interactionsData[interactionId],
                ...fullInteraction,
                _fullyLoaded: true  // Mark as fully loaded
            };
        }

        return data;
    } catch (error) {
        console.error('Error loading interaction detail:', error);
        return null;
    }
}

/**
 * Load and open artifact modal. Used for lazy-loaded artifacts.
 */
async function loadAndOpenArtifact(artifactId, interactionId) {
    // Show loading state
    const modal = document.getElementById('artifact-modal');
    const contentEl = document.getElementById('modal-artifact-content');
    const typeEl = document.getElementById('modal-artifact-type');
    const idEl = document.getElementById('modal-artifact-id');

    typeEl.textContent = 'Loading...';
    idEl.textContent = artifactId.substring(0, 12) + '...';
    contentEl.innerHTML = '<div class="loading"><span class="loading-spinner"></span>Loading artifact...</div>';
    modal.classList.add('visible');

    // Load interaction detail (which includes artifacts)
    const data = await loadInteractionDetail(interactionId);

    if (!data || !data.artifacts) {
        contentEl.innerHTML = '<div class="loading">Error loading artifact</div>';
        return;
    }

    const artifact = data.artifacts.find(a => a.id === artifactId);
    if (!artifact) {
        contentEl.innerHTML = '<div class="loading">Artifact not found</div>';
        return;
    }

    // Update modal with loaded artifact
    typeEl.textContent = artifact.type;
    contentEl.innerHTML = `<div class="artifact-content">${artifact.html}</div>`;

    // Update artifact list item if it exists (replace "pending" placeholder)
    updateArtifactListItem(artifactId, interactionId, artifact);
}

/**
 * Update an artifact list item from "pending" to loaded state.
 */
function updateArtifactListItem(artifactId, interactionId, artifact) {
    const listItem = document.querySelector(`.artifacts-list-item[data-artifact-id="${artifactId}"]`);
    if (!listItem) return;

    // Remove pending class
    listItem.classList.remove('artifacts-list-item-pending');

    // Update type
    const typeEl = listItem.querySelector('.artifacts-list-item-type');
    if (typeEl) {
        typeEl.textContent = artifact.type;
    }

    // Update preview
    const previewEl = listItem.querySelector('.artifacts-list-item-preview');
    if (previewEl && artifact.preview) {
        const truncatedPreview = artifact.preview.length > 100
            ? artifact.preview.substring(0, 100) + '...'
            : artifact.preview;
        previewEl.textContent = truncatedPreview;
    }

    // Add format badge if available
    if (artifact.format) {
        const titleEl = listItem.querySelector('.artifacts-list-item-title');
        if (titleEl && !titleEl.querySelector('.artifacts-list-item-format')) {
            const formatSpan = document.createElement('span');
            formatSpan.className = 'artifacts-list-item-format';
            formatSpan.textContent = artifact.format;
            titleEl.appendChild(formatSpan);
        }
    }
}

/**
 * Check if artifacts need to be loaded for an interaction.
 * Returns true if any artifacts are missing full HTML content.
 */
function needsArtifactLoading(interactionId) {
    const artifacts = window.artifactsData?.[interactionId] || [];
    // Check if any artifacts are missing HTML content (lightweight metadata only)
    return artifacts.some(a => !a.html);
}

/**
 * Check if interaction details need to be loaded (lightweight mode).
 * Returns true if the interaction only has basic metadata from lightweight loading.
 */
function needsInteractionDetailLoading(interaction) {
    if (!interaction) return false;
    // If already fully loaded, no need to load again
    if (interaction._fullyLoaded) return false;
    // Always load full details for any interaction not yet marked as fully loaded
    // This ensures all interaction types show their complete details
    return true;
}

/**
 * Ensure full interaction details are loaded before showing.
 */
async function ensureInteractionDetailsLoaded(interactionId) {
    await loadInteractionDetail(interactionId);
}

/**
 * Ensure artifacts are loaded for an interaction before showing details.
 */
async function ensureArtifactsLoaded(interactionId) {
    if (!needsArtifactLoading(interactionId)) {
        return; // Already loaded
    }

    await loadInteractionDetail(interactionId);
}

// ==========================================================================
// Left Panel Toggle
// ==========================================================================

function toggleLeftPanel() {
    const panel = document.getElementById('left-panel');
    panel.classList.toggle('collapsed');
    localStorage.setItem(
        'monitor-left-panel-collapsed',
        panel.classList.contains('collapsed') ? 'true' : 'false'
    );
}

// ==========================================================================
// Utility Functions
// ==========================================================================

function formatTimestamp(timestamp) {
    if (!timestamp) return '';
    try {
        const date = new Date(timestamp);
        return date.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    } catch (e) {
        return timestamp;
    }
}

function formatRelativeTimeFromEpochSeconds(epochSeconds) {
    if (!epochSeconds) return '';
    const nowSeconds = Date.now() / 1000;
    const deltaSeconds = Math.max(0, nowSeconds - epochSeconds);

    if (deltaSeconds < 5) return 'just now';
    if (deltaSeconds < 60) return `${Math.floor(deltaSeconds)}s ago`;

    const minutes = Math.floor(deltaSeconds / 60);
    if (minutes < 60) return `${minutes}m ago`;

    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;

    const days = Math.floor(hours / 24);
    return `${days}d ago`;
}

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Render an artifact as a compact item matching the main artifacts list style.
 * Reusable across sidebar and main artifacts list.
 * Shows only metadata (type, format, id) - no content preview.
 */
function renderArtifactPill(artifact, interactionId, options = {}) {
    const { showInteractionInfo = false, interaction = null } = options;
    const shortId = artifact.id.substring(0, 8) + '...';

    let interactionHtml = '';
    if (showInteractionInfo && interaction) {
        const shortInteractionId = interactionId.substring(0, 8) + '...';
        interactionHtml = `
            <div class="artifacts-list-item-interaction" onclick="showInteractionDetails('${escapeHtml(interactionId)}', true); event.stopPropagation();">
                <span class="artifacts-list-item-interaction-label">From:</span>
                <span class="artifacts-list-item-interaction-type">${escapeHtml(interaction.type)}</span>
                <span class="artifacts-list-item-interaction-id">${shortInteractionId}</span>
            </div>
        `;
    }

    // Format badge (if available)
    let formatHtml = '';
    if (artifact.format) {
        formatHtml = `<span class="artifacts-list-item-format">${escapeHtml(artifact.format)}</span>`;
    }

    // Tool name from interaction
    let toolHtml = '';
    if (interaction && (interaction.tool_name || interaction.tool)) {
        const toolName = interaction.tool_name || interaction.tool;
        toolHtml = `<span class="artifacts-list-item-tool">${escapeHtml(toolName)}</span>`;
    }

    // Timestamp (formatted to second precision)
    let timestampHtml = '';
    if (artifact.created_at) {
        const formattedTime = formatTimestamp(artifact.created_at);
        timestampHtml = `<span class="artifacts-list-item-time">${escapeHtml(formattedTime)}</span>`;
    }

    return `
        <div class="artifacts-list-item" data-artifact-id="${escapeHtml(artifact.id)}" data-interaction-id="${escapeHtml(interactionId)}">
            <div class="artifacts-list-item-header">
                <div class="artifacts-list-item-title">
                    <span class="artifacts-list-item-type">${escapeHtml(artifact.type)}</span>
                    ${formatHtml}
                    ${toolHtml}
                </div>
                <div class="artifacts-list-item-meta">
                    ${timestampHtml}
                    <span class="artifacts-list-item-id">${escapeHtml(shortId)}</span>
                </div>
            </div>
            ${interactionHtml}
            <button class="artifacts-list-item-open" onclick="openArtifactModal('${escapeHtml(artifact.id)}', '${escapeHtml(interactionId)}'); event.stopPropagation();" title="Open in modal">Open</button>
        </div>
    `;
}

function scrollToArtifacts(interactionId) {
    showInteractionDetails(interactionId, true);
}

// Auto-refresh every 30 seconds
setInterval(refreshAgents, 30000);
