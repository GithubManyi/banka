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
# Reduce logging verbosity
logging.getLogger('html2image').setLevel(logging.WARNING)
logging.getLogger('PIL').setLevel(logging.WARNING)
logging.getLogger('selenium').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
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
MAIN_USER = "Banka" # right-side sender
W, H = 1904, 934 # match video size
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
    """Get the correct avatar path for a character - SELF CONTAINED"""
    characters = load_characters()
 
    # Clean username
    username_clean = username.strip()
 
    # 1) Check character JSON first
    if username_clean in characters:
        avatar_path = characters[username_clean].get("avatar", "")
        if avatar_path:
            # Convert relative path to absolute path
            if not os.path.isabs(avatar_path):
                full_path = os.path.join(BASE_DIR, avatar_path)
            else:
                full_path = avatar_path
         
            if os.path.exists(full_path):
                print(f"✅ Found avatar for {username_clean}: {full_path}")
                return full_path
            else:
                print(f"⚠️ Avatar path in JSON doesn't exist: {full_path}")
 
    # 2) Check avatars directory directly
    avatars_dir = os.path.join(BASE_DIR, "static", "avatars")
    if os.path.exists(avatars_dir):
        # Try different filename variations
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
                print(f"✅ Found avatar in avatars dir: {possible_path}")
                return possible_path
 
    # 3) No avatar found, return empty string to trigger initial generation
    print(f"⚠️ No avatar found for {username_clean}, will generate initial")
    return ""
def encode_avatar_for_html(avatar_path):
    """Convert avatar image to base64 for HTML display - SELF CONTAINED"""
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
# ---------- PERFORMANCE OPTIMIZATIONS ---------- #
# Global HTML2Image instance
HTI = None
FRAME_CACHE = {}
CACHE_MAX_SIZE = 100
def get_html2image():
    """Ultra-fast Railway-optimized HTML2Image with emoji support"""
    global HTI
    if HTI is None:
        try:
            # STRATEGY: Try multiple paths with Railway priority
            chromium_path = None
           
            # 1. First try Railway environment variable (fastest)
            railway_path = os.environ.get('CHROMIUM_PATH')
            if railway_path and os.path.exists(railway_path):
                chromium_path = railway_path
                print(f"🚀 Using Railway Chromium: {chromium_path}")
           
            # 2. Try common system paths (fast)
            if not chromium_path:
                import shutil
                chromium_path = (
                    shutil.which("chromium") or
                    shutil.which("chromium-browser") or
                    shutil.which("google-chrome") or
                    "/usr/bin/chromium" # Railway default
                )
           
            if chromium_path:
                print(f"✅ Using Chromium: {chromium_path}")
                # ULTRA-FAST FLAGS (optimized for Railway)
                chrome_flags = [
                    "--headless=new", # ✅ New headless (much faster)
                    "--no-sandbox", # ✅ Required for Docker
                    "--disable-gpu", # ✅ No GPU in containers
                    "--disable-dev-shm-usage", # ✅ Prevent memory issues
                    "--disable-software-rasterizer", # ✅ Faster rendering
                    "--disable-webgl", # ✅ Not needed for 2D
                    "--no-first-run", # ✅ Skip initial setup
                    "--disable-translate", # ✅ No translation popups
                    "--disable-extensions", # ✅ No extensions needed
                    "--disable-background-networking", # ✅ Reduce network calls
                    "--disable-sync", # ✅ No sync services
                    "--disable-default-apps", # ✅ No default apps
                    "--mute-audio", # ✅ No audio needed
                    "--no-default-browser-check", # ✅ Skip browser check
                    "--disable-component-extensions-with-background-pages", # ✅ Reduce processes
                    "--disable-features=TranslateUI,BlinkGenPropertyTrees", # ✅ Optimize rendering
                    "--disable-ipc-flooding-protection", # ✅ Better performance
                    "--disable-renderer-backgrounding", # ✅ Keep renderers active
                    "--disable-background-timer-throttling", # ✅ Better performance
                    "--font-render-hinting=none", # ✅ Better emoji rendering
                    "--force-color-profile=srgb", # ✅ Consistent colors
                    "--enable-font-antialiasing", # ✅ Smoother text
                ]
                HTI = html2image.Html2Image(
                    browser_executable=chromium_path,
                    custom_flags=chrome_flags,
                    output_path=FRAMES_DIR,
                    size=(1920, 1080) # ✅ Pre-set size for faster rendering
                )
                print("🚀 Ultra-fast Railway Renderer Ready (Emoji Support)")
                # ✅ OPTIMIZED WARM-UP: Minimal but effective
                try:
                    # Fast warm-up with basic HTML
                    warmup_html = "<html><body style='background:#0b141a'></body></html>"
                    HTI.screenshot(html=warmup_html, save_as="__warmup.png")
                   
                    # Quick emoji test (only log if it fails)
                    emoji_test_html = """
                    <html><body style="background:#0b141a;color:white;font-family:'Noto Color Emoji','Apple Color Emoji',sans-serif;font-size:20px">
                        😀📱
                    </body></html>
                    """
                    HTI.screenshot(html=emoji_test_html, save_as="__emojitest.png")
                    print("✅ Warm-up completed with emoji support")
                   
                except Exception as warmup_error:
                    print(f"⚠️ Warm-up had minor issue (continuing anyway): {warmup_error}")
            else:
                print("⚠️ Chromium not found — fallback to PIL mode")
                HTI = None
        except Exception as e:
            print(f"❌ HTML2Image init error: {e}")
            # Don't give up completely - fallback will handle it
            HTI = None
    return HTI
