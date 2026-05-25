#!/usr/bin/env python3
"""
Helper script to extract cookies from your browser for authenticated YouTube access.

This script helps bypass YouTube's anti-bot detection by using your account's
authenticated session. Run this BEFORE using the transcriber.

Usage:
    python get_cookies.py
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def get_cookies_instructions() -> str:
    """Return instructions for extracting cookies from browser."""
    return """
╔════════════════════════════════════════════════════════════════════════════╗
║                    EXTRACT COOKIES FOR AUTHENTICATED ACCESS                ║
╚════════════════════════════════════════════════════════════════════════════╝

This will enable authenticated YouTube access to bypass anti-bot blocking.

OPTION 1: Using yt-dlp's built-in cookie extraction (Recommended for Chrome)
═══════════════════════════════════════════════════════════════════════════

Run this command:
    yt-dlp --cookies-from-browser chrome --extract-flat=no -j "https://www.youtube.com/watch?v=jNQXAC9IVRw" > /dev/null

This will:
1. Open a browser prompt (may require authentication)
2. Automatically extract cookies from Chrome
3. Save them to cookies.txt in the project root


OPTION 2: Manual cookie extraction using browser extension
═══════════════════════════════════════════════════════════════════════════

1. Install "Get cookies.txt" extension:
   - Chrome: https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndcbcohxjaoxxc51l/
   - Firefox: https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/

2. Log into YouTube in your browser (if not already logged in)

3. Click the extension button → "Export" → Save as "cookies.txt"

4. Move cookies.txt to your project root:
   C:\\Users\\{your_username}\\ProjectCode\\YoutubeToArticle\\cookies.txt

5. Verify it's in the right place:
   - You should see: cookies.txt at project root
   - Run the transcriber again


OPTION 3: Using yt-dlp CLI directly
═══════════════════════════════════════════════════════════════════════════

If you have Chrome/Firefox open and logged into YouTube:

    yt-dlp --cookies-from-browser chrome -o "test.mp4" "https://www.youtube.com/watch?v=jNQXAC9IVRw"

Replace "chrome" with "firefox" if using Firefox.


VERIFICATION
═══════════════════════════════════════════════════════════════════════════

After getting cookies.txt:
1. Check that cookies.txt exists in project root
2. Run the transcriber - it will automatically use the cookies
3. You should see: "Using authenticated cookies from: cookies.txt"


TROUBLESHOOTING
═══════════════════════════════════════════════════════════════════════════

- If still getting 403 errors: YouTube may have invalidated your session.
  Try logging out and back in, then re-export cookies.

- Cookies expire after ~3 weeks of inactivity
  Keep cookies.txt updated for persistent access.

- If browser extension doesn't work: Use yt-dlp's --cookies-from-browser option
  (requires browser to be open)

═══════════════════════════════════════════════════════════════════════════
"""


def main() -> None:
    """Display cookie extraction instructions."""
    print(get_cookies_instructions())
    
    # Check if cookies.txt already exists
    if Path("cookies.txt").exists():
        print("✅ cookies.txt found in project root!")
        print("   Your app will use authenticated access on next run.")
    else:
        print("⚠️  No cookies.txt found. Follow the instructions above to extract cookies.")
        print("   Once you have cookies.txt, place it in the project root directory.")


if __name__ == "__main__":
    main()
