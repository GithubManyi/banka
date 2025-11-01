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
from backend.avatar_handler import get_avatar
from backend.meme_utils import download_meme, find_meme
from backend.meme_fetcher import fetch_meme_from_giphy
from base64 import b64encode
import mimetypes
import requests
import random
import traceback
import gc
import logging

# FORCE PROPER RENDERING - Use HTML templates with Chrome-like styling
FORCE_PIL_MODE = True

# Reduce logging verbosity
logging.getLogger('PIL').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

def debug_caller():
    """Print who's calling the rendering functions"""
    stack = traceback.extract_stack()
    for i, frame in enumerate(stack[:-1]):
        if 'render_typing_bar_frame' in frame.name:
            caller_frame = stack[i-1] if i > 0 else frame
            print(f"🔍 CALLER: {caller_frame.filename}:{caller_frame.lineno} in {caller_frame.name}")
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

# ---------- CACHING SYSTEM ---------- #
FRAME_CACHE = {}
CACHE_MAX_SIZE = 200
AVATAR_CACHE = {}
AVATAR_CACHE_MAX_SIZE = 100

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

def get_cached_avatar(username):
    """Get cached base64 avatar or create and cache it"""
    if username in AVATAR_CACHE:
        return AVATAR_CACHE[username]
    
    avatar_path = get_avatar(username)
    avatar_data = None
    
    if avatar_path and os.path.exists(avatar_path):
        try:
            with open(avatar_path, "rb") as f:
                avatar_data = base64.b64encode(f.read()).decode("utf-8")
            mime_type = "image/jpeg"
            if avatar_path.lower().endswith('.png'):
                mime_type = "image/png"
            elif avatar_path.lower().endswith('.gif'):
                mime_type = "image/gif"
            avatar_data = f"data:{mime_type};base64,{avatar_data}"
        except Exception as e:
            print(f"⚠️ Failed to encode avatar {avatar_path}: {e}")
            avatar_data = None
    
    # Cache the result
    if len(AVATAR_CACHE) >= AVATAR_CACHE_MAX_SIZE:
        AVATAR_CACHE.pop(next(iter(AVATAR_CACHE)))
    
    AVATAR_CACHE[username] = avatar_data
    return avatar_data

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
    """Calculate realistic typing duration based on text length"""
    chars = len(text.strip())
    base_duration = 1.5
    char_duration = 0.08
    typing_time = base_duration + (chars * char_duration)
    return min(typing_time, 4.0)

