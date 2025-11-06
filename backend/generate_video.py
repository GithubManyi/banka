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
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed



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
# PERFORMANCE-OPTIMIZED HELPER FUNCTIONS
# --------------------

def _run_with_timeout(cmd: str, timeout=120, description=""):
    """Run command with timeout to prevent hanging - KEEPS ALL FEATURES"""
    print(f"⏱️ {description} (timeout={timeout}s): {cmd[:100]}...")
    try:
        result = subprocess.run(cmd, shell=True, timeout=timeout, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"⚠️ Command failed (returncode {result.returncode}): {result.stderr[:200]}")
            return False
        return True
    except subprocess.TimeoutExpired:
        print(f"❌ Command timed out after {timeout} seconds: {description}")
        return False
    except Exception as e:
        print(f"❌ Command failed with exception: {e}")
        return False

def _run_fast_ffmpeg(cmd: str, description=""):
    """Optimized FFmpeg with faster settings but ALL FEATURES"""
    # Use faster preset but keep all features
    cmd = cmd.replace("-preset ultrafast", "-preset superfast")
    cmd = cmd.replace("-crf 23", "-crf 25")  # Slightly higher CRF for speed but good quality
    return _run_with_timeout(cmd, timeout=180, description=description)

def debug_audio_generation(delayed_bg_files, delayed_files, final_audio):
    """Debug audio file generation - OPTIMIZED BUT KEEPS DEBUGGING"""
    print("🔊 ===== AUDIO GENERATION DEBUG =====")
    print(f"🔊 Background files: {len(delayed_bg_files)}")
    print(f"🔊 Sound effect files: {len(delayed_files)}")
    
    # Sample check to avoid too much I/O
    sample_size = min(5, len(delayed_bg_files), len(delayed_files))
    for i in range(sample_size):
        if i < len(delayed_bg_files):
            exists = "✅" if os.path.exists(delayed_bg_files[i]) else "❌"
            print(f"🔊   BG {i}: {exists} {os.path.basename(delayed_bg_files[i])}")
        if i < len(delayed_files):
            exists = "✅" if os.path.exists(delayed_files[i]) else "❌"
            print(f"🔊   SFX {i}: {exists} {os.path.basename(delayed_files[i])}")
    
    return len([f for f in delayed_bg_files + delayed_files if os.path.exists(f)]) > 0

def create_silent_audio_parallel(duration, output_path):
    """Create silent audio in parallel to save time"""
    return _run_with_timeout(
        f'ffmpeg -y -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 -t {duration:.3f} -c:a aac "{output_path}"',
        timeout=30,
        description="Create silent audio"
    )

def build_typing_audio_sessions_parallel(timeline, typing_sound_master_path, tmp_dir):
    """Creates typing audio sessions with PARALLEL processing"""
    os.makedirs(tmp_dir, exist_ok=True)
    sessions = {}
    current_session = None
    
    print(f"🎵 Scanning {len(timeline)} timeline entries for typing sessions...")
    
    # Group typing entries by session_id
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
    
    # Process sessions in parallel
    trimmed_map = {}
    
    def process_session(session_id, session_info, session_idx):
        session_duration = session_info["duration"]
        
        if session_duration <= 0:
            return None
            
        print(f"🎵 Creating audio for session {session_id}: {session_duration:.2f}s")
        
        out_file = os.path.join(tmp_dir, f"typing_session_{session_idx}_{session_id}.aac")
        
        success = _run_with_timeout(
            f"ffmpeg -y -hide_banner -loglevel error -i {shlex.quote(typing_sound_master_path)} "
            f"-t {session_duration:.3f} -c:a aac -b:a 128k {shlex.quote(out_file)}",
            timeout=30,
            description=f"Create typing session {session_idx}"
        )
        
        if success and os.path.exists(out_file):
            # Delay the sound to start at correct time
            start_time = timeline_time_at_index(timeline, session_info["start_idx"])
            millis = int(math.floor(start_time * 1000))
            delayed_typing = os.path.join(tmp_dir, f"delayed_typing_session_{session_idx}.aac")
            
            delay_success = _run_with_timeout(
                f'ffmpeg -y -i "{out_file}" -af "adelay={millis}|{millis}" -c:a aac "{delayed_typing}"',
                timeout=30,
                description=f"Delay typing session {session_idx}"
            )
            
            if delay_success and os.path.exists(delayed_typing):
                return session_id, delayed_typing, session_duration
        
        return None
    
    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_session = {}
        session_idx = 0
        
        for session_id, session_info in sessions.items():
            if session_info["duration"] > 0:
                future = executor.submit(process_session, session_id, session_info, session_idx)
                future_to_session[future] = session_id
                session_idx += 1
        
        for future in as_completed(future_to_session):
            result = future.result()
            if result:
                session_id, audio_file, duration = result
                trimmed_map[session_id] = {
                    "file": audio_file,
                    "duration": duration,
                    "first_idx": sessions[session_id]["start_idx"]
                }
    
    print(f"🎵 Successfully created {len(trimmed_map)} typing audio sessions in parallel")
    return trimmed_map

