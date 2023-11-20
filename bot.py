import discord
from discord.ext import commands
from discord.ext.commands import DefaultHelpCommand
from discord.ui import Button, View
import os
import json
import aiohttp  # um die Dateien herunterzuladen


token = os.environ.get('discordbot')


# Pfad zur Opus-Bibliothek auf einem Mac mit Homebrew
opus_lib_path = '/opt/homebrew/lib/libopus.dylib'

if os.path.exists(opus_lib_path) and not discord.opus.is_loaded():
    discord.opus.load_opus(opus_lib_path)
    print('Opus-Bibliothek erfolgreich geladen.')
else:
    print(f'Kann die Opus-Bibliothek nicht unter {opus_lib_path} finden oder sie ist bereits geladen.')


intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.voice_states = True

#bot = commands.Bot(command_prefix='!', intents=intents)
bot = commands.Bot(command_prefix='!', help_command=None, intents=intents)






# Funktion zum Laden der Soundränge aus einer JSON-Datei
def load_ranks():
    if os.path.exists('ranks.json'):
        with open('ranks.json', 'r') as f:
            return json.load(f)
    return {}

# Funktion zum Speichern der Soundränge in einer JSON-Datei
def save_ranks(ranks):
    with open('ranks.json', 'w') as f:
        json.dump(ranks, f, indent=4)

ranks = load_ranks()  # Lade die aktuellen Ränge beim Start des Bots




class SoundboardButton(Button):
    def __init__(self, sound_file, rank, points):
        # Das Label des Buttons enthält den Rang, den Namen und die Punktzahl
        super().__init__(label=f"{rank}. {os.path.splitext(sound_file)[0]} ({points})")
        self.sound_file = sound_file

    async def callback(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_connected():
            vc.stop()
            audio_source = discord.FFmpegPCMAudio(f'./media/{self.sound_file}')
            vc.play(audio_source)

            # Update rank
            label = os.path.splitext(self.sound_file)[0]
            ranks[label] = ranks.get(label, 0) + 1
            save_ranks(ranks)

            # Um die Labels der Buttons zu aktualisieren, muss die View aktualisiert werden
            # await interaction.response.edit_message(view=self.view)
            # await interaction.followup.send(f"Jetzt spielt: {label}. (Gespielt: {ranks[label]} mal)", ephemeral=True)
        else:
            await interaction.response.send_message("Ich bin in keinem Sprachkanal", ephemeral=True)

class SoundboardView(View):
    def __init__(self, sound_files_with_ranks):
        super().__init__(timeout=None)
        # Für jede Sounddatei wird ein Button mit dem entsprechenden Rang und den Punkten erstellt
        for sound_file, rank_and_points in sound_files_with_ranks:
            self.add_item(SoundboardButton(sound_file, *rank_and_points))

            




                # Eigene Help-Klasse, die von DefaultHelpCommand erbt
# class CustomHelpCommand(DefaultHelpCommand):
#     def __init__(self):
#         super().__init__()
    
#     async def send_bot_help(self, mapping):
#         # Passen Sie das Design der Hilfeausgabe an Ihre Vorlieben an
#         embed = discord.Embed(title="Bot Befehle", description="Liste aller Befehle", color=discord.Color.blue())
#         for cog, commands in mapping.items():
#             filtered = await self.filter_commands(commands, sort=True)
#             command_signatures = [self.get_command_signature(c) for c in filtered]
#             if command_signatures:
#                 cog_name = getattr(cog, "qualified_name", "No Category")
#                 embed.add_field(name=cog_name, value="\n".join(command_signatures), inline=False)
        
#         channel = self.get_destination()
#         await channel.send(embed=embed)


@bot.event
async def on_ready():
    print(f'Angemeldet als {bot.user.name}')


@bot.command(name='soundboard')
async def soundboard(ctx: commands.Context):
    # Überprüfen, ob der Befehl von jemandem in einem Sprachkanal gesendet wurde
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
    
    # Erstelle eine Ansicht des Soundboards mit dem aktuellen Ranking
    view = SoundboardView(sound_files_with_ranks)
    await ctx.send("Wähle einen Sound aus der Liste:", view=view)



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




bot.run(token)





