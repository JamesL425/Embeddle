/**
 * Game State Management
 * Centralized game state with reactive updates
 * 
 * This module provides a singleton state store for all game-related data.
 * Components can subscribe to state changes for reactive updates.
 * 
 * @module state/gameState
 */

import { saveGameSession, clearGameSession } from '../utils/storage.js';

/**
 * @typedef {Object} AuthUser
 * @property {string} id - User ID
 * @property {string} email - User email
 * @property {string} name - Display name
 * @property {string} avatar - Avatar URL
 * @property {boolean} is_admin - Whether user is admin
 * @property {boolean} [is_donor] - Whether user is a donor
 */

/**
 * @typedef {Object} GameState
 * @property {string|null} code - Current game code
 * @property {string|null} playerId - Current player ID
 * @property {string|null} playerName - Current player name
 * @property {string|null} sessionToken - Session token for authenticated actions
 * @property {boolean} isHost - Whether current player is host
 * @property {number|null} pollingInterval - Polling interval ID
 * @property {Object|null} theme - Current game theme
 * @property {string[]|null} wordPool - Player's word pool
 * @property {string[]|null} allThemeWords - All words in current theme
 * @property {string|null} myVote - Player's theme vote
 * @property {string|null} authToken - JWT auth token
 * @property {AuthUser|null} authUser - Authenticated user data
 * @property {boolean} isSpectator - Whether viewing as spectator
 * @property {string|null} spectatorId - Spectator ID
 * @property {boolean} isSingleplayer - Whether in singleplayer mode
 * @property {Object|null} pendingChallenge - Pending challenge data
 * @property {Object|null} userData - Additional user data
 */

/** @type {GameState} */
const gameState = {
    code: null,
    playerId: null,
    playerName: null,
    sessionToken: null,  // SECURITY: Session token for authenticated game actions
    isHost: false,
    pollingInterval: null,
    theme: null,
    wordPool: null,
    allThemeWords: null,
    myVote: null,
    authToken: null,
    authUser: null,
    isSpectator: false,
    spectatorId: null,
    isSingleplayer: false,
    pendingChallenge: null,
    userData: null,
};

/**
 * @typedef {function(string, *, GameState): void} StateChangeCallback
 */

/** @type {Set<StateChangeCallback>} */
const listeners = new Set();

/**
 * Subscribe to state changes.
 * 
 * @param {StateChangeCallback} callback - Called when state changes with (key, value, state)
 * @returns {function(): void} Unsubscribe function
 * 
 * @example
 * const unsubscribe = subscribe((key, value, state) => {
 *     if (key === 'code') {
 *         console.log('Game code changed to:', value);
 *     }
 * });
 * // Later: unsubscribe();
 */
export function subscribe(callback) {
    listeners.add(callback);
    return () => listeners.delete(callback);
}

/**
 * Notify all listeners of state change.
 * 
 * @private
 * @param {string} key - Changed key
 * @param {*} value - New value
 */
function notify(key, value) {
    listeners.forEach(cb => {
        try {
            cb(key, value, gameState);
        } catch (e) {
            console.error('State listener error:', e);
        }
    });
}

/**
 * Get entire game state (read-only copy).
 * 
 * @returns {GameState} Copy of current state
 */
export function getState() {
    return { ...gameState };
}

/**
 * Get a specific state value.
 * 
 * @param {keyof GameState} key - State key to get
 * @returns {*} Value for the key
 */
export function get(key) {
    return gameState[key];
}

/**
 * Set a state value.
 * Notifies listeners if value changed.
 * 
 * @param {keyof GameState} key - State key to set
 * @param {*} value - New value
 */
export function set(key, value) {
    const oldValue = gameState[key];
    if (oldValue !== value) {
        gameState[key] = value;
        notify(key, value);
    }
}

/**
 * Update multiple state values at once.
 * Notifies listeners for each changed value.
 * 
 * @param {Partial<GameState>} updates - Object with key-value pairs to update
 */
export function update(updates) {
    Object.entries(updates).forEach(([key, value]) => {
        if (gameState[key] !== value) {
            gameState[key] = value;
            notify(key, value);
        }
    });
}

/**
 * Reset game-specific state (keeps auth).
 * Clears game session from localStorage.
 */
export function resetGame() {
    gameState.code = null;
    gameState.playerId = null;
    gameState.sessionToken = null;  // SECURITY: Clear session token
    gameState.isHost = false;
    gameState.pollingInterval = null;
    gameState.theme = null;
    gameState.wordPool = null;
    gameState.allThemeWords = null;
    gameState.myVote = null;
    gameState.isSpectator = false;
    gameState.spectatorId = null;
    gameState.isSingleplayer = false;
    gameState.pendingChallenge = null;
    clearGameSession();
    notify('reset', null);
}

/**
 * Clear all state (full logout).
 * Resets everything including auth data.
 */
export function clearAll() {
    Object.keys(gameState).forEach(key => {
        gameState[key] = null;
    });
    gameState.isHost = false;
    gameState.isSpectator = false;
    gameState.isSingleplayer = false;
    clearGameSession();
    notify('clearAll', null);
}

/**
 * Save current game session to localStorage.
 */
export function persistSession() {
    saveGameSession(gameState);
}

/**
 * Set auth data.
 * 
 * @param {string} token - JWT token
 * @param {AuthUser} user - User data object
 */
export function setAuth(token, user) {
    gameState.authToken = token;
    gameState.authUser = user;
    if (user?.name) {
        gameState.playerName = user.name;
    }
    notify('auth', { token, user });
}

/**
 * Clear auth data.
 */
export function clearAuth() {
    gameState.authToken = null;
    gameState.authUser = null;
    notify('auth', null);
}

/**
 * Check if user is authenticated.
 * 
 * @returns {boolean} True if user has valid auth token
 */
export function isAuthenticated() {
    return Boolean(gameState.authToken);
}

/**
 * Check if user has admin privileges.
 * 
 * @returns {boolean} True if user is admin
 */
export function isAdmin() {
    return gameState.authUser?.is_admin;
}

// Export the raw state for legacy compatibility (read-only access recommended)
export { gameState };

