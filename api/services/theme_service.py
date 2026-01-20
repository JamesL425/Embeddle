"""
Theme Service
Theme management, loading, and word pool generation

This module handles:
- Loading themes from JSON files
- Theme validation and aliases
- Word pool generation for players
- Theme voting and selection
"""

import json
import random
from pathlib import Path
from typing import Optional, List, Dict, Any, Set


# ============== CONFIGURATION ==============

# Theme file paths
_THEMES_DIR = Path(__file__).parent.parent / "themes"
_REGISTRY_PATH = _THEMES_DIR / "theme_registry.json"
_LEGACY_THEMES_PATH = Path(__file__).parent.parent / "themes.json"

# Cached themes
_PREGENERATED_THEMES: Optional[Dict[str, List[str]]] = None
_THEME_CATEGORIES: Optional[List[str]] = None

# Backwards-compatible theme aliases for old game states
THEME_ALIASES: Dict[str, str] = {}


# ============== THEME LOADING ==============

def load_themes() -> Dict[str, List[str]]:
    """
    Load all themes from api/themes/ directory.
    
    Returns:
        Dict mapping theme names to lists of words
    """
    global _PREGENERATED_THEMES
    
    if _PREGENERATED_THEMES is not None:
        return _PREGENERATED_THEMES
    
    themes = {}
    
    # Load from registry if it exists
    if _REGISTRY_PATH.exists():
        try:
            with open(_REGISTRY_PATH) as f:
                registry = json.load(f)
            for entry in registry.get("themes", []):
                theme_file = _THEMES_DIR / entry.get("file", "")
                if theme_file.exists():
                    try:
                        with open(theme_file) as f:
                            theme_data = json.load(f)
                        theme_name = theme_data.get("name", entry.get("name", ""))
                        if theme_name and theme_data.get("words"):
                            themes[theme_name] = theme_data["words"]
                    except Exception as e:
                        print(f"[THEME] Error loading theme file {theme_file}: {e}")
        except Exception as e:
            print(f"[THEME] Error loading theme registry: {e}")
    
    # Fallback: load from legacy themes.json if themes/ directory is empty
    if not themes and _LEGACY_THEMES_PATH.exists():
        try:
            with open(_LEGACY_THEMES_PATH) as f:
                themes = json.load(f)
        except Exception as e:
            print(f"[THEME] Error loading legacy themes.json: {e}")
    
    _PREGENERATED_THEMES = themes
    return themes


def get_theme_categories() -> List[str]:
    """
    Get list of available theme category names.
    
    Returns:
        List of theme names
    """
    global _THEME_CATEGORIES
    
    if _THEME_CATEGORIES is not None:
        return _THEME_CATEGORIES
    
    themes = load_themes()
    _THEME_CATEGORIES = list(themes.keys())
    return _THEME_CATEGORIES


def get_theme_words(theme_name: str) -> List[str]:
    """
    Get words for a specific theme.
    
    Args:
        theme_name: Name of the theme
        
    Returns:
        List of words in the theme, or empty list if not found
    """
    themes = load_themes()
    
    # Check for exact match
    if theme_name in themes:
        return themes[theme_name]
    
    # Check aliases
    aliased_name = THEME_ALIASES.get(theme_name)
    if aliased_name and aliased_name in themes:
        return themes[aliased_name]
    
    return []


def validate_theme_name(theme_name: str) -> bool:
    """
    Check if a theme name is valid.
    
    Args:
        theme_name: Name to validate
        
    Returns:
        True if theme exists (directly or via alias)
    """
    themes = load_themes()
    return theme_name in themes or THEME_ALIASES.get(theme_name) in themes


# ============== THEME SELECTION ==============

def select_random_theme_options(count: int = 3) -> List[str]:
    """
    Select random theme options for voting.
    
    Args:
        count: Number of themes to select
        
    Returns:
        List of randomly selected theme names
    """
    categories = get_theme_categories()
    if not categories:
        return []
    
    return random.sample(categories, min(count, len(categories)))


