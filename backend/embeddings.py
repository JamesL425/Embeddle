"""OpenAI embedding service with caching and cosine similarity calculation."""

import os

import numpy as np
from openai import OpenAI, RateLimitError, APIError
from dotenv import load_dotenv
from wordfreq import word_frequency

load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Cache for embeddings (word -> embedding)
embedding_cache: dict[str, list[float]] = {}


class EmbeddingError(Exception):
    """Custom exception for embedding errors."""
    pass


def is_valid_word(word: str) -> bool:
    """Check if a word is a real English word using word frequency."""
    word_lower = word.lower().strip()
    
    # Must be alphabetic only (no numbers, spaces, or special chars)
    if not word_lower.isalpha():
        return False
    
    # Must be at least 2 characters
    if len(word_lower) < 2:
        return False
    
    # Check word frequency - if it's > 0, it's a known word
    # Using 'en' for English
    freq = word_frequency(word_lower, 'en')
    return freq > 0


def get_embedding(word: str) -> list[float]:
    """Get embedding for a word, using cache if available."""
    word_lower = word.lower().strip()
    
    if word_lower in embedding_cache:
        return embedding_cache[word_lower]
    
    try:
        response = client.embeddings.create(
            model="text-embedding-3-large",
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
    """Calculate cosine similarity between two embeddings."""
    vec1 = np.array(embedding1)
    vec2 = np.array(embedding2)
    
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return float(dot_product / (norm1 * norm2))


def calculate_similarities(
    guess_word: str, 
    players: list[tuple[str, list[float]]]
) -> dict[str, float]:
    """
    Calculate similarity between a guess word and all players' secret words.
    
    Args:
        guess_word: The word being guessed
        players: List of (player_id, secret_embedding) tuples
    
    Returns:
        Dictionary mapping player_id to similarity score
    """
    guess_embedding = get_embedding(guess_word)
    
    similarities = {}
    for player_id, secret_embedding in players:
        similarity = cosine_similarity(guess_embedding, secret_embedding)
        # Round to 2 decimal places for display
        similarities[player_id] = round(similarity, 2)
    
    return similarities

