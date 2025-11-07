import os
import json
import math
import glob
import shutil
import requests
import base64
from typing import List, Dict, Any, Tuple
from PIL import Image
from backend.meme_injector import inject_random_memes
from backend.render_bubble import add_still_to_concat, handle_meme_image
import subprocess
import shlex
from PIL import Image, ImageDraw, ImageFont
import random

# Add Groq import for AI moral generation
try:
    from groq import Groq
except ImportError:
    print("⚠️ Groq package not available - AI moral generation will use fallback")

# --------------------
# Paths & defaults
# --------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAMES_DIR = os.path.join(BASE_DIR, "frames")
TIMELINE_FILE = os.path.join(FRAMES_DIR, "timeline.json")
BG_TIMELINE_FILE = os.path.join(FRAMES_DIR, "bg_timeline.json")
STATIC_AUDIO = os.path.join(BASE_DIR, "static", "audio")
OUTPUT_VIDEO = os.path.join(BASE_DIR, "output.mp4")
TMP_DIR = os.path.join(BASE_DIR, "tmp_ffmpeg")
os.makedirs(TMP_DIR, exist_ok=True)
DEFAULT_BG = os.path.join(STATIC_AUDIO, "default_bg.mp3")
DEFAULT_SEND = os.path.join(STATIC_AUDIO, "send.mp3")
DEFAULT_RECV = os.path.join(STATIC_AUDIO, "recv.mp3")
FPS = 25 # Target frame rate

# --------------------
# Helper Functions
# --------------------
def debug_audio_generation(delayed_bg_files, delayed_files, final_audio):
    """Debug audio file generation"""
    print("🔊 ===== AUDIO GENERATION DEBUG =====")
    print(f"🔊 Background files: {len(delayed_bg_files)}")
    for i, file in enumerate(delayed_bg_files):
        exists = "✅" if os.path.exists(file) else "❌"
        print(f"🔊 BG {i}: {exists} {os.path.basename(file)}")
   
    print(f"🔊 Sound effect files: {len(delayed_files)}")
    for i, file in enumerate(delayed_files):
        exists = "✅" if os.path.exists(file) else "❌"
        print(f"🔊 SFX {i}: {exists} {os.path.basename(file)}")
   
    print(f"🔊 Final audio path: {final_audio}")
    print(f"🔊 Final audio exists: {os.path.exists(final_audio)}")
   
    # Check if any audio files exist at all
    all_files = delayed_bg_files + delayed_files
    existing_files = [f for f in all_files if os.path.exists(f)]
    print(f"🔊 Total existing audio files: {len(existing_files)}")
   
    return len(existing_files) > 0

def create_silent_audio(duration, output_path):
    """Create a silent audio file of specified duration"""
    try:
        _run(f'ffmpeg -y -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 -t {duration:.3f} -c:a aac "{output_path}"')
        return os.path.exists(output_path)
    except Exception as e:
        print(f"❌ Failed to create silent audio: {e}")
        return False

def debug_typing_timeline_entries(timeline):
    """Debug function to check typing entries in timeline"""
    print("🔍 ===== TYPING TIMELINE ENTRIES DEBUG =====")
   
    typing_entries = []
    for i, entry in enumerate(timeline):
        if entry.get("typing_bar"):
            typing_entries.append((i, entry))
   
    print(f"🔍 Found {len(typing_entries)} typing bar entries in timeline")
   
    if not typing_entries:
        print("❌ No typing bar entries found in timeline!")
        return
   
    # Show first 10 and last 10 entries
    print("🔍 First 10 typing entries:")
    for idx, entry in typing_entries[:10]:
        print(f"🔍 Frame {idx}: text='{entry.get('upcoming_text')}' sound={entry.get('sound')} duration={entry.get('duration')}")
   
    if len(typing_entries) > 20:
        print("🔍 ...")
        print("🔍 Last 10 typing entries:")
        for idx, entry in typing_entries[-10:]:
            print(f"🔍 Frame {idx}: text='{entry.get('upcoming_text')}' sound={entry.get('sound')} duration={entry.get('duration')}")
   
    # Count how many have sound=True
    sound_entries = [e for _, e in typing_entries if e.get('sound')]
    print(f"🔍 Entries with sound=True: {len(sound_entries)}")
   
    if sound_entries:
        print("🔍 Examples with sound=True:")
        for idx, entry in typing_entries:
            if entry.get('sound') and idx < 20:
                print(f"🔍 Frame {idx}: '{entry.get('upcoming_text')}'")

def build_typing_audio_sessions(timeline, typing_sound_master_path, tmp_dir):
    """
    Creates perfectly trimmed typing audio sessions
    """
    os.makedirs(tmp_dir, exist_ok=True)
    sessions = {}
    current_session = None
   
    print(f"🎵 Scanning {len(timeline)} timeline entries for typing sessions...")
   
    # First pass: group typing entries by session_id
    for idx, entry in enumerate(timeline):
        if entry.get("typing_bar") and entry.get("typing_session_id"):
            session_id = entry["typing_session_id"]
            duration = float(entry.get("duration", 0))
           
            if current_session is None or current_session["id"] != session_id:
                # Start new session
                if current_session:
                    sessions[current_session["id"]] = {
                        "start_idx": current_session["start_idx"],
                        "duration": current_session["duration"],
                        "frames": current_session["frames"]
                    }
               
                current_session = {
                    "id": session_id,
                    "start_idx": idx,
                    "duration": duration,
                    "frames": [idx]
                }
                print(f"🎵 Started new session: {session_id} at index {idx}")
            else:
                # Continue current session
                current_session["duration"] += duration
                current_session["frames"].append(idx)
   
    # Don't forget the last session
    if current_session is not None:
        sessions[current_session["id"]] = {
            "start_idx": current_session["start_idx"],
            "duration": current_session["duration"],
            "frames": current_session["frames"]
        }
        print(f"🎵 Finalized session: {current_session['id']}")
   
    print(f"🎵 Found {len(sessions)} typing sessions total")
   
    # Create trimmed audio files for each session
    trimmed_map = {}
    session_count = 0
   
    for session_id, session_info in sessions.items():
        session_duration = session_info["duration"]
       
        if session_duration <= 0:
            print(f"🎵 Skipping session {session_id} - zero duration")
            continue
           
        print(f"🎵 Creating audio for session {session_id}: {session_duration:.2f}s")
       
        # Create trimmed file with exact duration
        out_file = os.path.join(tmp_dir, f"typing_session_{session_count}_{session_id}.aac")
       
        # Use ffmpeg to trim the typing sound to exact session duration
        ffmpeg_cmd = (
            f"ffmpeg -y -hide_banner -loglevel error -i {shlex.quote(typing_sound_master_path)} "
            f"-t {session_duration:.3f} -c:a aac -b:a 128k {shlex.quote(out_file)}"
        )
       
        try:
            subprocess.check_call(ffmpeg_cmd, shell=True)
           
            if os.path.exists(out_file):
                file_size = os.path.getsize(out_file)
                print(f"🎵 ✅ Created typing audio: {out_file} ({file_size} bytes)")
                trimmed_map[session_id] = {
                    "file": out_file,
                    "duration": session_duration,
                    "first_idx": session_info["start_idx"]
                }
                session_count += 1
            else:
                print(f"🎵 ❌ Output file not created: {out_file}")
               
        except subprocess.CalledProcessError as e:
            print(f"🎵 ❌ FFmpeg failed for session {session_id}: {e}")
            continue
   
    print(f"🎵 Successfully created {len(trimmed_map)} typing audio sessions")
    return trimmed_map

