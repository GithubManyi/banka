import os
import json
import sys
import time
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from PIL import Image, ImageDraw, ImageFont
import base64
import hashlib
import colorsys
import html2image
import random
import traceback
import gc
import logging
from io import BytesIO
import signal

# ---------- COMPLETE SILENCE FOR PERFORMANCE ---------- #
logging.getLogger().setLevel(logging.ERROR)
for logger in ['html2image', 'PIL', 'selenium', 'urllib3', 'selenium.webdriver.remote.remote_connection']:
    logging.getLogger(logger).setLevel(logging.ERROR)

# SUPPRESS ALL CHROME/DBUS ERRORS
os.environ['DBUS_SESSION_BUS_ADDRESS'] = '/dev/null'
os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = '/dev/null'
os.environ['DISABLE_DEV_SHM'] = 'true'
os.environ['ENABLE_CRASH_REPORTER'] = 'false'
os.environ['GOOGLE_API_KEY'] = 'no'
os.environ['GOOGLE_DEFAULT_CLIENT_ID'] = 'no'
os.environ['GOOGLE_DEFAULT_CLIENT_SECRET'] = 'no'

# DISABLE ALL UNNECESSARY CHROME FEATURES
os.environ['CHROME_HEADLESS'] = 'true'
os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'
os.environ['GALLIUM_DRIVER'] = 'llvmpipe'
os.environ['NO_SANDBOX'] = '1'

# REDIRECT CONSOLE OUTPUT TO DEVNULL
sys.stdout = open(os.devnull, 'w')
sys.stderr = open(os.devnull, 'w')

# ---------- CONFIG ---------- #
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "backend", "templates")
TEMPLATE_FILE = "index.html"
OUTPUT_HTML = os.path.join(BASE_DIR, "rendered_chat.html")
FRAMES_DIR = os.path.join(BASE_DIR, "frames")
TIMELINE_FILE = os.path.join(FRAMES_DIR, "timeline.json")
AVATAR_DIR = os.path.join(BASE_DIR, "static", "avatars")
CHARACTERS_FILE = os.path.join(BASE_DIR, "characters.json")
os.makedirs(FRAMES_DIR, exist_ok=True)

MAIN_USER = "Banka"
W, H = 1904, 934

# ---------- ULTRA PERFORMANCE OPTIMIZATIONS ---------- #
FRAME_CACHE = {}
CACHE_MAX_SIZE = 50  # Smaller cache for speed
AVATAR_CACHE = {}
MESSAGE_HISTORY_LIMIT = 50  # Much smaller history
HTI = None
SIMPLE_MODE = True  # Skip all complex rendering

# ---------- ULTRA-FAST AVATAR MANAGEMENT ---------- #

