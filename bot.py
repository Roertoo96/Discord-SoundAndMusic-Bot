import discord
import platform
from discord.ext import commands
from discord.ext.commands import DefaultHelpCommand
from discord.ui import Button, View, Modal, InputText
import os
import json
import aiohttp  # um die Dateien herunterzuladen
import collections
import math

def perform_os_specific_action():
    current_os = platform.system()

    if current_os == "Windows":
        media = r"C:/Users/Andre/OneDrive/Github/PROST/media/"
        token = os.getenv('discordbot')
        return media, token
        # Hier den Code für Windows hinzufügen

    elif current_os == "Darwin":  # "Darwin" ist der Systemname für macOS
        media = '.\media\\'
        token = os.environ.get('discordbot')
        return media, token
        # Hier den Code für macOS hinzufügen

    else:
        media = '.\media\\'
        token = os.environ.get('discordbot')
        return media, token

# Media Variable setzen
media,token = perform_os_specific_action()

MAX_BUTTONS_PER_MESSAGE = 20  # Discord erlaubt aktuell maximal 25 Buttons pro Nachricht


token = os.getenv('discordbot')

# Pfad zur Opus-Bibliothek auf einem Mac mit Homebrew
# opus_lib_path = '/opt/homebrew/lib/libopus.dylib'
user_ranks = collections.defaultdict(int)


#if os.path.exists(opus_lib_path) and not discord.opus.is_loaded():
#    discord.opus.load_opus(opus_lib_path)
#    print('Opus-Bibliothek erfolgreich geladen.')
#else:
#    print(f'Kann die Opus-Bibliothek nicht unter {opus_lib_path} finden oder sie ist bereits geladen.')

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.voice_states = True

#bot = commands.Bot(command_prefix='!', intents=intents)
bot = commands.Bot(command_prefix='!', help_command=None, intents=intents)

# Laden von Soundrängen und Benutzerrängen aus einer JSON-Datei
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


# Initiallade die Ränge beim Starten des Bots
ranks, user_ranks, sound_emojis = load_ranks()



class SearchButton(Button):
    def __init__(self):
        super().__init__(label="Suche nach Sounds", style=discord.ButtonStyle.primary)
    
    async def callback(self, interaction: discord.Interaction):
        # Zeige das Modal an, wenn der Button gedrückt wird
        modal = SearchModal()
        await interaction.response.send_modal(modal)

class SearchModal(Modal):
    def __init__(self):
        super().__init__(title="Sound-Suche")

        self.add_item(InputText(
            label="Wonach möchtest du suchen?",
            placeholder="Gebe einen Suchbegriff ein...",
            custom_id="search_query",
            style=discord.InputTextStyle.short,
            min_length=1
        ))

    async def callback(self, interaction: discord.Interaction):
        # Hole die Suchanfrage aus dem Modal
        search_query = self.children[0].value

        # Führe die Suche durch und filtere die Sounddateien
        search_results = [
            (sound_file, (rank, ranks.get(os.path.splitext(sound_file)[0], 0)))
            for rank, sound_file in enumerate(sorted(
                os.listdir('./media'), key=lambda sf: ranks.get(os.path.splitext(sf)[0], 0), reverse=True), start=1)
            if search_query.lower() in os.path.splitext(sound_file)[0].lower() and sound_file.endswith(('.mp3', '.wav'))
        ]

        # Erstelle eine Ansicht mit den Ergebnissen der Suche
        if search_results:
            view = SoundboardView(search_results)
            await interaction.response.edit_message(view=view)
        else:
            await interaction.response.send_message("Es wurden keine passenden Sounds gefunden.")





class RefreshButton(Button):
    def __init__(self, label: str, style: discord.ButtonStyle, custom_id: str):
        super().__init__(label=label, style=style, custom_id=custom_id)

    async def callback(self, interaction: discord.Interaction):
        # Erstelle eine neue View mit dem ursprünglichen Suchbutton
        view = SoundboardView([])
        search_button = SearchButton()
        view.add_item(search_button)
        
        # Aktualisiere die Nachricht, um den neuen View anzuzeigen
        await interaction.response.edit_message(view=view)