def debug_timeline_entries():
    """Debug function to check what's in the timeline"""
    if hasattr(render_bubble, 'timeline') and render_bubble.timeline:
        print("🔍 ===== TIMELINE DEBUG =====")
        typing_entries = [e for e in render_bubble.timeline if e.get('typing_bar')]
        print(f"🔍 Found {len(typing_entries)} typing bar entries in timeline")
        
        for i, entry in enumerate(typing_entries[-10:]):
            print(f"🔍 Entry {i}: text='{entry.get('upcoming_text')}' sound={entry.get('sound')} duration={entry.get('duration')}")

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
        self._fonts_loaded = False
        self._font_large = None
        self._font_medium = None
        self._font_small = None
        self._font_xsmall = None
        
    def _load_fonts(self):
        """Load fonts once and cache them"""
        if self._fonts_loaded:
            return
            
        try:
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "Arial",
                "/System/Library/Fonts/Arial.ttf"
            ]
            
            for path in font_paths:
                try:
                    self._font_large = ImageFont.truetype(path, 24)
                    self._font_medium = ImageFont.truetype(path, 18)
                    self._font_small = ImageFont.truetype(path, 14)
                    self._font_xsmall = ImageFont.truetype(path, 12)
                    self._fonts_loaded = True
                    print(f"✅ Loaded fonts from: {path}")
                    break
                except:
                    continue
                    
            if not self._fonts_loaded:
                self._font_large = ImageFont.load_default()
                self._font_medium = ImageFont.load_default()
                self._font_small = ImageFont.load_default()
                self._font_xsmall = ImageFont.load_default()
                self._fonts_loaded = True
                print("⚠️ Using default fonts")
                
        except Exception as e:
            print(f"⚠️ Font loading failed: {e}")
            self._font_large = ImageFont.load_default()
            self._font_medium = ImageFont.load_default()
            self._font_small = ImageFont.load_default()
            self._font_xsmall = ImageFont.load_default()
            self._fonts_loaded = True
    
    def add_message(self, username, message, meme_path=None, is_read=False, typing=False):
        try:
            ts = datetime.now().strftime("%-I:%M %p").lower()
        except ValueError:
            ts = datetime.now().strftime("%#I:%M %p").lower()

        color = name_to_color(username)
        avatar_data = get_cached_avatar(username)

        meme_data = None
        if meme_path and os.path.exists(meme_path):
            try:
                meme_data = encode_meme(meme_path)
                if self._render_count % 10 == 0:
                    size_kb = os.path.getsize(meme_path) // 1024
                    print(f"✅ add_message: meme encoded {meme_path} size={size_kb}KB")
            except Exception as e:
                print(f"⚠️ add_message: failed to encode meme {meme_path}: {e}")

        message_entry = {
            "username": username,
            "text": message if not typing else "",
            "typing": typing,
            "is_sender": (username.strip().lower() == MAIN_USER.lower()),
            "is_read": is_read,
            "timestamp": ts,
            "color": color,
            "avatar": avatar_data
        }
    
        if meme_data:
            message_entry["meme"] = meme_data["meme"]
            message_entry["meme_type"] = meme_data["meme_type"]
            message_entry["mime"] = meme_data["mime"]
    
        self.message_history.append(message_entry)
        if self._render_count % 5 == 0:
            print(f"✅ Added message: {username} - Text: '{message}' - Has meme: {bool(meme_data)}")

    def _wrap_text(self, text, font, max_width):
        """Wrap text to fit within max_width"""
        words = text.split(' ')
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = self._font_medium.getbbox(test_line)
            test_width = bbox[2] - bbox[0] if bbox else len(test_line) * 10
            
            if test_width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines

    def _draw_message_bubble(self, draw, x, y, username, text, timestamp, color, is_sender, is_read=False):
        """Draw a proper WhatsApp-style message bubble"""
        # WhatsApp-like bubble colors
        bubble_color = (32, 44, 51) if not is_sender else (5, 97, 98)
        text_color = (233, 237, 239)
        meta_color = (134, 150, 160)
        read_color = (83, 189, 235)
        
        # Wrap text to fit bubble
        max_text_width = 400  # Match original WhatsApp width
        wrapped_lines = self._wrap_text(text, self._font_medium, max_text_width)
        
        # Calculate bubble dimensions
        line_height = 25
        padding = 20
        username_height = 20
        timestamp_height = 20
        
        text_height = len(wrapped_lines) * line_height
        bubble_height = username_height + text_height + timestamp_height + (padding * 2)
        bubble_width = max_text_width + (padding * 2)
        
        # Position bubble based on sender
        if is_sender:
            bubble_x = 1920 - bubble_width - 100  # Right side with margin
        else:
            bubble_x = 100  # Left side with margin
        
        # Draw bubble background (rounded rectangle effect)
        draw.rectangle([bubble_x, y, bubble_x + bubble_width, y + bubble_height], 
                      fill=bubble_color, outline=None)
        
        # Draw username (above bubble for receiver, not shown for sender in WhatsApp)
        if not is_sender:
            draw.text((bubble_x, y - 20), username, fill=color, font=self._font_small)
        
        # Draw message text
        text_y = y + padding + username_height
        for line in wrapped_lines:
            draw.text((bubble_x + padding, text_y), line, fill=text_color, font=self._font_medium)
            text_y += line_height
        
        # Draw timestamp and read receipts
        timestamp_x = bubble_x + padding
        timestamp_y = y + bubble_height - padding - timestamp_height
        
        # For sender, show timestamp and read receipts on right
        if is_sender:
            timestamp_text = f"{timestamp} "
            timestamp_bbox = draw.textbbox((0, 0), timestamp_text, font=self._font_xsmall)
            timestamp_width = timestamp_bbox[2] - timestamp_bbox[0]
            
            # Draw timestamp
            draw.text((bubble_x + bubble_width - timestamp_width - 30, timestamp_y), 
                     timestamp_text, fill=meta_color, font=self._font_xsmall)
            
            # Draw read receipts (✓✓ for read, ✓ for sent)
            if is_read:
                draw.text((bubble_x + bubble_width - 20, timestamp_y), "✓✓", fill=read_color, font=self._font_xsmall)
            else:
                draw.text((bubble_x + bubble_width - 10, timestamp_y), "✓", fill=meta_color, font=self._font_xsmall)
        else:
            # For receiver, just show timestamp on left
            draw.text((timestamp_x, timestamp_y), timestamp, fill=meta_color, font=self._font_xsmall)
        
        return bubble_height

    def _draw_typing_indicator(self, draw, x, y, username, color):
        """Draw typing indicator (three dots) for receiver"""
        bubble_color = (32, 44, 51)
        bubble_height = 50
        bubble_width = 80
        
        # Draw bubble
        draw.rectangle([x, y, x + bubble_width, y + bubble_height], fill=bubble_color, outline=None)
        
        # Draw username
        draw.text((x, y - 20), username, fill=color, font=self._font_small)
        
        # Draw typing dots with animation effect
        dot_y = y + 25
        current_time = time.time()
        dot_offset = int((current_time * 2) % 3)
        
        for i in range(3):
            dot_x = x + 20 + (i * 15)
            dot_size = 8
            # Animate the dots
            if i == dot_offset:
                draw.ellipse([dot_x, dot_y, dot_x + dot_size, dot_y + dot_size], fill=(134, 150, 160))
            else:
                draw.ellipse([dot_x, dot_y, dot_x + dot_size, dot_y + dot_size], fill=(80, 100, 120))
        
        return bubble_height

    def _draw_meme_indicator(self, draw, x, y, username, timestamp, color, is_sender):
        """Draw meme/media indicator"""
        bubble_color = (32, 44, 51) if not is_sender else (5, 97, 98)
        bubble_height = 80
        bubble_width = 200
        
        # Position bubble
        if is_sender:
            bubble_x = 1920 - bubble_width - 100
        else:
            bubble_x = 100
        
        # Draw bubble
        draw.rectangle([bubble_x, y, bubble_x + bubble_width, y + bubble_height], fill=bubble_color, outline=None)
        
        # Draw username for receiver
        if not is_sender:
            draw.text((bubble_x, y - 20), username, fill=color, font=self._font_small)
        
        # Draw media icon and text
        icon_x = bubble_x + 15
        icon_y = y + 20
        
        draw.text((icon_x, icon_y), "📷", fill=(233, 237, 239), font=self._font_medium)
        draw.text((icon_x + 30, icon_y), "Media", fill=(233, 237, 239), font=self._font_medium)
        
        # Draw timestamp
        timestamp_y = y + bubble_height - 25
        if is_sender:
            timestamp_bbox = draw.textbbox((0, 0), timestamp, font=self._font_xsmall)
            timestamp_width = timestamp_bbox[2] - timestamp_bbox[0]
            draw.text((bubble_x + bubble_width - timestamp_width - 10, timestamp_y), 
                     timestamp, fill=(134, 150, 160), font=self._font_xsmall)
        else:
            draw.text((bubble_x + 15, timestamp_y), timestamp, fill=(134, 150, 160), font=self._font_xsmall)
        
        return bubble_height

    def render_frame(self, frame_file, show_typing_bar=False, typing_user=None, upcoming_text="", short_wait=False):
        """PROPER WhatsApp-style rendering matching the original HTML/CSS"""
        start_time = time.time()
        self._render_count += 1
        
        # Load fonts if needed
        self._load_fonts()
        
        # Check cache first
        cache_key = get_frame_cache_key(self.message_history, show_typing_bar, typing_user, upcoming_text)
        
        if cache_key in FRAME_CACHE and os.path.exists(FRAME_CACHE[cache_key]):
            cached_frame = FRAME_CACHE[cache_key]
            if os.path.exists(cached_frame):
                import shutil
                shutil.copy2(cached_frame, frame_file)
                if self._render_count % 20 == 0:
                    print(f"⚡ CACHED FRAME: {cache_key[:8]}...")
                return f"CACHED: {cached_frame}"
        
        try:
            # Create WhatsApp-style background (dark theme)
            img = Image.new('RGB', (1920, 1080), color=(17, 27, 33))
            draw = ImageDraw.Draw(img)
            
            # Draw header (EXACTLY like original - back button left, title center, menu right)
            header_height = 70
            header_bg = Image.new('RGB', (1920, header_height), color=(32, 44, 51))
            img.paste(header_bg, (0, 0))
            
            # Draw back button (←) on LEFT
            draw.text((25, 25), "←", fill=(233, 237, 239), font=self._font_large)
            
            # Draw chat title CENTERED
            title_text = self.chat_title
            title_bbox = draw.textbbox((0, 0), title_text, font=self._font_medium)
            title_width = title_bbox[2] - title_bbox[0]
            title_x = (1920 - title_width) // 2
            draw.text((title_x, 20), title_text, fill=(233, 237, 239), font=self._font_medium)
            
            # Draw chat status below title (centered)
            status_text = self.chat_status
            status_bbox = draw.textbbox((0, 0), status_text, font=self._font_small)
            status_width = status_bbox[2] - status_bbox[0]
            status_x = (1920 - status_width) // 2
            draw.text((status_x, 45), status_text, fill=(134, 150, 160), font=self._font_small)
            
            # Draw menu dots (⋮) on RIGHT
            draw.text((1870, 25), "⋮", fill=(233, 237, 239), font=self._font_large)
            
            # Draw messages - last 10 messages
            y_pos = header_height + 30
            messages_to_show = self.message_history[-10:]
            
            for msg in messages_to_show:
                is_sender = msg.get('is_sender', False)
                username = msg.get('username', 'Unknown')
                text = msg.get('text', '')
                timestamp = msg.get('timestamp', '')
                color = msg.get('color', '#FFFFFF')
                is_typing = msg.get('typing', False)
                has_meme = msg.get('meme') is not None
                is_read = msg.get('is_read', False)
                
                if is_typing and not is_sender:
                    # TYPING INDICATOR (receiver only)
                    height = self._draw_typing_indicator(draw, 100, y_pos, username, color)
                    y_pos += height + 20
                    
                elif has_meme:
                    # MEME MESSAGE
                    height = self._draw_meme_indicator(draw, 100, y_pos, username, timestamp, color, is_sender)
                    y_pos += height + 20
                    
                else:
                    # REGULAR TEXT MESSAGE
                    height = self._draw_message_bubble(draw, 100, y_pos, username, text, timestamp, color, is_sender, is_read)
                    y_pos += height + 20
                
                # Stop if we run out of space
                if y_pos > 900:
                    break
            
            # Draw typing bar if active (sender typing) - PROPER WhatsApp style
            if show_typing_bar and typing_user:
                # Typing bar at bottom
                typing_bar_height = 70
                typing_bg = Image.new('RGB', (1920, typing_bar_height), color=(32, 44, 51))
                img.paste(typing_bg, (0, 1080 - typing_bar_height))
                
                # Input field
                input_width = 1500
                input_height = 45
                input_x = 100
                input_y = 1080 - typing_bar_height + 12
                
                # Draw input background
                draw.rectangle([input_x, input_y, input_x + input_width, input_y + input_height], 
                              fill=(42, 57, 66), outline=None)
                
                # Draw typing text with cursor
                typing_display = upcoming_text + "|" if upcoming_text else ""
                text_color = (233, 237, 239) if upcoming_text else (134, 150, 160)
                placeholder = "Type a message" if not upcoming_text else ""
                
                draw.text((input_x + 15, input_y + 12), typing_display or placeholder, 
                         fill=text_color, font=self._font_medium)
                
                # Draw action buttons on RIGHT (like original)
                button_x = 1720
                button_y = 1080 - typing_bar_height + 15
                
                draw.text((button_x, button_y), "📎", fill=(134, 150, 160), font=self._font_medium)
                draw.text((button_x + 50, button_y), "📷", fill=(134, 150, 160), font=self._font_medium)
                draw.text((button_x + 100, button_y), "🎤", fill=(134, 150, 160), font=self._font_medium)
            
            # Save optimized for speed
            img.save(frame_file, 'PNG', optimize=True)
            
            render_time = time.time() - start_time
            if self._render_count % 10 == 0 or render_time > 0.1:
                print(f"⚡ FRAME {self._render_count}: {render_time:.3f}s")
                
        except Exception as e:
            print(f"⚠️ PIL rendering failed: {e}")
            # Fallback
            try:
                img = Image.new('RGB', (1920, 1080), color=(17, 27, 33))
                draw = ImageDraw.Draw(img)
                draw.text((100, 100), f"Chat: {self.chat_title}", fill=(255, 255, 255), font=self._font_medium)
                img.save(frame_file)
            except:
                Image.new('RGB', (1920, 1080), color=(17, 27, 33)).save(frame_file)
        
        # Cache frame for maximum speed
        if len(FRAME_CACHE) < CACHE_MAX_SIZE:
            FRAME_CACHE[cache_key] = frame_file
        
        return frame_file

