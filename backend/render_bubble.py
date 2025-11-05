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

# ---------- CONTAINER STABILITY FIXES ---------- #
def signal_handler(sig, frame):
    # Don't exit on SIGTERM/SIGINT in container
    if sig in [signal.SIGTERM, signal.SIGINT]:
        return

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# Reduce logging verbosity
logging.getLogger('html2image').setLevel(logging.WARNING)
logging.getLogger('PIL').setLevel(logging.WARNING)
logging.getLogger('selenium').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('selenium.webdriver.remote.remote_connection').setLevel(logging.ERROR)

os.environ['DBUS_SESSION_BUS_ADDRESS'] = ''
os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = ''
os.environ['DISABLE_DEV_SHM'] = 'true'
os.environ['ENABLE_CRASH_REPORTER'] = 'false'

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

MAIN_USER = "Banka" # right-side sender
W, H = 1904, 934 # match video size

# ---------- PERFORMANCE OPTIMIZATIONS ---------- #
FRAME_CACHE = {}
CACHE_MAX_SIZE = 200  # Increased cache size
AVATAR_CACHE = {}
MESSAGE_HISTORY_LIMIT = 100  # Limit message history to prevent slowdown
HTI = None

# ---------- AVATAR MANAGEMENT SYSTEM ---------- #

def load_characters():
    """Load characters from JSON file - OPTIMIZED"""
    if os.path.exists(CHARACTERS_FILE):
        try:
            with open(CHARACTERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def get_character_avatar_path(username):
    """Get the correct avatar path for a character - OPTIMIZED"""
    # Check cache first
    cache_key = f"avatar_path_{username.strip().lower()}"
    if cache_key in AVATAR_CACHE:
        return AVATAR_CACHE[cache_key]
    
    username_clean = username.strip()
    
    # 1) Check character JSON first
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

    # 2) Check avatars directory directly
    avatars_dir = os.path.join(BASE_DIR, "static", "avatars")
    if os.path.exists(avatars_dir):
        possible_filenames = [
            f"{username_clean}.png",
            f"{username_clean}.jpg",
            f"{username_clean}.jpeg",
            username_clean.replace(' ', '_') + ".png",
            username_clean.replace(' ', '_') + ".jpg",
            username_clean.replace(' ', '_') + ".jpeg"
        ]
      
        for filename in possible_filenames:
            possible_path = os.path.join(avatars_dir, filename)
            if os.path.exists(possible_path):
                AVATAR_CACHE[cache_key] = possible_path
                return possible_path

    # 3) No avatar found
    AVATAR_CACHE[cache_key] = ""
    return ""

def encode_avatar_for_html(avatar_path):
    """Convert avatar image to base64 for HTML display - OPTIMIZED"""
    if not avatar_path or not os.path.exists(avatar_path):
        return ""
    
    # Check cache
    cache_key = f"avatar_base64_{avatar_path}"
    if cache_key in AVATAR_CACHE:
        return AVATAR_CACHE[cache_key]
  
    try:
        with open(avatar_path, "rb") as f:
            avatar_data = base64.b64encode(f.read()).decode("utf-8")
      
        mime_type = "image/jpeg"
        if avatar_path.lower().endswith('.png'):
            mime_type = "image/png"
        elif avatar_path.lower().endswith('.gif'):
            mime_type = "image/gif"
      
        result = f"data:{mime_type};base64,{avatar_data}"
        AVATAR_CACHE[cache_key] = result
        return result
    except Exception:
        return ""

def get_html2image():
    """Get or create HTML2Image instance with optimized Chrome flags"""
    global HTI
    if HTI is None:
        try:
            possible_paths = [
                '/usr/bin/chromium',
                '/usr/bin/chromium-browser',
                '/usr/bin/google-chrome',
                '/usr/bin/chrome',
                '/app/.apt/usr/bin/chromium-browser'
            ]
          
            chromium_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    chromium_path = path
                    break
          
            if chromium_path:
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
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                    '--no-default-browser-check',
                    '--no-first-run',
                    '--disable-default-apps',
                    '--disable-features=TranslateUI',
                    '--disable-ipc-flooding-protection',
                    '--enable-features=NetworkService,NetworkServiceInProcess',
                    '--disable-vulkan',
                    '--disable-gl-drawing-for-tests',
                    '--disable-crash-reporter',
                    '--disable-in-process-stack-traces',
                    '--disable-logging',
                    '--disable-breakpad',
                    '--memory-pressure-off'
                ]
              
                HTI = html2image.Html2Image(
                    browser='chromium',
                    browser_executable=chromium_path,
                    custom_flags=chrome_flags
                )
            else:
                HTI = None
        except Exception:
            HTI = None
    return HTI

