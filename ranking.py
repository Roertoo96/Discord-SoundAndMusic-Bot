import os
import json
import collections


def load_ranks():
    if os.path.exists('ranks.json'):
        with open('ranks.json', 'r') as f:
            data = json.load(f)
            sound_ranks = data.get('sound_ranks', {})
            user_ranks = data.get('user_ranks', {})  # Ändere von defaultdict(int) zu einem normalen Dictionary.
            sound_emojis = data.get('sound_emojis', {})
            return sound_ranks, user_ranks, sound_emojis
    else:
        return {}, {}, {}  # Return ein leeres Dictionary für user_ranks, anstelle von defaultdict(int).

def save_ranks(sound_ranks, user_ranks, sound_emojis):
    # Daten mit Sound Ranks, User Ranks (jetzt mit exp und level), und Sound Emojis speichern
    data = {
        'sound_ranks': sound_ranks,
        'user_ranks': user_ranks,  # Direktes Speichern des user_ranks Dictionary.
        'sound_emojis': sound_emojis
    }
    with open('ranks.json', 'w') as f:
        json.dump(data, f, indent=4)
