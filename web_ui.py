import subprocess
import sys
import os
import traceback

print("🚀 Application starting...")
print(f"📁 Current directory: {os.getcwd()}")
print(f"🐍 Python version: {sys.version}")

# SIMPLE FFMPEG CHECK ONLY - NO INSTALLATION
try:
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        print("✅ ffmpeg is available")
    else:
        print("❌ ffmpeg command failed")
except Exception as e:
    print(f"❌ ffmpeg check failed: {e}")

# NOW import the rest of your modules - WITHOUT try/except that hides errors
print("📦 Importing dependencies...")

# ADD THESE IMPORTS RIGHT AFTER YOUR EXISTING IMPORTS
import tempfile
import shutil
from pathlib import Path

# Add after your existing imports, around line 45-55
try:
    from static_server import get_static_path, get_avatar_path
    print("✅ Static server utilities imported")
except ImportError as e:
    print(f"⚠️ Could not import static server: {e}")
    # Fallback functions
    def get_static_path(filename):
        return os.path.join(PROJECT_ROOT, "static", filename)
    
    def get_avatar_path(username):
        return os.path.join(PROJECT_ROOT, "static", "images", "contact.png")

try:
    import gradio as gr
    print("✅ Gradio imported")
except ImportError as e:
    print(f"❌ Failed to import gradio: {e}")
    sys.exit(1)

try:
    import asyncio
    import json
    import shutil
    import pandas as pd
    import time
    import threading
    import math
    import random
    import psutil
    print("✅ Standard libraries imported")
except ImportError as e:
    print(f"❌ Failed to import standard libraries: {e}")
    sys.exit(1)

# Import your custom modules with better error handling
try:
    from backend.generate_script import generate_script_with_groq
    print("✅ Backend modules imported")
except ImportError as e:
    print(f"❌ Failed to import backend modules: {e}")
    print("💡 Make sure your backend directory exists and has the required files")
    # Continue anyway for now

try:
    from backend.generate_video import build_video_from_timeline
except ImportError as e:
    print(f"⚠️ Could not import build_video_from_timeline: {e}")

try:
    from backend.avatar_handler import save_uploaded_avatar
except ImportError as e:
    print(f"⚠️ Could not import avatar_handler: {e}")

try:
    from backend.render_bubble import render_bubble, render_typing_bubble, WhatsAppRenderer, render_typing_bar_frame, generate_beluga_typing_sequence, reset_typing_sessions
    print("✅ Render bubble modules imported")
    
    # Initialize renderer state (fresh each session)
    render_bubble.frame_count = 0
    render_bubble.timeline = []
    render_bubble.renderer = WhatsAppRenderer()
    print("✅ Renderer initialized")
    
except ImportError as e:
    print(f"❌ Failed to import render_bubble modules: {e}")
    # Create dummy functions to prevent crashes
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
    
    # Set up the global variables your code expects
    render_bubble.frame_count = 0
    render_bubble.timeline = []
    render_bubble.renderer = WhatsAppRenderer()

try:
    from groq import Groq
    # Groq client (assuming API key is set in environment)
    groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    print("✅ Groq client initialized")
except ImportError as e:
    print(f"⚠️ Groq not available: {e}")
    groq_client = None
except Exception as e:
    print(f"⚠️ Groq client initialization failed: {e}")
    groq_client = None

print("✅ All imports completed successfully")

# Rest of your configuration...
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

# Global flag to control auto-refresh thread
auto_refresh_running = False
auto_refresh_thread = None

# Flag to track if video rendering is in progress
rendering_in_progress = False

# Prevent Gradio timeouts
os.environ["GRADIO_QUEUE"] = "True"

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

print("✅ Configuration loaded successfully")

# =============================================
# CHARACTER MANAGEMENT SYSTEM
# =============================================

def load_characters():
    """Load characters from JSON file"""
    if os.path.exists(CHARACTERS_FILE):
        try:
            with open(CHARACTERS_FILE, "r", encoding="utf-8") as f:
                characters = json.load(f)
            print(f"✅ Loaded {len(characters)} characters from {CHARACTERS_FILE}")
            return characters
        except Exception as e:
            print(f"❌ Error loading characters: {e}")
            return {}
    else:
        print("⚠️ No characters file found, creating default")
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
        print(f"✅ Saved {len(characters)} characters to {CHARACTERS_FILE}")
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
# FIXED FILE UPLOAD FUNCTIONS FOR RAILWAY
# =============================================

def debug_upload_issue():
    """Debug function to identify upload problems"""
    print("🔍 ===== UPLOAD DEBUGGING =====")
    
    # Check audio directory permissions
    print(f"📁 Audio directory: {AUDIO_DIR}")
    print(f"📁 Exists: {os.path.exists(AUDIO_DIR)}")
    if os.path.exists(AUDIO_DIR):
        print(f"📁 Writable: {os.access(AUDIO_DIR, os.W_OK)}")
        print(f"📁 Readable: {os.access(AUDIO_DIR, os.R_OK)}")
        print(f"📁 Files in directory: {len(os.listdir(AUDIO_DIR))}")
    
    # Check disk space
    try:
        disk_usage = shutil.disk_usage(AUDIO_DIR)
        free_gb = disk_usage.free / (1024**3)
        print(f"💾 Free disk space: {free_gb:.2f} GB")
    except:
        print("💾 Could not check disk space")
    
    return "✅ Upload debug complete - check console for details"