def cleanup_resources():
    """Clean up all resources when done"""
    global HTI
    if HTI:
        HTI = None
    FRAME_CACHE.clear()
    AVATAR_CACHE.clear()
    gc.collect()

def get_frame_cache_key(messages, show_typing_bar, typing_user, upcoming_text):
    """Generate a cache key for frame rendering - OPTIMIZED"""
    # Use only essential data for cache key
    key_data = {
        'messages': [(msg.get('username', ''), msg.get('text', ''), msg.get('typing', False))
                    for msg in messages[-10:]],  # Only last 10 messages for cache key
        'show_typing_bar': show_typing_bar,
        'typing_user': typing_user,
        'upcoming_text': upcoming_text
    }
    return hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

# ---------- HELPERS ---------- #

def encode_meme(path):
    """Encode meme for HTML display - OPTIMIZED"""
    if not path or not isinstance(path, str) or not os.path.exists(path):
        return None
    
    # Check cache
    cache_key = f"meme_{path}"
    if cache_key in AVATAR_CACHE:
        return AVATAR_CACHE[cache_key]
    
    import mimetypes
    ext = os.path.splitext(path)[1].lower()
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = "application/octet-stream"
    with open(path, "rb") as f:
        data = f.read()
        encoded = base64.b64encode(data).decode("utf-8")
    result = {
        "meme": encoded,
        "meme_type": ext,
        "mime": mime
    }
    AVATAR_CACHE[cache_key] = result
    return result

def name_to_color(username: str) -> str:
    """Readable deterministic color from username - OPTIMIZED"""
    # Cache colors to avoid recomputation
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

def calculate_typing_duration(text):
    """Calculate realistic typing duration based on text length - OPTIMIZED"""
    chars = len(text.strip())
    base_duration = 1.5
    char_duration = 0.08
    typing_time = base_duration + (chars * char_duration)
    return min(typing_time, 4.0)

# ---------- EMOJI FONT SUPPORT ---------- #

