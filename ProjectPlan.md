This project plan outlines a professional-grade Windows application that leverages **Gemini 3 Flash** for aesthetic reasoning and **Python's image ecosystem** for precise manipulation.

---

## 📋 Project Plan: AI Passport Pro

### 1. Requirements

* **Functional:**
* Image upload via GUI (Drag & Drop or File Explorer).
* Gemini-driven analysis for optimal background color (Contrast-based).
* AI-detected cropping for "Head-to-Chest" framing.
* Manual overrides for crop adjustment.
* Single-click PNG export with a 3x4 aspect ratio and professional border.


* **Non-Functional:**
* **Latency:** Background removal and AI analysis should take < 5 seconds.
* **Privacy:** Temporary local storage of images; no cloud storage of user data.



### 2. Dependencies

To build this, you will need to install the following Python packages:

| Library | Purpose |
| --- | --- |
| `google-generativeai` | Connects to Gemini for skin tone/clothing analysis and coordinate detection. |
| `customtkinter` | Provides a modern, "Windows 11" style user interface. |
| `Pillow` (PIL) | The core library for cropping, adding borders, and saving PNGs. |
| `rembg` | Local AI model to remove backgrounds with high precision. |
| `opencv-python` | Used for pre-processing images (resizing/alignment). |
| `python-dotenv` | To securely manage your Gemini API Key. |

---

## 📂 File Structure

Organizing the project this way ensures scalability and makes it easy to debug the AI logic separately from the UI.

```text
PassportAI/
├── .env                # Stores your GOOGLE_API_KEY
├── main.py             # Entry point: Runs the CustomTkinter GUI
├── core/
│   ├── __init__.py
│   ├── ai_logic.py     # Gemini API calls (color analysis, coordinate detection)
│   ├── processor.py    # Image processing (rembg, Pillow cropping, borders)
├── assets/
│   ├── icons/          # App icons and buttons
│   └── temp/           # Temporary storage for processed frames
├── requirements.txt    # List of dependencies
└── README.md           # Documentation

```

---

## 🛠️ Technical Workflow

1. **Stage 1 (Analysis):** The app sends a low-res thumbnail to Gemini. Gemini returns a JSON object containing:
* `bg_color`: The hex code for the background.
* `crop_points`: The estimated -coordinates for the top of the head and the chest.


2. **Stage 2 (Processing):**
* `rembg` isolates the subject.
* `Pillow` creates a new canvas using the `bg_color`.
* The subject is pasted onto the canvas.


3. **Stage 3 (Finalizing):**
* A 3x4 crop is applied based on Gemini's coordinates.
* A 10px white/black border is drawn around the edge.



---

## 📜 Requirements.txt

You can create this file and run `pip install -r requirements.txt` to set up your environment:

```text
google-generativeai
customtkinter
rembg
Pillow
opencv-python
python-dotenv

```

**Would you like me to write the `ai_logic.py` file first, including the specific prompt to get the skin-tone color and crop coordinates from Gemini?**