def timeline_time_at_index(timeline, idx):
    """Calculate cumulative time up to a specific index"""
    return sum(float(t.get("duration", 0)) for t in timeline[:idx])

def _safe(path: str) -> str:
    return path.replace("\\", "/")

def ensure_local(path_or_url: str) -> str:
    """If given a URL, download to TMP_DIR and return local path"""
    if not path_or_url:
        return ""

    if isinstance(path_or_url, str) and path_or_url.startswith("http"):
        local_path = os.path.join(TMP_DIR, os.path.basename(path_or_url.split("?")[0]))
        if not os.path.exists(local_path):
            try:
                r = requests.get(path_or_url, stream=True, timeout=15)
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
    """If item contains meme_b64, decode it into TMP_DIR"""
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
    """Create concat file from frames"""
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

def _prepare_meme_clip_fast(src_path: str, out_path: str, hold_seconds: float, video_w: int, video_h: int):
    """Prepare meme clip with OPTIMIZED settings"""
    vf = (
        f"scale={video_w}:{video_h}:force_original_aspect_ratio=decrease,"
        f"scale=trunc(iw/2)*2:trunc(ih/2)*2,fps={FPS}"
    )
    cmd = (
        f'ffmpeg -y -i "{src_path}" -t {hold_seconds:.3f} -an '
        f'-vf "{vf}" -pix_fmt yuv420p -r {FPS} '
        f'-c:v libx264 -preset superfast -crf 25 "{out_path}"'  # Faster settings
    )
    return _run_fast_ffmpeg(cmd, description=f"Process meme clip {os.path.basename(src_path)}")

def _process_meme_item_fast(item, index, video_w, video_h, tmp_dir):
    """Process meme item with OPTIMIZED settings"""
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
            if _prepare_meme_clip_fast(meme_src, meme_clip, hold, video_w, video_h):
                return {"type": "video", "path": meme_clip, "duration": hold}
            else:
                return None
        except Exception as e:
            print(f"⚠️ Meme {index} conversion failed: {e}")
            return None
    else:
        return None

def create_moral_screen(moral_text, duration=4.0, output_path=None):
    """Create a moral of the lesson screen"""
    if not output_path:
        output_path = os.path.join(TMP_DIR, "moral_screen.png")
    
    frames = glob.glob(os.path.join(FRAMES_DIR, "*.png"))
    if frames:
        with Image.open(frames[0]) as img:
            width, height = img.size
    else:
        width, height = 1904, 934
    
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
    """Generate an intelligent moral based on the conversation content"""
    try:
        from groq import Groq
        
        conversation_lines = []
        for entry in timeline[-15:]:  # Limit to last 15 messages for performance
            if entry.get("text") and entry.get("text").strip():
                username = entry.get("username", "Unknown")
                text = entry.get("text", "").strip()
                conversation_lines.append(f"{username}: {text}")
        
        if not conversation_lines:
            return get_fallback_moral()
        
        conversation_text = "\n".join(conversation_lines)
        
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
    """Return a random fallback moral"""
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
    """Infer canvas size from first valid frame"""
    for item in timeline[:3]:  # Check only first 3 frames
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

