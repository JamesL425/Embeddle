/**
 * EMBEDDLE - Daily Ops System
 * Handles daily quests, currency, and shop purchases
 */

// Daily ops state
let dailyState = {
    panelOpen: false,
    wallet: { credits: 0 },
    quests: [],
    ownedCosmetics: {},
    date: '',
    loading: false,
};

// ============ PANEL TOGGLE ============

function toggleDailyPanel() {
    dailyState.panelOpen = !dailyState.panelOpen;
    const panel = document.getElementById('daily-panel');
    if (panel) {
        panel.classList.toggle('open', dailyState.panelOpen);
    }
    if (dailyState.panelOpen) {
        loadDaily();
    }
}

function closeDailyPanel() {
    dailyState.panelOpen = false;
    const panel = document.getElementById('daily-panel');
    if (panel) panel.classList.remove('open');
}

// ============ LOAD DAILY DATA ============

async function loadDaily() {
    if (!gameState.authToken) {
        renderDailyNoAuth();
        return;
    }
    
    if (dailyState.loading) return;
    dailyState.loading = true;
    
    try {
        const response = await fetch(`${API_BASE}/api/user/daily`, {
            headers: { 'Authorization': `Bearer ${gameState.authToken}` }
        });
        
        if (!response.ok) {
            throw new Error('Failed to load daily data');
        }
        
        const data = await response.json();
        dailyState.wallet = data.wallet || { credits: 0 };
        dailyState.quests = data.quests || [];
        dailyState.date = data.date || '';
        dailyState.ownedCosmetics = data.owned_cosmetics || {};
        
        renderDailyPanel();
    } catch (e) {
        console.error('Failed to load daily data:', e);
        renderDailyError();
    } finally {
        dailyState.loading = false;
    }
}

// ============ CLAIM QUEST ============

async function claimQuest(questId) {
    if (!gameState.authToken) {
        showError('Please sign in with Google to claim quests');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/api/user/daily/claim`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${gameState.authToken}`
            },
            body: JSON.stringify({ quest_id: questId })
        });
        
        if (!response.ok) {
            const err = await response.json();
            showError(err.detail || 'Failed to claim quest');
            return;
        }
        
        const data = await response.json();
        dailyState.wallet = data.wallet || dailyState.wallet;
        
        // Update the quest in local state
        const quest = dailyState.quests.find(q => q.id === questId);
        if (quest) {
            quest.claimed = true;
        }
        
        renderDailyPanel();
        showSuccess(`+${data.reward_credits || 0} credits!`);
    } catch (e) {
        console.error('Failed to claim quest:', e);
        showError('Failed to claim quest');
    }
}

// ============ PURCHASE COSMETIC ============

async function purchaseCosmetic(category, cosmeticId) {
    if (!gameState.authToken) {
        showError('Please sign in with Google to purchase cosmetics');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/api/shop/purchase`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${gameState.authToken}`
            },
            body: JSON.stringify({ category, cosmetic_id: cosmeticId })
        });
        
        if (!response.ok) {
            const err = await response.json();
            showError(err.detail || 'Failed to purchase cosmetic');
            return;
        }
        
        const data = await response.json();
        dailyState.wallet = data.wallet || dailyState.wallet;
        dailyState.ownedCosmetics = data.owned_cosmetics || dailyState.ownedCosmetics;
        
        renderDailyPanel();
        
        // Refresh cosmetics panel so newly-owned item becomes equippable
        if (typeof loadUserCosmetics === 'function') {
            loadUserCosmetics();
        }
        if (typeof updateCosmeticsPanel === 'function') {
            updateCosmeticsPanel();
        }
        
        showSuccess('Cosmetic purchased!');
    } catch (e) {
        console.error('Failed to purchase cosmetic:', e);
        showError('Failed to purchase cosmetic');
    }
}

// ============ RENDER FUNCTIONS ============

