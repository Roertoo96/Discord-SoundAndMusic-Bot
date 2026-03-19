import json
import os
import platform
import asyncio
import collections
from typing import Optional
import warnings
import tracemalloc
import time
import subprocess  # für FFmpeg stderr DEVNULL

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, TextInput

import aiohttp
import paramiko

from checkos import perform_os_specific_action
from ranking import load_ranks, save_ranks

############################################
# Konfiguration & Konstanten
############################################

# Media-Pfad & Fallback-Token
MEDIA_BASE, token_from_checkos = perform_os_specific_action()
TOKEN = os.getenv("discordbot")
if not TOKEN:
    p1 = os.getenv("discordbot_p1", "")
    p2 = os.getenv("discordbot_p2", "")
    if p1 and p2:
        TOKEN = p1 + p2
    else:
        TOKEN = token_from_checkos

MAX_BUTTONS_PER_MESSAGE = 20
OPUS_LIB_PATH = "/opt/homebrew/lib/libopus.dylib"          # macOS
LINUX_OPUS_PATH = "/usr/lib/x86_64-linux-gnu/libopus.so.0" # Debian/Ubuntu
LEVEL_UP_EXP = 100
EMPTY_VOICE_RESTART_TIMEOUT = 30 * 60

SSH_HOST = "45.93.251.18"
SSH_PORT = 22
SSH_USER = "root"
SSH_PASSWORD = os.environ.get("pav")  # Passwort via ENV setzen!
RESTART_NOTIFY_CHANNEL_ID = 1174617198191444058
RESTART_REQUEST_FILE = os.path.join(MEDIA_BASE, "restart_request.txt")
RESTART_NOTICE_FILE = os.path.join(MEDIA_BASE, "restart_notice.txt")

# Discord Intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.voice_states = True

# Globale Ranks / Emojis beim Start laden
ranks, user_ranks, sound_emojis = load_ranks()
if isinstance(user_ranks, collections.defaultdict):
    user_ranks = {k: v for k, v in user_ranks.items()}

############################################
# Hilfsfunktionen
############################################

