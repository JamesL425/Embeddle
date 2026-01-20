"""
Ranked Service
ELO/MMR calculations and ranked game management

This module handles:
- MMR calculations using ELO-style rating system
- Placement games and provisional period
- K-factor decay over time
- Tier/rank determination
- Leaderboard updates
"""

import math
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass


# ============== CONFIGURATION ==============

# Default configuration values (can be overridden by config.json)
DEFAULT_CONFIG = {
    "initial_mmr": 1000,
    "k_factor": 32,
    "placement_k_factor": 64,
    "placement_games": 5,
    "provisional_games": 15,
    "provisional_k_factor": 48,
    "k_factor_min": 20,
    "k_factor_decay_rate": 0.3,
    "participation_bonus": 2,
    "tier_thresholds": {
        "bronze": 800,
        "silver": 1000,
        "gold": 1200,
        "platinum": 1400,
        "diamond": 1700,
        "master": 2000,
    },
}

# Loaded configuration (set by init_ranked_config)
_config: Dict[str, Any] = DEFAULT_CONFIG.copy()


def init_ranked_config(config: Dict[str, Any]) -> None:
    """
    Initialize ranked configuration from config.json.
    
    Args:
        config: The 'ranked' section from config.json
    """
    global _config
    if config:
        _config = {**DEFAULT_CONFIG, **config}


def get_config() -> Dict[str, Any]:
    """Get current ranked configuration."""
    return _config.copy()


# ============== DATA CLASSES ==============

@dataclass
class RankedPlayer:
    """Represents a player in a ranked game."""
    player_id: str
    user_id: str  # Auth user ID
    mmr: int
    ranked_games: int
    is_alive: bool = True
    placement: int = 0  # Final placement (1 = winner)


@dataclass
class MMRResult:
    """Result of MMR calculation for a player."""
    old_mmr: int
    new_mmr: int
    delta: int
    k_factor: float


# ============== ELO CALCULATIONS ==============

def calculate_expected_score(player_mmr: int, opponent_mmr: int) -> float:
    """
    Calculate expected score using ELO formula.
    
    Args:
        player_mmr: Player's current MMR
        opponent_mmr: Opponent's current MMR
        
    Returns:
        Expected score between 0 and 1
    """
    return 1.0 / (1.0 + math.pow(10, (opponent_mmr - player_mmr) / 400.0))


def get_k_factor(ranked_games: int) -> float:
    """
    Get K-factor based on number of ranked games played.
    
    Higher K-factor during placement/provisional period allows
    faster rating adjustment for new players.
    
    Args:
        ranked_games: Number of ranked games player has completed
        
    Returns:
        K-factor to use for MMR calculation
    """
    placement_games = _config["placement_games"]
    provisional_games = _config["provisional_games"]
    
    if ranked_games < placement_games:
        # Placement period - highest K-factor
        return _config["placement_k_factor"]
    elif ranked_games < provisional_games:
        # Provisional period - elevated K-factor
        return _config["provisional_k_factor"]
    else:
        # Standard play - K-factor decays over time
        games_after_provisional = ranked_games - provisional_games
        decay = _config["k_factor_decay_rate"] * games_after_provisional
        k = _config["k_factor"] - decay
        return max(_config["k_factor_min"], k)


def calculate_mmr_change(
    player_mmr: int,
    opponent_mmr: int,
    actual_score: float,
    k_factor: float
) -> int:
    """
    Calculate MMR change for a single matchup.
    
    Args:
        player_mmr: Player's current MMR
        opponent_mmr: Opponent's current MMR
        actual_score: Actual result (1 = win, 0 = loss, 0.5 = draw)
        k_factor: K-factor to use
        
    Returns:
        MMR change (positive or negative)
    """
    expected = calculate_expected_score(player_mmr, opponent_mmr)
    return round(k_factor * (actual_score - expected))


# ============== MULTIPLAYER MMR ==============

def calculate_multiplayer_mmr(
    players: List[RankedPlayer],
    placements: Dict[str, int]  # player_id -> placement (1 = winner)
) -> Dict[str, MMRResult]:
    """
    Calculate MMR changes for a multiplayer game.
    
    Uses pairwise ELO calculations where each player is compared
    against every other player based on their relative placement.
    
    Args:
        players: List of RankedPlayer objects
        placements: Dict mapping player_id to final placement
        
    Returns:
        Dict mapping player_id to MMRResult
    """
    results: Dict[str, MMRResult] = {}
    
    for player in players:
        if player.player_id not in placements:
            continue
            
        player_placement = placements[player.player_id]
        k_factor = get_k_factor(player.ranked_games)
        
        total_delta = 0
        
        # Compare against each other player
        for opponent in players:
            if opponent.player_id == player.player_id:
                continue
            if opponent.player_id not in placements:
                continue
                
            opponent_placement = placements[opponent.player_id]
            
            # Determine actual score based on relative placement
            if player_placement < opponent_placement:
                actual_score = 1.0  # Player beat opponent
            elif player_placement > opponent_placement:
                actual_score = 0.0  # Player lost to opponent
            else:
                actual_score = 0.5  # Tie (shouldn't happen in this game)
            
            delta = calculate_mmr_change(
                player.mmr,
                opponent.mmr,
                actual_score,
                k_factor / (len(players) - 1)  # Divide K by number of matchups
            )
            total_delta += delta
        
        # Add participation bonus (makes system slightly positive-sum)
        participation_bonus = int(_config["participation_bonus"])
        total_delta += participation_bonus
        
        new_mmr = max(0, player.mmr + total_delta)
        
        results[player.player_id] = MMRResult(
            old_mmr=player.mmr,
            new_mmr=new_mmr,
            delta=total_delta,
            k_factor=k_factor,
        )
    
    return results