function renderDailyNoAuth() {
    const creditsEl = document.getElementById('daily-credits');
    const questsEl = document.getElementById('daily-quests');
    const shopEl = document.getElementById('daily-shop');
    
    if (creditsEl) creditsEl.textContent = '0';
    if (questsEl) questsEl.innerHTML = '<div class="daily-empty">Sign in with Google to access daily quests.</div>';
    if (shopEl) shopEl.innerHTML = '<div class="daily-empty">Sign in with Google to access the shop.</div>';
}

function renderDailyError() {
    const questsEl = document.getElementById('daily-quests');
    const shopEl = document.getElementById('daily-shop');
    
    if (questsEl) questsEl.innerHTML = '<div class="daily-empty">Failed to load quests. Try again later.</div>';
    if (shopEl) shopEl.innerHTML = '<div class="daily-empty">Failed to load shop. Try again later.</div>';
}

function renderDailyPanel() {
    renderDailyCredits();
    renderDailyQuests();
    renderDailyShop();
}

function renderDailyCredits() {
    const creditsEl = document.getElementById('daily-credits');
    if (creditsEl) {
        creditsEl.textContent = dailyState.wallet.credits || 0;
    }
}

function renderDailyQuests() {
    const container = document.getElementById('daily-quests');
    if (!container) return;
    
    if (!dailyState.quests || dailyState.quests.length === 0) {
        container.innerHTML = '<div class="daily-empty">No quests available.</div>';
        return;
    }
    
    let html = '';
    for (const quest of dailyState.quests) {
        const progress = quest.progress || 0;
        const target = quest.target || 1;
        const completed = progress >= target;
        const claimed = quest.claimed || false;
        const reward = quest.reward_credits || 0;
        const progressPct = Math.min(100, Math.round((progress / target) * 100));
        
        let statusClass = '';
        let statusText = '';
        let actionHtml = '';
        
        if (claimed) {
            statusClass = 'claimed';
            statusText = '✓ CLAIMED';
        } else if (completed) {
            statusClass = 'completed';
            statusText = 'READY';
            actionHtml = `<button class="btn btn-small btn-primary quest-claim-btn" data-quest-id="${quest.id}">CLAIM +${reward}</button>`;
        } else {
            statusClass = 'in-progress';
            statusText = `${progress}/${target}`;
        }
        
        html += `
            <div class="daily-quest ${statusClass}">
                <div class="quest-info">
                    <div class="quest-title">${escapeHtml(quest.title || 'Quest')}</div>
                    <div class="quest-desc">${escapeHtml(quest.description || '')}</div>
                    <div class="quest-progress-bar">
                        <div class="quest-progress-fill" style="width: ${progressPct}%"></div>
                    </div>
                </div>
                <div class="quest-status">
                    <span class="quest-status-text">${statusText}</span>
                    ${actionHtml}
                    ${!claimed && !completed ? `<span class="quest-reward">+${reward}</span>` : ''}
                </div>
            </div>
        `;
    }
    
    container.innerHTML = html;
    
    // Add click handlers for claim buttons
    container.querySelectorAll('.quest-claim-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const questId = btn.dataset.questId;
            if (questId) claimQuest(questId);
        });
    });
}

