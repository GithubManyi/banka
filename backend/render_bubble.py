import os
import json
import sys
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from jinja2 import Environment, FileSystemLoader
from PIL import Image
import base64
import hashlib
import colorsys
from backend.avatar_handler import get_avatar
from backend.meme_utils import download_meme, find_meme
from backend.meme_fetcher import fetch_meme_from_giphy
from base64 import b64encode
import mimetypes
import requests
import random
# DEBUG: Track who's calling render_typing_bar_frame
import traceback

# Add performance monitoring
import psutil
import gc

def debug_caller():
    """Print who's calling the rendering functions"""
    stack = traceback.extract_stack()
    # Look for the caller before render_typing_bar_frame
    for i, frame in enumerate(stack[:-1]):
        if 'render_typing_bar_frame' in frame.name:
            caller_frame = stack[i-1] if i > 0 else frame
            print(f"🔍 CALLER: {caller_frame.filename}:{caller_frame.lineno} in {caller_frame.name}")
            print(f"🔍   Calling code: {caller_frame.line}")
            break

# ---------- CONFIG ---------- #
ROOT = r"c:\Users\user\banka"
TMP = os.path.join(ROOT, "tmp_ffmpeg")
FPS = 25
W, H = 1904, 934  # match video size

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "backend", "templates")
TEMPLATE_FILE = "index.html"
OUTPUT_HTML = os.path.join(BASE_DIR, "rendered_chat.html")
FRAMES_DIR = os.path.join(BASE_DIR, "frames")
TIMELINE_FILE = os.path.join(FRAMES_DIR, "timeline.json")

os.makedirs(FRAMES_DIR, exist_ok=True)
os.makedirs(TMP, exist_ok=True)

MAIN_USER = "Banka"  # right-side sender

# ---------- PERFORMANCE OPTIMIZATIONS ---------- #
# Global persistent browser instance for faster rendering
PERSISTENT_DRIVER = None
DRIVER_LAST_USED = 0
DRIVER_TIMEOUT = 30  # Close driver after 30 seconds of inactivity

# Remove all Selenium imports and add:
import html2image

# Global HTML2Image instance
HTI = None

def get_html2image():
    """Get or create HTML2Image instance"""
    global HTI
    if HTI is None:
        HTI = html2image.Html2Image(
            browser='chromium',
            custom_flags=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--headless'
            ]
        )
        print("🚀 Created HTML2Image renderer")
    return HTI

# Update the cleanup function:
def cleanup_resources():
    """Clean up all resources when done"""
    global HTI
    if HTI:
        HTI = None
    FRAME_CACHE.clear()
    gc.collect()
    print("🧹 Cleaned up rendering resources")

def close_persistent_driver():
    """Close the persistent driver when done"""
    global PERSISTENT_DRIVER
    if PERSISTENT_DRIVER:
        try:
            PERSISTENT_DRIVER.quit()
            PERSISTENT_DRIVER = None
            print("🔴 Closed persistent driver")
        except Exception as e:
            print(f"⚠️ Error closing persistent driver: {e}")
            PERSISTENT_DRIVER = None

# Cache for rendered frames to avoid re-rendering identical states
FRAME_CACHE = {}
CACHE_MAX_SIZE = 100

def get_frame_cache_key(messages, show_typing_bar, typing_user, upcoming_text):
    """Generate a cache key for frame rendering"""
    key_data = {
        'messages': [(msg.get('username', ''), msg.get('text', ''), msg.get('typing', False)) 
                    for msg in messages],
        'show_typing_bar': show_typing_bar,
        'typing_user': typing_user,
        'upcoming_text': upcoming_text
    }
    return hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

# ---------- HELPERS ---------- # 
def encode_meme(path):
    if not path or not isinstance(path, str) or not os.path.exists(path):
        return None

    ext = os.path.splitext(path)[1].lower()
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = "application/octet-stream"

    with open(path, "rb") as f:
        data = f.read()
        encoded = base64.b64encode(data).decode("utf-8")

    return {
        "meme": encoded,
        "meme_type": ext,   # ".jpg", ".png", ".mp4", etc.
        "mime": mime        # "image/png", "image/jpeg", "video/mp4"
    }

