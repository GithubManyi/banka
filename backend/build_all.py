# backend/build_all.py
from backend.render_bubble import render_bubble
from generate_video import build_video_from_timeline

# 1) generate frames
render_bubble("Banka", "Hey guys, wifi is down!", True)
render_bubble("Jay", "Same here!", False)
render_bubble("Khooi", "My cat is online!", False)
render_bubble("Elon", "I can help fix the wifi!", True)

# 2) build video
build_video_from_timeline()
