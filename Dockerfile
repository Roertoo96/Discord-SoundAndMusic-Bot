FROM python:3.12-slim

# Installiere Systemabhängigkeiten für Audio (ffmpeg, opus etc.) und Ping
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg libopus0 libsodium23 iputils-ping && \
    rm -rf /var/lib/apt/lists/*

# Installiere Python-Bibliotheken für den Bot und das Web-UI
# VENV Warnungen werden in Docker oft ignoriert, wir nutzen das offizielle Python-Image.
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir 'discord.py[voice]' PyNaCl yt-dlp pytube paramiko flask werkzeug

# Setze das Arbeitsverzeichnis
WORKDIR /app

# Kopiere den gesamten Code ins Image (ignoriert Dateien aus .dockerignore)
COPY . /app

# Sicherstellen, dass das Media-Verzeichnis existiert
RUN mkdir -p /app/media