def calculate_elimination_order_placements(
    players: List[Dict[str, Any]],
    elimination_order: List[str]
) -> Dict[str, int]:
    """
    Calculate placements based on elimination order.
    
    Players eliminated first get the worst placement.
    The last player standing (winner) gets placement 1.
    
    Args:
        players: List of player dicts
        elimination_order: List of player IDs in order of elimination
        
    Returns:
        Dict mapping player_id to placement (1 = winner)
    """
    num_players = len(players)
    placements = {}
    
    # Eliminated players get placement based on when they were eliminated
    for i, player_id in enumerate(elimination_order):
        # First eliminated = worst placement (num_players)
        # Second eliminated = num_players - 1, etc.
        placements[player_id] = num_players - i
    
    # Winner (not in elimination order) gets placement 1
    for player in players:
        if player["id"] not in placements:
            placements[player["id"]] = 1
    
    return placements


# ============== TIER/RANK SYSTEM ==============

def get_tier(mmr: int) -> str:
    """
    Get tier name for an MMR value.
    
    Args:
        mmr: Player's MMR
        
    Returns:
        Tier name (e.g., "gold", "platinum")
    """
    thresholds = _config["tier_thresholds"]
    
    # Sort thresholds by value descending
    sorted_tiers = sorted(thresholds.items(), key=lambda x: x[1], reverse=True)
    
    for tier_name, threshold in sorted_tiers:
        if mmr >= threshold:
            return tier_name
    
    return "unranked"


def get_tier_info(mmr: int) -> Dict[str, Any]:
    """
    Get detailed tier information for an MMR value.
    
    Args:
        mmr: Player's MMR
        
    Returns:
        Dict with tier name, progress to next tier, etc.
    """
    thresholds = _config["tier_thresholds"]
    current_tier = get_tier(mmr)
    
    # Find current and next tier thresholds
    sorted_tiers = sorted(thresholds.items(), key=lambda x: x[1])
    
    current_threshold = 0
    next_tier = None
    next_threshold = None
    
    for i, (tier_name, threshold) in enumerate(sorted_tiers):
        if tier_name == current_tier:
            current_threshold = threshold
            if i + 1 < len(sorted_tiers):
                next_tier, next_threshold = sorted_tiers[i + 1]
            break
    
    # Calculate progress to next tier
    progress = 0.0
    if next_threshold is not None:
        range_size = next_threshold - current_threshold
        if range_size > 0:
            progress = (mmr - current_threshold) / range_size
            progress = max(0.0, min(1.0, progress))
    
    return {
        "tier": current_tier,
        "mmr": mmr,
        "threshold": current_threshold,
        "next_tier": next_tier,
        "next_threshold": next_threshold,
        "progress": progress,
    }


def is_placement_complete(ranked_games: int) -> bool:
    """
    Check if player has completed placement games.
    
    Args:
        ranked_games: Number of ranked games completed
        
    Returns:
        True if placement is complete
    """
    return ranked_games >= _config["placement_games"]


def is_provisional(ranked_games: int) -> bool:
    """
    Check if player is still in provisional period.
    
    Args:
        ranked_games: Number of ranked games completed
        
    Returns:
        True if still provisional
    """
    return ranked_games < _config["provisional_games"]


# ============== LEADERBOARD HELPERS ==============

def format_leaderboard_entry(
    name: str,
    mmr: int,
    ranked_games: int,
    ranked_wins: int,
    peak_mmr: Optional[int] = None
) -> Dict[str, Any]:
    """
    Format a leaderboard entry with tier info.
    
    Args:
        name: Player display name
        mmr: Current MMR
        ranked_games: Total ranked games
        ranked_wins: Total ranked wins
        peak_mmr: Peak MMR achieved
        
    Returns:
        Formatted leaderboard entry dict
    """
    tier_info = get_tier_info(mmr)
    
    return {
        "name": name,
        "mmr": mmr,
        "peak_mmr": peak_mmr or mmr,
        "tier": tier_info["tier"],
        "ranked_games": ranked_games,
        "ranked_wins": ranked_wins,
        "win_rate": round(ranked_wins / max(1, ranked_games) * 100, 1),
        "is_provisional": is_provisional(ranked_games),
        "placement_complete": is_placement_complete(ranked_games),
    }


def calculate_peak_mmr(current_mmr: int, previous_peak: int) -> int:
    """
    Calculate new peak MMR.
    
    Args:
        current_mmr: Current MMR after game
        previous_peak: Previous peak MMR
        
    Returns:
        New peak MMR
    """
    return max(current_mmr, previous_peak)

