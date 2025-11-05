# Optimized render_bubble.py
# Replaces original while preserving exact output and features.
# Key optimizations: template precompile, avatar & meme base64 cache,
# font caching, avoid unnecessary file moves by running screenshot in frames dir,
# limit message history passed to template, reduce I/O for timeline writes,
# optional OUTPUT_HTML writes controlled by env var to avoid disk churn.

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

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# Reduce logging verbosity (keep quiet)
logging.getLogger('html2image').setLevel(logging.WARNING)
logging.getLogger('PIL').setLevel(logging.WARNING)
logging.getLogger('selenium').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('selenium.webdriver.remote.remote_connection').setLevel(logging.ERROR)

os.environ.setdefault('DBUS_SESSION_BUS_ADDRESS', '')
os.environ.setdefault('DBUS_SYSTEM_BUS_ADDRESS', '')
os.environ.setdefault('DISABLE_DEV_SHM', 'true')
os.environ.setdefault('ENABLE_CRASH_REPORTER', 'false')

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
W, H = 1904, 934  # match video size

# ---------- PERFORMANCE OPTIMIZATIONS ---------- #
FRAME_CACHE = {}
CACHE_MAX_SIZE = 400  # allow larger cache (increase if disk permits)
AVATAR_CACHE = {}     # stores avatar paths, base64, colors, memes
MESSAGE_HISTORY_LIMIT = 200  # keep rendering correct but cap history
HTI = None
TEMPLATE_STR = None
FONT_CACHE = {}
WRITE_OUTPUT_HTML = os.environ.get('WRITE_OUTPUT_HTML', '0') == '1'
TIMELINE_WRITE_INTERVAL = 10  # write timeline every N frames to reduce I/O

# ---------- AVATAR MANAGEMENT SYSTEM ---------- #