def load_characters():
    """Load characters - ULTRA FAST"""
    if os.path.exists(CHARACTERS_FILE):
        try:
            with open(CHARACTERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def get_character_avatar_path(username):
    """Get avatar path - ULTRA FAST"""
    cache_key = f"avatar_path_{username.strip().lower()}"
    if cache_key in AVATAR_CACHE:
        return AVATAR_CACHE[cache_key]
    
    username_clean = username.strip()
    characters = load_characters()
    
    if username_clean in characters:
        avatar_path = characters[username_clean].get("avatar", "")
        if avatar_path:
            if not os.path.isabs(avatar_path):
                full_path = os.path.join(BASE_DIR, avatar_path)
            else:
                full_path = avatar_path
            if os.path.exists(full_path):
                AVATAR_CACHE[cache_key] = full_path
                return full_path

    return ""

def encode_avatar_for_html(avatar_path):
    """Encode avatar - ULTRA FAST"""
    if not avatar_path or not os.path.exists(avatar_path):
        return ""
    
    cache_key = f"avatar_base64_{avatar_path}"
    if cache_key in AVATAR_CACHE:
        return AVATAR_CACHE[cache_key]
  
    try:
        with open(avatar_path, "rb") as f:
            avatar_data = base64.b64encode(f.read()).decode("utf-8")
        mime_type = "image/png"
        result = f"data:{mime_type};base64,{avatar_data}"
        AVATAR_CACHE[cache_key] = result
        return result
    except Exception:
        return ""

def get_html2image():
    """Get HTML2Image with MAXIMUM error suppression"""
    global HTI
    if HTI is None:
        try:
            # Minimal Chrome paths
            possible_paths = [
                '/usr/bin/chromium',
                '/usr/bin/chromium-browser',
                '/app/.apt/usr/bin/chromium-browser'
            ]
          
            chromium_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    chromium_path = path
                    break
          
            if chromium_path:
                # ULTRA-MINIMAL CHROME FLAGS - NO DBUS, NO ERRORS
                chrome_flags = [
                    '--no-sandbox',
                    '--disable-dev-shm-usage', 
                    '--disable-gpu',
                    '--disable-software-rasterizer',
                    '--headless',
                    '--window-size=1920,1080',
                    '--disable-webgl',
                    '--disable-accelerated-2d-canvas',
                    '--disable-accelerated-video-decode',
                    '--no-default-browser-check',
                    '--no-first-run',
                    '--disable-default-apps',
                    '--disable-features=TranslateUI',
                    '--disable-ipc-flooding-protection',
                    '--disable-vulkan',
                    '--disable-crash-reporter',
                    '--disable-logging',
                    '--disable-breakpad',
                    '--memory-pressure-off',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                    '--mute-audio',
                    '--no-zygote',
                    '--single-process',
                    '--disable-threaded-animation',
                    '--disable-threaded-scrolling',
                    '--disable-in-process-stack-traces',
                    '--disable-histogram-customizer',
                    '--disable-gl-drawing-for-tests',
                    '--user-data-dir=/tmp/chrome-user-data'
                ]
              
                HTI = html2image.Html2Image(
                    browser='chromium',
                    browser_executable=chromium_path,
                    custom_flags=chrome_flags
                )
        except Exception:
            HTI = None
    return HTI

def cleanup_resources():
    """Clean up resources"""
    global HTI
    if HTI:
        HTI = None
    FRAME_CACHE.clear()
    AVATAR_CACHE.clear()
    gc.collect()

def get_frame_cache_key(messages, show_typing_bar, typing_user, upcoming_text):
    """Generate cache key - ULTRA FAST"""
    key_data = {
        'messages': [(msg.get('username', ''), msg.get('text', ''))
                    for msg in messages[-5:]],  # Only last 5 messages
        'show_typing_bar': show_typing_bar,
        'typing_user': typing_user
    }
    return hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

# ---------- ULTRA-FAST HELPERS ---------- #

def name_to_color(username: str) -> str:
    """Color from username - ULTRA FAST"""
    cache_key = f"color_{username.strip().lower()}"
    if cache_key in AVATAR_CACHE:
        return AVATAR_CACHE[cache_key]
    
    h = hashlib.md5(username.strip().lower().encode("utf-8")).hexdigest()
    n = int(h[:8], 16)
    hue = (n * 137) % 360
    saturation = 0.7
    lightness = 0.55
    r, g, b = colorsys.hls_to_rgb(hue/360, lightness, saturation)
    result = f'#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}'
    AVATAR_CACHE[cache_key] = result
    return result

# ---------- ULTRA-FAST RENDERER ---------- #

class WhatsAppRenderer:
    def __init__(self, chat_title="Default Group", chat_avatar=None, chat_status=None):
        self.message_history = []
        self.jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
        self.chat_title = chat_title
        self.chat_avatar = chat_avatar
        self.chat_status = chat_status
        self._render_count = 0
        self._template_cache = None
  
    def add_message(self, username, message, meme_path=None, is_read=False, typing=False):
        """ULTRA-FAST message addition"""
        try:
            ts = datetime.now().strftime("%-I:%M %p").lower()
        except ValueError:
            ts = datetime.now().strftime("%#I:%M %p").lower()
  
        color = name_to_color(username)
        avatar_path = get_character_avatar_path(username)
      
        # SIMPLE avatar handling
        avatar_data = ""
        mime = "image/png"
        if avatar_path and os.path.exists(avatar_path):
            avatar_data = encode_avatar_for_html(avatar_path)

        # Build message entry - MINIMAL
        message_entry = {
            "username": username,
            "text": message if not typing else "",
            "typing": typing,
            "is_sender": (username.strip().lower() == MAIN_USER.lower()),
            "is_read": is_read,
            "timestamp": ts,
            "color": color,
            "avatar": avatar_data,
            "avatar_format": mime
        }
  
        self.message_history.append(message_entry)
        
        # Strict history limit
        if len(self.message_history) > MESSAGE_HISTORY_LIMIT:
            self.message_history = self.message_history[-MESSAGE_HISTORY_LIMIT:]

    def render_frame(self, frame_file, show_typing_bar=False, typing_user=None, upcoming_text="", short_wait=False):
        """
        ULTRA-FAST frame rendering - SKIPS CHROME WHEN POSSIBLE
        """
        start_time = time.time()
        self._render_count += 1
      
        # Check cache first
        is_typing_frame = show_typing_bar and upcoming_text
        cache_key = get_frame_cache_key(self.message_history, show_typing_bar, typing_user, upcoming_text)
      
        if not is_typing_frame and cache_key in FRAME_CACHE:
            cached_frame = FRAME_CACHE[cache_key]
            if os.path.exists(cached_frame):
                import shutil
                shutil.copy2(cached_frame, frame_file)
                return "CACHED"
      
        # Use cached template
        if self._template_cache is None:
            template = self.jinja_env.get_template(TEMPLATE_FILE)
            self._template_cache = template
        else:
            template = self._template_cache
    
        # Filter messages
        filtered_messages = []
        for msg in self.message_history:
            if msg['is_sender'] and msg['typing']:
                continue
            filtered_messages.append(msg)
    
        rendered_html = template.render(
            messages=filtered_messages,
            static_path="/app/static",
            chat_title=getattr(self, "chat_title", None),
            chat_avatar=getattr(self, "chat_avatar", None),
            chat_status=getattr(self, "chat_status", None),
            show_typing_bar=show_typing_bar,
            typing_user=typing_user,
            upcoming_text=upcoming_text
        )
    
        with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
            f.write(rendered_html)
    
        # TRY SIMPLE MODE FIRST - SKIP CHROME COMPLETELY
        if SIMPLE_MODE or len(filtered_messages) < 10:
            self._create_simple_frame(frame_file, filtered_messages, show_typing_bar, typing_user, upcoming_text)
        else:
            # Fallback to Chrome only if necessary
            try:
                hti = get_html2image()
                if hti:
                    temp_html = os.path.join(FRAMES_DIR, f"temp_{hash(rendered_html)}.html")
                    with open(temp_html, "w", encoding="utf-8") as f:
                        f.write(rendered_html)
                  
                    hti.screenshot(
                        html_file=temp_html,
                        save_as=os.path.basename(frame_file),
                        size=(1920, 1080)
                    )
                  
                    generated_file = os.path.join(os.getcwd(), os.path.basename(frame_file))
                    if os.path.exists(generated_file):
                        os.rename(generated_file, frame_file)
                  
                    if os.path.exists(temp_html):
                        os.remove(temp_html)
                else:
                    self._create_simple_frame(frame_file, filtered_messages, show_typing_bar, typing_user, upcoming_text)
            except Exception:
                self._create_simple_frame(frame_file, filtered_messages, show_typing_bar, typing_user, upcoming_text)
      
        # Cache non-typing frames
        if not is_typing_frame and len(FRAME_CACHE) < CACHE_MAX_SIZE:
            FRAME_CACHE[cache_key] = frame_file
      
        return "RENDERED"

    def _create_simple_frame(self, frame_file, messages, show_typing_bar, typing_user, upcoming_text):
        """ULTRA-FAST simple frame creation - NO CHROME"""
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            # Simple solid background
            img = Image.new('RGB', (1920, 1080), color=(11, 20, 26))
            draw = ImageDraw.Draw(img)
            
            # Try to load a basic font
            try:
                font_large = ImageFont.truetype("Arial", 36)
                font_small = ImageFont.truetype("Arial", 20)
            except:
                font_large = ImageFont.load_default()
                font_small = ImageFont.load_default()
            
            # Minimal header
            draw.rectangle([0, 0, 1920, 100], fill=(17, 27, 33))
            draw.text((50, 30), f"💬 {self.chat_title}", fill=(255, 255, 255), font=font_large)
            draw.text((50, 70), f"Messages: {len(messages)}", fill=(134, 150, 160), font=font_small)
            
            # Show last few messages
            y_pos = 120
            for msg in messages[-8:]:  # Only show last 8 messages
                username = msg.get('username', '')
                text = msg.get('text', '')[:50]  # Truncate long messages
                is_sender = msg.get('is_sender', False)
                
                color = (0, 92, 75) if is_sender else (32, 44, 51)
                x_pos = 1000 if is_sender else 100
                
                # Simple message bubble
                draw.rectangle([x_pos-10, y_pos-10, x_pos+400, y_pos+40], fill=color, outline=color, width=2)
                draw.text((x_pos, y_pos), f"{username}: {text}", fill=(255, 255, 255), font=font_small)
                y_pos += 50
                
                if y_pos > 900:
                    break
            
            # Typing indicator
            if show_typing_bar and typing_user:
                draw.rectangle([0, 980, 1920, 1080], fill=(17, 27, 33))
                draw.text((100, 1000), f"⌨️ {typing_user} is typing...", fill=(100, 255, 100), font=font_small)
            
            # Fast save with low quality
            img.save(frame_file, format="PNG", optimize=True, quality=60)
            
        except Exception:
            # Absolute fallback - solid color image
            try:
                img = Image.new('RGB', (1920, 1080), color=(11, 20, 26))
                img.save(frame_file, format="PNG")
            except Exception:
                pass

# ---------- ULTRA-FAST BUBBLE RENDERING ---------- #

def render_bubble(username, message="", meme_path=None, is_sender=None, is_read=False, typing=False):
    """
    ULTRA-FAST bubble rendering - SKIPS TYPING ANIMATIONS
    """
    # Initialize renderer state once
    if not hasattr(render_bubble, 'renderer'):
        render_bubble.renderer = WhatsAppRenderer(
            chat_title="BANKA TOUR GROUP",
            chat_avatar="static/images/group.png",
            chat_status="jay, khooi, banka, Paula"
        )
        render_bubble.frame_count = 0
        render_bubble.timeline = []
    
    # Determine sender
    if is_sender is None:
        is_sender = (username.strip().lower() == MAIN_USER.lower())
    
    # SKIP TYPING ANIMATIONS FOR SPEED
    if typing:
        if is_sender:
            # Simple typing bar instead of complex animation
            frame_file = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
            render_bubble.renderer.render_frame(frame_file, show_typing_bar=True, typing_user=username)
            entry = {
                "frame": os.path.abspath(frame_file),
                "duration": 1.0,  # Shorter duration
                "is_sender": is_sender,
                "username": username,
                "text": "",
                "is_meme": False,
                "meme_path": None,
                "typing": True
            }
            render_bubble.timeline.append(entry)
            render_bubble.frame_count += 1
            return frame_file
        else:
            # Skip receiver typing entirely for speed
            return None
    
    # Normal message rendering
    render_bubble.renderer.add_message(username, message, meme_path=meme_path, is_read=is_read, typing=False)
    frame_file = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
  
    render_bubble.renderer.render_frame(frame_file, show_typing_bar=False)
    
    # Simple duration calculation
    text_dur = max(2.0, len(message.strip()) / 15.0)  # Faster pacing
    duration = text_dur
    
    entry = {
        "frame": os.path.abspath(frame_file),
        "duration": round(duration, 3),
        "is_sender": is_sender,
        "username": username,
        "text": message,
        "is_meme": False,
        "meme_path": None,
        "typing": False
    }
    
    render_bubble.timeline.append(entry)
    
    # Write timeline only occasionally
    if render_bubble.frame_count % 20 == 0:
        try:
            with open(TIMELINE_FILE, "w", encoding="utf-8") as tf:
                json.dump(render_bubble.timeline, tf, indent=2)
        except Exception:
            pass
    
    render_bubble.frame_count += 1
    return frame_file

def render_meme(username, meme_path):
    """Simple meme rendering"""
    return render_bubble(username, "", meme_path=meme_path)

def render_typing_bubble(username, duration=None, is_sender=None, custom_durations=None):
    """ULTRA-FAST typing bubble - SKIPPED"""
    return None  # Skip typing bubbles for speed

def render_typing_bar_frame(username, upcoming_text="", frame_path=None, duration=None, is_character_typing=True):
    """ULTRA-FAST typing bar - SIMPLIFIED"""
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
    
    # Simple typing bar render
    render_bubble.renderer.render_frame(
        frame_file=frame_path,
        show_typing_bar=True,
        typing_user=username,
        upcoming_text=upcoming_text[:30]  # Truncate long text
    )
    
    frame_duration = 0.5  # Fixed short duration
    
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
        "sound": False  # No sound for speed
    }
    
    render_bubble.timeline.append(entry)
    render_bubble.frame_count += 1
    return frame_path

