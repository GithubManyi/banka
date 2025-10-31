import os
import shutil

def setup_railway_directories():
    """Create necessary directories for Railway"""
    directories = [
        'static/audio',
        'static/images/avatars', 
        'static/avatars',
        'frames',
        'tmp_ffmpeg',
        'assets/memes/auto'
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"✅ Created directory: {directory}")

def setup_default_files():
    """Copy default files to appropriate locations"""
    # Copy default avatar if it doesn't exist
    default_avatar_src = 'static/images/contact.png'
    default_avatar_dest = 'static/avatars/default.png'
    
    if os.path.exists(default_avatar_src) and not os.path.exists(default_avatar_dest):
        shutil.copy2(default_avatar_src, default_avatar_dest)
        print("✅ Copied default avatar")
    
    # Create default audio files if they don't exist
    default_audio_files = ['default_bg.mp3', 'send.mp3', 'recv.mp3']
    for audio_file in default_audio_files:
        audio_path = f'static/audio/{audio_file}'
        if not os.path.exists(audio_path):
            # Create empty file as placeholder
            open(audio_path, 'wb').close()
            print(f"✅ Created placeholder: {audio_file}")

if __name__ == "__main__":
    print("🚀 Setting up Railway directories...")
    setup_railway_directories()
    setup_default_files()
    print("✅ Railway setup complete!")