def name_to_color(username: str) -> str:
    """Readable deterministic color from username, with better spread."""
    h = hashlib.md5(username.strip().lower().encode("utf-8")).hexdigest()
    n = int(h[:8], 16)

    hue = (n * 137) % 360
    saturation = 0.7
    lightness = 0.55

    r, g, b = colorsys.hls_to_rgb(hue/360, lightness, saturation)
    return f'#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}'

def calculate_typing_duration(text):
    """Calculate realistic typing duration based on text length"""
    chars = len(text.strip())
    base_duration = 1.5  # Minimum typing time
    char_duration = 0.08  # Per character typing speed
    
    typing_time = base_duration + (chars * char_duration)
    return min(typing_time, 4.0)  # Cap at 4 seconds max

def debug_timeline_entries():
    """Debug function to check what's in the timeline"""
    if hasattr(render_bubble, 'timeline') and render_bubble.timeline:
        print("🔍 ===== TIMELINE DEBUG =====")
        typing_entries = [e for e in render_bubble.timeline if e.get('typing_bar')]
        print(f"🔍 Found {len(typing_entries)} typing bar entries in timeline")
        
        for i, entry in enumerate(typing_entries[-10:]):  # Show last 10 entries
            print(f"🔍 Entry {i}: text='{entry.get('upcoming_text')}' sound={entry.get('sound')} duration={entry.get('duration')}")
        
        # Check if any have sound=True
        sound_entries = [e for e in typing_entries if e.get('sound')]
        print(f"🔍 Entries with sound=True: {len(sound_entries)}")


# ---------- RENDERER ---------- #
class WhatsAppRenderer:
    def __init__(self, chat_title="Default Group", chat_avatar=None, chat_status=None):
        self.message_history = []
        self.jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR)) 
        self.chat_title = chat_title
        self.chat_avatar = chat_avatar
        self.chat_status = chat_status
        self._last_render_time = 0
        self._render_count = 0
    
    def add_message(self, username, message, meme_path=None, is_read=False, typing=False):
        try:
            ts = datetime.now().strftime("%-I:%M %p").lower()
        except ValueError:
            ts = datetime.now().strftime("%#I:%M %p").lower()

        color = name_to_color(username)
        avatar_path = get_avatar(username)

        meme_data = None
        if meme_path and os.path.exists(meme_path):
            try:
                meme_data = encode_meme(meme_path)
                size_kb = os.path.getsize(meme_path) // 1024
                print(f"✅ add_message: meme encoded {meme_path} size={size_kb}KB mime={meme_data['mime']}")
            except Exception as e:
                print(f"⚠️ add_message: failed to encode meme {meme_path}: {e}")

        # Create single message entry with both text and meme
        message_entry = {
            "username": username,
            "text": message if not typing else "",
            "typing": typing,
            "is_sender": (username.strip().lower() == MAIN_USER.lower()),
            "is_read": is_read,
            "timestamp": ts,
            "color": color,
            "avatar": os.path.basename(avatar_path)
        }
    
        # Add meme data to the same message if present
        if meme_data:
            message_entry["meme"] = meme_data["meme"]
            message_entry["meme_type"] = meme_data["meme_type"]
            message_entry["mime"] = meme_data["mime"]
    
        self.message_history.append(message_entry)
        print(f"✅ Added combined message: {username} - Text: '{message}' - Has meme: {bool(meme_data)} - Typing: {typing}")

    def render_frame(self, frame_file, show_typing_bar=False, typing_user=None, upcoming_text="", driver=None, short_wait=False):
        """
        Optimized frame rendering with HTML2Image
        """
        start_time = time.time()
        self._render_count += 1
        
        # Check cache first (except for typing frames to maintain character-by-character animation)
        is_typing_frame = show_typing_bar and upcoming_text
        cache_key = get_frame_cache_key(self.message_history, show_typing_bar, typing_user, upcoming_text)
        
        # Don't cache typing frames to maintain the exact character-by-character animation
        if not is_typing_frame and cache_key in FRAME_CACHE and os.path.exists(FRAME_CACHE[cache_key]):
            # Copy cached frame instead of re-rendering (for non-typing frames only)
            cached_frame = FRAME_CACHE[cache_key]
            if os.path.exists(cached_frame):
                import shutil
                shutil.copy2(cached_frame, frame_file)
                print(f"⚡ Using cached frame: {cache_key[:8]}...")
                return f"CACHED: {cached_frame}"
        
        template = self.jinja_env.get_template(TEMPLATE_FILE)

        # Filter typing bubbles for sender
        filtered_messages = []
        for msg in self.message_history:
            if msg['is_sender'] and msg['typing']:
                continue
            filtered_messages.append(msg)

        rendered_html = template.render(
            messages=filtered_messages,
            chat_title=getattr(self, "chat_title", None),
            chat_avatar=getattr(self, "chat_avatar", None),
            chat_status=getattr(self, "chat_status", None),
            show_typing_bar=show_typing_bar,
            typing_user=typing_user,
            upcoming_text=upcoming_text
        )

        with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
            f.write(rendered_html)

        # Use HTML2Image for rendering
        hti = get_html2image()
        
        # Save HTML to temporary file
        temp_html = os.path.join(FRAMES_DIR, f"temp_{render_bubble.frame_count}.html")
        with open(temp_html, "w", encoding="utf-8") as f:
            f.write(rendered_html)
        
        # Render to image
        hti.screenshot(
            html_file=temp_html,
            save_as=os.path.basename(frame_file),
            size=(1920, 1080)
        )
        
        # Move the screenshot to the correct location
        generated_file = os.path.join(os.getcwd(), os.path.basename(frame_file))
        if os.path.exists(generated_file):
            os.rename(generated_file, frame_file)
        
        # Clean up temp HTML file
        if os.path.exists(temp_html):
            os.remove(temp_html)
        
        # Cache non-typing frames only (to maintain exact typing animation)
        if not is_typing_frame and len(FRAME_CACHE) < CACHE_MAX_SIZE:
            FRAME_CACHE[cache_key] = frame_file
        
        render_time = time.time() - start_time
        if render_time > 0.5:  # Only log slow renders
            print(f"⏱️ Frame {self._render_count} rendered in {render_time:.2f}s")
        
        return rendered_html

