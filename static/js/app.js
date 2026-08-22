/**
 * Event Money Tracker - High Performance SPA Controller
 * Featuring 0ms Latency Optimistic UI, Client-side State Store, and Non-blocking Background Sync.
 */

// ============================================================================
// CLIENT-SIDE IN-MEMORY STATE STORE
// ============================================================================
const AppState = {
    currentEventId: null,
    currentCurrency: '₹',
    events: [],
    categories: [],
    transactions: [],
    analytics: null,
    isInitialLoaded: false
};

let categoryChartInstance = null;

// ============================================================================
// INITIALIZATION ON DOM READY
// ============================================================================
document.addEventListener('DOMContentLoaded', () => {
    const selector = document.getElementById('event-selector');
    if (selector && selector.value) {
        AppState.currentEventId = parseInt(selector.value);
    }

    // Set today's date in transaction date input
    const todayStr = new Date().toISOString().split('T')[0];
    const txnDateInput = document.getElementById('modal-txn-date');
    if (txnDateInput) txnDateInput.value = todayStr;

    // Handle hash navigation
    const initialTab = (window.location.hash.replace('#', '') || 'overview').toLowerCase();
    switchTab(initialTab);

    // Initial Data Preload
    if (AppState.currentEventId) {
        loadEventFullData(AppState.currentEventId, true);
    }
});

// ============================================================================
// 0ms INSTANT TAB SWITCHER
// ============================================================================
function switchTab(tabId) {
    if (!tabId) return;

    // Hide all tabs & deactivate buttons
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));

    // Activate selected content & button
    const targetContent = document.getElementById(`tab-${tabId}`);
    const targetBtn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);

    if (targetContent) targetContent.classList.add('active');
    if (targetBtn) targetBtn.classList.add('active');

    // Update URL hash without jumping
    if (history.pushState) {
        history.pushState(null, null, `#${tabId}`);
    } else {
        location.hash = `#${tabId}`;
    }

    // 0ms Instant Render from memory
    if (tabId === 'categories') {
        if (AppState.categories && AppState.categories.length > 0) {
            renderCategoriesGrid(AppState.categories);
        } else if (AppState.currentEventId) {
            loadCategoriesTab(AppState.currentEventId, false);
        }
    } else if (tabId === 'transactions') {
        if (AppState.transactions && AppState.transactions.length > 0) {
            renderMainTransactionsTable(AppState.transactions);
        } else if (AppState.currentEventId) {
            loadTransactionsTab(AppState.currentEventId, false);
        }
    } else if (tabId === 'admin') {
        loadAdminStats();
    } else if (tabId === 'drive') {
        loadUserDriveFolders();
    }
}

// ============================================================================
// EVENT SELECTION & FAST DATA PREFETCH
// ============================================================================
function onEventSelectChange(eventId) {
    if (!eventId) return;
    AppState.currentEventId = parseInt(eventId);
    loadEventFullData(AppState.currentEventId);
}

async function loadEventFullData(eventId, silent = false) {
    if (!eventId) return;

    try {
        // Parallel non-blocking prefetch
        const [analyticsRes, txnsRes, catsRes] = await Promise.all([
            fetch(`/api/events/${eventId}/analytics`),
            fetch(`/api/events/${eventId}/transactions`),
            fetch(`/api/events/${eventId}/categories`)
        ]);

        const analyticsData = analyticsRes.ok ? await analyticsRes.json() : { status: 'error' };
        const txnsData = txnsRes.ok ? await txnsRes.json() : { status: 'error' };
        const catsData = catsRes.ok ? await catsRes.json() : { status: 'error' };

        if (analyticsData.status === 'success') {
            AppState.analytics = analyticsData.analytics;
            const ev = AppState.analytics.event;
            AppState.currentCurrency = ev.currency === 'INR' ? '₹' : (ev.currency === 'USD' ? '$' : ev.currency);

            // Update currency symbols
            document.querySelectorAll('.currency-symbol').forEach(el => el.textContent = AppState.currentCurrency);
            const modalCurr = document.getElementById('modal-curr-symbol');
            if (modalCurr) modalCurr.textContent = AppState.currentCurrency;

            // Render Overview metrics
            updateStatsUI(AppState.analytics.summary);
            updateCategoryChart(AppState.analytics.category_breakdown);
            updateLeaderboardsUI(AppState.analytics.top_contributors, AppState.analytics.top_payees);
            renderRecentTable(AppState.analytics.recent_transactions);
        }

        if (catsData.status === 'success') {
            AppState.categories = catsData.categories || [];
            populateCategoryDropdowns(AppState.categories);
            renderCategoriesGrid(AppState.categories);
        }

        if (txnsData.status === 'success') {
            AppState.transactions = txnsData.transactions || [];
            renderMainTransactionsTable(AppState.transactions);
        }

        AppState.isInitialLoaded = true;
    } catch (err) {
        console.error('Failed to sync event data:', err);
        if (!silent) showToast('Failed to refresh latest event data', 'error');
    }
}

// ============================================================================
// OVERVIEW & METRICS RENDERING
// ============================================================================
function updateStatsUI(summary) {
    if (!summary) return;
    const incEl = document.getElementById('stat-total-income');
    const expEl = document.getElementById('stat-total-expense');
    const netEl = document.getElementById('stat-net-balance');
    const budLimitEl = document.getElementById('stat-budget-limit');
    const budBar = document.getElementById('stat-budget-bar');
    const budUsed = document.getElementById('stat-budget-used');
    const budRemain = document.getElementById('stat-budget-remain');

    if (incEl) incEl.querySelector('.stat-number').textContent = formatNumber(summary.total_income);
    if (expEl) expEl.querySelector('.stat-number').textContent = formatNumber(summary.total_expense);
    
    if (netEl) {
        const netNum = netEl.querySelector('.stat-number');
        netNum.textContent = formatNumber(summary.net_balance);
        netNum.className = `stat-number ${summary.net_balance >= 0 ? 'text-emerald-400' : 'text-rose-400'}`;
    }

    if (budLimitEl) budLimitEl.querySelector('.stat-number').textContent = formatNumber(summary.budget_limit || 0);
    if (budBar) budBar.style.width = `${Math.min(summary.budget_utilization || 0, 100)}%`;
    if (budUsed) budUsed.textContent = `${summary.budget_utilization || 0}% Spent`;
    if (budRemain) {
        budRemain.textContent = summary.budget_remaining !== null 
            ? `${formatNumber(summary.budget_remaining)} left` 
            : 'No Limit';
    }
}

function updateLeaderboardsUI(contributors, payees) {
    const contList = document.getElementById('top-contributors-list');
    const payList = document.getElementById('top-payees-list');

    if (contList) {
        if (!contributors || contributors.length === 0) {
            contList.innerHTML = '<p class="text-xs text-slate-400 py-3 text-center">No incoming gifts recorded yet.</p>';
        } else {
            contList.innerHTML = contributors.map(c => `
                <div class="leaderboard-row">
                    <span class="font-medium text-slate-200">${escapeHtml(c.name)}</span>
                    <span class="font-bold text-emerald-400">+ ${AppState.currentCurrency} ${formatNumber(c.amount)}</span>
                </div>
            `).join('');
        }
    }

    if (payList) {
        if (!payees || payees.length === 0) {
            payList.innerHTML = '<p class="text-xs text-slate-400 py-3 text-center">No expenses recorded yet.</p>';
        } else {
            payList.innerHTML = payees.map(p => `
                <div class="leaderboard-row">
                    <span class="font-medium text-slate-200">${escapeHtml(p.name)}</span>
                    <span class="font-bold text-rose-400">- ${AppState.currentCurrency} ${formatNumber(p.amount)}</span>
                </div>
            `).join('');
        }
    }
}

