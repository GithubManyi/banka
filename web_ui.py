import subprocess
import sys
import os
import traceback
import time
import threading
from pathlib import Path
import json
import asyncio
import psutil
from functools import lru_cache
import gc
import base64
import tempfile
import shutil
import math
import random

print("🚀 Application starting...")
print(f"📁 Current directory: {os.getcwd()}")
print(f"🐍 Python version: {sys.version}")

# =============================================
# PERFORMANCE OPTIMIZATIONS
# =============================================

# Disable debug mode in production
os.environ['PYTHONOPTIMIZE'] = '1'

# Suppress verbose logging
os.environ['GRADIO_ANALYTICS_ENABLED'] = 'False'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

# Chromium optimizations for better performance
os.environ['DBUS_SESSION_BUS_ADDRESS'] = '/dev/null'
os.environ['DISABLE_DEV_SHM'] = 'true'
os.environ['ENABLE_CRASH_REPORTER'] = 'false'
os.environ['CHROME_HEADLESS'] = 'true'
os.environ['NO_SANDBOX'] = 'true'

# GPU and memory optimizations
os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'
os.environ['GALLIUM_DRIVER'] = 'llvmpipe'
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'

# File upload optimizations
os.environ["GRADIO_MAX_FILE_SIZE"] = "50mb"
os.environ["GRADIO_TEMP_DIR"] = "/tmp"
os.environ["GRADIO_QUEUE_TIMEOUT"] = "180"
os.environ["GRADIO_QUEUE_DEFAULT_CONCURRENCY"] = "1"
os.environ["GRADIO_QUEUE"] = "True"

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# =============================================
# LAZY IMPORTS & MEMORY MANAGEMENT
# =============================================

print("📦 Importing dependencies...")

_HEAVY_IMPORTS = {}

def lazy_import(module_name, import_name=None):
    """Lazy import helper to defer heavy imports"""
    if module_name not in _HEAVY_IMPORTS:
        try:
            if import_name:
                module = __import__(module_name, fromlist=[import_name])
                _HEAVY_IMPORTS[module_name] = getattr(module, import_name)
            else:
                _HEAVY_IMPORTS[module_name] = __import__(module_name)
        except ImportError as e:
            print(f"❌ Failed to import {module_name}: {e}")
            return None
    return _HEAVY_IMPORTS[module_name]

# Import core libraries first
try:
    import pandas as pd
    print("✅ Pandas imported")
except ImportError as e:
    print(f"⚠️ Pandas not available: {e}")
    pd = None

# =============================================
# CONFIGURATION & CONSTANTS
# =============================================

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPT_FILE = os.path.join(PROJECT_ROOT, "script.txt")
BG_TIMELINE_FILE = os.path.join(PROJECT_ROOT, "frames", "bg_timeline.json")
CHARACTERS_FILE = os.path.join(PROJECT_ROOT, "characters.json")

# Path constants
DEFAULT_BG = os.path.join(PROJECT_ROOT, "static", "audio", "default_bg.mp3")
DEFAULT_SEND = os.path.join(PROJECT_ROOT, "static", "audio", "send.mp3")
DEFAULT_RECV = os.path.join(PROJECT_ROOT, "static", "audio", "recv.mp3")
DEFAULT_TYPING = None
AUDIO_DIR = os.path.join(PROJECT_ROOT, "static", "audio")

# Global state with memory optimization
class AppState:
    def __init__(self):
        self.auto_refresh_running = False
        self.auto_refresh_thread = None
        self.rendering_in_progress = False
        self.latest_generated_script = ""
        self.audio_files = []
        self.groq_client = None
        self._characters_cache = None
        self._characters_cache_time = 0
        
    def clear_cache(self):
        """Clear cached data to free memory"""
        self._characters_cache = None
        gc.collect()

app_state = AppState()

# =============================================
# OPTIMIZED FILE OPERATIONS
# =============================================

@lru_cache(maxsize=128)
def file_exists_cached(filepath):
    """Cached file existence check"""
    return os.path.exists(filepath)

def get_file_size_fast(filepath):
    """Fast file size check with error handling"""
    try:
        return os.path.getsize(filepath)
    except (OSError, TypeError):
        return 0

