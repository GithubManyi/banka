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
import psutil

# ---------- MEMORY OPTIMIZATION ---------- #
def get_memory_usage():
    """Get current memory usage in MB"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024

def check_memory_limit(limit_mb=2000):
    """Check if memory usage exceeds limit and trigger cleanup"""
    current_memory = get_memory_usage()
    if current_memory > limit_mb:
        print(f"⚠️ High memory usage: {current_memory:.1f}MB, forcing cleanup")
        gc.collect()
        return True
    return False

# ---------- CONTAINER STABILITY FIXES ---------- #
def signal_handler(sig, frame):
    print(f"🚨 Received signal {sig}, but continuing...")
    if sig in [signal.SIGTERM, signal.SIGINT]:
        print("🛑 Ignoring termination signal to maintain container stability")
        return

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

MAIN_USER = "Banka"
W, H = 1904, 934

# ---------- OPTIMIZED CACHE SYSTEM ---------- #
FRAME_CACHE = {}
CACHE_MAX_SIZE = 50  # Reduced from 100 to save memory
CACHE_HITS = 0
CACHE_MISSES = 0

class OptimizedCache:
    def __init__(self, max_size=50):
        self.max_size = max_size
        self.cache = {}
        self.hits = 0
        self.misses = 0
        
    def get(self, key):
        if key in self.cache:
            self.hits += 1
            return self.cache[key]
        self.misses += 1
        return None
        
    def set(self, key, value):
        if len(self.cache) >= self.max_size:
            # Remove oldest item
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
        self.cache[key] = value
        
    def stats(self):
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return f"Cache: {len(self.cache)}/{self.max_size} items, Hit rate: {hit_rate:.1f}%"

frame_cache = OptimizedCache(max_size=50)

# ---------- AVATAR MANAGEMENT SYSTEM ---------- #
def load_characters():
    """Load characters from JSON file"""
    if os.path.exists(CHARACTERS_FILE):
        try:
            with open(CHARACTERS_FILE, "r", encoding="utf-8") as f:
                characters = json.load(f)
            return characters
        except Exception as e:
            print(f"❌ Error loading characters: {e}")
            return {}
    return {}

def get_character_avatar_path(username):
    """Get the correct avatar path for a character"""
    characters = load_characters()
    username_clean = username.strip()
    
    # 1) Check character JSON first
    if username_clean in characters:
        avatar_path = characters[username_clean].get("avatar", "")
        if avatar_path:
            if not os.path.isabs(avatar_path):
                full_path = os.path.join(BASE_DIR, avatar_path)
            else:
                full_path = avatar_path
            if os.path.exists(full_path):
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
                return possible_path
    
    return ""

def encode_avatar_for_html(avatar_path):
    """Convert avatar image to base64 for HTML display"""
    if not avatar_path or not os.path.exists(avatar_path):
        return ""
    try:
        with open(avatar_path, "rb") as f:
            avatar_data = base64.b64encode(f.read()).decode("utf-8")
        mime_type = "image/jpeg"
        if avatar_path.lower().endswith('.png'):
            mime_type = "image/png"
        elif avatar_path.lower().endswith('.gif'):
            mime_type = "image/gif"
        return f"data:{mime_type};base64,{avatar_data}"
    except Exception as e:
        print(f"⚠️ Failed to encode avatar {avatar_path}: {e}")
        return ""

# ---------- OPTIMIZED HTML2IMAGE INSTANCE ---------- #
HTI = None
HTI_LAST_USED = 0
HTI_TIMEOUT = 300  # Restart after 5 minutes of inactivity

def get_html2image():
    """Get or create HTML2Image instance with optimized settings"""
    global HTI, HTI_LAST_USED
    
    current_time = time.time()
    
    # Restart if too much time has passed to prevent memory leaks
    if HTI is not None and (current_time - HTI_LAST_USED) > HTI_TIMEOUT:
        print("🔄 Restarting HTML2Image instance due to inactivity timeout")
        HTI = None
        gc.collect()
    
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
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                    '--no-default-browser-check',
                    '--no-first-run',
                    '--disable-default-apps',
                    '--disable-features=TranslateUI',
                    '--disable-ipc-flooding-protection',
                    '--memory-pressure-off',
                    '--max-old-space-size=4096'
                ]
                
                HTI = html2image.Html2Image(
                    browser='chromium',
                    browser_executable=chromium_path,
                    custom_flags=chrome_flags
                )
        except Exception as e:
            print(f"⚠️ HTML2Image setup failed: {e}")
            HTI = None
    
    HTI_LAST_USED = current_time
    return HTI

def cleanup_resources():
    """Thorough cleanup of all resources"""
    global HTI, frame_cache
    if HTI:
        HTI = None
    frame_cache.cache.clear()
    gc.collect()
    print("🧹 Cleaned up rendering resources")

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

# ---------- OPTIMIZED HELPERS ---------- #
def encode_meme(path):
    """Encode meme for HTML display"""
    if not path or not isinstance(path, str) or not os.path.exists(path):
        return None
    import mimetypes
    ext = os.path.splitext(path)[1].lower()
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = "application/octet-stream"
    with open(path, "rb") as f:
        data = f.read()
        encoded = base64.b64encode(data).decode("utf-8")
    return {
        "meme": encoded,
        "meme_type": ext,
        "mime": mime
    }

def name_to_color(username: str) -> str:
    """Readable deterministic color from username"""
    h = hashlib.md5(username.strip().lower().encode("utf-8")).hexdigest()
    n = int(h[:8], 16)
    hue = (n * 137) % 360
    saturation = 0.7
    lightness = 0.55
    r, g, b = colorsys.hls_to_rgb(hue/360, lightness, saturation)
    return f'#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}'

def calculate_typing_duration(text):
    """Calculate realistic typing duration"""
    chars = len(text.strip())
    base_duration = 1.5
    char_duration = 0.08
    typing_time = base_duration + (chars * char_duration)
    return min(typing_time, 4.0)

# ---------- OPTIMIZED RENDERER ---------- #
class WhatsAppRenderer:
    def __init__(self, chat_title="Default Group", chat_avatar=None, chat_status=None):
        self.message_history = []
        self.jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
        self.chat_title = chat_title
        self.chat_avatar = chat_avatar
        self.chat_status = chat_status
        self._last_render_time = 0
        self._render_count = 0
        self._emoji_fonts = self._install_emoji_fonts()
        
    def _install_emoji_fonts(self):
        """Try to install or use emoji-supporting fonts"""
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
            return available_fonts
        except Exception as e:
            print(f"⚠️ Error checking emoji fonts: {e}")
            return []

    def add_message(self, username, message, meme_path=None, is_read=False, typing=False):
        """Add message to history with optimized avatar system"""
        try:
            ts = datetime.now().strftime("%-I:%M %p").lower()
        except ValueError:
            ts = datetime.now().strftime("%#I:%M %p").lower()

        color = name_to_color(username)
        avatar_path = get_character_avatar_path(username)
        
        # Generate avatar data
        if avatar_path and os.path.exists(avatar_path):
            try:
                with open(avatar_path, "rb") as f:
                    avatar_data = base64.b64encode(f.read()).decode("utf-8")
                mime = "image/jpeg"
                if avatar_path.lower().endswith('.png'):
                    mime = "image/png"
                elif avatar_path.lower().endswith('.gif'):
                    mime = "image/gif"
            except Exception as e:
                avatar_data = None
                mime = None
        else:
            # Generate initial avatar
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
            
            img_size = 200
            img = Image.new('RGB', (img_size, img_size), color=(r, g, b))
            draw = ImageDraw.Draw(img)
            
            if len(initial) == 1:
                font_size = 100
            else:
                font_size = 80
                
            try:
                font_paths = [
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/System/Library/Fonts/Helvetica.ttc",
                    "Arial",
                    "arial.ttf"
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
            
            if font:
                try:
                    bbox = draw.textbbox((0, 0), initial, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    x = (img_size - text_width) / 2
                    y = (img_size - text_height) / 2 - bbox[1]
                    
                    outline_width = max(2, img_size // 80)
                    for x_offset in [-outline_width, 0, outline_width]:
                        for y_offset in [-outline_width, 0, outline_width]:
                            if x_offset != 0 or y_offset != 0:
                                draw.text((x + x_offset, y + y_offset), initial, fill=(0, 0, 0, 128), font=font)
                    
                    draw.text((x, y), initial, fill=(255, 255, 255), font=font)
                except Exception:
                    x = img_size // 6
                    y = img_size // 4
                    draw.text((x, y), initial, fill=(255, 255, 255), font=font)
            else:
                x = img_size // 6
                y = img_size // 4
                draw.text((x, y), initial, fill=(255, 255, 255))
            
            img = img.resize((128, 128), Image.Resampling.LANCZOS)
            buf = BytesIO()
            img.save(buf, format="PNG")
            avatar_data = base64.b64encode(buf.getvalue()).decode("utf-8")
            mime = "image/png"

        # Meme handling
        meme_data = None
        if meme_path and os.path.exists(meme_path):
            try:
                meme_data = encode_meme(meme_path)
            except Exception as e:
                print(f"⚠️ Meme encode failed: {e}")

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

    def render_frame(self, frame_file, show_typing_bar=False, typing_user=None, upcoming_text="", short_wait=False):
        """Optimized frame rendering with memory management"""
        start_time = time.time()
        self._render_count += 1
        
        # Memory check
        if self._render_count % 20 == 0:
            check_memory_limit()
        
        # Check cache first
        is_typing_frame = show_typing_bar and upcoming_text
        cache_key = get_frame_cache_key(self.message_history, show_typing_bar, typing_user, upcoming_text)
        
        if not is_typing_frame:
            cached_frame = frame_cache.get(cache_key)
            if cached_frame and os.path.exists(cached_frame):
                import shutil
                shutil.copy2(cached_frame, frame_file)
                if self._render_count % 50 == 0:
                    print(f"⚡ Using cached frame: {cache_key[:8]}...")
                return f"CACHED: {cached_frame}"
        
        # Render template
        template = self.jinja_env.get_template(TEMPLATE_FILE)
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
        
        # Try HTML2Image first
        try:
            hti = get_html2image()
            if hti is None:
                raise Exception("HTML2Image not available")
            
            temp_html = os.path.join(FRAMES_DIR, f"temp_{self._render_count}.html")
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
                if self._render_count % 50 == 0:
                    print(f"✅ Rendered frame {self._render_count}: {frame_file}")
            else:
                raise Exception("HTML2Image didn't generate output file")
            
            if os.path.exists(temp_html):
                os.remove(temp_html)
                
        except Exception as e:
            # PIL fallback
            if self._render_count % 10 == 0:
                print(f"❌ HTML2Image failed: {e}")
                print("🔄 Falling back to PIL rendering...")
            
            from PIL import Image, ImageDraw, ImageFont
            
            img = Image.new('RGB', (1920, 1080), color=(11, 20, 26))
            draw = ImageDraw.Draw(img)
            
            try:
                font_large = None
                font_medium = None
                font_small = None
                
                if self._emoji_fonts:
                    for font_path in self._emoji_fonts:
                        try:
                            font_large = ImageFont.truetype(font_path, 36)
                            font_medium = ImageFont.truetype(font_path, 30)
                            font_small = ImageFont.truetype(font_path, 20)
                            break
                        except:
                            continue
                
                if font_large is None:
                    try:
                        font_large = ImageFont.truetype("Arial", 36)
                        font_medium = ImageFont.truetype("Arial", 30)
                        font_small = ImageFont.truetype("Arial", 20)
                    except:
                        font_large = ImageFont.load_default()
                        font_medium = ImageFont.load_default()
                        font_small = ImageFont.load_default()
                
                # Simplified rendering for speed
                topbar_height = 130
                draw.rectangle([0, 0, 1920, topbar_height], fill=(17, 27, 33))
                
                avatar_x, avatar_y = 24, 15
                avatar_size = 100
                draw.ellipse([avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size], 
                            fill=(42, 57, 66))
                
                draw.text((avatar_x + avatar_size + 24, 50), 
                          f"💬 {self.chat_title}", 
                          fill=(255, 255, 255), font=font_large)
                draw.text((avatar_x + avatar_size + 24, 90), 
                          f"👥 {self.chat_status}", 
                          fill=(134, 150, 160), font=font_small)
                
                chat_bg_top = topbar_height
                draw.rectangle([0, chat_bg_top, 1920, 1080], fill=(11, 20, 26))
                
                # Simple message display
                y_pos = chat_bg_top + 50
                for msg in filtered_messages[-10:]:  # Only show last 10 messages for speed
                    color = (0, 92, 75) if msg['is_sender'] else (32, 44, 51)
                    draw.rectangle([100, y_pos, 1820, y_pos + 60], fill=color, outline=(255, 255, 255))
                    draw.text((120, y_pos + 10), f"{msg['username']}: {msg['text'][:50]}", 
                             fill=(255, 255, 255), font=font_medium)
                    y_pos += 70
                    if y_pos > 1000:
                        break
                        
                if show_typing_bar and typing_user:
                    typing_bar_y = 1080 - 80
                    draw.rectangle([0, typing_bar_y, 1920, 1080], fill=(17, 27, 33))
                    bar_width = 1800
                    bar_x = (1920 - bar_width) // 2
                    draw.rounded_rectangle([bar_x, typing_bar_y + 10, bar_x + bar_width, typing_bar_y + 70],
                                          radius=48, fill=(32, 44, 51))
                    
                    typing_text = f"⌨️ {typing_user} is typing..."
                    if upcoming_text:
                        preview_text = upcoming_text.replace("|", "")[:30]
                        if len(upcoming_text) > 30:
                            preview_text += "..."
                        typing_text = f"⌨️ {typing_user}: {preview_text}"
                    
                    draw.text((bar_x + 60, typing_bar_y + 25), 
                             typing_text, 
                             fill=(100, 255, 100), font=font_medium)
                    
            except Exception as pil_error:
                draw.text((100, 100), f"Chat Frame - {len(filtered_messages)} messages", fill=(255, 255, 255))
                if show_typing_bar and typing_user:
                    draw.text((100, 150), f"{typing_user} typing: {upcoming_text}", fill=(100, 255, 100))
            
            img.save(frame_file, optimize=True, quality=85)  # Optimized save
        
        # Cache non-typing frames
        if not is_typing_frame:
            frame_cache.set(cache_key, frame_file)
        
        render_time = time.time() - start_time
        if render_time > 1.0:
            print(f"⏱️ Frame {self._render_count} rendered in {render_time:.2f}s")
        
        # Print cache stats periodically
        if self._render_count % 100 == 0:
            print(frame_cache.stats())
            print(f"💾 Memory usage: {get_memory_usage():.1f}MB")
        
        return rendered_html

# ---------- OPTIMIZED BUBBLE RENDERING ---------- #
def render_bubble(username, message="", meme_path=None, is_sender=None, is_read=False, typing=False):
    """
    Optimized bubble rendering with memory management
    """
    if not hasattr(render_bubble, 'renderer'):
        render_bubble.renderer = WhatsAppRenderer(
            chat_title="BANKA TOUR GROUP",
            chat_avatar="static/images/group.png",
            chat_status="jay, khooi, banka, Paula"
        )
        render_bubble.frame_count = 0
        render_bubble.timeline = []
    
    if is_sender is None:
        is_sender = (username.strip().lower() == MAIN_USER.lower())
    
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
    
    # Handle typing
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
            
            # Only save timeline every 10 frames to reduce I/O
            if render_bubble.frame_count % 10 == 0:
                with open(TIMELINE_FILE, "w", encoding="utf-8") as tf:
                    json.dump(render_bubble.timeline, tf, indent=2)
            
            render_bubble.frame_count += 1
            return frame_file
    
    # Normal message rendering
    render_bubble.renderer.add_message(username, message, meme_path=meme_path, is_read=is_read, typing=False)
    frame_file = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
    
    render_bubble.renderer.render_frame(frame_file, show_typing_bar=False, short_wait=False)
    
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
        except Exception as e:
            print(f"⚠️ render_bubble: failed to encode meme {meme_path}: {e}")
    
    render_bubble.timeline.append(entry)
    
    # Only save timeline every 10 frames to reduce I/O
    if render_bubble.frame_count % 10 == 0:
        with open(TIMELINE_FILE, "w", encoding="utf-8") as tf:
            json.dump(render_bubble.timeline, tf, indent=2)
    
    render_bubble.frame_count += 1
    
    if render_bubble.frame_count % 20 == 0:
        print(f"✅ Regular frame {render_bubble.frame_count}: {frame_file} ({duration}s)")
        print(f"💾 Memory: {get_memory_usage():.1f}MB")
    
    return frame_file

# Keep the rest of your functions but add memory management to them
def render_meme(username, meme_path):
    return render_bubble(username, "", meme_path=meme_path)

def render_typing_bubble(username, duration=None, is_sender=None, custom_durations=None):
    """Render typing bubble with memory management"""
    custom_durations = custom_durations or {}
    check_memory_limit()
    
    if not hasattr(render_bubble, 'renderer'):
        render_bubble.renderer = WhatsAppRenderer(
            chat_title="BANKA TOUR GROUP",
            chat_avatar="static/images/group.png",
            chat_status="jay, khooi, banka, Paula"
        )
        render_bubble.frame_count = 0
        render_bubble.timeline = []
    
    if is_sender is None:
        is_sender = (username.strip().lower() == MAIN_USER.lower())
    
    # Don't show typing bubbles for sender
    if is_sender:
        if render_bubble.frame_count % 20 == 0:
            print(f"⌨️ Skipping typing bubble for sender {username} - using typing bar instead")
        return render_typing_bar_frame(username, "", duration=1.5)
    
    # Use the main renderer, but temporarily add typing message
    original_history = render_bubble.renderer.message_history.copy()
    
    # Add typing indicator to main renderer temporarily
    render_bubble.renderer.add_message(username, None, typing=True)
    
    frame_file = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
    render_bubble.renderer.render_frame(frame_file, short_wait=True)
    
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
        "typing_sound": False
    }
    render_bubble.timeline.append(entry)
    
    with open(TIMELINE_FILE, "w", encoding="utf-8") as tf:
        json.dump(render_bubble.timeline, tf, indent=2)
    
    render_bubble.frame_count += 1
    if render_bubble.frame_count % 20 == 0:
        print(f"⌨️ Typing indicator for {username} (duration: {duration}s)")
    
    return frame_file

def render_typing_bar_frame(username, upcoming_text="", frame_path=None, duration=None, is_character_typing=True):
    """Render typing bar frames with memory management"""
    check_memory_limit()
    
    if not hasattr(render_bubble, 'renderer'):
        render_bubble.renderer = WhatsAppRenderer(
            chat_title="BANKA TOUR GROUP",
            chat_avatar="static/images/group.png",
            chat_status="jay, khooi, banka, Paula"
        )
        render_bubble.frame_count = 0
        render_bubble.timeline = []
    
    if not frame_path:
        frame_path = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
    
    # Skip typing bar for non-sender
    if username.strip().lower() != MAIN_USER.lower():
        if render_bubble.frame_count % 20 == 0:
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
    
    # Simple duration handling
    if duration is None or duration <= 0:
        if not is_character_typing or upcoming_text.endswith('|'):
            frame_duration = 0.8  # Longer for cursor blinks
        else:
            frame_duration = 0.4  # Shorter for actual typing
    else:
        frame_duration = duration
    
    # Simple sound logic
    should_play_sound = is_character_typing
    
    # Check if this is one of the last 3 frames (no cursor, complete text)
    current_text = upcoming_text.replace("|", "").strip()
    is_final_frame = (not upcoming_text.endswith('|') and current_text)
    if is_final_frame:
        should_play_sound = False  # No sound in final frames
    
    # Generate session ID for continuous sound grouping
    if not hasattr(render_bubble, 'current_typing_session'):
        render_bubble.current_typing_session = None
    
    # Start new session when we begin typing after not typing
    if is_character_typing and not hasattr(render_bubble, 'prev_typing_text'):
        render_bubble.prev_typing_text = ""
    
    current_text = upcoming_text.replace("|", "").strip()
    if is_character_typing and not render_bubble.prev_typing_text and current_text:
        render_bubble.current_typing_session = f"session_{render_bubble.frame_count}"
    
    # End session when we stop typing
    if not is_character_typing and render_bubble.current_typing_session:
        render_bubble.current_typing_session = None
    
    render_bubble.prev_typing_text = current_text
    
    # Simple timeline entry
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
    
    if render_bubble.frame_count % 20 == 0:
        print(f"🎹 Frame {render_bubble.frame_count}: '{upcoming_text}' - Sound: {should_play_sound}")
    
    render_bubble.timeline.append(entry)
    with open(TIMELINE_FILE, "w", encoding="utf-8") as tf:
        json.dump(render_bubble.timeline, tf, indent=2)
    
    render_bubble.frame_count += 1
    return frame_path

def generate_beluga_typing_sequence(real_message):
    """Generate typing sequence with fake typing and realistic timing"""
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
        """Adds cursor blinks - NO SOUND during blinks"""
        for _ in range(blinks):
            sequence.append((text + "|", 0.25, False))  # False = no typing activity (NO SOUND)
            sequence.append((text, 0.25, False))  # False = no typing activity (NO SOUND)
    
    # Controlled fake typing (1-2 times per video, not per message)
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
        if random.random() < 0.05:
            print("🎲 No fake typing this message")
    
    # Type actual message WITH SOUND (continuous)
    buf = ""
    for i, ch in enumerate(real_message):
        buf += ch
        is_active_typing = True
        
        # Last 3 characters should have no sound
        if i >= len(real_message) - 3:
            is_active_typing = False
            if random.random() < 0.05:
                print(f"🎹 LAST 3 CHARS: '{ch}' at position {i} - NO SOUND")
        
        sequence.append((buf + "|", typing_speed_for(ch), is_active_typing))
    
    # Final cursor blinks and stable frame - NO SOUND
    blink_frame(real_message, blinks=2)
    sequence.append((real_message, 0.8, False))
    
    print(f"⌨️ Generated {len(sequence)} typing frames for '{real_message[:50]}...'")
    
    return sequence

def render_typing_sequence(username, real_message):
    """Render the typing sequence frames with sound"""
    print(f"🎬 Starting typing sequence for '{username}': '{real_message[:50]}...'")
    
    sequence = generate_beluga_typing_sequence(real_message)
    
    rendered_frames = []
    for i, (text, duration, has_sound) in enumerate(sequence):
        if i % 20 == 0:
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

def reset_typing_sessions():
    """Reset typing session tracking"""
    if hasattr(render_bubble, 'typing_session_active'):
        render_bubble.typing_session_active = False
        render_bubble.typing_session_start = 0
        render_bubble.current_typing_session = None
        render_bubble.prev_typing_text = ""
        render_bubble.fake_typing_count = 0
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
        reset_typing_sessions()
        print("🔄 Initialized with memory optimization")
        
        # Your main script execution logic here...
        print(f"✅ Rendered {render_bubble.frame_count} frames from {script_file}")
      
    finally:
        cleanup_resources()