function renderRecentTable(txns) {
    const tbody = document.getElementById('overview-recent-tbody');
    if (!tbody) return;

    if (!txns || txns.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center py-6 text-slate-400 text-xs">No transactions recorded yet.</td></tr>';
        return;
    }

    tbody.innerHTML = txns.map(t => `
        <tr>
            <td class="text-xs text-slate-400 whitespace-nowrap">${formatDate(t.transaction_date)}</td>
            <td>
                <span class="${t.type === 'INCOME' ? 'badge-income' : 'badge-expense'}">
                    ${t.type === 'INCOME' ? 'GIFT / IN' : 'EXPENSE'}
                </span>
            </td>
            <td class="font-semibold text-slate-200">${escapeHtml(t.party_name)}</td>
            <td>
                <span class="inline-flex items-center text-xs" style="color: ${t.category_color}">
                    <i class="fa-solid ${t.category_icon} mr-1"></i> ${escapeHtml(t.category_name)}
                </span>
            </td>
            <td><span class="badge-mode">${t.payment_mode}</span></td>
            <td class="font-bold ${t.type === 'INCOME' ? 'text-emerald-400' : 'text-rose-400'} whitespace-nowrap">
                ${t.type === 'INCOME' ? '+' : '-'} ${AppState.currentCurrency} ${formatNumber(t.amount)}
            </td>
            <td>
                ${t.drive_web_view_link ? `
                    <button type="button" onclick="openReceiptModal('${t.drive_web_view_link}', '${escapeHtml(t.drive_file_name || 'Receipt')}', '${t.drive_thumbnail_link || ''}')" class="text-indigo-400 hover:text-indigo-300 text-xs flex items-center gap-1">
                        <i class="fa-brands fa-google-drive"></i> View
                    </button>
                ` : '<span class="text-xs text-slate-500">None</span>'}
            </td>
        </tr>
    `).join('');
}

// ============================================================================
// DOUGHNUT CHART.JS VISUALIZATION
// ============================================================================
function updateCategoryChart(categories) {
    const canvas = document.getElementById('categoryExpenseChart');
    if (!canvas) return;

    const expenseCats = (categories || []).filter(c => c.total_expense > 0);
    const legendList = document.getElementById('category-legend-list');

    if (expenseCats.length === 0) {
        if (categoryChartInstance) {
            categoryChartInstance.destroy();
            categoryChartInstance = null;
        }
        if (legendList) {
            legendList.innerHTML = '<p class="text-xs text-slate-400 col-span-2 text-center py-4">No expense breakdown data yet.</p>';
        }
        return;
    }

    const labels = expenseCats.map(c => c.name);
    const dataVals = expenseCats.map(c => c.total_expense);
    const colors = expenseCats.map(c => c.color || '#6366f1');

    if (categoryChartInstance) {
        categoryChartInstance.data.labels = labels;
        categoryChartInstance.data.datasets[0].data = dataVals;
        categoryChartInstance.data.datasets[0].backgroundColor = colors;
        categoryChartInstance.update();
    } else {
        const ctx = canvas.getContext('2d');
        categoryChartInstance = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: dataVals,
                    backgroundColor: colors,
                    borderWidth: 2,
                    borderColor: '#0f172a',
                    hoverOffset: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(ctx) {
                                const val = ctx.parsed || 0;
                                return ` ${ctx.label}: ${AppState.currentCurrency} ${formatNumber(val)}`;
                            }
                        }
                    }
                },
                cutout: '70%'
            }
        });
    }

    // Render custom legend
    if (legendList) {
        legendList.innerHTML = expenseCats.slice(0, 6).map(c => `
            <div class="category-legend-item">
                <span class="category-legend-dot" style="background-color: ${c.color}"></span>
                <span class="truncate text-slate-300">${escapeHtml(c.name)} (${c.expense_percentage || 0}%)</span>
            </div>
        `).join('');
    }
}

// ============================================================================
// TRANSACTIONS TAB & ASYNC CRUD
// ============================================================================
async function loadTransactionsTab(eventId, showSpinner = true) {
    const tbody = document.getElementById('transactions-tbody');
    if (showSpinner && tbody && (!AppState.transactions || AppState.transactions.length === 0)) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center py-6 text-slate-400 text-xs">Loading transactions...</td></tr>';
    }

    try {
        const res = await fetch(`/api/events/${eventId}/transactions`);
        const data = await res.json();
        if (data.status === 'success') {
            AppState.transactions = data.transactions || [];
            renderMainTransactionsTable(AppState.transactions);
        }
    } catch (err) {
        console.error('Failed to load transactions:', err);
    }
}

function renderMainTransactionsTable(txns) {
    const tbody = document.getElementById('transactions-tbody');
    if (!tbody) return;

    if (!txns || txns.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center py-8 text-slate-400 text-xs">No transactions match your criteria.</td></tr>';
        return;
    }

    tbody.innerHTML = txns.map(t => `
        <tr id="txn-row-${t.id}">
            <td class="text-xs text-slate-400 whitespace-nowrap">${formatDate(t.transaction_date)}</td>
            <td>
                <span class="${t.type === 'INCOME' ? 'badge-income' : 'badge-expense'}">
                    ${t.type === 'INCOME' ? 'GIFT / IN' : 'EXPENSE'}
                </span>
            </td>
            <td>
                <div class="font-bold text-slate-200">${escapeHtml(t.party_name)}</div>
            </td>
            <td>
                <span class="inline-flex items-center text-xs" style="color: ${t.category_color}">
                    <i class="fa-solid ${t.category_icon} mr-1"></i> ${escapeHtml(t.category_name)}
                </span>
            </td>
            <td>
                <div class="flex flex-col">
                    <span class="badge-mode">${t.payment_mode}</span>
                    ${t.reference_no ? `<span class="text-[10px] text-slate-400 truncate max-w-[100px]">${escapeHtml(t.reference_no)}</span>` : ''}
                </div>
            </td>
            <td class="text-xs text-slate-300 max-w-[180px] truncate" title="${escapeHtml(t.description || '')}">
                ${escapeHtml(t.description || '-')}
            </td>
            <td class="font-bold ${t.type === 'INCOME' ? 'text-emerald-400' : 'text-rose-400'} whitespace-nowrap">
                ${t.type === 'INCOME' ? '+' : '-'} ${AppState.currentCurrency} ${formatNumber(t.amount)}
            </td>
            <td>
                ${t.drive_web_view_link ? `
                    <button type="button" onclick="openReceiptModal('${t.drive_web_view_link}', '${escapeHtml(t.drive_file_name || 'Receipt')}', '${t.drive_thumbnail_link || ''}')" class="text-indigo-400 hover:text-indigo-300 text-xs flex items-center gap-1">
                        <i class="fa-brands fa-google-drive"></i> Receipt
                    </button>
                ` : '<span class="text-xs text-slate-500">None</span>'}
            </td>
            <td class="text-right">
                <button type="button" onclick="deleteTransaction(${t.id})" class="btn-icon-danger text-xs" title="Delete Entry">
                    <i class="fa-solid fa-trash-can"></i>
                </button>
            </td>
        </tr>
    `).join('');
}

// 0ms Instant Client-Side Search & Filter
function filterTransactionsLive() {
    const term = (document.getElementById('txn-search-input')?.value || '').toLowerCase().trim();
    const typeFilter = document.getElementById('txn-type-filter')?.value || '';
    const catFilter = document.getElementById('txn-category-filter')?.value || '';
    const modeFilter = document.getElementById('txn-mode-filter')?.value || '';

    const filtered = (AppState.transactions || []).filter(t => {
        if (typeFilter && t.type !== typeFilter) return false;
        if (catFilter && String(t.category_id) !== String(catFilter)) return false;
        if (modeFilter && t.payment_mode !== modeFilter) return false;
        if (term) {
            const matchParty = (t.party_name || '').toLowerCase().includes(term);
            const matchDesc = (t.description || '').toLowerCase().includes(term);
            const matchRef = (t.reference_no || '').toLowerCase().includes(term);
            const matchCat = (t.category_name || '').toLowerCase().includes(term);
            if (!matchParty && !matchDesc && !matchRef && !matchCat) return false;
        }
        return true;
    });

    renderMainTransactionsTable(filtered);
}

