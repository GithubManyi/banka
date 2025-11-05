import subprocess
import sys
import os
import traceback
import tempfile
import shutil
from pathlib import Path
import base64
import asyncio
import json
import pandas as pd
import time
import threading
import math
import random
import psutil
import signal

# =============================================
# ENHANCED CHROMIUM/CHROME SUPPRESSION
# =============================================

# Apply the same suppression as in render_bubble.py for consistency
os.environ['DBUS_SESSION_BUS_ADDRESS'] = ''
os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = ''
os.environ['DISABLE_DEV_SHM'] = 'true'
os.environ['ENABLE_CRASH_REPORTER'] = 'false'
os.environ['CHROME_HEADLESS'] = 'true'
os.environ['NO_AT_BRIDGE'] = '1'

# Disable GPU and other unnecessary features
os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'
os.environ['GALLIUM_DRIVER'] = 'llvmpipe'

# Disable various system integrations
os.environ['XDG_RUNTIME_DIR'] = '/tmp/runtime'
os.environ['XDG_CACHE_HOME'] = '/tmp/cache'
os.environ['HOME'] = '/tmp'

# Resource limits to prevent thread exhaustion
os.environ['GRADIO_ANALYTICS_ENABLED'] = 'False'
os.environ['BOKEH_Resources'] = 'minified'

# Reduce logging verbosity
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# =============================================
# CONTAINER STABILITY FIXES
# =============================================

def signal_handler(sig, frame):
    print(f"🚨 Received signal {sig}, but continuing...")
    # Don't exit on SIGTERM/SIGINT in container
    if sig in [signal.SIGTERM, signal.SIGINT]:
        print("🛑 Ignoring termination signal to maintain container stability")
        return

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# =============================================
# RESOURCE MANAGEMENT
# =============================================

def optimize_system_limits():
    """Optimize system limits to prevent resource exhaustion"""
    try:
        import resource
        # Increase resource limits
        resource.setrlimit(resource.RLIMIT_NOFILE, (4096, 8192))
        print("✅ System resource limits optimized")
    except Exception as e:
        print(f"⚠️ Could not optimize system limits: {e}")

optimize_system_limits()

def monitor_resources():
    """Monitor system resources"""
    try:
        memory = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=0.1)
        active_threads = threading.active_count()
        
        print(f"📊 Resource Monitor - Memory: {memory.percent}% | CPU: {cpu_percent}% | Threads: {active_threads}")
        
        # Warn if resources are high
        if memory.percent > 85:
            print("🚨 High memory usage detected")
        if active_threads > 50:
            print("🚨 High thread count detected")
            
    except Exception as e:
        print(f"⚠️ Resource monitoring failed: {e}")

# =============================================
# FFMPEG CHECK
# =============================================

try:
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
    if result.returncode != 0:
        print("ffmpeg command failed")
    else:
        print("✅ FFmpeg is available")
except Exception:
    print("ffmpeg check failed")

# =============================================
# IMPORTS WITH ENHANCED ERROR HANDLING
# =============================================

try:
    import gradio as gr
    print("✅ Gradio imported successfully")
except ImportError:
    print("Failed to import gradio")
    sys.exit(1)

# Import custom modules with error handling
try:
    from backend.generate_script import generate_script_with_groq
    print("✅ Script generation module imported")
except ImportError as e:
    print(f"⚠️ Script generation module not available: {e}")
    generate_script_with_groq = None

try:
    from backend.generate_video import build_video_from_timeline
    print("✅ Video generation module imported")
except ImportError as e:
    print(f"⚠️ Video generation module not available: {e}")
    build_video_from_timeline = None

try:
    from backend.avatar_handler import save_uploaded_avatar
    print("✅ Avatar handler imported")
except ImportError as e:
    print(f"⚠️ Avatar handler not available: {e}")
    save_uploaded_avatar = None

# Enhanced render bubble import with better error handling
try:
    from backend.render_bubble import render_bubble, render_typing_bubble, WhatsAppRenderer, render_typing_bar_frame, generate_beluga_typing_sequence, reset_typing_sessions
    
    # Initialize renderer state with resource limits
    render_bubble.frame_count = 0
    render_bubble.timeline = []
    render_bubble.renderer = WhatsAppRenderer()
    print("✅ Render bubble modules imported successfully")
    
except ImportError as e:
    print(f"⚠️ Could not import render_bubble modules: {e}")
    # Create enhanced dummy functions
    class WhatsAppRenderer:
        def __init__(self, *args, **kwargs):
            self.chat_title = "Chat"
            self.chat_status = "Online"
            self.chat_avatar = None
            
    def render_bubble(*args, **kwargs):
        # Create frames directory if it doesn't exist
        frames_dir = os.path.join(PROJECT_ROOT, "frames")
        os.makedirs(frames_dir, exist_ok=True)
        return os.path.join(frames_dir, "frame_0000.png")
        
    def render_typing_bubble(*args, **kwargs):
        frames_dir = os.path.join(PROJECT_ROOT, "frames")
        os.makedirs(frames_dir, exist_ok=True)
        return os.path.join(frames_dir, "frame_0000.png")
        
    def render_typing_bar_frame(*args, **kwargs):
        frames_dir = os.path.join(PROJECT_ROOT, "frames")
        os.makedirs(frames_dir, exist_ok=True)
        return os.path.join(frames_dir, "frame_0000.png")
        
    def generate_beluga_typing_sequence(*args, **kwargs):
        return []
        
    def reset_typing_sessions():
        pass
    
    # Set up the global variables
    render_bubble.frame_count = 0
    render_bubble.timeline = []
    render_bubble.renderer = WhatsAppRenderer()

# Groq client
try:
    from groq import Groq
    groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    print("✅ Groq client initialized")
except ImportError:
    print("⚠️ Groq client not available")
    groq_client = None
except Exception as e:
    print(f"⚠️ Groq client initialization failed: {e}")
    groq_client = None

# Static server imports
try:
    from static_server import get_static_path, get_avatar_path
    print("✅ Static server modules imported")
except ImportError:
    print("⚠️ Static server modules not available, using fallbacks")
    def get_static_path(filename):
        return os.path.join(PROJECT_ROOT, "static", filename)
    
    def get_avatar_path(username):
        return os.path.join(PROJECT_ROOT, "static", "images", "contact.png")

# =============================================
# CONFIGURATION
# =============================================

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

# =============================================
# ENHANCED ASSET MANAGEMENT
# =============================================

def create_default_assets():
    """Create default assets if they don't exist with better error handling"""
    static_dirs = [
        "static/images",
        "static/avatars", 
        "static/audio",
        "frames",
        "temp"
    ]
    
    for dir_path in static_dirs:
        full_path = os.path.join(PROJECT_ROOT, dir_path)
        try:
            os.makedirs(full_path, exist_ok=True)
            print(f"✅ Created directory: {full_path}")
        except Exception as e:
            print(f"⚠️ Could not create directory {full_path}: {e}")
    
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
            print("✅ Created default contact avatar")
        except ImportError:
            # Create empty file as fallback
            open(contact_path, 'a').close()
            print("⚠️ PIL not available, created placeholder avatar file")
        except Exception as e:
            print(f"⚠️ Could not create default avatar: {e}")
            open(contact_path, 'a').close()

create_default_assets()

# =============================================
# CHARACTER MANAGEMENT SYSTEM
# =============================================

def load_characters():
    """Load characters from JSON file"""
    if os.path.exists(CHARACTERS_FILE):
        try:
            with open(CHARACTERS_FILE, "r", encoding="utf-8") as f:
                characters = json.load(f)
            return characters
        except Exception:
            return {}
    else:
        default_characters = {
            "Jay": {"avatar": "static/images/contact.png", "personality": "Funny and energetic"},
            "Khooi": {"avatar": "static/images/contact.png", "personality": "Wise and calm"},
            "Banka": {"avatar": "static/images/contact.png", "personality": "Adventurous and brave"},
            "Brian": {"avatar": "static/images/contact.png", "personality": "Tech-savvy and logical"},
            "Alex": {"avatar": "static/images/contact.png", "personality": "Creative and artistic"},
            "Shiro": {"avatar": "static/images/contact.png", "personality": "Mysterious and quiet"},
            "Paula": {"avatar": "static/images/contact.png", "personality": "Friendly and outgoing"}
        }
        save_characters(default_characters)
        return default_characters

def save_characters(characters):
    """Save characters to JSON file"""
    try:
        with open(CHARACTERS_FILE, "w", encoding="utf-8") as f:
            json.dump(characters, f, indent=2)
        return True
    except Exception:
        return False

