import json
import os


RANKS_FILE = os.path.join("media", "ranks.json")
LEGACY_RANKS_FILE = "ranks.json"


def get_ranks_file_path():
    os.makedirs(os.path.dirname(RANKS_FILE), exist_ok=True)
    if os.path.exists(RANKS_FILE):
        return RANKS_FILE
    if os.path.exists(LEGACY_RANKS_FILE):
        return LEGACY_RANKS_FILE
    return RANKS_FILE


def load_ranks():
    ranks_file = get_ranks_file_path()
    if os.path.exists(ranks_file):
        with open(ranks_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            sound_ranks = data.get("sound_ranks", {})
            user_ranks = data.get("user_ranks", {})
            sound_emojis = data.get("sound_emojis", {})
            return sound_ranks, user_ranks, sound_emojis
    return {}, {}, {}


def save_ranks(sound_ranks, user_ranks, sound_emojis):
    data = {
        "sound_ranks": sound_ranks,
        "user_ranks": user_ranks,
        "sound_emojis": sound_emojis,
    }
    with open(RANKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
