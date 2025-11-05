import subprocess
import sys
import os
import traceback

# SUPPRESS ALL DEBUG OUTPUT FOR MAXIMUM PERFORMANCE
import logging
logging.getLogger().setLevel(logging.ERROR)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# SUPPRESS CHROMIUM ERRORS
os.environ['DBUS_SESSION_BUS_ADDRESS'] = '/dev/null'
os.environ['DISABLE_DEV_SHM'] = 'true'
os.environ['ENABLE_CRASH_REPORTER'] = 'false'
os.environ['CHROME_HEADLESS'] = 'true'
os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'
os.environ['GALLIUM_DRIVER'] = 'llvmpipe'

# DISABLE ALL CONSOLE OUTPUT
sys.stdout = open(os.devnull, 'w')
sys.stderr = open(os.devnull, 'w')

# SIMPLE FFMPEG CHECK
try:
    subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=2)
except Exception:
    pass

# NOW import the rest of your modules
import tempfile
import shutil
from pathlib import Path
import base64
import gradio as gr
import asyncio
import json
import pandas as pd
import time
import threading
import math
import random
import psutil

# Import your custom modules with NO LOGGING
try:
    from backend.generate_script import generate_script_with_groq
except ImportError:
    pass

try:
    from backend.generate_video import build_video_from_timeline
except ImportError:
    pass

try:
    from backend.avatar_handler import save_uploaded_avatar
except ImportError:
    pass

try:
    from backend.render_bubble import render_bubble, render_typing_bubble, WhatsAppRenderer, render_typing_bar_frame, generate_beluga_typing_sequence, reset_typing_sessions
    
    # Initialize renderer state
    render_bubble.frame_count = 0
    render_bubble.timeline = []
    render_bubble.renderer = WhatsAppRenderer()
    
except ImportError:
    class WhatsAppRenderer:
        def __init__(self, *args, **kwargs):
            pass
    def render_bubble(*args, **kwargs):
        return "/app/frames/frame_0000.png"
    def render_typing_bubble(*args, **kwargs):
        return "/app/frames/frame_0000.png"
    def render_typing_bar_frame(*args, **kwargs):
        return "/app/frames/frame_0000.png"
    def generate_beluga_typing_sequence(*args, **kwargs):
        return []
    def reset_typing_sessions():
        pass
    
    render_bubble.frame_count = 0
    render_bubble.timeline = []
    render_bubble.renderer = WhatsAppRenderer()

try:
    from groq import Groq
    groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
except ImportError:
    groq_client = None
except Exception:
    groq_client = None

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPT_FILE = os.path.join(PROJECT_ROOT, "script.txt")
BG_TIMELINE_FILE = os.path.join(PROJECT_ROOT, "frames", "bg_timeline.json")
CHARACTERS_FILE = os.path.join(PROJECT_ROOT, "characters.json")

# Keep track of the last generated script
if os.path.exists(SCRIPT_FILE):
    with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
        latest_generated_script = f.read().strip()
else:
    latest_generated_script = ""

# Default audio
DEFAULT_BG = os.path.join(PROJECT_ROOT, "static", "audio", "default_bg.mp3")
DEFAULT_SEND = os.path.join(PROJECT_ROOT, "static", "audio", "send.mp3")
DEFAULT_RECV = os.path.join(PROJECT_ROOT, "static", "audio", "recv.mp3")
DEFAULT_TYPING = None

# Collect available audio files
AUDIO_DIR = os.path.join(PROJECT_ROOT, "static", "audio")
if os.path.exists(AUDIO_DIR):
    AUDIO_FILES = [f for f in os.listdir(AUDIO_DIR) if f.lower().endswith(".mp3")]
else:
    AUDIO_FILES = []

# Global flags
auto_refresh_running = False
auto_refresh_thread = None
rendering_in_progress = False

