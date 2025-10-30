import os
import sys
import subprocess

# ===== FFMPEG INSTALLATION - ADD THIS AT THE VERY TOP =====
def install_ffmpeg():
    """Install ffmpeg if not available"""
    print("🔧 Checking for ffmpeg...")
    
    # First check if ffmpeg exists
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ ffmpeg is already installed")
            return True
    except:
        pass
    
    # Try different installation methods
    print("📦 Installing ffmpeg...")
    
    methods = [
        # Method 1: apt-get
        ["apt-get", "update", "-y"],
        ["apt-get", "install", "-y", "ffmpeg"],
        
        # Method 2: Download static binary
        ["wget", "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"],
        ["tar", "-xf", "ffmpeg-release-amd64-static.tar.xz"],
        ["cp", "ffmpeg-*-amd64-static/ffmpeg", "/usr/local/bin/"],
        ["cp", "ffmpeg-*-amd64-static/ffprobe", "/usr/local/bin/"],
    ]
    
    for cmd in methods:
        try:
            print(f"🔄 Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"⚠️ Command failed: {' '.join(cmd)}")
        except Exception as e:
            print(f"⚠️ Error running command: {e}")
    
    # Final check
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ ffmpeg installed successfully!")
            return True
        else:
            print("❌ ffmpeg installation failed")
            return False
    except:
        print("❌ ffmpeg not found after installation attempts")
        return False

# Install ffmpeg
if not install_ffmpeg():
    print("❌ CRITICAL: Cannot continue without ffmpeg")
    sys.exit(1)
# ===== END FFMPEG INSTALLATION =====


import os
from backend.render_bubble import WhatsAppRenderer  # Import the class now
from generate_video import build_video_from_timeline
from generate_video import build_video_from_timeline
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


MAIN_USER = "Banka"

def process_script(script_file):
    """Parse script with error handling"""
    messages = []
    try:
        with open(script_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                    
                if ":" not in line:
                    print(f"⚠️ Line {line_num} skipped (missing ':'): {line[:20]}...")
                    continue
                    
                user, msg = line.split(":", 1)
                messages.append({
                    "user": user.strip(),
                    "text": msg.strip(),
                    "is_sender": user.strip().lower() != MAIN_USER.lower()

                })  
    except Exception as e:
        print(f"❌ Script Error: {str(e)}")
    return messages

def calculate_duration(text):
    """Beluga-style dynamic timing"""
    words = len(text.split())
    return min(0.8 + (words * 0.15), 3.0)

def create_frames(script_path, output_dir):
    """Generate frames with WhatsApp-like stacking and Beluga effects"""
    try:
        os.makedirs(output_dir, exist_ok=True)
        print(f"✅ Frame directory: {output_dir}")

        for f in os.listdir(output_dir):
            if f.startswith("frame_") and f.endswith(".png"):
                os.remove(os.path.join(output_dir, f))
        print("🧹 Cleared previous frames")

        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Missing script: {script_path}")

        messages = process_script(script_path)
        if not messages:
            raise ValueError("Script contains no valid messages")
        print(f"📜 Processing {len(messages)} messages")

        frame_count = 0
        renderer = WhatsAppRenderer()  # Create the renderer instance
        
        for i, msg in enumerate(messages):
            try:
                # Add message to renderer
                renderer.add_message(
                    username=msg["user"],
                    message=msg["text"],
                    is_sender=msg["is_sender"]
                )
                
                # Calculate duration and determine frame count
                duration = calculate_duration(msg["text"])
                frames_needed = max(1, int(duration * 12))

                # Render frame using Selenium HTML/CSS pipeline
                frame_file = os.path.join(output_dir, f"frame_{frame_count:04d}.png")
                renderer.render_frame(frame_file)

                # Duplicate frame to maintain duration
                for _ in range(frames_needed):
                    dup_file = os.path.join(output_dir, f"frame_{frame_count:04d}.png")
                    # Copy the rendered frame to simulate multiple frames for timing
                    os.system(f'copy "{frame_file}" "{dup_file}" >nul')
                    frame_count += 1

                print(f"🖼 Created {frames_needed} frames for: {msg['text'][:30]}...")
                        
            except Exception as e:
                print(f"⚠️ Message {i+1} failed: {str(e)}")
                continue

        if frame_count == 0:
            raise ValueError("No frames generated - check script and images")
            
        print(f"🎉 Generated {frame_count} frames with WhatsApp stacking")
        return True

    except Exception as e:
        print(f"❌ Frame Generation Failed: {str(e)}")
        return False
    

if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    

    
    REQUIRED_PATHS = [
        os.path.join(BASE_DIR, "static", "images"),
        os.path.join(BASE_DIR, "script.txt")
    ]
    
    for path in REQUIRED_PATHS:
        if not os.path.exists(path):
            print(f"❌ Missing required path: {path}")
            exit(1)

    if create_frames(
        script_path=os.path.join(BASE_DIR, "script.txt"),
        output_dir=os.path.join(BASE_DIR, "frames")
    ):
    
        build_video_from_timeline(
            bg_audio=os.path.join(BASE_DIR, "static", "audio", "bg_music.mp3"),
            send_audio=os.path.join(BASE_DIR, "static", "audio", "send_ping.mp3"),
            recv_audio=os.path.join(BASE_DIR, "static", "audio", "recv_ping.mp3")
)

