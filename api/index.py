"""Vercel serverless function for Bagofwordsdle API with Upstash Redis storage."""

import json
import os
import secrets
import string
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
from http.server import BaseHTTPRequestHandler

import numpy as np
from openai import OpenAI
from wordfreq import word_frequency
from upstash_redis import Redis

# Initialize clients lazily
_openai_client = None
_redis_client = None


def get_openai_client():
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


def get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis(
            url=os.getenv("UPSTASH_REDIS_REST_URL"),
            token=os.getenv("UPSTASH_REDIS_REST_TOKEN"),
        )
    return _redis_client


# ============== HELPERS ==============

def generate_game_code() -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(6))


def generate_player_id() -> str:
    return secrets.token_hex(8)


def is_valid_word(word: str) -> bool:
    word_lower = word.lower().strip()
    if not word_lower.isalpha():
        return False
    if len(word_lower) < 2:
        return False
    freq = word_frequency(word_lower, 'en')
    return freq > 0


def get_embedding(word: str) -> list:
    word_lower = word.lower().strip()
    
    # Check Redis cache first
    redis = get_redis()
    cache_key = f"emb:{word_lower}"
    cached = redis.get(cache_key)
    if cached:
        return json.loads(cached)
    
    client = get_openai_client()
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=word_lower,
    )
    embedding = response.data[0].embedding
    
    # Cache for 24 hours
    redis.setex(cache_key, 86400, json.dumps(embedding))
    return embedding


def cosine_similarity(embedding1, embedding2) -> float:
    vec1 = np.array(embedding1)
    vec2 = np.array(embedding2)
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(dot_product / (norm1 * norm2))


# ============== GAME STORAGE ==============

def save_game(code: str, game_data: dict):
    redis = get_redis()
    # Games expire after 2 hours
    redis.setex(f"game:{code}", 7200, json.dumps(game_data))


def load_game(code: str) -> Optional[dict]:
    redis = get_redis()
    data = redis.get(f"game:{code}")
    if data:
        return json.loads(data)
    return None


def delete_game(code: str):
    redis = get_redis()
    redis.delete(f"game:{code}")


# ============== CONSTANTS ==============

ELIMINATION_THRESHOLD = 0.95
MIN_PLAYERS = 3
MAX_PLAYERS = 4


# ============== HANDLER ==============