def timeline_time_at_index(timeline, idx):
    """Calculate cumulative time up to a specific index in the timeline"""
    return sum(float(t.get("duration", 0)) for t in timeline[:idx])

def _run(cmd: str):
    print("RUN:", cmd)
    subprocess.check_call(cmd, shell=True)

def _safe(path: str) -> str:
    return path.replace("\\", "/")

def ensure_local(path_or_url: str) -> str:
    """
    If given a URL, download to TMP_DIR and return local path.
    If given an absolute local path, return it unchanged.
    If given a relative local path, return BASE_DIR + relative path.
    """
    if not path_or_url:
        return ""
    if isinstance(path_or_url, str) and path_or_url.startswith("http"):
        local_path = os.path.join(TMP_DIR, os.path.basename(path_or_url.split("?")[0]))
        if not os.path.exists(local_path):
            r = requests.get(path_or_url, stream=True, timeout=20)
            r.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in r.iter_content(1024 * 64):
                    f.write(chunk)
        return local_path
    if os.path.isabs(path_or_url):
        return path_or_url
    return os.path.join(BASE_DIR, path_or_url)

def _decode_meme_b64(item: Dict[str, Any], index: int) -> str:
    """
    If item contains meme_b64, decode it into TMP_DIR and return file path.
    Otherwise return None.
    """
    if not item.get("meme_b64"):
        return None
    # pick extension from hint or default
    ext = item.get("ext", ".png")
    out_path = os.path.join(TMP_DIR, f"meme_{index}{ext}")
    try:
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(item["meme_b64"]))
        item["file"] = out_path
        return out_path
    except Exception as e:
        print(f"⚠️ Failed to decode meme_b64 for item {index}: {e}")
        return None

def _is_valid_image(path: str) -> bool:
    try:
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False

def create_concat_file_from_frames_only(frames_dir: str, concat_path: str, fps: int = FPS) -> Tuple[float, List[str]]:
    frames = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
    frames = [f for f in frames if _is_valid_image(f)]
    if not frames:
        raise RuntimeError(f"No valid frames found in {frames_dir}")
    frame_duration = 1.0 / fps
    total_duration = 0.0
    lines = ["ffconcat version 1.0"]
    for frame in frames:
        add_still_to_concat(lines, _safe(frame), frame_duration)
        total_duration += frame_duration
    lines.append(f"file '{_safe(frames[-1])}'")
    with open(concat_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"✅ concat.txt (fallback) with {len(frames)} frames @ {fps}fps")
    return total_duration, frames

def _prepare_meme_clip(src_path: str, out_path: str, hold_seconds: float, video_w: int, video_h: int):
    # Ensure proper scaling + enforce even dimensions
    vf = (
        f"scale={video_w}:{video_h}:force_original_aspect_ratio=decrease,"
        f"scale=trunc(iw/2)*2:trunc(ih/2)*2,fps={FPS}"
    )
    cmd = (
        f'ffmpeg -y -i "{src_path}" -t {hold_seconds:.3f} -an '
        f'-vf "{vf}" -pix_fmt yuv420p -r {FPS} '
        f'-c:v libx264 -preset veryfast -crf 18 "{out_path}"'
    )
    _run(cmd)

def _process_meme_item(item, index, video_w, video_h, tmp_dir):
    # Check if file exists and is valid
    if "file" not in item or not item["file"]:
        print(f"⚠️ Meme {index}: No file path specified, skipping.")
        return None
       
    meme_src = ensure_local(item["file"])
   
    # Check if file actually exists
    if not os.path.exists(meme_src):
        print(f"⚠️ Meme {index}: File not found: {meme_src}, skipping.")
        return None
       
    hold = float(item.get("duration", 2.5))
    ext = os.path.splitext(meme_src)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".webp"):
        try:
            out_frame_path, seconds = handle_meme_image(meme_src, os.path.join(TMP_DIR, f"meme_{index}.png"), hold)
            # Ensure out_frame_path is a string, not a list
            if isinstance(out_frame_path, list):
                if out_frame_path:
                    out_frame_path = out_frame_path[0]
                    print(f"⚠️ Meme {index}: handle_meme_image returned list, using first frame: {out_frame_path}")
                else:
                    print(f"⚠️ Meme {index}: handle_meme_image returned empty list, skipping.")
                    return None
            if not os.path.exists(out_frame_path) or not _is_valid_image(out_frame_path):
                print(f"⚠️ Meme {index}: Invalid image output {out_frame_path}, skipping.")
                return None
            return {"type": "image", "path": out_frame_path, "duration": seconds}
        except Exception as e:
            print(f"⚠️ Meme {index} image processing failed: {e}")
            return None
    elif ext in (".gif", ".mp4", ".mov", ".mkv", ".webm"):
        meme_clip = os.path.join(tmp_dir, f"meme_{index}.mp4")
        try:
            _prepare_meme_clip(meme_src, meme_clip, hold, video_w, video_h)
            return {"type": "video", "path": meme_clip, "duration": hold}
        except Exception as e:
            print(f"⚠️ Meme {index} conversion failed: {e}. Falling back to thumbnail.")
            try:
                thumb, seconds = handle_meme_image(meme_src, os.path.join(TMP_DIR, f"meme_{index}_thumb.png"), min(hold, 2.0))
                if isinstance(thumb, list):
                    if thumb:
                        thumb = thumb[0]
                        print(f"⚠️ Meme {index}: Thumbnail returned list, using first: {thumb}")
                    else:
                        print(f"⚠️ Meme {index}: Thumbnail returned empty list, skipping.")
                        return None
                if not os.path.exists(thumb) or not _is_valid_image(thumb):
                    print(f"⚠️ Meme {index}: Invalid thumbnail {thumb}, skipping.")
                    return None
                return {"type": "image", "path": thumb, "duration": seconds}
            except Exception as e2:
                print(f"⚠️ Meme {index} thumbnail also failed: {e2}")
                return None
    else:
        print(f"⚠️ Meme {index}: unsupported extension {ext}, skipping.")
        return None

