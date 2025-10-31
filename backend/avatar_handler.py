# backend/avatar_handler.py
import os
import shutil
from PIL import Image, ImageDraw, ImageFont
import hashlib
import colorsys

# Railway-compatible avatar directory setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "..", "static")

# Try multiple possible avatar directories for Railway compatibility
possible_avatar_dirs = [
    os.path.join(STATIC_DIR, "images"),  # Original location
    os.path.join(STATIC_DIR, "avatars"), # New location for uploaded avatars
]

# Use the first directory that exists, or create the first one
AVATAR_DIR = None
for dir_path in possible_avatar_dirs:
    if os.path.exists(dir_path):
        AVATAR_DIR = dir_path
        break

if AVATAR_DIR is None:
    # Create the first directory if none exist
    AVATAR_DIR = possible_avatar_dirs[0]
    os.makedirs(AVATAR_DIR, exist_ok=True)

print(f"✅ Using avatar directory: {AVATAR_DIR}")

def get_font(size):
    """Railway-compatible font loader with fallbacks for Linux/Windows"""
    # Windows fonts
    windows_fonts = [
        r"C:\Windows\Fonts\segoeuib.ttf",   # Segoe UI Bold
        r"C:\Windows\Fonts\arialbd.ttf",    # Arial Bold
        r"C:\Windows\Fonts\verdanab.ttf"    # Verdana Bold
    ]
    
    # Linux fonts (common on Railway)
    linux_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ]
    
    # Check Windows fonts first
    for path in windows_fonts:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    
    # Check Linux fonts
    for path in linux_fonts:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    
    # Ultimate fallback
    try:
        return ImageFont.truetype("arial.ttf", size)
    except:
        return ImageFont.load_default()

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
    if not name or not name.strip():
        name = "Unknown"
    
    safe_name = name.lower().replace(" ", "_")
    
    # Try multiple possible locations for existing avatars
    possible_paths = [
        # Current avatar directory
        os.path.join(AVATAR_DIR, f"{safe_name}.png"),
        os.path.join(AVATAR_DIR, f"{safe_name}.jpg"),
        # Static/avatars directory
        os.path.join(STATIC_DIR, "avatars", f"{safe_name}.png"),
        os.path.join(STATIC_DIR, "avatars", f"{safe_name}.jpg"),
        # Static/images directory (legacy)
        os.path.join(STATIC_DIR, "images", f"{safe_name}.png"),
        os.path.join(STATIC_DIR, "images", f"{safe_name}.jpg"),
        # Static/images/avatars subdirectory
        os.path.join(STATIC_DIR, "images", "avatars", f"{safe_name}.png"),
        os.path.join(STATIC_DIR, "images", "avatars", f"{safe_name}.jpg"),
    ]
    
    # Check if avatar already exists in any location
    for path in possible_paths:
        if os.path.exists(path):
            print(f"✅ Found existing avatar for {name}: {path}")
            return path
    
    # If avatar doesn't exist, create it in the main AVATAR_DIR
    filename = f"{safe_name}.png"
    filepath = os.path.join(AVATAR_DIR, filename)
    
    print(f"🔄 Creating new avatar for {name} at: {filepath}")

    try:
        # Create the avatar
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
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        final_img.save(filepath, format="PNG")
        
        print(f"✅ Successfully created avatar for {name} at: {filepath}")
        return filepath
        
    except Exception as e:
        print(f"❌ Error creating avatar for {name}: {e}")
        # Fallback to default avatar
        fallback_path = os.path.join(STATIC_DIR, "images", "contact.png")
        if os.path.exists(fallback_path):
            return fallback_path
        else:
            # Ultimate fallback - create a simple colored circle
            try:
                fallback_img = Image.new("RGB", (size, size), color=(100, 100, 100))
                fallback_img.save(filepath, format="PNG")
                return filepath
            except:
                # If all else fails, return any path that might work
                return filepath

def save_uploaded_avatar(file_path, name, size=128):
    """
    Railway-compatible avatar upload handler.
    Saves uploaded avatar to multiple locations for redundancy.
    """
    if not file_path or not name:
        print("⚠️ No file path or name provided for avatar upload")
        return get_avatar(name, size)  # Return generated avatar as fallback
    
    safe_name = name.lower().replace(" ", "_")
    filename = f"{safe_name}.png"  # always save as PNG
    
    # Try to save to multiple locations for redundancy
    possible_save_paths = [
        os.path.join(AVATAR_DIR, filename),
        os.path.join(STATIC_DIR, "avatars", filename),
        os.path.join(STATIC_DIR, "images", filename),
    ]
    
    saved_path = None
    
    try:
        # Open and resize uploaded image once
        img = Image.open(file_path).convert("RGB")
        img = img.resize((size, size), Image.LANCZOS)
        
        for save_path in possible_save_paths:
            try:
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                img.save(save_path, format="PNG")
                
                # Verify the file was saved
                if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                    saved_path = save_path
                    print(f"✅ Successfully saved uploaded avatar to: {save_path}")
                    break  # Stop after first successful save
                else:
                    print(f"⚠️ Avatar save verification failed for: {save_path}")
                    
            except Exception as e:
                print(f"⚠️ Could not save avatar to {save_path}: {e}")
                continue
        
        if saved_path:
            return saved_path
        else:
            print("❌ Failed to save uploaded avatar to any location, using generated avatar")
            return get_avatar(name, size)  # Fallback to generated avatar
            
    except Exception as e:
        print(f"❌ Error processing uploaded avatar for {name}: {e}")
        return get_avatar(name, size)  # Fallback to generated avatar

# Legacy function alias for compatibility
def get_avatar_path(username):
    """Alias for get_avatar for backward compatibility"""
    return get_avatar(username)

# Test function
def test_avatar_system():
    """Test the avatar system"""
    print("🧪 Testing avatar system...")
    
    # Test getting avatars for common names
    test_names = ["Banka", "Jay", "Khooi", "Test User"]
    
    for name in test_names:
        try:
            avatar_path = get_avatar(name)
            exists = os.path.exists(avatar_path)
            print(f"   {name}: {avatar_path} - {'✅ EXISTS' if exists else '❌ MISSING'}")
        except Exception as e:
            print(f"   {name}: ❌ ERROR - {e}")
    
    print("✅ Avatar system test complete")

if __name__ == "__main__":
    test_avatar_system()
