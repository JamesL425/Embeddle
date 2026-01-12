"""Vercel serverless function for Bagofwordsdle API."""

import os
import secrets
import string
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
from openai import OpenAI, RateLimitError, APIError
from wordfreq import word_frequency
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from mangum import Mangum

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ============== MODELS ==============

class GameStatus(str, Enum):
    WAITING = "waiting"
    PLAYING = "playing"
    FINISHED = "finished"


@dataclass
class Player:
    id: str
    name: str
    secret_word: str
    secret_embedding: list[float] = field(default_factory=list)
    is_alive: bool = True
    can_change_word: bool = False

    def to_public_dict(self, viewer_id: str) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "secret_word": self.secret_word if self.id == viewer_id else None,
            "is_alive": self.is_alive,
            "can_change_word": self.can_change_word if self.id == viewer_id else None,
        }


@dataclass
class GuessResult:
    guesser_id: str
    guesser_name: str
    word: str
    similarities: dict[str, float]
    eliminations: list[str]

    def to_dict(self) -> dict:
        return {
            "guesser_id": self.guesser_id,
            "guesser_name": self.guesser_name,
            "word": self.word,
            "similarities": self.similarities,
            "eliminations": self.eliminations,
        }


@dataclass
class Game:
    code: str
    host_id: str
    players: list[Player] = field(default_factory=list)
    current_turn: int = 0
    status: GameStatus = GameStatus.WAITING
    winner: Optional[str] = None
    history: list[GuessResult] = field(default_factory=list)

    def get_player(self, player_id: str) -> Optional[Player]:
        for player in self.players:
            if player.id == player_id:
                return player
        return None

    def get_current_player(self) -> Optional[Player]:
        if not self.players or self.status != GameStatus.PLAYING:
            return None
        return self.players[self.current_turn]

    def get_alive_players(self) -> list[Player]:
        return [p for p in self.players if p.is_alive]

    def advance_turn(self) -> None:
        if self.status != GameStatus.PLAYING:
            return
        alive_players = self.get_alive_players()
        if len(alive_players) <= 1:
            self.status = GameStatus.FINISHED
            if alive_players:
                self.winner = alive_players[0].id
            return
        num_players = len(self.players)
        next_turn = (self.current_turn + 1) % num_players
        while not self.players[next_turn].is_alive:
            next_turn = (next_turn + 1) % num_players
        self.current_turn = next_turn

    def to_dict(self, viewer_id: str) -> dict:
        current_player = self.get_current_player()
        return {
            "code": self.code,
            "host_id": self.host_id,
            "players": [p.to_public_dict(viewer_id) for p in self.players],
            "current_turn": self.current_turn,
            "current_player_id": current_player.id if current_player else None,
            "status": self.status.value,
            "winner": self.winner,
            "history": [h.to_dict() for h in self.history],
        }


# ============== STORAGE ==============
# NOTE: This is in-memory and will reset between serverless invocations
# For production, use a database like Vercel KV or Upstash Redis
games: dict[str, Game] = {}


def generate_game_code() -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(6))


def generate_player_id() -> str:
    return secrets.token_hex(8)


def create_game() -> Game:
    code = generate_game_code()
    while code in games:
        code = generate_game_code()
    game = Game(code=code, host_id="")
    games[code] = game
    return game


def get_game(code: str) -> Optional[Game]:
    return games.get(code.upper())


# ============== EMBEDDINGS ==============

embedding_cache: dict[str, list[float]] = {}


class EmbeddingError(Exception):
    pass


def is_valid_word(word: str) -> bool:
    word_lower = word.lower().strip()
    if not word_lower.isalpha():
        return False
    if len(word_lower) < 2:
        return False
    freq = word_frequency(word_lower, 'en')
    return freq > 0


def get_embedding(word: str) -> list[float]:
    word_lower = word.lower().strip()
    if word_lower in embedding_cache:
        return embedding_cache[word_lower]
    try:
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=word_lower,
        )
        embedding = response.data[0].embedding
        embedding_cache[word_lower] = embedding
        return embedding
    except RateLimitError as e:
        raise EmbeddingError("API rate limit exceeded. Please try again in a moment.") from e
    except APIError as e:
        raise EmbeddingError(f"API error: {str(e)}") from e
    except Exception as e:
        raise EmbeddingError(f"Failed to get embedding: {str(e)}") from e


def cosine_similarity(embedding1: list[float], embedding2: list[float]) -> float:
    vec1 = np.array(embedding1)
    vec2 = np.array(embedding2)
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(dot_product / (norm1 * norm2))


