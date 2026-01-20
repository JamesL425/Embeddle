/**
 * Authentication Service
 * Handles OAuth, JWT tokens, and user sessions
 * 
 * This module manages all authentication-related functionality:
 * - Google OAuth flow initiation
 * - JWT token handling from URL params and localStorage
 * - Guest (name-only) login
 * - Session management
 * 
 * @module services/auth
 */

import { apiCall, getApiBase } from './api.js';
import * as gameState from '../state/gameState.js';
import { 
    getAuthToken, setAuthToken, removeAuthToken,
    getSavedName, setSavedName, removeSavedName
} from '../utils/storage.js';

/**
 * @typedef {Object} AuthUser
 * @property {string} id - User ID
 * @property {string} email - User email
 * @property {string} name - Display name
 * @property {string} [avatar] - Avatar URL
 * @property {boolean} [is_admin] - Whether user is admin
 * @property {boolean} [is_donor] - Whether user is donor
 * @property {boolean} [isGuest] - Whether this is a guest user
 */

/**
 * Initialize authentication from URL params or localStorage.
 * 
 * Checks for:
 * 1. OAuth callback token in URL (auth_token param)
 * 2. OAuth error in URL (auth_error param)
 * 3. Existing token in localStorage
 * 4. Saved guest name in localStorage
 * 
 * @returns {Promise<AuthUser|null>} User data if authenticated, null otherwise
 * @throws {Error} If OAuth callback contains an error
 * 
 * @example
 * try {
 *     const user = await initAuth();
 *     if (user) {
 *         console.log('Logged in as:', user.name);
 *     }
 * } catch (e) {
 *     console.error('Auth failed:', e.message);
 * }
 */
export async function initAuth() {
    // Check for OAuth callback token in URL
    const urlParams = new URLSearchParams(window.location.search);
    const authToken = urlParams.get('auth_token');
    const authError = urlParams.get('auth_error');
    const authErrorDescription = urlParams.get('auth_error_description') || urlParams.get('google_error_description') || '';
    const googleError = urlParams.get('google_error') || '';
    const authErrorStatus = urlParams.get('auth_error_status') || '';
    
    if (authError) {
        let msg = 'Login failed: ' + authError;
        if (googleError) msg += ` (${googleError})`;
        if (authErrorDescription) msg += ` - ${authErrorDescription}`;
        if (authErrorStatus) msg += ` [${authErrorStatus}]`;
        // Clean URL
        window.history.replaceState({}, document.title, window.location.pathname);
        throw new Error(msg);
    }
    
    if (authToken) {
        // Store token and fetch user info
        setAuthToken(authToken);
        // Clean URL
        window.history.replaceState({}, document.title, window.location.pathname);
        return await loadAuthenticatedUser(authToken);
    }
    
    // Check for existing auth token
    const savedToken = getAuthToken();
    if (savedToken) {
        return await loadAuthenticatedUser(savedToken);
    }
    
    // Fall back to simple name-based login
    const savedName = getSavedName();
    if (savedName) {
        gameState.set('playerName', savedName);
        return { name: savedName, isGuest: true };
    }
    
    return null;
}

/**
 * Load authenticated user data from server.
 * Validates the token and fetches full user profile.
 * 
 * @param {string} token - JWT token
 * @returns {Promise<AuthUser|null>} User data or null if token invalid
 */
export async function loadAuthenticatedUser(token) {
    try {
        const user = await apiCall('/api/auth/me', 'GET', null, { authToken: token });
        gameState.setAuth(token, user);
        return user;
    } catch (error) {
        console.error('Failed to load authenticated user:', error);
        removeAuthToken();
        gameState.clearAuth();
        return null;
    }
}

/**
 * Start Google OAuth flow.
 * Redirects the browser to Google's OAuth consent page.
 */
export function loginWithGoogle() {
    window.location.href = `${getApiBase()}/api/auth/google`;
}

/**
 * Login with simple name (guest mode).
 * Does not require server authentication.
 * 
 * @param {string} name - Player display name
 * @returns {AuthUser} Guest user object
 * @throws {Error} If name is invalid or reserved
 * 
 * @example
 * try {
 *     const user = loginAsGuest('PlayerOne');
 *     console.log('Playing as:', user.name);
 * } catch (e) {
 *     alert(e.message);
 * }
 */
export function loginAsGuest(name) {
    // Sanitize name
    const sanitizedName = name.replace(/<[^>]*>/g, '').substring(0, 20).trim();
    
    if (!sanitizedName) {
        throw new Error('Please enter a valid callsign');
    }
    
    // Check for admin callsign
    if (sanitizedName.toLowerCase() === 'admin') {
        throw new Error('This callsign is reserved. Please choose another.');
    }
    
    gameState.set('playerName', sanitizedName);
    setSavedName(sanitizedName);
    
    return { name: sanitizedName, isGuest: true };
}

/**
 * Logout current user.
 * Clears all auth state and saved credentials.
 */
export function logout() {
    gameState.clearAuth();
    gameState.set('playerName', null);
    removeSavedName();
    removeAuthToken();
}

/**
 * Check if user is authenticated (has valid token).
 * 
 * @returns {boolean} True if user has auth token
 */
export function isAuthenticated() {
    return gameState.isAuthenticated();
}

/**
 * Check if user has admin privileges.
 * 
 * @returns {boolean} True if user is admin
 */
export function isAdmin() {
    return gameState.isAdmin();
}

/**
 * Get current authenticated user.
 * 
 * @returns {AuthUser|null} Current user or null if not authenticated
 */
export function getCurrentUser() {
    return gameState.get('authUser');
}

/**
 * Get current player name.
 * Returns the display name for either authenticated or guest users.
 * 
 * @returns {string|null} Player name or null
 */
export function getPlayerName() {
    return gameState.get('playerName');
}

/**
 * Check if name is the admin callsign.
 * Used to prevent users from using reserved names.
 * 
 * @param {string} name - Name to check
 * @returns {boolean} True if name is 'admin' (case-insensitive)
 */
export function isAdminCallsign(name) {
    return name?.toLowerCase() === 'admin';
}

export default {
    initAuth,
    loadAuthenticatedUser,
    loginWithGoogle,
    loginAsGuest,
    logout,
    isAuthenticated,
    isAdmin,
    getCurrentUser,
    getPlayerName,
    isAdminCallsign,
};

