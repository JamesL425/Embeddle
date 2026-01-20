"""
Game Service
Core game logic and operations

This module provides the core game mechanics including:
- Game creation and management
- Player management (join, leave, ready)
- Word selection and changes
- Turn management
- Elimination and win conditions
"""

import secrets
import string
import time
from typing import Optional, List, Dict, Any

from ..data import save_game, load_game, delete_game


def generate_game_code() -> str:
    """
    Generate a unique 6-character game code.
    
    Returns:
        Uppercase alphanumeric game code
    """
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))


def generate_player_id() -> str:
    """
    Generate a unique 32-character player ID.
    
    Returns:
        Lowercase hex string (128 bits of entropy)
    """
    return secrets.token_hex(16)


def create_game(
    visibility: str = "private",
    is_ranked: bool = False,
    is_singleplayer: bool = False
) -> Dict[str, Any]:
    """
    Create a new game.
    
    Args:
        visibility: 'public' or 'private'
        is_ranked: Whether this is a ranked game
        is_singleplayer: Whether this is a singleplayer game
        
    Returns:
        Game state dictionary
    """
    code = generate_game_code()
    
    game: Dict[str, Any] = {
        "code": code,
        "status": "lobby",
        "visibility": visibility,
        "is_ranked": is_ranked,
        "is_singleplayer": is_singleplayer,
        "players": [],
        "max_players": 4,
        "min_players": 3,
        "theme": None,
        "theme_options": [],
        "theme_votes": {},
        "history": [],
        "current_turn": 0,
        "current_player_index": 0,
        "current_player_id": None,
        "all_words_set": False,
        "waiting_for_word_change": None,
        "host_id": None,
        "created_at": time.time(),
    }
    
    save_game(code, game)
    return game


