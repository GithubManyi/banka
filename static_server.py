import os
import flask
from flask import Flask, send_from_directory
from flask_cors import CORS

def setup_static_server(app):
    """Setup static file serving for Railway deployment"""
    
    @app.route('/static/<path:filename>')
    def serve_static(filename):
        static_dir = os.path.join(os.path.dirname(__file__), 'static')
        return send_from_directory(static_dir, filename)
    
    @app.route('/assets/<path:filename>')
    def serve_assets(filename):
        assets_dir = os.path.join(os.path.dirname(__file__), 'assets')
        return send_from_directory(assets_dir, filename)
    
    @app.route('/frames/<path:filename>')
    def serve_frames(filename):
        frames_dir = os.path.join(os.path.dirname(__file__), 'frames')
        return send_from_directory(frames_dir, filename)

def create_flask_app():
    """Create Flask app for static file serving"""
    app = Flask(__name__)
    CORS(app)
    setup_static_server(app)
    return app

# Railway-compatible static file paths
def get_static_path(filename):
    """Get absolute path for static files that works on Railway"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_path = os.path.join(base_dir, 'static', filename)
    
    # If file doesn't exist in static, check in current directory (for Railway)
    if not os.path.exists(static_path):
        # Try relative to current file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        static_path = os.path.join(current_dir, 'static', filename)
    
    return static_path

def get_avatar_path(username):
    """Get avatar path that works on Railway"""
    # First check if we have a custom avatar
    custom_avatar = os.path.join('static', 'avatars', f'{username}.png')
    if os.path.exists(custom_avatar):
        return custom_avatar
    
    # Fallback to default avatars
    default_avatars = ['jay.png', 'khooi.png', 'banka.png', 'alex.png', 'shiro.png', 'brian.png', 'paula.png']
    for avatar in default_avatars:
        avatar_path = get_static_path(os.path.join('images', 'avatars', avatar))
        if os.path.exists(avatar_path):
            return avatar_path
    
    # Ultimate fallback
    return get_static_path('images/contact.png')
