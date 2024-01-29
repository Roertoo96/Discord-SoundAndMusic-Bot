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
from checkos import perform_os_specific_action
from ranking import load_ranks,save_ranks
import paramiko
import asyncio
import subprocess
from discord.ext import tasks

# import logging
# logging.basicConfig(level=logging.DEBUG)
# paramiko.util.log_to_file('paramiko.log')

# Globale Funktion zum Pingen eines Servers
async def ping_server(host):
    try:
        cmd = ['ping', '-c', '1', '-W', '5', host] if platform.system().lower() != 'windows' else ['ping', '-n', '1', '-w', '5000', host]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        return proc.returncode == 0
    except Exception as e:
        print(f"Error during ping: {e}")
        return False

# Globale Funktion zum Ausführen eines SSH-Befehls
async def run_script_via_ssh(host, port, username, password, command):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(host, port=port, username=username, password=password, timeout=15)
        stdin, stdout, stderr = ssh.exec_command(command)
        return stdout.read().decode('utf-8'), stderr.read().decode('utf-8')
    finally:
        ssh.close()

####  Discord Intents  #####

intents = discord.Intents.default()  # Setzt die Standardintents
intents.messages = True              # Erlaubt dem Bot, Nachrichten zu erhalten
intents.message_content = True       # Erlaubt dem Bot, auf den Inhalt von Nachrichten zuzugreifen
intents.guilds = True                # Erlaubt dem Bot, sich über Serverevents zu informieren
intents.voice_states = True          # Erlaubt dem Bot, sich über Sprachstatusänderungen zu informieren



#####    Variablen     #####

media,token,passwordpavsrv = perform_os_specific_action()
MAX_BUTTONS_PER_MESSAGE = 20  # Discord erlaubt aktuell maximal 25 Buttons pro Nachricht
token = os.getenv('discordbot')
user_ranks = collections.defaultdict(int)
opus_lib_path = '/opt/homebrew/lib/libopus.dylib'
LEVEL_UP_EXP = 100  # Angenommen, jeder Levelaufstieg erfordert 100 EXP.
pw = passwordpavsrv
#passwordpavsrv = os.getenv('pav')
# passwordpavsrv = os.environ.get('pav')
# print(passwordpavsrv)





# Classe für den Status-Monitor des Servers
class ServerStatusMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.server_status = False
        self.server_monitor.start()

    @tasks.loop(minutes=1.0)
    async def server_monitor(self):
        host = "45.93.251.18"
        channel = self.bot.get_channel(1200120474198343871)
        status = await ping_server(host)
        if status != self.server_status:
            self.server_status = status
            message = f":green_circle: Der Server `{host}` ist jetzt erreichbar." if status else f":red_circle: Der Server `{host}` ist offline."
            if channel:
                await channel.send(message)

    @server_monitor.before_loop
    async def before_server_monitor(self):
        await self.bot.wa


####   opus wird nur für den  Mac benötigt   #####

if os.path.exists(opus_lib_path) and not discord.opus.is_loaded():
   discord.opus.load_opus(opus_lib_path)
   print('Opus-Bibliothek erfolgreich geladen.')
else:
   print(f'Kann die Opus-Bibliothek nicht unter {opus_lib_path} finden oder sie ist bereits geladen.')



#######    Bot start / commands laden   ########
bot = commands.Bot(command_prefix='!', help_command=None, intents=intents)



####### Initiallade die Ränge beim Starten des Bots  ######
ranks, user_ranks, sound_emojis = load_ranks()






##### Klassen und Discord funktionen #####

class SearchButton(Button):
    def __init__(self):
        super().__init__(label="Suche nach Sounds", style=discord.ButtonStyle.primary)
    
    async def callback(self, interaction: discord.Interaction):
        # Zeige das Modal an, wenn der Button gedrückt wird
        modal = SearchModal()
        await interaction.response.send_modal(modal)



