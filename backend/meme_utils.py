import os
import requests
import re

def download_meme(url, out_dir, filename):
    """Download meme GIF/video from URL and return local path."""
    os.makedirs(out_dir, exist_ok=True)
    local_path = os.path.join(out_dir, filename)
    if not os.path.exists(local_path):
        r = requests.get(url, stream=True)
        r.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)
    return local_path



def find_meme(query, assets_dir="assets/memes/auto"):
    """Find best matching meme file for the query."""
    safe_query = query.lower().strip()
    words = safe_query.split()  # split into keywords

    candidates = []
    for fname in os.listdir(assets_dir):
        name = fname.lower()
        # count how many query words appear in filename
        score = sum(1 for w in words if w in name)
        if score > 0:
            candidates.append((score, fname))

    if not candidates:
        return None  # no match found
    # sort by best match (highest score, then shortest filename)
    candidates.sort(key=lambda x: (-x[0], len(x[1])))
    return os.path.join(assets_dir, candidates[0][1])