# ---------- BUBBLE RENDERING ---------- #
def render_bubble(username, message="", meme_path=None, is_sender=None, is_read=False, typing=False):
    """
    Optimized bubble rendering with performance improvements.
    KEEPS THE EXACT SAME NUMBER OF FRAMES FOR TYPING ANIMATIONS.
    """
    # initialize renderer state once
    if not hasattr(render_bubble, 'renderer'):
        render_bubble.renderer = WhatsAppRenderer(
            chat_title="BANKA TOUR GROUP",
            chat_avatar="static/images/group.png",
            chat_status="jay, khooi, banka, Paula"
        )
        render_bubble.frame_count = 0
        render_bubble.timeline = []

    # decide sender side if not provided
    if is_sender is None:
        is_sender = (username.strip().lower() == MAIN_USER.lower())

    # small helpers
    def _text_duration(text: str, typing_flag: bool) -> float:
        if typing_flag:
            return 1.5
        chars = len(text.strip()) if text else 0
        return max(2.5, chars / 10.0)

    def _meme_duration(path: str) -> float:
        if not path or not os.path.exists(path):
            return 3.0
        try:
            with Image.open(path) as img:
                w, h = img.size
            aspect_ratio = h / max(w, 1)
            size_factor = (w * h) / (1920 * 1080)
            meme_duration = 2.0 + (aspect_ratio * 1.5) + (size_factor * 4.0)
            return max(2.5, min(meme_duration, 6.0))
        except Exception:
            return 3.0

    # 🔹 FIXED: Handle typing differently based on sender vs receiver
    if typing:
        if is_sender:
            # For sender (Banka) - show typing bar, NOT typing indicator bubble
            print(f"⌨️ Sender {username} typing - using typing bar instead of bubble")
            return render_typing_bar_frame(username, upcoming_text=message if message else "", duration=1.5)
        else:
            # For receiver - show typing indicator bubble
            print(f"⌨️ Receiver {username} typing - showing typing bubble")
            original_history = render_bubble.renderer.message_history.copy()
            render_bubble.renderer.add_message(username, None, typing=True)
            frame_file = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
            render_bubble.renderer.render_frame(frame_file, short_wait=True)  # Use short wait
            render_bubble.renderer.message_history = original_history

            entry = {
                "frame": os.path.abspath(frame_file),
                "duration": 1.5,
                "is_sender": is_sender,
                "username": username,
                "text": "",
                "is_meme": False,
                "meme_path": None,
                "typing": True
            }
            render_bubble.timeline.append(entry)
            with open(TIMELINE_FILE, "w", encoding="utf-8") as tf:
                json.dump(render_bubble.timeline, tf, indent=2)

            render_bubble.frame_count += 1
            return frame_file

    # Normal rendering for all users
    render_bubble.renderer.add_message(username, message, meme_path=meme_path, is_read=is_read, typing=False)
    frame_file = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
    
    # Use short wait for better performance
    is_typing_bar = (username.strip().lower() == MAIN_USER.lower() and not message)
    render_bubble.renderer.render_frame(frame_file, show_typing_bar=False, short_wait=is_typing_bar)

    # compute durations:
    text_dur = _text_duration(message, False)
    meme_dur = _meme_duration(meme_path) if meme_path else 0.0

    # If there's a meme, let the meme duration dominate so next message waits.
    if meme_path:
        duration = max(text_dur, meme_dur)
    else:
        duration = text_dur

    entry = {
        "frame": os.path.abspath(frame_file),
        "duration": round(duration, 3),
        "is_sender": is_sender,
        "username": username,
        "text": message,
        "is_meme": bool(meme_path),
        "meme_path": meme_path,
        "typing": False
    }

    # attach meme base64 & mime info for video builder if available
    if meme_path and os.path.exists(meme_path):
        try:
            meme_info = encode_meme(meme_path)
            if meme_info:
                entry["meme_type"] = meme_info.get("meme_type")
                entry["meme_b64"] = meme_info.get("meme")
                entry["mime"] = meme_info.get("mime")
        except Exception as e:
            print(f"⚠️ render_bubble: failed to encode meme {meme_path}: {e}")

    # append timeline and persist
    render_bubble.timeline.append(entry)
    with open(TIMELINE_FILE, "w", encoding="utf-8") as tf:
        json.dump(render_bubble.timeline, tf, indent=2)

    render_bubble.frame_count += 1
    return frame_file