// Mobile Filter Drawer Toggle
function toggleMobileFilters() {
    const container = document.getElementById('txn-filters-container');
    const btn = document.getElementById('btn-toggle-filters');
    if (!container) return;

    const isHidden = container.classList.contains('hidden');
    if (isHidden) {
        container.classList.remove('hidden');
        container.classList.add('flex');
        if (btn) {
            btn.classList.add('bg-indigo-600/30', 'text-indigo-300', 'border-indigo-500/50');
        }
    } else {
        container.classList.add('hidden');
        container.classList.remove('flex');
        if (btn) {
            btn.classList.remove('bg-indigo-600/30', 'text-indigo-300', 'border-indigo-500/50');
        }
    }
}
function openAddTransactionModal(type = 'EXPENSE') {
    if (!AppState.currentEventId) {
        showToast('Please select or create an event first.', 'warning');
        return;
    }
    updateTxnTypeUI(type);
    openModal('modal-add-transaction');
}

function updateTxnTypeUI(type) {
    const radio = document.querySelector(`input[name="type"][value="${type}"]`);
    if (radio) radio.checked = true;

    const labelExpense = document.getElementById('label-type-expense');
    const labelIncome = document.getElementById('label-type-income');
    const title = document.getElementById('txn-modal-title');
    const partyLabel = document.getElementById('label-party-name');

    if (type === 'EXPENSE') {
        labelExpense?.classList.add('bg-rose-500/20', 'text-rose-300', 'border', 'border-rose-500/40');
        labelIncome?.classList.remove('bg-emerald-500/20', 'text-emerald-300', 'border', 'border-emerald-500/40');
        if (title) title.innerHTML = '<i class="fa-solid fa-arrow-trend-down text-rose-400 mr-2"></i>Add Expense Entry';
        if (partyLabel) partyLabel.textContent = 'Payee / Vendor Name *';
    } else {
        labelIncome?.classList.add('bg-emerald-500/20', 'text-emerald-300', 'border', 'border-emerald-500/40');
        labelExpense?.classList.remove('bg-rose-500/20', 'text-rose-300', 'border', 'border-rose-500/40');
        if (title) title.innerHTML = '<i class="fa-solid fa-hand-holding-dollar text-emerald-400 mr-2"></i>Add Gift / Shagun Entry';
        if (partyLabel) partyLabel.textContent = 'Gift Contributor / Relative Name *';
    }
}

async function submitAddTransaction(e) {
    e.preventDefault();
    if (!AppState.currentEventId) return;

    const form = e.target;
    const formData = new FormData(form);
    const amountVal = parseFloat(formData.get('amount')) || 0;
    const typeVal = formData.get('type') || 'EXPENSE';
    const partyVal = formData.get('party_name') || '';
    const catIdVal = parseInt(formData.get('category_id')) || null;
    const paymentModeVal = formData.get('payment_mode') || 'CASH';
    const descVal = formData.get('description') || '';
    const dateVal = formData.get('transaction_date') || new Date().toISOString().split('T')[0];

    const matchedCat = (AppState.categories || []).find(c => c.id === catIdVal);

    // 1. 0ms Optimistic UI Update
    const optimisticTxn = {
        id: 'temp_' + Date.now(),
        event_id: AppState.currentEventId,
        category_id: catIdVal,
        category_name: matchedCat ? matchedCat.name : 'Uncategorized',
        category_color: matchedCat ? matchedCat.color : '#64748b',
        category_icon: matchedCat ? matchedCat.icon : 'fa-receipt',
        type: typeVal,
        amount: amountVal,
        party_name: partyVal,
        payment_mode: paymentModeVal,
        description: descVal,
        transaction_date: dateVal,
        drive_web_view_link: null,
        drive_file_name: null
    };

    AppState.transactions.unshift(optimisticTxn);
    renderMainTransactionsTable(AppState.transactions);

    // Optimistically update category spent
    if (matchedCat) {
        if (typeVal === 'EXPENSE') matchedCat.total_spent = (matchedCat.total_spent || 0) + amountVal;
        else matchedCat.total_received = (matchedCat.total_received || 0) + amountVal;
        renderCategoriesGrid(AppState.categories);
    }

    closeModal('modal-add-transaction');
    form.reset();
    showToast('Entry saved instantly!', 'success');

    // 2. Non-blocking Background API Sync
    try {
        const res = await fetch(`/api/events/${AppState.currentEventId}/transactions`, {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            // Replace optimistic txn with server generated one
            const idx = AppState.transactions.findIndex(t => t.id === optimisticTxn.id);
            if (idx !== -1) AppState.transactions[idx] = data.transaction;
            renderMainTransactionsTable(AppState.transactions);
            // Refresh analytics silently in background
            loadEventFullData(AppState.currentEventId, true);
        } else {
            showToast(data.message || 'Failed to sync entry to cloud', 'error');
        }
    } catch (err) {
        console.error('Background transaction sync error:', err);
    }
}

async function deleteTransaction(txnId) {
    if (!confirm('Are you sure you want to delete this transaction?')) return;

    // 1. 0ms Optimistic UI removal
    const removedTxn = AppState.transactions.find(t => t.id === txnId);
    AppState.transactions = AppState.transactions.filter(t => t.id !== txnId);
    renderMainTransactionsTable(AppState.transactions);

    if (removedTxn) {
        const cat = AppState.categories.find(c => c.id === removedTxn.category_id);
        if (cat) {
            if (removedTxn.type === 'EXPENSE') cat.total_spent = Math.max(0, (cat.total_spent || 0) - removedTxn.amount);
            else cat.total_received = Math.max(0, (cat.total_received || 0) - removedTxn.amount);
            renderCategoriesGrid(AppState.categories);
        }
    }
    showToast('Transaction deleted', 'info');

    // 2. Background API delete
    try {
        await fetch(`/api/transactions/${txnId}`, { method: 'DELETE' });
        loadEventFullData(AppState.currentEventId, true);
    } catch (err) {
        console.error('Failed to delete transaction on server:', err);
    }
}

// ============================================================================
// 0ms CATEGORIES TAB & OPTIMISTIC INLINE BUDGET MANAGER
// ============================================================================
async function loadCategoriesTab(eventId, showSpinner = false) {
    const grid = document.getElementById('categories-grid');
    if (showSpinner && grid && (!AppState.categories || AppState.categories.length === 0)) {
        grid.innerHTML = '<p class="text-xs text-slate-400 py-6 col-span-3 text-center">Loading categories...</p>';
    }

    try {
        const res = await fetch(`/api/events/${eventId}/categories`);
        const data = await res.json();
        if (data.status === 'success') {
            AppState.categories = data.categories || [];
            populateCategoryDropdowns(AppState.categories);
            renderCategoriesGrid(AppState.categories);
        }
    } catch (err) {
        console.error('Failed to load categories:', err);
    }
}

function renderCategoriesGrid(categories) {
    const grid = document.getElementById('categories-grid');
    if (!grid) return;

    if (!categories || categories.length === 0) {
        grid.innerHTML = '<p class="text-xs text-slate-400 py-8 col-span-3 text-center">No categories created yet. Click "Create Custom Category" above!</p>';
        return;
    }

    grid.innerHTML = categories.map(c => {
        const budgetVal = c.budget || 0;
        const spentVal = c.total_spent || 0;
        const receivedVal = c.total_received || 0;
        const pct = budgetVal > 0 ? Math.min(Math.round((spentVal / budgetVal) * 100), 100) : 0;
        const isOver = budgetVal > 0 && spentVal > budgetVal;

        return `
            <div class="stat-card" id="cat-card-${c.id}" style="border-left: 4px solid ${c.color}">
                <div class="flex items-center justify-between mb-2">
                    <div class="flex items-center space-x-2">
                        <div class="w-8 h-8 rounded-lg flex items-center justify-center text-sm" style="background-color: ${c.color}20; color: ${c.color}">
                            <i class="fa-solid ${c.icon}"></i>
                        </div>
                        <div>
                            <span class="font-bold text-white text-sm block leading-tight">${escapeHtml(c.name)}</span>
                            <span class="text-[10px] text-slate-400 uppercase tracking-wider">${c.type}</span>
                        </div>
                    </div>
                    <button type="button" onclick="deleteCategory(${c.id})" class="btn-icon-danger text-xs" title="Delete Category">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>

                <!-- Budget & Progress -->
                <div class="my-3 p-2.5 rounded-xl bg-slate-800/40 border border-slate-700/50">
                    <div class="flex items-center justify-between text-xs mb-1">
                        <span class="text-slate-400 flex items-center gap-1">
                            <i class="fa-solid fa-bullseye text-[10px] text-amber-400"></i> Budget:
                        </span>
                        <div class="flex items-center gap-1">
                            <span class="font-semibold text-slate-200" id="cat-budget-label-${c.id}">
                                ${budgetVal > 0 ? `${AppState.currentCurrency} ${formatNumber(budgetVal)}` : '<span class="text-slate-500 font-normal">No Limit</span>'}
                            </span>
                            <button type="button" onclick="promptEditCategoryBudget(${c.id}, ${budgetVal})" class="text-[11px] text-indigo-400 hover:text-indigo-300 p-0.5 ml-1" title="0ms Quick Edit Budget">
                                <i class="fa-solid fa-pen-to-square"></i>
                            </button>
                        </div>
                    </div>
                    ${budgetVal > 0 ? `
                        <div class="w-full bg-slate-700 h-1.5 rounded-full overflow-hidden my-1.5">
                            <div class="h-full ${isOver ? 'bg-rose-500' : 'bg-indigo-500'} rounded-full transition-all duration-300" style="width: ${pct}%"></div>
                        </div>
                        <div class="flex justify-between text-[10px] ${isOver ? 'text-rose-400 font-bold' : 'text-slate-400'}">
                            <span>${pct}% Utilized</span>
                            <span>${isOver ? 'Over Budget!' : `${AppState.currentCurrency} ${formatNumber(budgetVal - spentVal)} left`}</span>
                        </div>
                    ` : ''}
                </div>

                <!-- Financial Totals -->
                <div class="grid grid-cols-2 gap-2 text-xs pt-2 border-t border-slate-800">
                    <div>
                        <span class="text-slate-400 block text-[10px]">Total Outflow:</span>
                        <span class="font-bold text-rose-400">${AppState.currentCurrency} ${formatNumber(spentVal)}</span>
                    </div>
                    <div>
                        <span class="text-slate-400 block text-[10px]">Total Inflow:</span>
                        <span class="font-bold text-emerald-400">${AppState.currentCurrency} ${formatNumber(receivedVal)}</span>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function populateCategoryDropdowns(categories) {
    const modalSelect = document.getElementById('modal-txn-category-select');
    const filterSelect = document.getElementById('txn-category-filter');

    const optionsHtml = '<option value="">All Categories</option>' + (categories || []).map(c => `
        <option value="${c.id}">${escapeHtml(c.name)}</option>
    `).join('');

    const modalOptionsHtml = '<option value="">-- Select Category --</option>' + (categories || []).map(c => `
        <option value="${c.id}">${escapeHtml(c.name)}</option>
    `).join('');

    if (modalSelect) modalSelect.innerHTML = modalOptionsHtml;
    if (filterSelect) filterSelect.innerHTML = optionsHtml;
}

// 0ms Inline Category Budget Edit
function promptEditCategoryBudget(catId, currentBudget) {
    const newBudgetStr = prompt(`Enter new budget limit (${AppState.currentCurrency}) for this category:`, currentBudget || '');
    if (newBudgetStr === null) return; // user cancelled

    const newBudget = newBudgetStr.trim() === '' ? null : parseFloat(newBudgetStr);
    if (newBudget !== null && isNaN(newBudget)) {
        showToast('Please enter a valid monetary amount', 'warning');
        return;
    }

    // 1. 0ms Optimistic UI Update
    const cat = AppState.categories.find(c => c.id === catId);
    if (cat) {
        cat.budget = newBudget;
        renderCategoriesGrid(AppState.categories);
    }
    showToast('Budget updated instantly in 0ms!', 'success');

    // 2. Background API Sync
    fetch(`/api/categories/${catId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ budget: newBudget })
    }).catch(err => {
        console.error('Failed to sync budget to server:', err);
    });
}

