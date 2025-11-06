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
import time  # ADD THIS IMPORT

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

FPS = 25  # Target frame rate

# --------------------
# OPTIMIZED HELPER FUNCTIONS
# --------------------

def _run_with_timeout(cmd: str, timeout=60):
    """Run command with timeout to prevent hanging"""
    print(f"⏱️ RUN (timeout={timeout}s): {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, timeout=timeout, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"⚠️ Command failed (returncode {result.returncode}): {result.stderr}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"❌ Command timed out after {timeout} seconds: {cmd}")
        return False
    except Exception as e:
        print(f"❌ Command failed with exception: {e}")
        return False

def _run_fast(cmd: str):
    """Optimized version of _run with faster settings"""
    print(f"⚡ FAST RUN: {cmd}")
    try:
        # Use faster preset and higher CRF for speed
        cmd = cmd.replace("-preset ultrafast", "-preset superfast")
        cmd = cmd.replace("-crf 23", "-crf 28")  # Higher CRF = faster but lower quality
        subprocess.check_call(cmd, shell=True, timeout=120)  # 2 minute timeout
        return True
    except subprocess.TimeoutExpired:
        print(f"❌ Fast command timed out: {cmd}")
        return False
    except Exception as e:
        print(f"❌ Fast command failed: {e}")
        return False

def debug_audio_generation(delayed_bg_files, delayed_files, final_audio):
    """Debug audio file generation - OPTIMIZED"""
    print("🔊 ===== AUDIO GENERATION DEBUG =====")
    print(f"🔊 Background files: {len(delayed_bg_files)}")
    print(f"🔊 Sound effect files: {len(delayed_files)}")
    
    # Only check first few files to save time
    sample_files = delayed_bg_files[:3] + delayed_files[:3]
    for i, file in enumerate(sample_files):
        exists = "✅" if os.path.exists(file) else "❌"
        print(f"🔊   Sample {i}: {exists} {os.path.basename(file)}")
    
    return len([f for f in delayed_bg_files + delayed_files if os.path.exists(f)]) > 0

def create_silent_audio(duration, output_path):
    """Create a silent audio file of specified duration - OPTIMIZED"""
    try:
        return _run_with_timeout(
            f'ffmpeg -y -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 -t {duration:.3f} -c:a aac "{output_path}"',
            timeout=30
        )
    except Exception as e:
        print(f"❌ Failed to create silent audio: {e}")
        return False

def debug_typing_timeline_entries(timeline):
    """Debug function to check typing entries in timeline - OPTIMIZED"""
    print("🔍 ===== TYPING TIMELINE ENTRIES DEBUG =====")
    
    typing_entries = [entry for entry in timeline if entry.get("typing_bar")]
    print(f"🔍 Found {len(typing_entries)} typing bar entries in timeline")
    
    if not typing_entries:
        print("❌ No typing bar entries found in timeline!")
        return
    
    # Only show first 5 entries to save time
    for i, entry in enumerate(typing_entries[:5]):
        print(f"🔍   Entry {i}: text='{entry.get('upcoming_text')}' sound={entry.get('sound')}")

def build_typing_audio_sessions(timeline, typing_sound_master_path, tmp_dir):
    """Creates perfectly trimmed typing audio sessions - OPTIMIZED"""
    os.makedirs(tmp_dir, exist_ok=True)
    sessions = {}
    current_session = None
    
    print(f"🎵 Scanning {len(timeline)} timeline entries for typing sessions...")
    
    # First pass: group typing entries by session_id - OPTIMIZED
    for idx, entry in enumerate(timeline):
        if entry.get("typing_bar") and entry.get("typing_session_id"):
            session_id = entry["typing_session_id"]
            duration = float(entry.get("duration", 0))
            
            if current_session is None or current_session["id"] != session_id:
                if current_session:
                    sessions[current_session["id"]] = current_session
                current_session = {
                    "id": session_id,
                    "start_idx": idx,
                    "duration": duration,
                    "frames": [idx]
                }
            else:
                current_session["duration"] += duration
                current_session["frames"].append(idx)
    
    if current_session is not None:
        sessions[current_session["id"]] = current_session
    
    print(f"🎵 Found {len(sessions)} typing sessions total")
    
    # Create trimmed audio files for each session - WITH TIMEOUT
    trimmed_map = {}
    session_count = 0
    
    for session_id, session_info in sessions.items():
        session_duration = session_info["duration"]
        
        if session_duration <= 0:
            continue
            
        print(f"🎵 Creating audio for session {session_id}: {session_duration:.2f}s")
        
        out_file = os.path.join(tmp_dir, f"typing_session_{session_count}_{session_id}.aac")
        
        success = _run_with_timeout(
            f"ffmpeg -y -hide_banner -loglevel error -i {shlex.quote(typing_sound_master_path)} "
            f"-t {session_duration:.3f} -c:a aac -b:a 128k {shlex.quote(out_file)}",
            timeout=30
        )
        
        if success and os.path.exists(out_file):
            trimmed_map[session_id] = {
                "file": out_file,
                "duration": session_duration,
                "first_idx": session_info["start_idx"]
            }
            session_count += 1
    
    print(f"🎵 Successfully created {len(trimmed_map)} typing audio sessions")
    return trimmed_map