def create_moral_screen(moral_text, duration=4.0, output_path=None):
    """Create a moral of the lesson screen with black background and red text"""
    print(f"🎬 DEBUG create_moral_screen called with: '{moral_text}'")
    if not output_path:
        output_path = os.path.join(TMP_DIR, "moral_screen.png")
   
    # Get video dimensions from first frame to match size
    frames = glob.glob(os.path.join(FRAMES_DIR, "*.png"))
    if frames:
        with Image.open(frames[0]) as img:
            width, height = img.size
    else:
        width, height = 1904, 934 # Default dimensions
   
    # Create black background
    img = Image.new('RGB', (width, height), color='black')
    draw = ImageDraw.Draw(img)
   
    try:
        # Try to use a larger font, fallback to default if not available
        font_size = min(width // 15, 72)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except:
                font = ImageFont.load_default()
    except:
        font = ImageFont.load_default()
   
    # Split text into lines that fit the screen
    words = moral_text.split()
    lines = []
    current_line = []
   
    for word in words:
        test_line = ' '.join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        text_width = bbox[2] - bbox[0]
       
        if text_width < width * 0.8:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
   
    if current_line:
        lines.append(' '.join(current_line))
   
    # Calculate total text height and starting position
    line_height = font_size * 1.2
    total_text_height = len(lines) * line_height
    y_position = (height - total_text_height) // 2
   
    # Draw each line centered
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x_position = (width - text_width) // 2
       
        # Draw text with red color
        draw.text((x_position, y_position), line, fill='red', font=font)
        y_position += line_height
   
    img.save(output_path)
    print(f"✅ Created moral screen: {output_path}")
    print(f"✅ Moral screen exists: {os.path.exists(output_path)}")
    print(f"✅ Moral screen size: {os.path.getsize(output_path)} bytes")
   
    return output_path, duration

def generate_moral_from_conversation(timeline):
    """Generate an intelligent moral based on the conversation content"""
    try:
        from groq import Groq
       
        # Extract conversation text from timeline
        conversation_lines = []
        for entry in timeline:
            if entry.get("text") and entry.get("text").strip():
                username = entry.get("username", "Unknown")
                text = entry.get("text", "").strip()
                conversation_lines.append(f"{username}: {text}")
       
        if not conversation_lines:
            return get_fallback_moral()
       
        conversation_text = "\n".join(conversation_lines[-20:])
       
        # Initialize Groq client
        groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
       
        prompt = f"""Based on this conversation, generate a short, meaningful moral or lesson (1 sentence, max 15 words). Make it insightful and relevant to the conversation tone.
Conversation:
{conversation_text}
Moral of the story:"""
       
        response = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a wise storyteller who extracts meaningful life lessons from conversations. Keep responses very short (1 sentence, under 15 words)."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model="llama-3.1-8b-instant",
            max_tokens=30,
            temperature=0.7
        )
       
        moral = response.choices[0].message.content.strip()
       
        # Clean up the response
        moral = moral.replace('"', '').replace("Moral:", "").replace("Lesson:", "").strip()
       
        if moral and len(moral) > 5:
            print(f"🤖 AI-generated moral: '{moral}'")
            return moral
        else:
            return get_fallback_moral()
           
    except Exception as e:
        print(f"⚠️ AI moral generation failed: {e}")
        return get_fallback_moral()

def get_fallback_moral():
    """Return a random fallback moral if none provided"""
    fallback_morals = [
        "And that's why you should always think before you type",
        "Moral of the story: Think twice, send once",
        "The lesson: Great conversations create great connections",
        "Remember: Quality over quantity in every conversation",
        "The takeaway: Every message matters",
        "Moral: Better conversations lead to better relationships"
    ]
    return random.choice(fallback_morals)

def _infer_canvas_size_from_first_frame(timeline: List[Dict[str, Any]], default_w=1904, default_h=934) -> Tuple[int, int]:
    for item in timeline:
        if not item.get("is_meme"):
            f = item.get("frame")
            if f:
                frame_path = os.path.join(BASE_DIR, f) if not os.path.isabs(f) else f
                if os.path.exists(frame_path) and _is_valid_image(frame_path):
                    try:
                        with Image.open(frame_path) as im:
                            return im.width, im.height
                    except Exception:
                        pass
    return default_w, default_h

def debug_timeline_loading():
    """Debug timeline loading and frame paths"""
    print("🔍 ===== TIMELINE DEBUG =====")
   
    if os.path.exists(TIMELINE_FILE):
        with open(TIMELINE_FILE, "r", encoding="utf-8") as f:
            timeline = json.load(f)
       
        print(f"🔍 Timeline entries: {len(timeline)}")
        total_duration = 0
        for i, item in enumerate(timeline):
            duration = item.get("duration", 0)
            total_duration += duration
            frame_path = item.get("frame", "")
            has_frame = os.path.exists(frame_path) if frame_path else False
            print(f"🔍 Entry {i}: duration={duration}s, frame='{frame_path}', exists={has_frame}")
            if frame_path and not has_frame:
                abs_path = os.path.join(BASE_DIR, frame_path) if not os.path.isabs(frame_path) else frame_path
                print(f"🔍 Absolute path: {abs_path}, exists: {os.path.exists(abs_path)}")
       
        print(f"🔍 Total expected duration: {total_duration}s")
        return timeline, total_duration
    else:
        print("🔍 No timeline file found!")
        return [], 0

def debug_concat_file(concat_path):
    """Debug the concat file content"""
    print("🔍 ===== CONCAT FILE DEBUG =====")
    if os.path.exists(concat_path):
        with open(concat_path, "r", encoding="utf-8") as f:
            content = f.read()
        lines = content.splitlines()
        print(f"🔍 Concat file has {len(lines)} lines")
       
        # Look for moral screen
        moral_lines = [i for i, line in enumerate(lines) if "moral_screen" in line]
        if moral_lines:
            print(f"✅ Found moral screen at lines: {moral_lines}")
            for line_idx in moral_lines:
                print(f"🔍 Line {line_idx}: {lines[line_idx]}")
                if line_idx + 1 < len(lines):
                    print(f"🔍 Line {line_idx+1}: {lines[line_idx+1]}")
        else:
            print("❌ No moral screen found in concat file!")
       
        # Show last 10 lines
        print("🔍 Last 10 lines of concat file:")
        for line in lines[-10:]:
            print(f"🔍 {line}")
    else:
        print("❌ Concat file doesn't exist!")

