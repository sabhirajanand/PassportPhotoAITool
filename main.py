"""
PassportAI – Modern 3-step flow: (1) Add & crop, (2) Remove bg (optional) + color, (3) Border & export.
CTkImage for HighDPI; drag-to-crop canvas; modern UI.
"""
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tkinter as tk
import customtkinter as ctk
from PIL import Image

from crop_canvas import CropCanvas
from hsv_picker import HSVPicker
from installer import is_first_run, run_installer_if_first_run, _get_app_data_dir
from zoom_pan_image import ZoomPanImage

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

# Log Gemini background color suggestions to console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

# When frozen (PyInstaller): bundle root is read-only; use app data for temp
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys._MEIPASS)
    TEMP_DIR = _get_app_data_dir() / "temp"
else:
    APP_DIR = Path(__file__).resolve().parent
    TEMP_DIR = APP_DIR / "assets" / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

CROP_RATIOS = [
    ("Free", None),
    ("1:1", (1, 1)),
    ("3:4", (3, 4)),
    ("4:3", (4, 3)),
    ("4:6", (4, 6)),
    ("6:4", (6, 4)),
    ("5:7", (5, 7)),
    ("7:5", (7, 5)),
]

BORDER_PX = 10
PREVIEW_SIZE = 380  # max dimension so image stays contained in preview area
MAX_PREVIEW_HEIGHT = 400
UPSCALE_FACTOR = 2  # Enlarge after background for better quality when zooming

