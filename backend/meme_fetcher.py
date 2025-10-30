# backend/meme_fetcher.py
import os
import requests
import random
import subprocess
import hashlib

ASSETS_DIR = os.path.join("assets", "memes", "auto")
os.makedirs(ASSETS_DIR, exist_ok=True)

# Get your free Giphy API key at https://developers.giphy.com/
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY")
if not GIPHY_API_KEY:
    raise RuntimeError("GIPHY_API_KEY not set in environment")

# Meme topics we’ll randomly pick from
MEME_QUERIES = [
    "funny meme",
    "fail gif",
    "reaction meme",
    "cat meme",
    "dog meme",
    "awkward gif",
    "celebration meme",
    "angry gif",
    "dance meme",
    "lol",
]


def run_ffmpeg(cmd):
    """Run FFmpeg command and raise if it fails."""
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode())


def gif_to_mp4(gif_path: str) -> str:
    """
    Converts a downloaded GIF into MP4 for better FFmpeg compatibility.
    Resizes + pads to fit inside 1904x933 while keeping aspect ratio.
    Always outputs yuv420p, even dimensions.
    """
    mp4_path = gif_path.replace(".gif", ".mp4")
    cmd = [
        "ffmpeg", "-y",
        "-i", gif_path,
        "-movflags", "faststart",
        "-pix_fmt", "yuv420p",
        "-vf", (
            "scale='min(1904,iw)':'min(933,ih)':force_original_aspect_ratio=decrease,"
            "pad=1904:933:(trunc((ow-iw)/2)*2):(trunc((oh-ih)/2)*2):black,"
            "fps=25"
        ),
        "-r", "25",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        mp4_path
    ]
    try:
        run_ffmpeg(cmd)
    except Exception as e:
        print(f"[meme_fetcher] FFmpeg failed for {gif_path}: {e}")
        return gif_path  # fallback to original GIF

    if os.path.exists(mp4_path):
        try:
            os.remove(gif_path)  # cleanup original GIF
        except OSError:
            pass
        return mp4_path
    return gif_path


def url_to_hash(url: str) -> str:
    """Hash a URL to generate unique, repeatable filenames."""
    return hashlib.md5(url.encode()).hexdigest()


def fetch_meme_from_giphy(query: str) -> str | None:
    """
    Fetch a meme/GIF/MP4 from Giphy given a search query.
    Returns the local MP4 file path, or PNG fallback if failed.
    """
    try:
        url = (
            f"https://api.giphy.com/v1/gifs/search"
            f"?api_key={GIPHY_API_KEY}&q={query}&limit=5&rating=g&lang=en"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if not data["data"]:
            raise ValueError("No results found on Giphy")

        # Pick a random GIF from results
        gif_data = random.choice(data["data"])

        # Prefer MP4 URL if available
        mp4_url = gif_data["images"].get("downsized_small", {}).get("mp4")
        gif_url = gif_data["images"]["original"]["url"]

        safe_query = "_".join(query.lower().split())
        base_name = f"{safe_query}_{random.randint(1000,9999)}"
        out_path = os.path.join(ASSETS_DIR, base_name + ".mp4")

        if mp4_url:
            # Download MP4 directly
            r = requests.get(mp4_url, stream=True, timeout=15)
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"[meme_fetcher] Downloaded MP4 directly {mp4_url} → {out_path}")
            return out_path

        # Otherwise fallback: download GIF then convert
        gif_path = os.path.join(ASSETS_DIR, base_name + ".gif")
        r = requests.get(gif_url, stream=True, timeout=15)
        r.raise_for_status()
        with open(gif_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"[meme_fetcher] Downloaded GIF {gif_url} → {gif_path}")

        try:
            mp4_path = gif_to_mp4(gif_path)
            print(f"[meme_fetcher] Converted to {mp4_path}")
            return mp4_path
        except Exception as e:
            print(f"[meme_fetcher] Conversion failed: {e}")
            # Fallback: grab first frame as PNG thumbnail
            thumb_path = gif_path.replace(".gif", ".png")
            cmd = ["ffmpeg", "-y", "-i", gif_path, "-vframes", "1", thumb_path]
            try:
                run_ffmpeg(cmd)
                print(f"[meme_fetcher] Using thumbnail {thumb_path}")
                return thumb_path
            except Exception as e2:
                print(f"[meme_fetcher] Thumbnail also failed: {e2}")
                return None

    except Exception as e:
        print(f"[meme_fetcher] Failed to fetch meme for '{query}': {e}")
        return None


def clear_old_memes():
    """Delete all previously downloaded memes in ASSETS_DIR."""
    for f in os.listdir(ASSETS_DIR):
        try:
            os.remove(os.path.join(ASSETS_DIR, f))
        except Exception as e:
            print(f"[meme_fetcher] Could not delete {f}: {e}")


def fetch_memes(limit=10, cleanup=True):
    """
    Fetch multiple memes from Giphy (random topics) and return local MP4 relative paths.
    If cleanup=True, delete old memes first.
    """
    if cleanup:
        clear_old_memes()

    results = []
    for _ in range(limit):
        query = random.choice(MEME_QUERIES)
        path = fetch_meme_from_giphy(query)
        if path:
            results.append(path)

    return results


if __name__ == "__main__":
    memes = fetch_memes(5)
    print("✅ Downloaded memes:", memes)