def debug_concat_creation(lines, concat_path, total_duration):
    """Debug why concat file isn't being created"""
    print("🔍 ===== CONCAT CREATION DEBUG =====")
    print(f"🔍 Lines list length: {len(lines)}")
    print(f"🔍 Concat path: {concat_path}")
    print(f"🔍 Total duration: {total_duration}")
   
    if lines:
        print("🔍 First 3 lines:")
        for i, line in enumerate(lines[:3]):
            print(f"🔍 {i}: {line}")
        print("🔍 Last 3 lines:")
        for i, line in enumerate(lines[-3:], start=len(lines)-3):
            print(f"🔍 {i}: {line}")
    else:
        print("❌ Lines list is EMPTY!")
   
    # Check if directory exists
    concat_dir = os.path.dirname(concat_path)
    print(f"🔍 Concat directory exists: {os.path.exists(concat_dir)}")
    print(f"🔍 Concat directory: {concat_dir}")

# --------------------
# Main builder
# --------------------
def build_video_from_timeline(bg_audio=None, send_audio=None, recv_audio=None, typing_audio=None, typing_bar_audio=None, use_segments=False, bg_segments: List[Dict[str, Any]] = None, moral_text: str = None) -> str:
    print("🎬 ===== build_video_from_timeline CALLED =====")
    print(f"🎬 Parameters received:")
    print(f"🎬 bg_audio: {bg_audio}")
    print(f"🎬 send_audio: {send_audio}")
    print(f"🎬 recv_audio: {recv_audio}")
    print(f"🎬 typing_audio: {typing_audio}")
    print(f"🎬 typing_bar_audio: {typing_bar_audio}")
    print(f"🎬 use_segments: {use_segments}")
    print(f"🎬 bg_segments param: {bg_segments}")
    print(f"🎬 moral_text: '{moral_text}'")
    print(f"🎬 moral_text type: {type(moral_text)}")
    print(f"🎬 moral_text is None: {moral_text is None}")
    print(f"🎬 moral_text is empty string: {moral_text == ''}")
   
    # Initialize audio lists
    delayed_files: List[str] = [] # Sound effects
    delayed_bg_files: List[str] = [] # Background music ONLY
   
    # Debug timeline and frames
    print("🔍 Debugging timeline and frames...")
    debug_timeline, expected_duration = debug_timeline_loading()
    total_duration = 0.0
    print("🎬 ===== build_video_from_timeline STARTED =====")
   
    # Check frames directory
    frames_in_dir = glob.glob(os.path.join(FRAMES_DIR, "*.png"))
    print(f"🔍 Frames in {FRAMES_DIR}: {len(frames_in_dir)}")
   
    # Clean up temp directory
    if os.path.exists(TMP_DIR):
        shutil.rmtree(TMP_DIR)
    os.makedirs(TMP_DIR, exist_ok=True)
   
    if os.path.exists(OUTPUT_VIDEO):
        os.remove(OUTPUT_VIDEO)
   
    concat_txt = os.path.join(TMP_DIR, "concat.txt")
    total_duration = 0.0
    timeline: List[Dict[str, Any]] = []
    all_segment_paths: List[str] = []
   
    # ------------------ LOAD TIMELINE ------------------
    if os.path.exists(TIMELINE_FILE):
        with open(TIMELINE_FILE, "r", encoding="utf-8") as f:
            timeline = json.load(f)
        print(f"🎬 Loaded {len(timeline)} timeline entries from file")
       
        # Small delay between text & meme of same user
        for i, item in enumerate(timeline):
            if item.get("is_meme") and i > 0:
                prev = timeline[i - 1]
                if prev.get("text") and prev.get("username") == item.get("username") and not prev.get("is_meme"):
                    item["duration"] = item.get("duration", 2.0) + 0.5
                    print(f"⏱️ Added 0.5s delay between text & meme for {item['username']}")
       
        # Decode any base64 memes
        for i, item in enumerate(timeline):
            if item.get("meme_b64"):
                _decode_meme_b64(item, i)
       
        # Filter invalid entries
        valid_timeline = []
        for item in timeline:
            if item.get("typing"):
                valid_timeline.append(item)
                continue
            if item.get("is_meme") and ("file" not in item or not item["file"]):
                print(f"⚠️ Skipping meme missing file: {item}")
                continue
            if not item.get("is_meme") and ("frame" not in item or not item["frame"]):
                print(f"⚠️ Skipping frame missing path: {item}")
                continue
            valid_timeline.append(item)
       
        print(f"🎬 After filtering: {len(valid_timeline)} valid entries")
       
        # Inject random memes (if applicable)
        timeline = inject_random_memes(valid_timeline, chance=0.25, max_per_video=3)
       
        if timeline:
            video_w, video_h = _infer_canvas_size_from_first_frame(timeline)
            lines = ["ffconcat version 1.0"]
            meme_segments = []
           
            # ------------------ MAIN LOOP ------------------
            for i, item in enumerate(timeline):
                # --- Typing bubbles ---
                if item.get("typing"):
                    frame_path = os.path.join(BASE_DIR, item["frame"]) if not os.path.isabs(item["frame"]) else item["frame"]
                    if os.path.exists(frame_path) and _is_valid_image(frame_path):
                        seconds = float(item.get("duration", 1.5))
                        add_still_to_concat(lines, _safe(frame_path), seconds)
                        all_segment_paths.append(frame_path)
                        total_duration += seconds
                        print(f"✅ Typing frame {i}: {frame_path} ({seconds}s)")
                    else:
                        print(f"⚠️ Typing frame {i}: missing or invalid {item.get('frame')}")
                    continue
               
                # --- Typing BAR (new) ---
                if item.get("typing_bar"):
                    frame_path = os.path.join(BASE_DIR, item["frame"]) if not os.path.isabs(item["frame"]) else item["frame"]
                    if os.path.exists(frame_path) and _is_valid_image(frame_path):
                        seconds = float(item.get("duration", 1.5))
                        add_still_to_concat(lines, _safe(frame_path), seconds)
                        all_segment_paths.append(frame_path)
                        total_duration += seconds
                        print(f"✅ Typing BAR frame {i}: {frame_path} ({seconds}s) - upcoming_text: {item.get('upcoming_text', 'N/A')}")
                    else:
                        print(f"⚠️ Typing BAR frame {i}: missing or invalid {item.get('frame')}")
                    continue
               
                # --- Regular chat frames ---
                if not item.get("is_meme"):
                    frame_path = os.path.join(BASE_DIR, item["frame"]) if not os.path.isabs(item["frame"]) else item["frame"]
                    if os.path.exists(frame_path) and _is_valid_image(frame_path):
                        seconds = float(item.get("duration", 1.5))
                        add_still_to_concat(lines, _safe(frame_path), seconds)
                        all_segment_paths.append(frame_path)
                        total_duration += seconds
                        print(f"✅ Regular frame {i}: {frame_path} ({seconds}s)")
                        continue
                    else:
                        print(f"⚠️ Frame {i}: missing or invalid {item.get('frame')}")
                        continue
               
                # --- Meme chat frame priority ---
                if item.get("is_meme") and item.get("frame"):
                    frame_path = os.path.join(BASE_DIR, item["frame"]) if not os.path.isabs(item["frame"]) else item["frame"]
                    if os.path.exists(frame_path) and _is_valid_image(frame_path):
                        seconds = float(item.get("duration", 2.5))
                        add_still_to_concat(lines, _safe(frame_path), seconds)
                        all_segment_paths.append(frame_path)
                        total_duration += seconds
                        print(f"✅ Used rendered chat frame for meme {i}: {frame_path} ({seconds}s)")
                        continue
                    else:
                        print(f"⚠️ Meme {i}: frame missing or invalid, fallback to meme asset")
               
                # --- Fallback: process raw meme asset ---
                if "file" not in item or not item["file"]:
                    print(f"⚠️ Meme {i}: No file specified, skipping.")
                    continue
               
                meme_result = _process_meme_item(item, i, video_w, video_h, TMP_DIR)
                if meme_result and os.path.exists(meme_result["path"]):
                    if meme_result["type"] == "image":
                        add_still_to_concat(lines, _safe(meme_result["path"]), meme_result["duration"])
                        all_segment_paths.append(meme_result["path"])
                        total_duration += meme_result["duration"]
                        print(f"✅ Meme {i} processed as image: {meme_result['path']} ({meme_result['duration']}s)")
                    else:
                        lines.append(f"file '{_safe(meme_result['path'])}'")
                        all_segment_paths.append(meme_result["path"])
                        total_duration += meme_result["duration"]
                        print(f"✅ Meme {i} processed as video: {meme_result['path']} ({meme_result['duration']}s)")
                else:
                    print(f"⚠️ Meme {i}: Processing failed, skipping.")
           
            # ------------------ ADD MORAL SCREEN AT END ------------------
            if moral_text and moral_text.strip():
                print(f"🎬 Adding moral screen: '{moral_text}'")
               
                # Create moral screen with user-provided text
                moral_image_path, moral_duration = create_moral_screen(moral_text.strip())
               
                # Add moral screen to the lines list
                lines.append(f"file '{_safe(moral_image_path)}'")
                lines.append(f"duration {moral_duration:.3f}")
               
                total_duration += moral_duration
                print(f"✅ Added moral screen ({moral_duration}s) - Total duration now: {total_duration}s")
               
            elif moral_text is None or moral_text == '': # Use AI-generated moral if empty
                print("🎬 No moral provided - generating AI moral from conversation...")
               
                # Generate intelligent moral from conversation
                ai_moral = generate_moral_from_conversation(timeline)
                print(f"🤖 AI-generated moral: '{ai_moral}'")
               
                moral_image_path, moral_duration = create_moral_screen(ai_moral)
               
                lines.append(f"file '{_safe(moral_image_path)}'")
                lines.append(f"duration {moral_duration:.3f}")
               
                total_duration += moral_duration
                print(f"✅ Added AI-generated moral screen ({moral_duration}s) - Total duration now: {total_duration}s")
               
            else:
                # Safety fallback
                print("🎬 Invalid moral text - using fallback")
                fallback_moral = get_fallback_moral()
                moral_image_path, moral_duration = create_moral_screen(fallback_moral)
               
                lines.append(f"file '{_safe(moral_image_path)}'")
                lines.append(f"duration {moral_duration:.3f}")
               
                total_duration += moral_duration
                print(f"✅ Added fallback moral screen ({moral_duration}s)")
           
            # ------------------ WRITE CONCAT FILE ------------------
            debug_concat_creation(lines, concat_txt, total_duration)
            try:
                with open(concat_txt, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                print(f"✅ Successfully wrote concat file: {concat_txt}")
                print(f"✅ File exists after writing: {os.path.exists(concat_txt)}")
                if os.path.exists(concat_txt):
                    print(f"✅ File size: {os.path.getsize(concat_txt)} bytes")
            except Exception as e:
                print(f"❌ Failed to write concat file: {e}")
           
            debug_concat_file(concat_txt)
            print(f"🎬 Created concat file with {len(lines)} entries, total duration: {total_duration}s")
           
        else:
            print("🎬 No valid timeline entries, falling back to frames directory")
            total_duration, _ = create_concat_file_from_frames_only(FRAMES_DIR, concat_txt)
    else:
        print("🎬 No timeline file found, falling back to frames directory")
        total_duration, _ = create_concat_file_from_frames_only(FRAMES_DIR, concat_txt)
   
    # ------------------ RENDER VIDEO ------------------
    print(f"🎬 Rendering video with total duration: {total_duration}s")
    temp_video = os.path.join(TMP_DIR, "temp_video.mp4")
   
    # Debug: Check if concat file exists and has content
    if os.path.exists(concat_txt):
        with open(concat_txt, "r", encoding="utf-8") as f:
            concat_content = f.read()
        print(f"🎬 Concat file content preview (first 500 chars):")
        print(concat_content[:500])
        print(f"🎬 Concat file has {len(concat_content.splitlines())} lines")
    else:
        print("❌ Concat file not created!")
       
    _run(
        f'ffmpeg -y -f concat -safe 0 -i "{concat_txt}" '
        f'-vf "scale=1280:720" -r {FPS} -pix_fmt yuv420p '
        f'-c:v libx264 -preset ultrafast -crf 23 '
        f'-threads 2 -movflags +faststart "{temp_video}"'
    )
   
    # Check if temp video was created and get its actual duration
    if os.path.exists(temp_video):
        try:
            result = subprocess.run([
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                temp_video
            ], capture_output=True, text=True, check=True)
            actual_temp_duration = float(result.stdout.strip())
            print(f"🎬 Temp video duration: {actual_temp_duration}s")
        except Exception as e:
            print(f"⚠️ Could not get temp video duration: {e}")
    else:
        print("❌ Temp video not created!")
   
    final_audio = os.path.join(TMP_DIR, "final_audio.aac")
    delayed_bg_files: List[str] = []
   
    # ------------------ BACKGROUND AUDIO ------------------
    print(f"🎵 BG Segments parameter received: {bg_segments}")
   
    # Use passed segments if available, otherwise load from file
    if use_segments:
        if bg_segments is not None and len(bg_segments) > 0:
            print(f"🎵 Using BG segments passed as parameter: {len(bg_segments)} segments")
        elif os.path.exists(BG_TIMELINE_FILE):
            with open(BG_TIMELINE_FILE, "r", encoding="utf-8") as f:
                try:
                    bg_segments = json.load(f)
                except Exception as e:
                    print(f"⚠️ Failed to parse {BG_TIMELINE_FILE}: {e}")
                    bg_segments = []
            print(f"🎵 Loaded BG segments from file: {len(bg_segments)} segments")
        else:
            print("🎵 No BG segments found - parameter was None and file doesn't exist")
            bg_segments = []
    else:
        bg_segments = []
        print("🎵 Not using segments (use_segments=False)")
   
    # Track song positions for "continue" mode
    song_positions: Dict[str, float] = {}
   
    # Debug: print all segments being processed with their playback modes
    print("🎵 ===== SEGMENTS TO PROCESS =====")
    for i, seg in enumerate(bg_segments):
        audio_file = seg.get("audio", "")
        playback_mode = seg.get("playback_mode", "start_fresh")
        custom_start = seg.get("custom_start", 0.0)
        exists = "EXISTS" if os.path.exists(ensure_local(audio_file)) else "MISSING"
        duration = seg["end"] - seg["start"]
        mode_display = {
            "start_fresh": "🆕 Start Fresh",
            "continue": "🔄 Continue",
            "custom_start": f"⏱️ Custom Start ({custom_start}s)"
        }
        print(f"🎵 Segment {i}: {seg['start']}s - {seg['end']}s ({duration}s) -> {audio_file} [{exists}] - {mode_display.get(playback_mode, '🆕 Start Fresh')}")
    print("🎵 ===============================")
   
    # Check if user has defined any segments (opted in)
    has_user_defined_segments = len(bg_segments) > 0
   
    if has_user_defined_segments:
        print("🎵 User has defined BG segments - using segment-based audio (with silence for gaps)")
       
        # Fill any gaps with silence
        filled_segments = []
        current_time = 0.0
       
        # Sort segments by start time
        bg_segments.sort(key=lambda x: x["start"])
       
        # Add silence before first segment if needed
        if bg_segments and bg_segments[0]["start"] > 0:
            filled_segments.append({
                "start": 0.0,
                "end": bg_segments[0]["start"],
                "audio": "",
                "playback_mode": "start_fresh",
                "custom_start": 0.0
            })
       
        # Process all segments
        for i, seg in enumerate(bg_segments):
            filled_segments.append(seg)
           
            # Check for gap before next segment
            if i < len(bg_segments) - 1:
                next_start = bg_segments[i + 1]["start"]
                if seg["end"] < next_start:
                    filled_segments.append({
                        "start": seg["end"],
                        "end": next_start,
                        "audio": "",
                        "playback_mode": "start_fresh",
                        "custom_start": 0.0
                    })
       
        # Add silence after last segment if needed
        if bg_segments and bg_segments[-1]["end"] < total_duration:
            filled_segments.append({
                "start": bg_segments[-1]["end"],
                "end": total_duration,
                "audio": "",
                "playback_mode": "start_fresh",
                "custom_start": 0.0
            })
       
        # If no segments but file exists (empty array), fill entire duration with silence
        if not bg_segments:
            filled_segments.append({
                "start": 0.0,
                "end": total_duration,
                "audio": "",
                "playback_mode": "start_fresh",
                "custom_start": 0.0
            })
       
        # Process all filled segments
        for seg_idx, seg in enumerate(filled_segments):
            audio_path = seg.get("audio", "")
            playback_mode = seg.get("playback_mode", "start_fresh")
            custom_start = seg.get("custom_start", 0.0)
            seg_dur = seg["end"] - seg["start"]
           
            if seg_dur <= 0:
                continue
               
            # Check if this is a silence segment (empty audio path)
            if not audio_path or not os.path.exists(ensure_local(audio_path)):
                # Create silent clip for silence segments
                silent_clip = os.path.join(TMP_DIR, f"silent_seg_{seg_idx}.aac")
                _run(f'ffmpeg -y -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 -t {seg_dur:.3f} -c:a aac -b:a 192k "{silent_clip}"')
                millis = int(math.floor(seg["start"] * 1000))
                delayed_silent = os.path.join(TMP_DIR, f"delayed_silent_{seg_idx}.aac")
                _run(f'ffmpeg -y -i "{silent_clip}" -af "adelay={millis}|{millis}" "{delayed_silent}"')
                delayed_bg_files.append(delayed_silent)
                print(f"🔇 Silence segment: {seg['start']:.1f}-{seg['end']:.1f}s")
            else:
                # Create audio clip for segments with audio
                audio_path = ensure_local(audio_path)
                if os.path.exists(audio_path):
                    # Determine start offset based on playback mode
                    start_offset = 0.0
                   
                    if playback_mode == "continue":
                        last_position = song_positions.get(audio_path, 0.0)
                        start_offset = last_position
                        print(f"🔄 Continuing {os.path.basename(audio_path)} from {last_position:.2f}s")
                       
                    elif playback_mode == "custom_start":
                        start_offset = custom_start
                        print(f"⏱️ Starting {os.path.basename(audio_path)} from custom time: {custom_start:.2f}s")
                   
                    # Create the audio clip with the appropriate start offset
                    bg_clip = os.path.join(TMP_DIR, f"bg_seg_{seg_idx}.aac")
                   
                    # Use ffmpeg to extract portion starting from offset
                    _run(f'ffmpeg -y -ss {start_offset:.3f} -i "{audio_path}" -t {seg_dur:.3f} -c:a aac -b:a 192k "{bg_clip}"')
                   
                    # Update song position for "continue" mode
                    if playback_mode == "continue":
                        new_position = start_offset + seg_dur
                        song_positions[audio_path] = new_position
                        print(f"📝 Updated {os.path.basename(audio_path)} position: {new_position:.2f}s")
                   
                    millis = int(math.floor(seg["start"] * 1000))
                    delayed_bg = os.path.join(TMP_DIR, f"delayed_bg_{seg_idx}.aac")
                    _run(f'ffmpeg -y -i "{bg_clip}" -af "adelay={millis}|{millis}" "{delayed_bg}"')
                    delayed_bg_files.append(delayed_bg)
                   
                    mode_display = {
                        "start_fresh": "🆕 Start Fresh",
                        "continue": "🔄 Continue",
                        "custom_start": f"⏱️ Custom Start ({custom_start}s)"
                    }
                   
                    print(f"🎵 Audio segment: {seg['start']:.1f}-{seg['end']:.1f}s - {os.path.basename(audio_path)} - {mode_display.get(playback_mode, '🆕 Start Fresh')}")
                else:
                    print(f"⚠️ Audio file not found: {audio_path}, using silence")
                    # Fallback to silence
                    silent_clip = os.path.join(TMP_DIR, f"silent_seg_{seg_idx}.aac")
                    _run(f'ffmpeg -y -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 -t {seg_dur:.3f} -c:a aac -b:a 192k "{silent_clip}"')
                    millis = int(math.floor(seg["start"] * 1000))
                    delayed_silent = os.path.join(TMP_DIR, f"delayed_silent_{seg_idx}.aac")
                    _run(f'ffmpeg -y -i "{silent_clip}" -af "adelay={millis}|{millis}" "{delayed_silent}"')
                    delayed_bg_files.append(delayed_silent)
       
        print(f"🎵 Processed {len(filled_segments)} BG segments ({len(delayed_bg_files)} audio files)")
        print(f"🎵 Final song positions: {song_positions}")
    else:
        # No segments defined - use default background for entire video
        print("🎵 No BG segments defined - using default background audio")
        if bg_audio and os.path.exists(ensure_local(bg_audio)):
            bg_loop = os.path.join(TMP_DIR, "bg_loop.aac")
            _run(f'ffmpeg -y -stream_loop -1 -i "{ensure_local(bg_audio)}" -t {total_duration:.3f} -c:a aac -b:a 192k "{bg_loop}"')
            delayed_bg_files = [bg_loop]
            print(f"🔊 Using default background: {os.path.basename(bg_audio)}")
        else:
            print("⚠️ No valid background audio provided, rendering without background music")
   
    # ------------------ SOUND EFFECTS ------------------
    print("🎵 ===== SOUND EFFECTS DEBUG START =====")
    # Initialize sound effects list
    if 'delayed_files' not in locals():
        delayed_files = []
    print(f"🎵 Initial delayed_files count: {len(delayed_files)}")
   
    # ========== CONTINUOUS TYPING SOUND SOLUTION ==========
    print("🎹 ===== DEBUG TYPING SOUND GENERATION =====")
    # First, debug what's in the timeline
    debug_typing_timeline_entries(timeline)
   
    # ADD THE FIXED CHECK HERE:
    if typing_audio and os.path.exists(ensure_local(typing_audio)) and timeline:
        print("🎹 Starting typing sound generation...")
       
        # Check if typing audio file exists
        typing_audio_path = ensure_local(typing_audio)
        print(f"🎹 Typing audio path: {typing_audio_path}")
        print(f"🎹 Typing audio exists: {os.path.exists(typing_audio_path)}")
       
        if not os.path.exists(typing_audio_path):
            print("❌ Typing audio file not found!")
        else:
            # ✅ SIMPLIFIED APPROACH: Find all typing sessions with their start/end times
            typing_sessions = []
            current_session = None
           
            current_time = 0.0
            for i, entry in enumerate(timeline):
                duration = float(entry.get("duration", 0))
               
                is_typing_with_sound = (
                    entry.get("typing_bar") and
                    entry.get("sound", False)
                )
               
                print(f"🎹 Frame {i}: time={current_time:.2f}s, typing_bar={entry.get('typing_bar')}, sound={entry.get('sound')}, text='{entry.get('upcoming_text')}'")
               
                if is_typing_with_sound:
                    if current_session is None:
                        # Start new session
                        current_session = {
                            "start_time": current_time,
                            "end_time": current_time + duration,
                            "frame_count": 1
                        }
                        print(f"🎹 🟢 START session at frame {i}, time {current_time:.3f}s")
                    else:
                        # Continue current session
                        current_session["end_time"] = current_time + duration
                        current_session["frame_count"] += 1
                        print(f"🎹 🔵 CONTINUE session at frame {i}")
                else:
                    if current_session is not None:
                        # ✅ CRITICAL FIX: End the session 3 frames early to avoid sound overrun
                        session_duration = current_session["end_time"] - current_session["start_time"]
                        avg_frame_duration = session_duration / current_session["frame_count"]
                       
                        # Remove sound for last 3 frames
                        adjusted_end_time = current_session["end_time"] - (avg_frame_duration * 2)
                       
                        if adjusted_end_time > current_session["start_time"] + 0.1:
                            current_session["end_time"] = adjusted_end_time
                            print(f"🎹 🔴 END session at frame {i} (adjusted -2 frames: {current_session['start_time']:.3f}s -> {current_session['end_time']:.3f}s)")
                        else:
                            print(f"🎹 🔴 END session at frame {i} (too short, using original)")
                       
                        typing_sessions.append(current_session)
                        current_session = None
               
                current_time += duration
           
            # Don't forget the last session
            if current_session is not None:
                session_duration = current_session["end_time"] - current_session["start_time"]
                avg_frame_duration = session_duration / current_session["frame_count"]
                adjusted_end_time = current_session["end_time"] - (avg_frame_duration * 3)
               
                if adjusted_end_time > current_session["start_time"] + 0.1:
                    current_session["end_time"] = adjusted_end_time
                    print(f"🎹 🔴 END final session (adjusted -2 frames)")
               
                typing_sessions.append(current_session)
           
            print(f"🎹 Found {len(typing_sessions)} typing sessions")
           
            # Create one continuous sound file for each typing session
            for session_idx, session in enumerate(typing_sessions):
                session_duration = session["end_time"] - session["start_time"]
               
                if session_duration <= 0:
                    print(f"🎹 ⚠️ Skipping session {session_idx} - zero duration")
                    continue
               
                print(f"🎹 Processing session {session_idx}: {session_duration:.3f}s at {session['start_time']:.3f}s ({session['frame_count']} frames)")
               
                # Create continuous typing sound for this session
                typing_clip = os.path.join(TMP_DIR, f"typing_session_{session_idx}.aac")
               
                try:
                    # Create the typing sound for the entire session duration
                    cmd = [
                        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                        '-i', typing_audio_path,
                        '-t', str(session_duration),
                        '-c:a', 'aac', '-b:a', '192k',
                        typing_clip
                    ]
                    print(f"🎹 Creating typing sound: ffmpeg -i {typing_audio_path} -t {session_duration} {typing_clip}")
                    subprocess.run(cmd, check=True, capture_output=True)
                   
                    if os.path.exists(typing_clip):
                        file_size = os.path.getsize(typing_clip)
                        print(f"🎹 ✅ Created typing sound: {typing_clip} ({file_size} bytes)")
                       
                        # Delay the sound to start at the correct time
                        millis = int(math.floor(session["start_time"] * 1000))
                        delayed_typing = os.path.join(TMP_DIR, f"delayed_typing_session_{session_idx}.aac")
                       
                        cmd = [
                            'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                            '-i', typing_clip,
                            '-af', f'adelay={millis}|{millis}',
                            '-c:a', 'aac', '-b:a', '192k',
                            delayed_typing
                        ]
                        print(f"🎹 Delaying sound: ffmpeg -i {typing_clip} -af adelay={millis} {delayed_typing}")
                        subprocess.run(cmd, check=True, capture_output=True)
                       
                        if os.path.exists(delayed_typing):
                            delayed_size = os.path.getsize(delayed_typing)
                            delayed_files.append(delayed_typing)
                            print(f"🎹 ✅ Added delayed typing sound: {delayed_typing} ({delayed_size} bytes)")
                        else:
                            print(f"🎹 ❌ Delayed typing sound file not created: {delayed_typing}")
                    else:
                        print(f"🎹 ❌ Typing sound file not created: {typing_clip}")
                       
                except subprocess.CalledProcessError as e:
                    print(f"❌ FFmpeg failed for session {session_idx}: {e}")
                except Exception as e:
                    print(f"❌ Error creating typing audio for session {session_idx}: {e}")
           
            print(f"🎹 Final: {len(typing_sessions)} continuous typing sessions added to delayed_files")
    else:
        print("🎹 Skipping typing sounds - missing audio file or empty timeline")
        if not typing_audio:
            print("🎹 ❌ typing_audio parameter is None or empty")
        elif not os.path.exists(ensure_local(typing_audio)):
            print(f"🎹 ❌ typing_audio file not found: {typing_audio}")
        if not timeline:
            print("🎹 ❌ timeline is empty")
   
    # Process message sounds (send/recv)
    current_time = 0.0
    sound_idx = len(delayed_files)
    print("🎵 Processing message sounds...")
    for i, entry in enumerate(timeline):
        dur = float(entry.get("duration", 1.0))
   
        # Skip typing entries (we already handled them with sessions)
        if entry.get("typing") or entry.get("typing_bar"):
            current_time += dur
            continue
   
        # Message sounds (send/recv) for regular messages
        has_content = entry.get("text") or entry.get("is_meme")
        if has_content:
            sound_delay = current_time + 0.5
            audio_file = ensure_local(send_audio if entry.get("is_sender") else recv_audio)
       
            if audio_file and os.path.exists(audio_file):
                out_del = os.path.join(TMP_DIR, f"msg_{sound_idx}.wav")
                _run(f'ffmpeg -y -i "{audio_file}" -af "adelay={int(sound_delay*1000)}|{int(sound_delay*1000)}" "{out_del}"')
                delayed_files.append(out_del)
                sound_idx += 1
                print(f"🎵 ✅ Message sound at {sound_delay:.2f}s")
        current_time += dur
   
    print(f"🎵 ===== SOUND EFFECTS DEBUG END =====")
    print(f"🎵 Total sound effects generated: {len(delayed_files)}")
    for i, sound_file in enumerate(delayed_files):
        exists = "✅" if os.path.exists(sound_file) else "❌"
        print(f"🎵 {i}: {exists} {os.path.basename(sound_file)}")
   
    # ------------------ FINAL AUDIO MIX (FIXED VERSION) ------------------
    print(f"🎵 Mixing {len(delayed_bg_files)} background files + {len(delayed_files)} sound effects")
   
    # Debug audio files first
    has_audio = debug_audio_generation(delayed_bg_files, delayed_files, final_audio)
   
    if not has_audio:
        print("🎵 No audio files available - creating video without audio")
        final_video = OUTPUT_VIDEO
        _run(f'ffmpeg -y -i "{temp_video}" -c:v copy -an "{final_video}"')
    else:
        all_audio_files = delayed_bg_files + delayed_files
        existing_audio_files = [f for f in all_audio_files if os.path.exists(f)]
       
        print(f"🎵 Using {len(existing_audio_files)} existing audio files for mixing")
       
        if len(existing_audio_files) == 0:
            # No valid audio files
            final_video = OUTPUT_VIDEO
            _run(f'ffmpeg -y -i "{temp_video}" -c:v copy -an "{final_video}"')
        elif len(existing_audio_files) == 1:
            # Single audio file - just copy it
            single_audio = existing_audio_files[0]
            _run(f'ffmpeg -y -i "{temp_video}" -i "{single_audio}" -c:v copy -c:a aac -shortest -movflags +faststart "{final_video}"')
        else:
            # Multiple audio files - mix them
            inputs = " ".join(f'-i "{p}"' for p in existing_audio_files)
            num_inputs = len(existing_audio_files)
            labels = "".join(f'[{i}:a]' for i in range(num_inputs))
           
            try:
                _run(
                    f'ffmpeg -y {inputs} -filter_complex "{labels}amix=inputs={num_inputs}:normalize=0" '
                    f'-c:a aac -b:a 192k "{final_audio}"'
                )
               
                if os.path.exists(final_audio):
                    final_video = OUTPUT_VIDEO
                    _run(
                        f'ffmpeg -y -i "{temp_video}" -i "{final_audio}" -c:v copy -c:a aac -shortest -movflags +faststart "{final_video}"'
                    )
                else:
                    print("❌ Final audio mixing failed - creating video without audio")
                    final_video = OUTPUT_VIDEO
                    _run(f'ffmpeg -y -i "{temp_video}" -c:v copy -an "{final_video}"')
                   
            except Exception as e:
                print(f"❌ Audio mixing failed: {e} - creating video without audio")
                final_video = OUTPUT_VIDEO
                _run(f'ffmpeg -y -i "{temp_video}" -c:v copy -an "{final_video}"')
   
    # Final debug: check the actual duration of the output video
    if os.path.exists(final_video):
        try:
            result = subprocess.run([
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                final_video
            ], capture_output=True, text=True, check=True)
            actual_final_duration = float(result.stdout.strip())
            print(f"🎬 Final video duration: {actual_final_duration}s")
            print(f"🎬 Expected duration: {total_duration}s")
        except Exception as e:
            print(f"⚠️ Could not get final video duration: {e}")
   
    print(f"🎬 Final video saved to: {final_video}")
    return final_video
