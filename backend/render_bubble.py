#!/usr/bin/env python3
"""
render_bubble.py
Full replacement file with robust avatar-initials fallback and a safe video builder
that avoids 'local variable referenced before assignment' errors.
"""

import os
import json
import sys
import time
import subprocess
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from PIL import Image
import base64
import hashlib
import colorsys
import html2image
import random
import traceback
import gc
import logging

# ------------------ Logging ------------------
logging.getLogger('html2image').setLevel(logging.WARNING)
logging.getLogger('PIL').setLevel(logging.WARNING)
logging.getLogger('selenium').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('subprocess').setLevel(logging.WARNING)

# Suppress Chrome/Chromium specific warnings
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

MAIN_USER = "Banka"  # right-side sender
W, H = 1904, 934  # match video size (used for thumbnails)

# ---------- AVATAR MANAGEMENT SYSTEM ---------- #
def load_characters():
    """Load characters from JSON file - SELF CONTAINED"""
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
    """
    Return a filesystem path to an avatar image for username.
    If none present, return None (not a default image) to allow initials fallback.
    """
    characters = load_characters()
    username_clean = username.strip() if username else ""

    # 1) JSON mapping
    if username_clean in characters:
        avatar_path = characters[username_clean].get("avatar", "") or ""
        if avatar_path:
            if not os.path.isabs(avatar_path):
                full_path = os.path.join(BASE_DIR, avatar_path)
            else:
                full_path = avatar_path
            if os.path.exists(full_path):
                return full_path
            else:
                print(f"⚠️ Avatar path in JSON doesn't exist: {full_path}")

    # 2) avatars directory
    avatars_dir = os.path.join(BASE_DIR, "static", "avatars")
    if os.path.exists(avatars_dir) and username_clean:
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

    # If not found, return None -> caller will use initials
    return None

def encode_avatar_for_html(avatar_path):
    """Return data URI for avatar_path or empty string if missing"""
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

def get_user_initial(username):
    """Return up to 2-letter initial string for username."""
    if not username or not username.strip():
        return "?"
    parts = username.strip().split()
    if len(parts) == 1:
        return parts[0][0].upper()
    else:
        # use first letters of first two words
        return (parts[0][0] + parts[1][0]).upper()

# ---------- PERFORMANCE OPTIMIZATIONS ---------- #
HTI = None
FRAME_CACHE = {}
CACHE_MAX_SIZE = 100

def get_html2image():
    """Return Html2Image instance or None"""
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
                print("🚀 Created HTML2Image renderer with optimized Chrome flags")
            else:
                print("❌ No Chromium found, will use PIL fallback")
                HTI = None
        except Exception as e:
            print(f"⚠️ HTML2Image setup failed: {e}")
            HTI = None
    return HTI

def cleanup_resources():
    global HTI
    if HTI:
        HTI = None
    FRAME_CACHE.clear()
    gc.collect()
    print("🧹 Cleaned up rendering resources")

def get_frame_cache_key(messages, show_typing_bar, typing_user, upcoming_text):
    key_data = {
        'messages': [(msg.get('username', ''), msg.get('text', ''), msg.get('typing', False)) for msg in messages],
        'show_typing_bar': show_typing_bar,
        'typing_user': typing_user,
        'upcoming_text': upcoming_text
    }
    return hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

# ---------- HELPERS ---------- #
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
    """Deterministic color for initials background"""
    h = hashlib.md5(username.strip().lower().encode("utf-8")).hexdigest()
    n = int(h[:8], 16)
    hue = (n * 137) % 360
    saturation = 0.7
    lightness = 0.55
    r, g, b = colorsys.hls_to_rgb(hue/360, lightness, saturation)
    return f'#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}'

def calculate_typing_duration(text):
    chars = len(text.strip()) if text else 0
    base_duration = 1.5
    char_duration = 0.08
    typing_time = base_duration + (chars * char_duration)
    return min(typing_time, 4.0)

def debug_timeline_entries():
    if hasattr(render_bubble, 'timeline') and render_bubble.timeline:
        print("🔍 ===== TIMELINE DEBUG =====")
        typing_entries = [e for e in render_bubble.timeline if e.get('typing_bar')]
        print(f"🔍 Found {len(typing_entries)} typing bar entries in timeline")
        for i, entry in enumerate(typing_entries[-10:]):
            print(f"🔍 Entry {i}: text='{entry.get('upcoming_text')}' sound={entry.get('sound')} duration={entry.get('duration')}")

# ---------- VIDEO BUILDERS ---------- #
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

