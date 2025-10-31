# backend/avatar_handler.py
import os
import shutil
from PIL import Image, ImageDraw, ImageFont
import hashlib
import colorsys


# Use static/images/ so it matches index.html references
AVATAR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "images")
os.makedirs(AVATAR_DIR, exist_ok=True)


def get_font(size):
    font_paths = [
        r"C:\Windows\Fonts\segoeuib.ttf",   # Segoe UI Bold
        r"C:\Windows\Fonts\arialbd.ttf",    # Arial Bold
        r"C:\Windows\Fonts\verdanab.ttf"    # Verdana Bold
    ]
    for path in font_paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()  # fallback if none found


def name_to_color(username: str) -> str:
    """Deterministic bright color for avatar backgrounds."""
    h = hashlib.md5(username.strip().lower().encode("utf-8")).hexdigest()
    n = int(h[:8], 16)
    hue = (n * 137) % 360
    saturation = 0.65
    lightness = 0.55
    r, g, b = colorsys.hls_to_rgb(hue / 360, lightness, saturation)
    return (int(r * 255), int(g * 255), int(b * 255))


def get_initials(name: str) -> str:
    """Return initials like WhatsApp: J or JD."""
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[1][0]).upper()

def get_avatar(name, size=128):
    """Railway-compatible avatar path resolver"""
    safe_name = name.lower().replace(" ", "_")
    
    # Try multiple possible locations for existing avatars
    possible_paths = [
        os.path.join(AVATAR_DIR, f"{safe_name}.png"),
        os.path.join(AVATAR_DIR, f"{safe_name}.jpg"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "avatars", f"{safe_name}.png"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "avatars", f"{safe_name}.jpg"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "images", "avatars", f"{safe_name}.png"),
    ]
    
    # Check if avatar already exists in any location
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    # If avatar doesn't exist, create it in the main AVATAR_DIR
    filename = f"{safe_name}.png"
    filepath = os.path.join(AVATAR_DIR, filename)

    # Create the avatar (your existing creation code)
    initials = get_initials(name)
    bg_color = name_to_color(name)

    # --- Create square canvas ---
    img = Image.new("RGB", (size, size), color=bg_color)
    mask = Image.new("L", (size, size), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse((0, 0, size, size), fill=255)

    draw = ImageDraw.Draw(img)

    # --- WhatsApp-like font (bold, centered) ---
    font = get_font(size // 2)

    bbox = draw.textbbox((0, 0), initials, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    # Adjust with bbox offsets so text is truly centered
    x = (size - text_w) / 2 - bbox[0]
    y = (size - text_h) / 2 - bbox[1]

    draw.text((x, y), initials, fill=(255, 255, 255), font=font)

    # --- Apply circular mask ---
    final_img = Image.new("RGB", (size, size), (0, 0, 0))
    final_img.paste(img, (0, 0), mask)
    final_img.save(filepath, format="PNG")

    return filepath



# def get_avatar(name, color="#496d89", size=128):
#     """
#     Returns path to avatar image for given name.
#     If avatar doesn't exist, creates one with initials.
#     """
#     safe_name = name.lower().replace(" ", "_")
#     filename = f"{safe_name}.png"
#     filepath = os.path.join(AVATAR_DIR, filename)

#     if not os.path.exists(filepath):
#         initials = "".join([part[0].upper() for part in name.split() if part]) or "?"
#         img = Image.new("RGB", (size, size), color=color)
#         draw = ImageDraw.Draw(img)

#         # Try multiple fonts
#         try:
#             font = ImageFont.truetype("arial.ttf", size // 2)
#         except:
#             try:
#                 font = ImageFont.truetype("DejaVuSans-Bold.ttf", size // 2)
#             except:
#                 font = ImageFont.load_default()

#         # Center text using textbbox
#         bbox = draw.textbbox((0, 0), initials, font=font)
#         text_w = bbox[2] - bbox[0]
#         text_h = bbox[3] - bbox[1]

#         draw.text(
#             ((size - text_w) / 2, (size - text_h) / 2),
#             initials,
#             fill=(255, 255, 255),
#             font=font
#         )

#         img.save(filepath, format="PNG")

#     return filepath

def save_uploaded_avatar(file_path, name, size=128):
    """
    Saves an uploaded avatar image to the avatars directory,
    overwriting any existing avatar for the given name.
    Auto-resizes to `size` so it matches layout.
    """
    ext = os.path.splitext(file_path)[1].lower()
    safe_name = name.lower().replace(" ", "_")
    filename = f"{safe_name}.png"  # always save as PNG
    save_path = os.path.join(AVATAR_DIR, filename)

    # Open and resize uploaded image
    img = Image.open(file_path).convert("RGB")
    img = img.resize((size, size), Image.LANCZOS)
    img.save(save_path, format="PNG")

    return save_path