function openCreateCategoryModal() {
    if (!AppState.currentEventId) {
        showToast('Please select or create an event first.', 'warning');
        return;
    }
    openModal('modal-create-category');
}

async function submitCreateCategory(e) {
    e.preventDefault();
    if (!AppState.currentEventId) return;

    const form = e.target;
    const formData = new FormData(form);
    const payload = Object.fromEntries(formData.entries());

    // 1. 0ms Optimistic UI update
    const optimisticCat = {
        id: 'temp_cat_' + Date.now(),
        event_id: AppState.currentEventId,
        name: payload.name,
        type: payload.type || 'EXPENSE',
        color: payload.color || '#6366f1',
        icon: payload.icon || 'fa-tag',
        budget: payload.budget ? parseFloat(payload.budget) : null,
        total_spent: 0,
        total_received: 0,
        transaction_count: 0
    };

    AppState.categories.push(optimisticCat);
    renderCategoriesGrid(AppState.categories);
    populateCategoryDropdowns(AppState.categories);

    closeModal('modal-create-category');
    form.reset();
    showToast('Category created in 0ms!', 'success');

    // 2. Non-blocking background API sync
    try {
        const res = await fetch(`/api/events/${AppState.currentEventId}/categories`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            const idx = AppState.categories.findIndex(c => c.id === optimisticCat.id);
            if (idx !== -1) AppState.categories[idx] = data.category;
            renderCategoriesGrid(AppState.categories);
            populateCategoryDropdowns(AppState.categories);
        }
    } catch (err) {
        console.error('Background category creation sync error:', err);
    }
}

async function deleteCategory(categoryId) {
    if (!confirm('Are you sure you want to delete this category?')) return;

    // 1. 0ms Optimistic UI removal
    AppState.categories = AppState.categories.filter(c => c.id !== categoryId);
    renderCategoriesGrid(AppState.categories);
    populateCategoryDropdowns(AppState.categories);
    showToast('Category deleted in 0ms', 'info');

    // 2. Background API Sync
    try {
        await fetch(`/api/categories/${categoryId}`, { method: 'DELETE' });
    } catch (err) {
        console.error('Background category deletion error:', err);
    }
}

// ============================================================================
// EVENT CREATION
// ============================================================================
function openCreateEventModal() {
    openModal('modal-create-event');
}