def resolve_theme_votes(theme_votes: Dict[str, List[str]]) -> Optional[str]:
    """
    Resolve theme votes to determine the winning theme.
    
    Args:
        theme_votes: Dict mapping theme names to lists of voter IDs
        
    Returns:
        Name of winning theme, or None if no votes
    """
    if not theme_votes:
        return None
    
    # Count votes
    vote_counts = {theme: len(voters) for theme, voters in theme_votes.items()}
    
    if not vote_counts:
        return None
    
    # Find max votes
    max_votes = max(vote_counts.values())
    
    # Get all themes with max votes (for tie-breaking)
    top_themes = [theme for theme, count in vote_counts.items() if count == max_votes]
    
    # Random tie-breaker
    return random.choice(top_themes)


# ============== WORD POOL GENERATION ==============

def generate_word_pool(
    theme_words: List[str],
    pool_size: int = 16,
    exclude_words: Optional[Set[str]] = None
) -> List[str]:
    """
    Generate a word pool for a player from theme words.
    
    Args:
        theme_words: Full list of theme words
        pool_size: Number of words to include in pool
        exclude_words: Set of words to exclude (e.g., already assigned to other players)
        
    Returns:
        List of randomly selected words
    """
    if not theme_words:
        return []
    
    # Filter out excluded words
    available_words = theme_words
    if exclude_words:
        available_words = [w for w in theme_words if w.lower() not in exclude_words]
    
    # Sample from available words
    if len(available_words) <= pool_size:
        return available_words.copy()
    
    return random.sample(available_words, pool_size)


def generate_non_overlapping_pools(
    theme_words: List[str],
    num_players: int,
    pool_size: int = 16
) -> List[List[str]]:
    """
    Generate non-overlapping word pools for multiple players.
    
    This ensures each player gets a unique set of words with no overlap,
    which is important for fair gameplay.
    
    Args:
        theme_words: Full list of theme words
        num_players: Number of players needing pools
        pool_size: Size of each pool
        
    Returns:
        List of word pools (one per player)
    """
    if not theme_words:
        return [[] for _ in range(num_players)]
    
    total_needed = num_players * pool_size
    
    # If we don't have enough words for non-overlapping pools,
    # fall back to random sampling with potential overlap
    if len(theme_words) < total_needed:
        return [random.sample(theme_words, min(pool_size, len(theme_words))) 
                for _ in range(num_players)]
    
    # Shuffle all words and distribute
    shuffled = theme_words.copy()
    random.shuffle(shuffled)
    
    pools = []
    for i in range(num_players):
        start_idx = i * pool_size
        end_idx = start_idx + pool_size
        pools.append(shuffled[start_idx:end_idx])
    
    return pools


def generate_word_change_options(
    theme_words: List[str],
    current_word: str,
    guessed_words: Set[str],
    count: int = 16
) -> List[str]:
    """
    Generate word change options after a player eliminates someone.
    
    Args:
        theme_words: Full list of theme words
        current_word: Player's current secret word (excluded from options)
        guessed_words: Set of words that have been guessed (excluded)
        count: Number of options to provide
        
    Returns:
        List of word options for changing
    """
    if not theme_words:
        return []
    
    # Exclude current word and guessed words
    excluded = guessed_words.copy()
    excluded.add(current_word.lower())
    
    available = [w for w in theme_words if w.lower() not in excluded]
    
    if len(available) <= count:
        return available
    
    return random.sample(available, count)


# ============== THEME DATA HELPERS ==============

def build_theme_data(theme_name: str) -> Dict[str, Any]:
    """
    Build theme data dict for game state.
    
    Args:
        theme_name: Name of the theme
        
    Returns:
        Dict with theme name and words
    """
    words = get_theme_words(theme_name)
    return {
        "name": theme_name,
        "words": words,
    }


def get_theme_word_count(theme_name: str) -> int:
    """
    Get the number of words in a theme.
    
    Args:
        theme_name: Name of the theme
        
    Returns:
        Number of words, or 0 if theme not found
    """
    words = get_theme_words(theme_name)
    return len(words)


def reload_themes() -> None:
    """
    Force reload of themes from disk.
    
    Useful for development/testing.
    """
    global _PREGENERATED_THEMES, _THEME_CATEGORIES
    _PREGENERATED_THEMES = None
    _THEME_CATEGORIES = None
    load_themes()