def timeline_time_at_index(timeline, idx):
    """Calculate cumulative time up to a specific index in the timeline - OPTIMIZED"""
    return sum(float(t.get("duration", 0)) for t in timeline[:idx])

def _safe(path: str) -> str:
    return path.replace("\\", "/")

def ensure_local(path_or_url: str) -> str:
    """If given a URL, download to TMP_DIR and return local path - OPTIMIZED"""
    if not path_or_url:
        return ""

    if isinstance(path_or_url, str) and path_or_url.startswith("http"):
        local_path = os.path.join(TMP_DIR, os.path.basename(path_or_url.split("?")[0]))
        if not os.path.exists(local_path):
            try:
                r = requests.get(path_or_url, stream=True, timeout=10)  # Shorter timeout
                r.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in r.iter_content(1024 * 64):
                        f.write(chunk)
            except Exception as e:
                print(f"⚠️ Failed to download {path_or_url}: {e}")
                return ""
        return local_path

    if os.path.isabs(path_or_url):
        return path_or_url
    return os.path.join(BASE_DIR, path_or_url)

def _decode_meme_b64(item: Dict[str, Any], index: int) -> str:
    """If item contains meme_b64, decode it into TMP_DIR - OPTIMIZED"""
    if not item.get("meme_b64"):
        return None

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
    """Fast image validation"""
    try:
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False

def create_concat_file_from_frames_only(frames_dir: str, concat_path: str, fps: int = FPS) -> Tuple[float, List[str]]:
    """Create concat file from frames - OPTIMIZED"""
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
    """Prepare meme clip - OPTIMIZED with faster settings"""
    vf = (
        f"scale={video_w}:{video_h}:force_original_aspect_ratio=decrease,"
        f"scale=trunc(iw/2)*2:trunc(ih/2)*2,fps={FPS}"
    )
    cmd = (
        f'ffmpeg -y -i "{src_path}" -t {hold_seconds:.3f} -an '
        f'-vf "{vf}" -pix_fmt yuv420p -r {FPS} '
        f'-c:v libx264 -preset superfast -crf 28 "{out_path}"'  # Faster preset, higher CRF
    )
    _run_with_timeout(cmd, timeout=60)

def _process_meme_item(item, index, video_w, video_h, tmp_dir):
    """Process meme item - OPTIMIZED"""
    if "file" not in item or not item["file"]:
        return None
        
    meme_src = ensure_local(item["file"])
    
    if not os.path.exists(meme_src):
        return None
        
    hold = float(item.get("duration", 2.5))
    ext = os.path.splitext(meme_src)[1].lower()

    if ext in (".png", ".jpg", ".jpeg", ".webp"):
        try:
            out_frame_path, seconds = handle_meme_image(meme_src, os.path.join(TMP_DIR, f"meme_{index}.png"), hold)
            if isinstance(out_frame_path, list):
                if out_frame_path:
                    out_frame_path = out_frame_path[0]
                else:
                    return None
            if not os.path.exists(out_frame_path) or not _is_valid_image(out_frame_path):
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
            print(f"⚠️ Meme {index} conversion failed: {e}")
            return None
    else:
        return None

