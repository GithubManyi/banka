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
import mimetypes
import requests
import random
import logging
import gc
import shutil

# Suppress noisy logs
logging.getLogger('html2image').setLevel(logging.WARNING)
logging.getLogger('PIL').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

# ---------- CONFIG ---------- #
ROOT = r"c:\Users\user\banka"
TMP = os.path.join(ROOT, "tmp_ffmpeg")
FPS = 25
W, H = 1904, 934
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "backend", "templates")
TEMPLATE_FILE = "index.html"
OUTPUT_HTML = os.path.join(BASE_DIR, "rendered_chat.html")
FRAMES_DIR = os.path.join(BASE_DIR, "frames")
TIMELINE_FILE = os.path.join(FRAMES_DIR, "timeline.json")
os.makedirs(FRAMES_DIR, exist_ok=True)
os.makedirs(TMP, exist_ok=True)
MAIN_USER = "Banka"

# ---------- PERFORMANCE ---------- #
FRAME_CACHE = {}
CACHE_MAX_SIZE = 100
HTI = None

# Import backend utilities
try:
    from backend.avatar_handler import get_avatar
    from backend.meme_utils import download_meme, find_meme
    from backend.meme_fetcher import fetch_meme_from_giphy
except ImportError as e:
    print(f"Warning: Could not import backend utils: {e}")
    # Define stubs if not available
    def get_avatar(username): return "static/images/default.png"
    def find_meme(desc, assets_dir): return None

# ---------- HTML2IMAGE SETUP ---------- #
def get_html2image():
    global HTI
    if HTI is None:
        try:
            import html2image
            possible_paths = [
                '/usr/bin/chromium-browser',
                '/usr/bin/chromium',
                '/usr/bin/google-chrome',
                '/app/.apt/usr/bin/chromium-browser'
            ]
            chromium_path = next((p for p in possible_paths if os.path.exists(p)), None)
            if chromium_path:
                HTI = html2image.Html2Image(
                    browser='chromium',
                    browser_executable=chromium_path,
                    custom_flags=[
                        '--no-sandbox', '--disable-dev-shm-usage',
                        '--disable-gpu', '--headless', '--window-size=1920,1080'
                    ]
                )
                print(f"HTML2Image initialized with {chromium_path}")
            else:
                print("No Chromium found, using PIL fallback")
                HTI = None
        except Exception as e:
            print(f"HTML2Image setup failed: {e}")
            HTI = None
    return HTI

# ---------- HELPERS ---------- #
def encode_meme(path):
    if not path or not os.path.exists(path):
        return None
    ext = os.path.splitext(path)[1].lower()
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "application/octet-stream"
    try:
        with open(path, "rb") as f:
            data = f.read()
        encoded = base64.b64encode(data).decode("utf-8")
        return {"meme": encoded, "meme_type": ext, "mime": mime}
    except Exception as e:
        print(f"Failed to encode meme {path}: {e}")
        return None

def name_to_color(username: str) -> str:
    h = hashlib.md5(username.strip().lower().encode()).hexdigest()
    n = int(h[:8], 16)
    hue = (n * 137) % 360
    r, g, b = colorsys.hls_to_rgb(hue/360, 0.55, 0.7)
    return f'#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}'

def get_frame_cache_key(messages, show_typing_bar, typing_user, upcoming_text):
    key_data = {
        'messages': [(m.get('username',''), m.get('text',''), m.get('typing',False)) for m in messages],
        'show_typing_bar': show_typing_bar,
        'typing_user': typing_user,
        'upcoming_text': upcoming_text
    }
    return hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

