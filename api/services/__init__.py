"""
Services Module
Re-exports all service modules

This module provides centralized access to all business logic services:
- embedding_service: OpenAI embedding calls with caching
- ai_service: AI player logic for singleplayer mode
- economy_service: Credits, quests, and streak management
- game_service: Core game operations
- theme_service: Theme management and word pools
- ranked_service: ELO/MMR calculations
"""

from .embedding_service import (
    get_embedding,
    cosine_similarity,
    batch_get_embeddings,
)

from .ai_service import (
    AI_DIFFICULTY_CONFIG,
    create_ai_player,
    ai_select_secret_word,
    ai_update_memory,
    ai_find_similar_words,
    ai_choose_guess,
    ai_change_word,
)

from .economy_service import (
    get_user_credits,
    add_user_credits,
    check_and_update_streak,
    get_next_streak_info,
    user_owns_cosmetic,
    grant_owned_cosmetic,
    generate_daily_quests,
    generate_weekly_quests,
)

from .game_service import (
    generate_game_code,
    generate_player_id,
    create_game,
    add_player,
    remove_player,
    set_player_word,
    advance_turn,
    eliminate_player,
    check_game_over,
    get_game_for_player,
)

from .theme_service import (
    load_themes,
    get_theme_categories,
    get_theme_words,
    validate_theme_name,
    select_random_theme_options,
    resolve_theme_votes,
    generate_word_pool,
    generate_non_overlapping_pools,
    generate_word_change_options,
    build_theme_data,
    get_theme_word_count,
    reload_themes,
    THEME_ALIASES,
)

from .ranked_service import (
    init_ranked_config,
    get_config as get_ranked_config,
    RankedPlayer,
    MMRResult,
    calculate_expected_score,
    get_k_factor,
    calculate_mmr_change,
    calculate_multiplayer_mmr,
    calculate_elimination_order_placements,
    get_tier,
    get_tier_info,
    is_placement_complete,
    is_provisional,
    format_leaderboard_entry,
    calculate_peak_mmr,
)

__all__ = [
    # Embedding service
    "get_embedding",
    "cosine_similarity",
    "batch_get_embeddings",
    # AI service
    "AI_DIFFICULTY_CONFIG",
    "create_ai_player",
    "ai_select_secret_word",
    "ai_update_memory",
    "ai_find_similar_words",
    "ai_choose_guess",
    "ai_change_word",
    # Economy service
    "get_user_credits",
    "add_user_credits",
    "check_and_update_streak",
    "get_next_streak_info",
    "user_owns_cosmetic",
    "grant_owned_cosmetic",
    "generate_daily_quests",
    "generate_weekly_quests",
    # Game service
    "generate_game_code",
    "generate_player_id",
    "create_game",
    "add_player",
    "remove_player",
    "set_player_word",
    "advance_turn",
    "eliminate_player",
    "check_game_over",
    "get_game_for_player",
    # Theme service
    "load_themes",
    "get_theme_categories",
    "get_theme_words",
    "validate_theme_name",
    "select_random_theme_options",
    "resolve_theme_votes",
    "generate_word_pool",
    "generate_non_overlapping_pools",
    "generate_word_change_options",
    "build_theme_data",
    "get_theme_word_count",
    "reload_themes",
    "THEME_ALIASES",
    # Ranked service
    "init_ranked_config",
    "get_ranked_config",
    "RankedPlayer",
    "MMRResult",
    "calculate_expected_score",
    "get_k_factor",
    "calculate_mmr_change",
    "calculate_multiplayer_mmr",
    "calculate_elimination_order_placements",
    "get_tier",
    "get_tier_info",
    "is_placement_complete",
    "is_provisional",
    "format_leaderboard_entry",
    "calculate_peak_mmr",
]