def test_basic_file_operations():
    """Test if basic file operations work on Railway"""
    print("🔧 ===== TESTING BASIC FILE OPERATIONS =====")
    
    test_file = os.path.join(PROJECT_ROOT, "test_upload.txt")
    
    try:
        # Test 1: Create a file
        print("1. Testing file creation...")
        with open(test_file, "w") as f:
            f.write("test content")
        print("   ✅ File creation: SUCCESS")
        
        # Test 2: Read the file
        print("2. Testing file reading...")
        with open(test_file, "r") as f:
            content = f.read()
        print(f"   ✅ File reading: SUCCESS (content: {content})")
        
        # Test 3: Copy the file
        print("3. Testing file copying...")
        copy_file = os.path.join(PROJECT_ROOT, "test_copy.txt")
        shutil.copy2(test_file, copy_file)
        print("   ✅ File copying: SUCCESS")
        
        # Test 4: Check audio directory
        print("4. Testing audio directory...")
        print(f"   Audio dir: {AUDIO_DIR}")
        print(f"   Exists: {os.path.exists(AUDIO_DIR)}")
        if os.path.exists(AUDIO_DIR):
            print(f"   Writable: {os.access(AUDIO_DIR, os.W_OK)}")
        
        # Cleanup
        if os.path.exists(test_file):
            os.remove(test_file)
        if os.path.exists(copy_file):
            os.remove(copy_file)
            
        print("🔧 ===== BASIC FILE OPERATIONS TEST COMPLETE =====")
        return "✅ Basic file operations working - check console"
        
    except Exception as e:
        print(f"❌ Basic file operations failed: {e}")
        return f"❌ Basic file operations failed: {e}"

def check_gradio_file_object(file_input):
    """Check what Gradio is actually sending us"""
    print("🎯 ===== CHECKING GRADIO FILE OBJECT =====")
    
    # Get the current value from the file input
    file_obj = file_input
    
    print(f"🎯 Type: {type(file_obj)}")
    print(f"🎯 Value: {file_obj}")
    
    if file_obj is None:
        print("🎯 File object is None")
        return "File object is None"
    
    if isinstance(file_obj, list):
        print(f"🎯 List with {len(file_obj)} items")
        for i, item in enumerate(file_obj):
            print(f"🎯 Item {i}: {type(item)} = {item}")
            if hasattr(item, 'name'):
                print(f"🎯   .name: {item.name}")
            if hasattr(item, 'size'):
                print(f"🎯   .size: {item.size}")
            if hasattr(item, 'orig_name'):
                print(f"🎯   .orig_name: {item.orig_name}")
    else:
        print(f"🎯 Single object")
        if hasattr(file_obj, 'name'):
            print(f"🎯   .name: {file_obj.name}")
        if hasattr(file_obj, 'size'):
            print(f"🎯   .size: {file_obj.size}")
        if hasattr(file_obj, 'orig_name'):
            print(f"🎯   .orig_name: {file_obj.orig_name}")
    
    print("🎯 ===== GRADIO FILE CHECK COMPLETE =====")
    return "✅ Gradio file check complete - check console"

