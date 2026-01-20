/**
 * Storage Utilities
 * localStorage helpers with error handling
 * 
 * This module provides type-safe wrappers around localStorage
 * with automatic JSON serialization and error handling.
 * All keys are prefixed with 'embeddle_' to avoid conflicts.
 * 
 * @module utils/storage
 */

/**
 * @typedef {Object} GameSession
 * @property {string} code - Game code
 * @property {string} playerId - Player ID
 * @property {string} [playerName] - Player display name
 * @property {string} [sessionToken] - Session token for authenticated actions
 * @property {boolean} [isSingleplayer] - Whether this is a singleplayer game
 */

/**
 * @typedef {Object} RecentGame
 * @property {string} code - Game code
 * @property {string|null} playerId - Player ID
 * @property {string|null} playerName - Player name
 * @property {string|null} sessionToken - Session token
 * @property {boolean} isSingleplayer - Whether singleplayer
 * @property {number} lastSeen - Timestamp of last activity
 */

/**
 * Save game session to localStorage.
 * Also updates the recent games list and browser URL.
 * 
 * @param {Object} gameState - Current game state
 * @param {string} gameState.code - Game code
 * @param {string} gameState.playerId - Player ID
 * @param {string} [gameState.playerName] - Player name
 * @param {string} [gameState.sessionToken] - Session token
 * @param {boolean} [gameState.isSingleplayer] - Singleplayer flag
 */
export function saveGameSession(gameState) {
    if (gameState.code && gameState.playerId) {
        /** @type {GameSession} */
        const session = {
            code: gameState.code,
            playerId: gameState.playerId,
            playerName: gameState.playerName,
            sessionToken: gameState.sessionToken || null,  // SECURITY: Store session token
            isSingleplayer: gameState.isSingleplayer || false,
        };
        localStorage.setItem('embeddle_session', JSON.stringify(session));
        upsertRecentGame(session);
        // Update URL to include game code
        if (window.location.pathname !== `/game/${gameState.code}`) {
            history.pushState({ gameCode: gameState.code }, '', `/game/${gameState.code}`);
        }
    }
}

/**
 * Clear game session from localStorage.
 * Saves to recent games before clearing and resets URL.
 */
export function clearGameSession() {
    const existing = getSavedSession();
    if (existing) upsertRecentGame(existing);
    localStorage.removeItem('embeddle_session');
    if (window.location.pathname !== '/') {
        history.pushState({}, '', '/');
    }
}

/**
 * Get saved session from localStorage.
 * 
 * @returns {GameSession|null} Saved session or null if not found/invalid
 */
export function getSavedSession() {
    try {
        const saved = localStorage.getItem('embeddle_session');
        return saved ? JSON.parse(saved) : null;
    } catch (e) {
        localStorage.removeItem('embeddle_session');
        return null;
    }
}

/**
 * Get recent games list.
 * 
 * @returns {RecentGame[]} Array of recent games (max 10)
 */
export function getRecentGames() {
    try {
        const raw = localStorage.getItem('embeddle_recent_games');
        return raw ? JSON.parse(raw) : [];
    } catch (e) {
        localStorage.removeItem('embeddle_recent_games');
        return [];
    }
}

/**
 * Add or update a game in recent games list.
 * Maintains a maximum of 10 recent games.
 * 
 * @param {GameSession} session - Game session data
 */
export function upsertRecentGame(session) {
    if (!session?.code) return;
    const list = getRecentGames();
    const now = Date.now();
    /** @type {RecentGame} */
    const entry = {
        code: session.code,
        playerId: session.playerId || null,
        playerName: session.playerName || null,
        sessionToken: session.sessionToken || null,  // SECURITY: Store session token
        isSingleplayer: Boolean(session.isSingleplayer),
        lastSeen: now,
    };
    const idx = list.findIndex(x => x.code === entry.code && x.playerName === entry.playerName);
    if (idx >= 0) {
        list[idx] = { ...list[idx], ...entry };
    } else {
        list.unshift(entry);
    }
    localStorage.setItem('embeddle_recent_games', JSON.stringify(list.slice(0, 10)));
}

/**
 * Generate a random 32-character hex ID (128 bits for better security).
 * Uses crypto.getRandomValues when available for cryptographic randomness.
 * 
 * @returns {string} 32-character lowercase hex string
 */