# ---------- BUBBLE RENDERING ---------- #
def render_bubble(username, message="", meme_path=None, is_sender=None, is_read=False, typing=False):
    """Optimized bubble rendering with ORIGINAL WhatsApp styling"""
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

    # Handle typing differently based on sender vs receiver
    if typing:
        if is_sender:
            if render_bubble.frame_count % 20 == 0:
                print(f"⌨️ Sender {username} typing - using typing bar instead of bubble")
            return render_typing_bar_frame(username, upcoming_text=message if message else "", duration=1.5)
        else:
            if render_bubble.frame_count % 20 == 0:
                print(f"⌨️ Receiver {username} typing - showing typing bubble")
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
            with open(TIMELINE_FILE, "w", encoding="utf-8") as tf:
                json.dump(render_bubble.timeline, tf, indent=2)

            render_bubble.frame_count += 1
            return frame_file

    # Normal rendering for all users
    render_bubble.renderer.add_message(username, message, meme_path=meme_path, is_read=is_read, typing=False)
    frame_file = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
    
    is_typing_bar = (username.strip().lower() == MAIN_USER.lower() and not message)
    render_bubble.renderer.render_frame(frame_file, show_typing_bar=False, short_wait=is_typing_bar)

    # Compute durations
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
    with open(TIMELINE_FILE, "w", encoding="utf-8") as tf:
        json.dump(render_bubble.timeline, tf, indent=2)

    render_bubble.frame_count += 1
    return frame_file