def add_character(name, avatar_path, personality):
    """Add a new character"""
    characters = load_characters()
    
    if name in characters:
        return False, f"Character '{name}' already exists!"
    
    characters[name] = {
        "avatar": avatar_path,
        "personality": personality
    }
    
    if save_characters(characters):
        return True, f"Character '{name}' added successfully!"
    else:
        return False, f"Failed to save character '{name}'"

def update_character(name, avatar_path, personality):
    """Update an existing character"""
    characters = load_characters()
    
    if name not in characters:
        return False, f"Character '{name}' not found!"
    
    characters[name] = {
        "avatar": avatar_path,
        "personality": personality
    }
    
    if save_characters(characters):
        return True, f"Character '{name}' updated successfully!"
    else:
        return False, f"Failed to update character '{name}'"

def delete_character(name):
    """Delete a character"""
    characters = load_characters()
    
    if name not in characters:
        return False, f"Character '{name}' not found!"
    
    del characters[name]
    
    if save_characters(characters):
        return True, f"Character '{name}' deleted successfully!"
    else:
        return False, f"Failed to delete character '{name}'"

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

def get_character_avatar_path(username):
    """Return web path for avatar with better error handling"""
    default_web = "static/images/contact.png"
    default_fs = os.path.join(PROJECT_ROOT, default_web)
   
    if not os.path.exists(default_fs):
        create_default_assets()
   
    username_clean = username.strip()
   
    # Check character JSON first
    characters = load_characters()
    if username_clean in characters:
        avatar_web = characters[username_clean].get("avatar", "")
        if avatar_web:
            avatar_fs = os.path.join(PROJECT_ROOT, avatar_web)
            if os.path.exists(avatar_fs):
                return avatar_web
   
    # Check avatars directory
    avatars_dir = os.path.join(PROJECT_ROOT, "static", "avatars")
    for ext in ['.png', '.jpg', '.jpeg', '.gif']:
        avatar_path = os.path.join(avatars_dir, f"{username_clean}{ext}")
        if os.path.exists(avatar_path):
            return f"static/avatars/{username_clean}{ext}"
   
    return "INITIALS"

def encode_avatar_for_html(avatar_path):
    """Convert avatar image to base64 for HTML display"""
    if not avatar_path or not os.path.exists(avatar_path):
        return None
    
    try:
        with open(avatar_path, "rb") as f:
            avatar_data = base64.b64encode(f.read()).decode("utf-8")
        
        mime_type = "image/jpeg"
        if avatar_path.lower().endswith('.png'):
            mime_type = "image/png"
        elif avatar_path.lower().endswith('.gif'):
            mime_type = "image/gif"
        
        return f"data:{mime_type};base64,{avatar_data}"
    except Exception:
        return None

# =============================================
# AVATAR GENERATION SYSTEM
# =============================================