class SoundboardButton(Button):
    def __init__(self, sound_file, rank, points):
        emoji = sound_emojis.get(os.path.splitext(sound_file)[0])

        # Das Label des Buttons enthält den Rang, den Namen und die Punktzahl
        super().__init__(label=f"{rank}. {os.path.splitext(sound_file)[0]} ({points})", emoji=emoji)
        self.sound_file = sound_file

    async def callback(self, interaction: discord.Interaction):
        # Zuerst bestätige die Interaktion sofort
        await interaction.response.defer()
        
        vc = interaction.guild.voice_client
        if vc and vc.is_connected():
            vc.stop()
            audio_source = discord.FFmpegPCMAudio(f'{media}{self.sound_file}')
            #audio_source = discord.FFmpegPCMAudio(f'{self.sound_file}')
            vc.play(audio_source)

            # Update rank
            label = os.path.splitext(self.sound_file)[0]
            ranks[label] = ranks.get(label, 0) + 1
            user_ranks[interaction.user.id] += 1

            # Rufe save_ranks mit allen Dictionaries auf
            save_ranks(ranks, user_ranks, sound_emojis)

            # Du brauchst nicht zu warten, bis der Sound zu Ende ist
            # Die Interaktion wird bereits durch "defer()" bestätigt
        else:
            # Sende eine Nachricht, wenn der Bot nicht im Voice-Channel ist
            await interaction.followup.send("Ich bin in keinem Sprachkanal.", ephemeral=True)

class SoundboardView(View):
    def __init__(self, sound_files_with_ranks):
        super().__init__(timeout=None)
        
        for sound_file, rank_and_points in sound_files_with_ranks:
            self.add_item(SoundboardButton(sound_file, *rank_and_points))

        if sound_files_with_ranks:  # Wenn es Sound-Dateien gibt, dann haben wir Suchergebnisse
            refresh_button = RefreshButton(label="Zurücksetzen", style=discord.ButtonStyle.grey, custom_id="refresh_button")
            self.add_item(refresh_button)
@bot.event
async def on_ready():
    print(f'Angemeldet als {bot.user.name}')


@bot.command(name='soundboard')
async def soundboard(ctx: commands.Context):
    # Überprüfen, ob der Befehl von jemandem in einem Sprachkanal gesendet wurde
        # Ihr bisheriger Code für das Soundboard ...
    # Sende den Suchbutton am Ende des Befehls
    search_button = SearchButton()
    view = SoundboardView(sound_files_with_ranks=[])  # initial leer, bis Suche abgeschlossen ist
    view.add_item(search_button)  # Füge den Suchbutton zur Ansicht hinzu
    await ctx.send("Klicke auf den Button um nach Sounds zu suchen, oder benutze das Soundboard:", view=view)

    if ctx.author.voice is None:
        await ctx.send("Du musst in einem Sprachkanal sein, um das Soundboard zu verwenden.")
        return

    voice_channel = ctx.author.voice.channel

    # Verbinden Sie sich mit dem Sprachkanal, wenn Sie noch nicht verbunden sind
    if ctx.voice_client is None:
        await voice_channel.connect()
    elif ctx.voice_client.channel != voice_channel:
        # Wenn der Bot verbunden ist, aber nicht im richtigen Kanal, wechseln Sie den Kanal
        await ctx.voice_client.move_to(voice_channel)

    # Eine sortierte Liste von Sounddateien mit Rängen und Punkten erstellen
    sound_files_with_ranks = [
        (sound_file, (rank, ranks.get(os.path.splitext(sound_file)[0], 0)))
        for rank, sound_file in enumerate(sorted(
            os.listdir('./media'), key=lambda sf: ranks.get(os.path.splitext(sf)[0], 0), reverse=True), start=1)
        if sound_file.endswith(('.mp3', '.wav'))
    ]
    
    # Erstelle eine Liste von SoundboardViews, jede mit bis zu MAX_BUTTONS_PER_MESSAGE Buttons
    sound_files_chunks = [sound_files_with_ranks[i:i + MAX_BUTTONS_PER_MESSAGE] for i in range(0, len(sound_files_with_ranks), MAX_BUTTONS_PER_MESSAGE)]
    views = [SoundboardView(chunk) for chunk in sound_files_chunks]

    # Sende die Views in separaten Nachrichten
    for view in views:
        await ctx.send("", view=view)


@bot.command(name='setemoji')
async def setemoji(ctx, sound_name: str, emoji: str):
    # Prüfen, ob der Sound existiert
    sound_file = f'{sound_name}.mp3'  # oder '.wav', je nach Dateityp
    if not os.path.exists(f'./media/{sound_file}'):
        await ctx.send('Sound nicht gefunden.')
        return

    # Emoji in den Rängen speichern
    sound_emojis[sound_name] = emoji
    save_ranks(ranks, user_ranks, sound_emojis)  # Erweitert die Funktion save_ranks
    await ctx.send(f'Emoji für {sound_name} gesetzt zu {emoji}')


