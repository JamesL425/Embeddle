/**
 * Bagofwordsdle - Client Application
 */

const API_BASE = window.location.origin;

// Game state
let gameState = {
    code: null,
    playerId: null,
    playerName: null,
    isHost: false,
    pollingInterval: null,
};

// DOM Elements
const screens = {
    home: document.getElementById('home-screen'),
    join: document.getElementById('join-screen'),
    lobby: document.getElementById('lobby-screen'),
    game: document.getElementById('game-screen'),
    gameover: document.getElementById('gameover-screen'),
};

// Utility functions
function showScreen(screenName) {
    Object.values(screens).forEach(screen => screen.classList.remove('active'));
    screens[screenName].classList.add('active');
}

function showError(message) {
    alert(message); // Simple for now, could be a toast
}

async function apiCall(endpoint, method = 'GET', body = null) {
    const options = {
        method,
        headers: { 'Content-Type': 'application/json' },
    };
    
    if (body) {
        options.body = JSON.stringify(body);
    }
    
    const response = await fetch(`${API_BASE}${endpoint}`, options);
    const data = await response.json();
    
    if (!response.ok) {
        throw new Error(data.detail || 'An error occurred');
    }
    
    return data;
}

// Screen: Home
document.getElementById('create-game-btn').addEventListener('click', async () => {
    try {
        const data = await apiCall('/api/games', 'POST');
        gameState.code = data.code;
        
        // Pre-fill game code and show join screen
        document.getElementById('game-code').value = data.code;
        document.getElementById('game-code').readOnly = true;
        showScreen('join');
    } catch (error) {
        showError(error.message);
    }
});

document.getElementById('join-game-btn').addEventListener('click', () => {
    document.getElementById('game-code').value = '';
    document.getElementById('game-code').readOnly = false;
    showScreen('join');
});

// Screen: Join
document.getElementById('back-home-btn').addEventListener('click', () => {
    gameState.code = null;
    showScreen('home');
});

document.getElementById('join-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const code = document.getElementById('game-code').value.trim().toUpperCase();
    const name = document.getElementById('player-name').value.trim();
    const secretWord = document.getElementById('secret-word').value.trim();
    
    if (!code || !name || !secretWord) {
        showError('Please fill in all fields');
        return;
    }
    
    try {
        const data = await apiCall(`/api/games/${code}/join`, 'POST', {
            name,
            secret_word: secretWord,
        });
        
        gameState.code = code;
        gameState.playerId = data.player_id;
        gameState.playerName = name;
        
        // Clear form
        document.getElementById('player-name').value = '';
        document.getElementById('secret-word').value = '';
        
        // Show lobby and start polling
        showLobby();
    } catch (error) {
        showError(error.message);
    }
});

// Screen: Lobby
function showLobby() {
    document.getElementById('lobby-code').textContent = gameState.code;
    showScreen('lobby');
    startPolling();
}

document.getElementById('copy-code-btn').addEventListener('click', () => {
    navigator.clipboard.writeText(gameState.code);
    document.getElementById('copy-code-btn').textContent = 'Copied!';
    setTimeout(() => {
        document.getElementById('copy-code-btn').textContent = 'Copy';
    }, 2000);
});

document.getElementById('start-game-btn').addEventListener('click', async () => {
    try {
        await apiCall(`/api/games/${gameState.code}/start`, 'POST', {
            player_id: gameState.playerId,
        });
    } catch (error) {
        showError(error.message);
    }
});

function updateLobby(game) {
    const playersContainer = document.getElementById('lobby-players');
    playersContainer.innerHTML = '';
    
    game.players.forEach(player => {
        const isHost = player.id === game.host_id;
        const div = document.createElement('div');
        div.className = `player-item${isHost ? ' host' : ''}`;
        div.innerHTML = `
            <div class="player-avatar">${player.name.charAt(0).toUpperCase()}</div>
            <span>${player.name}${player.id === gameState.playerId ? ' (you)' : ''}</span>
        `;
        playersContainer.appendChild(div);
    });
    
    document.getElementById('player-count').textContent = game.players.length;
    
    // Update host status and start button
    gameState.isHost = game.host_id === gameState.playerId;
    const startBtn = document.getElementById('start-game-btn');
    startBtn.disabled = !gameState.isHost || game.players.length < 3;
    startBtn.textContent = gameState.isHost ? 'Start Game' : 'Waiting for host...';
}