def create_moral_screen(moral_text, duration=4.0, output_path=None):
    """Create a moral of the lesson screen - OPTIMIZED"""
    if not output_path:
        output_path = os.path.join(TMP_DIR, "moral_screen.png")
    
    # Get video dimensions from first frame
    frames = glob.glob(os.path.join(FRAMES_DIR, "*.png"))
    if frames:
        with Image.open(frames[0]) as img:
            width, height = img.size
    else:
        width, height = 1904, 934
    
    # Create simple black background with text
    img = Image.new('RGB', (width, height), color='black')
    draw = ImageDraw.Draw(img)
    
    try:
        font_size = min(width // 15, 72)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except:
            font = ImageFont.load_default()
    except:
        font = ImageFont.load_default()
    
    # Simple text splitting
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
    
    # Draw text
    line_height = font_size * 1.2
    total_text_height = len(lines) * line_height
    y_position = (height - total_text_height) // 2
    
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x_position = (width - text_width) // 2
        draw.text((x_position, y_position), line, fill='red', font=font)
        y_position += line_height
    
    img.save(output_path)
    return output_path, duration

def generate_moral_from_conversation(timeline):
    """Generate an intelligent moral based on the conversation content - OPTIMIZED"""
    try:
        from groq import Groq
        
        # Extract conversation text from timeline
        conversation_lines = []
        for entry in timeline[-10:]:  # Only last 10 messages for speed
            if entry.get("text") and entry.get("text").strip():
                username = entry.get("username", "Unknown")
                text = entry.get("text", "").strip()
                conversation_lines.append(f"{username}: {text}")
        
        if not conversation_lines:
            return get_fallback_moral()
        
        conversation_text = "\n".join(conversation_lines)
        
        groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        
        prompt = f"""Generate a short moral or lesson (1 sentence, max 15 words) from this conversation:

{conversation_text}

Moral:"""
        
        response = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            max_tokens=30,
            temperature=0.7
        )
        
        moral = response.choices[0].message.content.strip()
        moral = moral.replace('"', '').replace("Moral:", "").replace("Lesson:", "").strip()
        
        if moral and len(moral) > 5:
            return moral
        else:
            return get_fallback_moral()
            
    except Exception as e:
        print(f"⚠️ AI moral generation failed: {e}")
        return get_fallback_moral()

def get_fallback_moral():
    """Return a random fallback moral"""
    fallback_morals = [
        "And that's why you should always think before you type",
        "Moral of the story: Think twice, send once",
        "The lesson: Great conversations create great connections",
    ]
    return random.choice(fallback_morals)

def _infer_canvas_size_from_first_frame(timeline: List[Dict[str, Any]], default_w=1904, default_h=934) -> Tuple[int, int]:
    """Infer canvas size - OPTIMIZED"""
    for item in timeline[:5]:  # Only check first 5 items
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
    """Debug timeline loading - OPTIMIZED"""
    print("🔍 ===== TIMELINE DEBUG =====")
    
    if os.path.exists(TIMELINE_FILE):
        with open(TIMELINE_FILE, "r", encoding="utf-8") as f:
            timeline = json.load(f)
        
        print(f"🔍 Timeline entries: {len(timeline)}")
        total_duration = sum(item.get("duration", 0) for item in timeline)
        print(f"🔍 Total expected duration: {total_duration}s")
        return timeline, total_duration
    else:
        print("🔍 No timeline file found!")
        return [], 0

# --------------------
# OPTIMIZED MAIN BUILDER
# --------------------