def render_meme(username, meme_path):
    return render_bubble(username, "", meme_path=meme_path)

def render_typing_bubble(username, duration=None, is_sender=None, custom_durations=None):
    custom_durations = custom_durations or {}  # ✅ prevents NoneType errors
    """Optimized typing bubble rendering"""
    if not hasattr(render_bubble, 'renderer'):
        render_bubble.renderer = WhatsAppRenderer(
            chat_title="BANKA TOUR GROUP",
            chat_avatar="static/images/group.png", 
            chat_status="jay, khooi, banka"
        )
        render_bubble.frame_count = 0
        render_bubble.timeline = []
    

    if is_sender is None:
        is_sender = (username.strip().lower() == MAIN_USER.lower())

    # 🔹 FIXED: Don't show typing bubbles for sender
    if is_sender:
        print(f"⌨️ Skipping typing bubble for sender {username} - using typing bar instead")
        return render_typing_bar_frame(username, "", duration=1.5)

    # Use the MAIN renderer, but temporarily add typing message
    original_history = render_bubble.renderer.message_history.copy()
    
    # Add typing indicator to main renderer temporarily
    render_bubble.renderer.add_message(username, None, typing=True)
    
    frame_file = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
    render_bubble.renderer.render_frame(frame_file, short_wait=True)  # Use short wait
    
    # Restore original history (remove the typing message)
    render_bubble.renderer.message_history = original_history

    # Use custom duration if available, else default to 1.5
    typing_key = f"typing:{username}"
    duration = custom_durations.get(typing_key, 1.5) if custom_durations else 1.5
    if duration <= 0:
        print(f"⚠️ Invalid duration {duration} for typing indicator '{typing_key}', using 1.5")
        duration = 1.5

    entry = {
        "frame": os.path.abspath(frame_file),
        "duration": duration,
        "is_sender": is_sender,
        "username": username,
        "text": "",
        "is_meme": False,
        "meme_path": None,
        "typing": True,
        "typing_sound": False  # ✅ FORCE NO SOUND for typing bubbles
    }

    render_bubble.timeline.append(entry)
    
    with open(TIMELINE_FILE, "w", encoding="utf-8") as tf:
        json.dump(render_bubble.timeline, tf, indent=2)

    render_bubble.frame_count += 1
    print(f"⌨️ Typing indicator for {username} (duration: {duration}s, {'custom' if typing_key in custom_durations else 'default'})")
    return frame_file