# ... (rest of the functions remain the same as your working version) ...

def render_meme(username, meme_path):
    return render_bubble(username, "", meme_path=meme_path)

def render_typing_bubble(username, duration=None, is_sender=None, custom_durations=None):
    custom_durations = custom_durations or {}
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

    if is_sender:
        if render_bubble.frame_count % 20 == 0:
            print(f"⌨️ Skipping typing bubble for sender {username} - using typing bar instead")
        return render_typing_bar_frame(username, "", duration=1.5)

    original_history = render_bubble.renderer.message_history.copy()
    render_bubble.renderer.add_message(username, None, typing=True)
    frame_file = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
    render_bubble.renderer.render_frame(frame_file, short_wait=True)
    render_bubble.renderer.message_history = original_history

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

# ... (rest of the video helpers, typing functions, and main script remain exactly the same) ...

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

    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    frame_path = output_path if output_path.endswith('.png') else output_path + '.png'
    img.save(frame_path, "PNG")
    
    return frame_path, duration

def render_typing_bar_frame(username, upcoming_text="", frame_path=None, duration=None, is_character_typing=True):
    """Render typing bar frames with CONTINUOUS sound logic"""
    if render_bubble.frame_count % 50 == 0:
        debug_caller()
        print(f"🔍 CALLED WITH: '{upcoming_text}', duration={duration}, is_character_typing={is_character_typing}")
    
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
        if render_bubble.frame_count % 20 == 0:
            print(f"⌨️ Non-sender '{username}' - using typing bubble instead of typing bar")
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
    
    current_text = upcoming_text.replace("|", "").strip()
    prev_text = ""
    if render_bubble.timeline:
        for entry in reversed(render_bubble.timeline):
            if entry.get("typing_bar"):
                prev_text = entry.get("upcoming_text", "").replace("|", "").strip()
                break
    
    should_play_sound = is_character_typing
    is_final_frame = (not upcoming_text.endswith('|') and current_text)
    if is_final_frame:
        should_play_sound = False
        if render_bubble.frame_count % 20 == 0:
            print(f"🎹 FINAL FRAME DETECTED: '{upcoming_text}' - NO SOUND")

    if render_bubble.frame_count % 50 == 0:
        print(f"🎹 SIMPLE SOUND: is_typing={is_character_typing} -> sound={should_play_sound}")

    if not hasattr(render_bubble, 'current_typing_session'):
        render_bubble.current_typing_session = None
    
    if is_character_typing and not prev_text and current_text:
        render_bubble.current_typing_session = f"session_{render_bubble.frame_count}"
        if render_bubble.frame_count % 20 == 0:
            print(f"🎹 🆕 STARTING NEW TYPING SESSION: {render_bubble.current_typing_session}")
    
    if not is_character_typing and render_bubble.current_typing_session:
        if render_bubble.frame_count % 20 == 0:
            print(f"🎹 🛑 ENDING TYPING SESSION: {render_bubble.current_typing_session}")
        render_bubble.current_typing_session = None

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
    """Generate typing sequence with CONTINUOUS sound control"""
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

    if not hasattr(render_bubble, 'fake_typing_count'):
        render_bubble.fake_typing_count = 0
        render_bubble.max_fakes_per_video = random.randint(1, 2)

    if (render_bubble.fake_typing_count < render_bubble.max_fakes_per_video and 
        random.random() < 0.4):
        
        fake = random.choice(fake_phrases)
        render_bubble.fake_typing_count += 1
        print(f"🎲 FAKE TYPING {render_bubble.fake_typing_count}/{render_bubble.max_fakes_per_video}: '{fake}'")
        
        buf = ""
        for ch in fake:
            buf += ch
            sequence.append((buf + "|", typing_speed_for(ch), True))
        
        blink_frame(buf, blinks=1)
        
        for i in range(len(fake) - 1, -1, -1):
            buf = fake[:i]
            sequence.append((buf + "|", random.uniform(0.15, 0.25), False))
        
        sequence.append(("", 0.5, False))
    else:
        if random.random() < 0.05:
            print("🎲 No fake typing this message")

    buf = ""
    for i, ch in enumerate(real_message):
        buf += ch
        is_active_typing = True
        
        if i >= len(real_message) - 3:
            is_active_typing = False
            if random.random() < 0.05:
                print(f"🎹 LAST 3 CHARS: '{ch}' at position {i} - NO SOUND")
            
        sequence.append((buf + "|", typing_speed_for(ch), is_active_typing))

    blink_frame(real_message, blinks=2)
    sequence.append((real_message, 0.8, False))

    print(f"⌨️ Generated {len(sequence)} typing frames for '{real_message[:50]}...'")
    
    return sequence