def process_background_segments_parallel(bg_segments, total_duration, tmp_dir):
    """Process background segments in PARALLEL for performance"""
    delayed_bg_files = []
    song_positions = {}
    
    def process_segment(seg, seg_idx):
        audio_path = seg.get("audio", "")
        playback_mode = seg.get("playback_mode", "start_fresh")
        custom_start = seg.get("custom_start", 0.0)
        seg_dur = seg["end"] - seg["start"]
        
        if seg_dur <= 0:
            return None
            
        if not audio_path or not os.path.exists(ensure_local(audio_path)):
            # Create silent clip
            silent_clip = os.path.join(tmp_dir, f"silent_seg_{seg_idx}.aac")
            if create_silent_audio_parallel(seg_dur, silent_clip):
                millis = int(math.floor(seg["start"] * 1000))
                delayed_silent = os.path.join(tmp_dir, f"delayed_silent_{seg_idx}.aac")
                if _run_with_timeout(
                    f'ffmpeg -y -i "{silent_clip}" -af "adelay={millis}|{millis}" "{delayed_silent}"',
                    timeout=20,
                    description=f"Delay silent segment {seg_idx}"
                ):
                    return delayed_silent
            return None
        else:
            # Process audio segment
            audio_path = ensure_local(audio_path)
            if os.path.exists(audio_path):
                start_offset = 0.0
                
                if playback_mode == "continue":
                    start_offset = song_positions.get(audio_path, 0.0)
                elif playback_mode == "custom_start":
                    start_offset = custom_start
                
                bg_clip = os.path.join(tmp_dir, f"bg_seg_{seg_idx}.aac")
                
                if _run_with_timeout(
                    f'ffmpeg -y -ss {start_offset:.3f} -i "{audio_path}" -t {seg_dur:.3f} -c:a aac -b:a 192k "{bg_clip}"',
                    timeout=30,
                    description=f"Extract audio segment {seg_idx}"
                ):
                    if playback_mode == "continue":
                        song_positions[audio_path] = start_offset + seg_dur
                    
                    millis = int(math.floor(seg["start"] * 1000))
                    delayed_bg = os.path.join(tmp_dir, f"delayed_bg_{seg_idx}.aac")
                    
                    if _run_with_timeout(
                        f'ffmpeg -y -i "{bg_clip}" -af "adelay={millis}|{millis}" "{delayed_bg}"',
                        timeout=20,
                        description=f"Delay audio segment {seg_idx}"
                    ):
                        return delayed_bg
            return None
    
    # Process segments in parallel
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_to_segment = {}
        
        for seg_idx, seg in enumerate(bg_segments):
            future = executor.submit(process_segment, seg, seg_idx)
            future_to_segment[future] = seg_idx
        
        for future in as_completed(future_to_segment):
            result = future.result()
            if result:
                delayed_bg_files.append(result)
    
    return delayed_bg_files

# --------------------
# OPTIMIZED MAIN BUILDER - KEEPS ALL FEATURES
# --------------------

