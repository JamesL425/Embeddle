"""FastAPI application for Bagofwordsdle game."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from game import (
    Game, 
    GameStatus, 
    Player, 
    GuessResult,
    create_game, 
    get_game, 
    generate_player_id,
)
from embeddings import get_embedding, calculate_similarities, is_valid_word, EmbeddingError

app = FastAPI(title="Bagofwordsdle API")

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constants
ELIMINATION_THRESHOLD = 0.95
MIN_PLAYERS = 3
MAX_PLAYERS = 4


# Request/Response models
class CreateGameResponse(BaseModel):
    code: str
    player_id: str


class JoinGameRequest(BaseModel):
    name: str
    secret_word: str


class JoinGameResponse(BaseModel):
    player_id: str


class GuessRequest(BaseModel):
    player_id: str
    word: str


class ChangeWordRequest(BaseModel):
    player_id: str
    new_word: str


class StartGameRequest(BaseModel):
    player_id: str


class GameStateRequest(BaseModel):
    player_id: str


# API Endpoints

@app.post("/games", response_model=CreateGameResponse)
async def create_new_game():
    """Create a new game lobby."""
    game = create_game()
    return CreateGameResponse(code=game.code, player_id="")


@app.post("/games/{code}/join", response_model=JoinGameResponse)
async def join_game(code: str, request: JoinGameRequest):
    """Join a game with a name and secret word."""
    game = get_game(code)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    if game.status != GameStatus.WAITING:
        raise HTTPException(status_code=400, detail="Game has already started")
    
    if len(game.players) >= MAX_PLAYERS:
        raise HTTPException(status_code=400, detail="Game is full")
    
    # Check for duplicate names
    if any(p.name.lower() == request.name.lower() for p in game.players):
        raise HTTPException(status_code=400, detail="Name already taken")
    
    # Validate the secret word is a real word
    if not is_valid_word(request.secret_word):
        raise HTTPException(
            status_code=400, 
            detail="Please enter a valid English word (letters only, no spaces)"
        )
    
    # Create player with embedding
    player_id = generate_player_id()
    try:
        embedding = get_embedding(request.secret_word)
    except EmbeddingError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process word: {str(e)}")
    
    player = Player(
        id=player_id,
        name=request.name,
        secret_word=request.secret_word.lower().strip(),
        secret_embedding=embedding,
    )
    
    game.players.append(player)
    
    # First player becomes host
    if len(game.players) == 1:
        game.host_id = player_id
    
    return JoinGameResponse(player_id=player_id)


@app.post("/games/{code}/start")
async def start_game(code: str, request: StartGameRequest):
    """Start the game (host only)."""
    game = get_game(code)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    if game.host_id != request.player_id:
        raise HTTPException(status_code=403, detail="Only the host can start the game")
    
    if game.status != GameStatus.WAITING:
        raise HTTPException(status_code=400, detail="Game has already started")
    
    if len(game.players) < MIN_PLAYERS:
        raise HTTPException(
            status_code=400, 
            detail=f"Need at least {MIN_PLAYERS} players to start"
        )
    
    game.status = GameStatus.PLAYING
    game.current_turn = 0
    
    return {"status": "started"}


@app.get("/games/{code}")
async def get_game_state(code: str, player_id: str):
    """Get the current game state."""
    game = get_game(code)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    # Verify player is in the game
    player = game.get_player(player_id)
    if not player:
        raise HTTPException(status_code=403, detail="You are not in this game")
    
    return game.to_dict(player_id)


@app.post("/games/{code}/guess")
async def make_guess(code: str, request: GuessRequest):
    """Submit a guess word."""
    game = get_game(code)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    if game.status != GameStatus.PLAYING:
        raise HTTPException(status_code=400, detail="Game is not in progress")
    
    player = game.get_player(request.player_id)
    if not player:
        raise HTTPException(status_code=403, detail="You are not in this game")
    
    if not player.is_alive:
        raise HTTPException(status_code=400, detail="You have been eliminated")
    
    current_player = game.get_current_player()
    if not current_player or current_player.id != request.player_id:
        raise HTTPException(status_code=400, detail="It's not your turn")
    
    # Validate the guess is a real word
    if not is_valid_word(request.word):
        raise HTTPException(
            status_code=400, 
            detail="Please enter a valid English word (letters only, no spaces)"
        )
    
    # Calculate similarities for all players
    players_data = [(p.id, p.secret_embedding) for p in game.players]
    try:
        similarities = calculate_similarities(request.word, players_data)
    except EmbeddingError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process guess: {str(e)}")
    
    # Check for eliminations (only for OTHER players, can't eliminate yourself)
    eliminations = []
    for p in game.players:
        if p.id != request.player_id and p.is_alive:
            if similarities.get(p.id, 0) >= ELIMINATION_THRESHOLD:
                p.is_alive = False
                eliminations.append(p.id)
    
    # If player eliminated someone, they can change their word
    if eliminations:
        player.can_change_word = True
    
    # Record the guess
    guess_result = GuessResult(
        guesser_id=player.id,
        guesser_name=player.name,
        word=request.word.lower().strip(),
        similarities=similarities,
        eliminations=eliminations,
    )
    game.history.append(guess_result)
    
    # Advance to next turn
    game.advance_turn()
    
    return {
        "similarities": similarities,
        "eliminations": eliminations,
        "game_over": game.status == GameStatus.FINISHED,
        "winner": game.winner,
    }


@app.post("/games/{code}/change-word")
async def change_word(code: str, request: ChangeWordRequest):
    """Change your secret word (if you have the reward)."""
    game = get_game(code)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    if game.status != GameStatus.PLAYING:
        raise HTTPException(status_code=400, detail="Game is not in progress")
    
    player = game.get_player(request.player_id)
    if not player:
        raise HTTPException(status_code=403, detail="You are not in this game")
    
    if not player.can_change_word:
        raise HTTPException(
            status_code=400, 
            detail="You don't have a word change available"
        )
    
    # Validate the new word is a real word
    if not is_valid_word(request.new_word):
        raise HTTPException(
            status_code=400, 
            detail="Please enter a valid English word (letters only, no spaces)"
        )
    
    # Update the word and embedding
    try:
        embedding = get_embedding(request.new_word)
    except EmbeddingError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process word: {str(e)}")
    
    player.secret_word = request.new_word.lower().strip()
    player.secret_embedding = embedding
    player.can_change_word = False
    
    return {"status": "word_changed"}


# Serve static files (frontend)
import os
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