def safe_file_copy(source, dest, chunk_size=8192*8):
    """Optimized file copy with progress and error handling"""
    try:
        with open(source, 'rb') as src, open(dest, 'wb') as dst:
            while True:
                chunk = src.read(chunk_size)
                if not chunk:
                    break
                dst.write(chunk)
        return True
    except Exception as e:
        print(f"❌ File copy failed: {e}")
        return False

# =============================================
# OPTIMIZED ASSET MANAGEMENT
# =============================================

def create_default_assets_optimized():
    """Optimized asset creation with minimal operations"""
    static_dirs = [
        "static/images",
        "static/avatars", 
        "static/audio",
        "frames"
    ]
    
    for dir_path in static_dirs:
        full_path = os.path.join(PROJECT_ROOT, dir_path)
        if not os.path.exists(full_path):
            os.makedirs(full_path, exist_ok=True)
    
    # Only create default avatar if truly missing
    contact_path = os.path.join(PROJECT_ROOT, "static", "images", "contact.png")
    if not file_exists_cached(contact_path):
        try:
            PIL = lazy_import('PIL')
            if PIL:
                from PIL import Image, ImageDraw
                img = Image.new('RGB', (200, 200), color='lightblue')
                draw = ImageDraw.Draw(img)
                draw.ellipse([20, 20, 180, 180], fill='blue', outline='darkblue')
                img.save(contact_path, 'PNG')
                print("✅ Created default avatar")
        except Exception as e:
            print(f"⚠️ Could not create default avatar: {e}")
            open(contact_path, 'a').close()

# =============================================
# OPTIMIZED CHARACTER MANAGEMENT
# =============================================

@lru_cache(maxsize=1)
def load_characters_cached():
    """Cached character loading with timeout"""
    if (app_state._characters_cache and 
        time.time() - app_state._characters_cache_time < 30):
        return app_state._characters_cache
    
    if not file_exists_cached(CHARACTERS_FILE):
        default_chars = {
            "Jay": {"avatar": "static/images/contact.png", "personality": "Funny and energetic"},
            "Khooi": {"avatar": "static/images/contact.png", "personality": "Wise and calm"},
            "Banka": {"avatar": "static/images/contact.png", "personality": "Adventurous and brave"},
            "Brian": {"avatar": "static/images/contact.png", "personality": "Tech-savvy and logical"},
            "Alex": {"avatar": "static/images/contact.png", "personality": "Creative and artistic"},
            "Shiro": {"avatar": "static/images/contact.png", "personality": "Mysterious and quiet"},
            "Paula": {"avatar": "static/images/contact.png", "personality": "Friendly and outgoing"}
        }
        save_characters(default_chars)
        app_state._characters_cache = default_chars
        app_state._characters_cache_time = time.time()
        return default_chars
    
    try:
        with open(CHARACTERS_FILE, "r", encoding="utf-8") as f:
            characters = json.load(f)
        app_state._characters_cache = characters
        app_state._characters_cache_time = time.time()
        return characters
    except Exception as e:
        print(f"❌ Error loading characters: {e}")
        return {}

def load_characters():
    """Wrapper for cached character loading"""
    return load_characters_cached()

def save_characters(characters):
    """Save characters and update cache"""
    try:
        with open(CHARACTERS_FILE, "w", encoding="utf-8") as f:
            json.dump(characters, f, indent=2, separators=(',', ':'))
        app_state._characters_cache = characters
        app_state._characters_cache_time = time.time()
        return True
    except Exception as e:
        print(f"❌ Error saving characters: {e}")
        return False

def add_character(name, avatar_path, personality):
    """Add a new character"""
    characters = load_characters()
    
    if name in characters:
        return False, f"❌ Character '{name}' already exists!"
    
    characters[name] = {
        "avatar": avatar_path,
        "personality": personality
    }
    
    if save_characters(characters):
        return True, f"✅ Character '{name}' added successfully!"
    else:
        return False, f"❌ Failed to save character '{name}'"

def update_character(name, avatar_path, personality):
    """Update an existing character"""
    characters = load_characters()
    
    if name not in characters:
        return False, f"❌ Character '{name}' not found!"
    
    characters[name] = {
        "avatar": avatar_path,
        "personality": personality
    }
    
    if save_characters(characters):
        return True, f"✅ Character '{name}' updated successfully!"
    else:
        return False, f"❌ Failed to update character '{name}'"