# ---------- VIDEO HELPERS ---------- #
def add_still_to_concat(concat_lines, frame_file, duration):
    safe_path = frame_file.replace("\\", "/")
    concat_lines.append(f"file '{safe_path}'")
    concat_lines.append(f"duration {float(duration):.3f}")

def handle_meme_image(meme_path, output_path, duration=1.0, fps=25):
    if not os.path.exists(meme_path):
        raise FileNotFoundError(f"Meme not found: {meme_path}")

    img = Image.open(meme_path)
    img.thumbnail((W, H))

    # Create the output directory if it doesn't exist
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Save a single frame (not multiple frames)
    frame_path = output_path if output_path.endswith('.png') else output_path + '.png'
    img.save(frame_path, "PNG")
    
    # Return the single frame path and duration
    return frame_path, duration

def render_typing_bar_frame(username, upcoming_text="", frame_path=None, duration=None, is_character_typing=True):
    # DEBUG: Find who's calling this
    debug_caller()
    print(f"🔍 CALLED WITH: '{upcoming_text}', duration={duration}, is_character_typing={is_character_typing}")
    
    """
    SIMPLIFIED: Render typing bar frames with CONTINUOUS sound logic.
    """
    if not hasattr(render_bubble, 'renderer'):
        render_bubble.renderer = WhatsAppRenderer(
            chat_title="BANKA TOUR GROUP",
            chat_avatar="static/images/group.png",
            chat_status="jay, khooi, banka"
        )
        render_bubble.frame_count = 0
        render_bubble.timeline = []
    
    if not frame_path:
        frame_path = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")

    # Skip typing bar for non-sender
    if username.strip().lower() != MAIN_USER.lower():
        print(f"⌨️ Non-sender '{username}' - using typing bubble instead of typing bar")
        return render_typing_bubble(username, custom_durations={})

    # Save current history
    original_history = render_bubble.renderer.message_history.copy()

    # Use short_wait=True for typing frames
    render_bubble.renderer.render_frame(
        frame_file=frame_path,
        show_typing_bar=True,
        typing_user=username,
        upcoming_text=upcoming_text,
        short_wait=True
    )

    # Restore original history
    render_bubble.renderer.message_history = original_history

    # SIMPLE duration handling
    if duration is None or duration <= 0:
        if not is_character_typing or upcoming_text.endswith('|'):
            frame_duration = 0.8  # Longer for cursor blinks
        else:
            frame_duration = 0.4  # Shorter for actual typing
    else:
        frame_duration = duration
    
    # ✅ SIMPLIFIED SOUND LOGIC: Continuous sound during active typing
    current_text = upcoming_text.replace("|", "").strip()
    
    # Get previous frame's text for comparison
    prev_text = ""
    if render_bubble.timeline:
        # Look backwards for the most recent typing bar entry
        for entry in reversed(render_bubble.timeline):
            if entry.get("typing_bar"):
                prev_text = entry.get("upcoming_text", "").replace("|", "").strip()
                break
    
    # ✅ NEW RULES FOR CONTINUOUS SOUND:
    # 1. Play sound during ACTIVE typing (is_character_typing=True)
    # 2. Stop sound during cursor blinks (is_character_typing=False)  
    # 3. Stop sound when text is complete (no cursor) and we're in the last 3 frames
    should_play_sound = is_character_typing
    
    # Check if this is one of the last 3 frames (no cursor, complete text)
    is_final_frame = (not upcoming_text.endswith('|') and current_text)
    if is_final_frame:
        # Look ahead to see if there are more typing frames
        future_has_typing = False
        # We can't see future, but we can check if this looks like a completion frame
        should_play_sound = False  # No sound in final frames
        print(f"🎹 FINAL FRAME DETECTED: '{upcoming_text}' - NO SOUND")

    print(f"🎹 SIMPLE SOUND: is_typing={is_character_typing} -> sound={should_play_sound}")
    print(f"🎹 TEXT: prev='{prev_text}' current='{current_text}'")

    # Generate session ID for continuous sound grouping
    if not hasattr(render_bubble, 'current_typing_session'):
        render_bubble.current_typing_session = None
    
    # Start new session when we begin typing after not typing
    if is_character_typing and not prev_text and current_text:
        render_bubble.current_typing_session = f"session_{render_bubble.frame_count}"
        print(f"🎹 🆕 STARTING NEW TYPING SESSION: {render_bubble.current_typing_session}")
    
    # End session when we stop typing
    if not is_character_typing and render_bubble.current_typing_session:
        print(f"🎹 🛑 ENDING TYPING SESSION: {render_bubble.current_typing_session}")
        render_bubble.current_typing_session = None

    # SIMPLE timeline entry
    entry = {
        "frame": os.path.abspath(frame_path),
        "duration": frame_duration,
        "is_sender": True,
        "username": username,
        "text": "",
        "is_meme": False,
        "meme_path": None,
        "typing_bar": True,
        "upcoming_text": upcoming_text,
        "sound": should_play_sound,
        "typing_session_id": render_bubble.current_typing_session if is_character_typing else None
    }

    print(f"🎹 Frame {render_bubble.frame_count}: '{upcoming_text}' - Sound: {should_play_sound} - Session: {render_bubble.current_typing_session}")

    render_bubble.timeline.append(entry)

    with open(TIMELINE_FILE, "w", encoding="utf-8") as tf:
        json.dump(render_bubble.timeline, tf, indent=2)

    render_bubble.frame_count += 1
    return frame_path

