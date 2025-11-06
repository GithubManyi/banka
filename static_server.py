import os
from pathlib import Path

def get_static_path(filename=None):
    """Get absolute path for static files that works on Railway"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    if filename:
        static_path = os.path.join(base_dir, 'static', filename)
        
        # If file doesn't exist in static, check in current directory (for Railway)
        if not os.path.exists(static_path):
            # Try relative to current file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            static_path = os.path.join(current_dir, 'static', filename)
        
        return static_path
    else:
        # Return just the static directory path
        static_dir = os.path.join(base_dir, 'static')
        if not os.path.exists(static_dir):
            static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
        return static_dir

def get_avatar_path(username):
    """Get avatar path that works on Railway - FIXED VERSION"""
    if not username:
        return get_static_path('images/contact.png')
    
    # Clean username
    username_clean = username.strip()
    
    # First check if we have a custom avatar in avatars directory
    avatar_dir = os.path.join(get_static_path(), 'avatars')
    possible_names = [
        f"{username_clean}.png",
        f"{username_clean}.jpg", 
        f"{username_clean}.jpeg",
        f"{username_clean.replace(' ', '_')}.png",
        f"{username_clean.replace(' ', '_')}.jpg",
    ]
    
    for filename in possible_names:
        avatar_path = os.path.join(avatar_dir, filename)
        if os.path.exists(avatar_path):
            return avatar_path
    
    # Fallback to default avatars in images directory
    default_avatars = ['jay.png', 'khooi.png', 'banka.png', 'alex.png', 'shiro.png', 'brian.png', 'paula.png']
    images_dir = os.path.join(get_static_path(), 'images', 'avatars')
    
    for avatar in default_avatars:
        avatar_path = os.path.join(images_dir, avatar)
        if os.path.exists(avatar_path):
            return avatar_path
    
    # Ultimate fallback - contact.png
    contact_path = get_static_path('images/contact.png')
    if os.path.exists(contact_path):
        return contact_path
    
    # Last resort - return path even if it doesn't exist
    return contact_path

def get_frames_path(filename=None):
    """Get frames directory path"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    frames_dir = os.path.join(base_dir, 'frames')
    
    if filename:
        return os.path.join(frames_dir, filename)
    return frames_dir

def get_assets_path(filename=None):
    """Get assets directory path"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assets_dir = os.path.join(base_dir, 'assets')
    
    if filename:
        return os.path.join(assets_dir, filename)
    return assets_dir

# Railway-compatible file serving through Gradio
def serve_static_file(filename):
    """Serve static files directly (for use with Gradio)"""
    static_path = get_static_path(filename)
    if os.path.exists(static_path):
        return static_path
    return None

def serve_frame_file(filename):
    """Serve frame files directly (for use with Gradio)"""
    frame_path = get_frames_path(filename)
    if os.path.exists(frame_path):
        return frame_path
    return None

# Create necessary directories
def ensure_directories():
    """Ensure all necessary directories exist"""
    directories = [
        get_static_path(),
        os.path.join(get_static_path(), 'avatars'),
        os.path.join(get_static_path(), 'images'),
        os.path.join(get_static_path(), 'audio'),
        get_frames_path(),
        get_assets_path()
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
    
    # Create default contact.png if it doesn't exist
    contact_path = get_static_path('images/contact.png')
    if not os.path.exists(contact_path):
        try:
            from PIL import Image, ImageDraw
            img = Image.new('RGB', (200, 200), color='lightblue')
            draw = ImageDraw.Draw(img)
            draw.ellipse([20, 20, 180, 180], fill='blue', outline='darkblue')
            # Create simple smiley face
            draw.arc([50, 60, 150, 120], start=0, end=180, fill='white', width=8)
            draw.ellipse([70, 80, 90, 100], fill='white')
            draw.ellipse([110, 80, 130, 100], fill='white')
            
            os.makedirs(os.path.dirname(contact_path), exist_ok=True)
            img.save(contact_path, 'PNG')
            print("✅ Created default contact avatar")
        except ImportError:
            # Create empty file as fallback
            os.makedirs(os.path.dirname(contact_path), exist_ok=True)
            open(contact_path, 'a').close()
            print("⚠️ PIL not available, created placeholder avatar file")
        except Exception as e:
            print(f"⚠️ Could not create default avatar: {e}")

# Initialize directories when module loads
ensure_directories()
