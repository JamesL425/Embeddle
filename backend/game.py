"""Game state models and storage for Bagofwordsdle."""

import secrets
import string
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


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
        """Return player info, hiding secret word from other players."""
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
    similarities: dict[str, float]  # player_id -> similarity
    eliminations: list[str]  # player_ids eliminated by this guess

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
        """Get a player by ID."""
        for player in self.players:
            if player.id == player_id:
                return player
        return None

    def get_current_player(self) -> Optional[Player]:
        """Get the player whose turn it is."""
        if not self.players or self.status != GameStatus.PLAYING:
            return None
        return self.players[self.current_turn]

    def get_alive_players(self) -> list[Player]:
        """Get all players who are still alive."""
        return [p for p in self.players if p.is_alive]

    def advance_turn(self) -> None:
        """Move to the next alive player's turn."""
        if self.status != GameStatus.PLAYING:
            return

        alive_players = self.get_alive_players()
        if len(alive_players) <= 1:
            self.status = GameStatus.FINISHED
            if alive_players:
                self.winner = alive_players[0].id
            return

        # Find next alive player
        num_players = len(self.players)
        next_turn = (self.current_turn + 1) % num_players
        while not self.players[next_turn].is_alive:
            next_turn = (next_turn + 1) % num_players
        self.current_turn = next_turn

    def to_dict(self, viewer_id: str) -> dict:
        """Convert game to dict, with viewer-specific visibility."""
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


def generate_game_code() -> str:
    """Generate a 6-character alphanumeric game code."""
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(6))


def generate_player_id() -> str:
    """Generate a unique player ID."""
    return secrets.token_hex(8)


# In-memory game storage
games: dict[str, Game] = {}


def create_game() -> Game:
    """Create a new game and return it."""
    code = generate_game_code()
    while code in games:
        code = generate_game_code()
    
    game = Game(code=code, host_id="")
    games[code] = game
    return game


def get_game(code: str) -> Optional[Game]:
    """Get a game by code."""
    return games.get(code.upper())


def delete_game(code: str) -> None:
    """Delete a game."""
    games.pop(code.upper(), None)