async function submitCreateEvent(e) {
    e.preventDefault();
    const form = e.target;
    const formData = new FormData(form);
    const payload = Object.fromEntries(formData.entries());

    try {
        const res = await fetch('/api/events', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (res.ok && data.status === 'success') {
            showToast('Event created successfully!', 'success');
            closeModal('modal-create-event');
            setTimeout(() => {
                location.reload();
            }, 600);
        } else {
            showToast(data.message || 'Failed to create event', 'error');
        }
    } catch (err) {
        showToast('Error creating event', 'error');
    }
}

// ============================================================================
// GOOGLE DRIVE EXPLORER & CLOUD SYNC
// ============================================================================
const DriveExplorerState = {
    currentParentId: 'root',
    currentParentName: 'My Drive',
    pathHistory: [{ id: 'root', name: 'My Drive' }]
};

function formatDriveFileSize(bytes) {
    if (!bytes || isNaN(bytes) || bytes <= 0) return '';
    const num = parseFloat(bytes);
    if (num < 1024) return `${num} B`;
    if (num < 1024 * 1024) return `${(num / 1024).toFixed(1)} KB`;
    return `${(num / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileIconClass(mimeType, fileName = '') {
    if (!mimeType) mimeType = '';
    const lowerName = fileName.toLowerCase();
    if (mimeType.includes('image') || lowerName.endsWith('.png') || lowerName.endsWith('.jpg') || lowerName.endsWith('.jpeg')) {
        return 'fa-file-image text-pink-400';
    }
    if (mimeType.includes('pdf') || lowerName.endsWith('.pdf')) {
        return 'fa-file-pdf text-rose-400';
    }
    if (mimeType.includes('json') || lowerName.endsWith('.json')) {
        return 'fa-file-code text-amber-400';
    }
    if (mimeType.includes('csv') || mimeType.includes('sheet') || lowerName.endsWith('.csv')) {
        return 'fa-file-csv text-emerald-400';
    }
    return 'fa-file-lines text-slate-400';
}

async function triggerDriveBackup() {
    showToast('Initiating Google Drive backup...', 'info');
    try {
        const res = await fetch('/api/backup/drive', { method: 'POST' });
        const data = await res.json();

        if (res.ok && data.status === 'success') {
            showToast('Backup completed and saved to your designated Google Drive folder!', 'success');
            // Refresh in-panel explorer to display the newly saved backup file
            loadUserDriveFolders(DriveExplorerState.currentParentId, false);
        } else {
            showToast(data.message || 'Drive backup failed', 'error');
        }
    } catch (err) {
        showToast('Error communicating with Google Drive', 'error');
    }
}

// Load and render Google Drive folder and file hierarchy in the same panel
async function loadUserDriveFolders(parentId = 'root', forceScan = false) {
    const tbody = document.getElementById('drive-folders-tbody');
    const breadcrumbsEl = document.getElementById('drive-breadcrumbs');
    const btnUp = document.getElementById('btn-drive-up');
    const itemCountsEl = document.getElementById('drive-item-counts');
    const activeNameEl = document.getElementById('active-drive-folder-name');
    const activeIdEl = document.getElementById('active-drive-folder-id');

    if (!tbody) return;
    DriveExplorerState.currentParentId = parentId || 'root';

    if (forceScan || !tbody.children.length) {
        tbody.innerHTML = '<tr><td colspan="3" class="text-center py-6 text-slate-400 text-xs"><i class="fa-solid fa-spinner fa-spin mr-1.5 text-indigo-400"></i> Loading contents from My Drive...</td></tr>';
    }

    try {
        const res = await fetch(`/api/drive/folders?parent_id=${encodeURIComponent(DriveExplorerState.currentParentId)}`);
        const data = res.ok ? await res.json() : { status: 'error' };

        if (data.status === 'success') {
            const folders = data.folders || [];
            const files = data.files || [];
            const currentFolderId = data.current_folder_id;
            const currentFolderName = data.current_folder_name || 'EventMoneyTracker_Receipts';
            const currentParent = data.current_parent || {};

            DriveExplorerState.currentParentName = currentParent.name || (parentId === 'root' ? 'My Drive' : 'Folder');

            if (activeNameEl) activeNameEl.textContent = currentFolderName;
            if (activeIdEl) activeIdEl.textContent = currentFolderId ? `ID: ${currentFolderId}` : '(Not set)';

            if (itemCountsEl) {
                itemCountsEl.textContent = `${folders.length} folder${folders.length === 1 ? '' : 's'}${files.length ? `, ${files.length} file${files.length === 1 ? '' : 's'}` : ''}`;
            }

            // Render Breadcrumbs
            renderDriveBreadcrumbs();

            // Toggle Up Button
            if (btnUp) {
                if (DriveExplorerState.pathHistory.length > 1) {
                    btnUp.classList.remove('hidden');
                    btnUp.classList.add('inline-flex');
                } else {
                    btnUp.classList.add('hidden');
                    btnUp.classList.remove('inline-flex');
                }
            }

            // Render Folders & Files in the table
            if (folders.length === 0 && files.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="3" class="text-center py-8 text-slate-400 text-xs">
                            <div class="flex flex-col items-center justify-center space-y-1">
                                <i class="fa-regular fa-folder-open text-2xl text-slate-600 mb-1"></i>
                                <span>No items found inside "${escapeHtml(DriveExplorerState.currentParentName)}".</span>
                                <span class="text-[10px] text-slate-500">You can create a new folder below or set this current folder as your destination.</span>
                            </div>
                        </td>
                    </tr>
                `;
            } else {
                let html = '';

                // 1. Folders Rows
                folders.forEach(f => {
                    const isSelected = (f.id === currentFolderId);
                    html += `
                        <tr class="hover:bg-slate-800/40 transition">
                            <td>
                                <div class="flex items-center space-x-2.5">
                                    <div class="w-8 h-8 rounded-lg bg-amber-500/15 border border-amber-500/30 text-amber-400 flex items-center justify-center shrink-0 cursor-pointer" onclick="navigateToDriveFolder('${f.id}', '${escapeHtml(f.name)}')">
                                        <i class="fa-solid fa-folder"></i>
                                    </div>
                                    <div>
                                        <div class="font-bold text-slate-200 text-xs cursor-pointer hover:text-indigo-400 transition" onclick="navigateToDriveFolder('${f.id}', '${escapeHtml(f.name)}')">
                                            ${escapeHtml(f.name)}
                                        </div>
                                        <div class="text-[10px] font-mono text-slate-500">${f.id.slice(0, 16)}...</div>
                                    </div>
                                </div>
                            </td>
                            <td>
                                ${isSelected ? `
                                    <span class="inline-flex items-center text-[10px] font-bold text-emerald-400 bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 rounded-md">
                                        <i class="fa-solid fa-circle-check mr-1"></i> Active Destination
                                    </span>
                                ` : `
                                    <span class="text-[11px] text-slate-400"><i class="fa-solid fa-folder text-amber-400 text-[10px] mr-1"></i> Folder</span>
                                `}
                            </td>
                            <td class="text-right whitespace-nowrap">
                                <div class="inline-flex items-center gap-1.5">
                                    <!-- Enter Folder In Panel -->
                                    <button type="button" onclick="navigateToDriveFolder('${f.id}', '${escapeHtml(f.name)}')" class="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold transition flex items-center gap-1 shadow-sm" title="Open this folder inside the panel">
                                        <i class="fa-solid fa-folder-open"></i> Open Folder
                                    </button>

                                    <!-- Set as Destination -->
                                    <button type="button" onclick="onSelectExistingDriveFolder('${f.id}', '${escapeHtml(f.name)}')" class="px-2.5 py-1 ${isSelected ? 'bg-emerald-600 text-white' : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700'} rounded-lg text-xs font-semibold transition flex items-center gap-1" title="Set as designated backup folder">
                                        <i class="fa-solid ${isSelected ? 'fa-check' : 'fa-bullseye'}"></i> ${isSelected ? 'Selected' : 'Set Destination'}
                                    </button>
                                </div>
                            </td>
                        </tr>
                    `;
                });

                // 2. Files Rows (Receipts, JSON Backups)
                files.forEach(file => {
                    const iconCls = getFileIconClass(file.mimeType, file.name);
                    const sizeStr = formatDriveFileSize(file.size);
                    const modifiedStr = file.modifiedTime ? new Date(file.modifiedTime).toLocaleDateString() : '';

                    html += `
                        <tr class="hover:bg-slate-800/30 transition border-t border-slate-800/60">
                            <td>
                                <div class="flex items-center space-x-2.5">
                                    <div class="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 text-sm flex items-center justify-center shrink-0">
                                        <i class="fa-solid ${iconCls}"></i>
                                    </div>
                                    <div class="min-w-0">
                                        <div class="font-medium text-slate-300 text-xs truncate max-w-xs sm:max-w-md" title="${escapeHtml(file.name)}">
                                            ${escapeHtml(file.name)}
                                        </div>
                                        <div class="text-[10px] text-slate-500">${sizeStr ? sizeStr + ' • ' : ''}${modifiedStr}</div>
                                    </div>
                                </div>
                            </td>
                            <td>
                                <span class="text-[10px] font-mono text-slate-400 uppercase bg-slate-800 px-1.5 py-0.5 rounded border border-slate-700/60">
                                    ${file.name.split('.').pop() || 'FILE'}
                                </span>
                            </td>
                            <td class="text-right whitespace-nowrap">
                                <a href="/api/drive/files/${file.id}/download" class="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 hover:text-white rounded-lg text-xs font-medium transition inline-flex items-center gap-1" title="Download this file">
                                    <i class="fa-solid fa-download text-xs"></i> Download
                                </a>
                            </td>
                        </tr>
                    `;
                });

                tbody.innerHTML = html;
            }

            if (forceScan) {
                showToast(`Loaded ${folders.length} folders from My Drive!`, 'success');
            }
        } else {
            tbody.innerHTML = '<tr><td colspan="3" class="text-center py-6 text-amber-400 text-xs">Please connect your Google Drive account first.</td></tr>';
        }
    } catch (err) {
        console.error('Failed to load drive folders:', err);
        tbody.innerHTML = '<tr><td colspan="3" class="text-center py-6 text-rose-400 text-xs">Failed to load Google Drive folders.</td></tr>';
    }
}