function renderDailyShop() {
    const container = document.getElementById('daily-shop');
    if (!container) return;
    
    // Get shop items from cosmetics catalog (items with price > 0)
    if (!cosmeticsState.catalog) {
        container.innerHTML = '<div class="daily-empty">Loading shop...</div>';
        return;
    }
    
    const shopItems = [];
    const categoryMap = {
        'card_borders': 'card_border',
        'card_backgrounds': 'card_background',
        'name_colors': 'name_color',
        'badges': 'badge',
        'elimination_effects': 'elimination_effect',
        'guess_effects': 'guess_effect',
        'turn_indicators': 'turn_indicator',
        'victory_effects': 'victory_effect',
        'matrix_colors': 'matrix_color',
        'particle_overlays': 'particle_overlay',
        'seasonal_themes': 'seasonal_theme',
        'alt_backgrounds': 'alt_background',
    };
    
    for (const [catalogKey, items] of Object.entries(cosmeticsState.catalog)) {
        const categoryKey = categoryMap[catalogKey];
        if (!categoryKey) continue;
        
        for (const [itemId, item] of Object.entries(items)) {
            const price = parseInt(item.price || 0, 10);
            if (price > 0 && !item.premium) {
                const owned = isOwnedCosmetic(categoryKey, itemId);
                shopItems.push({
                    categoryKey,
                    catalogKey,
                    itemId,
                    item,
                    price,
                    owned,
                });
            }
        }
    }
    
    if (shopItems.length === 0) {
        container.innerHTML = '<div class="daily-empty">No items in shop.</div>';
        return;
    }
    
    // Group by category for display
    const byCategory = {};
    for (const si of shopItems) {
        if (!byCategory[si.categoryKey]) {
            byCategory[si.categoryKey] = [];
        }
        byCategory[si.categoryKey].push(si);
    }
    
    const categoryLabels = {
        'card_border': 'Card Border',
        'card_background': 'Card Background',
        'name_color': 'Name Color',
        'badge': 'Badge',
        'elimination_effect': 'Elimination Effect',
        'guess_effect': 'Guess Effect',
        'turn_indicator': 'Turn Indicator',
        'victory_effect': 'Victory Effect',
        'matrix_color': 'Matrix Color',
        'particle_overlay': 'Particles',
        'seasonal_theme': 'Seasonal',
        'alt_background': 'Background',
    };
    
    let html = '';
    for (const [catKey, items] of Object.entries(byCategory)) {
        html += `<div class="shop-category"><div class="shop-category-label">${categoryLabels[catKey] || catKey}</div>`;
        for (const si of items) {
            const canAfford = dailyState.wallet.credits >= si.price;
            const icon = si.item.icon || '';
            
            let btnHtml = '';
            if (si.owned) {
                btnHtml = '<span class="shop-owned">✓ OWNED</span>';
            } else if (canAfford) {
                btnHtml = `<button class="btn btn-small btn-primary shop-buy-btn" data-category="${si.categoryKey}" data-id="${si.itemId}">${si.price} ¢</button>`;
            } else {
                btnHtml = `<span class="shop-price locked">${si.price} ¢</span>`;
            }
            
            html += `
                <div class="shop-item ${si.owned ? 'owned' : ''} ${!canAfford && !si.owned ? 'locked' : ''}">
                    <div class="shop-item-info">
                        ${icon ? `<span class="shop-item-icon">${icon}</span>` : ''}
                        <span class="shop-item-name">${escapeHtml(si.item.name || si.itemId)}</span>
                    </div>
                    <div class="shop-item-action">
                        ${btnHtml}
                    </div>
                </div>
            `;
        }
        html += '</div>';
    }
    
    container.innerHTML = html;
    
    // Add click handlers for buy buttons
    container.querySelectorAll('.shop-buy-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const category = btn.dataset.category;
            const id = btn.dataset.id;
            if (category && id) purchaseCosmetic(category, id);
        });
    });
}

function isOwnedCosmetic(categoryKey, cosmeticId) {
    const owned = dailyState.ownedCosmetics[categoryKey];
    if (!Array.isArray(owned)) return false;
    return owned.includes(cosmeticId);
}

// Helper to escape HTML (if not already defined)
function escapeHtml(str) {
    if (typeof str !== 'string') return '';
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// Helper to show success message (if not already defined)
function showSuccess(msg) {
    // Use existing showError with a different style, or create a simple alert
    if (typeof showError === 'function') {
        // Temporarily show as a "success" style error
        const el = document.getElementById('error-toast');
        if (el) {
            el.textContent = msg;
            el.classList.add('show', 'success');
            setTimeout(() => {
                el.classList.remove('show', 'success');
            }, 3000);
            return;
        }
    }
    console.log('Success:', msg);
}

// ============ INIT ============

document.addEventListener('DOMContentLoaded', () => {
    // Panel toggle
    document.getElementById('daily-btn')?.addEventListener('click', toggleDailyPanel);
    document.getElementById('close-daily-btn')?.addEventListener('click', closeDailyPanel);
});

// Expose for external calls (e.g., after game ends)
window.loadDaily = loadDaily;
window.toggleDailyPanel = toggleDailyPanel;
window.closeDailyPanel = closeDailyPanel;

