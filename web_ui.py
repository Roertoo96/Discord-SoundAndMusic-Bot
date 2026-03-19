import os
import json
import subprocess
import time
from flask import Flask, request, render_template_string, redirect, url_for, flash, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "super_secret_discord_web_ui_key"

MEDIA_FOLDER = './media'
METADATA_FILE = os.path.join(MEDIA_FOLDER, 'metadata.json')
os.makedirs(MEDIA_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {'mp3', 'wav'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_metadata():
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "categories" not in data:
                    data["categories"] = ["Aktuelle Sounds", "Archiv", "Best of"]
                if "sounds" not in data:
                    data["sounds"] = {}
                return data
        except:
            pass
    return {"categories": ["Aktuelle Sounds", "Archiv", "Best of"], "sounds": {}}

def save_metadata(data):
    with open(METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def get_existing_files():
    if not os.path.exists(MEDIA_FOLDER):
        return set()
    return {f for f in os.listdir(MEDIA_FOLDER) if f.lower().endswith(('.mp3', '.wav'))}

def request_bot_restart(source='Web UI'):
    with open(os.path.join(MEDIA_FOLDER, 'restart_request.txt'), 'w', encoding='utf-8') as f:
        f.write(source)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Discord Soundboard Manager</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: rgba(30, 41, 59, 0.7);
            --text-color: #f8fafc;
            --accent: #3b82f6;
            --accent-hover: #2563eb;
            --danger: #ef4444;
            --danger-hover: #dc2626;
        }
        
        * { box-sizing: border-box; margin: 0; padding: 0; }
        
        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(at 0% 0%, hsla(253,16%,7%,1) 0, transparent 50%), 
                radial-gradient(at 50% 0%, hsla(225,39%,30%,1) 0, transparent 50%), 
                radial-gradient(at 100% 0%, hsla(339,49%,30%,1) 0, transparent 50%);
            color: var(--text-color);
            min-height: 100vh;
            padding: 2rem;
        }

        .container {
            max-width: 1000px;
            margin: 0 auto;
        }

        header {
            text-align: center;
            margin-bottom: 2rem;
        }
        h1 {
            font-size: 3rem;
            font-weight: 800;
            background: linear-gradient(to right, #60a5fa, #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        p.subtitle { color: #94a3b8; font-size: 1.1rem; }

        .glass-panel {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 2rem;
            margin-bottom: 2rem;
        }

        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.5rem 1rem;
            font-weight: 600;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            transition: all 0.2s ease;
            text-decoration: none;
            font-size: 0.9rem;
        }
        .btn-primary { background-color: var(--accent); color: white; }
        .btn-primary:hover { background-color: var(--accent-hover); }
        .btn-danger { background-color: var(--danger); color: white; }
        .btn-danger:hover { background-color: var(--danger-hover); }
        .btn-secondary { background-color: #475569; color: white; }
        .btn-secondary:hover { background-color: #334155; }

        .upload-form {
            display: flex; gap: 1rem; align-items: center;
        }

        .category-section {
            margin-bottom: 3rem;
        }
        .category-header {
            font-size: 1.8rem;
            margin-bottom: 1rem;
            border-bottom: 2px solid rgba(255,255,255,0.1);
            padding-bottom: 0.5rem;
            color: #e2e8f0;
        }

        .sound-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 1.5rem;
        }

        .sound-card {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            padding: 1.25rem;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }

        .sound-title {
            font-size: 1.1rem;
            font-weight: 600;
            color: #e2e8f0;
            word-break: break-all;
        }

        audio { width: 100%; height: 36px; border-radius: 18px; }

        .controls {
            display: flex; gap: 0.5rem; justify-content: space-between; align-items: center; flex-wrap: wrap; margin-top: 0.5rem;
        }
        
        .cat-select {
            background: #1e293b; color: white; border: 1px solid rgba(255,255,255,0.2);
            padding: 0.4rem; border-radius: 6px; outline: none; flex-grow: 1;
        }
        
        .order-buttons form { display: inline-block; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Soundboard Manager</h1>
            <p class="subtitle">Verwalte deine Sounds, Ordner (Kategorien) und Reihenfolge</p>
            <input type="text" id="searchInput" placeholder="Suche nach Sounds..." style="width: 100%; max-width: 600px; margin-top: 1.5rem; padding: 0.8rem 1.2rem; border-radius: 8px; border: 1px solid rgba(255,255,255,0.2); background: rgba(30, 41, 59, 0.8); color: white; font-size: 1.1rem; outline: none; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
        </header>

        {% with messages = get_flashed_messages() %}
            {% if messages %}
                <div style="margin-bottom: 1.5rem;">
                    {% for message in messages %}
                        <div style="padding: 1rem; background: rgba(59,130,246,0.2); border: 1px solid var(--accent); border-radius: 8px;">{{ message }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}

        <div class="glass-panel" style="display: flex; gap: 2rem; flex-wrap: wrap;">
            <div style="flex: 1; min-width: 300px;">
                <h2>Neuen Sound hochladen</h2>
                <form action="{{ url_for('upload_file') }}" method="post" enctype="multipart/form-data" class="upload-form" style="margin-top: 1rem;">
                    <input type="file" name="file" accept=".mp3,.wav" style="color: white; width: 100%;">
                    <select name="category" class="cat-select" style="max-width: 200px;">
                        {% for cat in categories %}
                            <option value="{{ cat }}">{{ cat }}</option>
                        {% endfor %}
                    </select>
                    <button type="submit" class="btn btn-primary">Hochladen</button>
                </form>
            </div>
            <div style="flex: 1; min-width: 300px; border-left: 1px solid rgba(255,255,255,0.1); padding-left: 2rem;">
                <h2>Neuen Ordner erstellen</h2>
                <form action="{{ url_for('create_category') }}" method="post" class="upload-form" style="margin-top: 1rem;">
                    <input type="text" name="new_category" class="cat-select" placeholder="Ordnername..." required style="flex-grow: 1;">
                    <button type="submit" class="btn btn-primary">Erstellen</button>
                </form>
            </div>
            <div style="flex: 1; min-width: 300px; border-left: 1px solid rgba(255,255,255,0.1); padding-left: 2rem;">
                <h2>Bot steuern</h2>
                <form action="{{ url_for('restart_bot') }}" method="post" style="margin-top: 1rem;" onsubmit="return confirm('Bot wirklich neu starten?');">
                    <button type="submit" class="btn btn-danger">Bot neu starten</button>
                </form>
                <p style="margin-top: 0.75rem; color: #94a3b8; font-size: 0.9rem;">
                    Der Bot beendet sich kurz selbst und wird durch Docker automatisch neu gestartet.
                </p>
            </div>
            <div style="flex: 1; min-width: 300px; border-left: 1px solid rgba(255,255,255,0.1); padding-left: 2rem;">
                <h2>Sound aufnehmen 🎤</h2>
                <div style="margin-top: 1rem; display: flex; flex-direction: column; gap: 0.5rem;" class="upload-form">
                    
                    <div style="display: flex; gap: 0.5rem;">
                        <button id="startRecordBtn" class="btn btn-primary" onclick="startRecording()">Start</button>
                        <button id="stopRecordBtn" class="btn btn-danger" onclick="stopRecording()" disabled>Stop</button>
                    </div>
                    
                    <div id="previewContainer" style="display: none; flex-direction: column; gap: 0.5rem; margin-top: 1rem; padding-top: 1rem; border-top: 1px solid rgba(255,255,255,0.1);">
                        <p style="margin:0;font-size:0.9rem;color:#cbd5e1;">Vorschau:</p>
                        <audio id="recordPreview" controls style="width: 100%; height: 36px;"></audio>
                        
                        <input type="text" id="recordName" class="cat-select" placeholder="Name für den Sound..." style="margin-top:0.5rem;">
                        <select id="recordCategory" class="cat-select">
                            {% for cat in categories %}
                                <option value="{{ cat }}">{{ cat }}</option>
                            {% endfor %}
                        </select>
                        <div style="display: flex; gap: 0.5rem; margin-top: 0.5rem; flex-wrap: wrap;">
                            <button id="saveRecordBtn" class="btn btn-primary" onclick="saveRecording()">Speichern</button>
                            <button id="previewDiscordBtn" class="btn btn-primary" onclick="previewOnDiscord()">🔊 Auf Discord</button>
                            <button id="discardRecordBtn" class="btn btn-secondary" onclick="discardRecording()">Verwerfen</button>
                        </div>
                    </div>

                    <div id="recordStatus" style="color: #cbd5e1; font-size: 0.9rem; margin-top: 0.5rem;"></div>
                </div>
            </div>
        </div>

        {% for cat in categories %}
        <div class="category-section">
            <div class="category-header" style="display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap;">
                <div>
                    <form action="{{ url_for('rename_category') }}" method="post" style="display: flex; align-items: center; gap: 0.5rem;">
                        <span style="font-size: 1.5rem;">📂</span>
                        <input type="hidden" name="old_category" value="{{ cat }}">
                        <input type="text" name="new_category" value="{{ cat }}" class="cat-select" style="font-size: 1.3rem; font-weight: bold; padding: 0.2rem 0.5rem; background: rgba(0,0,0,0.2); border: 1px dashed rgba(255,255,255,0.3); min-width: 200px;">
                        <button type="submit" class="btn btn-secondary" style="padding: 0.3rem 0.6rem; font-size: 0.8rem;" title="Speichern">💾 Umbenennen</button>
                    </form>
                </div>
                {% if categorized_sounds[cat]|length == 0 %}
                <form action="{{ url_for('delete_category') }}" method="post" onsubmit="return confirm('Ordner wirklich löschen?');">
                    <input type="hidden" name="category" value="{{ cat }}">
                    <button type="submit" class="btn btn-danger" style="padding: 0.3rem 0.6rem; font-size: 0.8rem;">🗑️ Ordner löschen</button>
                </form>
                {% endif %}
            </div>
            <div class="sound-grid">
                {% for sound in categorized_sounds[cat] %}
                <div class="sound-card">
                    <div class="sound-title">{{ sound.filename }}</div>
                    <audio controls preload="none">
                        <source src="{{ url_for('play_audio', filename=sound.filename) }}" type="audio/{{ 'mpeg' if sound.filename.endswith('.mp3') else 'wav' }}">
                    </audio>
                    <div class="controls">
                        <form action="{{ url_for('update_category', filename=sound.filename) }}" method="post" style="flex-grow: 1; margin-right: 0.5rem;">
                            <select name="category" class="cat-select" onchange="this.form.submit()">
                                {% for c in categories %}
                                <option value="{{ c }}" {% if c == cat %}selected{% endif %}>{{ c }}</option>
                                {% endfor %}
                            </select>
                        </form>
                        <div class="order-buttons">
                            <form action="{{ url_for('play_on_server', filename=sound.filename) }}" method="post" style="display:inline-block;">
                                <button type="submit" class="btn btn-primary" title="Im Discord abspielen">🔊</button>
                            </form>
                            <form action="{{ url_for('move_sound', filename=sound.filename, direction='up') }}" method="post">
                                <button type="submit" class="btn btn-secondary" title="Nach oben">▲</button>
                            </form>
                            <form action="{{ url_for('move_sound', filename=sound.filename, direction='down') }}" method="post">
                                <button type="submit" class="btn btn-secondary" title="Nach unten">▼</button>
                            </form>
                            <form action="{{ url_for('delete_file', filename=sound.filename) }}" method="post" onsubmit="return confirm('Sound wirklich löschen?');">
                                <button type="submit" class="btn btn-danger" title="Löschen">✕</button>
                            </form>
                        </div>
                    </div>
                </div>
                {% endfor %}
                {% if not categorized_sounds[cat] %}
                    <p style="color: #64748b; grid-column: 1 / -1;">Keine Sounds in diesem Ordner.</p>
                {% endif %}
            </div>
        </div>
        {% endfor %}
        
    </div>

    <script>
        let mediaRecorder;
        let audioChunks = [];
        let recordedBlob = null;

        async function startRecording() {
            try {
                discardRecording(); // Clean up prev session if any
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream);
                
                mediaRecorder.ondataavailable = event => {
                    if (event.data.size > 0) {
                        audioChunks.push(event.data);
                    }
                };

                mediaRecorder.onstop = async () => {
                    recordedBlob = new Blob(audioChunks, { type: 'audio/webm' });
                    audioChunks = [];
                    
                    document.getElementById("recordPreview").src = URL.createObjectURL(recordedBlob);
                    document.getElementById("previewContainer").style.display = "flex";
                    document.getElementById("recordStatus").innerText = "Aufnahme beendet. Bitte Name vergeben und Speichern.";
                    
                    mediaRecorder.stream.getTracks().forEach(track => track.stop());
                };

                audioChunks = [];
                mediaRecorder.start();
                document.getElementById("startRecordBtn").disabled = true;
                document.getElementById("stopRecordBtn").disabled = false;
                document.getElementById("recordStatus").innerText = "Aufnahme läuft... 🔴";
            } catch (err) {
                alert("Fehler beim Zugriff auf das Mikrofon! Stelle sicher, dass du Mikrofon-Berechtigungen erteilt hast und über HTTPS zugreifst, wenn es kein localhost ist. Error: " + err);
            }
        }

        function stopRecording() {
            if (mediaRecorder && mediaRecorder.state !== "inactive") {
                mediaRecorder.stop();
                document.getElementById("startRecordBtn").disabled = false;
                document.getElementById("stopRecordBtn").disabled = true;
            }
        }

        function discardRecording() {
            recordedBlob = null;
            document.getElementById("recordPreview").src = "";
            document.getElementById("previewContainer").style.display = "none";
            document.getElementById("recordName").value = "";
            document.getElementById("recordStatus").innerText = "";
            document.getElementById("startRecordBtn").disabled = false;
            document.getElementById("stopRecordBtn").disabled = true;
        }

        async function previewOnDiscord() {
            if (!recordedBlob) return;
            
            const formData = new FormData();
            formData.append("file", recordedBlob, "recording.webm");
            
            document.getElementById("previewDiscordBtn").disabled = true;
            document.getElementById("recordStatus").innerText = "Probehören wird gestartet...";
            
            try {
                const response = await fetch("{{ url_for('play_preview') }}", {
                    method: "POST",
                    body: formData
                });
                if(response.ok) {
                    document.getElementById("recordStatus").innerText = "Wird im Discord abgespielt!";
                } else {
                    document.getElementById("recordStatus").innerText = "Fehler beim Abspielen!";
                }
            } catch(e) {
                document.getElementById("recordStatus").innerText = "Verbindungsfehler!";
            } finally {
                document.getElementById("previewDiscordBtn").disabled = false;
            }
        }

        async function saveRecording() {
            if (!recordedBlob) return;
            
            const titleInput = document.getElementById("recordName").value.trim();
            if(!titleInput) {
                alert("Bitte einen Namen für den Sound eingeben!");
                return;
            }
            
            const formData = new FormData();
            formData.append("file", recordedBlob, "recording.webm");
            formData.append("name", titleInput);
            formData.append("category", document.getElementById("recordCategory").value);
            
            document.getElementById("saveRecordBtn").disabled = true;
            document.getElementById("recordStatus").innerText = "Wird gespeichert und konvertiert...";
            
            try {
                const response = await fetch("{{ url_for('upload_voice') }}", {
                    method: "POST",
                    body: formData
                });
                if(response.ok) {
                    window.location.reload();
                } else {
                    document.getElementById("recordStatus").innerText = "Fehler beim Speichern!";
                    document.getElementById("saveRecordBtn").disabled = false;
                }
            } catch(e) {
                document.getElementById("recordStatus").innerText = "Verbindungsfehler!";
                document.getElementById("saveRecordBtn").disabled = false;
            }
        }

        document.addEventListener("DOMContentLoaded", () => {
            const searchInput = document.getElementById("searchInput");
            const categorySections = document.querySelectorAll(".category-section");

            if (searchInput) {
                searchInput.addEventListener("input", (e) => {
                    const term = e.target.value.toLowerCase();
                    
                    categorySections.forEach(section => {
                        let hasVisibleSounds = false;
                        const cards = section.querySelectorAll(".sound-card");
                        
                        cards.forEach(card => {
                            const titleElement = card.querySelector(".sound-title");
                            if (titleElement) {
                                const filename = titleElement.innerText.toLowerCase();
                                if (filename.includes(term)) {
                                    card.style.display = "flex";
                                    hasVisibleSounds = true;
                                } else {
                                    card.style.display = "none";
                                }
                            }
                        });
                        
                        // Hide the whole category if it's empty during search, unless search is empty
                        if (hasVisibleSounds || term === "") {
                            section.style.display = "block";
                        } else {
                            section.style.display = "none";
                        }
                    });
                });
            }
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    meta = load_metadata()
    existing = get_existing_files()
    
    # Ensure all existing files are in metadata
    updated = False
    for f in existing:
        if f not in meta["sounds"]:
            meta["sounds"][f] = {"category": "Aktuelle Sounds", "order": 999}
            updated = True
    
    # Cleanup deleted files from metadata
    deleted = [f for f in meta["sounds"] if f not in existing]
    for f in deleted:
        del meta["sounds"][f]
        updated = True
        
    if updated:
        save_metadata(meta)
        
    categorized = {cat: [] for cat in meta["categories"]}
    for f in meta["sounds"]:
        if f in existing:
            cat = meta["sounds"][f]["category"]
            if cat not in categorized:
                cat = "Aktuelle Sounds"
            categorized[cat].append({"filename": f, "order": meta["sounds"][f]["order"]})
            
    for cat in categorized:
        categorized[cat].sort(key=lambda x: (x["order"], x["filename"]))
        
    return render_template_string(HTML_TEMPLATE, categories=meta["categories"], categorized_sounds=categorized)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('Keine Datei übergeben.')
        return redirect(url_for('index'))
    file = request.files['file']
    category = request.form.get('category', 'Aktuelle Sounds')
    
    if file.filename == '':
        flash('Keine Datei ausgewählt.')
        return redirect(url_for('index'))
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(MEDIA_FOLDER, filename))
        
        meta = load_metadata()
        meta["sounds"][filename] = {"category": category, "order": 999}
        save_metadata(meta)
        
        flash(f'{filename} erfolgreich nach "{category}" hochgeladen.')
    else:
        flash('Ungültiges Format. Nur .mp3 und .wav sind erlaubt.')
    return redirect(url_for('index'))

@app.route('/upload_voice', methods=['POST'])
def upload_voice():
    if 'file' not in request.files:
        return "No file", 400
    file = request.files['file']
    name = request.form.get('name', 'Sprachnotiz').strip()
    category = request.form.get('category', 'Aktuelle Sounds')
    
    if not name:
        name = "Sprachnotiz"
        
    safe_name = secure_filename(name)
    if not safe_name: safe_name = f"voice_{int(time.time())}"
    final_filename = safe_name + ".mp3"
    
    webm_path = os.path.join(MEDIA_FOLDER, f"temp_{int(time.time())}.webm")
    mp3_path = os.path.join(MEDIA_FOLDER, final_filename)
    
    file.save(webm_path)
    
    try:
        # Convert webm to mp3 using ffmpeg (which is available in docker)
        subprocess.run(["ffmpeg", "-y", "-i", webm_path, "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k", mp3_path], 
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(webm_path):
            os.remove(webm_path)
            
        meta = load_metadata()
        meta["sounds"][final_filename] = {"category": category, "order": 999}
        save_metadata(meta)
        flash(f'Voice-Aufnahme "{final_filename}" erfolgreich in Bereich "{category}" gespeichert.')
        return "OK", 200
    except subprocess.CalledProcessError as e:
        if os.path.exists(webm_path): os.remove(webm_path)
        print("FFmpeg error:", e)
        return "Error converting", 500

@app.route('/play_preview', methods=['POST'])
def play_preview():
    if 'file' not in request.files:
        return "No file", 400
    file = request.files['file']
    
    webm_path = os.path.join(MEDIA_FOLDER, "preview.webm")
    mp3_path = os.path.join(MEDIA_FOLDER, "preview.mp3")
    
    file.save(webm_path)
    
    try:
        subprocess.run(["ffmpeg", "-y", "-i", webm_path, "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k", mp3_path], 
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(webm_path):
            os.remove(webm_path)
            
        # Trigger play in discord
        with open(os.path.join(MEDIA_FOLDER, 'play_request.txt'), 'w', encoding='utf-8') as f:
            f.write("preview.mp3")
            
        return "OK", 200
    except subprocess.CalledProcessError as e:
        if os.path.exists(webm_path): os.remove(webm_path)
        print("FFmpeg error:", e)
        return "Error converting", 500

@app.route('/delete/<filename>', methods=['POST'])
def delete_file(filename):
    file_path = os.path.join(MEDIA_FOLDER, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        meta = load_metadata()
        if filename in meta["sounds"]:
            del meta["sounds"][filename]
            save_metadata(meta)
        flash(f'{filename} erfolgreich gelöscht.')
    else:
        flash('Datei nicht gefunden.')
    return redirect(url_for('index'))

@app.route('/update_category/<filename>', methods=['POST'])
def update_category(filename):
    meta = load_metadata()
    new_cat = request.form.get('category')
    if filename in meta["sounds"] and new_cat in meta["categories"]:
        meta["sounds"][filename]["category"] = new_cat
        meta["sounds"][filename]["order"] = 999
        save_metadata(meta)
        flash(f'{filename} wurde nach "{new_cat}" verschoben.')
    return redirect(url_for('index'))

@app.route('/move/<filename>/<direction>', methods=['POST'])
def move_sound(filename, direction):
    meta = load_metadata()
    if filename not in meta["sounds"]:
        return redirect(url_for('index'))
        
    cat = meta["sounds"][filename]["category"]
    existing = get_existing_files()
    
    sounds_in_cat = [f for f in meta["sounds"] if meta["sounds"][f]["category"] == cat and f in existing]
    sounds_in_cat.sort(key=lambda x: (meta["sounds"][x]["order"], x))
    
    for i, f in enumerate(sounds_in_cat):
        meta["sounds"][f]["order"] = i
        
    try:
        idx = sounds_in_cat.index(filename)
    except ValueError:
        return redirect(url_for('index'))
        
    if direction == 'up' and idx > 0:
        meta["sounds"][filename]["order"] = idx - 1
        meta["sounds"][sounds_in_cat[idx-1]]["order"] = idx
    elif direction == 'down' and idx < len(sounds_in_cat) - 1:
        meta["sounds"][filename]["order"] = idx + 1
        meta["sounds"][sounds_in_cat[idx+1]]["order"] = idx
        
    save_metadata(meta)
    return redirect(url_for('index'))

@app.route('/create_category', methods=['POST'])
def create_category():
    meta = load_metadata()
    new_cat = request.form.get('new_category', '').strip()
    if new_cat and new_cat not in meta["categories"]:
        meta["categories"].append(new_cat)
        save_metadata(meta)
        flash(f'Ordner "{new_cat}" erfolgreich erstellt.')
    elif new_cat in meta["categories"]:
        flash(f'Ordner "{new_cat}" existiert bereits.')
    return redirect(url_for('index'))

@app.route('/rename_category', methods=['POST'])
def rename_category():
    meta = load_metadata()
    old_cat = request.form.get('old_category')
    new_cat = request.form.get('new_category', '').strip()
    if old_cat in meta["categories"] and new_cat and new_cat != old_cat:
        if new_cat not in meta["categories"]:
            idx = meta["categories"].index(old_cat)
            meta["categories"][idx] = new_cat
            # update sounds that belonged to this category
            for f, data in meta["sounds"].items():
                if data.get("category") == old_cat:
                    meta["sounds"][f]["category"] = new_cat
            save_metadata(meta)
            flash(f'Ordner erfolgreich zu "{new_cat}" umbenannt.')
        else:
            flash(f'Ein Ordner mit dem Namen "{new_cat}" existiert bereits.')
    return redirect(url_for('index'))

@app.route('/delete_category', methods=['POST'])
def delete_category():
    meta = load_metadata()
    cat = request.form.get('category')
    if cat in meta["categories"]:
        meta["categories"].remove(cat)
        for f, data in meta["sounds"].items():
            if data.get("category") == cat:
                meta["sounds"][f]["category"] = "Aktuelle Sounds"
        
        if "Aktuelle Sounds" not in meta["categories"]:
            meta["categories"].insert(0, "Aktuelle Sounds")
            
        save_metadata(meta)
        flash(f'Ordner "{cat}" wurde gelöscht.')
    return redirect(url_for('index'))

@app.route('/media/<filename>')
def play_audio(filename):
    return send_from_directory(MEDIA_FOLDER, filename)

@app.route('/play_server/<filename>', methods=['POST'])
def play_on_server(filename):
    req_file = os.path.join(MEDIA_FOLDER, 'play_request.txt')
    with open(req_file, 'a', encoding='utf-8') as f:
        f.write(filename + '\n')
    flash(f'{filename} wird im Discord abgespielt!')
    return redirect(url_for('index'))

@app.route('/restart_bot', methods=['POST'])
def restart_bot():
    request_bot_restart()
    flash('Neustart fuer den Bot angefordert. Docker startet den Container in Kuerze neu.')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