class handler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_error(self, message, status=400):
        self._send_json({"detail": message}, status)

    def _get_body(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length:
            return json.loads(self.rfile.read(content_length))
        return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        path = self.path.split('?')[0]
        query = {}
        if '?' in self.path:
            query_string = self.path.split('?')[1]
            for param in query_string.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    query[key] = value

        # GET /api/games/{code}
        if path.startswith('/api/games/') and path.count('/') == 3:
            code = path.split('/')[3].upper()
            player_id = query.get('player_id', '')
            
            game = load_game(code)
            if not game:
                return self._send_error("Game not found", 404)
            
            # Check player exists
            player = None
            for p in game['players']:
                if p['id'] == player_id:
                    player = p
                    break
            
            if not player:
                return self._send_error("You are not in this game", 403)
            
            # Build response with hidden words
            response = {
                "code": game['code'],
                "host_id": game['host_id'],
                "players": [],
                "current_turn": game['current_turn'],
                "current_player_id": game['players'][game['current_turn']]['id'] if game['status'] == 'playing' and game['players'] else None,
                "status": game['status'],
                "winner": game.get('winner'),
                "history": game.get('history', []),
            }
            
            for p in game['players']:
                response['players'].append({
                    "id": p['id'],
                    "name": p['name'],
                    "secret_word": p['secret_word'] if p['id'] == player_id else None,
                    "is_alive": p['is_alive'],
                    "can_change_word": p.get('can_change_word', False) if p['id'] == player_id else None,
                })
            
            return self._send_json(response)

        self._send_error("Not found", 404)

    def do_POST(self):
        path = self.path.split('?')[0]
        body = self._get_body()

        # POST /api/games - Create game
        if path == '/api/games':
            code = generate_game_code()
            
            # Make sure code is unique
            while load_game(code):
                code = generate_game_code()
            
            game = {
                "code": code,
                "host_id": "",
                "players": [],
                "current_turn": 0,
                "status": "waiting",
                "winner": None,
                "history": [],
            }
            save_game(code, game)
            return self._send_json({"code": code, "player_id": ""})

        # POST /api/games/{code}/join
        if '/join' in path:
            code = path.split('/')[3].upper()
            game = load_game(code)
            
            if not game:
                return self._send_error("Game not found", 404)
            if game['status'] != 'waiting':
                return self._send_error("Game has already started", 400)
            if len(game['players']) >= MAX_PLAYERS:
                return self._send_error("Game is full", 400)
            
            name = body.get('name', '').strip()
            secret_word = body.get('secret_word', '').strip()
            
            if not name or not secret_word:
                return self._send_error("Name and secret word required", 400)
            
            if any(p['name'].lower() == name.lower() for p in game['players']):
                return self._send_error("Name already taken", 400)
            
            if not is_valid_word(secret_word):
                return self._send_error("Please enter a valid English word", 400)
            
            try:
                embedding = get_embedding(secret_word)
            except Exception as e:
                return self._send_error(f"API error: {str(e)}", 503)
            
            player_id = generate_player_id()
            player = {
                "id": player_id,
                "name": name,
                "secret_word": secret_word.lower(),
                "secret_embedding": embedding,
                "is_alive": True,
                "can_change_word": False,
            }
            game['players'].append(player)
            
            if len(game['players']) == 1:
                game['host_id'] = player_id
            
            save_game(code, game)
            return self._send_json({"player_id": player_id})

        # POST /api/games/{code}/start
        if '/start' in path:
            code = path.split('/')[3].upper()
            game = load_game(code)
            
            if not game:
                return self._send_error("Game not found", 404)
            
            player_id = body.get('player_id', '')
            if game['host_id'] != player_id:
                return self._send_error("Only the host can start", 403)
            if game['status'] != 'waiting':
                return self._send_error("Game already started", 400)
            if len(game['players']) < MIN_PLAYERS:
                return self._send_error(f"Need at least {MIN_PLAYERS} players", 400)
            
            game['status'] = 'playing'
            game['current_turn'] = 0
            save_game(code, game)
            return self._send_json({"status": "started"})

        # POST /api/games/{code}/guess
        if '/guess' in path:
            code = path.split('/')[3].upper()
            game = load_game(code)
            
            if not game:
                return self._send_error("Game not found", 404)
            if game['status'] != 'playing':
                return self._send_error("Game not in progress", 400)
            
            player_id = body.get('player_id', '')
            word = body.get('word', '').strip()
            
            player = None
            player_idx = -1
            for i, p in enumerate(game['players']):
                if p['id'] == player_id:
                    player = p
                    player_idx = i
                    break
            
            if not player:
                return self._send_error("You are not in this game", 403)
            if not player['is_alive']:
                return self._send_error("You have been eliminated", 400)
            
            current_player = game['players'][game['current_turn']]
            if current_player['id'] != player_id:
                return self._send_error("It's not your turn", 400)
            
            if not is_valid_word(word):
                return self._send_error("Please enter a valid English word", 400)
            
            try:
                guess_embedding = get_embedding(word)
            except Exception as e:
                return self._send_error(f"API error: {str(e)}", 503)
            
            similarities = {}
            for p in game['players']:
                sim = cosine_similarity(guess_embedding, p['secret_embedding'])
                similarities[p['id']] = round(sim, 2)
            
            eliminations = []
            for p in game['players']:
                if p['id'] != player_id and p['is_alive']:
                    if similarities.get(p['id'], 0) >= ELIMINATION_THRESHOLD:
                        p['is_alive'] = False
                        eliminations.append(p['id'])
            
            if eliminations:
                player['can_change_word'] = True
            
            # Record history
            history_entry = {
                "guesser_id": player['id'],
                "guesser_name": player['name'],
                "word": word.lower(),
                "similarities": similarities,
                "eliminations": eliminations,
            }
            game['history'].append(history_entry)
            
            # Advance turn
            alive_players = [p for p in game['players'] if p['is_alive']]
            if len(alive_players) <= 1:
                game['status'] = 'finished'
                if alive_players:
                    game['winner'] = alive_players[0]['id']
            else:
                num_players = len(game['players'])
                next_turn = (game['current_turn'] + 1) % num_players
                while not game['players'][next_turn]['is_alive']:
                    next_turn = (next_turn + 1) % num_players
                game['current_turn'] = next_turn
            
            save_game(code, game)
            
            return self._send_json({
                "similarities": similarities,
                "eliminations": eliminations,
                "game_over": game['status'] == 'finished',
                "winner": game.get('winner'),
            })

        # POST /api/games/{code}/change-word
        if '/change-word' in path:
            code = path.split('/')[3].upper()
            game = load_game(code)
            
            if not game:
                return self._send_error("Game not found", 404)
            if game['status'] != 'playing':
                return self._send_error("Game not in progress", 400)
            
            player_id = body.get('player_id', '')
            new_word = body.get('new_word', '').strip()
            
            player = None
            for p in game['players']:
                if p['id'] == player_id:
                    player = p
                    break
            
            if not player:
                return self._send_error("You are not in this game", 403)
            if not player.get('can_change_word', False):
                return self._send_error("You don't have a word change", 400)
            if not is_valid_word(new_word):
                return self._send_error("Please enter a valid English word", 400)
            
            try:
                embedding = get_embedding(new_word)
            except Exception as e:
                return self._send_error(f"API error: {str(e)}", 503)
            
            player['secret_word'] = new_word.lower()
            player['secret_embedding'] = embedding
            player['can_change_word'] = False
            
            save_game(code, game)
            return self._send_json({"status": "word_changed"})

        self._send_error("Not found", 404)