def generate_beluga_typing_sequence(real_message):
    """
    FIXED: Actually renders typing frames with CONTINUOUS sound control
    """
    if not real_message:
        return []

    import random

    fake_phrases = [
        "Wait", "Hold on", "Hmm", "Nah", "Actually", "But", "Wait what",
        "No way", "Umm", "For real", "Bruh", "Lol", "Well", "Okay"
    ]
    num_fakes = random.randint(1, 2)
    selected_fakes = random.sample(fake_phrases, num_fakes)

    sequence = []
    SPEED_MULTIPLIER = 0.5

    def typing_speed_for(char):
        if char in [".", ",", "!", "?", "…"]:
            base = random.uniform(0.12, 0.25)
        elif char == " ":
            base = random.uniform(0.06, 0.1)
        elif ord(char) > 127:
            base = random.uniform(0.15, 0.25)
        else:
            base = random.uniform(0.07, 0.17)
        return base * SPEED_MULTIPLIER

    def blink_frame(text, blinks=1):
        """Adds cursor blinks - NO SOUND during blinks"""
        for _ in range(blinks):
            sequence.append((text + "|", 0.25, False))  # False = no typing activity (NO SOUND)
            sequence.append((text, 0.25, False))        # False = no typing activity (NO SOUND)

    # CONTROLLED fake typing (1-2 times per video, not per message)
    if not hasattr(render_bubble, 'fake_typing_count'):
        render_bubble.fake_typing_count = 0
        render_bubble.max_fakes_per_video = random.randint(1, 2)  # 1-2 fakes total

    if (render_bubble.fake_typing_count < render_bubble.max_fakes_per_video and 
        random.random() < 0.4):  # 40% chance per message
        
        fake = random.choice(fake_phrases)
        render_bubble.fake_typing_count += 1
        print(f"🎲 FAKE TYPING {render_bubble.fake_typing_count}/{render_bubble.max_fakes_per_video}: '{fake}'")
        
        # Type fake text WITH SOUND (continuous)
        buf = ""
        for ch in fake:
            buf += ch
            sequence.append((buf + "|", typing_speed_for(ch), True))
        
        # Blink cursor - NO SOUND
        blink_frame(buf, blinks=1)
        
        # Delete fake text - NO SOUND
        for i in range(len(fake) - 1, -1, -1):
            buf = fake[:i]
            sequence.append((buf + "|", random.uniform(0.15, 0.25), False))
        
        # Pause - NO SOUND
        sequence.append(("", 0.5, False))
    else:
        print("🎲 No fake typing this message")

    # Type actual message WITH SOUND (continuous)
    buf = ""
    for i, ch in enumerate(real_message):
        buf += ch
        is_active_typing = True
        
        # Last 3 characters should have no sound
        if i >= len(real_message) - 3:
            is_active_typing = False
            print(f"🎹 LAST 3 CHARS: '{ch}' at position {i} - NO SOUND")
            
        sequence.append((buf + "|", typing_speed_for(ch), is_active_typing))

    # Final cursor blinks and stable frame - NO SOUND
    blink_frame(real_message, blinks=2)
    sequence.append((real_message, 0.8, False))

    print(f"⌨️ Generated {len(sequence)} typing frames for '{real_message}'")
    
    return sequence