// Navigate breadcrumb path
function renderDriveBreadcrumbs() {
    const breadcrumbsEl = document.getElementById('drive-breadcrumbs');
    if (!breadcrumbsEl) return;

    breadcrumbsEl.innerHTML = DriveExplorerState.pathHistory.map((step, idx) => {
        const isLast = (idx === DriveExplorerState.pathHistory.length - 1);
        if (isLast) {
            return `<span class="font-bold text-white">${escapeHtml(step.name)}</span>`;
        }
        return `
            <button type="button" onclick="navigateDriveToHistoryIndex(${idx})" class="font-semibold text-indigo-400 hover:underline flex items-center gap-1">
                ${idx === 0 ? '<i class="fa-brands fa-google-drive text-amber-400 mr-1"></i>' : ''}${escapeHtml(step.name)}
            </button>
            <span class="text-slate-600">/</span>
        `;
    }).join('');
}

// Get into a folder (drill down into subfolder in the same panel)
function navigateToDriveFolder(folderId, folderName) {
    if (folderId === 'root') {
        DriveExplorerState.pathHistory = [{ id: 'root', name: 'My Drive' }];
    } else {
        const existingIdx = DriveExplorerState.pathHistory.findIndex(p => p.id === folderId);
        if (existingIdx !== -1) {
            DriveExplorerState.pathHistory = DriveExplorerState.pathHistory.slice(0, existingIdx + 1);
        } else {
            DriveExplorerState.pathHistory.push({ id: folderId, name: folderName });
        }
    }
    loadUserDriveFolders(folderId, false);
}

function navigateDriveToHistoryIndex(idx) {
    if (idx >= 0 && idx < DriveExplorerState.pathHistory.length) {
        DriveExplorerState.pathHistory = DriveExplorerState.pathHistory.slice(0, idx + 1);
        const target = DriveExplorerState.pathHistory[idx];
        loadUserDriveFolders(target.id, false);
    }
}

function navigateDriveFolderUp() {
    if (DriveExplorerState.pathHistory.length > 1) {
        DriveExplorerState.pathHistory.pop();
        const prev = DriveExplorerState.pathHistory[DriveExplorerState.pathHistory.length - 1];
        loadUserDriveFolders(prev.id, false);
    }
}

// User sets an existing folder as destination
async function onSelectExistingDriveFolder(folderId, folderName) {
    if (!folderId) return;

    try {
        const res = await fetch('/api/drive/select-folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_id: folderId, folder_name: folderName })
        });
        const data = await res.json();

        if (res.ok && data.status === 'success') {
            showToast(`Active destination set to "${data.folder.folder_name}"!`, 'success');
            const activeNameEl = document.getElementById('active-drive-folder-name');
            const activeIdEl = document.getElementById('active-drive-folder-id');

            if (activeNameEl) activeNameEl.textContent = data.folder.folder_name;
            if (activeIdEl) activeIdEl.textContent = `ID: ${data.folder.folder_id}`;

            loadUserDriveFolders(DriveExplorerState.currentParentId, false);
        } else {
            showToast(data.message || 'Failed to select folder', 'error');
        }
    } catch (err) {
        showToast('Error setting designated folder', 'error');
    }
}

async function submitDriveFolder(e) {
    e.preventDefault();
    const folderName = document.getElementById('drive-folder-input').value.trim();
    if (!folderName) return;

    try {
        const res = await fetch('/api/drive/folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_name: folderName })
        });
        const data = await res.json();

        if (res.ok && data.status === 'success') {
            showToast(`Designated folder updated to "${data.folder_name}"!`, 'success');
            const activeNameEl = document.getElementById('active-drive-folder-name');
            const activeIdEl = document.getElementById('active-drive-folder-id');

            if (activeNameEl) activeNameEl.textContent = data.folder_name;
            if (activeIdEl) activeIdEl.textContent = data.folder_id ? `ID: ${data.folder_id}` : '';

            loadUserDriveFolders(DriveExplorerState.currentParentId, false);
        } else {
            showToast(data.message || 'Failed to update folder', 'error');
        }
    } catch (err) {
        showToast('Error updating folder settings', 'error');
    }
}