def cleanup_resources():
    """Clean up all resources when done"""
    global HTI
    if HTI:
        HTI = None
    FRAME_CACHE.clear()
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
        "meme_type": ext, # ".jpg", ".png", ".mp4", etc.
        "mime": mime # "image/png", "image/jpeg", "video/mp4"
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
    base_duration = 1.5 # Minimum typing time
    char_duration = 0.08 # Per character typing speed
 
    typing_time = base_duration + (chars * char_duration)
    return min(typing_time, 4.0) # Cap at 4 seconds max
def debug_timeline_entries():
    """Debug function to check what's in the timeline"""
    if hasattr(render_bubble, 'timeline') and render_bubble.timeline:
        print("🔍 ===== TIMELINE DEBUG =====")
        typing_entries = [e for e in render_bubble.timeline if e.get('typing_bar')]
        print(f"🔍 Found {len(typing_entries)} typing bar entries in timeline")
     
        for i, entry in enumerate(typing_entries[-10:]): # Show last 10 entries
            print(f"🔍 Entry {i}: text='{entry.get('upcoming_text')}' sound={entry.get('sound')} duration={entry.get('duration')}")
# ---------- VIDEO HELPERS ---------- #
def add_still_to_concat(concat_lines, frame_file, duration):
    """Add a still frame to concat file for video generation"""
    safe_path = frame_file.replace("\\", "/")
    concat_lines.append(f"file '{safe_path}'")
    concat_lines.append(f"duration {float(duration):.3f}")