export function generateHexId32() {
    const bytes = new Uint8Array(16);
    if (window.crypto && window.crypto.getRandomValues) {
        window.crypto.getRandomValues(bytes);
    } else {
        for (let i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256);
    }
    return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Generate a random 16-character hex ID.
 * 
 * @deprecated Use generateHexId32 instead for better security
 * @returns {string} 16-character lowercase hex string
 */
export function generateHexId16() {
    const bytes = new Uint8Array(8);
    if (window.crypto && window.crypto.getRandomValues) {
        window.crypto.getRandomValues(bytes);
    } else {
        for (let i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256);
    }
    return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Get or create a persistent spectator ID.
 * Creates a new ID if none exists or existing one is invalid.
 * 
 * @returns {string} 32-character hex spectator ID
 */
export function getOrCreateSpectatorId() {
    try {
        const key = 'embeddle_spectator_id';
        const existing = localStorage.getItem(key);
        // Accept both old 16-char and new 32-char IDs
        if (existing && /^[a-f0-9]{16,32}$/i.test(existing)) {
            return existing.toLowerCase();
        }
        const id = generateHexId32();
        localStorage.setItem(key, id);
        return id;
    } catch (e) {
        return generateHexId32();
    }
}

/**
 * Get game code from current URL.
 * Matches /game/{CODE} pattern.
 * 
 * @returns {string|null} Uppercase game code or null if not on game page
 */
export function getGameCodeFromURL() {
    const match = window.location.pathname.match(/^\/game\/([A-Z0-9]+)$/i);
    return match ? match[1].toUpperCase() : null;
}

/**
 * Get challenge ID from current URL.
 * Matches /challenge/{ID} pattern.
 * 
 * @returns {string|null} Uppercase challenge ID or null if not on challenge page
 */
export function getChallengeIdFromURL() {
    const match = window.location.pathname.match(/^\/challenge\/([A-Z0-9]+)$/i);
    return match ? match[1].toUpperCase() : null;
}

/**
 * @typedef {Object} GameOptions
 * @property {boolean} [musicEnabled] - Background music enabled
 * @property {boolean} [sfxEnabled] - Sound effects enabled
 * @property {number} [musicVolume] - Music volume (0-1)
 * @property {number} [sfxVolume] - SFX volume (0-1)
 */

/**
 * Save options to localStorage.
 * 
 * @param {GameOptions} options - Options object to save
 */
export function saveOptions(options) {
    try {
        localStorage.setItem('embeddle_options', JSON.stringify(options));
    } catch (e) {
        // ignore
    }
}

/**
 * Load options from localStorage.
 * 
 * @param {GameOptions} defaults - Default options to use if none saved
 * @returns {GameOptions} Merged options (saved + defaults)
 */
export function loadOptions(defaults) {
    try {
        const raw = localStorage.getItem('embeddle_options');
        const parsed = raw ? JSON.parse(raw) : null;
        if (parsed && typeof parsed === 'object') {
            return { ...defaults, ...parsed };
        }
        return { ...defaults };
    } catch (e) {
        return { ...defaults };
    }
}

/**
 * Get saved auth token.
 * 
 * @returns {string|null} JWT token or null
 */
export function getAuthToken() {
    return localStorage.getItem('embeddle_auth_token');
}

/**
 * Save auth token.
 * 
 * @param {string} token - JWT token to save
 */
export function setAuthToken(token) {
    localStorage.setItem('embeddle_auth_token', token);
}

/**
 * Remove auth token.
 */
export function removeAuthToken() {
    localStorage.removeItem('embeddle_auth_token');
}

/**
 * Get saved player name.
 * 
 * @returns {string|null} Player name or null
 */
export function getSavedName() {
    return localStorage.getItem('embeddle_name');
}

/**
 * Save player name.
 * 
 * @param {string} name - Player name to save
 */
export function setSavedName(name) {
    localStorage.setItem('embeddle_name', name);
}

/**
 * Remove saved player name.
 */
export function removeSavedName() {
    localStorage.removeItem('embeddle_name');
}

/**
 * Generic save to localStorage with error handling.
 * Value is automatically JSON stringified.
 * 
 * @param {string} key - Storage key (will be prefixed with embeddle_)
 * @param {*} value - Value to store
 */
export function saveToStorage(key, value) {
    try {
        localStorage.setItem(`embeddle_${key}`, JSON.stringify(value));
    } catch (e) {
        console.warn('[Storage] Failed to save:', key, e);
    }
}

/**
 * Generic load from localStorage with error handling.
 * Value is automatically JSON parsed.
 * 
 * @param {string} key - Storage key (will be prefixed with embeddle_)
 * @returns {*} Parsed value or null if not found/invalid
 */
export function loadFromStorage(key) {
    try {
        const raw = localStorage.getItem(`embeddle_${key}`);
        return raw ? JSON.parse(raw) : null;
    } catch (e) {
        console.warn('[Storage] Failed to load:', key, e);
        return null;
    }
}