def build_video_from_timeline(bg_audio=None, send_audio=None, recv_audio=None, typing_audio=None, typing_bar_audio=None, use_segments=False, bg_segments: List[Dict[str, Any]] = None, moral_text: str = None) -> str:
    print("🎬 ===== OPTIMIZED build_video_from_timeline STARTED (ALL FEATURES) =====")
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
    delayed_files = []
    delayed_bg_files = []

    # ------------------ LOAD AND PROCESS TIMELINE ------------------
    if os.path.exists(TIMELINE_FILE):
        with open(TIMELINE_FILE, "r", encoding="utf-8") as f:
            timeline = json.load(f)

        print(f"🎬 Loaded {len(timeline)} timeline entries")

        # Decode base64 memes
        for i, item in enumerate(timeline):
            if item.get("meme_b64"):
                _decode_meme_b64(item, i)

        # Filter invalid entries
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

        timeline = inject_random_memes(valid_timeline, chance=0.25, max_per_video=3)
        print(f"🎬 After filtering: {len(timeline)} valid entries")

        if timeline:
            video_w, video_h = _infer_canvas_size_from_first_frame(timeline)
            lines = ["ffconcat version 1.0"]

            # ------------------ PROCESS ALL FRAME TYPES ------------------
            for i, item in enumerate(timeline):
                frame_path = None
                seconds = float(item.get("duration", 1.5))
                
                # Handle all frame types
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
                    meme_result = _process_meme_item_fast(item, i, video_w, video_h, TMP_DIR)
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
            elif moral_text is None or moral_text == '':
                ai_moral = generate_moral_from_conversation(timeline)
                moral_image_path, moral_duration = create_moral_screen(ai_moral)
                lines.append(f"file '{_safe(moral_image_path)}'")
                lines.append(f"duration {moral_duration:.3f}")
                total_duration += moral_duration
                print(f"✅ Added AI-generated moral screen ({moral_duration}s)")

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

    # ------------------ RENDER VIDEO WITH OPTIMIZED SETTINGS ------------------
    print(f"🎬 Rendering video with total duration: {total_duration}s")
    temp_video = os.path.join(TMP_DIR, "temp_video.mp4")
    
    success = _run_fast_ffmpeg(
        f'ffmpeg -y -f concat -safe 0 -i "{concat_txt}" '
        f'-vf "scale=1280:720" -r {FPS} -pix_fmt yuv420p '
        f'-c:v libx264 -preset superfast -crf 25 '  # Optimized settings
        f'-threads 2 -movflags +faststart "{temp_video}"',
        description="Render main video"
    )
    
    if not success or not os.path.exists(temp_video):
        print("❌ Video rendering failed!")
        return None

    # ------------------ PROCESS AUDIO (ALL FEATURES) ------------------
    final_audio = os.path.join(TMP_DIR, "final_audio.aac")
    
    # Process background segments (KEPT FEATURE)
    if use_segments and bg_segments:
        print("🎵 Processing background segments in parallel...")
        delayed_bg_files = process_background_segments_parallel(bg_segments, total_duration, TMP_DIR)
        print(f"🎵 Processed {len(delayed_bg_files)} background segments")
    elif bg_audio and os.path.exists(ensure_local(bg_audio)):
        # Default background audio
        bg_loop = os.path.join(TMP_DIR, "bg_loop.aac")
        if _run_with_timeout(
            f'ffmpeg -y -stream_loop -1 -i "{ensure_local(bg_audio)}" -t {total_duration:.3f} -c:a aac -b:a 192k "{bg_loop}"',
            timeout=60,
            description="Create background audio loop"
        ):
            delayed_bg_files = [bg_loop]

    # Process typing sounds (KEPT FEATURE)
    if typing_audio and os.path.exists(ensure_local(typing_audio)) and timeline:
        print("🎹 Processing typing sounds in parallel...")
        typing_sessions = build_typing_audio_sessions_parallel(timeline, ensure_local(typing_audio), TMP_DIR)
        for session_info in typing_sessions.values():
            if os.path.exists(session_info["file"]):
                delayed_files.append(session_info["file"])

    # Process message sounds (KEPT FEATURE)
    current_time = 0.0
    for i, entry in enumerate(timeline):
        dur = float(entry.get("duration", 1.0))
        
        if entry.get("typing") or entry.get("typing_bar"):
            current_time += dur
            continue
        
        has_content = entry.get("text") or entry.get("is_meme")
        if has_content:
            sound_delay = current_time + 0.5
            audio_file = ensure_local(send_audio if entry.get("is_sender") else recv_audio)
            
            if audio_file and os.path.exists(audio_file):
                out_del = os.path.join(TMP_DIR, f"msg_{len(delayed_files)}.wav")
                if _run_with_timeout(
                    f'ffmpeg -y -i "{audio_file}" -af "adelay={int(sound_delay*1000)}|{int(sound_delay*1000)}" "{out_del}"',
                    timeout=20,
                    description=f"Create message sound {i}"
                ):
                    delayed_files.append(out_del)
        
        current_time += dur

    # ------------------ FINAL AUDIO MIXING ------------------
    print(f"🎵 Mixing {len(delayed_bg_files)} background files + {len(delayed_files)} sound effects")
    
    all_audio_files = delayed_bg_files + delayed_files
    existing_audio_files = [f for f in all_audio_files if os.path.exists(f)]
    
    if len(existing_audio_files) == 0:
        # No audio - create video without audio
        final_video = OUTPUT_VIDEO
        _run_with_timeout(
            f'ffmpeg -y -i "{temp_video}" -c:v copy -an "{final_video}"',
            timeout=30,
            description="Create video without audio"
        )
    elif len(existing_audio_files) == 1:
        # Single audio file
        final_video = OUTPUT_VIDEO
        _run_with_timeout(
            f'ffmpeg -y -i "{temp_video}" -i "{existing_audio_files[0]}" -c:v copy -c:a aac -shortest -movflags +faststart "{final_video}"',
            timeout=60,
            description="Mix video with single audio"
        )
    else:
        # Multiple audio files - mix them
        inputs = " ".join(f'-i "{p}"' for p in existing_audio_files)
        num_inputs = len(existing_audio_files)
        labels = "".join(f'[{i}:a]' for i in range(num_inputs))
        
        if _run_with_timeout(
            f'ffmpeg -y {inputs} -filter_complex "{labels}amix=inputs={num_inputs}:normalize=0" -c:a aac -b:a 192k "{final_audio}"',
            timeout=90,
            description="Mix all audio files"
        ) and os.path.exists(final_audio):
            final_video = OUTPUT_VIDEO
            _run_with_timeout(
                f'ffmpeg -y -i "{temp_video}" -i "{final_audio}" -c:v copy -c:a aac -shortest -movflags +faststart "{final_video}"',
                timeout=60,
                description="Combine video with mixed audio"
            )
        else:
            # Fallback: video without audio
            final_video = OUTPUT_VIDEO
            _run_with_timeout(
                f'ffmpeg -y -i "{temp_video}" -c:v copy -an "{final_video}"',
                timeout=30,
                description="Create video without audio (fallback)"
            )

    # Final timing
    end_time = time.time()
    print(f"🎬 Video generation completed in {end_time - start_time:.2f} seconds")
    
    if os.path.exists(OUTPUT_VIDEO):
        print(f"🎬 Final video saved to: {OUTPUT_VIDEO}")
        return OUTPUT_VIDEO
    else:
        print("❌ Final video not created!")
        return None