// ============================================================================
// ADMIN PORTAL (USERS, EVENTS, PURGE, STATS, AUDIT TRAIL)
// ============================================================================
async function loadAdminStats() {
    const usersTbody = document.getElementById('admin-users-tbody');
    const eventsTbody = document.getElementById('admin-events-tbody');
    const auditTbody = document.getElementById('admin-audit-tbody');

    if (usersTbody && (!usersTbody.children.length || usersTbody.innerText.includes('Loading'))) {
        usersTbody.innerHTML = '<tr><td colspan="9" class="text-center py-6 text-slate-400 text-xs">Loading registered users...</td></tr>';
    }
    if (eventsTbody && (!eventsTbody.children.length || eventsTbody.innerText.includes('Loading'))) {
        eventsTbody.innerHTML = '<tr><td colspan="7" class="text-center py-6 text-slate-400 text-xs">Loading platform events...</td></tr>';
    }
    if (auditTbody && (!auditTbody.children.length || auditTbody.innerText.includes('Loading'))) {
        auditTbody.innerHTML = '<tr><td colspan="5" class="text-center py-6 text-slate-400 text-xs">Loading audit history...</td></tr>';
    }

    try {
        const [statsRes, usersRes, eventsRes, auditRes] = await Promise.all([
            fetch('/api/admin/stats'),
            fetch('/api/admin/users'),
            fetch('/api/admin/events'),
            fetch('/api/admin/audit?limit=50')
        ]);

        const statsData = statsRes.ok ? await statsRes.json() : { status: 'error' };
        const usersData = usersRes.ok ? await usersRes.json() : { status: 'error' };
        const eventsData = eventsRes.ok ? await eventsRes.json() : { status: 'error' };
        const auditData = auditRes.ok ? await auditRes.json() : { status: 'error' };

        // 1. System Counters
        if (statsData.status === 'success' && statsData.counts) {
            const counts = statsData.counts;
            const uEl = document.getElementById('admin-count-users');
            const eEl = document.getElementById('admin-count-events');
            const tEl = document.getElementById('admin-count-txns');
            if (uEl) uEl.textContent = counts.users || 0;
            if (eEl) eEl.textContent = counts.events || 0;
            if (tEl) tEl.textContent = counts.transactions || 0;
        }

        // 2. Registered Users Table
        if (usersData.status === 'success' && usersTbody) {
            const users = usersData.users || [];
            const badge = document.getElementById('admin-users-badge');
            if (badge) badge.textContent = `${users.length} Registered Accounts`;

            if (users.length === 0) {
                usersTbody.innerHTML = '<tr><td colspan="9" class="text-center py-6 text-slate-400 text-xs">No users registered in system.</td></tr>';
            } else {
                usersTbody.innerHTML = users.map(u => `
                    <tr>
                        <td class="text-xs font-mono text-slate-400">#${u.id}</td>
                        <td>
                            <div class="flex items-center space-x-2.5">
                                ${u.avatar_url ? `
                                    <img src="${u.avatar_url}" alt="${escapeHtml(u.name)}" class="w-7 h-7 rounded-full border border-slate-700 object-cover">
                                ` : `
                                    <div class="w-7 h-7 rounded-full bg-indigo-600/30 border border-indigo-500/40 text-indigo-300 font-bold text-xs flex items-center justify-center">
                                        ${(u.name || 'U')[0].toUpperCase()}
                                    </div>
                                `}
                                <span class="font-bold text-slate-200 text-xs">${escapeHtml(u.name || 'User')}</span>
                            </div>
                        </td>
                        <td class="text-xs text-slate-300 font-mono">${escapeHtml(u.email)}</td>
                        <td>
                            ${u.is_admin ? `
                                <span class="px-2 py-0.5 rounded-md text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40">
                                    <i class="fa-solid fa-shield-halved mr-1"></i> Admin
                                </span>
                            ` : `
                                <span class="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-slate-800 text-slate-400 border border-slate-700">
                                    User
                                </span>
                            `}
                        </td>
                        <td>
                            ${u.google_linked ? `
                                <span class="inline-flex items-center text-[10px] font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 px-2 py-0.5 rounded-md">
                                    <i class="fa-brands fa-google mr-1"></i> Linked
                                </span>
                            ` : `
                                <span class="inline-flex items-center text-[10px] text-slate-500">
                                    <i class="fa-solid fa-key mr-1"></i> Local
                                </span>
                            `}
                        </td>
                        <td class="text-xs font-semibold text-slate-300">${u.events_count || 0}</td>
                        <td class="text-xs font-semibold text-slate-300">${u.transactions_count || 0}</td>
                        <td class="text-xs text-slate-400 whitespace-nowrap">${formatDate(u.created_at)}</td>
                        <td class="text-right whitespace-nowrap">
                            <div class="inline-flex items-center gap-1.5">
                                <button type="button" onclick="adminPurgeUserData(${u.id}, '${escapeHtml(u.email)}')" class="px-2 py-1 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded-lg text-[11px] font-medium transition" title="Purge all events and transactions for this user">
                                    <i class="fa-solid fa-broom mr-1"></i> Purge Data
                                </button>
                                ${!u.is_admin ? `
                                    <button type="button" onclick="adminDeleteUser(${u.id}, '${escapeHtml(u.email)}')" class="px-2 py-1 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded-lg text-[11px] font-medium transition" title="Delete account and all data">
                                        <i class="fa-solid fa-trash mr-1"></i> Delete
                                    </button>
                                ` : `
                                    <span class="text-[10px] text-slate-600 px-2 py-1 italic">Protected</span>
                                `}
                            </div>
                        </td>
                    </tr>
                `).join('');
            }
        }

        // 3. Platform Events & Purge Manager
        if (eventsData.status === 'success' && eventsTbody) {
            const events = eventsData.events || [];
            const badge = document.getElementById('admin-events-badge');
            if (badge) badge.textContent = `${events.length} Platform Events`;

            if (events.length === 0) {
                eventsTbody.innerHTML = '<tr><td colspan="7" class="text-center py-6 text-slate-400 text-xs">No events registered on platform.</td></tr>';
            } else {
                eventsTbody.innerHTML = events.map(e => `
                    <tr>
                        <td>
                            <div class="font-bold text-slate-200 text-xs">${escapeHtml(e.title)}</div>
                            <div class="text-[10px] text-slate-400 truncate max-w-[180px]">${escapeHtml(e.description || 'No description')}</div>
                        </td>
                        <td>
                            <div class="text-xs text-slate-300">${escapeHtml(e.owner_name)}</div>
                            <div class="text-[10px] font-mono text-slate-500">${escapeHtml(e.owner_email)}</div>
                        </td>
                        <td class="text-xs text-slate-400 whitespace-nowrap">${e.event_date || '-'} (${e.currency})</td>
                        <td class="text-xs font-semibold text-slate-300">
                            ${e.budget_limit ? `${e.currency} ${Number(e.budget_limit).toLocaleString()}` : '<span class="text-slate-500 text-[10px]">None</span>'}
                        </td>
                        <td class="text-xs font-bold ${e.stats && e.stats.net_balance >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
                            ${e.currency} ${e.stats ? Number(e.stats.net_balance).toLocaleString() : 0}
                        </td>
                        <td class="text-xs font-semibold text-slate-300">${e.stats ? e.stats.transaction_count : 0}</td>
                        <td class="text-right">
                            <button type="button" onclick="adminDeleteEvent(${e.id}, '${escapeHtml(e.title)}')" class="px-2.5 py-1 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded-lg text-xs font-medium transition" title="Delete event and all transactions">
                                <i class="fa-solid fa-trash-can mr-1"></i> Delete
                            </button>
                        </td>
                    </tr>
                `).join('');
            }
        }

        // 4. Security & Transaction Audit Trail Table
        if (auditData.status === 'success' && auditTbody) {
            const logs = auditData.logs || [];
            if (logs.length === 0) {
                auditTbody.innerHTML = '<tr><td colspan="5" class="text-center py-6 text-slate-400 text-xs">No audit logs recorded yet.</td></tr>';
            } else {
                auditTbody.innerHTML = logs.map(l => {
                    let actionBadgeClass = 'bg-slate-800 text-slate-300 border-slate-700';
                    let actionIcon = 'fa-clock';

                    if (l.action.includes('REGISTER')) {
                        actionBadgeClass = 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
                        actionIcon = 'fa-user-plus';
                    } else if (l.action.includes('LOGIN')) {
                        actionBadgeClass = 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30';
                        actionIcon = 'fa-right-to-bracket';
                    } else if (l.action.includes('RESTORE')) {
                        actionBadgeClass = 'bg-rose-500/20 text-rose-300 border-rose-500/40';
                        actionIcon = 'fa-bolt';
                    } else if (l.action.includes('BACKUP')) {
                        actionBadgeClass = 'bg-amber-500/15 text-amber-300 border-amber-500/30';
                        actionIcon = 'fa-database';
                    } else if (l.action.includes('DELETE') || l.action.includes('PURGE')) {
                        actionBadgeClass = 'bg-rose-500/15 text-rose-300 border-rose-500/30';
                        actionIcon = 'fa-trash-can';
                    } else if (l.action.includes('CREATE')) {
                        actionBadgeClass = 'bg-teal-500/15 text-teal-300 border-teal-500/30';
                        actionIcon = 'fa-plus';
                    }

                    const detailsStr = typeof l.details === 'object' ? JSON.stringify(l.details) : String(l.details || '-');

                    return `
                        <tr>
                            <td class="text-xs text-slate-400 whitespace-nowrap">${formatDate(l.timestamp)}</td>
                            <td>
                                <div class="text-xs font-semibold text-slate-200">${escapeHtml(l.user_name || 'System')}</div>
                                <div class="text-[10px] text-slate-400 font-mono">${escapeHtml(l.user_email || '-')}</div>
                            </td>
                            <td>
                                <span class="px-2 py-0.5 rounded-md text-[10px] font-semibold border inline-flex items-center gap-1 ${actionBadgeClass}">
                                    <i class="fa-solid ${actionIcon}"></i>
                                    <span>${escapeHtml(l.action)}</span>
                                </span>
                            </td>
                            <td class="text-xs font-mono text-slate-400">${escapeHtml(l.ip_address || '-')}</td>
                            <td class="text-xs text-slate-300 max-w-[280px] truncate" title="${escapeHtml(detailsStr)}">
                                ${escapeHtml(detailsStr)}
                            </td>
                        </tr>
                    `;
                }).join('');
            }
        }
    } catch (err) {
        console.error('Failed to load admin stats:', err);
        if (usersTbody) usersTbody.innerHTML = '<tr><td colspan="9" class="text-center py-6 text-rose-400 text-xs">Failed to load users.</td></tr>';
        if (eventsTbody) eventsTbody.innerHTML = '<tr><td colspan="7" class="text-center py-6 text-rose-400 text-xs">Failed to load platform events.</td></tr>';
        if (auditTbody) auditTbody.innerHTML = '<tr><td colspan="5" class="text-center py-6 text-rose-400 text-xs">Failed to load audit history.</td></tr>';
    }
}