## Modal ist das in Discortd ein Dialogfenster ##
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
            view = SoundboardView(search_results, user_ranks, sound_emojis)
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
    def __init__(self, sound_file, rank, points, user_ranks, sound_emojis):
        emoji = sound_emojis.get(os.path.splitext(sound_file)[0])
        
        # Das Label des Buttons enthält den Rang, den Namen und die Punktzahl
        super().__init__(label=f"{rank}. {os.path.splitext(sound_file)[0]} ({points})", emoji=emoji)
        
        self.sound_file = sound_file
        self.user_ranks = user_ranks
        self.sound_emojis = sound_emojis

    async def callback(self, interaction: discord.Interaction):
        # Zuerst bestätige die Interaktion sofort
        await interaction.response.defer()
        
        vc = interaction.guild.voice_client
        if vc and vc.is_connected():
            vc.stop()  # Stoppen Sie die aktuelle Tonwiedergabe falls vorhanden
            audio_source = discord.FFmpegPCMAudio(f'{media}{self.sound_file}')
            vc.play(audio_source)  # Spielen Sie den neuen Ton ab

            user_id = str(interaction.user.id)
            # Stellen Sie sicher, dass der Benutzer im user_ranks-Verzeichnis ist, initialisieren Sie ihn andernfalls
            if user_id not in self.user_ranks:
                self.user_ranks[user_id] = {"exp": 0, "level": 1}
            
            user_data = self.user_ranks[user_id]

            # Fügen Sie einige EXP hinzu für das Abspielen des Sounds
            user_data['exp'] += 10  # Hier geben Sie jedem Nutzer 10 EXP für das Abspielen eines Sounds 

            # Prüfen Sie ob ein Levelaufstieg vorgenommen werden sollte
            if user_data['exp'] >= LEVEL_UP_EXP:
                user_data['level'] += 1  # Erhöhen des Nutzerlevels
                user_data['exp'] = user_data['exp'] - LEVEL_UP_EXP  # Abziehen der EXP für den Levelaufstieg

            # Aktualisieren Sie die Hauptdatenstruktur user_ranks
            self.user_ranks[user_id] = user_data
            
            # Erhöhen Sie die Anzahl der Abspielungen des Sounds
            label = os.path.splitext(self.sound_file)[0]
            ranks[label] = ranks.get(label, 0) + 1
            
            # Speichern Sie die aktualisierten Ränge und Nutzerinformationen
            save_ranks(ranks, self.user_ranks, self.sound_emojis)

            # Hinweis: Sie müssen nicht auf das Ende der Tonwiedergabe warten
            # Die Interaktion ist bereits durch "defer()" bestätigt
        else:
            # Geben Sie eine Nachricht aus, falls der Bot nicht in einem Sprachkanal ist
            await interaction.followup.send("Ich bin in keinem Sprachkanal.", ephemeral=True)

class SoundboardView(View):
    def __init__(self, sound_files_with_ranks, user_ranks, sound_emojis):
        super().__init__(timeout=None)
        
        for sound_file, rank_and_points in sound_files_with_ranks:
            self.add_item(SoundboardButton(sound_file, *rank_and_points, user_ranks, sound_emojis))

        if sound_files_with_ranks:  # Wenn es Sound-Dateien gibt, dann haben wir Suchergebnisse
            refresh_button = RefreshButton(label="Zurücksetzen", style=discord.ButtonStyle.grey, custom_id="refresh_button")
            self.add_item(refresh_button)
@bot.event
async def on_ready():
    print(f'Angemeldet als {bot.user.name}')





#####  Discord commands  #####




@bot.command(name='soundboard')
async def soundboard(ctx: commands.Context):
    # Überprüfen, ob der Befehl von jemandem in einem Sprachkanal gesendet wurde
        # Ihr bisheriger Code für das Soundboard ...
    # Sende den Suchbutton am Ende des Befehls
    ranks, user_ranks, sound_emojis = load_ranks()

    search_button = SearchButton()
    view = SoundboardView(sound_files_with_ranks=[], user_ranks=user_ranks, sound_emojis=sound_emojis)
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
    views = [SoundboardView(chunk, user_ranks, sound_emojis) for chunk in sound_files_chunks]

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
    ranks, user_ranks, sound_emojis = load_ranks()  # Nutzer-Rangdaten laden

    # Stelle sicher, dass user_ranks keine defaultdict ist, sondern ein normales Dictionary
    if isinstance(user_ranks, collections.defaultdict):
        user_ranks = {k: v for k, v in user_ranks.items()}
        
    # Liste nach EXP sortieren und Klicks mit anzeigen
    sorted_user_ranks = sorted(user_ranks.items(), key=lambda item: (item[1]['level'], item[1]['exp']), reverse=True)
    
    if not sorted_user_ranks:
        await ctx.send("Noch keine Rankings vorhanden.")
        return
    
     # Erstelle die Rangliste für die Nachricht
    rankings_description = []
    for user_id, stats in sorted_user_ranks:
        try:
            exp_to_next_level = LEVEL_UP_EXP - stats['exp']  # EXP benötigt für das nächste Level
            user = await bot.fetch_user(int(user_id))  # Benutzerobjekt mittels ID abrufen

            # Formatiere die Ranking-Eintragung
            ranking_entry = f"{user.display_name}: {stats['exp']} EXP (Noch {exp_to_next_level} bis Level {stats['level'] + 1}), Level: {stats['level']}"
            rankings_description.append(ranking_entry)
        except Exception as e:
            print(f"Ein Fehler trat auf beim Abrufen des Nutzerprofils: {e}")

    # Nachrichtenbeschreibung zusammensetzen
    rankings_description = "\n".join(rankings_description)

    # Erstelle eine Embed-Nachricht für die Anzeige
    embed = discord.Embed(title="User Rankings", description=rankings_description, color=0x00ff00)
    await ctx.send(embed=embed)