def handle_audio_upload_fixed(audio_file, audio_type):
    """FIXED VERSION for Railway - with comprehensive debugging"""
    print(f"🎵 ===== ENTERING handle_audio_upload for {audio_type} =====")
    print(f"🎵 Input type: {type(audio_file)}")
    print(f"🎵 Input value: {audio_file}")
    
    if not audio_file:
        print(f"🎵 No file provided, returning early")
        return AUDIO_FILES, f"⚠️ No {audio_type} audio uploaded."
    
    print(f"🎵 Starting {audio_type} audio upload processing...")
    
    try:
        # Create audio directory if it doesn't exist
        print(f"🎵 Creating audio directory: {AUDIO_DIR}")
        os.makedirs(AUDIO_DIR, exist_ok=True)
        print(f"🎵 Audio directory ready: {os.path.exists(AUDIO_DIR)}")
        
        files_to_process = []
        if isinstance(audio_file, list):
            files_to_process = audio_file
            print(f"🎵 Processing {len(files_to_process)} files from list")
        else:
            files_to_process = [audio_file]
            print(f"🎵 Processing single file")
        
        print(f"🎵 Files to process: {len(files_to_process)}")
        
        statuses = []
        new_files = []
        
        for i, f in enumerate(files_to_process):
            print(f"🎵 --- Processing file {i+1}/{len(files_to_process)} ---")
            
            # Handle both Gradio file objects and file paths
            if hasattr(f, 'name'):
                source_path = f.name
                # Try to get original filename, fall back to basename
                if hasattr(f, 'orig_name'):
                    filename = f.orig_name
                else:
                    filename = os.path.basename(f.name)
                print(f"🎵 Gradio file object detected")
                print(f"🎵 Source path: {source_path}")
                print(f"🎵 Filename: {filename}")
            else:
                # Handle string paths
                source_path = str(f)
                filename = os.path.basename(str(f))
                print(f"🎵 String path detected: {source_path}")
                print(f"🎵 Filename: {filename}")
            
            # Check if source exists
            source_exists = os.path.exists(source_path)
            print(f"🎵 Checking if source exists: {source_exists}")
            
            if not source_exists:
                print(f"❌ Source file does not exist: {source_path}")
                statuses.append(f"❌ {filename} (file not found)")
                continue
            
            # Check file size and readability
            try:
                file_size = os.path.getsize(source_path)
                is_readable = os.access(source_path, os.R_OK)
                print(f"🎵 Source file size: {file_size} bytes")
                print(f"🎵 Source file readable: {is_readable}")
                
                if file_size == 0:
                    print(f"❌ Source file is empty: {filename}")
                    statuses.append(f"❌ {filename} (empty file)")
                    continue
                    
            except Exception as size_error:
                print(f"❌ Error checking file {filename}: {size_error}")
                statuses.append(f"❌ {filename} (error: {str(size_error)})")
                continue
            
            # Clean filename for security
            original_filename = filename
            filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
            if filename != original_filename:
                print(f"🎵 Cleaned filename: {original_filename} -> {filename}")
            
            # Create destination path
            dest_path = os.path.join(AUDIO_DIR, filename)
            print(f"🎵 Destination path: {dest_path}")
            
            # Check if audio directory is writable
            audio_dir_writable = os.access(AUDIO_DIR, os.W_OK)
            print(f"🎵 Audio dir writable: {audio_dir_writable}")
            
            if not audio_dir_writable:
                print(f"❌ Audio directory is not writable: {AUDIO_DIR}")
                statuses.append(f"❌ {filename} (directory not writable)")
                continue
            
            # Copy file with error handling
            print(f"🎵 Starting file copy...")
            try:
                shutil.copy2(source_path, dest_path)
                print(f"🎵 File copy completed")
                
                # Verify the file was copied
                dest_exists = os.path.exists(dest_path)
                print(f"🎵 Checking if destination exists: {dest_exists}")
                
                if dest_exists:
                    copied_size = os.path.getsize(dest_path)
                    print(f"🎵 Destination file size: {copied_size} bytes")
                    
                    if copied_size > 0:
                        if filename not in AUDIO_FILES:
                            AUDIO_FILES.append(filename)
                            new_files.append(filename)
                            print(f"🎵 Added to AUDIO_FILES: {filename}")
                        statuses.append(filename)
                        print(f"✅ Successfully uploaded: {filename}")
                    else:
                        print(f"❌ File copy failed: {filename} is empty")
                        # Remove empty file
                        if os.path.exists(dest_path):
                            os.remove(dest_path)
                            print(f"🎵 Removed empty file")
                        statuses.append(f"❌ {filename} (copy failed - empty)")
                else:
                    print(f"❌ File copy failed: {filename} not found at destination")
                    statuses.append(f"❌ {filename} (copy failed - not found)")
                    
            except Exception as copy_error:
                print(f"❌ Error copying {filename}: {copy_error}")
                traceback.print_exc()
                statuses.append(f"❌ {filename} (error: {str(copy_error)})")
                continue
        
        print(f"🎵 Processing complete. Statuses: {statuses}")
        
        # Filter successful uploads
        successful_uploads = [s for s in statuses if not s.startswith('❌')]
        
        if successful_uploads:
            if len(successful_uploads) == 1:
                status_msg = f"✅ Uploaded {audio_type} audio: {successful_uploads[0]}"
            else:
                status_msg = f"✅ Uploaded {len(successful_uploads)} {audio_type} audios"
            
            print(f"🎵 Returning success: {status_msg}")
            
            # Return updated dropdown choices
            unique_files = list(dict.fromkeys(AUDIO_FILES))
            return gr.Dropdown(choices=unique_files + [""]), status_msg
        else:
            error_msg = f"❌ Failed to upload {audio_type} audio. Check console for details."
            print(f"🎵 Returning error: {error_msg}")
            return gr.Dropdown(choices=AUDIO_FILES + [""]), error_msg
            
    except Exception as e:
        error_msg = f"❌ Error in handle_audio_upload: {e}"
        print(error_msg)
        traceback.print_exc()
        return gr.Dropdown(choices=AUDIO_FILES + [""]), f"❌ Error uploading {audio_type} audio: {str(e)}"
    
    finally:
        print(f"🎵 ===== EXITING handle_audio_upload for {audio_type} =====")

# =============================================
# FIXED FILE HANDLING FUNCTIONS
# =============================================

def get_file_path(file_input, choice, default):
    """Safely get file path from Gradio file input (handles lists)"""
    if file_input:
        # Handle list of files (multiple upload)
        if isinstance(file_input, list):
            if file_input and hasattr(file_input[0], 'name'):
                return file_input[0].name
            elif file_input:
                return str(file_input[0])
            else:
                return default
        # Handle single file
        elif hasattr(file_input, 'name'):
            return file_input.name
        else:
            return str(file_input)
    elif choice:
        # Handle dropdown choice
        if isinstance(choice, list) and choice:
            choice = choice[0]
        full_path = os.path.join(PROJECT_ROOT, "static", "audio", choice)
        return full_path if os.path.exists(full_path) else default
    else:
        return default

# =============================================
# KEEP ALL YOUR EXISTING FUNCTIONS BELOW (with fixes)
# =============================================