# Modern palette
COLORS = {
    "bg": ("#f0f2f5", "#1a1a2e"),
    "card": ("#ffffff", "#16213e"),
    "accent": "#6366f1",
    "accent_hover": "#4f46e5",
    "text": ("#1f2937", "#e2e8f0"),
    "text_muted": ("#6b7280", "#94a3b8"),
    "success": "#10b981",
    "border": ("#e5e7eb", "#2d3748"),
    "status_success": "#059669",
    "status_error": "#dc2626",
    "status_warning": "#d97706",
    "status_info": ("#6b7280", "#94a3b8"),
}

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PassportAI")
        self.geometry("960x780")
        self.minsize(800, 640)

        self._ai = None
        self._processor = None

        self.source_path = None
        self.original_image = None
        self.step1_cropped = None
        self.step2_with_bg = None
        self.cached_rgba = None  # no-background image for Step 2 color change
        self.step2_bg_color = None  # current background hex
        self.step2_bg_source = None  # "api" | "default" | "custom"
        self._ctk_images = []
        self._processing = False
        self._crop_ratio_index = 2  # default 3:4 (passport)

        self._build_ui()

    def _get_processor(self):
        """Lazy-load ImageProcessor (pulls in rembg/cv2/numpy on first use)."""
        if self._processor is None:
            from core.processor import ImageProcessor
            self._processor = ImageProcessor()
        return self._processor

    def _get_ai(self):
        """Lazy-load AILogic (pulls in google.generativeai on first use)."""
        if self._ai is None:
            from core.ai_logic import AILogic
            self._ai = AILogic()
        return self._ai

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.configure(fg_color=COLORS["bg"])

        # Header: title (left), status message (top right), step indicator below
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=16)
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text="PassportAI",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="w", padx=0, pady=(0, 4))

        self.status_var = ctk.StringVar(value="")
        self._status_label = ctk.CTkLabel(
            header, textvariable=self.status_var,
            font=ctk.CTkFont(size=13),
            text_color=COLORS["status_info"][0] if isinstance(COLORS["status_info"], tuple) else COLORS["status_info"],
        )
        self._status_label.grid(row=0, column=1, sticky="e", padx=0, pady=(0, 4))

        self._step_indicator = ctk.CTkFrame(header, fg_color="transparent")
        self._step_indicator.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self._step_dots = []
        for i in range(3):
            f = ctk.CTkFrame(self._step_indicator, width=36, height=36, corner_radius=18, fg_color=COLORS["border"])
            f.grid(row=0, column=i * 2, padx=2, pady=0)
            lbl = ctk.CTkLabel(f, text=str(i + 1), font=ctk.CTkFont(size=12, weight="bold"), text_color=COLORS["text_muted"])
            lbl.place(relx=0.5, rely=0.5, anchor="center")
            f._label = lbl
            self._step_dots.append(f)
            if i < 2:
                ctk.CTkLabel(self._step_indicator, text="  →  ", font=ctk.CTkFont(size=14), text_color=COLORS["text_muted"]).grid(row=0, column=i * 2 + 1, padx=0)

        self.steps_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.steps_frame.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 24))
        self.steps_frame.grid_columnconfigure(0, weight=1)
        self.steps_frame.grid_rowconfigure(0, weight=1)

        # ----- Step 1 -----
        self.step1_frame = ctk.CTkFrame(self.steps_frame, fg_color="transparent")
        self.step1_frame.grid(row=0, column=0, sticky="nsew")
        self.step1_frame.grid_columnconfigure(0, weight=1)
        self.step1_frame.grid_rowconfigure(2, weight=1)

        card1 = ctk.CTkFrame(self.step1_frame, fg_color=COLORS["card"], corner_radius=12, border_width=1, border_color=COLORS["border"])
        card1.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        card1.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(card1, text="📷  Add photo", command=self._select_image, width=140, height=36, corner_radius=8, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"]).grid(row=0, column=0, padx=16, pady=12)
        ctk.CTkLabel(card1, text="Aspect ratio:", font=ctk.CTkFont(size=13), text_color=COLORS["text"]).grid(row=0, column=1, sticky="w", padx=(16, 8), pady=12)
        self.ratio_var = ctk.StringVar(value=CROP_RATIOS[2][0])  # 3:4 default
        self.ratio_menu = ctk.CTkOptionMenu(card1, variable=self.ratio_var, values=[r[0] for r in CROP_RATIOS], command=self._on_ratio_change, width=100, height=32, corner_radius=8)
        self.ratio_menu.grid(row=0, column=2, padx=8, pady=12)

        crop_hint = ctk.CTkLabel(
            self.step1_frame,
            text="Drag on the image to draw a selection, then drag corners or edges to resize. Drag inside to move.",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"],
        )
        crop_hint.grid(row=1, column=0, sticky="w", padx=0, pady=(0, 8))

        canvas_frame = ctk.CTkFrame(self.step1_frame, fg_color=COLORS["card"], corner_radius=12, border_width=1, border_color=COLORS["border"])
        canvas_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 12))
        canvas_frame.grid_columnconfigure(0, weight=1)
        canvas_frame.grid_rowconfigure(0, weight=1)
        self.crop_canvas = CropCanvas(canvas_frame, width=560, height=400)
        self.crop_canvas.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

        step1_btns = ctk.CTkFrame(self.step1_frame, fg_color="transparent")
        step1_btns.grid(row=3, column=0, sticky="ew", pady=12)
        step1_btns.grid_columnconfigure(0, weight=1)
        self.btn_step1_next = ctk.CTkButton(step1_btns, text="Next → Step 2", command=self._go_step2, width=140, height=36, corner_radius=8, state="disabled", fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        self.btn_step1_next.grid(row=0, column=1, padx=0, pady=0)

        # ----- Step 2 -----
        self.step2_frame = ctk.CTkFrame(self.steps_frame, fg_color="transparent")
        self.step2_frame.grid(row=0, column=0, sticky="nsew")
        self.step2_frame.grid_columnconfigure(0, weight=1)
        self.step2_frame.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(self.step2_frame, text="Remove background (optional) and set background color", font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["text"]).grid(row=0, column=0, sticky="w", padx=0, pady=(0, 12))
        step2_btns = ctk.CTkFrame(self.step2_frame, fg_color="transparent")
        step2_btns.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        step2_btns.grid_columnconfigure(0, weight=1)
        self.btn_remove_bg = ctk.CTkButton(step2_btns, text="Remove background & suggest color", command=self._run_step2, width=240, height=40, corner_radius=8, state="disabled", fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        self.btn_remove_bg.grid(row=0, column=0, padx=0, pady=(0, 8))
        # Content: left = preview, right = Photoshop-style HSV picker
        step2_content = ctk.CTkFrame(self.step2_frame, fg_color="transparent")
        step2_content.grid(row=2, column=0, sticky="nsew", pady=(0, 12))
        step2_content.grid_columnconfigure(0, weight=1)
        step2_content.grid_rowconfigure(0, weight=1)
        self.preview_frame_2 = ctk.CTkFrame(step2_content, fg_color=COLORS["card"], corner_radius=12, border_width=1, border_color=COLORS["border"], height=MAX_PREVIEW_HEIGHT)
        self.preview_frame_2.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.preview_frame_2.grid_propagate(False)
        self.preview_frame_2.grid_columnconfigure(0, weight=1)
        self.preview_frame_2.grid_rowconfigure(0, weight=1)
        self.preview_zoom_2 = ZoomPanImage(self.preview_frame_2, width=540, height=MAX_PREVIEW_HEIGHT - 50, placeholder_text="Cropped image will appear here")
        self.preview_zoom_2.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        # Step 2 loader overlay (rotating spinner over preview while removing background)
        self.step2_loader_overlay = ctk.CTkFrame(self.preview_frame_2, fg_color=COLORS["card"], corner_radius=12, border_width=1, border_color=COLORS["border"])
        self._step2_loader_angle = 0
        self._step2_loader_job = None
        loader_inner = ctk.CTkFrame(self.step2_loader_overlay, fg_color="transparent")
        loader_inner.place(relx=0.5, rely=0.5, anchor="center")
        self.step2_loader_canvas = tk.Canvas(loader_inner, width=56, height=56, highlightthickness=0)
        self.step2_loader_canvas.pack(pady=(0, 12))
        self._step2_loader_arc_id = None
        ctk.CTkLabel(loader_inner, text="Removing background…", font=ctk.CTkFont(size=14), text_color=COLORS["text_muted"]).pack()
        # Right: Photoshop-style Hue + Saturation/Value picker
        step2_picker_frame = ctk.CTkFrame(step2_content, fg_color="transparent", width=220)
        step2_picker_frame.grid(row=0, column=1, sticky="nsew")
        step2_picker_frame.grid_propagate(False)
        ctk.CTkLabel(step2_picker_frame, text="Background color", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLORS["text"]).pack(anchor="w", pady=(0, 8))
        self.step2_hsv_picker = HSVPicker(step2_picker_frame, initial_hex="#FFFFFF", on_change=self._on_picker_color_change)
        self.step2_hsv_picker.pack(anchor="w")
        # Selected color (below picker)
        selected_row = ctk.CTkFrame(step2_picker_frame, fg_color="transparent")
        selected_row.pack(anchor="w", pady=(16, 0))
        ctk.CTkLabel(selected_row, text="Selected color", font=ctk.CTkFont(size=12), text_color=COLORS["text_muted"]).pack(side="left", padx=(0, 8))
        self.step2_color_swatch = ctk.CTkFrame(selected_row, width=28, height=28, corner_radius=6, fg_color="#FFFFFF", border_width=1, border_color=COLORS["border"])
        self.step2_color_swatch.pack(side="left", padx=(0, 6))
        self.step2_color_label = ctk.CTkLabel(selected_row, text="#FFFFFF", font=ctk.CTkFont(size=12), text_color=COLORS["text"])
        self.step2_color_label.pack(side="left")
        # Gemini suggested color with Apply button (shown when we have a suggestion)
        self.step2_gemini_suggested_hex = None
        self.step2_gemini_row = ctk.CTkFrame(step2_picker_frame, fg_color="transparent")
        self.step2_gemini_row.pack(anchor="w", pady=(12, 0))
        ctk.CTkLabel(self.step2_gemini_row, text="Suggested by Gemini", font=ctk.CTkFont(size=12), text_color=COLORS["text_muted"]).pack(side="left", padx=(0, 8))
        self.step2_gemini_swatch = ctk.CTkFrame(self.step2_gemini_row, width=28, height=28, corner_radius=6, fg_color="#FFFFFF", border_width=1, border_color=COLORS["border"])
        self.step2_gemini_swatch.pack(side="left", padx=(0, 8))
        self.btn_apply_gemini = ctk.CTkButton(self.step2_gemini_row, text="Apply", command=self._apply_gemini_suggested_color, width=70, height=28, corner_radius=6, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        self.btn_apply_gemini.pack(side="left")
        self.step2_gemini_row.pack_forget()  # show only after we have a suggestion
        step2_nav = ctk.CTkFrame(self.step2_frame, fg_color="transparent")
        step2_nav.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        step2_nav.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(step2_nav, text="← Previous", command=self._go_step1, width=100, height=36, corner_radius=8).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=0)
        self.btn_step2_next = ctk.CTkButton(step2_nav, text="Next → Step 3", command=self._go_step3, width=140, height=36, corner_radius=8, state="disabled", fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        self.btn_step2_next.grid(row=0, column=1, sticky="w", padx=0, pady=0)

        # ----- Step 3 -----
        self.step3_frame = ctk.CTkFrame(self.steps_frame, fg_color="transparent")
        self.step3_frame.grid(row=0, column=0, sticky="nsew")
        self.step3_frame.grid_columnconfigure(0, weight=1)
        self.step3_frame.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(self.step3_frame, text="Add border (optional) and export", font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["text"]).grid(row=0, column=0, sticky="w", padx=0, pady=(0, 12))
        self.border_check_var = ctk.BooleanVar(value=True)
        step3_opts = ctk.CTkFrame(self.step3_frame, fg_color="transparent")
        step3_opts.grid(row=1, column=0, sticky="w", pady=(0, 12))
        ctk.CTkCheckBox(step3_opts, text="Add 10px border (white + black)", variable=self.border_check_var, command=self._preview_step3, font=ctk.CTkFont(size=13)).grid(row=0, column=0, sticky="w", padx=0, pady=0)
        self.preview_frame_3 = ctk.CTkFrame(self.step3_frame, fg_color=COLORS["card"], corner_radius=12, border_width=1, border_color=COLORS["border"], height=MAX_PREVIEW_HEIGHT)
        self.preview_frame_3.grid(row=2, column=0, sticky="nsew", pady=(0, 12))
        self.preview_frame_3.grid_propagate(False)
        self.preview_frame_3.grid_columnconfigure(0, weight=1)
        self.preview_frame_3.grid_rowconfigure(0, weight=1)
        self.preview_zoom_3 = ZoomPanImage(self.preview_frame_3, width=540, height=MAX_PREVIEW_HEIGHT - 50, placeholder_text="Final preview")
        self.preview_zoom_3.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        step3_nav = ctk.CTkFrame(self.step3_frame, fg_color="transparent")
        step3_nav.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        step3_nav.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(step3_nav, text="← Previous", command=self._back_to_step2, width=100, height=40, corner_radius=8).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=0)
        self.btn_export = ctk.CTkButton(step3_nav, text="Export PNG", command=self._export_png, width=140, height=40, corner_radius=8, state="disabled", fg_color=COLORS["success"])
        self.btn_export.grid(row=0, column=1, sticky="w", padx=(0, 8), pady=0)
        self.btn_a4_print = ctk.CTkButton(step3_nav, text="Print on A4", command=self._open_a4_preview, width=110, height=40, corner_radius=8, state="disabled", fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        self.btn_a4_print.grid(row=0, column=2, sticky="w", padx=(0, 6), pady=0)
        
        self._update_step_indicator(1)
        self._show_step(1)
        self.update_idletasks()
        self.after(50, lambda: (self.update_idletasks(), self.update()))

    def _update_step_indicator(self, active_step):
        for i, dot in enumerate(self._step_dots):
            if i + 1 == active_step:
                dot.configure(fg_color=COLORS["accent"])
                if hasattr(dot, "_label"):
                    dot._label.configure(text_color="white")
            else:
                dot.configure(fg_color=COLORS["border"])
                if hasattr(dot, "_label"):
                    dot._label.configure(text_color=COLORS["text_muted"])

    def _show_step(self, n):
        self.step1_frame.grid_remove()
        self.step2_frame.grid_remove()
        self.step3_frame.grid_remove()
        self._update_step_indicator(n)
        if n == 1:
            self.step1_frame.grid(row=0, column=0, sticky="nsew")
        elif n == 2:
            self.step2_frame.grid(row=0, column=0, sticky="nsew")
        else:
            self.step3_frame.grid(row=0, column=0, sticky="nsew")
            self._preview_step3()

    def _set_status(self, msg, kind="info"):
        """Show a status message in the top-right. kind: 'success' | 'error' | 'warning' | 'info'."""
        self.status_var.set(msg)
        if kind == "success":
            self._status_label.configure(text_color=COLORS["status_success"])
        elif kind == "error":
            self._status_label.configure(text_color=COLORS["status_error"])
        elif kind == "warning":
            self._status_label.configure(text_color=COLORS["status_warning"])
        else:
            color = COLORS["status_info"]
            self._status_label.configure(text_color=color[0] if isinstance(color, tuple) else color)  # info = muted
        self.update_idletasks()

    def _draw_step2_loader(self):
        """Draw one frame of the rotating spinner on the Step 2 loader canvas."""
        if self._step2_loader_arc_id is not None:
            self.step2_loader_canvas.delete(self._step2_loader_arc_id)
        self.step2_loader_canvas.delete("all")
        mode = ctk.get_appearance_mode()
        border_outline = COLORS["border"][0] if mode == "Light" else COLORS["border"][1]
        r = 24
        cx, cy = 28, 28
        self.step2_loader_canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=border_outline, width=2)
        start = self._step2_loader_angle % 360
        self._step2_loader_arc_id = self.step2_loader_canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r, start=start, extent=270,
            outline=COLORS["accent"], width=3, style=tk.ARC
        )
        self._step2_loader_angle = (self._step2_loader_angle + 12) % 360

    def _animate_step2_loader(self):
        """Schedule next spinner frame; called every 50ms while overlay is visible."""
        if not self._processing:
            return
        self._draw_step2_loader()
        self._step2_loader_job = self.after(50, self._animate_step2_loader)

    def _show_step2_loader(self):
        """Show rotating loader overlay over Step 2 preview."""
        mode = ctk.get_appearance_mode()
        canvas_bg = COLORS["card"][0] if mode == "Light" else COLORS["card"][1]
        self.step2_loader_canvas.configure(bg=canvas_bg)
        self.step2_loader_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._step2_loader_angle = 0
        self._draw_step2_loader()
        self._step2_loader_job = self.after(50, self._animate_step2_loader)

    def _hide_step2_loader(self):
        """Hide loader overlay and stop animation."""
        if self._step2_loader_job:
            self.after_cancel(self._step2_loader_job)
            self._step2_loader_job = None
        self.step2_loader_overlay.place_forget()

    def _select_image(self):
        path = ctk.filedialog.askopenfilename(title="Select photo", filetypes=[("Images", " ".join("*" + e for e in IMAGE_EXT)), ("All", "*.*")])
        if path and Path(path).suffix.lower() in IMAGE_EXT:
            self._load_image(path)

    def _load_image(self, path):
        try:
            had_previous = self.step1_cropped is not None or self.step2_with_bg is not None
            self.original_image = Image.open(path).convert("RGB")
            self.source_path = path
            self.step1_cropped = None
            self.step2_with_bg = None
            self.cached_rgba = None
            self.step2_bg_color = None
            self.step2_bg_source = None
            self.crop_canvas.set_ratio(CROP_RATIOS[self._crop_ratio_index][1])
            self.crop_canvas.set_image(self.original_image)
            self.btn_step1_next.configure(state="normal")
            self._show_step(1)
            if had_previous:
                self._set_status(f"Loaded: {Path(path).name}. Adjust crop and click Next.", "success")
            else:
                self._set_status(f"Loaded: {Path(path).name}. Drag to select area, then click Next.", "success")
        except Exception as e:
            self._set_status(f"Error loading image: {e}", "error")

    def _on_ratio_change(self, choice):
        for i, (label, ratio) in enumerate(CROP_RATIOS):
            if label == choice:
                self._crop_ratio_index = i
                break
        self.crop_canvas.set_ratio(CROP_RATIOS[self._crop_ratio_index][1])
        if self.original_image is not None:
            self.crop_canvas.set_image(self.original_image)

    def _go_step1(self):
        """Back from Step 2 to Step 1. Crop canvas keeps previous selection (no reload)."""
        self._show_step(1)

    def _go_step2(self):
        """From Step 1 to Step 2. Apply crop from current selection and show cropped image in Step 2."""
        if self.original_image is None:
            return
        box = self.crop_canvas.get_crop_box()
        self.step1_cropped = self._get_processor().crop_image(self.original_image, box)
        self._show_step(2)
        self._show_preview_pil(self.preview_zoom_2, self.step1_cropped)
        self.btn_remove_bg.configure(state="normal")
        self.btn_step2_next.configure(state="normal")  # allow skipping bg removal

    def _back_to_step2(self):
        """Back from Step 3 to Step 2."""
        self._show_step(2)
        if self.step2_with_bg is not None:
            self._show_preview_pil(self.preview_zoom_2, self.step2_with_bg)
        else:
            self._show_preview_pil(self.preview_zoom_2, self.step1_cropped)
        self.btn_remove_bg.configure(state="normal")
        self.btn_step2_next.configure(state="normal")  # can always go to Step 3 (with or without bg removal)

    def _run_step2(self):
        if self.step1_cropped is None or self._processing:
            return
        self._processing = True
        self.btn_remove_bg.configure(state="disabled")
        self._set_status("Removing background…", "info")
        self._show_step2_loader()

        def run():
            t0 = time.perf_counter()
            try:
                img = self.step1_cropped
                # Run three models (body + body + cloth) and Gemini in parallel
                with ThreadPoolExecutor(max_workers=4) as ex:
                    future_mask_a = ex.submit(self._get_processor().get_mask_a, img)
                    future_mask_b = ex.submit(self._get_processor().get_mask_b, img)
                    future_mask_cloth = ex.submit(self._get_processor().get_mask_cloth, img)
                    future_bg = ex.submit(self._get_ai().suggest_background_color, pil_image=img)
                    mask_a = future_mask_a.result()
                    mask_b = future_mask_b.result()
                    mask_cloth = future_mask_cloth.result()
                    bg = future_bg.result()
                self.step2_bg_source = "api" if bg is not None else "default"
                if bg is None:
                    bg = "#FFFFFF"
                self.step2_gemini_suggested_hex = bg  # store so user can re-apply via Apply
                self.after(0, lambda: self._set_status("Combining masks and refining edges…", "info"))
                rgba = self._get_processor().combine_masks_and_cutout(
                    img, mask_a, mask_b, mask_cloth=mask_cloth,
                    alpha_matting=True,
                    post_process_mask=True,
                )
                self.cached_rgba = rgba
                self.step2_bg_color = bg
                step2_rgb = self._get_processor().apply_background(rgba, bg)
                self.step2_with_bg = self._get_processor().upscale_for_quality(step2_rgb, UPSCALE_FACTOR)
                elapsed = time.perf_counter() - t0
                self.after(0, lambda: self._hide_step2_loader())
                self.after(0, lambda: self._update_step2_color_ui())
                self.after(0, lambda: self._show_preview_pil(self.preview_zoom_2, self.step2_with_bg))
                self.after(0, lambda: self.btn_step2_next.configure(state="normal"))
                self.after(0, lambda: self._set_status(f"Done in {elapsed:.1f}s. Change background color if you like, then Next → Step 3.", "success"))
            except Exception as e:
                self.after(0, lambda: self._hide_step2_loader())
                self.after(0, lambda: self._set_status(f"Error: {e}", "error"))
                self.after(0, lambda: self.btn_remove_bg.configure(state="normal"))
            finally:
                self._processing = False

        threading.Thread(target=run, daemon=True).start()

    def _update_step2_color_ui(self):
        hex_color = self.step2_bg_color or "#FFFFFF"
        self.step2_color_swatch.configure(fg_color=hex_color)
        self.step2_color_label.configure(text=hex_color)
        if hasattr(self, "step2_hsv_picker") and self.step2_hsv_picker.winfo_exists():
            self.step2_hsv_picker.set_hex(hex_color)
        if self.step2_gemini_suggested_hex:
            self.step2_gemini_swatch.configure(fg_color=self.step2_gemini_suggested_hex)
            self.step2_gemini_row.pack(anchor="w", pady=(12, 0))
        else:
            self.step2_gemini_row.pack_forget()

    def _apply_gemini_suggested_color(self):
        """Apply the Gemini-suggested background color."""
        if self.step2_gemini_suggested_hex:
            self._apply_bg_color(self.step2_gemini_suggested_hex)

    def _on_picker_color_change(self, hex_color):
        """Called when user changes color via the HSV picker."""
        self._apply_bg_color(hex_color)

    def _apply_bg_color(self, hex_color):
        if self.cached_rgba is None:
            return
        if not hex_color.startswith("#"):
            hex_color = "#" + hex_color
        self.step2_bg_color = hex_color
        self.step2_bg_source = "custom"
        step2_rgb = self._get_processor().apply_background(self.cached_rgba, hex_color)
        self.step2_with_bg = self._get_processor().upscale_for_quality(step2_rgb, UPSCALE_FACTOR)
        self._update_step2_color_ui()
        self._show_preview_pil(self.preview_zoom_2, self.step2_with_bg)
        self._set_status("Background color updated.", "success")

    def _get_image_for_step3(self):
        """Image to use for Step 3: with bg removal if done, otherwise cropped image."""
        if self.step2_with_bg is not None:
            return self.step2_with_bg
        return self.step1_cropped

    def _go_step3(self):
        if self._get_image_for_step3() is None:
            return
        self._show_step(3)
        self._preview_step3()
        self.btn_export.configure(state="normal")
        is_passport_34 = self._crop_ratio_index == 2
        self.btn_a4_print.configure(state="normal" if is_passport_34 else "disabled")

    def _preview_step3(self):
        img = self._get_image_for_step3()
        if img is None:
            return
        add_border = self.border_check_var.get()
        img = self._get_processor().add_border(img, BORDER_PX if add_border else 0)
        self._show_preview_pil(self.preview_zoom_3, img)

    def _export_png(self):
        img = self._get_image_for_step3()
        if img is None:
            return
        add_border = self.border_check_var.get()
        img = self._get_processor().add_border(img, BORDER_PX if add_border else 0)
        path = ctk.filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png"), ("All", "*.*")], initialdir=os.path.expanduser("~"))
        if path:
            ok = self._get_processor().export_png(img, path)
            self._set_status("Saved: " + path if ok else "Save failed.", "success" if ok else "error")

    def _open_a4_preview(self):
        img = self._get_image_for_step3()
        if img is None or self._crop_ratio_index != 2:
            return
        add_border = self.border_check_var.get()
        img = self._get_processor().add_border(img, BORDER_PX if add_border else 0)
        from a4_print_preview import open_a4_preview
        open_a4_preview(self, img)

    def _show_preview_pil(self, widget, pil_image):
        """Show PIL image in preview. widget is ZoomPanImage (set_image) or legacy label."""
        if hasattr(widget, "set_image"):
            widget.set_image(pil_image)
            return
        if pil_image is None:
            widget.configure(image=None, text="No image")
            return
        pil = pil_image
        max_side = min(PREVIEW_SIZE, MAX_PREVIEW_HEIGHT - 40)
        r = min(max_side / pil.width, max_side / pil.height, 1.0)
        w = int(pil.width * r)
        h = int(pil.height * r)
        if r < 1:
            pil = pil.resize((w, h), Image.Resampling.LANCZOS)
        ctk_img = ctk.CTkImage(light_image=pil, size=(w, h))
        self._ctk_images = [img for img in self._ctk_images if img is not None][-4:]
        self._ctk_images.append(ctk_img)
        widget.configure(image=ctk_img, text="")


def _get_initial_file_from_args():
    """Return first valid image path from sys.argv (for 'Open with' / drag-drop)."""
    for i in range(1, len(sys.argv)):
        path = sys.argv[i]
        if path and os.path.isfile(path) and Path(path).suffix.lower() in IMAGE_EXT:
            return path
    return None


if __name__ == "__main__":
    # Use launcher for splash screen and deferred loading (better startup UX)
    import launch
    launch.main()
