import os
import json
import collections


def load_ranks():
    if os.path.exists('ranks.json'):
        with open('ranks.json', 'r') as f:
            data = json.load(f)
            sound_ranks = data.get('sound_ranks', {})
            user_ranks = collections.defaultdict(int, data.get('user_ranks', {}))
            sound_emojis = data.get('sound_emojis', {})
            return sound_ranks, user_ranks, sound_emojis
    else:
        return {}, collections.defaultdict(int), {}

# Speichern von Soundrängen und Benutzerrängen in einer JSON-Datei
def save_ranks(sound_ranks, user_rankings, sound_emojis):
    # Konsolidieren von Benutzerranken
    consolidated_user_rankings = {}
    for user_id, points in user_rankings.items():
        # user_id als string, um mit JSON-Schlüsseln kompatibel zu sein
        user_id_str = str(user_id)
        consolidated_user_rankings[user_id_str] = points
            
    # Speichern der Daten mit konsolidierten Benutzerrankings und Sound Emojis
    data = {
        'sound_ranks': sound_ranks,
        'user_ranks': consolidated_user_rankings,
        'sound_emojis': sound_emojis  # Speichere die Sound Emojis
    }
    with open('ranks.json', 'w') as f:
        json.dump(data, f, indent=4)