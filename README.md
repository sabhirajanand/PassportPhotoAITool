# PassportAI

A professional-grade application for creating passport photos using Gemini AI and Python.

**Supported platforms:** macOS, Windows, Ubuntu (and most Linux desktops).

## Setup

1.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
2.  Set up your Google API Key in `.env`:
    ```
    GOOGLE_API_KEY=your_api_key_here
    ```
3.  Run the application:
    ```bash
    python main.py
    ```
   On macOS, the app sets `TK_SILENCE_DEPRECATION=1` automatically to suppress the system Tk warning.

## Features

-   Image upload via GUI
-   AI-driven background color analysis
-   Automatic cropping
-   Background removal
-   Export to PNG
