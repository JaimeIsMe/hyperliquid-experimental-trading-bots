#!/usr/bin/env python3
"""
🚀 Color Trader Web Interface Launcher
Quick startup script for the Color Trader web dashboard
"""

import os
import sys
import subprocess
import webbrowser
import time
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import fastapi
        import uvicorn
        import pyautogui
        from experimental_color_trader import ExperimentalColorTrader
        print("✅ All dependencies are installed!")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("\n🔧 Please install dependencies first:")
        print("pip install -r requirements.txt")
        return False

def check_env_file():
    """Check if .env file exists"""
    if not Path('.env').exists():
        print("⚠️  .env file not found!")
        print("\n🔧 Please create your .env file:")
        print("1. Copy the template: cp .env.example .env")
        print("2. Edit .env and add your HYPERLIQUID_PRIVATE_KEY")
        print("3. Run this script again")
        return False
    print("✅ .env file found!")
    return True

def main():
    print("🎨 Color Trader Web Interface Launcher")
    print("=" * 50)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Check environment file
    if not check_env_file():
        sys.exit(1)
    
    print("\n🚀 Starting web server...")
    print("📱 Dashboard URL: http://localhost:8000")
    print("🔄 The dashboard will open automatically in your browser")
    print("\n⚠️  IMPORTANT NOTES:")
    print("• Make sure your trading indicator is visible on screen")
    print("• The bot will start in PAPER TRADING mode by default")
    print("• Use the calibration tool to set your screen region")
    print("• Set LIVE_TRADING=true in .env when ready for real trading")
    print("\n" + "=" * 50)
    
    # Wait a moment for user to read
    time.sleep(3)
    
    try:
        # Start the web server
        import uvicorn
        
        # Open browser after a short delay
        def open_browser():
            time.sleep(2)
            webbrowser.open('http://localhost:8000')
        
        import threading
        browser_thread = threading.Thread(target=open_browser, daemon=True)
        browser_thread.start()
        
        # Start the server
        uvicorn.run("web_server:app", host="0.0.0.0", port=8000, reload=False)
        
    except KeyboardInterrupt:
        print("\n🛑 Web server stopped by user")
    except Exception as e:
        print(f"\n❌ Error starting web server: {e}")
        print("\n🔧 Try running manually:")
        print("python3 web_server.py")

if __name__ == "__main__":
    main()