# ---------- RENDERER ---------- #
class WhatsAppRenderer:
    def __init__(self, chat_title="Default Group", chat_avatar=None, chat_status=None):
        self.message_history = []
        self.jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
        self.chat_title = chat_title
        self.chat_avatar = chat_avatar
        self.chat_status = chat_status
        self._render_count = 0

    def add_message(self, username, message, meme_path=None, is_read=False, typing=False):
        ts = datetime.now().strftime("%-I:%M %p").lower()
        color = name_to_color(username)
        avatar_path = get_avatar(username)
        meme_data = encode_meme(meme_path) if meme_path and os.path.exists(meme_path) else None

        entry = {
            "username": username,
            "text": "" if typing else message,
            "typing": typing,
            "is_sender": username.strip().lower() == MAIN_USER.lower(),
            "is_read": is_read,
            "timestamp": ts,
            "color": color,
            "avatar": os.path.basename(avatar_path)
        }
        if meme_data:
            entry.update(meme_data)
        self.message_history.append(entry)

    def render_frame(self, frame_file, show_typing_bar=False, typing_user=None, upcoming_text="", short_wait=False):
        self._render_count += 1
        cache_key = get_frame_cache_key(self.message_history, show_typing_bar, typing_user, upcoming_text)
        is_typing = show_typing_bar and upcoming_text

        if not is_typing and cache_key in FRAME_CACHE and os.path.exists(FRAME_CACHE[cache_key]):
            if self._render_count % 50 == 0:
                print(f"Cache hit: {cache_key[:8]}")
            shutil.copy2(FRAME_CACHE[cache_key], frame_file)
            return

        template = self.jinja_env.get_template(TEMPLATE_FILE)
        filtered = [m for m in self.message_history if not (m['is_sender'] and m['typing'])]
        html = template.render(
            messages=filtered,
            chat_title=self.chat_title,
            chat_avatar=self.chat_avatar,
            chat_status=self.chat_status,
            show_typing_bar=show_typing_bar,
            typing_user=typing_user,
            upcoming_text=upcoming_text
        )

        with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
            f.write(html)

        # Try HTML2Image
        hti = get_html2image()
        success = False
        if hti:
            try:
                temp_html = os.path.join(FRAMES_DIR, f"temp_{self._render_count}.html")
                with open(temp_html, "w", encoding="utf-8") as f:
                    f.write(html)
                hti.screenshot(html_file=temp_html, save_as=os.path.basename(frame_file), size=(1920, 1080))
                generated = os.path.join(os.getcwd(), os.path.basename(frame_file))
                if os.path.exists(generated):
                    os.rename(generated, frame_file)
                    success = True
                if os.path.exists(temp_html):
                    os.remove(temp_html)
            except Exception as e:
                if self._render_count % 10 == 0:
                    print(f"HTML2Image failed: {e}")

        # PIL Fallback
        if not success:
            img = Image.new('RGB', (1920, 1080), (53, 53, 53))
            draw = ImageDraw.Draw(img)
            try:
                font_l = ImageFont.truetype("Arial", 24)
                font_m = ImageFont.truetype("Arial", 18)
                font_s = ImageFont.truetype("Arial", 14)
            except:
                font_l = font_m = font_s = ImageFont.load_default()

            y = 50
            draw.text((100, y), f"{self.chat_title}", fill=(255,255,255), font=font_l); y += 40
            draw.text((100, y), f"{self.chat_status}", fill=(200,200,200), font=font_m); y += 60

            if show_typing_bar and typing_user:
                draw.text((100, y), f"{typing_user} is typing: {upcoming_text}", fill=(100,255,100), font=font_m); y += 40

            for msg in filtered[-8:]:
                x = 100 if not msg['is_sender'] else 1000
                draw.text((x, y), f"{msg['username']} • {msg['timestamp']}", fill=msg['color'], font=font_s); y += 25
                lines = []
                line = ""
                for w in msg['text'].split():
                    t = line + w + " "
                    if len(t) > 50:
                        lines.append(line); line = w + " "
                    else:
                        line = t
                if line: lines.append(line)
                for l in lines:
                    draw.text((x, y), l, fill=(255,255,255), font=font_m); y += 25
                if msg.get('typing'):
                    draw.text((x, y), "typing...", fill=(200,200,100), font=font_s); y += 20
                y += 15
            img.save(frame_file)
            if self._render_count % 50 == 0:
                print(f"PIL frame: {frame_file}")

        if not is_typing and len(FRAME_CACHE) < CACHE_MAX_SIZE:
            FRAME_CACHE[cache_key] = frame_file

# ---------- BUBBLE RENDERING ---------- #
def render_bubble(username, message="", meme_path=None, is_sender=None, is_read=False, typing=False):
    if not hasattr(render_bubble, 'renderer'):
        render_bubble.renderer = WhatsAppRenderer(
            chat_title="BANKA TOUR GROUP",
            chat_avatar="static/images/group.png",
            chat_status="jay, khooi, banka, Paula"
        )
        render_bubble.frame_count = 0
        render_bubble.timeline = []

    is_sender = is_sender if is_sender is not None else (username.strip().lower() == MAIN_USER.lower())

    if typing:
        if is_sender:
            return render_typing_bar_frame(username, message or "", duration=1.5)
        else:
            orig = render_bubble.renderer.message_history.copy()
            render_bubble.renderer.add_message(username, None, typing=True)
            frame = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
            render_bubble.renderer.render_frame(frame, short_wait=True)
            render_bubble.renderer.message_history = orig
            entry = {"frame": os.path.abspath(frame), "duration": 1.5, "typing": True, "username": username}
            render_bubble.timeline.append(entry)
            with open(TIMELINE_FILE, "w") as f: json.dump(render_bubble.timeline, f, indent=2)
            render_bubble.frame_count += 1
            return frame

    render_bubble.renderer.add_message(username, message, meme_path, is_read)
    frame = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
    render_bubble.renderer.render_frame(frame, show_typing_bar=False)

    text_dur = max(2.5, len(message)/10) if message else 0
    meme_dur = 3.0
    if meme_path and os.path.exists(meme_path):
        try:
            with Image.open(meme_path) as img:
                w, h = img.size
            size_factor = (w*h)/(1920*1080)
            aspect = h/max(w,1)
            meme_dur = 2.0 + aspect*1.5 + size_factor*4.0
            meme_dur = max(2.5, min(meme_dur, 6.0))
        except: pass
    duration = max(text_dur, meme_dur) if meme_path else text_dur

    entry = {
        "frame": os.path.abspath(frame),
        "duration": round(duration, 3),
        "is_sender": is_sender,
        "username": username,
        "text": message,
        "is_meme": bool(meme_path),
        "typing": False
    }
    if meme_path and os.path.exists(meme_path):
        info = encode_meme(meme_path)
        if info:
            entry.update({"meme_type": info["meme_type"], "meme_b64": info["meme"], "mime": info["mime"]})

    render_bubble.timeline.append(entry)
    with open(TIMELINE_FILE, "w") as f: json.dump(render_bubble.timeline, f, indent=2)
    render_bubble.frame_count += 1
    return frame

