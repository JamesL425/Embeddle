# Bagofwordsdle

A multiplayer word deduction game where players try to guess each other's secret words using semantic similarity.

## How to Play

1. **Setup**: Each player joins with a name and picks a secret word
2. **Gameplay**: On your turn, guess any word
3. **Reveal**: Everyone sees how similar your guess is to ALL players' secret words
4. **Elimination**: If your guess is >95% similar to someone's word, they're eliminated!
5. **Reward**: Eliminating a player lets you change your own secret word
6. **Win**: Be the last player standing

## Tech Stack

- **Backend**: Python FastAPI
- **Embeddings**: OpenAI `text-embedding-3-small`
- **Frontend**: Vanilla HTML/CSS/JS

## Setup

### Prerequisites

- Python 3.11+
- OpenAI API key

### Installation

1. Clone the repository:
```bash
cd bagofwordsdle
```

2. Create a virtual environment and install dependencies:
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Set your OpenAI API key:
```bash
export OPENAI_API_KEY="your-api-key-here"
```

Or create a `.env` file in the `backend` directory:
```
OPENAI_API_KEY=your-api-key-here
```

### Running the Game

1. Start the backend server:
```bash
cd backend
python main.py
```

2. Open your browser to `http://localhost:8000`

3. Create a game, share the code with friends, and play!

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/games` | Create a new game |
| POST | `/games/{code}/join` | Join with name + secret word |
| POST | `/games/{code}/start` | Start the game (host only) |
| GET | `/games/{code}?player_id=...` | Get game state |
| POST | `/games/{code}/guess` | Submit a guess |
| POST | `/games/{code}/change-word` | Change your word (if earned) |

## Game Rules

- **Players**: 3-4 per game
- **Elimination threshold**: 95% cosine similarity
- **Word change reward**: Earned by eliminating another player

## Strategy Tips

- Pick a word that's unique but not too obscure
- Your guesses reveal info about YOUR word too - be careful!
- Use the similarity percentages to narrow down opponents' words
- If you eliminate someone, consider changing your word to reset their intel on you

