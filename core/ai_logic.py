"""
Gemini API for background color suggestion only (no auto crop).
Uses gemini-2.5-flash (free tier 2026); fallback to gemini-2.0-flash if 404.
"""
import json
import logging
import os
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

logger = logging.getLogger(__name__)

THUMBNAIL_MAX_SIZE = 512
MODEL_NAMES = ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash")


class AILogic:
    def __init__(self):
        self.model = None
        api_key = os.getenv("GOOGLE_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(MODEL_NAMES[0])
        else:
            print("Warning: GOOGLE_API_KEY not found in .env")

    def _create_thumbnail(self, image_path, out_path, max_size=THUMBNAIL_MAX_SIZE):
        img = Image.open(image_path).convert("RGB")
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        img.save(out_path, "JPEG", quality=85)
        return img.size

    def _parse_json_response(self, text):
        text = text.strip()
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            text = text[start:end]
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            text = text[start:end]
        return json.loads(text.strip())

    def suggest_background_color(self, image_path=None, pil_image=None):
        """
        Sends a low-res thumbnail to Gemini. Returns only bg_color (hex string).
        Pass image_path=... or pil_image=... (PIL Image); if pil_image, saves to temp first.
        Tries gemini-2.5-flash first; on 404 falls back to gemini-2.0-flash, then gemini-1.5-flash.
        """
        if not self.model or (image_path is None and pil_image is None):
            return None
        temp_dir = Path(__file__).resolve().parent.parent / "assets" / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = temp_dir / "gemini_thumb.jpg"
        try:
            if pil_image is not None:
                img = pil_image.convert("RGB").copy()
                img.thumbnail((THUMBNAIL_MAX_SIZE, THUMBNAIL_MAX_SIZE), Image.Resampling.LANCZOS)
                img.save(str(thumb_path), "JPEG", quality=85)
            else:
                self._create_thumbnail(image_path, str(thumb_path))
        except Exception as e:
            print(f"Thumbnail error: {e}")
            return None
        try:
            thumb_file = genai.upload_file(path=str(thumb_path), display_name="PassportThumb")
        finally:
            if thumb_path.exists():
                thumb_path.unlink(missing_ok=True)
        prompt = """You are an expert in color theory and portrait photography. Analyze this passport/ID-style portrait.

**Step 1: Observe:**
- Skin tone: Analyze the person’s skin in terms relevant to color theory (e.g. undertone, temperature, saturation) so you can reason about which background will flatter it.
- Clothing: Identify the main colors and tone of the outfit so the background can complement the person without clashing or blending with what they wear.

**Step 2: Apply color theory to pick the background:**
- Using color theory (complementary, analogous, contrast, harmony, and how colors interact with skin and clothing), **automatically derive** the single best solid background color. Do not follow a fixed recipe—reason from the observed skin tone and clothing to choose a color that makes the face look natural and the person stand out.
- Ensure the background complements the person (especially the face), avoids clashing with skin or blending with the outfit, and stays professional and suitable for official/ID photos (solid, even, not distracting).

**Step 3: Output:**
Return ONLY a single JSON object with one key: "bg_color" (string, hex including #). No explanation, no markdown outside the JSON.
Example: {"bg_color": "#E8EEF2"}"""
        for name in MODEL_NAMES:
            try:
                model = genai.GenerativeModel(name)
                response = model.generate_content([thumb_file, prompt])
                result = self._parse_json_response(response.text)
                bg_color = result.get("bg_color") or "#FFFFFF"
                logger.info("Gemini background color suggestion: model=%s, bg_color=%s", name, bg_color)
                return bg_color
            except Exception as e:
                err = str(e).lower()
                if "404" in err or "not found" in err:
                    logger.debug("Model %s not available, trying next: %s", name, e)
                    continue
                logger.exception("Error in AI analysis: %s", e)
                return None
        logger.warning("All Gemini models failed; using default bg_color=#FFFFFF")
        return "#FFFFFF"

    def analyze_image(self, image_path):
        """Legacy: same as suggest_background_color, returns dict for compatibility."""
        bg = self.suggest_background_color(image_path)
        return {"bg_color": bg or "#FFFFFF", "crop_points": None, "thumbnail_size": None} if bg is not None else None
