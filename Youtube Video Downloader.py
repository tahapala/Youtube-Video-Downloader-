# ============================================================
#  YouTube Video Downloader
#  Required library: pip install yt-dlp
# ============================================================

import yt_dlp
import os
import glob
import subprocess

def print_header():
    print("=" * 50)
    print("       🎬 YouTube Video Downloader")
    print("=" * 50)
    print()

def show_menu():
    print("What would you like to download?")
    print()
    print("  1 - 🎥 Download Video (1080p MP4)")
    print("  2 - 🎵 Download Audio Only (MP3)")
    print("  3 - 📋 View Video Information")
    print("  4 - 🚪 Exit")
    print()

def show_video_info(url):
    """Displays video information without downloading."""
    print("\n⏳ Fetching information...")

    ydl_opts = {"quiet": True}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            print("\n📌 Video Information:")
            print("-" * 40)
            print(f"  Title    : {info.get('title', 'Unknown')}")
            print(f"  Channel  : {info.get('uploader', 'Unknown')}")
            print(f"  Duration : {info.get('duration', 0) // 60} minutes {info.get('duration', 0) % 60} seconds")
            print(f"  Views    : {info.get('view_count', 0):,}")
            print(f"  Date     : {info.get('upload_date', '??')}")
            print("-" * 40)
    except Exception as error:
        print(f"\n❌ Error: {error}")

def download_video(url, folder):
    """
    Downloads 1080p video and best audio separately, then merges them
    using a direct FFmpeg subprocess call that forces AAC audio re-encoding.

    Root cause of the 'no audio' bug:
      yt-dlp picks opus/webm as the best audio stream (f251).
      When FFmpeg merges this into an MP4 container without explicit
      re-encoding, opus is not a valid MP4 audio codec — so FFmpeg
      silently drops the audio track. The fix is to call FFmpeg directly
      with -c:a aac to always re-encode audio before muxing into MP4.
    """
    script_dir  = os.path.dirname(os.path.abspath(__file__))
    ffmpeg_path = os.path.join(script_dir, "ffmpeg.exe")
    cookie_file = os.path.join(script_dir, "www.youtube.com_cookies.txt")

    tmp_video = os.path.join(folder, "_tmp_video.%(ext)s")
    tmp_audio = os.path.join(folder, "_tmp_audio.%(ext)s")

    common_opts = {
        "noplaylist"     : True,
        "ffmpeg_location": ffmpeg_path,
        "cookiefile"     : cookie_file,
        "quiet"          : False,
    }

    # ── Step 1: Download video-only stream ─────────────────────────────────
    print("\n⏳ Downloading video stream...")
    try:
        with yt_dlp.YoutubeDL({**common_opts,
                                "format"  : "bestvideo[height<=1080]",
                                "outtmpl" : tmp_video}) as ydl:
            info  = ydl.extract_info(url, download=True)
            title = info.get("title", "video")
    except Exception as error:
        _handle_error(error)
        return

    # ── Step 2: Download audio-only stream ─────────────────────────────────
    print("\n⏳ Downloading audio stream...")
    try:
        with yt_dlp.YoutubeDL({**common_opts,
                                "format"  : "bestaudio",
                                "outtmpl" : tmp_audio}) as ydl:
            ydl.download([url])
    except Exception as error:
        _handle_error(error)
        _cleanup(folder)
        return

    # ── Step 3: Locate the actual files written by yt-dlp ──────────────────
    video_files = glob.glob(os.path.join(folder, "_tmp_video.*"))
    audio_files = glob.glob(os.path.join(folder, "_tmp_audio.*"))

    if not video_files or not audio_files:
        print("\n❌ Could not locate temporary files. Aborting.")
        _cleanup(folder)
        return

    video_file = video_files[0]
    audio_file = audio_files[0]

    # ── Step 4: Build a safe output filename ───────────────────────────────
    safe_title  = "".join(c for c in title if c not in r'\/:*?"<>|').strip()
    output_file = os.path.join(folder, f"{safe_title}.mp4")

    # ── Step 5: FFmpeg merge — copy video, RE-ENCODE audio to AAC ──────────
    #   -c:v copy  → keep original video bitstream (fast, lossless)
    #   -c:a aac   → convert opus/vorbis/any codec → AAC (required for MP4)
    #   -b:a 192k  → 192 kbps audio quality
    #   -movflags +faststart → optimise file for immediate playback
    print("\n🔀 Merging video + audio (encoding audio as AAC for MP4 compatibility)...")

    cmd = [
        ffmpeg_path,
        "-y",                        # overwrite output without asking
        "-i", video_file,            # video-only input
        "-i", audio_file,            # audio-only input
        "-c:v", "copy",              # copy video stream (no re-encode)
        "-c:a", "aac",               # re-encode audio to AAC
        "-b:a", "192k",              # audio bitrate
        "-movflags", "+faststart",   # mp4 streaming optimisation
        output_file,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"\n❌ FFmpeg merge failed:\n{result.stderr[-1000:]}")
            return
    except FileNotFoundError:
        print("\n⚠️  ffmpeg.exe not found!")
        print("   Please ensure ffmpeg.exe is in the same folder as this script.")
        return
    finally:
        # Always clean up temp files, even if merge failed
        _cleanup(folder)

    print("\n✅ Video downloaded successfully!")
    print(f"📁 Saved to: {output_file}")