// Admin Action: Purge All Financial Data for a User
async function adminPurgeUserData(userId, userEmail) {
    if (!confirm(`Are you sure you want to PURGE all events, categories, and transactions for user ${userEmail}? This action cannot be undone.`)) {
        return;
    }

    try {
        const res = await fetch(`/api/admin/users/${userId}/purge`, { method: 'POST' });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast(`Purged user data: ${data.message}`, 'success');
            loadAdminStats();
            loadEvents();
        } else {
            showToast(data.message || 'Failed to purge user data', 'error');
        }
    } catch (err) {
        showToast('Error executing user data purge', 'error');
    }
}

// Admin Action: Delete User Account Permanently
async function adminDeleteUser(userId, userEmail) {
    if (!confirm(`CRITICAL WARNING: Are you sure you want to permanently DELETE the user account ${userEmail} and all their data?`)) {
        return;
    }

    try {
        const res = await fetch(`/api/admin/users/${userId}`, { method: 'DELETE' });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast(`User account deleted: ${userEmail}`, 'success');
            loadAdminStats();
            loadEvents();
        } else {
            showToast(data.message || 'Failed to delete user', 'error');
        }
    } catch (err) {
        showToast('Error deleting user account', 'error');
    }
}

// Admin Action: Delete Any Event
async function adminDeleteEvent(eventId, eventTitle) {
    if (!confirm(`Are you sure you want to delete event "${eventTitle}" and all its associated transactions?`)) {
        return;
    }

    try {
        const res = await fetch(`/api/admin/events/${eventId}`, { method: 'DELETE' });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast(`Event "${eventTitle}" deleted successfully.`, 'success');
            loadAdminStats();
            loadEvents();
        } else {
            showToast(data.message || 'Failed to delete event', 'error');
        }
    } catch (err) {
        showToast('Error deleting event', 'error');
    }
}

function openAdminRestoreModal() {
    openModal('modal-admin-restore');
}

async function submitAdminRestore(e) {
    e.preventDefault();
    if (!confirm('CRITICAL WARNING: This will replace the current database with the uploaded backup. Continue?')) {
        return;
    }

    const form = e.target;
    const formData = new FormData(form);
    const submitBtn = document.getElementById('btn-submit-restore');
    const originalText = submitBtn.innerHTML;

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1"></i> Restoring Database...';

    try {
        const res = await fetch('/api/admin/restore', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();

        if (res.ok && data.status === 'success') {
            showToast('Database restore completed successfully!', 'success');
            closeModal('modal-admin-restore');
            setTimeout(() => {
                location.reload();
            }, 1000);
        } else {
            showToast(data.message || 'Database restore failed', 'error');
        }
    } catch (err) {
        showToast('Error during restore process', 'error');
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
    }
}

// ============================================================================
// RECEIPT PREVIEW MODAL
// ============================================================================
function openReceiptModal(driveLink, fileName, thumbUrl) {
    const modal = document.getElementById('receipt-modal');
    const content = document.getElementById('receipt-modal-content');
    const title = document.getElementById('receipt-modal-title');
    const link = document.getElementById('receipt-drive-link');

    if (title) title.innerHTML = `<i class="fa-solid fa-receipt text-indigo-400 mr-2"></i> ${escapeHtml(fileName)}`;
    if (link) link.href = driveLink;

    if (content) {
        if (thumbUrl || driveLink.match(/\.(jpg|jpeg|png|webp|gif)/i)) {
            content.innerHTML = `<img src="${thumbUrl || driveLink}" alt="Receipt" class="max-h-[380px] max-w-full rounded-lg shadow-lg border border-slate-700 object-contain mx-auto">`;
        } else {
            content.innerHTML = `
                <div class="text-center py-8">
                    <i class="fa-solid fa-file-pdf text-5xl text-rose-400 mb-3"></i>
                    <p class="text-slate-300 font-semibold mb-2">${escapeHtml(fileName)}</p>
                    <p class="text-xs text-slate-400">PDF / Document stored securely in Google Drive.</p>
                </div>
            `;
        }
    }

    if (modal) modal.classList.remove('hidden');
}

function closeReceiptModal() {
    const modal = document.getElementById('receipt-modal');
    if (modal) modal.classList.add('hidden');
}

// ============================================================================
// MODAL & UI UTILITIES
// ============================================================================
function openModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.remove('hidden');
}

function closeModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.add('hidden');
}

function toggleExportMenu() {
    const menu = document.getElementById('export-dropdown-menu');
    if (menu) menu.classList.toggle('hidden');
}

window.addEventListener('click', (e) => {
    if (!e.target.closest('.dropdown-export')) {
        const menu = document.getElementById('export-dropdown-menu');
        if (menu && !menu.classList.contains('hidden')) {
            menu.classList.add('hidden');
        }
    }
});

// ============================================================================
// POP-OUT TOAST SYSTEM
// ============================================================================
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const normalizedType = (type === 'danger' || type === 'error') ? 'error' : type;

    const toast = document.createElement('div');
    toast.className = `toast toast-${normalizedType}`;
    
    let icon = 'fa-solid fa-circle-info';
    if (normalizedType === 'success') icon = 'fa-solid fa-circle-check';
    else if (normalizedType === 'error') icon = 'fa-solid fa-circle-exclamation';
    else if (normalizedType === 'warning') icon = 'fa-solid fa-triangle-exclamation';

    toast.innerHTML = `
        <div class="toast-icon-badge">
            <i class="${icon}"></i>
        </div>
        <div class="toast-message">${escapeHtml(message)}</div>
        <button type="button" class="toast-close-btn" title="Dismiss" onclick="dismissToast(this.closest('.toast'))">&times;</button>
    `;

    container.appendChild(toast);

    const timer = setTimeout(() => {
        dismissToast(toast);
    }, 4500);

    toast._dismissTimer = timer;
}

function dismissToast(toastEl) {
    if (!toastEl || toastEl._isDismissing) return;
    toastEl._isDismissing = true;
    if (toastEl._dismissTimer) clearTimeout(toastEl._dismissTimer);
    
    toastEl.classList.add('toast-hide');
    setTimeout(() => {
        toastEl.remove();
    }, 300);
}

// ============================================================================
// FORMATTERS
// ============================================================================
function formatNumber(num) {
    if (num === null || num === undefined || isNaN(num)) return '0.00';
    return Number(num).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatDate(isoStr) {
    if (!isoStr) return '-';
    try {
        const d = new Date(isoStr);
        return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
    } catch {
        return isoStr;
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
