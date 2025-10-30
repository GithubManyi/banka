import random
from backend.meme_fetcher import fetch_memes
import os
import base64

def encode_file_to_base64(path: str) -> str | None:
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def inject_random_memes(timeline, chance=0.3, max_per_video=3):
    """Inject memes as part of existing messages, not as separate entries."""
    if not timeline:
        return timeline

    # fetch some memes automatically
    meme_candidates = fetch_memes(limit=10, cleanup=True)

    injected = 0
    new_timeline = []

    for entry in timeline:
        # Only inject into regular text messages from real people
        if (injected < max_per_video and 
            random.random() < chance and 
            meme_candidates and
            "username" in entry and 
            entry["username"] != "MemeBot" and
            not entry.get("is_meme", False) and
            not entry.get("typing", False) and
            entry.get("text", "").strip() and  # Only messages with text
            "meme_path" not in entry):  # Don't add meme to existing memes
            
            meme_file = random.choice(meme_candidates)
            
            # Add meme to the existing message instead of creating new one
            entry["meme_path"] = meme_file
            entry["is_meme"] = True
            entry["meme_type"] = os.path.splitext(meme_file)[1].lower()
            
            # Encode meme data
            meme_data = encode_file_to_base64(meme_file)
            if meme_data:
                entry["meme_b64"] = meme_data
            
            injected += 1
        
        new_timeline.append(entry)

    return new_timeline