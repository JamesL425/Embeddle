#!/usr/bin/env python3
"""
Precompute and cache theme embeddings and similarity matrices.

This script precomputes all embeddings and similarity matrices for all themes,
storing them in Redis for instant lookups during gameplay. This makes bot
decisions much faster since they don't need to compute similarities on-the-fly.

Run this script:
- Once after deploying new themes
- Periodically to refresh cache (embeddings expire after 24h by default)
- On server startup for local development

Usage:
    python api/precompute_embeddings.py [--force]

Options:
    --force    Recompute even if already cached
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from openai import OpenAI
from upstash_redis import Redis

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Load config
CONFIG_PATH = Path(__file__).parent / "config.json"
with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

EMBEDDING_MODEL = CONFIG.get("embedding", {}).get("model", "text-embedding-3-large")
EMBEDDING_CACHE_SECONDS = CONFIG.get("embedding", {}).get("cache_expiry_seconds", 86400)
# Similarity matrices can be cached longer since themes are static
SIMILARITY_MATRIX_CACHE_SECONDS = 86400 * 7  # 7 days


def get_redis():
    """Get Redis client."""
    url = os.getenv("UPSTASH_REDIS_REST_URL")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        raise RuntimeError("UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN required")
    return Redis(url=url, token=token)


def get_openai_client():
    """Get OpenAI client."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY required")
    return OpenAI(api_key=api_key)


def load_themes() -> dict:
    """Load all themes from api/themes/ directory."""
    themes_dir = Path(__file__).parent / "themes"
    registry_path = themes_dir / "theme_registry.json"
    
    themes = {}
    
    if registry_path.exists():
        with open(registry_path) as f:
            registry = json.load(f)
        for entry in registry.get("themes", []):
            theme_file = themes_dir / entry.get("file", "")
            if theme_file.exists():
                with open(theme_file) as f:
                    theme_data = json.load(f)
                theme_name = theme_data.get("name", entry.get("name", ""))
                if theme_name and theme_data.get("words"):
                    themes[theme_name] = theme_data["words"]
    
    return themes


def batch_get_embeddings(client: OpenAI, words: list, batch_size: int = 100) -> dict:
    """Get embeddings for multiple words in batches."""
    result = {}
    words_lower = [w.lower().strip() for w in words]
    
    for i in range(0, len(words_lower), batch_size):
        batch = words_lower[i:i + batch_size]
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
        )
        for j, embedding_data in enumerate(response.data):
            result[batch[j]] = embedding_data.embedding
    
    return result