def handle_meme_image(meme_path, output_path, duration=1.0, fps=25):
    """Handle meme image processing for video generation"""
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
# ---------- EMOJI FONT SUPPORT ---------- #
def install_emoji_fonts():
    """Try to install or use emoji-supporting fonts"""
    try:
        # List of emoji-supporting fonts to try
        emoji_fonts = [
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", # Good unicode support
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", # Good unicode support
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf", # Best for emoji
            "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", # Color emoji
            "/System/Library/Fonts/Apple Color Emoji.ttc", # macOS
            "C:/Windows/Fonts/segoeuiemoji.ttf", # Windows
        ]
       
        available_fonts = []
        for font_path in emoji_fonts:
            if os.path.exists(font_path):
                available_fonts.append(font_path)
                print(f"✅ Found emoji font: {font_path}")
       
        return available_fonts
    except Exception as e:
        print(f"⚠️ Error checking emoji fonts: {e}")
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
        # Initialize emoji fonts
        self._emoji_fonts = install_emoji_fonts()
        self._emoji_fonts_checked = True
 
    def add_message(self, username, message, meme_path=None, is_read=False, typing=False):
        """COMPLETE METHOD - Add message to history with FIXED AVATAR SYSTEM"""
        try:
            ts = datetime.now().strftime("%-I:%M %p").lower()
        except ValueError:
            ts = datetime.now().strftime("%#I:%M %p").lower()
 
        color = name_to_color(username)
 
        # --- FIXED AVATAR RESOLUTION SYSTEM ---
        avatar_path = get_character_avatar_path(username)
     
        # Encode avatar or generate initial if not found
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
                print(f"⚠️ Failed to encode avatar {avatar_path}: {e}")
                # Fall through to generate initial
                avatar_data = None
                mime = None
     
        else:
            # Generate initial avatar with LARGER FONT SIZES and BETTER CENTERING
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
           
            # Create a larger image for better quality
            img_size = 200 # Increased from 128 for better quality
            img = Image.new('RGB', (img_size, img_size), color=(r, g, b))
            draw = ImageDraw.Draw(img)
           
            # ✅ FIXED: BETTER FONT SIZES AND CENTERING
            if len(initial) == 1:
                font_size = 100 # Bigger for single letters
            else:
                font_size = 80 # Bigger for two letters
           
            try:
                # Try multiple font paths for better emoji support
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
                        print(f"✅ Using font: {font_path}")
                        break
                    except Exception as e:
                        continue
               
                if font is None:
                    # Final fallback to default font
                    font = ImageFont.load_default()
                    print("⚠️ Using default font")
                   
            except Exception as font_error:
                print(f"⚠️ Font loading error for {username}: {font_error}")
                font = ImageFont.load_default()
           
            # ✅ FIXED: PERFECT CENTERING
            if font:
                try:
                    # Get text bounding box
                    bbox = draw.textbbox((0, 0), initial, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                   
                    # Perfect center calculation
                    x = (img_size - text_width) / 2
                    y = (img_size - text_height) / 2 - bbox[1] # Adjust for baseline
                   
                    # Draw the text with subtle outline for better visibility
                    outline_width = max(2, img_size // 80)
                    for x_offset in [-outline_width, 0, outline_width]:
                        for y_offset in [-outline_width, 0, outline_width]:
                            if x_offset != 0 or y_offset != 0:
                                draw.text((x + x_offset, y + y_offset), initial, fill=(0, 0, 0, 128), font=font)
                   
                    # Draw the main text
                    draw.text((x, y), initial, fill=(255, 255, 255), font=font)
                   
                    print(f"✅ Perfectly centered avatar for {username}: '{initial}' at ({x:.1f}, {y:.1f})")
                   
                except Exception as draw_error:
                    print(f"⚠️ Error drawing text for {username}: {draw_error}")
                    # Fallback: simple centered text
                    x = img_size // 4
                    y = img_size // 4
                    draw.text((x, y), initial, fill=(255, 255, 255), font=font)
            else:
                # Fallback positioning
                x = img_size // 6
                y = img_size // 4
                draw.text((x, y), initial, fill=(255, 255, 255))
           
            # Resize to standard avatar size for consistency
            img = img.resize((128, 128), Image.Resampling.LANCZOS)
           
            buf = BytesIO()
            img.save(buf, format="PNG")
            avatar_data = base64.b64encode(buf.getvalue()).decode("utf-8")
            mime = "image/png"
            print(f"✅ Generated perfectly centered avatar for {username}")
 
        # --- MEME HANDLING ---
        meme_data = None
        if meme_path and os.path.exists(meme_path):
            try:
                meme_data = encode_meme(meme_path)
            except Exception as e:
                print(f"⚠️ Meme encode failed: {e}")
 
        # --- BUILD MESSAGE ENTRY ---
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
        """
        Optimized frame rendering with HTML2Image fallback to PIL
        """
        start_time = time.time()
        self._render_count += 1
     
        # Check cache first
        is_typing_frame = show_typing_bar and upcoming_text
        cache_key = get_frame_cache_key(self.message_history, show_typing_bar, typing_user, upcoming_text)
     
        if not is_typing_frame and cache_key in FRAME_CACHE and os.path.exists(FRAME_CACHE[cache_key]):
            cached_frame = FRAME_CACHE[cache_key]
            if os.path.exists(cached_frame):
                import shutil
                shutil.copy2(cached_frame, frame_file)
                # REDUCED LOGGING: Only log every 50th cache hit
                if self._render_count % 50 == 0:
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
            static_path="/app/static", # ✅ critical for headless chrome
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
            # Get HTML2Image with optimized flags
            hti = get_html2image()
            if hti is None:
                raise Exception("HTML2Image not available")
         
            # Save HTML to temporary file
            temp_html = os.path.join(FRAMES_DIR, f"temp_{render_bubble.frame_count}.html")
            with open(temp_html, "w", encoding="utf-8") as f:
                f.write(rendered_html)
         
            # Render to image with error handling
            try:
                hti.screenshot(
                    html_file=temp_html,
                    save_as=os.path.basename(frame_file),
                    size=(1920, 1080)
                )
            except Exception as render_error:
                print(f"⚠️ HTML2Image render failed: {render_error}")
                raise render_error
         
            # Move the screenshot to the correct location
            generated_file = os.path.join(os.getcwd(), os.path.basename(frame_file))
            if os.path.exists(generated_file):
                os.rename(generated_file, frame_file)
                # REDUCED LOGGING: Only log every 50th frame
                if self._render_count % 50 == 0:
                    print(f"✅ Rendered frame {self._render_count}: {frame_file}")
            else:
                # If file wasn't generated, fall back to PIL
                raise Exception("HTML2Image didn't generate output file")
         
            # Clean up temp HTML file
            if os.path.exists(temp_html):
                os.remove(temp_html)
             
        except Exception as e:
            # REDUCED LOGGING: Only log HTML2Image failures, not every fallback
            if self._render_count % 10 == 0:
                print(f"❌ HTML2Image failed: {e}")
                print("🔄 Falling back to PIL rendering...")
         
            # PIL FALLBACK - Compatible with your HTML structure
            from PIL import Image, ImageDraw, ImageFont
           
            # Create background matching your HTML theme
            img = Image.new('RGB', (1920, 1080), color=(11, 20, 26)) # --app-bg: #0b141a
            draw = ImageDraw.Draw(img)
           
            try:
                # Try to use emoji-supporting fonts first
                font_large = None
                font_medium = None
                font_small = None
               
                if self._emoji_fonts:
                    for font_path in self._emoji_fonts:
                        try:
                            # Match your HTML font sizes (scaled for PIL)
                            font_large = ImageFont.truetype(font_path, 36) # Matches your 36px name
                            font_medium = ImageFont.truetype(font_path, 30) # Matches your 30px text
                            font_small = ImageFont.truetype(font_path, 20) # Matches your 20px timestamp
                            print(f"✅ Using emoji font: {os.path.basename(font_path)}")
                            break
                        except:
                            continue
               
                # Fallback to system fonts
                if font_large is None:
                    try:
                        font_large = ImageFont.truetype("Arial", 36)
                        font_medium = ImageFont.truetype("Arial", 30)
                        font_small = ImageFont.truetype("Arial", 20)
                    except:
                        font_large = ImageFont.load_default()
                        font_medium = ImageFont.load_default()
                        font_small = ImageFont.load_default()
           
                # ✅ COMPATIBLE: Match your HTML structure exactly
               
                # 1. Draw topbar (130px high)
                topbar_height = 130
                draw.rectangle([0, 0, 1920, topbar_height], fill=(17, 27, 33)) # --panel-bg: #111b21
               
                # Avatar circle
                avatar_x, avatar_y = 24, 15
                avatar_size = 100
                draw.ellipse([avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size],
                            fill=(42, 57, 66)) # --avatar-bg: #2a3942
               
                # Chat title and status (matching your HTML)
                draw.text((avatar_x + avatar_size + 24, 50),
                          f"💬 {self.chat_title}",
                          fill=(255, 255, 255), font=font_large)
                draw.text((avatar_x + avatar_size + 24, 90),
                          f"👥 {self.chat_status}",
                          fill=(134, 150, 160), font=font_small) # --muted: #8696a0
               
                # 2. Draw chat background with pattern (simplified)
                chat_bg_top = topbar_height
                draw.rectangle([0, chat_bg_top, 1920, 1080], fill=(11, 20, 26)) # --chat-bg: #0b141a
               
                # 3. Draw messages in your HTML-compatible layout
                chat_container_top = chat_bg_top + 32 # Your 32px padding
                chat_container_bottom = 1080 - 30 # Your 30px bottom padding
               
                # Calculate available height for messages
                available_height = chat_container_bottom - chat_container_top
               
                # Reserve space for typing bar if active
                typing_bar_height = 80 if (show_typing_bar and typing_user) else 0
                if typing_bar_height > 0:
                    available_height -= typing_bar_height
               
                # Start from bottom (like your HTML auto-scroll)
                current_y = chat_container_bottom
               
                # Process messages from newest to oldest (bottom to top)
                visible_messages = []
               
                for msg in reversed(filtered_messages):
                    # Estimate message height (matching your bubble sizing)
                    lines = []
                    current_line = ""
                   
                    # Wrap text to match your bubble width (approx 70% of screen)
                    max_chars = 60 # Adjusted for your font size
                    for word in msg['text'].split():
                        test_line = current_line + word + " "
                        if len(test_line) > max_chars:
                            lines.append(current_line)
                            current_line = word + " "
                        else:
                            current_line = test_line
                    if current_line:
                        lines.append(current_line)
                   
                    # Calculate bubble height (matching your CSS)
                    bubble_padding = 28 + 14 # pad-x + pad-y equivalents
                    line_height = 40 # Approximate for your font size
                    message_height = bubble_padding + (len(lines) * line_height) + 40 # + footer space
                   
                    # Check if we have space above
                    if current_y - message_height < chat_container_top:
                        break # No more space
                   
                    visible_messages.append((msg, message_height, lines))
                    current_y -= message_height
               
                # ✅ Draw messages from bottom to top (newest at bottom)
                current_y = chat_container_bottom
               
                for msg, message_height, lines in reversed(visible_messages):
                    # Match your HTML bubble positioning
                    if msg['is_sender']:
                        # Right side (sender) - green
                        bubble_x = 1920 - 500 - 20 # Right-aligned like your CSS
                        bubble_color = (0, 92, 75) # --outgoing: #005c4b
                        avatar_x = bubble_x + 500 - 120 # Avatar on right
                    else:
                        # Left side (receiver) - dark
                        bubble_x = 150 # Left-aligned like your CSS
                        bubble_color = (32, 44, 51) # --incoming: #202c33
                        avatar_x = bubble_x - 144 # Avatar on left (120px + 24px margin)
                   
                    # Draw message bubble
                    bubble_top = current_y - message_height
                    bubble_bottom = current_y
                   
                    # Rounded rectangle bubble
                    draw.rounded_rectangle(
                        [bubble_x, bubble_top, bubble_x + 500, bubble_bottom],
                        radius=18, # --bubble-radius: 18px
                        fill=bubble_color
                    )
                   
                    # Username (only for first in group - simplified)
                    username_y = bubble_top + 14
                    draw.text((bubble_x + 18, username_y),
                             msg['username'],
                             fill=msg['color'], font=font_small)
                   
                    # Message text lines
                    text_y = username_y + 30
                    for line in lines:
                        draw.text((bubble_x + 18, text_y), line,
                                 fill=(233, 237, 239), font=medium) # --text: #e9edef
                        text_y += 40 # line-height equivalent
                   
                    # Timestamp at bottom
                    timestamp_y = bubble_bottom - 30
                    draw.text((bubble_x + 18, timestamp_y),
                             msg['timestamp'],
                             fill=(255, 255, 255, 153), font=font_small) # semi-transparent white
                   
                    # Move up for next message
                    current_y -= message_height
               
                # 4. Draw typing bar if active (matches your HTML)
                if show_typing_bar and typing_user:
                    typing_bar_y = 1080 - 80
                   
                    # Typing bar background
                    draw.rectangle([0, typing_bar_y, 1920, 1080],
                                  fill=(17, 27, 33)) # --panel-bg: #111b21
                   
                    # WhatsApp-style input bar
                    bar_width = 1800
                    bar_x = (1920 - bar_width) // 2
                    draw.rounded_rectangle([bar_x, typing_bar_y + 10, bar_x + bar_width, typing_bar_y + 70],
                                          radius=48, fill=(32, 44, 51)) # --incoming: #202c33
                   
                    # Typing text
                    typing_text = f"⌨️ {typing_user} is typing..."
                    if upcoming_text:
                        preview_text = upcoming_text.replace("|", "")[:30]
                        if len(upcoming_text) > 30:
                            preview_text += "..."
                        typing_text = f"⌨️ {typing_user}: {preview_text}"
                   
                    draw.text((bar_x + 60, typing_bar_y + 25),
                             typing_text,
                             fill=(100, 255, 100), font=font_medium)
                   
                    # Animated dots
                    dots = "." * ((self._render_count // 10) % 4)
                    draw.text((bar_x + 60, typing_bar_y + 50),
                             f"Typing{dots}",
                             fill=(134, 150, 160), font=font_small)
           
            except Exception as pil_error:
                if self._render_count % 10 == 0:
                    print(f"⚠️ Advanced PIL rendering failed: {pil_error}")
                # Ultra simple fallback
                draw.text((100, 100), f"Chat Frame - {len(filtered_messages)} messages", fill=(255, 255, 255))
                if show_typing_bar and typing_user:
                    draw.text((100, 150), f"{typing_user} typing: {upcoming_text}", fill=(100, 255, 100))
           
            img.save(frame_file)
            if self._render_count % 50 == 0:
                print(f"✅ PIL fallback frame {self._render_count}: {frame_file}")
     
        # Cache non-typing frames only
        if not is_typing_frame and len(FRAME_CACHE) < CACHE_MAX_SIZE:
            FRAME_CACHE[cache_key] = frame_file
     
        render_time = time.time() - start_time
        # REDUCED LOGGING: Only log slow renders
        if render_time > 1.0:
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
            # REDUCED LOGGING
            if render_bubble.frame_count % 20 == 0:
                print(f"⌨️ Sender {username} typing - using typing bar instead of bubble")
            return render_typing_bar_frame(username, upcoming_text=message if message else "", duration=1.5)
        else:
            # For receiver - show typing indicator bubble
            # REDUCED LOGGING
            if render_bubble.frame_count % 20 == 0:
                print(f"⌨️ Receiver {username} typing - showing typing bubble")
            original_history = render_bubble.renderer.message_history.copy()
            render_bubble.renderer.add_message(username, None, typing=True)
            frame_file = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
            render_bubble.renderer.render_frame(frame_file, short_wait=True) # Use short wait
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
    # REDUCED LOGGING: Only log every 20th frame
    if render_bubble.frame_count % 20 == 0:
        print(f"✅ Regular frame {render_bubble.frame_count}: {frame_file} ({duration}s)")
    return frame_file
def render_meme(username, meme_path):
    return render_bubble(username, "", meme_path=meme_path)
def render_typing_bubble(username, duration=None, is_sender=None, custom_durations=None):
    custom_durations = custom_durations or {} # ✅ prevents NoneType errors
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
        # REDUCED LOGGING
        if render_bubble.frame_count % 20 == 0:
            print(f"⌨️ Skipping typing bubble for sender {username} - using typing bar instead")
        return render_typing_bar_frame(username, "", duration=1.5)
    # Use the MAIN renderer, but temporarily add typing message
    original_history = render_bubble.renderer.message_history.copy()
 
    # Add typing indicator to main renderer temporarily
    render_bubble.renderer.add_message(username, None, typing=True)
 
    frame_file = os.path.join(FRAMES_DIR, f"frame_{render_bubble.frame_count:04d}.png")
    render_bubble.renderer.render_frame(frame_file, short_wait=True) # Use short wait
 
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
        "typing_sound": False # ✅ FORCE NO SOUND for typing bubbles
    }
    render_bubble.timeline.append(entry)
 
    with open(TIMELINE_FILE, "w", encoding="utf-8") as tf:
        json.dump(render_bubble.timeline, tf, indent=2)
    render_bubble.frame_count += 1
    # REDUCED LOGGING: Only log every 20th typing indicator
    if render_bubble.frame_count % 20 == 0:
        print(f"⌨️ Typing indicator for {username} (duration: {duration}s)")
    return frame_file
def render_typing_bar_frame(username, upcoming_text="", frame_path=None, duration=None, is_character_typing=True):
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
        # REDUCED LOGGING
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
    # SIMPLE duration handling
    if duration is None or duration <= 0:
        if not is_character_typing or upcoming_text.endswith('|'):
            frame_duration = 0.8 # Longer for cursor blinks
        else:
            frame_duration = 0.4 # Shorter for actual typing
    else:
        frame_duration = duration
 
    # ✅ SIMPLIFIED SOUND LOGIC: Continuous sound during active typing
    should_play_sound = is_character_typing
 
    # Check if this is one of the last 3 frames (no cursor, complete text)
    current_text = upcoming_text.replace("|", "").strip()
    is_final_frame = (not upcoming_text.endswith('|') and current_text)
    if is_final_frame:
        should_play_sound = False # No sound in final frames
        # REDUCED LOGGING
        if render_bubble.frame_count % 20 == 0:
            print(f"🎹 FINAL FRAME DETECTED: '{upcoming_text}' - NO SOUND")
    # REDUCED LOGGING: Only log sound info every 50th frame
    if render_bubble.frame_count % 50 == 0:
        print(f"🎹 SIMPLE SOUND: is_typing={is_character_typing} -> sound={should_play_sound}")
    # Generate session ID for continuous sound grouping
    if not hasattr(render_bubble, 'current_typing_session'):
        render_bubble.current_typing_session = None
 
    # Start new session when we begin typing after not typing
    if is_character_typing and not hasattr(render_bubble, 'prev_typing_text'):
        render_bubble.prev_typing_text = ""
 
    current_text = upcoming_text.replace("|", "").strip()
    if is_character_typing and not render_bubble.prev_typing_text and current_text:
        render_bubble.current_typing_session = f"session_{render_bubble.frame_count}"
        # REDUCED LOGGING
        if render_bubble.frame_count % 20 == 0:
            print(f"🎹 🆕 STARTING NEW TYPING SESSION: {render_bubble.current_typing_session}")
 
    # End session when we stop typing
    if not is_character_typing and render_bubble.current_typing_session:
        # REDUCED LOGGING
        if render_bubble.frame_count % 20 == 0:
            print(f"🎹 🛑 ENDING TYPING SESSION: {render_bubble.current_typing_session}")
        render_bubble.current_typing_session = None
    render_bubble.prev_typing_text = current_text
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
    # REDUCED LOGGING: Only log every 20th typing frame
    if render_bubble.frame_count % 20 == 0:
        print(f"🎹 Frame {render_bubble.frame_count}: '{upcoming_text}' - Sound: {should_play_sound}")
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
            sequence.append((text + "|", 0.25, False)) # False = no typing activity (NO SOUND)
            sequence.append((text, 0.25, False)) # False = no typing activity (NO SOUND)
    # CONTROLLED fake typing (1-2 times per video, not per message)
    if not hasattr(render_bubble, 'fake_typing_count'):
        render_bubble.fake_typing_count = 0
        render_bubble.max_fakes_per_video = random.randint(1, 2) # 1-2 fakes total
    if (render_bubble.fake_typing_count < render_bubble.max_fakes_per_video and
        random.random() < 0.4): # 40% chance per message
     
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
        # REDUCED LOGGING
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
            # REDUCED LOGGING
            if random.random() < 0.05:
                print(f"🎹 LAST 3 CHARS: '{ch}' at position {i} - NO SOUND")
         
        sequence.append((buf + "|", typing_speed_for(ch), is_active_typing))
    # Final cursor blinks and stable frame - NO SOUND
    blink_frame(real_message, blinks=2)
    sequence.append((real_message, 0.8, False))
    # REDUCED LOGGING
    print(f"⌨️ Generated {len(sequence)} typing frames for '{real_message[:50]}...'")
 
    return sequence
def render_typing_sequence(username, real_message):
    """
    FIXED: Actually renders the typing sequence frames with sound
    """
    print(f"🎬 Starting typing sequence for '{username}': '{real_message[:50]}...'")
 
    sequence = generate_beluga_typing_sequence(real_message)
 
    rendered_frames = []
    for i, (text, duration, has_sound) in enumerate(sequence):
        # REDUCED LOGGING: Only log every 20th typing frame
        if i % 20 == 0:
            print(f"🎬 Rendering typing frame {i}: '{text}' - duration: {duration}s - sound: {has_sound}")
     
        # Actually render the frame with sound information
        frame_path = render_typing_bar_frame(
            username=username,
            upcoming_text=text,
            duration=duration,
            is_character_typing=has_sound # This controls the sound!
        )
        rendered_frames.append(frame_path)
 
    print(f"🎬 Completed typing sequence: {len(rendered_frames)} frames rendered")
    return rendered_frames
def reset_typing_sessions():
    """Reset typing session tracking - call this when starting a new video"""
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
        print("🔄 Initialized typing session tracking for main script")
        # Your main script execution logic here...
        print(f"✅ Rendered {render_bubble.frame_count} frames from {script_file}")
     
    finally:
        cleanup_resources() 
