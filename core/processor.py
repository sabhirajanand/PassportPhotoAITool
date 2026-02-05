"""
Image processing: crop, background removal, background color, optional border, export.
Triple-model removal: u2net_human_seg + u2net + u2net_cloth_seg run in parallel.
Human + u2net agree on body; cloth model recovers clothing and edges. Combined mask
= (human ∩ u2net) ∪ cloth, then alpha matting.
"""
import io
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageColor, ImageOps
from rembg import remove, new_session
from rembg.bg import alpha_matting_cutout, naive_cutout, post_process as rembg_post_process

BORDER_PX = 10  # 10px professional border (5 white + 5 black) when enabled

# Three rembg sessions (lazy-loaded)
_REMBG_SESSION_A = None   # u2net_human_seg – portrait/body
_REMBG_SESSION_B = None  # u2net – general
_REMBG_SESSION_C = None  # u2net_cloth_seg – clothing and edges


def _get_rembg_session_a():
    """Lazy-load u2net_human_seg for portrait foreground."""
    global _REMBG_SESSION_A
    if _REMBG_SESSION_A is None:
        _REMBG_SESSION_A = new_session("u2net_human_seg")
    return _REMBG_SESSION_A


def _get_rembg_session_b():
    """Lazy-load u2net for second opinion on foreground."""
    global _REMBG_SESSION_B
    if _REMBG_SESSION_B is None:
        _REMBG_SESSION_B = new_session("u2net")
    return _REMBG_SESSION_B


def _get_rembg_session_c():
    """Lazy-load u2net_cloth_seg for clothing and edge detection."""
    global _REMBG_SESSION_C
    if _REMBG_SESSION_C is None:
        _REMBG_SESSION_C = new_session("u2net_cloth_seg")
    return _REMBG_SESSION_C


def _head_chest_from_face_opencv(pil_image_rgba):
    """Fallback: OpenCV face → head/chest coords. Used only if needed elsewhere."""
    try:
        rgb = pil_image_rgba.convert("RGB")
        arr = np.array(rgb)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        h, w = gray.shape
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        face_cascade = cv2.CascadeClassifier(cascade_path)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        if len(faces) == 0:
            return None
        x, y, fw, fh = max(faces, key=lambda r: r[2] * r[3])
        head_top = max(0, int(y - 0.3 * fh))
        chest_bottom = min(h, int(y + fh * 2.2))
        return {"head_top": head_top, "chest_bottom": chest_bottom}
    except Exception:
        return None