@bot.command(name='upload', help='Lade eine MP3-Datei hoch. !upload')
async def upload(ctx):
    # Prüfen, ob es Anhänge gibt
    if ctx.message.attachments:
        # Gehe alle Anhänge durch
        for attachment in ctx.message.attachments:
            # Überprüfe, ob der Dateityp .mp3 ist
            if attachment.filename.lower().endswith('.mp3'):
                # Erstelle den Media-Ordner, wenn er nicht existiert
                os.makedirs('media', exist_ok=True)
                # Definiere den Pfad, wo die Datei gespeichert werden soll
                file_path = os.path.join('media', attachment.filename)
                
                # Verwenden von aiohttp, um die Datei asynchron herunterzuladen
                async with aiohttp.ClientSession() as session:
                    async with session.get(attachment.url) as resp:
                        if resp.status == 200:
                            # Schreibe die Datei in den Media-Ordner
                            with open(file_path, 'wb') as f:
                                f.write(await resp.read())
                            await ctx.send(f'Datei "{attachment.filename}" gespeichert.')
                        else:
                            await ctx.send('Fehler beim Herunterladen der Datei.')
    else:
        await ctx.send('Keine Anhänge gefunden.')



@bot.command(name='delete', help='Lösche eine MP3-Datei. !delete dateiname.mp3')
@commands.has_permissions(manage_messages=True)  # Erlaubt diesen Befehl nur für Benutzer mit der Berechtigung Nachrichten zu verwalten.
async def delete(ctx, *, file_name: str):
    # Pfad zum Ordner, wo die Dateien gespeichert sind
    media_folder = os.path.join(os.getcwd(), 'media')
    file_path = os.path.join(media_folder, file_name)
    
    # Überprüfen, ob die Datei existiert
    if os.path.exists(file_path) and file_path.endswith('.mp3'):
        os.remove(file_path)  # Lösche die Datei
        await ctx.send(f'Datei "{file_name}" wurde erfolgreich gelöscht.')
    else:
        await ctx.send(f'Datei "{file_name}" nicht gefunden oder Dateityp nicht zulässig.')

@bot.command(name='list')
async def list_files(ctx):
    # Liste alle MP3-Dateien im 'media'-Ordner auf
    files = os.listdir('./media')
    mp3_files = [f for f in files if f.endswith('.mp3')]
    await ctx.send("Verfügbare MP3-Dateien:\n" + "\n".join(mp3_files) if mp3_files else "Keine Dateien gefunden.")


@bot.command(name='help')
async def help_command(ctx):
    embed = discord.Embed(title="Hilfe", description="Liste aller verfügbaren Befehle", color=0x00ff00)
    
    # Für jede Command Category oder für Command-Group
    embed.add_field(name="Befehl", value="`!help`\n`!upload`\n`!delete`", inline=True)
    embed.add_field(name="Beschreibung", value="Zeigt diese Hilfe an\nLädt eine MP3 hoch\nLöscht eine MP3", inline=True)
    embed.add_field(name="Verwendung", value="`!help`\n`!upload [Attachment]`\n`!delete <filename>`", inline=True)
    
    await ctx.send(embed=embed)

# Neue Funktion send_rankings hinzufügen
@bot.command(name='rankings')
async def send_rankings(ctx: commands.Context):
    # Erstellen Sie eine sortierte Liste der Benutzerrankings
    sorted_user_ranks = sorted(user_ranks.items(), key=lambda item: item[1], reverse=True)
    if not sorted_user_ranks:
        await ctx.send("Noch keine Rankings vorhanden.")
        return
    
    # Erstellen Sie eine Nachricht mit den Top-Rankings
    rankings_description = "\n".join([f"<@{user_id}>: {points} Klick(s)" for user_id, points in sorted_user_ranks])
    embed = discord.Embed(title="User Rankings", description=rankings_description, color=0x00ff00)
    await ctx.send(embed=embed)

def load_ranks():
    if os.path.exists('ranks.json'):
        with open('ranks.json', 'r') as f:
            data = json.load(f)
            return data.get('sound_ranks', {}), collections.defaultdict(int, data.get('user_ranks', {}))
    return {}, collections.defaultdict(int)

ranks, user_ranks = load_ranks()

bot.run(token)