def build_video_from_timeline(timeline, out_path, fps=25, audio_path=None):
    """
    Build a video from timeline entries using ffmpeg (concat demuxer).
    This function is defensive and guarantees final_video variable will exist before return.
    Returns path to final video or None on failure.
    """
    final_video = None  # always define
    try:
        if not timeline:
            raise ValueError("Timeline is empty")

        concat_txt = os.path.join(FRAMES_DIR, "ff_concat.txt")
        # Build a concat file including durations; for safe use we'll copy frames into a temp folder if needed
        lines = []
        for entry in timeline:
            frame = entry.get("frame")
            duration = float(entry.get("duration", 1.0))
            if not os.path.exists(frame):
                print(f"⚠️ Frame missing: {frame} - skipping")
                continue
            add_still_to_concat(lines, frame, duration)
        if not lines:
            raise RuntimeError("No valid frames to concat")

        with open(concat_txt, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        # temp output
        tmp_out = os.path.join(FRAMES_DIR, "tmp_video.mp4")

        # ffmpeg concat demuxer command
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", concat_txt,
            "-vsync", "vfr", "-pix_fmt", "yuv420p",
            tmp_out
        ]
        if audio_path and os.path.exists(audio_path):
            # Add audio mixing - simple overlay
            final_video = os.path.join(os.path.dirname(out_path), os.path.basename(out_path))
            cmd_audio = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", tmp_out, "-i", audio_path,
                "-shortest", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                final_video
            ]
            # First create tmp_out
            subprocess.check_call(cmd)
            # Then mux audio
            subprocess.check_call(cmd_audio)
        else:
            # no audio
            final_video = out_path
            subprocess.check_call(cmd + [final_video])

        # On success, return path
        print(f"✅ Video built: {final_video}")
        return final_video

    except subprocess.CalledProcessError as cpe:
        print(f"❌ ffmpeg failed: {cpe}")
        traceback.print_exc()
        return final_video  # possibly None
    except Exception as e:
        print(f"❌ build_video_from_timeline error: {e}")
        traceback.print_exc()
        return final_video
    finally:
        # attempt to remove concat file
        try:
            if os.path.exists(concat_txt):
                os.remove(concat_txt)
        except Exception:
            pass

