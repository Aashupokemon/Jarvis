#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  JARVIS Setup & Run Script
#  Run this once to install everything, then use: python jarvis.py
# ─────────────────────────────────────────────────────────────────────────────

set -e

echo ""
echo "╔═══════════════════════════════════════════╗"
echo "║   J.A.R.V.I.S  —  Setup Script          ║"
echo "╚═══════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "❌ Python 3 not found. Install it from https://www.python.org/downloads/"
    exit 1
fi
PYTHON=$(command -v python3)
echo "✅ Python: $($PYTHON --version)"

# Check pip
if ! $PYTHON -m pip --version &>/dev/null; then
    echo "❌ pip not found. Install pip first."
    exit 1
fi

# Create venv (optional but recommended)
if [ ! -d "venv" ]; then
    echo "🔧 Creating virtual environment..."
    $PYTHON -m venv venv
fi

# Activate venv
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    source venv/Scripts/activate
else
    source venv/bin/activate
fi
echo "✅ Virtual environment active."

# Upgrade pip
pip install --upgrade pip -q

# Install core packages first
echo ""
echo "📦 Installing core packages..."
pip install requests psutil pyttsx3 -q

# Install Whisper (speech recognition)
echo "📦 Installing Whisper (offline speech recognition)..."
pip install openai-whisper sounddevice soundfile numpy -q

# FFmpeg check (needed by Whisper)
if ! command -v ffmpeg &>/dev/null; then
    echo ""
    echo "⚠️  FFmpeg not found. Whisper needs it."
    echo "   Ubuntu/Debian:  sudo apt install ffmpeg"
    echo "   macOS:          brew install ffmpeg"
    echo "   Windows:        https://ffmpeg.org/download.html"
fi

# Optional: screenshot support
echo "📦 Installing screenshot support..."
pip install pyautogui pillow -q 2>/dev/null || echo "   (pyautogui optional — skip if it fails)"

# Phase 4: tray GUI
echo "📦 Installing system tray support..."
pip install pystray -q 2>/dev/null || echo "   (pystray optional — skip if it fails)"

# Phase 4: Google APIs (Gmail + Calendar)
echo "📦 Installing Google API client (Gmail + Calendar)..."
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client -q \
    2>/dev/null || echo "   (Google API client optional — skip if it fails)"

echo ""
echo "═══════════════════════════════════════════"
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Get your Anthropic API key: https://console.anthropic.com"
echo "  2. Run Jarvis (terminal mode):  python jarvis.py"
echo "     Or tray mode (background):   python jarvis_tray.py"
echo "  3. Optional:    export ANTHROPIC_API_KEY=your_key_here"
echo "  4. Optional Phase 4 setup:"
echo "     - Email/Calendar: see email_calendar.py header for Google OAuth steps"
echo "     - Screen vision: works out of the box once pyautogui is installed"
echo "     - Custom skills: edit skills.json"
echo "     - Plugins: drop .py files into plugins/"
echo "═══════════════════════════════════════════"
echo ""

# Ask if user wants to run now
read -p "🚀 Run Jarvis now? (y/n): " run
if [[ "$run" == "y" || "$run" == "Y" ]]; then
    python jarvis.py
fi