def calculate_similarities(guess_word: str, players: list[tuple[str, list[float]]]) -> dict[str, float]:
    guess_embedding = get_embedding(guess_word)
    similarities = {}
    for player_id, secret_embedding in players:
        similarity = cosine_similarity(guess_embedding, secret_embedding)
        similarities[player_id] = round(similarity, 2)
    return similarities


# ============== FASTAPI APP ==============

app = FastAPI(title="Bagofwordsdle API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ELIMINATION_THRESHOLD = 0.95
MIN_PLAYERS = 3
MAX_PLAYERS = 4


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


@app.post("/api/games", response_model=CreateGameResponse)
async def create_new_game():
    game = create_game()
    return CreateGameResponse(code=game.code, player_id="")


@app.post("/api/games/{code}/join", response_model=JoinGameResponse)
async def join_game(code: str, request: JoinGameRequest):
    game = get_game(code)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.status != GameStatus.WAITING:
        raise HTTPException(status_code=400, detail="Game has already started")
    if len(game.players) >= MAX_PLAYERS:
        raise HTTPException(status_code=400, detail="Game is full")
    if any(p.name.lower() == request.name.lower() for p in game.players):
        raise HTTPException(status_code=400, detail="Name already taken")
    if not is_valid_word(request.secret_word):
        raise HTTPException(status_code=400, detail="Please enter a valid English word (letters only, no spaces)")
    
    player_id = generate_player_id()
    try:
        embedding = get_embedding(request.secret_word)
    except EmbeddingError as e:
        raise HTTPException(status_code=503, detail=str(e))
    
    player = Player(
        id=player_id,
        name=request.name,
        secret_word=request.secret_word.lower().strip(),
        secret_embedding=embedding,
    )
    game.players.append(player)
    if len(game.players) == 1:
        game.host_id = player_id
    return JoinGameResponse(player_id=player_id)


@app.post("/api/games/{code}/start")
async def start_game(code: str, request: StartGameRequest):
    game = get_game(code)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.host_id != request.player_id:
        raise HTTPException(status_code=403, detail="Only the host can start the game")
    if game.status != GameStatus.WAITING:
        raise HTTPException(status_code=400, detail="Game has already started")
    if len(game.players) < MIN_PLAYERS:
        raise HTTPException(status_code=400, detail=f"Need at least {MIN_PLAYERS} players to start")
    
    game.status = GameStatus.PLAYING
    game.current_turn = 0
    return {"status": "started"}


@app.get("/api/games/{code}")
async def get_game_state(code: str, player_id: str):
    game = get_game(code)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    player = game.get_player(player_id)
    if not player:
        raise HTTPException(status_code=403, detail="You are not in this game")
    return game.to_dict(player_id)


@app.post("/api/games/{code}/guess")
async def make_guess(code: str, request: GuessRequest):
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
    if not is_valid_word(request.word):
        raise HTTPException(status_code=400, detail="Please enter a valid English word (letters only, no spaces)")
    
    players_data = [(p.id, p.secret_embedding) for p in game.players]
    try:
        similarities = calculate_similarities(request.word, players_data)
    except EmbeddingError as e:
        raise HTTPException(status_code=503, detail=str(e))
    
    eliminations = []
    for p in game.players:
        if p.id != request.player_id and p.is_alive:
            if similarities.get(p.id, 0) >= ELIMINATION_THRESHOLD:
                p.is_alive = False
                eliminations.append(p.id)
    
    if eliminations:
        player.can_change_word = True
    
    guess_result = GuessResult(
        guesser_id=player.id,
        guesser_name=player.name,
        word=request.word.lower().strip(),
        similarities=similarities,
        eliminations=eliminations,
    )
    game.history.append(guess_result)
    game.advance_turn()
    
    return {
        "similarities": similarities,
        "eliminations": eliminations,
        "game_over": game.status == GameStatus.FINISHED,
        "winner": game.winner,
    }


@app.post("/api/games/{code}/change-word")
async def change_word(code: str, request: ChangeWordRequest):
    game = get_game(code)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.status != GameStatus.PLAYING:
        raise HTTPException(status_code=400, detail="Game is not in progress")
    
    player = game.get_player(request.player_id)
    if not player:
        raise HTTPException(status_code=403, detail="You are not in this game")
    if not player.can_change_word:
        raise HTTPException(status_code=400, detail="You don't have a word change available")
    if not is_valid_word(request.new_word):
        raise HTTPException(status_code=400, detail="Please enter a valid English word (letters only, no spaces)")
    
    try:
        embedding = get_embedding(request.new_word)
    except EmbeddingError as e:
        raise HTTPException(status_code=503, detail=str(e))
    
    player.secret_word = request.new_word.lower().strip()
    player.secret_embedding = embedding
    player.can_change_word = False
    return {"status": "word_changed"}


# Vercel handler
handler = Mangum(app, lifespan="off")