def debug_performance():
    """Debug function to identify performance bottlenecks"""
    print("🔍 ===== PERFORMANCE DEBUGGING =====")
    
    # Check system resources
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    print(f"💻 CPU Usage: {cpu_percent}%")
    print(f"💾 Memory Usage: {memory.percent}% ({memory.used//1024//1024}MB / {memory.total//1024//1024}MB)")
    
    # Check if Chrome processes are running
    chrome_processes = []
    for proc in psutil.process_iter(['name']):
        try:
            if 'chrome' in proc.info['name'].lower():
                chrome_processes.append(proc.info['name'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    print(f"🌐 Chrome processes: {len(chrome_processes)}")
    
    # Check frames directory
    frames_dir = os.path.join(PROJECT_ROOT, "frames")
    if os.path.exists(frames_dir):
        frame_files = [f for f in os.listdir(frames_dir) if f.startswith('frame_') and f.endswith('.png')]
        print(f"🖼️  Frames generated: {len(frame_files)}")
    
    return f"✅ Performance check complete - CPU: {cpu_percent}%, Memory: {memory.percent}%, Chrome processes: {len(chrome_processes)}"

# Paths
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPT_FILE = os.path.join(PROJECT_ROOT, "script.txt")
BG_TIMELINE_FILE = os.path.join(PROJECT_ROOT, "frames", "bg_timeline.json")

# Renderer state (fresh each session)
try:
    render_bubble.frame_count = 0
    render_bubble.timeline = []
    render_bubble.renderer = WhatsAppRenderer()
    print("✅ Renderer initialized")
except Exception as e:
    print(f"⚠️ Renderer initialization failed: {e}")

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

# Global flag to control auto-refresh thread
auto_refresh_running = False
auto_refresh_thread = None

# Flag to track if video rendering is in progress
rendering_in_progress = False

# Groq client (assuming API key is set in environment)
try:
    groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    print("✅ Groq client initialized")
except Exception as e:
    print(f"⚠️ Groq client initialization failed: {e}")
    groq_client = None

# --------------------------
# Functions helper
# --------------------------

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
        return [], "⚠️ No timeline file found.", "00:00"

    with open(timeline_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not data:
        print("⚠️ Timeline file exists but contains no data.")
        return [], "⚠️ No timeline data found.", "00:00"

    data = [[
        item.get("index", i),
        item.get("username", ""),
        item.get("text", ""),
        item.get("duration", 1.5)
    ] for i, item in enumerate(data)]

    total_seconds, formatted = calculate_total_runtime(data)
    return data, f"✅ Loaded timeline ({len(data)} messages) — ⏱️ Total: {total_seconds:.1f}s ({formatted})", formatted

def start_auto_refresh(load_button, timeline_table, status_box, total_duration_box, interval=10):
    global auto_refresh_running, auto_refresh_thread, rendering_in_progress
    
    def loop():
        while auto_refresh_running:
            if rendering_in_progress:
                print("⏳ Video rendering in progress, pausing auto-refresh")
                time.sleep(2)
                continue
            time.sleep(interval)
            try:
                load_button.click(fn=load_timeline_data, outputs=[timeline_table, status_box, total_duration_box])
            except Exception as e:
                print(f"⚠️ Auto-refresh failed: {e}")
    
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
        print(f"Raw input data to save_timeline_data: {data}")

        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        elif isinstance(data, pd.DataFrame):
            data = data.to_dict('records')
        elif not isinstance(data, list):
            print(f"⚠️ Invalid data type received: {type(data)}")
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
                    print(f"⚠️ Skipping unrecognized row format at index {i}: {row}")
                    continue

                if duration <= 0:
                    print(f"⚠️ Invalid duration {duration} for text '{text}', using 2.0")
                    duration = 2.0

                new_data.append({
                    "index": index,
                    "username": username,
                    "text": text,
                    "duration": duration
                })
            except Exception as row_e:
                print(f"⚠️ Error parsing row {i}: {row_e}")
                continue

        if not new_data:
            print("⚠️ No valid rows to save.")
            return "⚠️ No valid timeline entries to save."

        os.makedirs(frames_dir, exist_ok=True)
        with open(timeline_file, "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=2)

        print(f"✅ Saved {len(new_data)} entries to {timeline_file}")
        return f"✅ Saved {len(new_data)} timeline entries."

    except Exception as e:
        print(f"❌ Error saving timeline: {e}")
        return f"❌ Error saving timeline: {e}"

def auto_pace_timeline():
    timeline_file = os.path.join(PROJECT_ROOT, "frames", "timeline.json")
    if not os.path.exists(timeline_file):
        return [], "⚠️ No timeline.json found to auto-pace.", "00:00"

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
    return rows, f"🎚️ Auto-paced timeline! 🎬 Total: {round(total, 2)}s (≈{formatted})", formatted

def debug_timeline_durations():
    """Debug function to check timeline durations"""
    timeline_file = os.path.join(PROJECT_ROOT, "frames", "timeline.json")
    if os.path.exists(timeline_file):
        with open(timeline_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        total_duration = 0
        print("🔍 DEBUG Timeline Durations:")
        for i, entry in enumerate(data):
            duration = entry.get("duration", 0)
            total_duration += duration
            print(f"   Entry {i}: {entry.get('username', '')}: '{entry.get('text', '')}' -> {duration}s")
        
        print(f"🔍 TOTAL DURATION: {total_duration}s")
        return f"Total duration: {total_duration}s across {len(data)} entries"
    else:
        return "No timeline file found"

def handle_generate(characters, topic, mood, length, title, avatar_upload, manual_script):
    global latest_generated_script

    if manual_script and manual_script.strip():
        latest_generated_script = manual_script.strip()
    else:
        char_list = [c.strip() for c in characters.split(",") if c.strip()]
        if avatar_upload and char_list:
            # Use new avatar handling - ADD THIS LINE
            avatar_path, avatar_status = handle_avatar_upload(avatar_upload, char_list[0])
            print(avatar_status)
        latest_generated_script = generate_script_with_groq(char_list, topic, mood, length, title)

    with open(SCRIPT_FILE, "w", encoding="utf-8") as f:
        f.write(latest_generated_script.strip() + "\n")

    return latest_generated_script, f"✅ Script ready & saved to {SCRIPT_FILE}"

def handle_manual_script(script_text):
    global latest_generated_script
    latest_generated_script = script_text.strip()
    with open(SCRIPT_FILE, "w", encoding="utf-8") as f:
        f.write(latest_generated_script + "\n")
    return latest_generated_script, f"✅ Manual script saved to {SCRIPT_FILE}"

def handle_render(bg_choice, send_choice, recv_choice, typing_choice, typing_bar_choice, bg_upload, send_upload, recv_upload, typing_upload, typing_bar_upload, chat_title, chat_status, chat_avatar, moral_text):
    global latest_generated_script, rendering_in_progress
    reset_typing_sessions()

     # ADD DEBUG HERE
    print(f"🎬 DEBUG handle_render: moral_text = '{moral_text}'")
    print(f"🎬 DEBUG moral_text type: {type(moral_text)}")
    print(f"🎬 DEBUG moral_text is None: {moral_text is None}")
    print(f"🎬 DEBUG moral_text is empty string: {moral_text == ''}")
    

    rendering_in_progress = True
    try:
        if os.path.exists(SCRIPT_FILE):
            with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
                latest_generated_script = f.read().strip()

        if not latest_generated_script.strip():
            return None, "❌ No script available. Please generate a script first.", None

        frames_dir = os.path.join(PROJECT_ROOT, "frames")
        timeline_file = os.path.join(frames_dir, "timeline.json")
        custom_durations = {}

        if os.path.exists(timeline_file):
            try:
                with open(timeline_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for i, entry in enumerate(data):
                    key = f"typing:{entry['username']}" if not entry.get("text") and entry.get("username") else entry.get("text", f"msg_{i}")
                    try:
                        duration = float(entry.get("duration", 2.0))
                        if duration <= 0:
                            print(f"⚠️ Invalid duration {duration} for key '{key}', using 2.0")
                            duration = 2.0
                        custom_durations[key.strip()] = duration
                    except (ValueError, TypeError) as e:
                        print(f"⚠️ Invalid duration for key '{key}': {e}, using 2.0")
                        custom_durations[key.strip()] = 2.0
                print(f"✅ Loaded {len(custom_durations)} custom durations from {timeline_file}")
            except Exception as e:
                print(f"⚠️ Could not read custom durations: {e}")

        if os.path.exists(frames_dir):
            shutil.rmtree(frames_dir)
        os.makedirs(frames_dir, exist_ok=True)

        render_bubble.frame_count = 0
        render_bubble.timeline = []
        render_bubble.renderer = WhatsAppRenderer()

        # Extract unique characters from the script and set chat_status
        characters = set()
        for line in latest_generated_script.splitlines():
            if ":" in line:
                name, _ = line.split(":", 1)
                name = name.strip()
                if name.lower() != "banka":  # Avoid adding Banka here, will handle separately
                    characters.add(name)
        # Add "You" for Banka if present
        if any("Banka" in line for line in latest_generated_script.splitlines()):
            characters.add("You")
        dynamic_chat_status = ", ".join(sorted(characters)) if characters else "No participants"

        render_bubble.renderer.chat_title = chat_title or "Banka😎"
        render_bubble.renderer.chat_status = dynamic_chat_status
        
        # FIXED: Handle chat_avatar properly (it might be a list)
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
        import random
        from backend.meme_fetcher import fetch_meme_from_giphy
        
        for line in latest_generated_script.splitlines():
            line = line.strip()
            if not line:
                continue

            if line.startswith("MEME:"):
                meme_desc = line[5:].strip()
                print(f"🎭 Processing meme: {meme_desc}")

                meme_sender = "MemeBot"
                is_meme_sender = True

                if render_bubble.timeline:
                    for i in range(len(render_bubble.timeline)-1, -1, -1):
                        entry = render_bubble.timeline[i]
                        if entry.get("username") and entry.get("username") != "MemeBot" and not entry.get("is_meme", False):
                            meme_sender = entry["username"]
                            is_meme_sender = entry.get("is_sender", True)
                            break
                
                meme_file = fetch_meme_from_giphy(meme_desc)
                if meme_file:
                    render_bubble(meme_sender, "", meme_path=meme_file, is_sender=is_meme_sender)
                    if render_bubble.timeline:
                        custom_key = ""
                        duration = custom_durations.get(custom_key, 4.0)
                        render_bubble.timeline[-1]["duration"] = duration
                        print(f"✅ Standalone meme from {meme_sender}: {meme_file} (duration: {duration}s, {'custom' if custom_key in custom_durations else 'default'})")
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

                    print(f"🔎 Found meme message: {name}: text='{text_message}' meme='{meme_desc}'")

                    meme_file = fetch_meme_from_giphy(meme_desc)
                    if meme_file:
                        render_bubble(name, text_message, meme_path=meme_file, is_sender=is_sender)
                        if render_bubble.timeline:
                            custom_key = text_message.strip() if text_message.strip() else ""
                            duration = custom_durations.get(custom_key, 4.0 if not text_message.strip() else max(3.0, len(text_message) / 8))
                            render_bubble.timeline[-1]["duration"] = duration
                            print(f"✅ Combined message from {name}: '{text_message}' + meme: {meme_desc} (duration: {duration}s, {'custom' if custom_key in custom_durations else 'default'})")
                    else:
                        print(f"⚠️ Meme not found, sending text only: {name}: {text_message}")
                        if text_message.strip():
                            render_bubble(name, text_message, is_sender=is_sender)
                            if render_bubble.timeline:
                                custom_key = text_message.strip()
                                duration = custom_durations.get(custom_key, max(3.0, len(text_message) / 8))
                                render_bubble.timeline[-1]["duration"] = duration
                                print(f"💬 Text-only (meme failed): {name}: {text_message} (duration: {duration}s, {'custom' if custom_key in custom_durations else 'default'})")
                else:
                    text_message = message
    
                    # Add typing stages for Banka specifically
                    if name.strip().lower() == "banka" and random.random() < 0.85:  # 85% chance for Banka

                        # Auto-generate typing stages for Banka only - BELUGA STYLE
                        typing_sequence = generate_beluga_typing_sequence(text_message)
                        for text, duration, should_play_sound in typing_sequence:
                            render_typing_bar_frame(
                                username=name,
                                upcoming_text=text,
                                duration=duration,
                                is_character_typing=should_play_sound  # This should be True for actual typing frames
                            )
                        print(f"🔊 TYPING BAR: '{text}' | duration: {duration}s | sound: {should_play_sound}")  # Debug output
                    # For other senders, keep the existing random typing logic
                    elif is_sender and random.random() < 0.3:
                        print(f"⌨️ Adding typing indicator for {name}")
                        render_typing_bubble(name, is_sender, custom_durations=custom_durations)  # ✅ For receivers - typing bubble
                        

                    # Then render the actual message bubble normally
                    custom_key = text_message.strip()
                    duration = custom_durations.get(custom_key, max(3.0, len(text_message) / 8))
                    render_bubble(name, text_message, is_sender=is_sender)
                    if render_bubble.timeline:
                        render_bubble.timeline[-1]["duration"] = duration
                        print(f"💬 Message: {name}: {message} (duration: {duration}s, {'custom' if custom_key in custom_durations else 'default'})")

        with open(timeline_file, "w", encoding="utf-8") as f:
            json.dump(render_bubble.timeline, f, indent=2)
        print(f"✅ Saved timeline with {len(render_bubble.timeline)} entries")

        # FIXED: Use the safe file path function
        bg_path = get_file_path(bg_upload, bg_choice, DEFAULT_BG)
        send_path = get_file_path(send_upload, send_choice, DEFAULT_SEND)
        recv_path = get_file_path(recv_upload, recv_choice, DEFAULT_RECV)
        typing_path = get_file_path(typing_upload, typing_choice, DEFAULT_TYPING)
        typing_bar_path = get_file_path(typing_bar_upload, typing_bar_choice, None)

        # Check if background segments exist to determine use_segments
        use_segments = os.path.exists(BG_TIMELINE_FILE)

        # Load segments if using them
        bg_segments = []
        if use_segments and os.path.exists(BG_TIMELINE_FILE):
            with open(BG_TIMELINE_FILE, "r", encoding="utf-8") as f:
                bg_segments = json.load(f)
        

        try:
            video_path = build_video_from_timeline(
                bg_audio=bg_path, 
                send_audio=send_path, 
                recv_audio=recv_path, 
                typing_audio=typing_path,
                typing_bar_audio=typing_bar_path,  # Add typing bar audio
                use_segments=use_segments,  # Use segments if BG timeline file exists
                bg_segments=bg_segments if use_segments else None,  # Pass segments data
                moral_text=moral_text  # ADD THIS LINE - pass moral text
            )
            if video_path:
                optimized_path = video_path.replace('.mp4', '_optimized.mp4')
                subprocess.run([
                    'ffmpeg', '-i', video_path, 
                    '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                    '-c:a', 'aac', '-b:a', '192k',
                    '-movflags', '+faststart', '-y', optimized_path
                ], check=True)
                os.remove(video_path)
                video_path = optimized_path
            custom_count = sum(1 for entry in render_bubble.timeline if (entry.get("text", "").strip() in custom_durations or (entry.get("is_meme", False) and "" in custom_durations) or (entry.get("typing", False) and f"typing:{entry['username']}" in custom_durations)))
            return video_path, f"✅ Video rendered successfully! Used {custom_count} custom durations, {len(render_bubble.timeline) - custom_count} default durations.", video_path
        except Exception as e:
            return None, f"❌ Error rendering video: {e}", None
    finally:
        rendering_in_progress = False

# ... (keep all your other existing functions exactly as they were)

# =============================================
# GRADIO UI WITH CHARACTER MANAGEMENT
# =============================================

with gr.Blocks() as demo:
    gr.Markdown("## 🎬 Chat Script & Video Generator", elem_classes="orange-title")
    
    # Create a simple tab system without complex initial states
    with gr.Tabs() as tabs:
        # ====================================
        # TAB 1: Character Management
        # ====================================
        with gr.TabItem("👥 Character Management", id="characters_tab"):
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
                    characters_list = gr.Dropdown(
                        choices=get_character_names(),
                        label="Select Character",
                        allow_custom_value=False
                    )
                    character_preview = gr.Image(label="Avatar Preview", height=200)
                    character_details = gr.Textbox(label="Character Details", interactive=False, lines=3)
                    
                    gr.Markdown("#### Quick Actions")
                    with gr.Row():
                        refresh_chars_btn = gr.Button("🔄 Refresh List")
                        use_chars_btn = gr.Button("🎭 Use in Script")
            
            # Character management event handlers
            def refresh_characters():
                characters = get_character_names()
                return gr.Dropdown(choices=characters), "", "static/images/contact.png", ""
            
            def load_character_details(name):
                if not name:
                    return "static/images/contact.png", ""
                details = get_character_details(name)
                return details["avatar"], details["personality"]
            
            def add_character_handler(name, personality, avatar):
                if not name:
                    return "❌ Please enter a character name", "", "static/images/contact.png", ""
                
                avatar_path = "static/images/contact.png"
                if avatar:
                    # Save avatar and get path
                    avatar_path, avatar_status = handle_avatar_upload(avatar, name)
                    print(avatar_status)
                
                success, message = add_character(name, avatar_path, personality)
                characters = get_character_names()
                return message, gr.Dropdown(choices=characters), "static/images/contact.png", ""
            
            def update_character_handler(name, personality, avatar):
                if not name:
                    return "❌ Please select a character to update", "", "static/images/contact.png", ""
                
                avatar_path = get_character_details(name)["avatar"]
                if avatar:
                    # Update avatar and get path
                    avatar_path, avatar_status = handle_avatar_upload(avatar, name)
                    print(avatar_status)
                
                success, message = update_character(name, avatar_path, personality)
                characters = get_character_names()
                details = get_character_details(name)
                return message, gr.Dropdown(choices=characters), details["avatar"], details["personality"]
            
            def delete_character_handler(name):
                if not name:
                    return "❌ Please select a character to delete", "", "static/images/contact.png", ""
                
                success, message = delete_character(name)
                characters = get_character_names()
                return message, gr.Dropdown(choices=characters), "static/images/contact.png", ""
            
            def use_characters_in_script():
                characters = get_character_names()
                if characters:
                    char_string = ", ".join(characters)
                    return char_string
                else:
                    return ""
            
            # Connect event handlers
            refresh_chars_btn.click(
                fn=refresh_characters,
                outputs=[characters_list, char_status, character_preview, character_details]
            )
            
            characters_list.change(
                fn=load_character_details,
                inputs=[characters_list],
                outputs=[character_preview, character_details]
            )
            
            add_char_btn.click(
                fn=add_character_handler,
                inputs=[character_name, character_personality, character_avatar],
                outputs=[char_status, characters_list, character_preview, character_details]
            )
            
            update_char_btn.click(
                fn=update_character_handler,
                inputs=[characters_list, character_personality, character_avatar],
                outputs=[char_status, characters_list, character_preview, character_details]
            )
            
            delete_char_btn.click(
                fn=delete_character_handler,
                inputs=[characters_list],
                outputs=[char_status, characters_list, character_preview, character_details]
            )
            
            use_chars_btn.click(
                fn=use_characters_in_script,
                outputs=[character_name]  # This will populate the characters field in the script tab
            )

        # ====================================
        # TAB 2: Script & Video Generator
        # ====================================
        with gr.TabItem("🧠 Script & Video", id="script_tab"):
            with gr.Row():
                characters = gr.Textbox(label="Characters (comma-separated)", placeholder="Jay, Khooi, Banka, brian, Alex, Shiro, Paula")
                topic = gr.Textbox(label="Topic")
                mood = gr.Textbox(label="Mood")
                length = gr.Number(label="Length (lines)", value=10)
                title = gr.Textbox(label="Title")

            # Moral text input
            moral_text = gr.Textbox(
                label="Moral of the Story (Optional)",
                placeholder="e.g., And the moral of the story is...",
                lines=2,
                max_lines=4
            )
            
            with gr.Row():
                chat_title = gr.Textbox(label="Chat Window Title", placeholder="BANKA TOUR GROUP")
                chat_status = gr.Textbox(label="Chat Status", placeholder="jay, khooi, banka, alex, shiro, brian,Paula ")
                chat_avatar = gr.File(label="Chat Avatar", file_types=[".png", ".jpg", ".jpeg"])

            with gr.Row():
                bg_choice = gr.Dropdown(
                    choices=AUDIO_FILES + [""],
                    label="Background Audio",
                    value="",
                    allow_custom_value=True
                )
                bg_upload = gr.File(label="Upload Background Audio(s)", file_count="multiple", file_types=[".mp3"])
                # ADD DEBUG BUTTONS
                debug_upload_btn = gr.Button("🐛 Debug Upload Issue", size="sm")
                test_file_btn = gr.Button("🔧 Test File Ops", size="sm")
                check_gradio_btn = gr.Button("🎯 Check Gradio File", size="sm")
                
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
                typing_bar_choice = gr.Dropdown(
                    choices=[""] + AUDIO_FILES,
                    label="Typing Bar Sound🛑",
                    value="",
                    interactive=False,
                    info="Sound for typing bar animation. Please do not use this one",
                    allow_custom_value=True
                )
                typing_bar_upload = gr.File(label="Upload Typing Bar Sound.(Closed for now)", file_types=[".mp3"], interactive=False)
                avatar_upload = gr.File(label="Upload Avatar", file_types=[".png", ".jpg", ".jpeg"])
            
            with gr.Row():
                manual_script = gr.Textbox(
                    label="Manual Script (optional, overrides AI)",
                    placeholder="Paste your own script here...\nFormat: Name: message",
                    lines=30)
                generate_btn = gr.Button("Generate Script")
                render_btn = gr.Button("Render Video")

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

            # USE THE FIXED UPLOAD FUNCTION
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
            typing_bar_upload.change(
                fn=lambda x: handle_audio_upload_fixed(x, "typing bar"),
                inputs=[typing_bar_upload],
                outputs=[typing_bar_choice, status]
            )

            # ADD DEBUG BUTTON HANDLERS
            debug_upload_btn.click(
                fn=debug_upload_issue,
                outputs=[status]
            )
            
            test_file_btn.click(
                fn=test_basic_file_operations,
                outputs=[status]
            )
            
            check_gradio_btn.click(
                fn=lambda: check_gradio_file_object(bg_upload.value),
                outputs=[status]
            )

            render_btn.click(
                fn=handle_render,
                inputs=[
                    bg_choice, send_choice, recv_choice, typing_choice, typing_bar_choice,
                    bg_upload, send_upload, recv_upload, typing_upload, typing_bar_upload,
                    chat_title, chat_status, chat_avatar, moral_text
                ],
                outputs=[video_file, status, video_download]
            )

        # ====================================
        # TAB 3: Timeline Editor
        # ====================================
        with gr.TabItem("🕒 Timeline Editor", id="timeline_tab"):
            # ... (keep your existing timeline editor code exactly as it was)
            gr.Markdown("### Adjust Message Durations")

            with gr.Row():
                load_timeline_btn = gr.Button("🔁 Load Timeline")
                auto_pace_btn = gr.Button("🎚️ Auto-Pace")
                save_btn = gr.Button("💾 Save Changes")
                auto_refresh_toggle = gr.Checkbox(label="Enable Auto-Refresh", value=True)
                debug_duration_btn = gr.Button("🔍 Debug Durations")

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
            debug_duration_btn.click(fn=debug_timeline_durations, outputs=[status_box])

            # ... (rest of your timeline editor code remains the same)

    # Add auto-refresh functionality
    def on_tab_change(evt: gr.SelectData):
        tab_index = evt.index
        auto_refresh_enabled = auto_refresh_toggle.value if 'auto_refresh_toggle' in locals() else True
        
        print(f"Selected tab index: {tab_index}, Auto-refresh enabled: {auto_refresh_enabled}")
        
        if tab_index == 2 and auto_refresh_enabled:  # Changed to 2 since we added characters tab
            stop_auto_refresh()
            return "⏸️ Auto-refresh stopped"
        else:   
            start_auto_refresh(load_timeline_btn, timeline_table, status_box, total_duration_box, interval=10)
            return "✅ Auto-refresh started for Timeline Editor"

    tabs.select(fn=on_tab_change, inputs=None, outputs=[status_box])

    # Add initialization function to set audio values after load
    def initialize_audio_values():
        """Set initial audio values after the UI loads"""
        if AUDIO_FILES:
            return [
                AUDIO_FILES[0],  # bg_choice
                AUDIO_FILES[0],  # send_choice
                AUDIO_FILES[0],  # recv_choice
                "",              # typing_choice
                AUDIO_FILES[0],  # bg_choice_timeline
                AUDIO_FILES[0],  # send_choice_timeline
                AUDIO_FILES[0],  # recv_choice_timeline
                ""               # typing_choice_timeline
            ]
        return ["", "", "", "", "", "", "", ""]

    # Set initial values after load - THIS MUST BE INSIDE THE BLOCKS CONTEXT
    demo.load(
        fn=initialize_audio_values,
        outputs=[
            bg_choice, send_choice, recv_choice, typing_choice,
            bg_choice_timeline, send_choice_timeline, recv_choice_timeline, typing_choice_timeline
        ]
    )

    # Add CSS
    demo.css = """
    .orange-title {
        color: var(--primary-500) !important;
        text-align: center;
    }
    """

if __name__ == "__main__":
    print("🎬 Starting Banka Video Generator Web UI...")
    demo.queue(max_size=10)
    port = int(os.environ.get("PORT", 7860))
    print(f"🌐 Launching on port {port}...")
    try:
        demo.launch(server_name="0.0.0.0", server_port=port, share=False, inbrowser=False)
    except Exception as e:
        print(f"💥 Failed to launch: {e}")
        traceback.print_exc()