class ImageProcessor:
    def __init__(self):
        pass

    def crop_image(self, pil_image, box):
        """
        Crop PIL image by box. box = (left, top, right, bottom) in image coords.
        Returns PIL Image (same mode as input).
        """
        if pil_image is None:
            return None
        L, T, R, B = box
        w, h = pil_image.size
        L = max(0, min(L, w - 1))
        T = max(0, min(T, h - 1))
        R = max(L + 1, min(R, w))
        B = max(T + 1, min(B, h))
        return pil_image.crop((L, T, R, B))

    def get_mask_a(self, pil_image):
        """Get foreground mask from first model (u2net_human_seg). Returns PIL L mode."""
        if pil_image is None:
            return None
        img = pil_image.convert("RGB") if pil_image.mode != "RGB" else pil_image
        session = _get_rembg_session_a()
        masks = session.predict(img)
        return masks[0] if masks else None

    def get_mask_b(self, pil_image):
        """Get foreground mask from second model (u2net). Returns PIL L mode."""
        if pil_image is None:
            return None
        img = pil_image.convert("RGB") if pil_image.mode != "RGB" else pil_image
        session = _get_rembg_session_b()
        masks = session.predict(img)
        return masks[0] if masks else None

    def get_mask_cloth(self, pil_image):
        """Get foreground mask from cloth model (u2net_cloth_seg). Better for clothing and edges. Returns PIL L mode."""
        if pil_image is None:
            return None
        img = pil_image.convert("RGB") if pil_image.mode != "RGB" else pil_image
        session = _get_rembg_session_c()
        masks = session.predict(img)
        return masks[0] if masks else None

    def combine_masks_and_cutout(
        self,
        pil_image,
        mask_a,
        mask_b,
        mask_cloth=None,
        alpha_matting=True,
        alpha_matting_fg_threshold=240,
        alpha_matting_bg_threshold=10,
        alpha_matting_erode_size=8,
        post_process_mask=True,
    ):
        """
        Combine foreground masks and cut out the subject.
        Base = (mask_a ∩ mask_b). If mask_cloth is provided: combined = base ∪ cloth
        so clothing and edges from the cloth model are included. Returns RGBA PIL.
        """
        if pil_image is None or mask_a is None or mask_b is None:
            return None
        img = pil_image.convert("RGB") if pil_image.mode != "RGB" else pil_image
        # Ensure same size
        if mask_a.size != mask_b.size:
            mask_b = mask_b.resize(mask_a.size, Image.Resampling.LANCZOS)
        a = np.array(mask_a, dtype=np.float32)
        b = np.array(mask_b, dtype=np.float32)
        base = np.minimum(a, b)
        if mask_cloth is not None:
            if mask_cloth.size != mask_a.size:
                mask_cloth = mask_cloth.resize(mask_a.size, Image.Resampling.LANCZOS)
            cloth = np.array(mask_cloth, dtype=np.float32)
            # Include clothing/edges: keep pixel if (body) or (cloth says foreground)
            combined = np.maximum(base, cloth).clip(0, 255).astype(np.uint8)
        else:
            combined = base.clip(0, 255).astype(np.uint8)
        combined_pil = Image.fromarray(combined, mode="L")
        if post_process_mask:
            combined_pil = Image.fromarray(rembg_post_process(combined))
        try:
            if alpha_matting:
                cutout = alpha_matting_cutout(
                    img,
                    combined_pil,
                    alpha_matting_fg_threshold,
                    alpha_matting_bg_threshold,
                    alpha_matting_erode_size,
                )
            else:
                cutout = naive_cutout(img, combined_pil)
        except Exception:
            cutout = naive_cutout(img, combined_pil)
        return cutout.convert("RGBA") if cutout.mode != "RGBA" else cutout

    def remove_background_from_pil(self, pil_image):
        """
        Single-model removal (fallback). Uses u2net_human_seg + alpha matting.
        Prefer running get_mask_a + get_mask_b in parallel and combine_masks_and_cutout for better quality.
        """
        if pil_image is None:
            return None
        if pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")
        session = _get_rembg_session_a()
        try:
            out = remove(
                pil_image,
                session=session,
                alpha_matting=True,
                alpha_matting_foreground_threshold=240,
                alpha_matting_background_threshold=10,
                alpha_matting_erode_size=8,
                post_process_mask=True,
            )
        except Exception:
            out = remove(
                pil_image,
                session=session,
                alpha_matting=False,
                post_process_mask=True,
            )
        if out is None:
            return None
        if isinstance(out, bytes):
            out = Image.open(io.BytesIO(out))
        return out.convert("RGBA")

    def remove_background(self, input_image_path):
        """Remove background from file path. Returns RGBA PIL."""
        img = Image.open(input_image_path).convert("RGB")
        return self.remove_background_from_pil(img)

    def upscale_for_quality(self, pil_image, factor=2):
        """
        Enlarge image by factor using high-quality Lanczos resampling.
        Adds more pixels so zooming doesn't show blockiness. factor=2 doubles width/height.
        """
        if pil_image is None or factor <= 1:
            return pil_image
        w, h = pil_image.size
        new_w, new_h = int(w * factor), int(h * factor)
        return pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)

    def apply_background(self, pil_rgba, bg_hex):
        """
        Paste subject (RGBA) onto a canvas filled with bg_hex. Returns RGB PIL.
        """
        if pil_rgba is None:
            return None
        if bg_hex and str(bg_hex).startswith("#"):
            bg_rgb = ImageColor.getrgb(bg_hex)
        else:
            bg_rgb = (255, 255, 255)
        w, h = pil_rgba.size
        canvas = Image.new("RGBA", (w, h), bg_rgb)
        canvas.paste(pil_rgba, (0, 0), pil_rgba)
        out = Image.new("RGB", (w, h), bg_rgb)
        out.paste(canvas, mask=pil_rgba.split()[3])
        return out

    def add_border(self, pil_image, border_px=0):
        """
        Add professional border (5px white + 5px black) if border_px > 0.
        border_px=0 means no border. Returns RGB PIL.
        """
        if pil_image is None or border_px <= 0:
            return pil_image.convert("RGB") if pil_image else None
        half = border_px // 2
        img = ImageOps.expand(pil_image, border=half, fill="white")
        img = ImageOps.expand(img, border=half, fill="black")
        return img.convert("RGB")

    def export_png(self, pil_image, save_path):
        if pil_image is None:
            return False
        try:
            path = Path(save_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            pil_image.save(path, "PNG")
            return True
        except Exception as e:
            print(f"Error saving PNG: {e}")
            return False