def render_typing_sequence(username, real_message):
    # After rendering the typing sequence, add this:
    debug_timeline_entries()
    """
    FIXED: Actually renders the typing sequence frames with sound
    """
    print(f"🎬 Starting typing sequence for '{username}': '{real_message}'")
    
    sequence = generate_beluga_typing_sequence(real_message)
    
    rendered_frames = []
    for i, (text, duration, has_sound) in enumerate(sequence):
        print(f"🎬 Rendering typing frame {i}: '{text}' - duration: {duration}s - sound: {has_sound}")
        
        # Actually render the frame with sound information
        frame_path = render_typing_bar_frame(
            username=username,
            upcoming_text=text,
            duration=duration,
            is_character_typing=has_sound  # This controls the sound!
        )
        rendered_frames.append(frame_path)
    
    print(f"🎬 Completed typing sequence: {len(rendered_frames)} frames rendered")
    return rendered_frames


# ---------- CLEANUP ---------- #
def cleanup_resources():
    """Clean up all resources when done"""
    close_persistent_driver()
    FRAME_CACHE.clear()
    gc.collect()
    print("🧹 Cleaned up rendering resources")

def reset_typing_sessions():
    """Reset typing session tracking - call this when starting a new video"""
    if hasattr(render_bubble, 'typing_session_active'):
        render_bubble.typing_session_active = False
        render_bubble.typing_session_start = 0
        print("🔄 Reset typing session tracking")