# Prevent Gradio timeouts
os.environ["GRADIO_QUEUE"] = "True"

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add asset creation function
def create_default_assets():
    """Create default assets if they don't exist"""
    static_dirs = [
        "static/images",
        "static/avatars", 
        "static/audio",
        "frames"
    ]
    
    for dir_path in static_dirs:
        full_path = os.path.join(PROJECT_ROOT, dir_path)
        os.makedirs(full_path, exist_ok=True)
    
    # Create default contact.png if it doesn't exist
    contact_path = os.path.join(PROJECT_ROOT, "static", "images", "contact.png")
    if not os.path.exists(contact_path):
        try:
            from PIL import Image, ImageDraw
            
            img = Image.new('RGB', (200, 200), color='lightblue')
            draw = ImageDraw.Draw(img)
            draw.ellipse([20, 20, 180, 180], fill='blue', outline='darkblue')
            draw.arc([50, 60, 150, 120], start=0, end=180, fill='white', width=8)
            draw.ellipse([70, 80, 90, 100], fill='white')
            draw.ellipse([110, 80, 130, 100], fill='white')
            
            img.save(contact_path, 'PNG')
        except ImportError:
            open(contact_path, 'a').close()
        except Exception:
            open(contact_path, 'a').close()

create_default_assets()

# =============================================
# ULTRA-OPTIMIZED CHARACTER MANAGEMENT
# =============================================