def render_typing_sequence(username, real_message):
    """Render typing sequence frames with sound"""
    if random.random() < 0.05:
        debug_timeline_entries()
    
    print(f"🎬 Starting typing sequence for '{username}': '{real_message[:50]}...'")
    
    sequence = generate_beluga_typing_sequence(real_message)
    
    rendered_frames = []
    for i, (text, duration, has_sound) in enumerate(sequence):
        if i % 20 == 0:
            print(f"🎬 Rendering typing frame {i}: '{text}' - duration: {duration}s - sound: {has_sound}")
        
        frame_path = render_typing_bar_frame(
            username=username,
            upcoming_text=text,
            duration=duration,
            is_character_typing=has_sound
        )
        rendered_frames.append(frame_path)
    
    print(f"🎬 Completed typing sequence: {len(rendered_frames)} frames rendered")
    return rendered_frames

# ---------- CLEANUP ---------- #
def cleanup_resources():
    """Clean up all resources when done"""
    FRAME_CACHE.clear()
    AVATAR_CACHE.clear()
    gc.collect()
    print("🧹 Cleaned up rendering resources")

def reset_typing_sessions():
    """Reset typing session tracking"""
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

                render_bubble.timeline[-1]["is_meme"] = True
                meme_info = encode_meme(meme_file)
                render_bubble.timeline[-1]["meme_type"] = meme_info["meme_type"]
                render_bubble.timeline[-1]["meme_b64"] = meme_info["meme"]
                render_bubble.timeline[-1]["mime"] = meme_info["mime"]

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

                if is_sender and message:
                    print(f"🎬 Banka is typing: '{message}' - rendering typing sequence...")
                    render_typing_sequence(name, message)
                    print(f"🎬 Rendering final message after typing...")
                
                if "[MEME]" in message:
                    text_part, meme_desc = message.split("[MEME]", 1)
                    text_message = text_part.strip()
                    meme_desc = meme_desc.strip()

                    print(f"🔎 Found meme in message: {name}: '{text_message}' + [MEME:{meme_desc}]")
                    
                    meme_file = find_meme(meme_desc, assets_dir=os.path.join("assets", "memes", "auto"))
                    
                    if not meme_file:
                        auto_dir = os.path.join("assets", "memes", "auto")
                        files = [f for f in os.listdir(auto_dir) if os.path.isfile(os.path.join(auto_dir, f))]
                        if files:
                            meme_file = os.path.join(auto_dir, random.choice(files))
                            print(f"⚠️ No exact match for '{meme_desc}', using random: {meme_file}")

                    if meme_file and os.path.exists(meme_file):
                        render_bubble(name, text_message, meme_path=meme_file, is_sender=is_sender, is_read=is_read)
                        print(f"✅ Combined message: {name}: '{text_message}' + meme")
                    else:
                        render_bubble(name, text_message, is_sender=is_sender, is_read=is_read)
                        print(f"💬 Text only: {name}: {text_message} (meme not found)")
                else:
                    if not is_sender:
                        for msg in render_bubble.renderer.message_history:
                            if msg["is_sender"]:
                                msg["is_read"] = True

                    if render_bubble.frame_count % 10 == 0:
                        print(f"💬 Chat line: {name}: {message[:80]}")
                    render_bubble(name, message, is_sender=is_sender, is_read=is_read)

        print(f"✅ Rendered {render_bubble.frame_count} frames from {script_file}")
        
    finally:
        cleanup_resources()