def install_emoji_fonts():
    """Try to install or use emoji-supporting fonts - OPTIMIZED"""
    try:
        emoji_fonts = [
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
            "/System/Library/Fonts/Apple Color Emoji.ttc",
            "C:/Windows/Fonts/segoeuiemoji.ttf",
        ]
        
        available_fonts = []
        for font_path in emoji_fonts:
            if os.path.exists(font_path):
                available_fonts.append(font_path)
                break  # Only need one working font
        
        return available_fonts
    except Exception:
        return []

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
        self._emoji_fonts = install_emoji_fonts()
        self._emoji_fonts_checked = True
        self._template_cache = None
  
    def add_message(self, username, message, meme_path=None, is_read=False, typing=False):
        """OPTIMIZED METHOD - Add message to history with performance improvements"""
        try:
            ts = datetime.now().strftime("%-I:%M %p").lower()
        except ValueError:
            ts = datetime.now().strftime("%#I:%M %p").lower()
  
        color = name_to_color(username)
        avatar_path = get_character_avatar_path(username)
      
        # Encode avatar or generate initial if not found
        if avatar_path and os.path.exists(avatar_path):
            try:
                avatar_data = encode_avatar_for_html(avatar_path)
                mime = "image/jpeg"
                if avatar_path.lower().endswith('.png'):
                    mime = "image/png"
                elif avatar_path.lower().endswith('.gif'):
                    mime = "image/gif"
            except Exception:
                avatar_data = None
                mime = None
        else:
            # Generate initial avatar - OPTIMIZED
            def get_initials(name):
                words = name.strip().split()
                if len(words) == 0:
                    return "?"
                elif len(words) == 1:
                    return name[:1].upper()
                else:
                    return (words[0][0] + words[-1][0]).upper()
            
            initial = get_initials(username)
            color_hex = color
            r, g, b = int(color_hex[1:3], 16), int(color_hex[3:5], 16), int(color_hex[5:7], 16)
            
            # Create optimized image
            img_size = 128  # Reduced for performance
            img = Image.new('RGB', (img_size, img_size), color=(r, g, b))
            draw = ImageDraw.Draw(img)
            
            font_size = 60 if len(initial) == 1 else 45
            
            try:
                font_paths = [
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
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
                    font = ImageFont.load_default()
                    
            except Exception:
                font = ImageFont.load_default()
            
            # Simple centered text
            if font:
                try:
                    bbox = draw.textbbox((0, 0), initial, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    x = (img_size - text_width) / 2
                    y = (img_size - text_height) / 2 - bbox[1]
                    draw.text((x, y), initial, fill=(255, 255, 255), font=font)
                except Exception:
                    x = img_size // 6
                    y = img_size // 4
                    draw.text((x, y), initial, fill=(255, 255, 255))
            else:
                x = img_size // 6
                y = img_size // 4
                draw.text((x, y), initial, fill=(255, 255, 255))
            
            buf = BytesIO()
            img.save(buf, format="PNG")
            avatar_data = base64.b64encode(buf.getvalue()).decode("utf-8")
            mime = "image/png"
  
        # Meme handling
        meme_data = None
        if meme_path and os.path.exists(meme_path):
            try:
                meme_data = encode_meme(meme_path)
            except Exception:
                pass
  
        # Build message entry
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
  
        if meme_data:
            message_entry["meme"] = meme_data["meme"]
            message_entry["meme_type"] = meme_data["meme_type"]
            message_entry["mime"] = meme_data["mime"]
  
        self.message_history.append(message_entry)
        
        # Limit message history to prevent slowdown
        if len(self.message_history) > MESSAGE_HISTORY_LIMIT:
            self.message_history = self.message_history[-MESSAGE_HISTORY_LIMIT:]

    def render_frame(self, frame_file, show_typing_bar=False, typing_user=None, upcoming_text="", short_wait=False):
        """
        HIGHLY OPTIMIZED frame rendering with performance improvements
        """
        start_time = time.time()
        self._render_count += 1
      
        # Check cache first - OPTIMIZED CACHE LOGIC
        is_typing_frame = show_typing_bar and upcoming_text
        cache_key = get_frame_cache_key(self.message_history, show_typing_bar, typing_user, upcoming_text)
      
        if not is_typing_frame and cache_key in FRAME_CACHE:
            cached_frame = FRAME_CACHE[cache_key]
            if os.path.exists(cached_frame):
                import shutil
                shutil.copy2(cached_frame, frame_file)
                return f"CACHED: {cached_frame}"
      
        # Use cached template if available
        if self._template_cache is None:
            template = self.jinja_env.get_template(TEMPLATE_FILE)
            self._template_cache = template
        else:
            template = self._template_cache
    
        # Filter typing bubbles for sender - OPTIMIZED
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
    
        # Try HTML2Image first, fallback to PIL if it fails
        try:
            hti = get_html2image()
            if hti is None:
                raise Exception("HTML2Image not available")
          
            # Direct rendering without temp file when possible
            temp_html = os.path.join(FRAMES_DIR, f"temp_{render_bubble.frame_count}.html")
            with open(temp_html, "w", encoding="utf-8") as f:
                f.write(rendered_html)
          
            hti.screenshot(
                html_file=temp_html,
                save_as=os.path.basename(frame_file),
                size=(1920, 1080)
            )
          
            # Move the screenshot to the correct location
            generated_file = os.path.join(os.getcwd(), os.path.basename(frame_file))
            if os.path.exists(generated_file):
                os.rename(generated_file, frame_file)
            else:
                raise Exception("HTML2Image didn't generate output file")
          
            # Clean up temp HTML file
            if os.path.exists(temp_html):
                os.remove(temp_html)
              
        except Exception:
            # FAST PIL FALLBACK - Minimal rendering
            from PIL import Image, ImageDraw, ImageFont
            
            # Simple background
            img = Image.new('RGB', (1920, 1080), color=(11, 20, 26))
            draw = ImageDraw.Draw(img)
            
            try:
                # Try to use available fonts quickly
                font_large = None
                if self._emoji_fonts:
                    for font_path in self._emoji_fonts:
                        try:
                            font_large = ImageFont.truetype(font_path, 36)
                            break
                        except:
                            continue
                
                if font_large is None:
                    try:
                        font_large = ImageFont.truetype("Arial", 36)
                    except:
                        font_large = ImageFont.load_default()
            
                # Minimal rendering - just show message count and typing status
                topbar_height = 130
                draw.rectangle([0, 0, 1920, topbar_height], fill=(17, 27, 33))
                
                # Simple text display
                draw.text((100, 50), f"💬 {self.chat_title}", fill=(255, 255, 255), font=font_large)
                draw.text((100, 90), f"Messages: {len(filtered_messages)}", fill=(134, 150, 160), font=font_large)
                
                # Show typing status if active
                if show_typing_bar and typing_user:
                    draw.text((100, 150), f"⌨️ {typing_user} is typing...", fill=(100, 255, 100), font=font_large)
                    if upcoming_text:
                        preview = upcoming_text.replace("|", "")[:40] + "..." if len(upcoming_text) > 40 else upcoming_text.replace("|", "")
                        draw.text((100, 190), f"Preview: {preview}", fill=(200, 200, 200), font=font_large)
            
            except Exception:
                # Ultra simple fallback
                draw.text((100, 100), f"Chat - {len(filtered_messages)} messages", fill=(255, 255, 255))
                if show_typing_bar and typing_user:
                    draw.text((100, 150), f"{typing_user} typing...", fill=(100, 255, 100))
            
            img.save(frame_file, optimize=True, quality=85)  # Optimized save
      
        # Cache non-typing frames only
        if not is_typing_frame and len(FRAME_CACHE) < CACHE_MAX_SIZE:
            FRAME_CACHE[cache_key] = frame_file
      
        render_time = time.time() - start_time
        if render_time > 2.0:  # Only log very slow renders
            print(f"⏱️ Slow frame {self._render_count}: {render_time:.2f}s")
      
        return rendered_html

# ---------- BUBBLE RENDERING ---------- #

def render_bubble(username, message="", meme_path=None, is_sender=None, is_read=False, typing=False):
    """
    OPTIMIZED bubble rendering with performance improvements.
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
    
    # OPTIMIZED duration calculation
    def _text_duration(text: str, typing_flag: bool) -> float:
        if typing_flag:
            return 1.5
        chars = len(text.strip()) if text else 0
        return max(2.5, chars / 12.0)  # Slightly faster
    
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
    
    # Handle typing - OPTIMIZED
    if typing:
        if is_sender:
            return render_typing_bar_frame(username, upcoming_text=message if message else "", duration=1.5)
        else:
            original_history = render_bubble.renderer.message_history.copy()
            render_bubble.renderer.add_message(username, None, typing=True)
            frame_file = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
            render_bubble.renderer.render_frame(frame_file, short_wait=True)
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
            # Only write timeline every 10 frames to reduce I/O
            if render_bubble.frame_count % 10 == 0:
                with open(TIMELINE_FILE, "w", encoding="utf-8") as tf:
                    json.dump(render_bubble.timeline, tf, indent=2)
            render_bubble.frame_count += 1
            return frame_file
    
    # Normal rendering
    render_bubble.renderer.add_message(username, message, meme_path=meme_path, is_read=is_read, typing=False)
    frame_file = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
  
    render_bubble.renderer.render_frame(frame_file, show_typing_bar=False, short_wait=False)
    
    # compute durations:
    text_dur = _text_duration(message, False)
    meme_dur = _meme_duration(meme_path) if meme_path else 0.0
    
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
    
    if meme_path and os.path.exists(meme_path):
        try:
            meme_info = encode_meme(meme_path)
            if meme_info:
                entry["meme_type"] = meme_info.get("meme_type")
                entry["meme_b64"] = meme_info.get("meme")
                entry["mime"] = meme_info.get("mime")
        except Exception:
            pass
    
    render_bubble.timeline.append(entry)
    
    # Optimized timeline writing - only write every 10 frames
    if render_bubble.frame_count % 10 == 0:
        with open(TIMELINE_FILE, "w", encoding="utf-8") as tf:
            json.dump(render_bubble.timeline, tf, indent=2)
    
    render_bubble.frame_count += 1
    return frame_file

def render_meme(username, meme_path):
    return render_bubble(username, "", meme_path=meme_path)

def render_typing_bubble(username, duration=None, is_sender=None, custom_durations=None):
    """OPTIMIZED typing bubble rendering"""
    custom_durations = custom_durations or {}
    
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
    
    if is_sender:
        return render_typing_bar_frame(username, "", duration=1.5)
    
    original_history = render_bubble.renderer.message_history.copy()
    render_bubble.renderer.add_message(username, None, typing=True)
    frame_file = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
    render_bubble.renderer.render_frame(frame_file, short_wait=True)
    render_bubble.renderer.message_history = original_history
    
    typing_key = f"typing:{username}"
    duration = custom_durations.get(typing_key, 1.5) if custom_durations else 1.5
    if duration <= 0:
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
        "typing_sound": False
    }
    render_bubble.timeline.append(entry)
  
    # Optimized timeline writing
    if render_bubble.frame_count % 10 == 0:
        with open(TIMELINE_FILE, "w", encoding="utf-8") as tf:
            json.dump(render_bubble.timeline, tf, indent=2)
    
    render_bubble.frame_count += 1
    return frame_file

def render_typing_bar_frame(username, upcoming_text="", frame_path=None, duration=None, is_character_typing=True):
    """
    OPTIMIZED: Render typing bar frames
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
    
    if username.strip().lower() != MAIN_USER.lower():
        return render_typing_bubble(username, custom_durations={})
    
    original_history = render_bubble.renderer.message_history.copy()
    render_bubble.renderer.render_frame(
        frame_file=frame_path,
        show_typing_bar=True,
        typing_user=username,
        upcoming_text=upcoming_text,
        short_wait=True
    )
    render_bubble.renderer.message_history = original_history
    
    if duration is None or duration <= 0:
        if not is_character_typing or upcoming_text.endswith('|'):
            frame_duration = 0.8
        else:
            frame_duration = 0.4
    else:
        frame_duration = duration
  
    should_play_sound = is_character_typing
    current_text = upcoming_text.replace("|", "").strip()
    is_final_frame = (not upcoming_text.endswith('|') and current_text)
    if is_final_frame:
        should_play_sound = False
    
    # Session tracking
    if not hasattr(render_bubble, 'current_typing_session'):
        render_bubble.current_typing_session = None

    current_text = upcoming_text.replace("|", "").strip()
    if is_character_typing and not hasattr(render_bubble, 'prev_typing_text'):
        render_bubble.prev_typing_text = ""

    if is_character_typing and not render_bubble.prev_typing_text and current_text:
        render_bubble.current_typing_session = f"session_{render_bubble.frame_count}"

    if not is_character_typing and render_bubble.current_typing_session:
        render_bubble.current_typing_session = None
        
    render_bubble.prev_typing_text = current_text
    
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
    
    render_bubble.timeline.append(entry)
    
    # Optimized timeline writing
    if render_bubble.frame_count % 10 == 0:
        with open(TIMELINE_FILE, "w", encoding="utf-8") as tf:
            json.dump(render_bubble.timeline, tf, indent=2)
            
    render_bubble.frame_count += 1
    return frame_path

def generate_beluga_typing_sequence(real_message):
    """
    OPTIMIZED: Generate typing sequences
    """
    if not real_message:
        return []
        
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
        for _ in range(blinks):
            sequence.append((text + "|", 0.25, False))
            sequence.append((text, 0.25, False))
    
    # Fake typing logic
    if not hasattr(render_bubble, 'fake_typing_count'):
        render_bubble.fake_typing_count = 0
        render_bubble.max_fakes_per_video = random.randint(1, 2)
        
    if (render_bubble.fake_typing_count < render_bubble.max_fakes_per_video and
        random.random() < 0.4):
      
        fake = random.choice(fake_phrases)
        render_bubble.fake_typing_count += 1
      
        buf = ""
        for ch in fake:
            buf += ch
            sequence.append((buf + "|", typing_speed_for(ch), True))
      
        blink_frame(buf, blinks=1)
      
        for i in range(len(fake) - 1, -1, -1):
            buf = fake[:i]
            sequence.append((buf + "|", random.uniform(0.15, 0.25), False))
      
        sequence.append(("", 0.5, False))
    
    # Type actual message
    buf = ""
    for i, ch in enumerate(real_message):
        buf += ch
        is_active_typing = True
      
        if i >= len(real_message) - 3:
            is_active_typing = False
          
        sequence.append((buf + "|", typing_speed_for(ch), is_active_typing))
    
    blink_frame(real_message, blinks=2)
    sequence.append((real_message, 0.8, False))
  
    return sequence

def render_typing_sequence(username, real_message):
    """
    OPTIMIZED: Render typing sequence frames
    """
    sequence = generate_beluga_typing_sequence(real_message)
    rendered_frames = []
    
    for i, (text, duration, has_sound) in enumerate(sequence):
        frame_path = render_typing_bar_frame(
            username=username,
            upcoming_text=text,
            duration=duration,
            is_character_typing=has_sound
        )
        rendered_frames.append(frame_path)
  
    return rendered_frames

def reset_typing_sessions():
    """Reset typing session tracking"""
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
            print("Usage: python render_bubble.py script.txt")
            sys.exit(1)
        script_file = sys.argv[1]
        render_bubble.frame_count = 0
        render_bubble.timeline = []
        render_bubble.renderer = WhatsAppRenderer()
        reset_typing_sessions()
        print(f"✅ Rendered {render_bubble.frame_count} frames from {script_file}")
      
    finally:
        cleanup_resources()