// Screen: Game
function showGame(game) {
    showScreen('game');
    updateGame(game);
}

function updateGame(game) {
    // Update your secret word
    const myPlayer = game.players.find(p => p.id === gameState.playerId);
    if (myPlayer) {
        document.getElementById('your-secret-word').textContent = myPlayer.secret_word || '???';
        
        // Show/hide change word option
        const changeWordContainer = document.getElementById('change-word-container');
        if (myPlayer.can_change_word) {
            changeWordContainer.classList.remove('hidden');
        } else {
            changeWordContainer.classList.add('hidden');
        }
    }
    
    // Update players grid
    updatePlayersGrid(game);
    
    // Update turn indicator
    updateTurnIndicator(game);
    
    // Update guess form
    const isMyTurn = game.current_player_id === gameState.playerId && myPlayer?.is_alive;
    const guessInput = document.getElementById('guess-input');
    const guessForm = document.getElementById('guess-form');
    guessInput.disabled = !isMyTurn;
    guessForm.querySelector('button').disabled = !isMyTurn;
    
    // Update history
    updateHistory(game);
}

function updatePlayersGrid(game) {
    const grid = document.getElementById('players-grid');
    grid.innerHTML = '';
    
    // Get latest similarities from history
    const latestSimilarities = {};
    if (game.history.length > 0) {
        const latest = game.history[game.history.length - 1];
        Object.assign(latestSimilarities, latest.similarities);
    }
    
    game.players.forEach(player => {
        const isCurrentTurn = player.id === game.current_player_id;
        const isYou = player.id === gameState.playerId;
        
        const div = document.createElement('div');
        div.className = `player-card${isCurrentTurn ? ' current-turn' : ''}${!player.is_alive ? ' eliminated' : ''}${isYou ? ' is-you' : ''}`;
        
        let similarityHtml = '';
        if (latestSimilarities[player.id] !== undefined) {
            const sim = latestSimilarities[player.id];
            const simClass = getSimilarityClass(sim);
            similarityHtml = `<div class="similarity ${simClass}">${(sim * 100).toFixed(0)}%</div>`;
        }
        
        div.innerHTML = `
            <div class="name">${player.name}${isYou ? ' (you)' : ''}</div>
            <div class="status ${player.is_alive ? 'alive' : 'eliminated'}">
                ${player.is_alive ? 'Alive' : 'Eliminated'}
            </div>
            ${similarityHtml}
        `;
        grid.appendChild(div);
    });
}

function getSimilarityClass(sim) {
    if (sim >= 0.95) return 'danger';
    if (sim >= 0.7) return 'high';
    if (sim >= 0.4) return 'medium';
    return 'low';
}

function updateTurnIndicator(game) {
    const indicator = document.getElementById('turn-indicator');
    const turnText = document.getElementById('turn-text');
    
    if (game.status === 'finished') {
        indicator.classList.remove('your-turn');
        turnText.textContent = 'Game Over!';
        return;
    }
    
    const currentPlayer = game.players.find(p => p.id === game.current_player_id);
    const isMyTurn = game.current_player_id === gameState.playerId;
    
    if (isMyTurn) {
        indicator.classList.add('your-turn');
        turnText.textContent = "It's your turn! Make a guess.";
    } else {
        indicator.classList.remove('your-turn');
        turnText.textContent = `Waiting for ${currentPlayer?.name || '...'} to guess...`;
    }
}