def generate_avatar_with_initials(username, size=200):
    """Generate a WhatsApp-style avatar with initials"""
    def get_initials(name):
        words = name.strip().split()
        if len(words) == 0:
            return "?"
        elif len(words) == 1:
            return name[:1].upper()
        else:
            return (words[0][0] + words[-1][0]).upper()
    
    initials = get_initials(username)
    
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        colors = [
            '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
            '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9',
            '#F8C471', '#82E0AA', '#F1948A', '#85C1E9', '#D7BDE2'
        ]
        
        color_index = hash(username) % len(colors)
        background_color = colors[color_index]
        
        img = Image.new('RGB', (size, size), color=background_color)
        draw = ImageDraw.Draw(img)
        
        try:
            if len(initials) == 1:
                font_size = int(size * 0.75)
            else:
                font_size = int(size * 0.65)
            
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 
                "/System/Library/Fonts/Helvetica.ttc",
                "Arial"
            ]
            
            font = None
            for font_path in font_paths:
                try:
                    font = ImageFont.truetype(font_path, font_size)
                    break
                except:
                    continue
            
            if font is None:
                try:
                    font = ImageFont.load_default()
                except:
                    font = None
                
        except Exception:
            font = None
        
        if font:
            try:
                bbox = draw.textbbox((0, 0), initials, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                x = (size - text_width) // 2
                y = (size - text_height) // 2
                
                outline_width = max(2, size // 100)
                for x_offset in [-outline_width, 0, outline_width]:
                    for y_offset in [-outline_width, 0, outline_width]:
                        if x_offset != 0 or y_offset != 0:
                            draw.text((x + x_offset, y + y_offset), initials, fill='rgba(0,0,0,0.3)', font=font)
                
                draw.text((x, y), initials, fill='white', font=font)
                
            except Exception:
                x = size // 4
                y = size // 4
                draw.text((x, y), initials, fill='white', font=font)
        else:
            x = size // 6
            y = size // 4
            for i in range(max(1, size // 50)):
                draw.text((x+i, y), initials, fill='white')
                draw.text((x, y+i), initials, fill='white')
        
        return img
        
    except ImportError:
        return create_fallback_avatar(username, size)
    except Exception:
        return create_fallback_avatar(username, size)

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
    
    if os.path.exists(avatar_path):
        return f"static/avatars/{avatar_filename}"
    
    avatar_image = generate_avatar_with_initials(username)
    if avatar_image:
        try:
            avatar_image.save(avatar_path, 'PNG')
            return f"static/avatars/{avatar_filename}"
        except Exception:
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
        
        if not os.path.exists(full_avatar_path):
            create_default_assets()
        
        return render_bubble(username, message, meme_path=meme_path, is_sender=is_sender, is_read=is_read)
        
    except FileNotFoundError:
        create_default_assets()
        return render_bubble(username, message, meme_path=meme_path, is_sender=is_sender, is_read=is_read)
    except Exception as e:
        raise

def get_character_avatar_preview(character_name):
    """Get avatar preview for character management"""
    if not character_name:
        return "static/images/contact.png"
    
    avatar_path = get_character_avatar_path(character_name)
    
    if avatar_path == "INITIALS" or avatar_path == "static/images/contact.png":
        initial_avatar_path = get_or_create_initial_avatar(character_name)
        if initial_avatar_path and os.path.exists(os.path.join(PROJECT_ROOT, initial_avatar_path)):
            return initial_avatar_path
    
    if avatar_path and os.path.exists(os.path.join(PROJECT_ROOT, avatar_path)):
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

# =============================================
# FILE UPLOAD FUNCTIONS
# =============================================

def optimize_upload_settings():
    """Optimize settings for better file upload handling"""
    os.environ["GRADIO_MAX_FILE_SIZE"] = "100mb"
    os.environ["GRADIO_TEMP_DIR"] = "/tmp"
    os.environ["GRADIO_QUEUE_TIMEOUT"] = "300"
    os.environ["GRADIO_QUEUE_DEFAULT_CONCURRENCY"] = "1"

optimize_upload_settings()

def check_file_size(file_path, max_size_mb=50):
    """Check if file size is within limits"""
    try:
        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)
        if file_size_mb > max_size_mb:
            return False, f"File too large: {file_size_mb:.2f}MB (max {max_size_mb}MB)"
        return True, f"File size OK: {file_size_mb:.2f}MB"
    except Exception as e:
        return False, f"Error checking file size: {e}"

def handle_audio_upload_fixed(audio_file, audio_type):
    """Handle audio uploads with better error handling"""
    if not audio_file:
        return gr.Dropdown(choices=AUDIO_FILES + [""], value=""), f"No {audio_type} audio uploaded."
    
    try:
        os.makedirs(AUDIO_DIR, exist_ok=True)
        
        files_to_process = []
        if isinstance(audio_file, list):
            files_to_process = audio_file
        else:
            files_to_process = [audio_file]
        
        statuses = []
        new_files = []
        
        for f in files_to_process:
            if hasattr(f, 'name'):
                source_path = f.name
                if hasattr(f, 'orig_name'):
                    filename = f.orig_name
                else:
                    filename = os.path.basename(f.name)
            else:
                source_path = str(f)
                filename = os.path.basename(str(f))
            
            if not os.path.exists(source_path):
                statuses.append(f"File not found: {filename}")
                continue
            
            try:
                file_size = os.path.getsize(source_path)
                is_readable = os.access(source_path, os.R_OK)
                
                if file_size == 0:
                    statuses.append(f"Empty file: {filename}")
                    continue
                    
            except Exception:
                statuses.append(f"Error checking file: {filename}")
                continue
            
            original_filename = filename
            filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
            
            dest_path = os.path.join(AUDIO_DIR, filename)
            audio_dir_writable = os.access(AUDIO_DIR, os.W_OK)
            
            if not audio_dir_writable:
                statuses.append(f"Directory not writable: {filename}")
                continue
            
            try:
                shutil.copy2(source_path, dest_path)
                
                if os.path.exists(dest_path):
                    copied_size = os.path.getsize(dest_path)
                    
                    if copied_size > 0:
                        if filename not in AUDIO_FILES:
                            AUDIO_FILES.append(filename)
                            new_files.append(filename)
                        statuses.append(filename)
                    else:
                        if os.path.exists(dest_path):
                            os.remove(dest_path)
                        statuses.append(f"Copy failed - empty: {filename}")
                else:
                    statuses.append(f"Copy failed - not found: {filename}")
                    
            except Exception:
                statuses.append(f"Error copying: {filename}")
                continue
        
        successful_uploads = [s for s in statuses if not s.startswith('❌') and not s.startswith('File') and not s.startswith('Empty') and not s.startswith('Error') and not s.startswith('Directory') and not s.startswith('Copy')]
        
        if successful_uploads:
            if len(successful_uploads) == 1:
                status_msg = f"Uploaded {audio_type} audio: {successful_uploads[0]}"
            else:
                status_msg = f"Uploaded {len(successful_uploads)} {audio_type} audios"
            
            unique_files = list(dict.fromkeys(AUDIO_FILES))
            current_choices = unique_files + [""]
            new_value = successful_uploads[0] if successful_uploads else ""
            
            return gr.Dropdown(choices=current_choices, value=new_value), status_msg
        else:
            error_msg = f"Failed to upload {audio_type} audio."
            return gr.Dropdown(choices=AUDIO_FILES + [""], value=""), error_msg
            
    except Exception as e:
        return gr.Dropdown(choices=AUDIO_FILES + [""], value=""), f"Error uploading {audio_type} audio: {str(e)}"

def handle_character_avatar_upload(avatar_file, character_name):
    """Handle avatar uploads for specific characters"""
    if not avatar_file or not character_name:
        return "static/images/contact.png", "No avatar or character name provided"
    
    try:
        avatars_dir = os.path.join(PROJECT_ROOT, "static", "avatars")
        os.makedirs(avatars_dir, exist_ok=True)
        
        if hasattr(avatar_file, 'name'):
            source_path = avatar_file.name
            ext = os.path.splitext(avatar_file.name)[1]
        else:
            source_path = str(avatar_file)
            ext = os.path.splitext(str(avatar_file))[1]
        
        size_ok, size_msg = check_file_size(source_path, max_size_mb=5)
        if not size_ok:
            return "static/images/contact.png", size_msg
        
        safe_name = "".join(c for c in character_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        dest_filename = f"{safe_name}{ext}"
        dest_path = os.path.join(avatars_dir, dest_filename)
        
        shutil.copy2(source_path, dest_path)
        
        if os.path.exists(dest_path):
            relative_path = f"static/avatars/{dest_filename}"
            
            characters = load_characters()
            if character_name in characters:
                characters[character_name]["avatar"] = relative_path
                save_characters(characters)
            else:
                characters[character_name] = {
                    "avatar": relative_path,
                    "personality": "New character"
                }
                save_characters(characters)
            
            return relative_path, f"Avatar uploaded for {character_name}"
        else:
            return "static/images/contact.png", f"Failed to upload avatar for {character_name}"
            
    except Exception as e:
        return "static/images/contact.png", f"Error uploading avatar: {str(e)}"

# =============================================
# FIXED FILE HANDLING FUNCTIONS
# =============================================

def get_file_path(file_input, choice, default):
    """Safely get file path from Gradio file input (handles lists)"""
    if file_input:
        if isinstance(file_input, list):
            if file_input and hasattr(file_input[0], 'name'):
                return file_input[0].name
            elif file_input:
                return str(file_input[0])
            else:
                return default
        elif hasattr(file_input, 'name'):
            return file_input.name
        else:
            return str(file_input)
    elif choice:
        if isinstance(choice, list) and choice:
            choice = choice[0]
        full_path = os.path.join(PROJECT_ROOT, "static", "audio", choice)
        return full_path if os.path.exists(full_path) else default
    else:
        return default

# =============================================
# ENHANCED RENDER FUNCTIONS WITH RESOURCE MANAGEMENT
# =============================================

def safe_render_with_limits(*args, **kwargs):
    """Wrapper for render functions with resource limits"""
    try:
        # Monitor resources before rendering
        monitor_resources()
        
        # Clear any temporary files before rendering
        temp_dir = os.path.join(PROJECT_ROOT, "temp")
        if os.path.exists(temp_dir):
            for file in os.listdir(temp_dir):
                try:
                    os.remove(os.path.join(temp_dir, file))
                except:
                    pass
        
        # Call the actual render function
        return render_bubble(*args, **kwargs)
    except Exception as e:
        print(f"Render error: {e}")
        # Return a fallback frame
        frames_dir = os.path.join(PROJECT_ROOT, "frames")
        os.makedirs(frames_dir, exist_ok=True)
        return os.path.join(frames_dir, "frame_fallback.png")

# Replace the original render_bubble with our safe version
original_render_bubble = render_bubble
render_bubble = safe_render_with_limits

# =============================================
# ENHANCED VIDEO RENDERING WITH BETTER ERROR HANDLING
# =============================================

def safe_build_video_from_timeline(*args, **kwargs):
    """Wrapper for video building with enhanced error handling"""
    try:
        if build_video_from_timeline:
            print("Starting video rendering process...")
            result = build_video_from_timeline(*args, **kwargs)
            if result and os.path.exists(result):
                print(f"Video successfully rendered: {result}")
                
                # Optimize the video
                try:
                    optimized_path = result.replace('.mp4', '_optimized.mp4')
                    print(f"Optimizing video: {result} -> {optimized_path}")
                    
                    # Use simpler ffmpeg command for better compatibility
                    cmd = [
                        'ffmpeg', '-i', result,
                        '-c:v', 'libx264', '-preset', 'medium', '-crf', '23',
                        '-c:a', 'aac', '-b:a', '128k',
                        '-movflags', '+faststart',
                        '-y', optimized_path
                    ]
                    
                    result_ffmpeg = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    if result_ffmpeg.returncode == 0 and os.path.exists(optimized_path):
                        # Remove original and use optimized
                        try:
                            os.remove(result)
                        except:
                            pass
                        print(f"Video optimization successful: {optimized_path}")
                        return optimized_path
                    else:
                        print(f"FFmpeg optimization failed: {result_ffmpeg.stderr}")
                        return result
                except Exception as e:
                    print(f"Optimization failed, using original: {e}")
                    return result
            else:
                print("Video rendering failed - no output file produced")
                return None
        else:
            print("Video rendering module not available")
            return None
    except Exception as e:
        print(f"Error in video rendering: {e}")
        traceback.print_exc()
        return None

# =============================================
# CORE APPLICATION FUNCTIONS
# =============================================

def calculate_total_runtime(data):
    total_seconds = 0.0
    cleaned_rows = []

    for row in data:
        try:
            duration = float(row[3])
        except (ValueError, TypeError, IndexError):
            duration = 0.0
        total_seconds += duration
        cleaned_rows.append(row)

    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    formatted = f"{minutes:02d}:{seconds:02d}"

    return total_seconds, formatted

def load_timeline_data():
    timeline_path = os.path.join(PROJECT_ROOT, "frames", "timeline.json")
    if not os.path.exists(timeline_path):
        return [], "No timeline file found.", "00:00"

    with open(timeline_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not data:
        return [], "No timeline data found.", "00:00"

    data = [[
        item.get("index", i),
        item.get("username", ""),
        item.get("text", ""),
        item.get("duration", 1.5)
    ] for i, item in enumerate(data)]

    total_seconds, formatted = calculate_total_runtime(data)
    return data, f"Loaded timeline ({len(data)} messages) — Total: {total_seconds:.1f}s ({formatted})", formatted

def start_auto_refresh(load_button, timeline_table, status_box, total_duration_box, interval=10):
    global auto_refresh_running, auto_refresh_thread, rendering_in_progress
    
    def loop():
        while auto_refresh_running:
            if rendering_in_progress:
                time.sleep(2)
                continue
            time.sleep(interval)
            try:
                load_button.click(fn=load_timeline_data, outputs=[timeline_table, status_box, total_duration_box])
            except Exception:
                pass
    
    if not auto_refresh_running:
        auto_refresh_running = True
        auto_refresh_thread = threading.Thread(target=loop, daemon=True)
        auto_refresh_thread.start()

def stop_auto_refresh():
    global auto_refresh_running
    auto_refresh_running = False

def save_timeline_data(data):
    frames_dir = os.path.join(PROJECT_ROOT, "frames")
    timeline_file = os.path.join(frames_dir, "timeline.json")

    try:
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        elif isinstance(data, pd.DataFrame):
            data = data.to_dict('records')
        elif not isinstance(data, list):
            return "Invalid data format."

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
            return "No valid timeline entries to save."

        os.makedirs(frames_dir, exist_ok=True)
        with open(timeline_file, "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=2)

        return f"Saved {len(new_data)} timeline entries."

    except Exception as e:
        return f"Error saving timeline: {e}"

def auto_pace_timeline():
    timeline_file = os.path.join(PROJECT_ROOT, "frames", "timeline.json")
    if not os.path.exists(timeline_file):
        return [], "No timeline.json found to auto-pace.", "00:00"

    with open(timeline_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    for entry in data:
        text = entry.get("text", "")
        is_meme = entry.get("is_meme", False)

        if is_meme:
            entry["duration"] = 3.5
        elif len(text.strip()) == 0:
            entry["duration"] = 1.5
        else:
            base = 2.0 + len(text) / 40.0
            if "?" in text or "!" in text:
                base += 0.5
            entry["duration"] = round(min(base, 6.0), 2)

    with open(timeline_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    rows = []
    for i, item in enumerate(data):
        rows.append([i, item.get("username", ""), item.get("text", ""), item.get("duration", 0)])

    total, formatted = calculate_total_runtime(rows)
    return rows, f"Auto-paced timeline! Total: {round(total, 2)}s (≈{formatted})", formatted

def emergency_fix_assets():
    """Emergency function to fix missing assets"""
    try:
        create_default_assets()
        
        audio_dir = os.path.join(PROJECT_ROOT, "static", "audio")
        if not os.listdir(audio_dir):
            silent_audio = os.path.join(audio_dir, "silent.mp3")
            subprocess.run([
                'ffmpeg', '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
                '-t', '1', '-q:a', '9', '-y', silent_audio
            ], capture_output=True)
        
        return "Emergency asset fix completed"
    except Exception as e:
        return f"Emergency fix failed: {e}"

def handle_generate(characters, topic, mood, length, title, avatar_upload, manual_script):
    global latest_generated_script

    if manual_script and manual_script.strip():
        latest_generated_script = manual_script.strip()
    else:
        char_list = [c.strip() for c in characters.split(",") if c.strip()]
        if avatar_upload and char_list:
            avatar_path, avatar_status = handle_character_avatar_upload(avatar_upload, char_list[0])
        
        if generate_script_with_groq:
            latest_generated_script = generate_script_with_groq(char_list, topic, mood, length, title)
        else:
            latest_generated_script = "AI script generation not available"

    with open(SCRIPT_FILE, "w", encoding="utf-8") as f:
        f.write(latest_generated_script.strip() + "\n")

    return latest_generated_script, f"Script ready & saved to {SCRIPT_FILE}"

def handle_manual_script(script_text):
    global latest_generated_script
    latest_generated_script = script_text.strip()
    with open(SCRIPT_FILE, "w", encoding="utf-8") as f:
        f.write(latest_generated_script + "\n")
    return latest_generated_script, f"Manual script saved to {SCRIPT_FILE}"

# SAFE WRAPPER FUNCTIONS TO HANDLE MISSING PARAMETERS
def safe_handle_render(bg_choice, send_choice, recv_choice, typing_choice, typing_bar_choice, 
                      bg_upload, send_upload, recv_upload, typing_upload, typing_bar_upload,
                      chat_title, chat_status, chat_avatar, moral_text):
    """Wrapper that ensures all parameters have proper default values"""
    # Ensure all required parameters have default values
    bg_choice = bg_choice or ""
    send_choice = send_choice or ""
    recv_choice = recv_choice or ""
    typing_choice = typing_choice or ""
    typing_bar_choice = typing_bar_choice or ""
    chat_title = chat_title or "Banka😎"
    chat_status = chat_status or ""
    moral_text = moral_text or ""
    
    # Handle file uploads - convert None to empty strings
    bg_upload = bg_upload if bg_upload is not None else ""
    send_upload = send_upload if send_upload is not None else ""
    recv_upload = recv_upload if recv_upload is not None else ""
    typing_upload = typing_upload if typing_upload is not None else ""
    typing_bar_upload = typing_bar_upload if typing_bar_upload is not None else ""
    chat_avatar = chat_avatar if chat_avatar is not None else ""
    
    return handle_render(
        bg_choice, send_choice, recv_choice, typing_choice, typing_bar_choice,
        bg_upload, send_upload, recv_upload, typing_upload, typing_bar_upload,
        chat_title, chat_status, chat_avatar, moral_text
    )

def safe_handle_timeline_render(bg_choice, send_choice, recv_choice, typing_choice, typing_bar_choice,
                               bg_upload, send_upload, recv_upload, typing_upload, typing_bar_upload, moral_text):
    """Wrapper that ensures all parameters have proper default values"""
    # Ensure all required parameters have default values
    bg_choice = bg_choice or ""
    send_choice = send_choice or ""
    recv_choice = recv_choice or ""
    typing_choice = typing_choice or ""
    typing_bar_choice = typing_bar_choice or ""
    moral_text = moral_text or ""
    
    # Handle file uploads - convert None to empty strings
    bg_upload = bg_upload if bg_upload is not None else ""
    send_upload = send_upload if send_upload is not None else ""
    recv_upload = recv_upload if recv_upload is not None else ""
    typing_upload = typing_upload if typing_upload is not None else ""
    typing_bar_upload = typing_bar_upload if typing_bar_upload is not None else ""
    
    return handle_timeline_render(
        bg_choice, send_choice, recv_choice, typing_choice, typing_bar_choice,
        bg_upload, send_upload, recv_upload, typing_upload, typing_bar_upload, moral_text
    )

def handle_render(bg_choice, send_choice, recv_choice, typing_choice, typing_bar_choice, bg_upload, send_upload, recv_upload, typing_upload, typing_bar_upload, chat_title, chat_status, chat_avatar, moral_text):
    global latest_generated_script, rendering_in_progress
    
    print("Starting render process...")
    
    reset_typing_sessions()

    rendering_in_progress = True
    try:
        # Check script availability
        if os.path.exists(SCRIPT_FILE):
            with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
                latest_generated_script = f.read().strip()

        if not latest_generated_script.strip():
            return None, "No script available. Please generate a script first.", None

        frames_dir = os.path.join(PROJECT_ROOT, "frames")
        timeline_file = os.path.join(frames_dir, "timeline.json")
        
        # Clean up previous frames
        if os.path.exists(frames_dir):
            try:
                shutil.rmtree(frames_dir)
            except Exception as e:
                print(f"Warning: Could not clean frames directory: {e}")
        os.makedirs(frames_dir, exist_ok=True)

        # Reset render state
        render_bubble.frame_count = 0
        render_bubble.timeline = []
        
        # Initialize renderer with safe defaults
        try:
            render_bubble.renderer = WhatsAppRenderer()
        except:
            render_bubble.renderer = type('MockRenderer', (), {
                'chat_title': chat_title or "Banka😎",
                'chat_status': chat_status or "",
                'chat_avatar': chat_avatar or "static/images/contact.png"
            })()

        characters = set()
        for line in latest_generated_script.splitlines():
            if ":" in line:
                name, _ = line.split(":", 1)
                name = name.strip()
                if name.lower() != "banka":
                    characters.add(name)
        if any("Banka" in line for line in latest_generated_script.splitlines()):
            characters.add("You")
        dynamic_chat_status = ", ".join(sorted(characters)) if characters else "No participants"

        render_bubble.renderer.chat_title = chat_title or "Banka😎"
        render_bubble.renderer.chat_status = dynamic_chat_status
        
        if chat_avatar:
            if isinstance(chat_avatar, list) and chat_avatar:
                render_bubble.renderer.chat_avatar = chat_avatar[0].name if hasattr(chat_avatar[0], 'name') else str(chat_avatar[0])
            elif hasattr(chat_avatar, 'name'):
                render_bubble.renderer.chat_avatar = chat_avatar.name
            else:
                render_bubble.renderer.chat_avatar = str(chat_avatar)
        else:
            render_bubble.renderer.chat_avatar = "static/images/contact.png"

        MAIN_USER = "Banka"
        
        for line in latest_generated_script.splitlines():
            line = line.strip()
            if not line:
                continue

            if line.startswith("MEME:"):
                meme_desc = line[5:].strip()
                meme_sender = "MemeBot"
                is_meme_sender = True

                if render_bubble.timeline:
                    for i in range(len(render_bubble.timeline)-1, -1, -1):
                        entry = render_bubble.timeline[i]
                        if entry.get("username") and entry.get("username") != "MemeBot" and not entry.get("is_meme", False):
                            meme_sender = entry["username"]
                            is_meme_sender = entry.get("is_sender", True)
                            break
                
                try:
                    from backend.meme_fetcher import fetch_meme_from_giphy
                    meme_file = fetch_meme_from_giphy(meme_desc)
                except ImportError:
                    meme_file = None
                    
                if meme_file:
                    safe_render_bubble(meme_sender, "", meme_path=meme_file, is_sender=is_meme_sender)
                    if render_bubble.timeline:
                        render_bubble.timeline[-1]["duration"] = 4.0
                continue

            if ":" in line:
                name, message = line.split(":", 1)
                name, message = name.strip(), message.strip()
                is_sender = (name.lower() != MAIN_USER.lower())

                text_message = ""
                meme_desc = ""

                if "[MEME]" in message:
                    if message.strip() == "[MEME]":
                        meme_desc = message.replace("[MEME]", "").strip()
                        text_message = ""
                    else:
                        text_part, meme_desc = message.split("[MEME]", 1)
                        text_message = text_part.strip()
                        meme_desc = meme_desc.strip()

                    try:
                        from backend.meme_fetcher import fetch_meme_from_giphy
                        meme_file = fetch_meme_from_giphy(meme_desc)
                    except ImportError:
                        meme_file = None
                        
                    if meme_file:
                        safe_render_bubble(name, text_message, meme_path=meme_file, is_sender=is_sender)
                        if render_bubble.timeline:
                            duration = 4.0 if not text_message.strip() else max(3.0, len(text_message) / 8)
                            render_bubble.timeline[-1]["duration"] = duration
                    else:
                        if text_message.strip():
                            safe_render_bubble(name, text_message, is_sender=is_sender)
                            if render_bubble.timeline:
                                duration = max(3.0, len(text_message) / 8)
                                render_bubble.timeline[-1]["duration"] = duration
                else:
                    text_message = message
    
                    if name.strip().lower() == "banka" and random.random() < 0.85:
                        typing_sequence = generate_beluga_typing_sequence(text_message)
                        for frame_text, frame_duration, frame_sound in typing_sequence:
                            render_typing_bar_frame(
                                username=name,
                                upcoming_text=frame_text,
                                duration=frame_duration,
                                is_character_typing=frame_sound
                            )
                    elif is_sender and random.random() < 0.3:
                        render_typing_bubble(name, is_sender)

                    duration = max(3.0, len(text_message) / 8)
                    
                    safe_render_bubble(name, text_message, is_sender=is_sender)
                    
                    if render_bubble.timeline:
                        render_bubble.timeline[-1]["duration"] = duration

        with open(timeline_file, "w", encoding="utf-8") as f:
            json.dump(render_bubble.timeline, f, indent=2)

        # Use the safe video builder
        video_path = safe_build_video_from_timeline(
            bg_audio=get_file_path(bg_upload, bg_choice, DEFAULT_BG),
            send_audio=get_file_path(send_upload, send_choice, DEFAULT_SEND),
            recv_audio=get_file_path(recv_upload, recv_choice, DEFAULT_RECV),
            typing_audio=get_file_path(typing_upload, typing_choice, DEFAULT_TYPING),
            typing_bar_audio=get_file_path(typing_bar_upload, typing_bar_choice, None),
            use_segments=os.path.exists(BG_TIMELINE_FILE),
            bg_segments=load_bg_segments() if os.path.exists(BG_TIMELINE_FILE) else None,
            moral_text=moral_text
        )
        
        if video_path:
            return video_path, "Video rendered successfully!", video_path
        else:
            return None, "Video rendering failed. Check console for details.", None
            
    except Exception as e:
        error_msg = f"Error rendering video: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return None, error_msg, None
    finally:
        rendering_in_progress = False

def handle_timeline_render(bg_choice, send_choice, recv_choice, typing_choice, typing_bar_choice, bg_upload, send_upload, recv_upload, typing_upload, typing_bar_upload, moral_text):
    global rendering_in_progress
    
    rendering_in_progress = True
    
    try:
        timeline_file = os.path.join(PROJECT_ROOT, "frames", "timeline.json")
        if not os.path.exists(timeline_file):
            return None, "No timeline file found. Please generate a timeline first.", None
        
        with open(timeline_file, "r", encoding="utf-8") as f:
            timeline_data = json.load(f)
        
        if not timeline_data:
            return None, "Timeline file is empty.", None
        
        total_duration = sum(entry.get("duration", 0) for entry in timeline_data)

        bg_timeline_file = os.path.join(PROJECT_ROOT, "frames", "bg_timeline.json")
        bg_segments = []
        
        if os.path.exists(bg_timeline_file):
            bg_segments = load_bg_segments(bg_timeline_file)

        if isinstance(bg_choice, list) and bg_choice:
            bg_choice = bg_choice[0] if bg_choice[0] else ""
        elif isinstance(bg_choice, list) and not bg_choice:
            bg_choice = ""

        def get_audio_path(upload_file, choice, default):
            if upload_file:
                if isinstance(upload_file, list):
                    if upload_file:
                        if hasattr(upload_file[0], 'name'):
                            return upload_file[0].name
                        else:
                            return str(upload_file[0])
                    else:
                        return default
                if hasattr(upload_file, 'name'):
                    return upload_file.name
                else:
                    return str(upload_file)
            elif choice:
                if isinstance(choice, list) and choice:
                    choice = choice[0]
                full_path = os.path.join(PROJECT_ROOT, "static", "audio", choice)
                return full_path if os.path.exists(full_path) else default
            else:
                return default
        
        bg_path = get_audio_path(bg_upload, bg_choice, DEFAULT_BG)
        send_path = get_audio_path(send_upload, send_choice, DEFAULT_SEND)
        recv_path = get_audio_path(recv_upload, recv_choice, DEFAULT_RECV)
        typing_path = get_audio_path(typing_upload, typing_choice, DEFAULT_TYPING)
        typing_bar_path = get_audio_path(typing_bar_upload, typing_bar_choice, None)

        use_segments = os.path.exists(bg_timeline_file) and bg_segments

        # Use the safe video builder
        video_path = safe_build_video_from_timeline(
            bg_audio=bg_path,
            send_audio=send_path,
            recv_audio=recv_path,
            typing_audio=typing_path,
            typing_bar_audio=typing_bar_path,
            use_segments=use_segments,
            bg_segments=bg_segments if use_segments else None,
            moral_text=moral_text
        )
        
        if video_path and os.path.exists(video_path):
            try:
                result = subprocess.run([
                    'ffprobe', '-v', 'error', 
                    '-show_entries', 'format=duration', 
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    video_path
                ], capture_output=True, text=True, check=True)
                actual_duration = float(result.stdout.strip())
            except Exception:
                actual_duration = 0
            
            return video_path, f"Video rendered successfully! Expected: {total_duration}s, Actual: {actual_duration}s", video_path
        else:
            return None, "Video rendering failed - no output file", None
            
    except Exception as e:
        return None, f"Error: {str(e)}", None
    finally:
        rendering_in_progress = False

# =============================================
# BACKGROUND MUSIC SEGMENT FUNCTIONS
# =============================================

def load_bg_segments(file_path=None):
    """Safe loader for background segments"""
    if file_path is None:
        file_path = BG_TIMELINE_FILE
    
    if not os.path.exists(file_path):
        return []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
    except Exception:
        return []

    repaired = []
    changed = False

    for i, seg in enumerate(data):
        try:
            start_val = float(seg.get("start", 0))
        except:
            start_val = 0.0
            changed = True

        try:
            end_val = float(seg.get("end", 0))
        except:
            end_val = start_val
            changed = True

        if end_val <= start_val:
            end_val = start_val + 10.0
            changed = True

        playback_mode = seg.get("playback_mode", "start_fresh")
        if playback_mode not in ["start_fresh", "continue", "custom_start"]:
            playback_mode = "start_fresh"
            changed = True
            
        custom_start = seg.get("custom_start", 0.0)
        try:
            custom_start = float(custom_start)
            if custom_start < 0:
                custom_start = 0.0
                changed = True
        except:
            custom_start = 0.0
            changed = True

        audio_file = str(seg.get("audio", "")).strip()
        if not audio_file:
            continue

        if not os.path.isabs(audio_file):
            if "static" in audio_file or "audio" in audio_file:
                audio_file = os.path.abspath(audio_file)
            else:
                from pathlib import Path
                audio_file = str(Path("static/audio") / os.path.basename(audio_file))
            changed = True

        repaired.append({
            "start": start_val,
            "end": end_val,
            "audio": audio_file,
            "playback_mode": playback_mode,
            "custom_start": custom_start
        })

    if changed or len(repaired) != len(data):
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(repaired, f, indent=2)
        except Exception:
            pass

    return repaired

def load_bg_segments_ui():
    """Wrapper for UI that loads segments and returns them in UI format"""
    segments = load_bg_segments()
    
    ui_segments = []
    for seg in segments:
        audio_filename = os.path.basename(seg["audio"]) if seg["audio"] else ""
        playback_mode = seg.get("playback_mode", "start_fresh")
        custom_start = seg.get("custom_start", 0.0)
        ui_segments.append([seg["start"], seg["end"], audio_filename, playback_mode, custom_start])
    
    return ui_segments, f"Loaded {len(ui_segments)} BG segments"

def add_bg_segment(start, end, audio, playback_mode, custom_start, current_segments, timeline_table):
    try:
        if start is None or end is None:
            return current_segments, "Start and end times cannot be empty"
        
        try:
            start_val = float(start)
        except:
            start_val = 0.0

        try:
            end_val = float(end)
        except:
            end_val = start_val

        audio = str(audio).strip() if audio else ""
        
        if playback_mode == "custom_start":
            try:
                custom_start_val = float(custom_start) if custom_start is not None else 0.0
                if custom_start_val < 0:
                    return current_segments, "Custom start time cannot be negative"
            except:
                return current_segments, "Invalid custom start time"
        else:
            custom_start_val = 0.0
        
        if start_val < 0:
            return current_segments, "Invalid segment: start time cannot be negative"
        if end_val <= start_val:
            return current_segments, "Invalid segment: end time must be greater than start time"
        if end_val - start_val < 0.1:
            return current_segments, "Segment too short: must be at least 0.1 seconds"
        
        total_duration = 9999
        if isinstance(timeline_table, dict) and "data" in timeline_table:
            data = timeline_table["data"]
        elif hasattr(timeline_table, "values"):
            data = timeline_table.values.tolist()
        else:
            data = timeline_table
        
        try:
            if data:
                total_duration, _ = calculate_total_runtime(data)
        except Exception:
            pass
        
        if end_val > total_duration:
            end_val = total_duration
        
        segments_list = []

        if current_segments is not None:
            try:
                if hasattr(current_segments, "values"):
                    if not current_segments.empty:
                        segments_list = current_segments.values.tolist()
                elif isinstance(current_segments, dict) and "data" in current_segments:
                    segments_list = current_segments["data"]
                elif isinstance(current_segments, list) and len(current_segments) > 0:
                    segments_list = current_segments[:]
            except Exception:
                pass

        for i, seg in enumerate(segments_list):
            if len(seg) < 2:
                continue
            seg_start = float(seg[0]) if seg[0] else 0
            seg_end = float(seg[1]) if seg[1] else 0
            if not (end_val <= seg_start or start_val >= seg_end):
                return current_segments, f"Segment overlaps with existing segment {i}"
        
        new_segment = [start_val, end_val, audio, playback_mode, custom_start_val]
        segments_list.append(new_segment)
        segments_list.sort(key=lambda x: float(x[0]) if x[0] is not None else 0)
        
        segments_to_save = []
        for row in segments_list:
            if len(row) < 3:
                continue

            try:
                seg_start = float(row[0])
            except:
                seg_start = 0.0

            try:
                seg_end = float(row[1])
            except:
                seg_end = seg_start

            audio_file = str(row[2]).strip() if len(row) > 2 else ""
            playback_mode = str(row[3]) if len(row) > 3 else "start_fresh"
            custom_start = float(row[4]) if len(row) > 4 and row[4] is not None else 0.0

            if seg_end <= seg_start:
                continue

            segment_data = {
                "start": seg_start,
                "end": seg_end,
                "audio": audio_file,
                "playback_mode": playback_mode,
                "custom_start": custom_start
            }

            segments_to_save.append(segment_data)
        
        os.makedirs(os.path.dirname(BG_TIMELINE_FILE), exist_ok=True)
        with open(BG_TIMELINE_FILE, "w", encoding="utf-8") as f:
            json.dump(segments_to_save, f, indent=2)
        
        ui_segments = [[s["start"], s["end"], s["audio"], s["playback_mode"], s["custom_start"]] for s in segments_to_save]
        
        mode_display = {
            "start_fresh": "Start Fresh",
            "continue": "Continue", 
            "custom_start": f"Custom Start ({custom_start_val}s)"
        }
        
        return ui_segments, f"Added segment: {start_val}s–{end_val}s ({audio}) - {mode_display[playback_mode]}"
    
    except Exception as e:
        return current_segments, f"Error adding segment: {e}"

def save_bg_segments(segments, timeline_table):
    try:
        if isinstance(segments, dict) and "data" in segments:
            segments_list = segments["data"]
        elif isinstance(segments, pd.DataFrame):
            segments_list = segments.values.tolist()
        elif not segments:
            segments_list = []
        else:
            segments_list = segments

        if isinstance(timeline_table, dict) and "data" in timeline_table:
            data = timeline_table["data"]
        else:
            data = timeline_table
        total_duration, _ = calculate_total_runtime(data)

        segments_to_save = []
        for i, row in enumerate(segments_list):
            try:
                start = float(row[0])
                end = float(row[1])
                audio = str(row[2]).strip() if len(row) > 2 and row[2] else ""
                playback_mode = str(row[3]) if len(row) > 3 and row[3] else "start_fresh"
                custom_start = float(row[4]) if len(row) > 4 and row[4] is not None else 0.0
                
                if start >= end:
                    continue
                if end > total_duration:
                    end = total_duration
                
                for j, seg in enumerate(segments_to_save):
                    if not (end <= seg["start"] or start >= seg["end"]):
                        return None, f"Segment {i} overlaps with segment {j}"
                
                audio_path = ""
                if audio:
                    audio_path = os.path.join(PROJECT_ROOT, "static", "audio", audio)
                    if not os.path.exists(audio_path):
                        audio_path = ""
                
                segments_to_save.append({
                    "start": start, 
                    "end": end, 
                    "audio": audio_path,
                    "playback_mode": playback_mode,
                    "custom_start": custom_start
                })
                
            except (ValueError, TypeError):
                continue

        segments_to_save.sort(key=lambda x: x["start"])
        
        os.makedirs(os.path.dirname(BG_TIMELINE_FILE), exist_ok=True)
        with open(BG_TIMELINE_FILE, "w", encoding="utf-8") as f:
            json.dump(segments_to_save, f, indent=2)
            
        return gr.Dropdown(choices=AUDIO_FILES + [""], value=""), f"Saved {len(segments_to_save)} BG segments"
        
    except Exception as e:
        return gr.Dropdown(choices=AUDIO_FILES + [""], value=""), f"Error saving BG segments: {str(e)}"

def reset_bg_segments():
    if os.path.exists(BG_TIMELINE_FILE):
        os.remove(BG_TIMELINE_FILE)
    return pd.DataFrame(columns=["start_seconds", "end_seconds", "audio", "playback_mode", "custom_start"]), "Reset all BG segments"

def create_fallback_avatar(username, size=200):
    """Create a fallback avatar using command line tools if PIL fails"""
    try:
        def get_initials(name):
            words = name.strip().split()
            if len(words) == 0:
                return "?"
            elif len(words) == 1:
                return name[:1].upper()
            else:
                return (words[0][0] + words[-1][0]).upper()
        
        initials = get_initials(username)
        
        avatars_dir = os.path.join(PROJECT_ROOT, "static", "avatars")
        os.makedirs(avatars_dir, exist_ok=True)
        
        colors = ['red', 'blue', 'green', 'purple', 'orange', 'teal']
        color_index = hash(username) % len(colors)
        color = colors[color_index]
        
        try:
            from PIL import Image, ImageDraw
            img = Image.new('RGB', (size, size), color=color)
            draw = ImageDraw.Draw(img)
            draw.text((size//4, size//4), initials, fill='white')
            return img
        except ImportError:
            return None
        
    except Exception:
        return None

# =============================================
# ENHANCED GRADIO UI WITH RESOURCE MANAGEMENT
# =============================================

def cleanup_resources():
    """Clean up temporary resources"""
    try:
        temp_dir = os.path.join(PROJECT_ROOT, "temp")
        if os.path.exists(temp_dir):
            for file in os.listdir(temp_dir):
                try:
                    os.remove(os.path.join(temp_dir, file))
                except:
                    pass
        print("✅ Cleaned up temporary resources")
    except Exception as e:
        print(f"⚠️ Cleanup warning: {e}")

# Create the Gradio interface
with gr.Blocks() as demo:
    gr.Markdown("## Chat Script & Video Generator")
    
    # Create invisible placeholder components
    typing_bar_choice_placeholder = gr.Textbox(visible=False, value=None)
    typing_bar_upload_placeholder = gr.File(visible=False, value=None)
    typing_bar_choice_timeline_placeholder = gr.Textbox(visible=False, value=None)
    typing_bar_upload_timeline_placeholder = gr.File(visible=False, value=None)
    
    with gr.Tabs() as tabs:
        with gr.TabItem("Character Management"):
            gr.Markdown("### Manage Characters for Your Stories")
            
            with gr.Row():
                with gr.Column():
                    gr.Markdown("#### Add/Edit Character")
                    character_name = gr.Textbox(label="Character Name", placeholder="Enter character name")
                    character_personality = gr.Textbox(label="Personality/Traits", placeholder="Describe the character's personality", lines=3)
                    character_avatar = gr.File(
                        label="Character Avatar", 
                        file_types=[".png", ".jpg", ".jpeg"],
                        type="filepath"
                    )
                    
                    with gr.Row():
                        add_char_btn = gr.Button("Add Character", variant="primary")
                        update_char_btn = gr.Button("Update Character")
                        delete_char_btn = gr.Button("Delete Character", variant="stop")
                    
                    char_status = gr.Textbox(label="Status", interactive=False)
                
                with gr.Column():
                    gr.Markdown("#### Existing Characters")
                    characters_list = gr.Dropdown(
                        choices=get_character_names(),
                        label="Select Character",
                        allow_custom_value=False
                    )
                    character_preview = gr.Image(label="Avatar Preview", height=200)
                    character_details = gr.Textbox(label="Character Details", interactive=False, lines=3)
                    
                    gr.Markdown("#### Quick Actions")
                    with gr.Row():
                        refresh_chars_btn = gr.Button("Refresh List")
                        use_chars_btn = gr.Button("Use in Script")
            
            def add_character_handler(name, personality, avatar):
                if not name:
                    return "Please enter a character name", gr.Dropdown(choices=get_character_names(), value=""), "static/images/contact.png", "", None
                
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
            
            def update_character_handler(name, personality, avatar):
                if not name:
                    return "Please select a character to update", gr.Dropdown(choices=get_character_names(), value=""), "static/images/contact.png", "", None
                
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
            
            def delete_character_handler(name):
                if not name:
                    return "Please select a character to delete", gr.Dropdown(choices=get_character_names(), value=""), "static/images/contact.png", "", None
                
                success, message = delete_character(name)
                characters = get_character_names()
                if success:
                    new_value = characters[0] if characters else ""
                    return message, gr.Dropdown(choices=characters, value=new_value), "static/images/contact.png", "", None
                else:
                    return message, gr.Dropdown(choices=characters, value=name if name in characters else ""), "static/images/contact.png", "", None
            
            def use_characters_in_script():
                characters = get_character_names()
                if characters:
                    char_string = ", ".join(characters)
                    return char_string
                else:
                    return ""
            
            refresh_chars_btn.click(
                fn=refresh_characters,
                outputs=[characters_list, char_status, character_preview, character_details, character_avatar]
            )
            
            characters_list.change(
                fn=load_character_details,
                inputs=[characters_list],
                outputs=[character_preview, character_details, character_avatar]
            )
            
            add_char_btn.click(
                fn=add_character_handler,
                inputs=[character_name, character_personality, character_avatar],
                outputs=[char_status, characters_list, character_preview, character_details, character_avatar]
            )
            
            update_char_btn.click(
                fn=update_character_handler,
                inputs=[characters_list, character_personality, character_avatar],
                outputs=[char_status, characters_list, character_preview, character_details, character_avatar]
            )
            
            delete_char_btn.click(
                fn=delete_character_handler,
                inputs=[characters_list],
                outputs=[char_status, characters_list, character_preview, character_details, character_avatar]
            )
            
            use_chars_btn.click(
                fn=use_characters_in_script,
                outputs=[character_name]
            )

        with gr.TabItem("Script & Video"):
            with gr.Row():
                characters = gr.Textbox(label="Characters (comma-separated)", placeholder="Jay, Khooi, Banka, Brian, Alex, Shiro, Paula")
                topic = gr.Textbox(label="Topic")
                mood = gr.Textbox(label="Mood")
                length = gr.Number(label="Length (lines)", value=10)
                title = gr.Textbox(label="Title")

            moral_text = gr.Textbox(
                label="Moral of the Story (Optional)",
                placeholder="e.g., And the moral of the story is...",
                lines=2,
                max_lines=4
            )
            
            with gr.Row():
                chat_title = gr.Textbox(label="Chat Window Title", placeholder="BANKA TOUR GROUP")
                chat_status = gr.Textbox(label="Chat Status", placeholder="jay, khooi, banka, alex, shiro, brian, paula")
                chat_avatar = gr.File(label="Chat Avatar", file_types=[".png", ".jpg", ".jpeg"])

            with gr.Row():
                bg_choice = gr.Dropdown(
                    choices=AUDIO_FILES + [""],
                    label="Background Audio",
                    value="",
                    allow_custom_value=True
                )
                bg_upload = gr.File(label="Upload Background Audio(s)", file_count="multiple", file_types=[".mp3"])
                send_choice = gr.Dropdown(
                    choices=AUDIO_FILES + [""],
                    label="Send Sound",
                    value="",
                    allow_custom_value=True
                )
                send_upload = gr.File(label="Upload Send Sound", file_types=[".mp3"])
                recv_choice = gr.Dropdown(
                    choices=AUDIO_FILES + [""],
                    label="Receive Sound",
                    value="",
                    allow_custom_value=True
                )
                recv_upload = gr.File(label="Upload Receive Sound", file_types=[".mp3"])
                typing_choice = gr.Dropdown(
                    choices=[""] + AUDIO_FILES,
                    label="Typing Sound",
                    value="",
                    allow_custom_value=True
                )
                typing_upload = gr.File(label="Upload Typing Sound", file_types=[".mp3"])
                avatar_upload = gr.File(label="Upload Avatar", file_types=[".png", ".jpg", ".jpeg"])
            
            with gr.Row():
                manual_script = gr.Textbox(
                    label="Manual Script (optional, overrides AI)",
                    placeholder="Paste your own script here...\nFormat: Name: message",
                    lines=30)
                generate_btn = gr.Button("Generate Script")
                render_btn = gr.Button("Render Video", variant="primary")

            script_output = gr.Textbox(label="Generated Script", lines=15)
            status = gr.Textbox(label="Status")
            video_file = gr.Video(label="Rendered Video")
            video_download = gr.File(label="Download Video", file_types=[".mp4"], interactive=False)

            generate_btn.click(
                fn=handle_generate,
                inputs=[characters, topic, mood, length, title, avatar_upload, manual_script],
                outputs=[script_output, status]
            )

            save_manual_btn = gr.Button("Save Manual Script")
            save_manual_btn.click(
                fn=handle_manual_script,
                inputs=[manual_script],
                outputs=[script_output, status]
            )

            bg_upload.change(
                fn=lambda x: handle_audio_upload_fixed(x, "background"),
                inputs=[bg_upload],
                outputs=[bg_choice, status]
            )
            send_upload.change(
                fn=lambda x: handle_audio_upload_fixed(x, "send"),
                inputs=[send_upload],
                outputs=[send_choice, status]
            )
            recv_upload.change(
                fn=lambda x: handle_audio_upload_fixed(x, "receive"),
                inputs=[recv_upload],
                outputs=[recv_choice, status]
            )
            typing_upload.change(
                fn=lambda x: handle_audio_upload_fixed(x, "typing"),
                inputs=[typing_upload],
                outputs=[typing_choice, status]
            )

            # FIXED: Use safe wrapper and placeholder components with None values
            render_btn.click(
                fn=safe_handle_render,
                inputs=[
                    bg_choice, send_choice, recv_choice, typing_choice, typing_bar_choice_placeholder,
                    bg_upload, send_upload, recv_upload, typing_upload, typing_bar_upload_placeholder,
                    chat_title, chat_status, chat_avatar, moral_text
                ],
                outputs=[video_file, status, video_download]
            )

        with gr.TabItem("Timeline Editor"):
            gr.Markdown("### Adjust Message Durations")

            with gr.Row():
                load_timeline_btn = gr.Button("Load Timeline")
                auto_pace_btn = gr.Button("Auto-Pace")
                save_btn = gr.Button("Save Changes")
                auto_refresh_toggle = gr.Checkbox(label="Enable Auto-Refresh", value=True)

            moral_text_timeline = gr.Textbox(
                label="Moral of the Story (Optional)",
                placeholder="e.g., And the moral of the story is...",
                lines=2,
                max_lines=4
            )
               
            timeline_table = gr.Dataframe(
                headers=["index", "username", "text", "duration"],
                datatype=["number", "str", "str", "number"],
                interactive=True,
                label="Timeline (Adjust durations manually)"
            )
            status_box = gr.Textbox(label="Status", interactive=False)
            total_duration_box = gr.Textbox(label="Total Video Duration (MM:SS)", interactive=False)

            load_timeline_btn.click(fn=load_timeline_data, outputs=[timeline_table, status_box, total_duration_box])
            auto_pace_btn.click(fn=auto_pace_timeline, outputs=[timeline_table, status_box, total_duration_box])
            save_btn.click(fn=save_timeline_data, inputs=[timeline_table], outputs=[status_box])

            with gr.Row():
                bg_choice_timeline = gr.Dropdown(
                    choices=AUDIO_FILES + [""],
                    label="Background Audio",
                    value="",
                    interactive=True,
                    allow_custom_value=True
                )
                bg_upload_timeline = gr.File(label="Upload Background Audio(s)", file_count="multiple", file_types=[".mp3"])
                send_choice_timeline = gr.Dropdown(
                    choices=AUDIO_FILES + [""],
                    label="Send Sound",
                    value="",
                    interactive=True,
                    allow_custom_value=True
                )
                send_upload_timeline = gr.File(label="Upload Send Sound", file_types=[".mp3"])
                recv_choice_timeline = gr.Dropdown(
                    choices=AUDIO_FILES + [""],
                    label="Receive Sound",
                    value="",
                    interactive=True,
                    allow_custom_value=True
                )
                recv_upload_timeline = gr.File(label="Upload Receive Sound", file_types=[".mp3"])
                typing_choice_timeline = gr.Dropdown(
                    choices=[""] + AUDIO_FILES,
                    label="Typing Sound",
                    value="",
                    interactive=True,
                    allow_custom_value=True
                )
                typing_upload_timeline = gr.File(label="Upload Typing Sound", file_types=[".mp3"])

            with gr.Accordion("Background Music Segments", open=False):
                gr.Markdown("Add background music segments by specifying start time, end time, and selecting an audio file.")
                
                with gr.Row():
                    segment_start = gr.Number(label="Start Time (seconds)", value=0.0, precision=2)
                    segment_end = gr.Number(label="End Time (seconds)", value=10.0, precision=2)
                    segment_audio = gr.Dropdown(
                        choices=AUDIO_FILES + [""],
                        label="Audio File",
                        value=""
                    )
                    add_segment_btn = gr.Button("Add Segment")
                
                segments_table = gr.Dataframe(
                    headers=["start_seconds", "end_seconds", "audio"],
                    datatype=["number", "number", "str"],
                    type="pandas",
                    interactive=True,
                    value=pd.DataFrame(columns=["start_seconds", "end_seconds", "audio"]),
                    col_count=(3, "fixed"),
                    row_count=(1, "dynamic"),
                    wrap=True,
                    elem_id="segments_table"
                )
                bg_status = gr.Textbox(label="BG Status", interactive=False)
                with gr.Row():
                    load_bg_btn = gr.Button("Load BG Segments")
                    save_bg_btn = gr.Button("Save BG Segments")
                    reset_btn = gr.Button("Reset All Segments")

                add_segment_btn.click(
                    fn=lambda s, e, a, cs, tt: add_bg_segment(s, e, a, "start_fresh", 0.0, cs, tt),
                    inputs=[segment_start, segment_end, segment_audio, segments_table, timeline_table],
                    outputs=[segments_table, bg_status]
                )
                load_bg_btn.click(
                    fn=load_bg_segments_ui,
                    outputs=[segments_table, bg_status]
                )
                save_bg_btn.click(
                    fn=save_bg_segments,
                    inputs=[segments_table, timeline_table],
                    outputs=[bg_choice_timeline, bg_status]
                )
                reset_btn.click(
                    fn=reset_bg_segments,
                    outputs=[segments_table, bg_status]
                )

            with gr.Row():
                render_btn = gr.Button("Render Video")
            
            timeline_video_file = gr.Video(label="Rendered Video")
            timeline_status = gr.Textbox(label="Render Status")
            timeline_video_download = gr.File(label="Download Video", file_types=[".mp4"], interactive=False)

            # FIXED: Use safe wrapper and placeholder components with None values
            render_btn.click(
                fn=safe_handle_timeline_render, 
                inputs=[
                    bg_choice_timeline, send_choice_timeline, recv_choice_timeline, typing_choice_timeline, typing_bar_choice_timeline_placeholder,
                    bg_upload_timeline, send_upload_timeline, recv_upload_timeline, typing_upload_timeline, typing_bar_upload_timeline_placeholder,
                    moral_text_timeline
                ],
                outputs=[timeline_video_file, timeline_status, timeline_video_download]
            )

            bg_upload_timeline.change(
                fn=lambda x: handle_audio_upload_fixed(x, "background"),
                inputs=[bg_upload_timeline],
                outputs=[bg_choice_timeline, bg_status]
            )
            send_upload_timeline.change(
                fn=lambda x: handle_audio_upload_fixed(x, "send"),
                inputs=[send_upload_timeline],
                outputs=[send_choice_timeline, bg_status]
            )
            recv_upload_timeline.change(
                fn=lambda x: handle_audio_upload_fixed(x, "receive"),
                inputs=[recv_upload_timeline],
                outputs=[recv_choice_timeline, bg_status]
            )
            typing_upload_timeline.change(
                fn=lambda x: handle_audio_upload_fixed(x, "typing"),
                inputs=[typing_upload_timeline],
                outputs=[typing_choice_timeline, bg_status]
            )

    def on_tab_change(evt: gr.SelectData):
        tab_index = evt.index
        auto_refresh_enabled = auto_refresh_toggle.value if 'auto_refresh_toggle' in locals() else True
        
        if tab_index == 2 and auto_refresh_enabled:
            stop_auto_refresh()
            return "Auto-refresh stopped"
        else:   
            start_auto_refresh(load_timeline_btn, timeline_table, status_box, total_duration_box, interval=10)
            return "Auto-refresh started for Timeline Editor"

    tabs.select(fn=on_tab_change, inputs=None, outputs=[status_box])

    def initialize_audio_values():
        if AUDIO_FILES:
            bg_val = AUDIO_FILES[0] if AUDIO_FILES else ""
            send_val = AUDIO_FILES[0] if AUDIO_FILES else ""
            recv_val = AUDIO_FILES[0] if AUDIO_FILES else ""
            typing_val = ""
            
            return [
                bg_val, send_val, recv_val, typing_val,
                bg_val, send_val, recv_val, typing_val
            ]
        return ["", "", "", "", "", "", "", ""]

    demo.load(
        fn=initialize_audio_values,
        outputs=[
            bg_choice, send_choice, recv_choice, typing_choice,
            bg_choice_timeline, send_choice_timeline, recv_choice_timeline, typing_choice_timeline
        ]
    )

    # Add cleanup on demo close
    demo.unload(cleanup_resources)

# =============================================
# LAUNCH WITH RESOURCE MANAGEMENT
# =============================================

if __name__ == "__main__":
    # Set lower concurrency for resource-constrained environments - FIXED QUEUE PARAMETERS
    demo.queue(max_size=5)
    port = int(os.environ.get("PORT", 7860))

    try:
        print("Starting application with enhanced resource management...")
        print("✅ Chromium/Chrome suppression active")
        print("✅ Resource monitoring active")
        print("✅ Signal handlers registered")
        
        demo.launch(
            server_name="0.0.0.0",
            server_port=port,
            share=False,
            inbrowser=False,
            show_error=True,
            debug=True
        )
    except Exception as e:
        print(f"Failed to launch: {e}")
        traceback.print_exc()
    finally:
        cleanup_resources()