# ---------- MAIN SCRIPT ---------- #
if __name__ == "__main__":
    try:
        if len(sys.argv) < 2:
            print("Usage: python render_bubble.py script.txt")
            sys.exit(1)

        script_file = sys.argv[1]
        render_bubble.frame_count = 0
        render_bubble.timeline = []
        render_bubble.renderer = WhatsAppRenderer()
         # ✅ ADD THESE for session tracking:
        render_bubble.typing_session_active = False
        render_bubble.typing_session_start = 0
        print("🔄 Initialized typing session tracking for main script")

        with open(script_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("MEME:"):
                meme_desc = line[5:].strip()
                print(f"🔎 Found MEME description: {meme_desc}")

                meme_file = find_meme(meme_desc, assets_dir=os.path.join("assets", "memes", "auto"))

                if not meme_file:
                    print(f"⚠️ No meme found for '{meme_desc}', skipping…")
                    continue

                print(f"✅ Matched meme '{meme_desc}' → {meme_file}")
                frame_file = render_meme(MAIN_USER, meme_file)

                # Add timeline entry with base64
                render_bubble.timeline[-1]["is_meme"] = True
                meme_info = encode_meme(meme_file)
                render_bubble.timeline[-1]["meme_type"] = meme_info["meme_type"]
                render_bubble.timeline[-1]["meme_b64"] = meme_info["meme"]
                render_bubble.timeline[-1]["mime"] = meme_info["mime"]

                if not meme_file:
                    auto_dir = os.path.join("assets", "memes", "auto")
                    files = [f for f in os.listdir(auto_dir) if os.path.isfile(os.path.join(auto_dir, f))]
                    if not files:
                        print(f"⚠️ No memes available in {auto_dir}, skipping random fallback")
                        continue
                    meme_file = os.path.join(auto_dir, random.choice(files))
                    print(f"⚠️ No exact match for '{meme_desc}', using random: {meme_file}")

                else:
                    print(f"✅ Matched meme '{meme_desc}' → {meme_file}")

                if meme_file:
                    if meme_file.startswith("http"):
                        try:
                            local_name = os.path.basename(meme_file.split("?")[0])
                            local_path = os.path.join("assets", "memes", "auto", local_name)
                            os.makedirs(os.path.dirname(local_path), exist_ok=True)
                            print(f"⬇️ Downloading meme URL to {local_path}")
                            with requests.get(meme_file, stream=True, timeout=20) as r:
                                r.raise_for_status()
                                with open(local_path, "wb") as fh:
                                    for ch in r.iter_content(8192):
                                        fh.write(ch)
                            meme_file = local_path
                        except Exception as e:
                            print(f"⚠️ Failed to download meme URL {meme_file}: {e}")

                    if not os.path.exists(meme_file):
                        print(f"⚠️ Meme file not found after fetch: {meme_file}")
                    else:
                        print(f"✅ Meme fetched: {meme_file} (exists={os.path.exists(meme_file)})")
                        frame_file = render_meme(MAIN_USER, meme_file)

                        # Add timeline entry with base64
                        render_bubble.timeline[-1]["is_meme"] = True
                        render_bubble.timeline[-1]["meme_type"] = os.path.splitext(meme_file)[1].lower()
                        render_bubble.timeline[-1]["meme_b64"] = encode_meme(meme_file)

                else:
                    print(f"⚠️ Meme fetch failed for: {meme_desc}")

            elif line.startswith("[MEME]"):
                parts = line.replace("[MEME]", "").strip().split(" ", 1)
                if len(parts) == 2:
                    username, meme_path = parts[0], parts[1]
                else:
                    username, meme_path = MAIN_USER, parts[0]
                print(f"🔎 Found explicit [MEME] line: user={username} path={meme_path}")
                if not os.path.exists(meme_path):
                    print(f"⚠️ explicit meme file not found: {meme_path}")
                else:
                    frame_file = render_meme(username, meme_path)
                    render_bubble.timeline[-1]["is_meme"] = True
                    render_bubble.timeline[-1]["meme_type"] = os.path.splitext(meme_path)[1].lower()
                    render_bubble.timeline[-1]["meme_b64"] = encode_meme(meme_path)

            elif ":" in line:
                name, message = line.split(":", 1)
                name = name.strip()
                message = message.strip()
                is_sender = (name.lower() == MAIN_USER.lower())
                is_read = False

                # 🔥 FIX: If it's Banka typing, render the typing sequence first
                if is_sender and message:
                    print(f"🎬 Banka is typing: '{message}' - rendering typing sequence...")
                    # Render the typing sequence with sound
                    render_typing_sequence(name, message)
                    # Now render the final message bubble
                    print(f"🎬 Rendering final message after typing...")
                
                # Rest of your existing code continues here...

                # Check if this message contains a meme reference
                if "[MEME]" in message:
                    # COMBINE: Send text + meme in the SAME bubble
                    text_part, meme_desc = message.split("[MEME]", 1)
                    text_message = text_part.strip()
                    meme_desc = meme_desc.strip()

                    print(f"🔎 Found meme in message: {name}: '{text_message}' + [MEME:{meme_desc}]")
                    
                    # Look for meme file
                    meme_file = find_meme(meme_desc, assets_dir=os.path.join("assets", "memes", "auto"))
                    
                    if not meme_file:
                        # Fallback to random meme
                        auto_dir = os.path.join("assets", "memes", "auto")
                        files = [f for f in os.listdir(auto_dir) if os.path.isfile(os.path.join(auto_dir, f))]
                        if files:
                            meme_file = os.path.join(auto_dir, random.choice(files))
                            print(f"⚠️ No exact match for '{meme_desc}', using random: {meme_file}")

                    if meme_file and os.path.exists(meme_file):
                        # Send text + meme in the SAME bubble
                        render_bubble(name, text_message, meme_path=meme_file, is_sender=is_sender, is_read=is_read)
                        print(f"✅ Combined message: {name}: '{text_message}' + meme")
                    else:
                        # Fallback: just send text
                        render_bubble(name, text_message, is_sender=is_sender, is_read=is_read)
                        print(f"💬 Text only: {name}: {text_message} (meme not found)")
                else:
                    # Regular text message
                    if not is_sender:
                        for msg in render_bubble.renderer.message_history:
                            if msg["is_sender"]:
                                msg["is_read"] = True

                    print(f"💬 Chat line: {name}: {message[:80]}")
                    render_bubble(name, message, is_sender=is_sender, is_read=is_read)

        print(f"✅ Rendered {render_bubble.frame_count} frames from {script_file}")
        
    finally:
        cleanup_resources()