def download_audio(url, folder):
    """Downloads only the audio from the video and converts it to MP3 using local cookies file."""
    print("\n⏳ Downloading audio, please wait...")

    script_dir  = os.path.dirname(os.path.abspath(__file__))
    ffmpeg_path = os.path.join(script_dir, "ffmpeg.exe")
    cookie_file = os.path.join(script_dir, "www.youtube.com_cookies.txt")

    ydl_opts = {
        "format"         : "bestaudio/best",
        "outtmpl"        : os.path.join(folder, "%(title)s.%(ext)s"),
        "noplaylist"     : True,
        "ffmpeg_location": ffmpeg_path,
        "cookiefile"     : cookie_file,
        "postprocessors" : [
            {
                "key"             : "FFmpegExtractAudio",
                "preferredcodec"  : "mp3",
                "preferredquality": "192",
            }
        ],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print("\n✅ Audio downloaded successfully!")
        print(f"📁 Saved to: {folder}")
    except Exception as error:
        _handle_error(error)

def choose_folder():
    """Determines the save folder."""
    default_path = os.path.join(os.path.expanduser("~"), "Downloads")

    print(f"\n📁 Save folder (Enter = {default_path}):")
    folder = input("   >> ").strip()

    if not folder:
        folder = default_path

    os.makedirs(folder, exist_ok=True)
    return folder

# ── Helpers ────────────────────────────────────────────────────────────────

def _handle_error(error):
    """Prints a user-friendly error message."""
    msg = str(error).lower()
    if "ffmpeg" in msg:
        print("\n⚠️  'ffmpeg' is required!")
        print("   Please ensure ffmpeg.exe is in the same folder as this script.")
    elif "cookie" in msg:
        print("\n⚠️  Cookie file error!")
        print("   Please ensure 'www.youtube.com_cookies.txt' is in the same folder as this script.")
    else:
        print(f"\n❌ An error occurred: {error}")

def _cleanup(folder):
    """Removes leftover temporary video/audio files."""
    for pattern in ("_tmp_video.*", "_tmp_audio.*"):
        for f in glob.glob(os.path.join(folder, pattern)):
            try:
                os.remove(f)
            except OSError:
                pass

# ============================================================
#  MAIN PROGRAM
# ============================================================

print_header()

while True:
    show_menu()

    choice = input("Your choice (1/2/3/4): ").strip()

    if choice == "4":
        print("\n👋 Goodbye!")
        break

    if choice not in ("1", "2", "3"):
        print("\n⚠️  Invalid choice! Please enter 1, 2, 3, or 4.\n")
        continue

    print()
    url = input("🔗 Enter YouTube URL: ").strip()

    if not url:
        print("\n⚠️  URL cannot be empty!\n")
        continue

    if "youtube.com" not in url and "youtu.be" not in url:
        print("\n⚠️  Please enter a valid YouTube link!\n")
        continue

    if choice == "3":
        show_video_info(url)

    elif choice == "1":
        folder = choose_folder()
        download_video(url, folder)

    elif choice == "2":
        folder = choose_folder()
        download_audio(url, folder)

    print()