# ---------- RENDERER CLASS ---------- #
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
        """Add message to history with avatar fallback to initials"""
        try:
            ts = datetime.now().strftime("%-I:%M %p").lower()
        except Exception:
            ts = datetime.now().strftime("%#I:%M %p").lower()

        color = name_to_color(username or "")
        # avatar resolution - return path or None
        avatar_fs_path = get_character_avatar_path(username or "")
        avatar_data = ""
        mime = ""
        has_avatar = False
        if avatar_fs_path:
            try:
                with open(avatar_fs_path, "rb") as f:
                    avatar_data = base64.b64encode(f.read()).decode("utf-8")
                mime = "image/png" if avatar_fs_path.lower().endswith(".png") else "image/jpeg"
                has_avatar = bool(avatar_data)
            except Exception as e:
                print(f"⚠️ Failed to encode avatar {avatar_fs_path}: {e}")
                avatar_data = ""
                mime = ""
                has_avatar = False

        user_initial = get_user_initial(username or "")

        # meme
        meme_data = None
        if meme_path and os.path.exists(meme_path):
            try:
                meme_data = encode_meme(meme_path)
            except Exception as e:
                print(f"⚠️ Meme encode failed: {e}")

        message_entry = {
            "username": username,
            "text": message if not typing else "",
            "typing": typing,
            "is_sender": (username.strip().lower() == MAIN_USER.lower()) if username else False,
            "is_read": is_read,
            "timestamp": ts,
            "color": color,
            "avatar": avatar_data,
            "avatar_format": mime,
            "user_initial": user_initial,
            "has_avatar": has_avatar
        }
        if meme_data:
            message_entry["meme"] = meme_data["meme"]
            message_entry["meme_type"] = meme_data["meme_type"]
            message_entry["mime"] = meme_data["mime"]

        self.message_history.append(message_entry)

    def render_frame(self, frame_file, show_typing_bar=False, typing_user=None, upcoming_text="", short_wait=False):
        """
        Render HTML via html2image, fallback to PIL-created placeholder
        Returns the rendered HTML (string) for debugging, and writes frame image
        """
        start_time = time.time()
        self._render_count += 1

        is_typing_frame = show_typing_bar and upcoming_text
        cache_key = get_frame_cache_key(self.message_history, show_typing_bar, typing_user, upcoming_text)
        if not is_typing_frame and cache_key in FRAME_CACHE and os.path.exists(FRAME_CACHE[cache_key]):
            cached_frame = FRAME_CACHE[cache_key]
            if os.path.exists(cached_frame):
                import shutil
                shutil.copy2(cached_frame, frame_file)
                if self._render_count % 50 == 0:
                    print(f"⚡ Using cached frame: {cache_key[:8]}...")
                return f"CACHED: {cached_frame}"

        template = self.jinja_env.get_template(TEMPLATE_FILE)

        filtered_messages = []
        for msg in self.message_history:
            if msg.get('is_sender') and msg.get('typing'):
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

        # Try html2image
        try:
            hti = get_html2image()
            if hti is None:
                raise Exception("HTML2Image unavailable")
            temp_html = os.path.join(FRAMES_DIR, f"temp_{int(time.time()*1000)}.html")
            with open(temp_html, "w", encoding="utf-8") as f:
                f.write(rendered_html)
            try:
                hti.screenshot(html_file=temp_html, save_as=os.path.basename(frame_file), size=(1920, 1080))
            except Exception as render_error:
                print(f"⚠️ HTML2Image render failed: {render_error}")
                raise render_error
            generated_file = os.path.join(os.getcwd(), os.path.basename(frame_file))
            if os.path.exists(generated_file):
                os.rename(generated_file, frame_file)
            else:
                raise Exception("HTML2Image didn't generate output")
            if os.path.exists(temp_html):
                os.remove(temp_html)
        except Exception as e:
            # PIL fallback
            if self._render_count % 10 == 0:
                print(f"❌ HTML2Image failed: {e}\n🔄 Falling back to PIL rendering...")
            from PIL import ImageDraw, ImageFont
            img = Image.new('RGB', (1920, 1080), color=(53, 53, 53))
            draw = ImageDraw.Draw(img)
            try:
                try:
                    font_large = ImageFont.truetype("Arial", 24)
                    font_medium = ImageFont.truetype("Arial", 18)
                    font_small = ImageFont.truetype("Arial", 14)
                except Exception:
                    font_large = ImageFont.load_default()
                    font_medium = ImageFont.load_default()
                    font_small = ImageFont.load_default()

                y_pos = 50
                draw.text((100, y_pos), f"💬 {self.chat_title}", fill=(255,255,255), font=font_large)
                y_pos += 40
                draw.text((100, y_pos), f"👥 {self.chat_status}", fill=(200,200,200), font=font_medium)
                y_pos += 60
                if show_typing_bar and typing_user:
                    draw.text((100, y_pos), f"⌨️ {typing_user} is typing: {upcoming_text}", fill=(100,255,100), font=font_medium)
                    y_pos += 40

                for msg in filtered_messages[-8:]:
                    bubble_x = 100 if not msg.get('is_sender') else 1000
                    user_text = f"{msg.get('username')} • {msg.get('timestamp')}"
                    draw.text((bubble_x, y_pos), user_text, fill=msg.get('color'), font=font_small)
                    y_pos += 25
                    text = msg.get('text') or ""
                    message_lines = []
                    current_line = ""
                    for word in text.split():
                        test_line = current_line + word + " "
                        if len(test_line) > 50:
                            message_lines.append(current_line)
                            current_line = word + " "
                        else:
                            current_line = test_line
                    if current_line:
                        message_lines.append(current_line)
                    for line in message_lines:
                        draw.text((bubble_x, y_pos), line, fill=(255,255,255), font=font_medium)
                        y_pos += 25
                    if msg.get('typing'):
                        draw.text((bubble_x, y_pos), "⏳ typing...", fill=(200,200,100), font=font_small)
                        y_pos += 20
                    y_pos += 15
            except Exception as pil_error:
                if self._render_count % 10 == 0:
                    print(f"⚠️ Advanced PIL rendering failed: {pil_error}")
                draw.text((100,100), f"Chat Frame - {len(filtered_messages)} messages", fill=(255,255,255))
                if show_typing_bar and typing_user:
                    draw.text((100,150), f"{typing_user} typing: {upcoming_text}", fill=(100,255,100))
            img.save(frame_file)
            if self._render_count % 50 == 0:
                print(f"✅ PIL fallback frame {self._render_count}: {frame_file}")

        # Cache non-typing frames
        if not is_typing_frame and len(FRAME_CACHE) < CACHE_MAX_SIZE:
            FRAME_CACHE[cache_key] = frame_file

        render_time = time.time() - start_time
        if render_time > 1.0:
            print(f"⏱️ Frame {self._render_count} rendered in {render_time:.2f}s")

        return rendered_html