async def ping_server(host: str) -> bool:
    try:
        cmd = ["ping", "-c", "1", "-W", "5", host] if platform.system().lower() != "windows" else [
            "ping", "-n", "1", "-w", "5000", host
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return proc.returncode == 0
    except Exception as e:
        print(f"Error during ping: {e}")
        return False


async def run_script_via_ssh(host: str, port: int, username: str, password: str, command: str):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(host, port=port, username=username, password=password, timeout=15)
        stdin, stdout, stderr = ssh.exec_command(command)
        return stdout.read().decode("utf-8"), stderr.read().decode("utf-8")
    finally:
        ssh.close()

def write_restart_notice(source: str):
    with open(RESTART_NOTICE_FILE, "w", encoding="utf-8") as f:
        f.write(source.strip() or "Unbekannt")

def request_bot_restart(source: str):
    write_restart_notice(source)
    with open(RESTART_REQUEST_FILE, "w", encoding="utf-8") as f:
        f.write(source.strip() or "Unbekannt")

async def get_restart_notification_channel():
    channel = bot.get_channel(RESTART_NOTIFY_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(RESTART_NOTIFY_CHANNEL_ID)
        except Exception as e:
            print("Restart notification channel fetch error:", e)
            return None
    return channel

async def send_restart_notification():
    if not os.path.exists(RESTART_NOTICE_FILE):
        return

    source = "Unbekannt"
    try:
        with open(RESTART_NOTICE_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                source = content
    except Exception as e:
        print("Restart notice read error:", e)

    channel = await get_restart_notification_channel()
    if channel is None:
        return

    try:
        await channel.send(f"PROST_Bot wurde neu gestartet. Ausgeloest durch: {source}")
        os.remove(RESTART_NOTICE_FILE)
    except Exception as e:
        print("Restart notification send error:", e)

def get_human_members_in_channel(channel: Optional[discord.abc.GuildChannel]):
    if channel is None or not hasattr(channel, "members"):
        return []
    return [member for member in channel.members if not member.bot]

async def perform_bot_restart(source: str):
    write_restart_notice(source)
    channel = await get_restart_notification_channel()
    if channel is not None:
        try:
            await channel.send(f"PROST_Bot wird jetzt neu gestartet. Ausgeloest durch: {source}")
        except Exception as e:
            print("Restart pending notification send error:", e)
    print(f"Restart request received from {source}. Shutting down bot for Docker restart.")
    await bot.close()

# FFmpeg-Quelle für LOKALE Dateien (vermeidet ResourceWarnings)
def make_ffmpeg_source_local(path: str) -> discord.FFmpegPCMAudio:
    return discord.FFmpegPCMAudio(
        path,
        before_options='-nostdin',
        options='-vn'
    )

# --- Keep-Alive: endlose Stille via ffmpeg lavfi ---
def make_silence_source() -> discord.FFmpegPCMAudio:
    # anullsrc erzeugt Stille (48kHz, Stereo)
    return discord.FFmpegPCMAudio(
        source="anullsrc=r=48000:cl=stereo",
        before_options="-nostdin -f lavfi -i",
        options="-vn -ac 2 -ar 48000"
    )

async def ensure_keepalive(vc: discord.VoiceClient):
    """Startet Stille, wenn nichts spielt – hält die Voice-Verbindung stabil."""
    if vc is None:
        return
    try:
        if vc.is_playing() or vc.is_paused():
            return
    except Exception:
        pass
    try:
        prev = getattr(vc, "source", None)
        if prev and hasattr(prev, "cleanup"):
            prev.cleanup()
    except Exception:
        pass
    silent = make_silence_source()

    def _after(_err: Optional[Exception]):
        try:
            if hasattr(silent, "cleanup"):
                silent.cleanup()
        except Exception:
            pass

    try:
        vc.play(silent, after=_after)
    except discord.ClientException:
        # Wenn gleichzeitig etwas anderes startet, ignorieren
        pass

############################################
# Server Status Monitor
############################################

class ServerStatusMonitor(commands.Cog):
    def __init__(self, bot: commands.Bot, channel_id: int):
        self.bot = bot
        self.channel_id = channel_id
        self.server_status: Optional[bool] = None
        self.server_monitor.start()

    @tasks.loop(seconds=30)
    async def server_monitor(self):
        current_status = await ping_server(SSH_HOST)
        if self.server_status is None or self.server_status != current_status:
            self.server_status = current_status
            message = ":green_circle: Server ist online." if current_status else ":red_circle: Server ist offline."
            channel = self.bot.get_channel(self.channel_id)
            if channel:
                await channel.send(message)

    @server_monitor.before_loop
    async def before_server_monitor(self):
        await self.bot.wait_until_ready()

############################################
# Opus laden (macOS oder Linux)
############################################

if not discord.opus.is_loaded():
    loaded = False
    if os.path.exists(OPUS_LIB_PATH):
        try:
            discord.opus.load_opus(OPUS_LIB_PATH)
            print("Opus-Bibliothek erfolgreich geladen (macOS).")
            loaded = True
        except Exception as e:
            print(f"Opus konnte nicht von macOS-Pfad geladen werden: {e}")
    if not loaded and os.path.exists(LINUX_OPUS_PATH):
        try:
            discord.opus.load_opus(LINUX_OPUS_PATH)
            print("Opus-Bibliothek erfolgreich geladen (Linux).")
            loaded = True
        except Exception as e:
            print(f"Opus konnte nicht von Linux-Pfad geladen werden: {e}")
    if not loaded:
        print("Hinweis: Opus wurde nicht geladen. Installiere libopus (z. B. apt-get install -y libopus0).")
else:
    print("Opus ist bereits geladen.")

# Kosmetische ResourceWarnings aus dem player unterdrücken
warnings.filterwarnings("ignore", category=ResourceWarning, module="discord.player")

############################################
# UI-Komponenten
############################################




class RefreshButton(Button):
    def __init__(self):
        super().__init__(label="Zurücksetzen", style=discord.ButtonStyle.grey, custom_id="refresh_button")

    async def callback(self, interaction: discord.Interaction):
        view = SoundboardView([], user_ranks, sound_emojis)
        await interaction.response.edit_message(view=view)


class SoundboardButton(Button):
    def __init__(self, sound_file, rank, points, user_ranks_map, sound_emoji_map):
        label_base = os.path.splitext(sound_file)[0]
        emoji = sound_emoji_map.get(label_base)
        
        full_label = f"{rank}. {label_base} ({points})"
        if len(full_label) > 80:
            allowed_len = 80 - len(f"{rank}.  ({points})") - 3
            display_label = label_base[:allowed_len] + "..."
            full_label = f"{rank}. {display_label} ({points})"
            
        super().__init__(label=full_label, emoji=emoji)
        self.sound_file = sound_file
        self.user_ranks_map = user_ranks_map

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        vc = interaction.guild.voice_client
        if vc is None:
            vc = discord.utils.get(bot.voice_clients, guild=interaction.guild)

        # Wenn bereits verbunden -> sofort abspielen
        if vc and getattr(vc, "channel", None):
            try:
                # ggf. laufende Quelle/Keep-Alive stoppen & aufräumen
                try:
                    if vc.is_playing():
                        vc.stop()
                except Exception:
                    pass
                try:
                    prev = getattr(vc, "source", None)
                    if prev and hasattr(prev, "cleanup"):
                        prev.cleanup()
                except Exception:
                    pass

                audio_path = os.path.join(MEDIA_BASE, self.sound_file)
                source = make_ffmpeg_source_local(audio_path)

                def _after(err: Optional[Exception], _vc=vc, _source=source):
                    try:
                        if hasattr(_source, "cleanup"):
                            _source.cleanup()
                    except Exception:
                        pass
                    if err:
                        print("FFmpeg/Player error:", err)
                    # nach Track-Ende wieder Keep-Alive starten
                    try:
                        asyncio.get_running_loop().create_task(ensure_keepalive(_vc))
                    except Exception:
                        pass

                vc.play(source, after=_after)

                # letzten Channel merken
                bot._last_vc_channel = getattr(bot, "_last_vc_channel", {})
                bot._last_vc_channel[interaction.guild.id] = vc.channel.id

                # XP & Klicks
                uid = str(interaction.user.id)
                data = self.user_ranks_map.get(uid, {"exp": 0, "level": 1})
                data["exp"] += 10
                if data["exp"] >= LEVEL_UP_EXP:
                    data["level"] += 1
                    data["exp"] -= LEVEL_UP_EXP
                self.user_ranks_map[uid] = data

                label = os.path.splitext(self.sound_file)[0]
                ranks[label] = ranks.get(label, 0) + 1
                save_ranks(ranks, self.user_ranks_map, sound_emojis)
                return
            except Exception as e:
                await interaction.followup.send(f"Abspiel-Fehler: {e}", ephemeral=True)
                return

        # nicht verbunden: Ziel ermitteln (letzter Channel oder User-Channel)
        target_channel = None
        last_map = getattr(bot, "_last_vc_channel", {})
        chan_id = last_map.get(interaction.guild.id)
        if chan_id:
            target_channel = interaction.guild.get_channel(chan_id)
        if target_channel is None:
            user_voice = getattr(interaction.user, "voice", None)
            if user_voice and user_voice.channel:
                target_channel = user_voice.channel
        if target_channel is None:
            await interaction.followup.send(
                "Kein Ziel-Sprachkanal gefunden (Bot ist nicht verbunden und kein letzter/aktueller Voice vorhanden).",
                ephemeral=True
            )
            return

        try:
            if vc is None:
                vc = await target_channel.connect()
            else:
                await vc.move_to(target_channel)
            bot._voice_join_ts[interaction.guild.id] = time.monotonic()
            bot._last_vc_channel = getattr(bot, "_last_vc_channel", {})
            bot._last_vc_channel[interaction.guild.id] = target_channel.id
            # direkt nach Join Keep-Alive starten
            await ensure_keepalive(vc)
        except Exception as e:
            await interaction.followup.send(f"Voice-Connect fehlgeschlagen: {e}", ephemeral=True)
            return

        # jetzt echten Sound spielen (Keep-Alive vorher stoppen)
        try:
            try:
                if vc.is_playing():
                    vc.stop()
            except Exception:
                pass
            try:
                prev = getattr(vc, "source", None)
                if prev and hasattr(prev, "cleanup"):
                    prev.cleanup()
            except Exception:
                pass

            audio_path = os.path.join(MEDIA_BASE, self.sound_file)
            source = make_ffmpeg_source_local(audio_path)

            def _after(err: Optional[Exception], _vc=vc, _source=source):
                try:
                    if hasattr(_source, "cleanup"):
                        _source.cleanup()
                except Exception:
                    pass
                if err:
                    print("FFmpeg/Player error:", err)
                # nach Track-Ende wieder Keep-Alive starten
                try:
                    asyncio.get_running_loop().create_task(ensure_keepalive(_vc))
                except Exception:
                    pass

            vc.play(source, after=_after)

            uid = str(interaction.user.id)
            data = self.user_ranks_map.get(uid, {"exp": 0, "level": 1})
            data["exp"] += 10
            if data["exp"] >= LEVEL_UP_EXP:
                data["level"] += 1
                data["exp"] -= LEVEL_UP_EXP
            self.user_ranks_map[uid] = data

            label = os.path.splitext(self.sound_file)[0]
            ranks[label] = ranks.get(label, 0) + 1
            save_ranks(ranks, self.user_ranks_map, sound_emojis)
        except Exception as e:
            await interaction.followup.send(f"Abspiel-Fehler: {e}", ephemeral=True)


class SoundboardView(View):
    def __init__(self, sound_files_with_ranks, user_ranks_map, sound_emoji_map):
        super().__init__(timeout=None)
        for sound_file, rank_and_points in sound_files_with_ranks:
            self.add_item(SoundboardButton(sound_file, *rank_and_points, user_ranks_map, sound_emoji_map))
        if sound_files_with_ranks:
            self.add_item(RefreshButton())

############################################
# Categories (Ordner) & Views
############################################

def get_sounds_categorized():
    meta_path = "./media/metadata.json"
    files = [f for f in os.listdir("./media") if f.lower().endswith((".mp3", ".wav"))]
    try:
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
    except:
        meta = {"categories": ["Aktuelle Sounds", "Archiv", "Best of"], "sounds": {}}
        
    categories_map = {c: [] for c in meta.get("categories", [])}
    categories_map["Uncategorized"] = []
    
    for f in files:
        data = meta.get("sounds", {}).get(f, {})
        cat = data.get("category", "Aktuelle Sounds")
        if cat not in categories_map:
            cat = "Aktuelle Sounds"
            if cat not in categories_map:
                categories_map[cat] = []
        categories_map[cat].append({"file": f, "order": data.get("order", 999)})
        
    for cat in categories_map:
        categories_map[cat].sort(key=lambda x: (x["order"], x["file"]))
        
    return categories_map

class CategoryFolderButton(Button):
    def __init__(self, category_name, items):
        super().__init__(label=f"📁 {category_name} ({len(items)})", style=discord.ButtonStyle.secondary)
        self.category_name = category_name
        self.items = items
        
    async def callback(self, interaction: discord.Interaction):
        sound_files_with_ranks = []
        for idx, item in enumerate(self.items, start=1):
            sf = item["file"]
            pts = ranks.get(os.path.splitext(sf)[0], 0)
            sound_files_with_ranks.append((sf, (idx, pts)))
            
        chunks = [sound_files_with_ranks[i:i + MAX_BUTTONS_PER_MESSAGE] for i in range(0, len(sound_files_with_ranks), MAX_BUTTONS_PER_MESSAGE)]
        
        await interaction.response.send_message(f"📂 **{self.category_name}**:", ephemeral=True)
        for chunk in chunks:
            await interaction.followup.send("\u200b", view=SoundboardView(chunk, user_ranks, sound_emojis), ephemeral=True)

class CategoryFolderView(View):
    def __init__(self, categories_map):
        super().__init__(timeout=None)
        for cat, items in categories_map.items():
            if not items and cat == "Uncategorized": continue
            self.add_item(CategoryFolderButton(cat, items))

############################################
# Web UI Watcher
############################################

@tasks.loop(seconds=0.25)
async def web_ui_watcher():
    req_file = os.path.join(MEDIA_BASE, "play_request.txt")
    restart_file = RESTART_REQUEST_FILE
    if os.path.exists(restart_file):
        restart_source = "Web UI"
        try:
            with open(restart_file, "r", encoding="utf-8") as f:
                restart_source = f.read().strip() or restart_source
        except Exception as e:
            print("Restart Request Read Error:", e)
        try:
            os.remove(restart_file)
        except Exception as e:
            print("Restart Request Cleanup Error:", e)
        await perform_bot_restart(restart_source)
        return
    if os.path.exists(req_file):
        try:
            with open(req_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            os.remove(req_file)
            for line in lines:
                filename = line.strip()
                if not filename: continue
                # We play on the first active guild
                played = False
                for guild_id, chan_id in getattr(bot, "_last_vc_channel", {}).items():
                    guild = bot.get_guild(guild_id)
                    if not guild: continue
                    target_channel = guild.get_channel(chan_id)
                    if not target_channel: continue
                    vc = guild.voice_client
                    if vc is None:
                        try:
                            vc = await target_channel.connect()
                        except:
                            continue
                    try:
                        if vc.is_playing():
                            vc.stop()
                        audio_path = os.path.join(MEDIA_BASE, filename)
                        if not os.path.exists(audio_path): continue
                        source = make_ffmpeg_source_local(audio_path)
                        def _after(err: Optional[Exception], _vc=vc, _source=source):
                            try:
                                if hasattr(_source, "cleanup"): _source.cleanup()
                            except: pass
                            try:
                                asyncio.get_running_loop().create_task(ensure_keepalive(_vc))
                            except: pass
                        vc.play(source, after=_after)
                        played = True
                    except Exception as e:
                        print("Web Play Error:", e)
                    if played:
                        break
        except Exception as e:
            print("Web UI Watcher Error:", e)

@web_ui_watcher.before_loop
async def before_web_ui_watcher():
    await bot.wait_until_ready()

@tasks.loop(seconds=30)
async def empty_voice_restart_watcher():
    for vc in list(bot.voice_clients):
        guild = getattr(vc, "guild", None)
        if guild is None:
            continue

        channel = getattr(vc, "channel", None)
        if channel is None:
            bot._empty_voice_since.pop(guild.id, None)
            continue

        human_members = get_human_members_in_channel(channel)
        if human_members:
            bot._empty_voice_since.pop(guild.id, None)
            continue

        empty_since = bot._empty_voice_since.get(guild.id)
        if empty_since is None:
            bot._empty_voice_since[guild.id] = time.monotonic()
            continue

        if time.monotonic() - empty_since >= EMPTY_VOICE_RESTART_TIMEOUT:
            bot._empty_voice_since.pop(guild.id, None)
            await perform_bot_restart(f"Voice-Timeout nach 30 Minuten ohne Nutzer in {channel.name}")
            return

@empty_voice_restart_watcher.before_loop
async def before_empty_voice_restart_watcher():
    await bot.wait_until_ready()

############################################
# Bot-Klasse & Instanz
############################################

class SoundBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._voice_join_ts = {}
        self._empty_voice_since = {}
        self._last_vc_channel: dict = {}
        self.http_session: Optional[aiohttp.ClientSession] = None

    async def setup_hook(self):
        connector = aiohttp.TCPConnector(limit=20, force_close=True)
        self.http_session = aiohttp.ClientSession(connector=connector)
        await self.add_cog(ServerStatusMonitor(self, channel_id=1200120616230076496))
        await self.tree.sync()
        web_ui_watcher.start()
        empty_voice_restart_watcher.start()

    async def close(self):
        try:
            for vc in list(self.voice_clients):
                try:
                    await vc.disconnect(force=True)
                except Exception as e:
                    print("Voice disconnect error on shutdown:", e)
            if self.http_session and not self.http_session.closed:
                await self.http_session.close()
        finally:
            await super().close()

bot = SoundBot(command_prefix="!", help_command=None, intents=intents)

############################################
# Events
############################################

@bot.event
async def on_ready():
    print(f"Angemeldet als {bot.user.name}")
    await send_restart_notification()

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if member.id == bot.user.id:
        print("[VOICE]", f"before={getattr(before.channel, 'name', None)}", f"after={getattr(after.channel, 'name', None)}")
        if after.channel is not None:
            if get_human_members_in_channel(after.channel):
                bot._empty_voice_since.pop(member.guild.id, None)
            else:
                bot._empty_voice_since[member.guild.id] = time.monotonic()
        else:
            bot._empty_voice_since.pop(member.guild.id, None)
        return

    guild = member.guild
    vc = guild.voice_client
    if vc is None or vc.channel is None:
        bot._empty_voice_since.pop(guild.id, None)
        return

    if get_human_members_in_channel(vc.channel):
        bot._empty_voice_since.pop(guild.id, None)
    else:
        bot._empty_voice_since[guild.id] = time.monotonic()

# Optional: CommandNotFound leise ignorieren (verhindert Logspam)
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    raise error

############################################
# Commands
############################################

@bot.command(name="soundboard")
async def soundboard_cmd(ctx: commands.Context):
    if ctx.author.voice is None:
        await ctx.send("Du musst in einem Sprachkanal sein, um das Soundboard zu verwenden.")
        return

    vc = ctx.voice_client
    try:
        target_channel = ctx.author.voice.channel
        if vc is None:
            vc = await target_channel.connect()
        elif vc.channel != target_channel:
            await vc.move_to(target_channel)

        bot._voice_join_ts[ctx.guild.id] = time.monotonic()
        bot._last_vc_channel[ctx.guild.id] = target_channel.id

        # Direkt nach Join Keep-Alive starten
        await ensure_keepalive(vc)

    except Exception as e:
        await ctx.send(f"Voice-Connect fehlgeschlagen: {e}")
        return

    categories_map = get_sounds_categorized()
    view = CategoryFolderView(categories_map)
    await ctx.send("📂 Klicke auf einen Ordner, um Sounds abzuspielen, oder nutze die Suche:", view=view)


@bot.command(name="setemoji")
async def setemoji(ctx: commands.Context, sound_name: str, emoji: str):
    file_mp3 = os.path.join("./media", f"{sound_name}.mp3")
    file_wav = os.path.join("./media", f"{sound_name}.wav")
    if not (os.path.exists(file_mp3) or os.path.exists(file_wav)):
        await ctx.send("Sound nicht gefunden.")
        return
    sound_emojis[sound_name] = emoji
    save_ranks(ranks, user_ranks, sound_emojis)
    await ctx.send(f"Emoji für {sound_name} gesetzt zu {emoji}")


@bot.command(name="upload", help="Lade eine MP3/WAV-Datei hoch. !upload (mit Anhang)")
async def upload(ctx: commands.Context):
    if not ctx.message.attachments:
        await ctx.send("Keine Anhänge gefunden.")
        return

    session = getattr(bot, 'http_session', None)
    if session is None:
        await ctx.send("Interner Fehler: HTTP-Session fehlt.")
        return

    os.makedirs("media", exist_ok=True)

    for attachment in ctx.message.attachments:
        if not attachment.filename.lower().endswith((".mp3", ".wav")):
            continue
        target_path = os.path.join("media", attachment.filename)
        try:
            async with session.get(attachment.url) as resp:
                resp.raise_for_status()
                data = await resp.read()
            with open(target_path, "wb") as f:
                f.write(data)
            await ctx.send(f'Datei "{attachment.filename}" gespeichert.')
        except Exception as e:
            await ctx.send(f"Fehler beim Herunterladen der Datei {attachment.filename}: {e}")


@bot.command(name="delete", help="Lösche eine Datei. !delete dateiname.mp3|wav")
@commands.has_permissions(manage_messages=True)
async def delete_cmd(ctx: commands.Context, *, file_name: str):
    file_path = os.path.join(os.getcwd(), "media", file_name)
    if os.path.exists(file_path) and file_path.lower().endswith((".mp3", ".wav")):
        os.remove(file_path)
        await ctx.send(f'Datei "{file_name}" wurde erfolgreich gelöscht.')
    else:
        await ctx.send(f'Datei "{file_name}" nicht gefunden oder Dateityp nicht zulässig.')


@bot.command(name="list")
async def list_files(ctx: commands.Context):
    base = "./media"
    files = os.listdir(base) if os.path.exists(base) else []
    audio_files = [f for f in files if f.lower().endswith((".mp3", ".wav"))]

    msg = "Verfügbare Dateien:\n" + "\n".join(audio_files) if audio_files else "Keine Dateien gefunden."
    await ctx.send(msg)


@bot.command(name="help")
async def help_command(ctx: commands.Context):
    embed = discord.Embed(title="Hilfe", description="Liste aller verfügbaren Befehle", color=0x00FF00)
    embed.add_field(name="Befehl", value="`!help`\n`!upload`\n`!delete`\n`!list`\n`!soundboard`\n`!search`\n`!setemoji`\n`!rankings`\n`!restart`\n`!startpal`", inline=True)
    embed.add_field(name="Beschreibung", value=(
        "Zeigt diese Hilfe an\n"
        "Lädt eine MP3/WAV hoch\n"
        "Löscht eine Datei\n"
        "Listet Dateien\n"
        "Öffnet das Soundboard\n"
        "Suche nach Sounds im Chat\n"
        "Setzt Emoji für Sound\n"
        "Zeigt User-Rankings\n"
        "Rebootet Server per SSH\n"
        "Startet PalServer per SSH"
    ), inline=True)
    await ctx.send(embed=embed)


@bot.command(name="search", help="Suche nach Sounds direkt im Chat. Beispiel: !search hallo")
async def search_cmd(ctx: commands.Context, *, query: str):
    if ctx.author.voice is None:
        await ctx.send("Du solltest in einem Sprachkanal sein, um Sounds abzuspielen.")
    
    query = query.strip().lower()
    if not os.path.exists("./media"):
        await ctx.send("Keine Sounds vorhanden.")
        return
        
    all_files = [f for f in os.listdir("./media") if f.lower().endswith((".mp3", ".wav"))]
    sorted_files = sorted(all_files, key=lambda sf: ranks.get(os.path.splitext(sf)[0], 0), reverse=True)
    search_results = [
        (sf, (idx, ranks.get(os.path.splitext(sf)[0], 0)))
        for idx, sf in enumerate(sorted_files, start=1)
        if query in os.path.splitext(sf)[0].lower()
    ]
    
    if not search_results:
        await ctx.send(f"Es wurden keine passenden Sounds für **{query}** gefunden.")
    else:
        chunks = [search_results[i:i + MAX_BUTTONS_PER_MESSAGE] for i in range(0, len(search_results), MAX_BUTTONS_PER_MESSAGE)]
        await ctx.send(f"Suchergebnisse für **{query}**:")
        for chunk in chunks:
            await ctx.send(view=SoundboardView(chunk, user_ranks, sound_emojis))


@bot.command(name="rankings")
async def send_rankings(ctx: commands.Context):
    _ranks, _user_ranks, _sound_emojis = load_ranks()
    if isinstance(_user_ranks, collections.defaultdict):
        _user_ranks = {k: v for k, v in _user_ranks.items()}
    sorted_user_ranks = sorted(_user_ranks.items(), key=lambda item: (item[1]['level'], item[1]['exp']), reverse=True)
    if not sorted_user_ranks:
        await ctx.send("Noch keine Rankings vorhanden.")
        return
    lines = []
    for user_id, stats in sorted_user_ranks:
        try:
            user = await bot.fetch_user(int(user_id))
            exp_to_next = LEVEL_UP_EXP - stats['exp']
            lines.append(f"{user.display_name}: {stats['exp']} EXP (Noch {exp_to_next} bis Level {stats['level'] + 1}), Level: {stats['level']}")
        except Exception as e:
            print(f"Profilabruf-Fehler: {e}")
    embed = discord.Embed(title="User Rankings", description="\n".join(lines), color=0x00FF00)
    await ctx.send(embed=embed)


@bot.command(name="restart")
async def restart_cmd(ctx: commands.Context):
    await ctx.send(f"⚠ Versuche, den Server `{SSH_HOST}` neu zu starten. Bitte warten…")
    _, error = await run_script_via_ssh(SSH_HOST, SSH_PORT, SSH_USER, SSH_PASSWORD, "sudo reboot")
    if error:
        await ctx.send(f"Fehler beim Ausführen des Neustartbefehls: {error}")
        return
    await ctx.send(f"🔄 Der Server `{SSH_HOST}` wird neu gestartet. Der Status wird in Kürze überprüft…")
    await asyncio.sleep(15)
    for _ in range(10):
        if await ping_server(SSH_HOST):
            await ctx.send(f"✅ Der Server `{SSH_HOST}` ist wieder erreichbar.")
            return
        await asyncio.sleep(30)
    await ctx.send(f"❌ Der Server `{SSH_HOST}` ist nicht innerhalb der erwarteten Zeit erreichbar geworden.")


@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
@bot.tree.command(name="restart", description="Startet den Discord-Bot neu.")
async def restart_slash(interaction: discord.Interaction):
    source = f"/restart von {interaction.user.display_name}"
    await interaction.response.send_message("Bot-Neustart wird ausgefuehrt.", ephemeral=True)
    request_bot_restart(source)


@bot.command(name="startpal")
async def startpal(ctx: commands.Context):
    command = "cd /home/steam/Steam/steamapps/common/PalServer/ && sudo -u steam ./PalServer.sh"
    try:
        output, error = await run_script_via_ssh(SSH_HOST, SSH_PORT, SSH_USER, SSH_PASSWORD, command)
        if error:
            error_message = (error[:1900] + "…(gekürzt)") if len(error) > 1900 else error
            await ctx.send(f"Es gab einen Fehler beim Ausführen des Skripts: ```{error_message}```")
        else:
            safe_out = (output[:1900] + "…") if len(output) > 1900 else output
            await ctx.send(f"Skript wurde erfolgreich auf `{SSH_HOST}` gestartet: ```{safe_out}```")
    except Exception as e:
        await ctx.send("Beim Versuch, den Server zu starten, ist ein unerwarteter Fehler aufgetreten. Bitte Serverkonsole prüfen.")
        print(f"Fehler beim Ausführen von startpal: {e}")

# Extra Utilities
@bot.command(name="leave")
async def leave(ctx: commands.Context):
    vc = ctx.voice_client
    if vc and getattr(vc, "channel", None):
        await vc.disconnect(force=True)
        await ctx.send("✅ Voice getrennt.")
    else:
        await ctx.send("Ich bin in keinem Voice-Channel.")

@bot.command(name="summon")
async def summon(ctx: commands.Context):
    if not ctx.author.voice:
        return await ctx.send("Geh bitte zuerst in einen Voice-Channel.")
    vc = ctx.voice_client
    if vc is None:
        vc = await ctx.author.voice.channel.connect(reconnect=False)
    else:
        await vc.move_to(ctx.author.voice.channel)
    # nach summon auch Keep-Alive starten
    await ensure_keepalive(vc)
    await ctx.send("✅ Voice verbunden.")

############################################
# Start
############################################

if __name__ == "__main__":
    warnings.simplefilter("default", ResourceWarning)
    tracemalloc.start()
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        pass