function updateHistory(game) {
    const historyLog = document.getElementById('history-log');
    historyLog.innerHTML = '';
    
    // Show history in reverse order (newest first)
    [...game.history].reverse().forEach(entry => {
        const div = document.createElement('div');
        div.className = 'history-entry';
        
        let simsHtml = '';
        game.players.forEach(player => {
            const sim = entry.similarities[player.id];
            if (sim !== undefined) {
                const simClass = getSimilarityClass(sim);
                simsHtml += `
                    <div class="sim-badge">
                        <span>${player.name}</span>
                        <span class="score ${simClass}">${(sim * 100).toFixed(0)}%</span>
                    </div>
                `;
            }
        });
        
        let eliminationHtml = '';
        if (entry.eliminations.length > 0) {
            const eliminatedNames = entry.eliminations.map(id => {
                const p = game.players.find(pl => pl.id === id);
                return p ? p.name : 'Unknown';
            });
            eliminationHtml = `<div class="elimination">Eliminated: ${eliminatedNames.join(', ')}</div>`;
        }
        
        div.innerHTML = `
            <div class="header">
                <span class="guesser">${entry.guesser_name}</span>
                <span class="word">"${entry.word}"</span>
            </div>
            <div class="similarities">${simsHtml}</div>
            ${eliminationHtml}
        `;
        historyLog.appendChild(div);
    });
}

// Guess form
document.getElementById('guess-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const guessInput = document.getElementById('guess-input');
    const word = guessInput.value.trim();
    
    if (!word) return;
    
    try {
        await apiCall(`/api/games/${gameState.code}/guess`, 'POST', {
            player_id: gameState.playerId,
            word,
        });
        guessInput.value = '';
    } catch (error) {
        showError(error.message);
    }
});

// Change word
document.getElementById('change-word-btn').addEventListener('click', async () => {
    const newWord = document.getElementById('new-word-input').value.trim();
    
    if (!newWord) {
        showError('Please enter a new word');
        return;
    }
    
    try {
        await apiCall(`/api/games/${gameState.code}/change-word`, 'POST', {
            player_id: gameState.playerId,
            new_word: newWord,
        });
        document.getElementById('new-word-input').value = '';
    } catch (error) {
        showError(error.message);
    }
});

// Screen: Game Over
function showGameOver(game) {
    showScreen('gameover');
    
    const winner = game.players.find(p => p.id === game.winner);
    const isWinner = game.winner === gameState.playerId;
    
    document.getElementById('gameover-title').textContent = isWinner ? 'You Won!' : 'Game Over!';
    document.getElementById('gameover-message').textContent = winner 
        ? `${winner.name} is the last one standing!`
        : 'The game has ended.';
    
    // Note: We can't show all secret words since the API hides them
    // This would require a special endpoint or storing them client-side
    const revealedWords = document.getElementById('revealed-words');
    revealedWords.innerHTML = '<p style="color: var(--text-muted);">Secret words are hidden for privacy.</p>';
}

document.getElementById('play-again-btn').addEventListener('click', () => {
    stopPolling();
    gameState = {
        code: null,
        playerId: null,
        playerName: null,
        isHost: false,
        pollingInterval: null,
    };
    showScreen('home');
});

// Polling
function startPolling() {
    if (gameState.pollingInterval) {
        clearInterval(gameState.pollingInterval);
    }
    
    pollGameState();
    gameState.pollingInterval = setInterval(pollGameState, 2000);
}

function stopPolling() {
    if (gameState.pollingInterval) {
        clearInterval(gameState.pollingInterval);
        gameState.pollingInterval = null;
    }
}

async function pollGameState() {
    if (!gameState.code || !gameState.playerId) return;
    
    try {
        const game = await apiCall(`/api/games/${gameState.code}?player_id=${gameState.playerId}`);
        
        if (game.status === 'waiting') {
            updateLobby(game);
        } else if (game.status === 'playing') {
            if (screens.lobby.classList.contains('active')) {
                showGame(game);
            } else {
                updateGame(game);
            }
        } else if (game.status === 'finished') {
            stopPolling();
            showGameOver(game);
        }
    } catch (error) {
        console.error('Polling error:', error);
        // Don't show error for polling failures
    }
}

// Initialize
showScreen('home');