def generate_beluga_typing_sequence(real_message):
    """ULTRA-FAST typing sequence - MINIMAL"""
    if not real_message:
        return []
    
    # Only generate essential frames
    sequence = []
    
    # Start typing
    sequence.append(("|", 0.3, True))
    
    # Type message in chunks (much fewer frames)
    chunk_size = max(3, len(real_message) // 4)
    for i in range(0, len(real_message), chunk_size):
        chunk = real_message[:i+chunk_size] + "|"
        sequence.append((chunk, 0.2, True))
    
    # Final message
    sequence.append((real_message, 0.5, False))
    
    return sequence

def render_typing_sequence(username, real_message):
    """ULTRA-FAST typing sequence rendering"""
    sequence = generate_beluga_typing_sequence(real_message)
    rendered_frames = []
    
    for text, duration, has_sound in sequence:
        frame_path = render_typing_bar_frame(
            username=username,
            upcoming_text=text,
            duration=duration,
            is_character_typing=has_sound
        )
        if frame_path:
            rendered_frames.append(frame_path)
  
    return rendered_frames

def reset_typing_sessions():
    """Reset typing sessions"""
    if hasattr(render_bubble, 'typing_session_active'):
        render_bubble.typing_session_active = False
        render_bubble.typing_session_start = 0
        render_bubble.current_typing_session = None
        render_bubble.prev_typing_text = ""
        render_bubble.fake_typing_count = 0

# ---------- MAIN SCRIPT ---------- #

if __name__ == "__main__":
    try:
        if len(sys.argv) < 2:
            sys.exit(1)
        script_file = sys.argv[1]
        render_bubble.frame_count = 0
        render_bubble.timeline = []
        render_bubble.renderer = WhatsAppRenderer()
        reset_typing_sessions()
      
    finally:
        cleanup_resources()
