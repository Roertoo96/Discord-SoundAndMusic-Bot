import discord
from discord.ext import commands
from pytube import YouTube
import os
import asyncio
import yt_dlp


token = os.environ.get('discordmusicbot')


intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.voice_states = True


bot = commands.Bot(command_prefix='!', intents=intents)

ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'postprocessor_args': [
        '-ar', '48000',
        '-ac', '2',
        '-b:a', '64k',
        '-vn',
    ],
    'restrictfilenames': True,
    'noplaylist': True,
}

ffmpeg_options = {
    'options': '-vn'
}

@bot.event
async def on_ready():
    print(f'Bot is ready!')
    if not discord.opus.is_loaded():
        # Versuchen Sie, den korrekten Namen der Bibliothek anzugeben (abhängig von Ihrem System mag dies variieren.)
        opus_lib = '/opt/homebrew/Cellar/opus/1.4/lib/libopus.dylib'
        discord.opus.load_opus(opus_lib)

@bot.command(name='join', help='Tells the bot to join the voice channel')
async def join(ctx):
    if not ctx.message.author.voice:
        await ctx.send("You are not connected to a voice channel.")
        return
    else:
        channel = ctx.message.author.voice.channel
    await channel.connect()

@bot.command(name='leave', help='To make the bot leave the voice channel')
async def leave(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_connected():
        await voice_client.disconnect()
    else:
        await ctx.send("The bot is not connected to a voice channel.")

# YouTube DL Optionen für das Extrahieren der besten Audio-Qualität
ydl_opts = {
    'format': 'bestaudio',
    'noplaylist': True,
    'quiet': True,
    'extract_flat': 'in_playlist'
}

@bot.command(name='play')
async def play(ctx, url):
    if not ctx.author.voice:
        await ctx.send("You are not connected to a voice channel.")
        return

    voice_client = ctx.voice_client
    if voice_client is None:
        channel = ctx.author.voice.channel
        voice_client = await channel.connect()
    elif voice_client.is_playing():
        voice_client.stop()

    # YouTube DL Optionen für das Extrahieren der besten Audio-Qualität in einem Stream
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True, # Nur ein Video abspielen
        'quiet': True # Fehlermeldungen unterdrücken
    }

    # Extract information using yt_dlp
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as e:
            await ctx.send(str(e))
            return

    # URL zum Streamen finden
    audio_url = next((format['url'] for format in info['formats'] if format.get('acodec') != 'none'), None)
    if audio_url is None:
        await ctx.send("Could not retrieve a valid audio source from the provided URL.")
        return

    # Nutzen Sie den FFmpeg AudioQuelle ohne die lokale Dateioptionen
    voice_client.play(discord.FFmpegPCMAudio(audio_url, before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"))

    title = info.get('title', 'No title available')
    await ctx.send(f'Playing: {title}')

@bot.command(name='pause', help='This command pauses the song')
async def pause(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        voice_client.pause()
    else:
        await ctx.send("Currently no audio is playing.")

@bot.command(name='resume', help='Resumes the song')
async def resume(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_paused():
        voice_client.resume()
    else:
        await ctx.send("The audio is not paused.")

@bot.command(name='stop', help='Stops the song')
async def stop(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        voice_client.stop()
    else:
        await ctx.send("Currently no audio is playing.")


bot.run(token)