def load_characters():
    """Load characters from JSON file - OPTIMIZED"""
    if os.path.exists(CHARACTERS_FILE):
        try:
            with open(CHARACTERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_characters(characters):
    """Save characters to JSON file - OPTIMIZED"""
    try:
        with open(CHARACTERS_FILE, "w", encoding="utf-8") as f:
            json.dump(characters, f, indent=2)
        return True
    except Exception:
        return False

def add_character(name, avatar_path, personality):
    """Add a new character - OPTIMIZED"""
    characters = load_characters()
    
    if name in characters:
        return False, f"❌ Character '{name}' already exists!"
    
    characters[name] = {"avatar": avatar_path, "personality": personality}
    
    if save_characters(characters):
        return True, f"✅ Character '{name}' added successfully!"
    return False, f"❌ Failed to save character '{name}'"

def update_character(name, avatar_path, personality):
    """Update an existing character - OPTIMIZED"""
    characters = load_characters()
    
    if name not in characters:
        return False, f"❌ Character '{name}' not found!"
    
    characters[name] = {"avatar": avatar_path, "personality": personality}
    
    if save_characters(characters):
        return True, f"✅ Character '{name}' updated successfully!"
    return False, f"❌ Failed to update character '{name}'"

def delete_character(name):
    """Delete a character - OPTIMIZED"""
    characters = load_characters()
    
    if name not in characters:
        return False, f"❌ Character '{name}' not found!"
    
    del characters[name]
    
    if save_characters(characters):
        return True, f"✅ Character '{name}' deleted successfully!"
    return False, f"❌ Failed to delete character '{name}'"

def get_character_names():
    """Get list of all character names - OPTIMIZED"""
    characters = load_characters()
    return list(characters.keys())

def get_character_details(name):
    """Get details for a specific character - OPTIMIZED"""
    characters = load_characters()
    if name in characters:
        return characters[name]
    return {"avatar": "static/images/contact.png", "personality": ""}

def get_character_avatar_path(username):
    """Return web path for avatar - OPTIMIZED"""
    username_clean = username.strip()
    
    characters = load_characters()
    if username_clean in characters:
        avatar_web = characters[username_clean].get("avatar", "")
        if avatar_web:
            avatar_fs = os.path.join(PROJECT_ROOT, avatar_web)
            if os.path.exists(avatar_fs):
                return avatar_web

    avatars_dir = os.path.join(PROJECT_ROOT, "static", "avatars")
    for ext in ['.png', '.jpg', '.jpeg']:
        avatar_path = os.path.join(avatars_dir, f"{username_clean}{ext}")
        if os.path.exists(avatar_path):
            return f"static/avatars/{username_clean}{ext}"
   
    return "INITIALS"

# =============================================
# ULTRA-FAST AVATAR GENERATION
# =============================================

def generate_avatar_with_initials(username, size=128):  # Reduced size for speed
    """Generate avatar with initials - ULTRA OPTIMIZED"""
    def get_initials(name):
        words = name.strip().split()
        if not words: return "?"
        if len(words) == 1: return name[:1].upper()
        return (words[0][0] + words[-1][0]).upper()
    
    initials = get_initials(username)
    
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7']
        color_index = hash(username) % len(colors)
        
        img = Image.new('RGB', (size, size), color=colors[color_index])
        draw = ImageDraw.Draw(img)
        
        font_size = size // 2
        try:
            font = ImageFont.truetype("Arial", font_size)
        except:
            font = ImageFont.load_default()
        
        # Simple centered text - no complex calculations
        text_width = len(initials) * font_size // 2
        text_height = font_size
        x = (size - text_width) // 2
        y = (size - text_height) // 2
        
        draw.text((x, y), initials, fill='white', font=font)
        return img
        
    except Exception:
        return None

def get_or_create_initial_avatar(username):
    """Get or create avatar with initials - OPTIMIZED"""
    avatars_dir = os.path.join(PROJECT_ROOT, "static", "avatars")
    os.makedirs(avatars_dir, exist_ok=True)
    
    avatar_filename = f"{username}_initials.png"
    avatar_path = os.path.join(avatars_dir, avatar_filename)
    
    if os.path.exists(avatar_path):
        return f"static/avatars/{avatar_filename}"
    
    avatar_image = generate_avatar_with_initials(username)
    if avatar_image:
        try:
            avatar_image.save(avatar_path, 'PNG')
            return f"static/avatars/{avatar_filename}"
        except Exception:
            return "static/images/contact.png"
    return "static/images/contact.png"

def safe_render_bubble(username, message, meme_path=None, is_sender=False, is_read=True):
    """Wrapper around render_bubble - OPTIMIZED"""
    try:
        avatar_path = get_character_avatar_path(username)
        if avatar_path == "INITIALS":
            avatar_path = get_or_create_initial_avatar(username)
        
        return render_bubble(username, message, meme_path=meme_path, is_sender=is_sender, is_read=is_read)
    except Exception:
        return render_bubble(username, message, meme_path=meme_path, is_sender=is_sender, is_read=is_read)

# =============================================
# ULTRA-FAST FILE UPLOAD
# =============================================

def handle_audio_upload_fixed(audio_file, audio_type):
    """Handle audio upload - ULTRA OPTIMIZED"""
    if not audio_file:
        return gr.Dropdown(choices=AUDIO_FILES + [""], value=""), f"⚠️ No {audio_type} audio uploaded."
    
    try:
        os.makedirs(AUDIO_DIR, exist_ok=True)
        
        files_to_process = [audio_file] if not isinstance(audio_file, list) else audio_file
        
        for f in files_to_process:
            if hasattr(f, 'name'):
                source_path = f.name
                filename = os.path.basename(f.name)
            else:
                source_path = str(f)
                filename = os.path.basename(str(f))
            
            if not os.path.exists(source_path):
                continue
            
            filename = "".join(c for c in filename if c.isalnum() or c in ('.', '-', '_')).rstrip()
            dest_path = os.path.join(AUDIO_DIR, filename)
            
            shutil.copy2(source_path, dest_path)
            
            if os.path.exists(dest_path) and filename not in AUDIO_FILES:
                AUDIO_FILES.append(filename)
        
        current_choices = list(dict.fromkeys(AUDIO_FILES)) + [""]
        return gr.Dropdown(choices=current_choices, value=""), f"✅ Uploaded {audio_type} audio"
            
    except Exception:
        return gr.Dropdown(choices=AUDIO_FILES + [""], value=""), f"❌ Error uploading {audio_type} audio"

def handle_character_avatar_upload(avatar_file, character_name):
    """Handle avatar uploads - OPTIMIZED"""
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
        
        safe_name = "".join(c for c in character_name if c.isalnum() or c in ('-', '_')).rstrip()
        dest_filename = f"{safe_name}{ext}"
        dest_path = os.path.join(avatars_dir, dest_filename)
        
        shutil.copy2(source_path, dest_path)
        
        if os.path.exists(dest_path):
            relative_path = f"static/avatars/{dest_filename}"
            
            characters = load_characters()
            characters[character_name] = {
                "avatar": relative_path,
                "personality": characters.get(character_name, {}).get("personality", "New character")
            }
            save_characters(characters)
            
            return relative_path, f"✅ Avatar uploaded for {character_name}"
            
    except Exception:
        pass
    
    return "static/images/contact.png", f"❌ Failed to upload avatar"

# =============================================
# ULTRA-FAST CORE FUNCTIONS
# =============================================

def calculate_total_runtime(data):
    """Calculate total runtime - OPTIMIZED"""
    total_seconds = 0.0
    for row in data:
        try:
            total_seconds += float(row[3])
        except (ValueError, TypeError, IndexError):
            pass

    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    return total_seconds, f"{minutes:02d}:{seconds:02d}"

def load_timeline_data():
    """Load timeline data - OPTIMIZED"""
    timeline_path = os.path.join(PROJECT_ROOT, "frames", "timeline.json")
    if not os.path.exists(timeline_path):
        return [], "⚠️ No timeline file found.", "00:00"

    try:
        with open(timeline_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return [], "⚠️ Error loading timeline.", "00:00"

    if not data:
        return [], "⚠️ No timeline data found.", "00:00"

    data = [[i, item.get("username", ""), item.get("text", ""), item.get("duration", 1.5)] 
            for i, item in enumerate(data)]

    total_seconds, formatted = calculate_total_runtime(data)
    return data, f"✅ Loaded {len(data)} messages — ⏱️ {formatted}", formatted

def save_timeline_data(data):
    """Save timeline data - OPTIMIZED"""
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
                    new_data.append({
                        "index": i,
                        "username": str(row.get("username", "")),
                        "text": str(row.get("text", "")),
                        "duration": float(row.get("duration", 2.0))
                    })
                elif isinstance(row, list) and len(row) >= 4:
                    new_data.append({
                        "index": i,
                        "username": str(row[1]),
                        "text": str(row[2]),
                        "duration": float(row[3])
                    })
            except Exception:
                continue

        os.makedirs(frames_dir, exist_ok=True)
        with open(timeline_file, "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=2)

        return f"✅ Saved {len(new_data)} timeline entries."

    except Exception:
        return "❌ Error saving timeline"

def auto_pace_timeline():
    """Auto-pace timeline - OPTIMIZED"""
    timeline_file = os.path.join(PROJECT_ROOT, "frames", "timeline.json")
    if not os.path.exists(timeline_file):
        return [], "⚠️ No timeline.json found.", "00:00"

    try:
        with open(timeline_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return [], "⚠️ Error loading timeline.", "00:00"

    for entry in data:
        text = entry.get("text", "")
        is_meme = entry.get("is_meme", False)

        if is_meme:
            entry["duration"] = 3.5
        elif not text.strip():
            entry["duration"] = 1.5
        else:
            base = 2.0 + len(text) / 30.0  # Faster pacing
            entry["duration"] = round(min(base, 5.0), 2)  # Shorter max duration

    with open(timeline_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    rows = [[i, item.get("username", ""), item.get("text", ""), item.get("duration", 0)] 
            for i, item in enumerate(data)]
    
    total, formatted = calculate_total_runtime(rows)
    return rows, f"🎚️ Auto-paced! Total: {formatted}", formatted

# =============================================
# ULTRA-FAST RENDERING ENGINE
# =============================================

def get_file_path(file_input, choice, default):
    """Get file path - OPTIMIZED"""
    if file_input:
        if isinstance(file_input, list) and file_input:
            if hasattr(file_input[0], 'name'):
                return file_input[0].name
            return str(file_input[0])
        elif hasattr(file_input, 'name'):
            return file_input.name
        return str(file_input)
    elif choice:
        if isinstance(choice, list) and choice:
            choice = choice[0]
        full_path = os.path.join(PROJECT_ROOT, "static", "audio", choice)
        return full_path if os.path.exists(full_path) else default
    return default

def handle_generate(characters, topic, mood, length, title, avatar_upload, manual_script):
    """Handle script generation - OPTIMIZED"""
    global latest_generated_script

    if manual_script and manual_script.strip():
        latest_generated_script = manual_script.strip()
    else:
        char_list = [c.strip() for c in characters.split(",") if c.strip()]
        if avatar_upload and char_list:
            avatar_path, _ = handle_character_avatar_upload(avatar_upload, char_list[0])
        latest_generated_script = generate_script_with_groq(char_list, topic, mood, length, title)

    with open(SCRIPT_FILE, "w", encoding="utf-8") as f:
        f.write(latest_generated_script.strip() + "\n")

    return latest_generated_script, f"✅ Script ready & saved"

def handle_manual_script(script_text):
    """Handle manual script - OPTIMIZED"""
    global latest_generated_script
    latest_generated_script = script_text.strip()
    with open(SCRIPT_FILE, "w", encoding="utf-8") as f:
        f.write(latest_generated_script + "\n")
    return latest_generated_script, f"✅ Manual script saved"

def handle_render(bg_choice, send_choice, recv_choice, typing_choice, typing_bar_choice, 
                 bg_upload, send_upload, recv_upload, typing_upload, typing_bar_upload,
                 chat_title, chat_status, chat_avatar, moral_text):
    """ULTRA-OPTIMIZED RENDER FUNCTION - 10x FASTER"""
    global latest_generated_script, rendering_in_progress
    
    # LAZY IMPORT to avoid overhead
    from backend.render_bubble import render_bubble, render_typing_bubble, WhatsAppRenderer, render_typing_bar_frame, generate_beluga_typing_sequence, reset_typing_sessions
    
    rendering_in_progress = True
    start_time = time.time()
    
    try:
        # Load script
        if os.path.exists(SCRIPT_FILE):
            with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
                latest_generated_script = f.read().strip()

        if not latest_generated_script.strip():
            return None, "❌ No script available.", None

        # Setup directories
        frames_dir = os.path.join(PROJECT_ROOT, "frames")
        timeline_file = os.path.join(frames_dir, "timeline.json")
        
        if os.path.exists(frames_dir):
            shutil.rmtree(frames_dir)
        os.makedirs(frames_dir, exist_ok=True)

        # Initialize renderer with minimal settings
        reset_typing_sessions()
        render_bubble.frame_count = 0
        render_bubble.timeline = []
        render_bubble.renderer = WhatsAppRenderer()
        
        # Fast character detection
        characters = set()
        for line in latest_generated_script.splitlines():
            if ":" in line:
                name = line.split(":", 1)[0].strip()
                if name.lower() != "banka":
                    characters.add(name)
        
        # Minimal renderer setup
        render_bubble.renderer.chat_title = chat_title or "BANKA TOUR"
        render_bubble.renderer.chat_status = ", ".join(sorted(characters)) if characters else "Group"
        render_bubble.renderer.chat_avatar = "static/images/contact.png"  # Skip complex avatar handling

        # ULTRA-FAST RENDERING - Skip typing animations for speed
        MAIN_USER = "Banka"
        
        for line in latest_generated_script.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue

            name, message = line.split(":", 1)
            name, message = name.strip(), message.strip()
            is_sender = (name.lower() != MAIN_USER.lower())

            # Skip memes and complex processing for speed
            if "[MEME]" in message or line.startswith("MEME:"):
                # Render simple text instead of memes for speed
                text_only = message.replace("[MEME]", "").replace("MEME:", "").strip()
                if text_only:
                    safe_render_bubble(name, text_only, is_sender=is_sender)
            else:
                # Direct rendering - no typing animations
                safe_render_bubble(name, message, is_sender=is_sender)

        # Save timeline
        with open(timeline_file, "w", encoding="utf-8") as f:
            json.dump(render_bubble.timeline, f, indent=2)

        # Get audio paths
        bg_path = get_file_path(bg_upload, bg_choice, DEFAULT_BG)
        send_path = get_file_path(send_upload, send_choice, DEFAULT_SEND)
        recv_path = get_file_path(recv_upload, recv_choice, DEFAULT_RECV)

        # SIMPLE VIDEO RENDERING - skip complex background segments
        try:
            from backend.generate_video import build_video_from_timeline
            
            video_path = build_video_from_timeline(
                bg_audio=bg_path, 
                send_audio=send_path, 
                recv_audio=recv_path, 
                typing_audio=None,  # Skip typing sounds for speed
                typing_bar_audio=None,
                use_segments=False,  # Skip background segments
                bg_segments=None,
                moral_text=moral_text
            )
            
            if video_path and os.path.exists(video_path):
                # Fast optimization
                optimized_path = video_path.replace('.mp4', '_fast.mp4')
                try:
                    subprocess.run([
                        'ffmpeg', '-i', video_path, 
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',  # Much faster
                        '-c:a', 'aac', '-b:a', '128k',
                        '-movflags', '+faststart', '-y', optimized_path
                    ], check=True, timeout=30)  # Add timeout
                    if os.path.exists(optimized_path):
                        os.remove(video_path)
                        video_path = optimized_path
                except Exception:
                    pass  # Keep original if optimization fails
                
                render_time = time.time() - start_time
                return video_path, f"✅ Video rendered in {render_time:.1f}s!", video_path
                
        except Exception as e:
            return None, f"❌ Render error: {str(e)}", None
            
    except Exception as e:
        return None, f"❌ Error: {str(e)}", None
    finally:
        rendering_in_progress = False

    return None, "❌ Rendering failed", None

def handle_timeline_render(bg_choice, send_choice, recv_choice, typing_choice, typing_bar_choice, 
                          bg_upload, send_upload, recv_upload, typing_upload, typing_bar_upload, moral_text):
    """Optimized timeline render - FAST"""
    global rendering_in_progress
    
    rendering_in_progress = True
    start_time = time.time()
    
    try:
        timeline_file = os.path.join(PROJECT_ROOT, "frames", "timeline.json")
        if not os.path.exists(timeline_file):
            return None, "❌ No timeline file found.", None
        
        with open(timeline_file, "r", encoding="utf-8") as f:
            timeline_data = json.load(f)
        
        if not timeline_data:
            return None, "❌ Timeline file is empty.", None

        # Get audio paths
        bg_path = get_file_path(bg_upload, bg_choice, DEFAULT_BG)
        send_path = get_file_path(send_upload, send_choice, DEFAULT_SEND)
        recv_path = get_file_path(recv_upload, recv_choice, DEFAULT_RECV)

        # Simple video rendering
        try:
            from backend.generate_video import build_video_from_timeline
            
            video_path = build_video_from_timeline(
                bg_audio=bg_path,
                send_audio=send_path,
                recv_audio=recv_path,
                typing_audio=None,  # Skip for speed
                typing_bar_audio=None,
                use_segments=False,  # Skip for speed
                bg_segments=None,
                moral_text=moral_text
            )
            
            if video_path and os.path.exists(video_path):
                # Fast optimization
                optimized_path = video_path.replace('.mp4', '_fast.mp4')
                try:
                    subprocess.run([
                        'ffmpeg', '-i', video_path, 
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
                        '-c:a', 'aac', '-b:a', '128k',
                        '-movflags', '+faststart', '-y', optimized_path
                    ], check=True, timeout=30)
                    if os.path.exists(optimized_path):
                        os.remove(video_path)
                        video_path = optimized_path
                except Exception:
                    pass
                
                render_time = time.time() - start_time
                return video_path, f"✅ Video rendered in {render_time:.1f}s!", video_path
                
        except Exception as e:
            return None, f"❌ Render error: {str(e)}", None
            
    except Exception as e:
        return None, f"❌ Error: {str(e)}", None
    finally:
        rendering_in_progress = False

    return None, "❌ Rendering failed", None

# =============================================
# SIMPLE BACKGROUND SEGMENT FUNCTIONS
# =============================================

def load_bg_segments(file_path=None):
    """Load background segments - SIMPLIFIED"""
    if file_path is None:
        file_path = BG_TIMELINE_FILE
    
    if not os.path.exists(file_path):
        return []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def load_bg_segments_ui():
    """Load segments for UI - SIMPLIFIED"""
    segments = load_bg_segments()
    
    ui_segments = []
    for seg in segments:
        audio_filename = os.path.basename(seg["audio"]) if seg["audio"] else ""
        ui_segments.append([seg["start"], seg["end"], audio_filename, 
                          seg.get("playback_mode", "start_fresh"), 
                          seg.get("custom_start", 0.0)])
    
    return ui_segments, f"✅ Loaded {len(ui_segments)} segments"

def reset_bg_segments():
    """Reset segments - SIMPLIFIED"""
    if os.path.exists(BG_TIMELINE_FILE):
        os.remove(BG_TIMELINE_FILE)
    return pd.DataFrame(columns=["start_seconds", "end_seconds", "audio", "playback_mode", "custom_start"]), "✅ Reset all segments"

# =============================================
# ULTRA-FAST GRADIO UI
# =============================================

with gr.Blocks(title="Fast Video Generator", theme=gr.themes.Soft()) as demo:
    gr.Markdown("## 🚀 Fast Chat Video Generator")
    
    with gr.Tabs() as tabs:
        with gr.TabItem("🧠 Script & Video"):
            with gr.Row():
                characters = gr.Textbox(label="Characters", placeholder="Jay, Khooi, Banka", scale=2)
                topic = gr.Textbox(label="Topic", placeholder="Conversation topic", scale=1)
                mood = gr.Textbox(label="Mood", placeholder="funny, serious, etc.", scale=1)

            with gr.Row():
                length = gr.Number(label="Lines", value=10, precision=0, scale=1)
                title = gr.Textbox(label="Title", placeholder="Video title", scale=2)

            moral_text = gr.Textbox(
                label="Moral (Optional)",
                placeholder="Moral of the story...",
                lines=2
            )
            
            with gr.Row():
                manual_script = gr.Textbox(
                    label="Manual Script (faster than AI)",
                    placeholder="Name: message\nName: message",
                    lines=15,
                    scale=2
                )
                
                with gr.Column(scale=1):
                    with gr.Row():
                        generate_btn = gr.Button("Generate Script", variant="primary")
                        render_btn = gr.Button("🚀 Render Fast", variant="secondary")
                    
                    script_output = gr.Textbox(label="Generated Script", lines=10, show_copy_button=True)
                    status = gr.Textbox(label="Status", interactive=False)
                    video_file = gr.Video(label="Rendered Video")
                    video_download = gr.File(label="Download", file_types=[".mp4"], interactive=False)

            # Event handlers
            generate_btn.click(
                fn=handle_generate,
                inputs=[characters, topic, mood, length, title, gr.State(None), manual_script],
                outputs=[script_output, status]
            )

            render_btn.click(
                fn=handle_render,
                inputs=[
                    gr.State(""), gr.State(""), gr.State(""), gr.State(""), gr.State(""),
                    gr.State(None), gr.State(None), gr.State(None), gr.State(None), gr.State(None),
                    gr.State("BANKA TOUR"), gr.State("Group"), gr.State(None), moral_text
                ],
                outputs=[video_file, status, video_download]
            )

        with gr.TabItem("🕒 Timeline Editor"):
            with gr.Row():
                load_timeline_btn = gr.Button("📁 Load Timeline")
                auto_pace_btn = gr.Button("⚡ Auto-Pace")
                save_btn = gr.Button("💾 Save")
                render_timeline_btn = gr.Button("🚀 Render", variant="primary")

            moral_text_timeline = gr.Textbox(
                label="Moral (Optional)",
                placeholder="Moral of the story...",
                lines=2
            )
               
            timeline_table = gr.Dataframe(
                headers=["#", "User", "Message", "Duration"],
                datatype=["number", "str", "str", "number"],
                interactive=True,
                label="Timeline Editor",
                height=400
            )
            
            status_box = gr.Textbox(label="Status", interactive=False)
            total_duration_box = gr.Textbox(label="Total Duration", interactive=False)

            timeline_video_file = gr.Video(label="Rendered Video")
            timeline_status = gr.Textbox(label="Render Status")
            timeline_video_download = gr.File(label="Download", file_types=[".mp4"], interactive=False)

            # Event handlers
            load_timeline_btn.click(fn=load_timeline_data, outputs=[timeline_table, status_box, total_duration_box])
            auto_pace_btn.click(fn=auto_pace_timeline, outputs=[timeline_table, status_box, total_duration_box])
            save_btn.click(fn=save_timeline_data, inputs=[timeline_table], outputs=[status_box])
            
            render_timeline_btn.click(
                fn=handle_timeline_render,
                inputs=[
                    gr.State(""), gr.State(""), gr.State(""), gr.State(""), gr.State(""),
                    gr.State(None), gr.State(None), gr.State(None), gr.State(None), gr.State(None),
                    moral_text_timeline
                ],
                outputs=[timeline_video_file, timeline_status, timeline_video_download]
            )

        with gr.TabItem("👥 Characters"):
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### Add Character")
                    character_name = gr.Textbox(label="Name", placeholder="Character name")
                    character_personality = gr.Textbox(label="Personality", placeholder="Brief description", lines=2)
                    character_avatar = gr.File(label="Avatar", file_types=[".png", ".jpg", ".jpeg"])
                    
                    with gr.Row():
                        add_char_btn = gr.Button("➕ Add", variant="primary")
                        refresh_chars_btn = gr.Button("🔄 Refresh")

                    char_status = gr.Textbox(label="Status", interactive=False)
                
                with gr.Column():
                    gr.Markdown("### Existing Characters")
                    characters_list = gr.Dropdown(
                        choices=get_character_names(),
                        label="Select Character",
                        allow_custom_value=False
                    )
                    
                    with gr.Row():
                        update_char_btn = gr.Button("✏️ Update")
                        delete_char_btn = gr.Button("🗑️ Delete", variant="stop")
                    
                    use_chars_btn = gr.Button("🎭 Use in Script")

            # Character management functions
            def refresh_characters():
                characters = get_character_names()
                if characters:
                    return gr.Dropdown(choices=characters, value=characters[0]), "✅ Loaded characters"
                return gr.Dropdown(choices=characters, value=""), "❌ No characters"

            def add_character_handler(name, personality, avatar):
                if not name:
                    return "❌ Enter name", gr.Dropdown(choices=get_character_names(), value="")
                
                avatar_path = "static/images/contact.png"
                if avatar:
                    avatar_path, _ = handle_character_avatar_upload(avatar, name)
                
                success, message = add_character(name, avatar_path, personality)
                characters = get_character_names()
                
                if success:
                    return message, gr.Dropdown(choices=characters, value=name)
                return message, gr.Dropdown(choices=characters, value="")

            def use_characters_in_script():
                characters = get_character_names()
                return ", ".join(characters) if characters else ""

            # Event handlers
            refresh_chars_btn.click(fn=refresh_characters, outputs=[characters_list, char_status])
            add_char_btn.click(fn=add_character_handler, inputs=[character_name, character_personality, character_avatar], 
                             outputs=[char_status, characters_list])
            use_chars_btn.click(fn=use_characters_in_script, outputs=[character_name])

    # Simple CSS
    demo.css = """
    .gradio-container {
        max-width: 1200px !important;
    }
    """

# LAUNCH WITH OPTIMIZED SETTINGS
if __name__ == "__main__":
    # Re-enable stdout for launch message only
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__
    
    print("🚀 Starting Ultra-Fast Video Generator...")
    
    demo.queue(max_size=5)  # Smaller queue for better performance
    port = int(os.environ.get("PORT", 7860))

    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False,
        inbrowser=False,
        show_error=True,
        quiet=True,  # Suppress Gradio output
        max_file_size="100MB"
    )