def render_meme(username, meme_path):
    return render_bubble(username, "", meme_path=meme_path)

def render_typing_bar_frame(username, upcoming_text="", frame_path=None, duration=None, is_character_typing=True):
    if not hasattr(render_bubble, 'renderer'):
        render_bubble.renderer = WhatsAppRenderer(...)
        render_bubble.frame_count = 0
        render_bubble.timeline = []

    if username.strip().lower() != MAIN_USER.lower():
        return render_typing_bubble(username)

    frame_path = frame_path or os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
    orig = render_bubble.renderer.message_history.copy()
    render_bubble.renderer.render_frame(frame_path, show_typing_bar=True, typing_user=username, upcoming_text=upcoming_text, short_wait=True)
    render_bubble.renderer.message_history = orig

    frame_duration = 0.4 if (duration is None and is_character_typing and not upcoming_text.endswith('|')) else 0.8
    frame_duration = duration or frame_duration

    should_play_sound = is_character_typing and upcoming_text.endswith('|')
    if not upcoming_text.endswith('|') and upcoming_text.strip():
        should_play_sound = False

    entry = {
        "frame": os.path.abspath(frame_path),
        "duration": frame_duration,
        "typing_bar": True,
        "upcoming_text": upcoming_text,
        "sound": should_play_sound
    }
    render_bubble.timeline.append(entry)
    with open(TIMELINE_FILE, "w") as f: json.dump(render_bubble.timeline, f, indent=2)
    render_bubble.frame_count += 1
    return frame_path

def generate_beluga_typing_sequence(text):
    sequence = []
    SPEED = 0.5
    def speed(char):
        if char in ".,!?": return random.uniform(0.12, 0.25) * SPEED
        if char == " ": return random.uniform(0.06, 0.1) * SPEED
        return random.uniform(0.07, 0.17) * SPEED

    buf = ""
    for i, ch in enumerate(text):
        buf += ch
        active = i < len(text) - 3
        sequence.append((buf + "|", speed(ch), active))
    for _ in range(2):
        sequence.append((text + "|", 0.25, False))
        sequence.append((text, 0.25, False))
    sequence.append((text, 0.8, False))
    return sequence

def render_typing_sequence(username, message):
    seq = generate_beluga_typing_sequence(message)
    for text, dur, sound in seq:
        render_typing_bar_frame(username, text, duration=dur, is_character_typing=sound)
    render_bubble(username, message)

# ---------- CLEANUP ---------- #
def cleanup_resources():
    global HTI
    HTI = None
    FRAME_CACHE.clear()
    gc.collect()
    print("Cleaned up resources")

# ---------- MAIN ---------- #
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python render_bubble.py script.txt")
        sys.exit(1)

    render_bubble.frame_count = 0
    render_bubble.timeline = []
    render_bubble.renderer = WhatsAppRenderer()

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
        if not line: continue
        if line.startswith("MEME:"):
            desc = line[5:].strip()
            path = find_meme(desc) or random.choice([os.path.join("assets/memes/auto", f) for f in os.listdir("assets/memes/auto") if os.path.isfile(os.path.join("assets/memes/auto", f))])
            render_meme(MAIN_USER, path)
        elif line.startswith("[MEME]"):
            parts = line[6:].strip().split(" ", 1)
            user = MAIN_USER if len(parts) == 1 else parts[0]
            path = parts[-1]
            render_meme(user, path)
        elif ":" in line:
            name, msg = line.split(":", 1)
            name, msg = name.strip(), msg.strip()
            is_sender = name.lower() == MAIN_USER.lower()
            if is_sender and msg:
                render_typing_sequence(name, msg)
            else:
                render_bubble(name, msg, is_sender=is_sender)

    print(f"Rendered {render_bubble.frame_count} frames")
    cleanup_resources()