async def ping_server(host):
    try:
        # Konstruiere den Ping-Befehl basierend auf dem Betriebssystem
        cmd = ['ping', '-c', '1', '-W', '5', host] if platform.system().lower() != 'windows' else ['ping', '-n', '1', '-w', '5000', host]
        
        # Führe den Ping-Befehl aus
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Warte, bis der Ping-Befehl abgeschlossen ist
        stdout, stderr = await proc.communicate()
        
        # Überprüfe den Rückgabecode des Pings
        return proc.returncode == 0
    except Exception as e:
        print(f"Error during ping: {e}")
        return False


async def run_script_via_ssh(host, port, username, password, command):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(host, port=port, username=username, password=password, timeout=15)
        stdin, stdout, stderr = ssh.exec_command(command)
        return stdout.read().decode('utf-8'), stderr.read().decode('utf-8')
    finally:
        ssh.close()




# Funktion, um die Discord Fehlermeldung zu senden
async def send_unreachable_message(ctx, host):
    embed = discord.Embed(
        title="Serverfehler",
        description=f":red_circle: Der Server {host} ist nicht erreichbar. Bitte überprüfen Sie den Serverstatus.",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)


@bot.command(name='restart')
async def restart(ctx):
    host = "45.93.251.18"
    port = 22
    username = "root"
    password = pw  # Setzen Sie Ihr Passwort sicher
    reboot_command = "sudo reboot"
    
    await ctx.send(f"⚠ Versuche, den Server `{host}` neu zu starten. Bitte warten...")
    _, error = await run_script_via_ssh(host, port, username, password, reboot_command)
    
    if error:
        await ctx.send(f"Fehler beim Ausführen des Neustartbefehls: {error}")
    else:
        await ctx.send(f"🔄 Der Server `{host}` wird neu gestartet. Der Status wird in Kürze überprüft...")
        await asyncio.sleep(15)
        
        for i in range(10):
            if await ping_server(host):
                await ctx.send(f"✅ Der Server `{host}` ist wieder erreichbar.")
                return
            else:
                await asyncio.sleep(30)

        await ctx.send(f"❌ Der Server `{host}` ist nicht innerhalb der erwarteten Zeit erreichbar geworden.")


# Stellen Sie sicher, dass Sie den `startpal`-Befehl anpassen, um die Ping-Überprüfung zu verwenden
@bot.command(name='startpal')
async def startpal(ctx):
    # Setzen Sie hier Ihre SSH Serverdaten ein
    host = "45.93.251.18"
    port = 22
    username = "root"
    password = pw
    command = "cd /home/steam/Steam/steamapps/common/PalServer/ && sudo -u steam ./PalServer.sh"

    # Führe das SSH-Kommando aus, ohne zuvor zu pingen
    try:
        output, error = await run_script_via_ssh(host, port, username, password, command)
        if error:
            error_message = (error[:1900] if len(error) > 1900 else error) + '...(gekürzt)'
            await ctx.send(f"Es gab einen Fehler beim Ausführen des Skripts: ```{error_message}```")
        else:
            await ctx.send(f"Skript wurde erfolgreich auf `{host}` gestartet: ```{output[:1900]}```")  # Output gekürzt, falls zu lang
    except Exception as e:
        await ctx.send("Beim Versuch, den Server zu starten, ist ein unerwarteter Fehler aufgetreten. Bitte überprüfen Sie die Serverkonsole oder kontaktieren Sie den Administrator.")
        print(f"Fehler beim Ausführen von startpal: {e}")








bot.add_cog(ServerStatusMonitor(bot))

bot.run(token)




