import json
import os
import subprocess
import requests
import random
from datetime import datetime
from backend.meme_fetcher import fetch_meme_from_giphy
from backend.render_bubble import render_bubble, WhatsAppRenderer, render_typing_bar_frame, generate_beluga_typing_sequence
from backend.avatar_handler import get_avatar, name_to_color
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(BASE_DIR, "timeline.json")
FRAME_DIR = os.path.join(BASE_DIR, "frames")


def run_ffmpeg(cmd):
    """Run ffmpeg command safely."""
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        print("⚠️ FFmpeg error:", e.stderr.decode())


def download_meme(url, save_path):
    """
    Downloads a meme (GIF/WEBP/MP4) and saves as PNG for inline bubble rendering.
    """
    tmp_file = save_path + ".tmp"

    r = requests.get(url, stream=True, timeout=10)
    if r.status_code == 200:
        with open(tmp_file, "wb") as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)

        # Convert into PNG for bubble rendering
        cmd = ["ffmpeg", "-y", "-i", tmp_file, "-vf", "scale=400:-1", "-frames:v", "1", save_path]
        run_ffmpeg(cmd)
        os.remove(tmp_file)
        return save_path
    else:
        print(f"⚠ Failed to download meme: {url}")
        return None


def parse_script_line(line):
    line = line.strip()

    # Meme lines
    if line.startswith("MEME:"):
        query = line.replace("MEME:", "").strip()
        meme_path = fetch_meme_from_giphy(query)
        if meme_path:
            return {
                "speaker": "system",   # or whoever you want to show
                "meme": meme_path,
                "duration": 3.0,
                "is_meme": True
            }
        return None

    # Normal text lines
    elif ":" in line:
        speaker, text = line.split(":", 1)
        return {
            "speaker": speaker.strip(),
            "text": text.strip(),
            "duration": 2.5,
            "is_meme": False
        }

    return None


def render_typing_bubble(speaker, is_sender, out_path):
    """
    Render a WhatsApp-style typing indicator (3 dots).
    """
    renderer = WhatsAppRenderer(
        chat_title="BANKA TOUR GROUP",
        chat_avatar="static/images/group.png",
        chat_status="jay, khooi, banka"
    )

    renderer.message_history.append({
        "username": speaker,
        "text": None,       # no text
        "typing": True,     # <-- flag for template
        "meme": None,
        "meme_type": None,
        "mime": None,
        "is_sender": is_sender,
        "is_read": False,
        "timestamp": datetime.now().strftime("%-I:%M %p").lower(),
        "color": name_to_color(speaker),
        "avatar": os.path.basename(get_avatar(speaker))
    })

    renderer.render_frame(out_path, show_typing_bar=False)  # No typing bar for chat bubbles


def calculate_typing_duration(text):
    """Calculate realistic typing duration based on text length"""
    chars = len(text.strip())
    base_duration = 1.5  # Minimum typing time
    char_duration = 0.08  # Per character typing speed
    
    typing_time = base_duration + (chars * char_duration)
    return min(typing_time, 4.0)  # Cap at 4 seconds max




def generate_timeline(script_lines):
    os.makedirs(FRAME_DIR, exist_ok=True)
    timeline = []
    frame_count = 0

    # ✅ Create persistent Chrome driver once
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--force-device-scale-factor=1")

    shared_driver = webdriver.Chrome(options=chrome_options)

    try:
        for line in script_lines:
            entry = parse_script_line(line)
            if not entry:
                continue

            if entry["is_meme"]:
                # Meme bubble only
                frame_path = os.path.join(FRAME_DIR, f"meme_{frame_count:04d}.png")
                render_bubble(entry["speaker"], None, False, frame_path, meme=entry["meme"])
                timeline.append({
                    "frame": frame_path,
                    "duration": entry["duration"],
                    "is_meme": True,
                    "username": entry["speaker"]
                })
                frame_count += 1
                continue

            speaker = entry["speaker"]
            text = entry["text"]
            is_sender = (speaker.lower() == "banka")  # Your main user

            # 🔹 ONLY ADD TYPING BAR FOR MAIN USER (Banka) - BELUGA STYLE
            if is_sender and text.strip():
                typing_sequence = generate_beluga_typing_sequence(text)

                print(f"🔍 TIMELINE: Generated {len(typing_sequence)} Beluga frames for '{text}'")

                for i, (typing_text, duration) in enumerate(typing_sequence):
                    typing_path = os.path.join(FRAME_DIR, f"typing_bar_{frame_count:04d}.png")
                    render_typing_bar_frame(
                        speaker,
                        typing_text,
                        typing_path,
                        driver=shared_driver,  # ✅ use persistent driver
                        short_wait=True
                    )
                    timeline.append({
                        "frame": typing_path,
                        "duration": duration,
                        "is_sender": is_sender,
                        "typing_bar": True,
                        "username": speaker,
                        "upcoming_text": typing_text
                    })
                    frame_count += 1

                print(f"🔍 TIMELINE: Added {len(typing_sequence)} frames to timeline")

            # 🔹 OTHER USERS (random typing chance)
            elif random.random() < 0.3:
                typing_path = os.path.join(FRAME_DIR, f"typing_{frame_count:04d}.png")
                render_typing_bubble(speaker, is_sender, typing_path)
                timeline.append({
                    "frame": typing_path,
                    "duration": round(random.uniform(1.2, 2.2), 2),
                    "is_sender": is_sender,
                    "typing": True
                })
                frame_count += 1

            # 🔹 ACTUAL MESSAGE (for everyone)
            frame_path = os.path.join(FRAME_DIR, f"msg_{frame_count:04d}.png")
            render_bubble(
                speaker,
                text,
                is_sender,
                frame_path,
                driver=shared_driver  # ✅ use the same Chrome
            )

            chars = len(text.strip())
            msg_duration = max(1.0, chars / 15)

            timeline.append({
                "frame": frame_path,
                "duration": round(msg_duration, 2),
                "is_sender": is_sender,
                "username": speaker,
                "text": text
            })
            frame_count += 1

    finally:
        # ✅ Quit Chrome after all frames are done
        shared_driver.quit()

    # Save timeline JSON
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(timeline, f, indent=2, ensure_ascii=False)

    print(f"✅ Timeline saved to {OUTPUT_PATH}")
    return timeline