def compute_similarity_matrix(embeddings: dict) -> dict:
    """
    Compute similarity matrix for all words using vectorized numpy operations.
    Returns dict mapping word -> {word: similarity} for O(1) lookups.
    """
    words = list(embeddings.keys())
    if not words:
        return {}
    
    # Stack all embeddings into a matrix for vectorized computation
    embeddings_matrix = np.array([embeddings[w] for w in words])
    
    # Normalize all vectors (for cosine similarity)
    norms = np.linalg.norm(embeddings_matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1  # Avoid division by zero
    normalized = embeddings_matrix / norms
    
    # Compute all pairwise similarities at once: (n x d) @ (d x n) = (n x n)
    similarity_matrix = np.dot(normalized, normalized.T)
    
    # Convert to dict format
    matrix = {}
    for i, w1 in enumerate(words):
        matrix[w1] = {}
        for j, w2 in enumerate(words):
            matrix[w1][w2] = round(float(similarity_matrix[i, j]), 4)
    
    return matrix


def cache_embeddings(redis: Redis, embeddings: dict, force: bool = False) -> int:
    """Cache individual word embeddings in Redis. Returns count of newly cached."""
    cached_count = 0
    for word, embedding in embeddings.items():
        cache_key = f"emb:{word}"
        if not force:
            existing = redis.get(cache_key)
            if existing:
                continue
        redis.setex(cache_key, EMBEDDING_CACHE_SECONDS, json.dumps(embedding))
        cached_count += 1
    return cached_count


def cache_similarity_matrix(redis: Redis, theme_name: str, matrix: dict, force: bool = False) -> bool:
    """Cache similarity matrix for a theme. Returns True if cached."""
    # Use a consistent key format for theme similarity matrices
    cache_key = f"theme_sim:{theme_name.lower().replace(' ', '_').replace('&', 'and')}"
    
    if not force:
        existing = redis.get(cache_key)
        if existing:
            return False
    
    redis.setex(cache_key, SIMILARITY_MATRIX_CACHE_SECONDS, json.dumps(matrix))
    return True


def get_cached_similarity_matrix(redis: Redis, theme_name: str) -> dict | None:
    """Get cached similarity matrix for a theme."""
    cache_key = f"theme_sim:{theme_name.lower().replace(' ', '_').replace('&', 'and')}"
    cached = redis.get(cache_key)
    if cached:
        return json.loads(cached)
    return None


def precompute_all(force: bool = False, verbose: bool = True) -> dict:
    """
    Precompute embeddings and similarity matrices for all themes.
    
    Returns stats dict with counts of what was processed.
    """
    redis = get_redis()
    client = get_openai_client()
    themes = load_themes()
    
    stats = {
        "themes_processed": 0,
        "embeddings_cached": 0,
        "matrices_cached": 0,
        "themes_skipped": 0,
        "errors": [],
    }
    
    if verbose:
        print(f"Found {len(themes)} themes to process")
    
    for theme_name, words in themes.items():
        try:
            if verbose:
                print(f"\nProcessing theme: {theme_name} ({len(words)} words)")
            
            # Check if matrix already cached
            if not force:
                existing_matrix = get_cached_similarity_matrix(redis, theme_name)
                if existing_matrix:
                    if verbose:
                        print(f"  ✓ Matrix already cached, skipping")
                    stats["themes_skipped"] += 1
                    continue
            
            # Get embeddings
            start = time.time()
            embeddings = batch_get_embeddings(client, words)
            embed_time = time.time() - start
            if verbose:
                print(f"  Got {len(embeddings)} embeddings in {embed_time:.2f}s")
            
            # Cache individual embeddings
            cached = cache_embeddings(redis, embeddings, force=force)
            stats["embeddings_cached"] += cached
            if verbose:
                print(f"  Cached {cached} embeddings")
            
            # Compute and cache similarity matrix
            start = time.time()
            matrix = compute_similarity_matrix(embeddings)
            compute_time = time.time() - start
            if verbose:
                print(f"  Computed similarity matrix in {compute_time:.3f}s")
            
            if cache_similarity_matrix(redis, theme_name, matrix, force=force):
                stats["matrices_cached"] += 1
                if verbose:
                    print(f"  ✓ Cached similarity matrix")
            
            stats["themes_processed"] += 1
            
        except Exception as e:
            error_msg = f"Error processing {theme_name}: {e}"
            stats["errors"].append(error_msg)
            if verbose:
                print(f"  ✗ {error_msg}")
    
    return stats


def main():
    parser = argparse.ArgumentParser(description="Precompute theme embeddings and similarity matrices")
    parser.add_argument("--force", action="store_true", help="Recompute even if already cached")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    args = parser.parse_args()
    
    print("=" * 60)
    print("Precomputing theme embeddings and similarity matrices")
    print("=" * 60)
    
    start = time.time()
    stats = precompute_all(force=args.force, verbose=not args.quiet)
    total_time = time.time() - start
    
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Themes processed: {stats['themes_processed']}")
    print(f"  Themes skipped (already cached): {stats['themes_skipped']}")
    print(f"  Embeddings cached: {stats['embeddings_cached']}")
    print(f"  Similarity matrices cached: {stats['matrices_cached']}")
    print(f"  Errors: {len(stats['errors'])}")
    print(f"  Total time: {total_time:.2f}s")
    print("=" * 60)
    
    if stats["errors"]:
        print("\nErrors:")
        for err in stats["errors"]:
            print(f"  - {err}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