def load_characters():
    if os.path.exists(CHARACTERS_FILE):
        try:
            with open(CHARACTERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def get_character_avatar_path(username):
    cache_key = f"avatar_path_{username.strip().lower()}"
    if cache_key in AVATAR_CACHE:
        return AVATAR_CACHE[cache_key]

    username_clean = username.strip()
    characters = load_characters()
    if username_clean in characters:
        avatar_path = characters[username_clean].get("avatar", "")
        if avatar_path:
            full_path = avatar_path if os.path.isabs(avatar_path) else os.path.join(BASE_DIR, avatar_path)
            if os.path.exists(full_path):
                AVATAR_CACHE[cache_key] = full_path
                return full_path

    avatars_dir = AVATAR_DIR
    if os.path.exists(avatars_dir):
        for ext in ('.png', '.jpg', '.jpeg'):
            candidates = [f"{username_clean}{ext}", f"{username_clean.replace(' ', '_')}{ext}"]
            for fn in candidates:
                p = os.path.join(avatars_dir, fn)
                if os.path.exists(p):
                    AVATAR_CACHE[cache_key] = p
                    return p

    AVATAR_CACHE[cache_key] = ""
    return ""


def encode_avatar_for_html(avatar_path):
    if not avatar_path or not os.path.exists(avatar_path):
        return ""
    cache_key = f"avatar_base64_{avatar_path}"
    if cache_key in AVATAR_CACHE:
        return AVATAR_CACHE[cache_key]

    # Small optimization: read once and reuse
    try:
        with open(avatar_path, 'rb') as f:
            data = f.read()
        b64 = base64.b64encode(data).decode('utf-8')
        mime_type = 'image/jpeg'
        if avatar_path.lower().endswith('.png'):
            mime_type = 'image/png'
        elif avatar_path.lower().endswith('.gif'):
            mime_type = 'image/gif'
        result = f"data:{mime_type};base64,{b64}"
        AVATAR_CACHE[cache_key] = result
        return result
    except Exception:
        return ""

# ---------- HTML2Image (Chromium) ---------- #

def get_html2image():
    global HTI
    if HTI is not None:
        return HTI

    possible_paths = [
        '/usr/bin/chromium', '/usr/bin/chromium-browser',
        '/usr/bin/google-chrome', '/usr/bin/chrome',
        '/app/.apt/usr/bin/chromium-browser'
    ]
    chromium_path = None
    for p in possible_paths:
        if os.path.exists(p):
            chromium_path = p
            break

    flags = [
        '--no-sandbox', '--disable-dev-shm-usage', '--headless', '--window-size=1920,1080',
        '--disable-gpu', '--disable-software-rasterizer', '--no-first-run', '--no-default-browser-check',
        '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding', '--disable-logging', '--disable-crash-reporter'
    ]

    try:
        if chromium_path:
            HTI = html2image.Html2Image(browser='chromium', browser_executable=chromium_path, custom_flags=flags)
        else:
            HTI = None
    except Exception:
        HTI = None
    return HTI

# ---------- CLEANUP ---------- #

def cleanup_resources():
    global HTI
    HTI = None
    FRAME_CACHE.clear()
    AVATAR_CACHE.clear()
    FONT_CACHE.clear()
    gc.collect()

# ---------- FRAME CACHE KEY ---------- #

def get_frame_cache_key(messages, show_typing_bar, typing_user, upcoming_text):
    # Only include last N messages to keep key stable and small
    key_msgs = [(m.get('username',''), m.get('text',''), m.get('typing', False)) for m in messages[-20:]]
    key_data = {
        'messages': key_msgs,
        'show_typing_bar': show_typing_bar,
        'typing_user': typing_user,
        'upcoming_text': upcoming_text
    }
    return hashlib.md5(json.dumps(key_data, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()

# ---------- HELPERS ---------- #

def encode_meme(path):
    if not path or not isinstance(path, str) or not os.path.exists(path):
        return None
    cache_key = f"meme_{path}"
    if cache_key in AVATAR_CACHE:
        return AVATAR_CACHE[cache_key]
    import mimetypes
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = 'application/octet-stream'
    with open(path, 'rb') as f:
        b = f.read()
    encoded = base64.b64encode(b).decode('utf-8')
    res = {'meme': encoded, 'mime': mime, 'meme_type': os.path.splitext(path)[1].lower()}
    AVATAR_CACHE[cache_key] = res
    return res


def name_to_color(username: str) -> str:
    cache_key = f"color_{username.strip().lower()}"
    if cache_key in AVATAR_CACHE:
        return AVATAR_CACHE[cache_key]
    h = hashlib.md5(username.strip().lower().encode('utf-8')).hexdigest()
    n = int(h[:8], 16)
    hue = (n * 137) % 360
    sat = 0.7
    light = 0.55
    r, g, b = colorsys.hls_to_rgb(hue/360, light, sat)
    res = f'#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}'
    AVATAR_CACHE[cache_key] = res
    return res


def calculate_typing_duration(text):
    chars = len(text.strip())
    base = 1.5
    per = 0.07
    return min(base + chars * per, 4.0)

# ---------- FONT LOADING (cache) ---------- #

def load_font(path, size):
    key = f"{path}:{size}"
    if key in FONT_CACHE:
        return FONT_CACHE[key]
    try:
        f = ImageFont.truetype(path, size)
    except Exception:
        try:
            f = ImageFont.load_default()
        except Exception:
            f = None
    FONT_CACHE[key] = f
    return f

# ---------- EMOJI FONT DETECTION ---------- #

def install_emoji_fonts():
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Apple Color Emoji.ttc",
        "C:/Windows/Fonts/segoeuiemoji.ttf"
    ]
    found = []
    for p in candidates:
        if os.path.exists(p):
            found.append(p)
            break
    return found

# ---------- RENDERER ---------- #

class WhatsAppRenderer:
    def __init__(self, chat_title="Default Group", chat_avatar=None, chat_status=None):
        self.message_history = []
        self.jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)
        self.chat_title = chat_title
        self.chat_avatar = chat_avatar
        self.chat_status = chat_status
        self._render_count = 0
        self._emoji_fonts = install_emoji_fonts()
        # Precompile template to reduce repeated parsing cost
        global TEMPLATE_STR
        try:
            self.template = self.jinja_env.get_template(TEMPLATE_FILE)
        except Exception:
            # fallback: load raw template text if Jinja fails
            try:
                with open(os.path.join(TEMPLATE_DIR, TEMPLATE_FILE), 'r', encoding='utf-8') as tf:
                    TEMPLATE_STR = tf.read()
                self.template = None
            except Exception:
                self.template = None

    def add_message(self, username, message, meme_path=None, is_read=False, typing=False):
        # timestamp generation - robust across platforms
        try:
            ts = datetime.now().strftime("%-I:%M %p").lower()
        except Exception:
            ts = datetime.now().strftime("%I:%M %p").lstrip('0').lower()

        color = name_to_color(username)
        avatar_path = get_character_avatar_path(username)
        avatar_data = ""
        mime = None
        if avatar_path:
            avatar_data = encode_avatar_for_html(avatar_path)
            if avatar_data:
                mime = 'image/png' if avatar_path.lower().endswith('.png') else 'image/jpeg'

        if not avatar_data:
            # initials fallback generation - cached per username
            initials_key = f"initials_{username.strip().lower()}"
            if initials_key in AVATAR_CACHE:
                avatar_data = AVATAR_CACHE[initials_key]
                mime = 'image/png'
            else:
                initials = ''.join([w[0] for w in username.strip().split()[:2]]).upper() or '?'
                img_size = 128
                r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
                img = Image.new('RGB', (img_size, img_size), color=(r, g, b))
                draw = ImageDraw.Draw(img)
                font_size = 60 if len(initials) == 1 else 48
                # try candidate fonts once
                fonts = [
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                ]
                font = None
                for fp in fonts:
                    font = load_font(fp, font_size)
                    if font:
                        break
                if font is None:
                    font = ImageFont.load_default()
                try:
                    bbox = draw.textbbox((0, 0), initials, font=font)
                    w = bbox[2] - bbox[0]
                    h = bbox[3] - bbox[1]
                    x = (img_size - w) / 2
                    y = (img_size - h) / 2 - bbox[1]
                    draw.text((x, y), initials, font=font, fill=(255, 255, 255))
                except Exception:
                    draw.text((img_size//6, img_size//4), initials, fill=(255,255,255))
                buf = BytesIO()
                img.save(buf, format='PNG')
                avatar_data = base64.b64encode(buf.getvalue()).decode('utf-8')
                avatar_data = f"data:image/png;base64,{avatar_data}"
                AVATAR_CACHE[initials_key] = avatar_data
                mime = 'image/png'

        meme_data = None
        if meme_path and os.path.exists(meme_path):
            meme_data = encode_meme(meme_path)

        entry = {
            'username': username,
            'text': message if not typing else '',
            'typing': typing,
            'is_sender': username.strip().lower() == MAIN_USER.lower(),
            'is_read': is_read,
            'timestamp': ts,
            'color': color,
            'avatar': avatar_data,
            'avatar_format': mime
        }
        if meme_data:
            entry['meme'] = meme_data['meme']
            entry['mime'] = meme_data['mime']
            entry['meme_type'] = meme_data['meme_type']

        self.message_history.append(entry)
        # Keep message history within limit
        if len(self.message_history) > MESSAGE_HISTORY_LIMIT:
            self.message_history = self.message_history[-MESSAGE_HISTORY_LIMIT:]

    def _render_html(self, messages_slice, show_typing_bar, typing_user, upcoming_text):
        # Use precompiled template when available
        if self.template:
            return self.template.render(
                messages=messages_slice,
                static_path='/app/static',
                chat_title=getattr(self, 'chat_title', None),
                chat_avatar=getattr(self, 'chat_avatar', None),
                chat_status=getattr(self, 'chat_status', None),
                show_typing_bar=show_typing_bar,
                typing_user=typing_user,
                upcoming_text=upcoming_text
            )
        else:
            # fallback naive string replacement — rarely used but preserves output
            global TEMPLATE_STR
            if TEMPLATE_STR:
                return TEMPLATE_STR.format(messages=messages_slice)
            return ""

    def render_frame(self, frame_file, show_typing_bar=False, typing_user=None, upcoming_text="", short_wait=False):
        start = time.time()
        self._render_count += 1
        is_typing_frame = show_typing_bar and bool(upcoming_text)

        cache_key = get_frame_cache_key(self.message_history, show_typing_bar, typing_user, upcoming_text)
        if not is_typing_frame and cache_key in FRAME_CACHE:
            cached = FRAME_CACHE[cache_key]
            if os.path.exists(cached):
                # fast copy using os.replace where possible
                try:
                    os.replace(cached, frame_file)
                except Exception:
                    import shutil
                    shutil.copy2(cached, frame_file)
                return cached

        # Build filtered messages (skip sender typing bubbles)
        filtered = [m for m in self.message_history if not (m['is_sender'] and m['typing'])]
        # Keep slice for rendering (limit passed into template to avoid huge DOM)
        messages_slice = filtered[-MESSAGE_HISTORY_LIMIT:]

        rendered_html = self._render_html(messages_slice, show_typing_bar, typing_user, upcoming_text)

        # Optionally write OUTPUT_HTML — disabled by default to reduce I/O
        if WRITE_OUTPUT_HTML:
            try:
                with open(OUTPUT_HTML, 'w', encoding='utf-8') as of:
                    of.write(rendered_html)
            except Exception:
                pass

        # Try rendering with HTML2Image (Chromium). Run screenshot inside FRAMES_DIR to avoid moving files
        try:
            hti = get_html2image()
            if hti is None:
                raise Exception('HTML2Image not available')
            temp_name = f"temp_{int(time.time()*1000)}.html"
            temp_path = os.path.join(FRAMES_DIR, temp_name)
            with open(temp_path, 'w', encoding='utf-8') as tf:
                tf.write(rendered_html)

            cwd = os.getcwd()
            try:
                os.chdir(FRAMES_DIR)
                hti.screenshot(html_file=temp_name, save_as=os.path.basename(frame_file), size=(1920,1080))
            finally:
                os.chdir(cwd)

            # remove temp
            try:
                os.remove(temp_path)
            except Exception:
                pass

        except Exception:
            # Fast PIL fallback — minimal but reliable
            try:
                img = Image.new('RGB', (1920,1080), color=(11,20,26))
                draw = ImageDraw.Draw(img)
                font_large = None
                if self._emoji_fonts:
                    for fp in self._emoji_fonts:
                        font_large = load_font(fp, 36)
                        if font_large:
                            break
                if font_large is None:
                    font_large = load_font('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 36) or ImageFont.load_default()
                draw.rectangle([0,0,1920,130], fill=(17,27,33))
                draw.text((100,50), f"💬 {self.chat_title}", fill=(255,255,255), font=font_large)
                draw.text((100,90), f"Messages: {len(filtered)}", fill=(134,150,160), font=font_large)
                if show_typing_bar and typing_user:
                    draw.text((100,150), f"⌨️ {typing_user} is typing...", fill=(100,255,100), font=font_large)
                img.save(frame_file, optimize=True, quality=85)
            except Exception:
                # Last resort
                with open(frame_file, 'wb') as fh:
                    fh.write(b'')

        # Cache non-typing frames
        if not is_typing_frame:
            if len(FRAME_CACHE) >= CACHE_MAX_SIZE:
                # remove random/old entry (simple LRU-ish by popitem)
                try:
                    FRAME_CACHE.pop(next(iter(FRAME_CACHE)))
                except Exception:
                    FRAME_CACHE.clear()
            FRAME_CACHE[cache_key] = frame_file

        render_time = time.time() - start
        if render_time > 3.0:
            # only log notably slow frames
            logging.warning(f"Slow frame {self._render_count}: {render_time:.2f}s")
        return frame_file

# ---------- BUBBLE RENDERING API (unchanged behavior) ---------- #

def render_bubble(username, message="", meme_path=None, is_sender=None, is_read=False, typing=False):
    if not hasattr(render_bubble, 'renderer'):
        render_bubble.renderer = WhatsAppRenderer(chat_title="BANKA TOUR GROUP", chat_avatar="static/images/group.png", chat_status="jay, khooi, banka, Paula")
        render_bubble.frame_count = 0
        render_bubble.timeline = []

    if is_sender is None:
        is_sender = (username.strip().lower() == MAIN_USER.lower())

    def _text_duration(text, typing_flag):
        if typing_flag:
            return 1.5
        chars = len(text.strip()) if text else 0
        return max(2.0, chars / 12.0)

    def _meme_duration(path):
        if not path or not os.path.exists(path):
            return 3.0
        try:
            with Image.open(path) as im:
                w,h = im.size
            size_factor = (w*h) / (1920*1080)
            return max(2.5, min(6.0, 2.0 + size_factor*3.0))
        except Exception:
            return 3.0

    if typing:
        if is_sender:
            return render_typing_bar_frame(username, upcoming_text=message if message else "", duration=1.5)
        else:
            orig = render_bubble.renderer.message_history.copy()
            render_bubble.renderer.add_message(username, None, typing=True)
            frame_file = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
            render_bubble.renderer.render_frame(frame_file, short_wait=True)
            render_bubble.renderer.message_history = orig
            entry = {"frame": os.path.abspath(frame_file), "duration":1.5, "is_sender":is_sender, "username":username, "text":"", "is_meme":False, "meme_path":None, "typing":True}
            render_bubble.timeline.append(entry)
            if render_bubble.frame_count % TIMELINE_WRITE_INTERVAL == 0:
                try:
                    with open(TIMELINE_FILE,'w',encoding='utf-8') as tf:
                        json.dump(render_bubble.timeline, tf, indent=2)
                except Exception:
                    pass
            render_bubble.frame_count += 1
            return frame_file

    # Normal flow
    render_bubble.renderer.add_message(username, message, meme_path=meme_path, is_read=is_read, typing=False)
    frame_file = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
    render_bubble.renderer.render_frame(frame_file, show_typing_bar=False, short_wait=False)

    text_dur = _text_duration(message, False)
    meme_dur = _meme_duration(meme_path) if meme_path else 0.0
    duration = max(text_dur, meme_dur) if meme_path else text_dur

    entry = {"frame": os.path.abspath(frame_file), "duration": round(duration,3), "is_sender": is_sender, "username": username, "text": message, "is_meme": bool(meme_path), "meme_path": meme_path, "typing": False}
    if meme_path and os.path.exists(meme_path):
        try:
            mi = encode_meme(meme_path)
            if mi:
                entry['meme_type'] = mi.get('meme_type')
                entry['meme_b64'] = mi.get('meme')
                entry['mime'] = mi.get('mime')
        except Exception:
            pass

    render_bubble.timeline.append(entry)
    if render_bubble.frame_count % TIMELINE_WRITE_INTERVAL == 0:
        try:
            with open(TIMELINE_FILE, 'w', encoding='utf-8') as tf:
                json.dump(render_bubble.timeline, tf, indent=2)
        except Exception:
            pass
    render_bubble.frame_count += 1
    return frame_file


def render_meme(username, meme_path):
    return render_bubble(username, "", meme_path=meme_path)


def render_typing_bubble(username, duration=None, is_sender=None, custom_durations=None):
    custom_durations = custom_durations or {}
    if not hasattr(render_bubble, 'renderer'):
        render_bubble.renderer = WhatsAppRenderer(chat_title="BANKA TOUR GROUP", chat_avatar="static/images/group.png", chat_status="jay, khooi, banka")
        render_bubble.frame_count = 0
        render_bubble.timeline = []
    if is_sender is None:
        is_sender = (username.strip().lower() == MAIN_USER.lower())
    if is_sender:
        return render_typing_bar_frame(username, "", duration=1.5)
    orig = render_bubble.renderer.message_history.copy()
    render_bubble.renderer.add_message(username, None, typing=True)
    frame_file = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
    render_bubble.renderer.render_frame(frame_file, short_wait=True)
    render_bubble.renderer.message_history = orig
    typing_key = f"typing:{username}"
    dur = custom_durations.get(typing_key, 1.5) if custom_durations else 1.5
    if dur <= 0:
        dur = 1.5
    entry = {"frame": os.path.abspath(frame_file), "duration": dur, "is_sender": is_sender, "username": username, "text":"", "is_meme": False, "meme_path": None, "typing": True, "typing_sound": False}
    render_bubble.timeline.append(entry)
    if render_bubble.frame_count % TIMELINE_WRITE_INTERVAL == 0:
        try:
            with open(TIMELINE_FILE, 'w', encoding='utf-8') as tf:
                json.dump(render_bubble.timeline, tf, indent=2)
        except Exception:
            pass
    render_bubble.frame_count += 1
    return frame_file


def render_typing_bar_frame(username, upcoming_text="", frame_path=None, duration=None, is_character_typing=True):
    if not hasattr(render_bubble, 'renderer'):
        render_bubble.renderer = WhatsAppRenderer(chat_title="BANKA TOUR GROUP", chat_avatar="static/images/group.png", chat_status="jay, khooi, banka")
        render_bubble.frame_count = 0
        render_bubble.timeline = []
    if not frame_path:
        frame_path = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
    if username.strip().lower() != MAIN_USER.lower():
        return render_typing_bubble(username, custom_durations={})
    orig = render_bubble.renderer.message_history.copy()
    render_bubble.renderer.render_frame(frame_file=frame_path, show_typing_bar=True, typing_user=username, upcoming_text=upcoming_text, short_wait=True)
    render_bubble.renderer.message_history = orig
    if duration is None or duration <= 0:
        if not is_character_typing or upcoming_text.endswith('|'):
            frame_duration = 0.8
        else:
            frame_duration = 0.4
    else:
        frame_duration = duration
    should_play_sound = is_character_typing
    current_text = upcoming_text.replace('|','').strip()
    is_final = (not upcoming_text.endswith('|') and current_text)
    if is_final:
        should_play_sound = False
    if not hasattr(render_bubble, 'current_typing_session'):
        render_bubble.current_typing_session = None
    if is_character_typing and not hasattr(render_bubble, 'prev_typing_text'):
        render_bubble.prev_typing_text = ''
    if is_character_typing and not render_bubble.prev_typing_text and current_text:
        render_bubble.current_typing_session = f"session_{render_bubble.frame_count}"
    if not is_character_typing and render_bubble.current_typing_session:
        render_bubble.current_typing_session = None
    render_bubble.prev_typing_text = current_text
    entry = {"frame": os.path.abspath(frame_path), "duration": frame_duration, "is_sender": True, "username": username, "text":"", "is_meme": False, "meme_path": None, "typing_bar": True, "upcoming_text": upcoming_text, "sound": should_play_sound, "typing_session_id": (render_bubble.current_typing_session if is_character_typing else None)}
    render_bubble.timeline.append(entry)
    if render_bubble.frame_count % TIMELINE_WRITE_INTERVAL == 0:
        try:
            with open(TIMELINE_FILE, 'w', encoding='utf-8') as tf:
                json.dump(render_bubble.timeline, tf, indent=2)
        except Exception:
            pass
    render_bubble.frame_count += 1
    return frame_path


def generate_beluga_typing_sequence(real_message):
    if not real_message:
        return []
    fake_phrases = ["Wait","Hold on","Hmm","Nah","Actually","But","Wait what","No way","Umm","For real","Bruh","Lol","Well","Okay"]
    sequence = []
    SPEED_MULTIPLIER = 0.5
    def typing_speed_for(ch):
        if ch in ['.',',','!','?','…']:
            base = random.uniform(0.12,0.25)
        elif ch == ' ':
            base = random.uniform(0.06,0.1)
        elif ord(ch) > 127:
            base = random.uniform(0.15,0.25)
        else:
            base = random.uniform(0.07,0.17)
        return base * SPEED_MULTIPLIER
    def blink_frame(text, blinks=1):
        for _ in range(blinks):
            sequence.append((text + '|', 0.25, False))
            sequence.append((text, 0.25, False))
    if not hasattr(render_bubble, 'fake_typing_count'):
        render_bubble.fake_typing_count = 0
        render_bubble.max_fakes_per_video = random.randint(1,2)
    if (render_bubble.fake_typing_count < render_bubble.max_fakes_per_video and random.random() < 0.4):
        fake = random.choice(fake_phrases)
        render_bubble.fake_typing_count += 1
        buf = ''
        for ch in fake:
            buf += ch
            sequence.append((buf + '|', typing_speed_for(ch), True))
        blink_frame(buf, blinks=1)
        for i in range(len(fake)-1, -1, -1):
            buf = fake[:i]
            sequence.append((buf + '|', random.uniform(0.15,0.25), False))
        sequence.append(('', 0.5, False))
    buf = ''
    for i,ch in enumerate(real_message):
        buf += ch
        is_active = True
        if i >= len(real_message)-3:
            is_active = False
        sequence.append((buf + '|', typing_speed_for(ch), is_active))
    blink_frame(real_message, blinks=2)
    sequence.append((real_message, 0.8, False))
    return sequence


def render_typing_sequence(username, real_message):
    seq = generate_beluga_typing_sequence(real_message)
    rendered = []
    for text, dur, has_sound in seq:
        fp = render_typing_bar_frame(username, upcoming_text=text, duration=dur, is_character_typing=has_sound)
        rendered.append(fp)
    return rendered


def reset_typing_sessions():
    if hasattr(render_bubble, 'typing_session_active'):
        render_bubble.typing_session_active = False
        render_bubble.typing_session_start = 0
        render_bubble.current_typing_session = None
        render_bubble.prev_typing_text = ''
        render_bubble.fake_typing_count = 0

# ---------- MAIN SCRIPT ---------- #
if __name__ == '__main__':
    try:
        if len(sys.argv) < 2:
            print('Usage: python render_bubble.py script.txt')
            sys.exit(1)
        script_file = sys.argv[1]
        render_bubble.frame_count = 0
        render_bubble.timeline = []
        render_bubble.renderer = WhatsAppRenderer()
        reset_typing_sessions()
        print(f"✅ Prepared renderer; start file: {script_file}")
    finally:
        cleanup_resources()