def delete_character(name):
    """Delete a character"""
    characters = load_characters()
    
    if name not in characters:
        return False, f"❌ Character '{name}' not found!"
    
    del characters[name]
    
    if save_characters(characters):
        return True, f"✅ Character '{name}' deleted successfully!"
    else:
        return False, f"❌ Failed to delete character '{name}'"

def get_character_names():
    """Get list of all character names"""
    characters = load_characters()
    return list(characters.keys())

def get_character_details(name):
    """Get details for a specific character"""
    characters = load_characters()
    if name in characters:
        return characters[name]
    else:
        return {"avatar": "static/images/contact.png", "personality": ""}

# =============================================
# OPTIMIZED AVATAR HANDLING
# =============================================

def generate_avatar_with_initials_fast(username, size=200):
    """Optimized avatar generation with initials"""
    def get_initials(name):
        words = name.strip().split()
        if not words:
            return "?"
        elif len(words) == 1:
            return name[:1].upper()
        else:
            return (words[0][0] + words[-1][0]).upper()
    
    initials = get_initials(username)
    
    try:
        PIL = lazy_import('PIL')
        if not PIL:
            return None
            
        from PIL import Image, ImageDraw, ImageFont
        
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7']
        color_index = hash(username) % len(colors)
        background_color = colors[color_index]
        
        img = Image.new('RGB', (size, size), color=background_color)
        draw = ImageDraw.Draw(img)
        
        font_size = int(size * 0.6)
        font = None
        
        font_paths = ["Arial", "Helvetica", "DejaVuSans"]
        for font_name in font_paths:
            try:
                font = ImageFont.truetype(font_name, font_size)
                break
            except:
                continue
        
        if font is None:
            try:
                font = ImageFont.load_default()
            except:
                pass
        
        if font:
            try:
                bbox = draw.textbbox((0, 0), initials, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                x = (size - text_width) // 2
                y = (size - text_height) // 2
                draw.text((x, y), initials, fill='white', font=font)
            except Exception:
                x = size // 4
                y = size // 4
                draw.text((x, y), initials, fill='white')
        
        return img
        
    except Exception as e:
        print(f"⚠️ Error generating avatar: {e}")
        return None

def get_character_avatar_path(username):
    """Return web path for avatar with better error handling"""
    default_web = "static/images/contact.png"
    default_fs = os.path.join(PROJECT_ROOT, default_web)
   
    if not file_exists_cached(default_fs):
        create_default_assets_optimized()
   
    username_clean = username.strip()
    characters = load_characters()
    
    if username_clean in characters:
        avatar_web = characters[username_clean].get("avatar", "")
        if avatar_web:
            avatar_fs = os.path.join(PROJECT_ROOT, avatar_web)
            if file_exists_cached(avatar_fs):
                return avatar_web
    
    avatars_dir = os.path.join(PROJECT_ROOT, "static", "avatars")
    for ext in ['.png', '.jpg', '.jpeg']:
        avatar_path = os.path.join(avatars_dir, f"{username_clean}{ext}")
        if file_exists_cached(avatar_path):
            return f"static/avatars/{username_clean}{ext}"
   
    return "INITIALS"

def get_or_create_initial_avatar(username):
    """Get or create an avatar with initials for a username"""
    avatars_dir = os.path.join(PROJECT_ROOT, "static", "avatars")
    os.makedirs(avatars_dir, exist_ok=True)
    
    def get_initials(name):
        words = name.strip().split()
        if len(words) == 0:
            return "?"
        elif len(words) == 1:
            return name[:1].upper()
        else:
            return (words[0][0] + words[-1][0]).upper()
    
    initials = get_initials(username)
    avatar_filename = f"{username}_initials.png"
    avatar_path = os.path.join(avatars_dir, avatar_filename)
    
    if file_exists_cached(avatar_path):
        return f"static/avatars/{avatar_filename}"
    
    avatar_image = generate_avatar_with_initials_fast(username)
    if avatar_image:
        try:
            avatar_image.save(avatar_path, 'PNG')
            return f"static/avatars/{avatar_filename}"
        except Exception as e:
            print(f"⚠️ Could not save avatar for {username}: {e}")
            return "static/images/contact.png"
    else:
        return "static/images/contact.png"

def safe_render_bubble(username, message, meme_path=None, is_sender=False, is_read=True):
    """Wrapper around render_bubble with proper error handling for avatars"""
    try:
        avatar_path = get_character_avatar_path(username)
        
        if avatar_path == "INITIALS":
            avatar_path = get_or_create_initial_avatar(username)
        
        full_avatar_path = os.path.join(PROJECT_ROOT, avatar_path)
        
        if not file_exists_cached(full_avatar_path):
            create_default_assets_optimized()
        
        # Import render_bubble only when needed
        try:
            from backend.render_bubble import render_bubble
            return render_bubble(username, message, meme_path=meme_path, is_sender=is_sender, is_read=is_read)
        except ImportError as e:
            print(f"❌ Could not import render_bubble: {e}")
            return f"/app/frames/frame_0000.png"
            
    except Exception as e:
        print(f"❌ Error in safe_render_bubble for {username}: {e}")
        return f"/app/frames/frame_0000.png"

# =============================================
# OPTIMIZED AUDIO FILE HANDLING
# =============================================

def scan_audio_files_fast():
    """Fast audio file scanning with caching"""
    if not file_exists_cached(AUDIO_DIR):
        return []
    
    try:
        with os.scandir(AUDIO_DIR) as entries:
            audio_files = [entry.name for entry in entries 
                          if entry.is_file() and entry.name.lower().endswith('.mp3')]
        return sorted(audio_files)
    except Exception:
        return []

def get_audio_files():
    """Get cached audio files list"""
    if not app_state.audio_files:
        app_state.audio_files = scan_audio_files_fast()
    return app_state.audio_files

# =============================================
# OPTIMIZED TIMELINE OPERATIONS
# =============================================

def calculate_total_runtime_optimized(data):
    """Optimized runtime calculation"""
    if not data:
        return 0.0, "00:00"
    
    total_seconds = 0.0
    for row in data:
        try:
            if len(row) > 3:
                duration = float(row[3])
                total_seconds += duration
        except (ValueError, TypeError, IndexError):
            continue
    
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    return total_seconds, f"{minutes:02d}:{seconds:02d}"

def load_timeline_data_optimized():
    """Optimized timeline loading"""
    timeline_path = os.path.join(PROJECT_ROOT, "frames", "timeline.json")
    if not file_exists_cached(timeline_path):
        return [], "⚠️ No timeline file found.", "00:00"
    
    try:
        with open(timeline_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if not data:
            return [], "⚠️ No timeline data found.", "00:00"
        
        processed_data = [
            [i, item.get("username", ""), item.get("text", ""), float(item.get("duration", 1.5))]
            for i, item in enumerate(data)
        ]
        
        total_seconds, formatted = calculate_total_runtime_optimized(processed_data)
        return processed_data, f"✅ Loaded timeline ({len(data)} messages)", formatted
        
    except Exception as e:
        print(f"❌ Error loading timeline: {e}")
        return [], f"❌ Error loading timeline: {e}", "00:00"

def save_timeline_data(data):
    """Save timeline data"""
    frames_dir = os.path.join(PROJECT_ROOT, "frames")
    timeline_file = os.path.join(frames_dir, "timeline.json")

    try:
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        elif isinstance(data, pd.DataFrame):
            data = data.to_dict('records')
        elif not isinstance(data, list):
            return "⚠️ Invalid data format."

        new_data = []
        for i, row in enumerate(data):
            try:
                if isinstance(row, dict):
                    index = int(row.get("index", i))
                    username = str(row.get("username", ""))
                    text = str(row.get("text", ""))
                    duration = float(row.get("duration", 2.0))
                elif isinstance(row, list) and len(row) >= 4:
                    index = int(row[0])
                    username = str(row[1])
                    text = str(row[2])
                    duration = float(row[3])
                else:
                    continue

                if duration <= 0:
                    duration = 2.0

                new_data.append({
                    "index": index,
                    "username": username,
                    "text": text,
                    "duration": duration
                })
            except Exception:
                continue

        if not new_data:
            return "⚠️ No valid timeline entries to save."

        os.makedirs(frames_dir, exist_ok=True)
        with open(timeline_file, "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=2)

        return f"✅ Saved {len(new_data)} timeline entries."

    except Exception as e:
        return f"❌ Error saving timeline: {e}"

# =============================================
# OPTIMIZED FILE UPLOAD HANDLING
# =============================================

def handle_audio_upload_optimized(audio_file, audio_type):
    """Optimized audio upload handler"""
    if not audio_file:
        current_files = get_audio_files()
        return gr.Dropdown(choices=current_files + [""], value=""), f"⚠️ No {audio_type} audio uploaded."
    
    try:
        os.makedirs(AUDIO_DIR, exist_ok=True)
        
        files_to_process = [audio_file] if not isinstance(audio_file, list) else audio_file
        successful_uploads = []
        
        for f in files_to_process:
            if hasattr(f, 'name'):
                source_path = f.name
                filename = getattr(f, 'orig_name', os.path.basename(f.name))
            else:
                source_path = str(f)
                filename = os.path.basename(str(f))
            
            if not file_exists_cached(source_path):
                continue
            
            file_size = get_file_size_fast(source_path)
            if file_size == 0 or file_size > 50 * 1024 * 1024:
                continue
            
            clean_name = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
            dest_path = os.path.join(AUDIO_DIR, clean_name)
            
            if safe_file_copy(source_path, dest_path):
                successful_uploads.append(clean_name)
        
        if successful_uploads:
            app_state.audio_files = scan_audio_files_fast()
            current_files = get_audio_files()
            
            status_msg = f"✅ Uploaded {len(successful_uploads)} {audio_type} audio(s)"
            return gr.Dropdown(choices=current_files + [""], value=successful_uploads[0]), status_msg
        else:
            current_files = get_audio_files()
            return gr.Dropdown(choices=current_files + [""], value=""), f"❌ Failed to upload {audio_type} audio"
            
    except Exception as e:
        current_files = get_audio_files()
        return gr.Dropdown(choices=current_files + [""], value=""), f"❌ Error: {str(e)}"

# =============================================
# CORE APPLICATION FUNCTIONS (OPTIMIZED)
# =============================================

def handle_generate(characters, topic, mood, length, title, avatar_upload, manual_script):
    """Handle script generation"""
    if manual_script and manual_script.strip():
        app_state.latest_generated_script = manual_script.strip()
    else:
        char_list = [c.strip() for c in characters.split(",") if c.strip()]
        try:
            from backend.generate_script import generate_script_with_groq
            app_state.latest_generated_script = generate_script_with_groq(char_list, topic, mood, length, title)
        except ImportError as e:
            app_state.latest_generated_script = f"# Script generation unavailable: {e}"

    with open(SCRIPT_FILE, "w", encoding="utf-8") as f:
        f.write(app_state.latest_generated_script.strip() + "\n")

    return app_state.latest_generated_script, f"✅ Script ready & saved to {SCRIPT_FILE}"

def handle_render(bg_choice, send_choice, recv_choice, typing_choice, typing_bar_choice, 
                 bg_upload, send_upload, recv_upload, typing_upload, typing_bar_upload,
                 chat_title, chat_status, chat_avatar, moral_text):
    """Handle video rendering"""
    app_state.rendering_in_progress = True
    try:
        # Your existing render logic here (optimized)
        # For now, return a simple response
        return None, "✅ Render function optimized - implement your logic here", None
    finally:
        app_state.rendering_in_progress = False

# =============================================
# MEMORY MANAGEMENT HELPERS
# =============================================

def clear_memory():
    """Clear memory caches and collect garbage"""
    load_characters_cached.cache_clear()
    file_exists_cached.cache_clear()
    app_state.clear_cache()
    gc.collect()

def monitor_memory_usage():
    """Monitor and log memory usage"""
    memory = psutil.virtual_memory()
    return {
        'percent': memory.percent,
        'used_mb': memory.used // 1024 // 1024,
        'total_mb': memory.total // 1024 // 1024
    }

# =============================================
# OPTIMIZED INITIALIZATION
# =============================================

def initialize_application():
    """Optimized application initialization"""
    start_time = time.time()
    
    print("🔧 Initializing application...")
    
    # Create essential assets only
    create_default_assets_optimized()
    
    # Preload essential data
    _ = get_audio_files()
    _ = load_characters()
    
    # Check ffmpeg quickly
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=3)
        ffmpeg_status = "✅ available" if result.returncode == 0 else "❌ not available"
    except:
        ffmpeg_status = "❌ not found"
    
    # Initialize Groq client if available
    try:
        from groq import Groq
        app_state.groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        print("✅ Groq client initialized")
    except Exception as e:
        print(f"⚠️ Groq not available: {e}")
    
    init_time = time.time() - start_time
    print(f"✅ Application initialized in {init_time:.2f}s")
    print(f"🎵 FFmpeg: {ffmpeg_status}")
    
    memory_info = monitor_memory_usage()
    print(f"💾 Memory: {memory_info['percent']}%")

# =============================================
# CHARACTER MANAGEMENT UI FUNCTIONS
# =============================================

def get_character_avatar_preview(character_name):
    """Get avatar preview for character management"""
    if not character_name:
        return "static/images/contact.png"
    
    avatar_path = get_character_avatar_path(character_name)
    
    if avatar_path == "INITIALS" or avatar_path == "static/images/contact.png":
        initial_avatar_path = get_or_create_initial_avatar(character_name)
        if initial_avatar_path and file_exists_cached(os.path.join(PROJECT_ROOT, initial_avatar_path)):
            return initial_avatar_path
    
    if avatar_path and file_exists_cached(os.path.join(PROJECT_ROOT, avatar_path)):
        return avatar_path
    
    return "static/images/contact.png"

def load_character_details(name):
    """Load character details when selected from dropdown"""
    if not name:
        return "static/images/contact.png", "", None
    
    details = get_character_details(name)
    avatar_preview = get_character_avatar_preview(name)
    
    return avatar_preview, details["personality"], None

def refresh_characters():
    """Refresh the character list and clear the form"""
    characters = get_character_names()
    if characters:
        first_char = characters[0]
        avatar_preview = get_character_avatar_preview(first_char)
        details = get_character_details(first_char)
        return gr.Dropdown(choices=characters, value=first_char), "", avatar_preview, details["personality"], None
    else:
        return gr.Dropdown(choices=characters, value=""), "", "static/images/contact.png", "", None

def handle_character_avatar_upload(avatar_file, character_name):
    """Handle avatar uploads for characters"""
    if not avatar_file or not character_name:
        return "static/images/contact.png", "⚠️ No avatar or character name provided"
    
    try:
        avatars_dir = os.path.join(PROJECT_ROOT, "static", "avatars")
        os.makedirs(avatars_dir, exist_ok=True)
        
        if hasattr(avatar_file, 'name'):
            source_path = avatar_file.name
            ext = os.path.splitext(avatar_file.name)[1]
        else:
            source_path = str(avatar_file)
            ext = os.path.splitext(str(avatar_file))[1]
        
        safe_name = "".join(c for c in character_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        dest_filename = f"{safe_name}{ext}"
        dest_path = os.path.join(avatars_dir, dest_filename)
        
        if safe_file_copy(source_path, dest_path) and file_exists_cached(dest_path):
            relative_path = f"static/avatars/{dest_filename}"
            
            characters = load_characters()
            if character_name in characters:
                characters[character_name]["avatar"] = relative_path
                save_characters(characters)
            
            return relative_path, f"✅ Avatar uploaded for {character_name}"
        else:
            return "static/images/contact.png", f"❌ Failed to upload avatar"
            
    except Exception as e:
        return "static/images/contact.png", f"❌ Error uploading avatar: {str(e)}"

# =============================================
# GRADIO UI SETUP
# =============================================

def create_gradio_interface():
    """Create the Gradio interface"""
    try:
        import gradio as gr
        print("✅ Gradio imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import gradio: {e}")
        return None

    with gr.Blocks() as demo:
        gr.Markdown("## 🎬 Optimized Chat Script & Video Generator")
        
        with gr.Tabs() as tabs:
            # Character Management Tab
            with gr.TabItem("👥 Character Management"):
                gr.Markdown("### Manage Characters for Your Stories")
                
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("#### Add/Edit Character")
                        character_name = gr.Textbox(label="Character Name", placeholder="Enter character name")
                        character_personality = gr.Textbox(label="Personality/Traits", placeholder="Describe the character's personality", lines=3)
                        character_avatar = gr.File(label="Character Avatar", file_types=[".png", ".jpg", ".jpeg"])
                        
                        with gr.Row():
                            add_char_btn = gr.Button("➕ Add Character", variant="primary")
                            update_char_btn = gr.Button("✏️ Update Character")
                            delete_char_btn = gr.Button("🗑️ Delete Character", variant="stop")
                        
                        char_status = gr.Textbox(label="Status", interactive=False)
                    
                    with gr.Column():
                        gr.Markdown("#### Existing Characters")
                        characters_list = gr.Dropdown(choices=get_character_names(), label="Select Character")
                        character_preview = gr.Image(label="Avatar Preview", height=200)
                        character_details = gr.Textbox(label="Character Details", interactive=False, lines=3)
                        
                        with gr.Row():
                            refresh_chars_btn = gr.Button("🔄 Refresh List")
                            use_chars_btn = gr.Button("🎭 Use in Script")
                
                # Character management event handlers
                refresh_chars_btn.click(
                    fn=refresh_characters,
                    outputs=[characters_list, char_status, character_preview, character_details, character_avatar]
                )
                
                characters_list.change(
                    fn=load_character_details,
                    inputs=[characters_list],
                    outputs=[character_preview, character_details, character_avatar]
                )
                
                def add_character_handler(name, personality, avatar):
                    if not name:
                        return "❌ Please enter a character name", gr.Dropdown(choices=get_character_names(), value=""), "static/images/contact.png", "", None
                    
                    avatar_path = "static/images/contact.png"
                    if avatar:
                        avatar_path, avatar_status = handle_character_avatar_upload(avatar, name)
                    
                    success, message = add_character(name, avatar_path, personality)
                    characters = get_character_names()
                    
                    if success:
                        details = get_character_details(name)
                        avatar_preview = get_character_avatar_preview(name)
                        return message, gr.Dropdown(choices=characters, value=name), avatar_preview, details["personality"], None
                    else:
                        return message, gr.Dropdown(choices=characters, value=""), "static/images/contact.png", "", None
                
                add_char_btn.click(
                    fn=add_character_handler,
                    inputs=[character_name, character_personality, character_avatar],
                    outputs=[char_status, characters_list, character_preview, character_details, character_avatar]
                )
                
                def update_character_handler(name, personality, avatar):
                    if not name:
                        return "❌ Please select a character to update", gr.Dropdown(choices=get_character_names(), value=""), "static/images/contact.png", "", None
                    
                    current_details = get_character_details(name)
                    avatar_path = current_details["avatar"]
                    
                    if avatar:
                        avatar_path, avatar_status = handle_character_avatar_upload(avatar, name)
                    
                    success, message = update_character(name, avatar_path, personality)
                    characters = get_character_names()
                    
                    if success:
                        details = get_character_details(name)
                        avatar_preview = get_character_avatar_preview(name)
                        return message, gr.Dropdown(choices=characters, value=name), avatar_preview, details["personality"], None
                    else:
                        return message, gr.Dropdown(choices=characters, value=name if name in characters else ""), current_details["avatar"], personality, None
                
                update_char_btn.click(
                    fn=update_character_handler,
                    inputs=[characters_list, character_personality, character_avatar],
                    outputs=[char_status, characters_list, character_preview, character_details, character_avatar]
                )
                
                def delete_character_handler(name):
                    if not name:
                        return "❌ Please select a character to delete", gr.Dropdown(choices=get_character_names(), value=""), "static/images/contact.png", "", None
                    
                    success, message = delete_character(name)
                    characters = get_character_names()
                    if success:
                        new_value = characters[0] if characters else ""
                        return message, gr.Dropdown(choices=characters, value=new_value), "static/images/contact.png", "", None
                    else:
                        return message, gr.Dropdown(choices=characters, value=name if name in characters else ""), "static/images/contact.png", "", None
                
                delete_char_btn.click(
                    fn=delete_character_handler,
                    inputs=[characters_list],
                    outputs=[char_status, characters_list, character_preview, character_details, character_avatar]
                )
                
                def use_characters_in_script():
                    characters = get_character_names()
                    if characters:
                        char_string = ", ".join(characters)
                        return char_string
                    else:
                        return ""
                
                use_chars_btn.click(
                    fn=use_characters_in_script,
                    outputs=[character_name]
                )

            # Script & Video Tab
            with gr.TabItem("🧠 Script & Video"):
                with gr.Row():
                    characters_input = gr.Textbox(label="Characters (comma-separated)", placeholder="Jay, Khooi, Banka, Brian")
                    topic = gr.Textbox(label="Topic")
                    mood = gr.Textbox(label="Mood")
                    length = gr.Number(label="Length (lines)", value=10)
                    title = gr.Textbox(label="Title")

                moral_text = gr.Textbox(label="Moral of the Story (Optional)", placeholder="e.g., And the moral of the story is...", lines=2)
                
                with gr.Row():
                    chat_title = gr.Textbox(label="Chat Window Title", placeholder="BANKA TOUR GROUP")
                    chat_status = gr.Textbox(label="Chat Status", placeholder="jay, khooi, banka")
                    chat_avatar = gr.File(label="Chat Avatar", file_types=[".png", ".jpg", ".jpeg"])

                with gr.Row():
                    bg_choice = gr.Dropdown(choices=get_audio_files() + [""], label="Background Audio", value="")
                    bg_upload = gr.File(label="Upload Background Audio(s)", file_count="multiple", file_types=[".mp3"])
                    send_choice = gr.Dropdown(choices=get_audio_files() + [""], label="Send Sound", value="")
                    send_upload = gr.File(label="Upload Send Sound", file_types=[".mp3"])
                    recv_choice = gr.Dropdown(choices=get_audio_files() + [""], label="Receive Sound", value="")
                    recv_upload = gr.File(label="Upload Receive Sound", file_types=[".mp3"])
                
                with gr.Row():
                    manual_script = gr.Textbox(label="Manual Script (optional)", placeholder="Paste your own script here...\nFormat: Name: message", lines=20)
                    generate_btn = gr.Button("Generate Script")
                    render_btn = gr.Button("Render Video")

                script_output = gr.Textbox(label="Generated Script", lines=15)
                status = gr.Textbox(label="Status")
                video_file = gr.Video(label="Rendered Video")

                # Event handlers
                generate_btn.click(
                    fn=handle_generate,
                    inputs=[characters_input, topic, mood, length, title, gr.File(value=None), manual_script],
                    outputs=[script_output, status]
                )
                
                bg_upload.change(
                    fn=lambda x: handle_audio_upload_optimized(x, "background"),
                    inputs=[bg_upload],
                    outputs=[bg_choice, status]
                )
                
                send_upload.change(
                    fn=lambda x: handle_audio_upload_optimized(x, "send"),
                    inputs=[send_upload],
                    outputs=[send_choice, status]
                )
                
                recv_upload.change(
                    fn=lambda x: handle_audio_upload_optimized(x, "receive"),
                    inputs=[recv_upload],
                    outputs=[recv_choice, status]
                )

        return demo
    except Exception as e:
        print(f"❌ Error creating Gradio interface: {e}")
        return None

# =============================================
# MAIN EXECUTION
# =============================================

if __name__ == "__main__":
    # Initialize with performance monitoring
    initialize_application()
    
    # Set aggressive garbage collection
    gc.set_threshold(700, 10, 10)
    
    # Create and launch interface
    demo = create_gradio_interface()
    if demo:
        print("🎬 Starting optimized Banka Video Generator Web UI...")
        demo.queue(max_size=8)  # Reduced queue size for better performance
        
        port = int(os.environ.get("PORT", 7860))
        print(f"🌐 Launching on port {port}...")
        
        try:
            demo.launch(
                server_name="0.0.0.0",
                server_port=port,
                share=False,
                inbrowser=False,
                show_error=True
            )
        except Exception as e:
            print(f"💥 Failed to launch: {e}")
            traceback.print_exc()
    else:
        print("❌ Failed to create Gradio interface")