# ---------- BUBBLE RENDERING ---------- #
def render_bubble(username, message="", meme_path=None, is_sender=None, is_read=False, typing=False):
    """
    Add message and render a frame. Returns path to created frame image.
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
        is_sender = (username.strip().lower() == MAIN_USER.lower()) if username else False

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

    # typing handling
    if typing:
        if is_sender:
            if render_bubble.frame_count % 20 == 0:
                print(f"⌨️ Sender {username} typing - using typing bar")
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

    # normal message
    render_bubble.renderer.add_message(username, message, meme_path=meme_path, is_read=is_read, typing=False)
    frame_file = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
    is_typing_bar = (username.strip().lower() == MAIN_USER.lower() and not message) if username else False
    render_bubble.renderer.render_frame(frame_file, show_typing_bar=False, short_wait=is_typing_bar)

    text_dur = _text_duration(message, False)
    meme_dur = _meme_duration(meme_path) if meme_path else 0.0
    duration = max(text_dur, meme_dur) if meme_path else text_dur

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
    if render_bubble.frame_count % 20 == 0:
        print(f"✅ Regular frame {render_bubble.frame_count}: {frame_file} ({duration}s)")
    return frame_file

def render_meme(username, meme_path):
    return render_bubble(username, "", meme_path=meme_path)

def render_typing_bubble(username, duration=None, is_sender=None, custom_durations=None):
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
        is_sender = (username.strip().lower() == MAIN_USER.lower()) if username else False
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

def render_typing_bar_frame(username, upcoming_text="", frame_path=None, duration=None, is_character_typing=True):
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
    should_play_sound = is_character_typing
    current_text = upcoming_text.replace("|", "").strip()
    is_final_frame = (not upcoming_text.endswith('|') and current_text)
    if is_final_frame:
        should_play_sound = False
        if render_bubble.frame_count % 20 == 0:
            print(f"🎹 FINAL FRAME DETECTED: '{upcoming_text}' - NO SOUND")
    if render_bubble.frame_count % 50 == 0:
        print(f"🎹 SIMPLE SOUND: is_typing={is_character_typing} -> sound={should_play_sound}")
    if not hasattr(render_bubble, 'current_typing_session'):
        render_bubble.current_typing_session = None
    if is_character_typing and not hasattr(render_bubble, 'prev_typing_text'):
        render_bubble.prev_typing_text = ""
    current_text = upcoming_text.replace("|", "").strip()
    if is_character_typing and not render_bubble.prev_typing_text and current_text:
        render_bubble.current_typing_session = f"session_{render_bubble.frame_count}"
        if render_bubble.frame_count % 20 == 0:
            print(f"🎹 🆕 STARTING NEW TYPING SESSION: {render_bubble.current_typing_session}")
    if not is_character_typing and render_bubble.current_typing_session:
        if render_bubble.frame_count % 20 == 0:
            print(f"🎹 🛑 ENDING TYPING SESSION: {render_bubble.current_typing_session}")
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
    if render_bubble.frame_count % 20 == 0:
        print(f"🎹 Frame {render_bubble.frame_count}: '{upcoming_text}' - Sound: {should_play_sound}")
    render_bubble.timeline.append(entry)
    with open(TIMELINE_FILE, "w", encoding="utf-8") as tf:
        json.dump(render_bubble.timeline, tf, indent=2)
    render_bubble.frame_count += 1
    return frame_path

# ---------- Typing sequence helpers (kept) ---------- #
def generate_beluga_typing_sequence(real_message):
    if not real_message:
        return []
    fake_phrases = ["Wait", "Hold on", "Hmm", "Nah", "Actually", "But", "Wait what", "No way", "Umm", "For real", "Bruh", "Lol", "Well", "Okay"]
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
    if (render_bubble.fake_typing_count < render_bubble.max_fakes_per_video and random.random() < 0.4):
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
    return rendered_frames

def reset_typing_sessions():
    if hasattr(render_bubble, 'typing_session_active'):
        render_bubble.typing_session_active = False
    render_bubble.typing_session_start = 0
    render_bubble.current_typing_session = None
    render_bubble.prev_typing_text = ""
    render_bubble.fake_typing_count = 0
    print("🔄 Reset typing session tracking")

# ---------- MAIN ---------- #
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
        print("🔄 Initialized typing session tracking for main script")

        # Example minimal run: (you likely have your own script parser)
        # For quick test, render a few test frames:
        render_bubble("Banka", "Hello, this is a test message.")
        render_bubble("Paula", "Hi Banka! Nice to see you here.")
        render_bubble("Jay Khooi", "This message has no avatar so initial should show.")
        render_typing_sequence("Banka", "Typing test...")

        # After frames exist, attempt to build video (safe path)
        try:
            timeline = getattr(render_bubble, "timeline", [])
            out_video = os.path.join(BASE_DIR, "output_video.mp4")
            # Attempt to build video if ffmpeg is available
            final = build_video_from_timeline(timeline, out_video)
            if final:
                print(f"✅ Final video: {final}")
            else:
                print("⚠️ Video build returned None (ffmpeg may not be available or no frames).")
        except Exception as video_err:
            print(f"❌ Error rendering video: {video_err}")
            traceback.print_exc()

        print(f"✅ Rendered {render_bubble.frame_count} frames from {script_file}")

    finally:
        cleanup_resources()