def add_player(
    game: Dict[str, Any],
    name: str,
    cosmetics: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Add a player to a game.
    
    Args:
        game: Game state dictionary
        name: Player display name
        cosmetics: Optional cosmetics configuration
        
    Returns:
        New player dictionary
    """
    player_id = generate_player_id()
    
    player: Dict[str, Any] = {
        "id": player_id,
        "name": name,
        "is_ai": False,
        "secret_word": None,
        "secret_embedding": None,
        "is_alive": True,
        "can_change_word": False,
        "word_pool": [],
        "is_ready": False,
        "cosmetics": cosmetics or {},
    }
    
    game["players"].append(player)
    
    # First player is host
    if len(game["players"]) == 1:
        game["host_id"] = player_id
    
    save_game(game["code"], game)
    return player


def remove_player(game: Dict[str, Any], player_id: str) -> bool:
    """
    Remove a player from a game.
    
    Args:
        game: Game state dictionary
        player_id: ID of player to remove
        
    Returns:
        True if player was removed
    """
    game["players"] = [p for p in game["players"] if p["id"] != player_id]
    
    # Update host if needed
    if game["host_id"] == player_id and game["players"]:
        game["host_id"] = game["players"][0]["id"]
    
    save_game(game["code"], game)
    return True


def set_player_word(
    game: Dict[str, Any],
    player_id: str,
    word: str,
    embedding: Optional[List[float]] = None
) -> bool:
    """
    Set a player's secret word.
    
    Args:
        game: Game state dictionary
        player_id: ID of player
        word: Secret word to set
        embedding: Optional embedding vector (legacy support)
        
    Returns:
        True if word was set successfully
    """
    player = next((p for p in game["players"] if p["id"] == player_id), None)
    if not player:
        return False
    
    player["secret_word"] = word
    # NOTE: We no longer store secret_embedding - it's in Redis cache as emb:{word}
    if embedding:
        player["secret_embedding"] = embedding  # Legacy support
    player["is_ready"] = True
    
    # Check if all players have words
    all_set = all(p.get("secret_word") for p in game["players"])
    game["all_words_set"] = all_set
    
    save_game(game["code"], game)
    return True


def advance_turn(game: Dict[str, Any]) -> Optional[str]:
    """
    Advance to the next player's turn.
    
    Skips eliminated players automatically.
    
    Args:
        game: Game state dictionary
        
    Returns:
        ID of the new current player, or None if no alive players
    """
    alive_players = [p for p in game["players"] if p.get("is_alive", True)]
    if not alive_players:
        return None
    
    current_idx = game.get("current_player_index", 0)
    
    # Find next alive player
    for i in range(len(game["players"])):
        next_idx = (current_idx + 1 + i) % len(game["players"])
        next_player = game["players"][next_idx]
        if next_player.get("is_alive", True):
            game["current_player_index"] = next_idx
            game["current_turn"] = next_idx
            game["current_player_id"] = next_player["id"]
            break
    
    save_game(game["code"], game)
    return game["current_player_id"]


def eliminate_player(game: Dict[str, Any], player_id: str) -> bool:
    """
    Eliminate a player from the game.
    
    Args:
        game: Game state dictionary
        player_id: ID of player to eliminate
        
    Returns:
        True if player was eliminated
    """
    player = next((p for p in game["players"] if p["id"] == player_id), None)
    if not player:
        return False
    
    player["is_alive"] = False
    player["can_change_word"] = False
    
    save_game(game["code"], game)
    return True


def check_game_over(game: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Check if the game is over and return winner info.
    
    A game ends when only one player (or fewer) remains alive.
    
    Args:
        game: Game state dictionary
        
    Returns:
        Dict with 'finished' and 'winner' keys if game over, None otherwise
    """
    alive_players = [p for p in game["players"] if p.get("is_alive", True)]
    
    if len(alive_players) <= 1:
        game["status"] = "finished"
        winner = alive_players[0] if alive_players else None
        game["winner_id"] = winner["id"] if winner else None
        game["winner_name"] = winner["name"] if winner else None
        game["winner"] = {
            "id": winner["id"],
            "name": winner["name"],
        } if winner else None
        save_game(game["code"], game)
        return {
            "finished": True,
            "winner": winner,
        }
    
    return None


def get_game_for_player(game: Dict[str, Any], player_id: str) -> Dict[str, Any]:
    """
    Get game state sanitized for a specific player.
    
    Hides other players' secret words and sensitive information.
    
    Args:
        game: Game state dictionary
        player_id: ID of player requesting the state
        
    Returns:
        Sanitized game state dictionary
    """
    is_player = any(p["id"] == player_id for p in game["players"])
    game_finished = game.get("status") == "finished"
    
    # Hide other players' secret words and embeddings
    sanitized_players: List[Dict[str, Any]] = []
    for p in game["players"]:
        player_data: Dict[str, Any] = {
            "id": p["id"],
            "name": p["name"],
            "is_ai": p.get("is_ai", False),
            "is_alive": p.get("is_alive", True),
            "has_word": bool(p.get("secret_word")),
            "cosmetics": p.get("cosmetics", {}),
            "can_change_word": p.get("can_change_word", False),
            "is_ready": p.get("is_ready", False),
        }
        
        # Include own secret word
        if p["id"] == player_id:
            player_data["secret_word"] = p.get("secret_word")
            player_data["word_pool"] = p.get("word_pool", [])
            player_data["word_change_options"] = p.get("word_change_options", [])
        
        # Include revealed words for eliminated players or when game is finished
        if not p.get("is_alive", True) or game_finished:
            player_data["secret_word"] = p.get("secret_word")
        
        sanitized_players.append(player_data)
    
    return {
        "code": game["code"],
        "status": game["status"],
        "players": sanitized_players,
        "theme": game.get("theme"),
        "theme_options": game.get("theme_options", []),
        "theme_votes": game.get("theme_votes", {}),
        "history": game.get("history", []),
        "current_player_id": game.get("current_player_id"),
        "current_turn": game.get("current_turn", 0),
        "all_words_set": game.get("all_words_set", False),
        "waiting_for_word_change": game.get("waiting_for_word_change"),
        "is_host": game.get("host_id") == player_id,
        "host_id": game.get("host_id"),
        "is_ranked": game.get("is_ranked", False),
        "is_singleplayer": game.get("is_singleplayer", False),
        "winner": game.get("winner"),
    }

