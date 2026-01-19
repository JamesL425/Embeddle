/**
 * Panels UI Component
 * Manages side panels (options, cosmetics, daily) and top bar
 */

import { optionsState, getOptions } from '../state/optionsState.js';
import { saveOptions, loadFromStorage, saveToStorage } from '../utils/storage.js';
import { applyMusicPreference, setMusicVolume, setSfxVolume } from '../utils/audio.js';
import * as chat from './chat.js';

// Panel states
let optionsPanelOpen = false;
let topbarCollapsed = false;

/**
 * Initialize panels
 */
export function init() {
    // Top bar toggle (mobile)
    initTopbarToggle();
    
    // Options panel
    document.getElementById('options-btn')?.addEventListener('click', toggleOptions);
    document.getElementById('close-options-btn')?.addEventListener('click', closeOptions);
    
    // Option toggle handlers
    document.getElementById('opt-chat-enabled')?.addEventListener('change', (e) => {
        optionsState.chatEnabled = Boolean(e.target.checked);
        saveOptions(optionsState);
        applyOptions();
    });
    
    // Music volume slider
    document.getElementById('opt-music-volume')?.addEventListener('input', (e) => {
        const volume = parseInt(e.target.value, 10) || 0;
        optionsState.musicVolume = volume;
        setMusicVolume(volume);
        updateVolumeDisplay('music-volume-display', volume);
        saveOptions(optionsState);
        applyOptions();
    });
    
    // SFX volume slider
    document.getElementById('opt-sfx-volume')?.addEventListener('input', (e) => {
        const volume = parseInt(e.target.value, 10) || 0;
        optionsState.sfxVolume = volume;
        setSfxVolume(volume);
        updateVolumeDisplay('sfx-volume-display', volume);
        saveOptions(optionsState);
    });
    
    document.getElementById('opt-turn-notifications')?.addEventListener('change', (e) => {
        optionsState.turnNotificationsEnabled = Boolean(e.target.checked);
        saveOptions(optionsState);
        applyOptions();
    });
    document.getElementById('opt-nerd-mode')?.addEventListener('change', (e) => {
        optionsState.nerdMode = Boolean(e.target.checked);
        saveOptions(optionsState);
        applyOptions();
    });
    
    // ML Info modal
    document.getElementById('ml-info-btn')?.addEventListener('click', () => {
        const modal = document.getElementById('ml-info-modal');
        if (modal) modal.classList.add('show');
    });
    document.getElementById('close-ml-info-btn')?.addEventListener('click', () => {
        const modal = document.getElementById('ml-info-modal');
        if (modal) modal.classList.remove('show');
    });
}

/**
 * Update volume display text
 * @param {string} elementId - ID of the display element
 * @param {number} volume - Volume value 0-100
 */
function updateVolumeDisplay(elementId, volume) {
    const el = document.getElementById(elementId);
    if (el) {
        el.textContent = `${volume}%`;
    }
}

/**
 * Initialize top bar toggle for mobile
 */
function initTopbarToggle() {
    const toggle = document.getElementById('topbar-toggle');
    const loggedInBox = document.getElementById('logged-in-box');
    
    if (!toggle || !loggedInBox) return;
    
    // Load saved state (default to collapsed on mobile)
    const savedState = loadFromStorage('topbar_collapsed');
    topbarCollapsed = savedState !== null ? savedState : true;
    
    // Apply initial state
    updateTopbarState();
    
    // Add click handler
    toggle.addEventListener('click', () => {
        topbarCollapsed = !topbarCollapsed;
        saveToStorage('topbar_collapsed', topbarCollapsed);
        updateTopbarState();
    });
}

/**
 * Update top bar collapsed/expanded state
 */
function updateTopbarState() {
    const loggedInBox = document.getElementById('logged-in-box');
    const toggle = document.getElementById('topbar-toggle');
    const nameEl = document.getElementById('logged-in-name');
    
    if (!loggedInBox || !toggle) return;
    
    loggedInBox.classList.toggle('collapsed', topbarCollapsed);
    toggle.setAttribute('aria-expanded', String(!topbarCollapsed));
    
    // Update toggle to show username when collapsed
    if (nameEl) {
        toggle.setAttribute('data-username', nameEl.textContent || 'OPERATIVE');
    }
}

/**
 * Update the username displayed in the toggle (call when name changes)
 */
export function updateTopbarUsername(name) {
    const toggle = document.getElementById('topbar-toggle');
    const nameEl = document.getElementById('logged-in-name');
    
    if (nameEl) {
        nameEl.textContent = name;
    }
    if (toggle) {
        toggle.setAttribute('data-username', name);
    }
}

/**
 * Toggle options panel
 */
export function toggleOptions() {
    optionsPanelOpen = !optionsPanelOpen;
    const panel = document.getElementById('options-panel');
    if (panel) {
        panel.classList.toggle('open', optionsPanelOpen);
    }
    if (optionsPanelOpen) {
        applyOptionsToUI();
    }
}

/**
 * Close options panel
 */
export function closeOptions() {
    optionsPanelOpen = false;
    const panel = document.getElementById('options-panel');
    if (panel) panel.classList.remove('open');
}

/**
 * Apply options to UI elements
 */
export function applyOptionsToUI() {
    const chatCb = document.getElementById('opt-chat-enabled');
    const musicSlider = document.getElementById('opt-music-volume');
    const sfxSlider = document.getElementById('opt-sfx-volume');
    const turnNotifCb = document.getElementById('opt-turn-notifications');
    const nerdCb = document.getElementById('opt-nerd-mode');

    if (chatCb) chatCb.checked = Boolean(optionsState.chatEnabled);
    
    // Handle music volume (migrate from old musicEnabled boolean)
    let musicVol = optionsState.musicVolume;
    if (typeof musicVol !== 'number') {
        // Migrate from old boolean format
        musicVol = optionsState.musicEnabled === false ? 0 : 12;
        optionsState.musicVolume = musicVol;
    }
    if (musicSlider) {
        musicSlider.value = musicVol;
        updateVolumeDisplay('music-volume-display', musicVol);
    }
    
    // Handle SFX volume (migrate from old individual toggles)
    let sfxVol = optionsState.sfxVolume;
    if (typeof sfxVol !== 'number') {
        // Default to 50% for new users, or based on old settings
        sfxVol = 50;
        optionsState.sfxVolume = sfxVol;
    }
    if (sfxSlider) {
        sfxSlider.value = sfxVol;
        updateVolumeDisplay('sfx-volume-display', sfxVol);
    }
    
    // Set audio module volumes
    setMusicVolume(musicVol);
    setSfxVolume(sfxVol);
    
    if (turnNotifCb) turnNotifCb.checked = Boolean(optionsState.turnNotificationsEnabled);
    if (nerdCb) nerdCb.checked = Boolean(optionsState.nerdMode);
}

/**
 * Apply options (update UI state based on options)
 */
export function applyOptions() {
    // Update chat visibility
    chat.updateVisibility();
    
    // Apply music volume preference
    const musicVol = typeof optionsState.musicVolume === 'number' ? optionsState.musicVolume : 12;
    applyMusicPreference(musicVol);
    
    // Render chat if needed
    chat.render();
    
    // Apply nerd mode to body class
    document.body.classList.toggle('nerd-mode', Boolean(optionsState.nerdMode));
}

export default {
    init,
    toggleOptions,
    closeOptions,
    applyOptionsToUI,
    applyOptions,
    updateTopbarUsername,
};