def build_video_from_timeline(bg_audio=None, send_audio=None, recv_audio=None, typing_audio=None, typing_bar_audio=None, use_segments=False, bg_segments: List[Dict[str, Any]] = None, moral_text: str = None) -> str:
    print("🎬 ===== OPTIMIZED build_video_from_timeline STARTED =====")
    start_time = time.time()
    
    # Clean up temp directory
    if os.path.exists(TMP_DIR):
        shutil.rmtree(TMP_DIR)
    os.makedirs(TMP_DIR, exist_ok=True)
    
    if os.path.exists(OUTPUT_VIDEO):
        os.remove(OUTPUT_VIDEO)

    concat_txt = os.path.join(TMP_DIR, "concat.txt")
    total_duration = 0.0
    timeline = []

    # ------------------ LOAD TIMELINE ------------------
    if os.path.exists(TIMELINE_FILE):
        with open(TIMELINE_FILE, "r", encoding="utf-8") as f:
            timeline = json.load(f)

        print(f"🎬 Loaded {len(timeline)} timeline entries")

        # Filter invalid entries quickly
        valid_timeline = []
        for item in timeline:
            if item.get("typing") or item.get("typing_bar"):
                valid_timeline.append(item)
                continue
            if item.get("is_meme") and ("file" not in item or not item["file"]):
                continue
            if not item.get("is_meme") and ("frame" not in item or not item["frame"]):
                continue
            valid_timeline.append(item)

        timeline = valid_timeline
        print(f"🎬 After filtering: {len(timeline)} valid entries")

        if timeline:
            video_w, video_h = _infer_canvas_size_from_first_frame(timeline)
            lines = ["ffconcat version 1.0"]

            # ------------------ FAST FRAME PROCESSING ------------------
            for i, item in enumerate(timeline):
                # Handle all frame types quickly
                frame_path = None
                seconds = float(item.get("duration", 1.5))
                
                if item.get("typing") or item.get("typing_bar") or not item.get("is_meme"):
                    frame_path = os.path.join(BASE_DIR, item["frame"]) if not os.path.isabs(item["frame"]) else item["frame"]
                elif item.get("is_meme") and item.get("frame"):
                    frame_path = os.path.join(BASE_DIR, item["frame"]) if not os.path.isabs(item["frame"]) else item["frame"]

                if frame_path and os.path.exists(frame_path) and _is_valid_image(frame_path):
                    add_still_to_concat(lines, _safe(frame_path), seconds)
                    total_duration += seconds
                    continue

                # Fallback: process raw meme asset
                if item.get("is_meme") and "file" in item and item["file"]:
                    meme_result = _process_meme_item(item, i, video_w, video_h, TMP_DIR)
                    if meme_result and os.path.exists(meme_result["path"]):
                        if meme_result["type"] == "image":
                            add_still_to_concat(lines, _safe(meme_result["path"]), meme_result["duration"])
                            total_duration += meme_result["duration"]
                        else:
                            lines.append(f"file '{_safe(meme_result['path'])}'")
                            total_duration += meme_result["duration"]

            # ------------------ ADD MORAL SCREEN ------------------
            if moral_text and moral_text.strip():
                moral_image_path, moral_duration = create_moral_screen(moral_text.strip())
                lines.append(f"file '{_safe(moral_image_path)}'")
                lines.append(f"duration {moral_duration:.3f}")
                total_duration += moral_duration
                print(f"✅ Added moral screen ({moral_duration}s)")

            # ------------------ WRITE CONCAT FILE ------------------
            try:
                with open(concat_txt, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                print(f"✅ Created concat file with {len(lines)} entries, total duration: {total_duration}s")
            except Exception as e:
                print(f"❌ Failed to write concat file: {e}")
                return None
        else:
            print("🎬 No valid timeline entries, falling back to frames directory")
            total_duration, _ = create_concat_file_from_frames_only(FRAMES_DIR, concat_txt)
    else:
        print("🎬 No timeline file found, falling back to frames directory")
        total_duration, _ = create_concat_file_from_frames_only(FRAMES_DIR, concat_txt)

    # ------------------ FAST VIDEO RENDERING ------------------
    print(f"🎬 Rendering video with total duration: {total_duration}s")
    temp_video = os.path.join(TMP_DIR, "temp_video.mp4")
    
    # Use faster settings for video rendering
    success = _run_fast(
        f'ffmpeg -y -f concat -safe 0 -i "{concat_txt}" '
        f'-vf "scale=1280:720" -r {FPS} -pix_fmt yuv420p '
        f'-c:v libx264 -preset superfast -crf 28 '  # Faster settings
        f'-threads 2 -movflags +faststart "{temp_video}"'
    )
    
    if not success or not os.path.exists(temp_video):
        print("❌ Video rendering failed!")
        return None

    # ------------------ SIMPLIFIED AUDIO PROCESSING ------------------
    final_audio = os.path.join(TMP_DIR, "final_audio.aac")
    
    # Use only basic background audio (skip complex segment processing)
    if bg_audio and os.path.exists(ensure_local(bg_audio)):
        bg_loop = os.path.join(TMP_DIR, "bg_loop.aac")
        if _run_with_timeout(f'ffmpeg -y -stream_loop -1 -i "{ensure_local(bg_audio)}" -t {total_duration:.3f} -c:a aac -b:a 192k "{bg_loop}"', timeout=30):
            # Mix with video
            final_video = OUTPUT_VIDEO
            if _run_with_timeout(f'ffmpeg -y -i "{temp_video}" -i "{bg_loop}" -c:v copy -c:a aac -shortest -movflags +faststart "{final_video}"', timeout=60):
                print(f"✅ Final video with audio: {final_video}")
            else:
                # Fallback: video without audio
                _run_with_timeout(f'ffmpeg -y -i "{temp_video}" -c:v copy -an "{final_video}"', timeout=30)
        else:
            # Video without audio
            final_video = OUTPUT_VIDEO
            _run_with_timeout(f'ffmpeg -y -i "{temp_video}" -c:v copy -an "{final_video}"', timeout=30)
    else:
        # Video without audio
        final_video = OUTPUT_VIDEO
        _run_with_timeout(f'ffmpeg -y -i "{temp_video}" -c:v copy -an "{final_video}"', timeout=30)

    # Final timing
    end_time = time.time()
    print(f"🎬 Video generation completed in {end_time - start_time:.2f} seconds")
    
    if os.path.exists(final_video):
        print(f"🎬 Final video saved to: {final_video}")
        return final_video
    else:
        print("❌ Final video not created!")
        return None
