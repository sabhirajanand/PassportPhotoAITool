"""
Zoom and pan image widget: canvas with zoom in/out buttons, scrollbars when zoomed,
mouse wheel zoom, and click-drag pan. For Step 2 and Step 3 preview areas.
"""
import tkinter as tk
from PIL import Image, ImageTk

import customtkinter as ctk


class ZoomPanImage(ctk.CTkFrame):
    """
    Displays a PIL image with zoom (buttons + mouse wheel) and pan (drag + scrollbars).
    Call set_image(pil_image) to set the image. Placeholder text when no image.
    """

    MIN_ZOOM = 0.0
    MAX_ZOOM = 4.0
    ZOOM_STEP = 1.25

    def __init__(self, parent, width=500, height=400, placeholder_text="Image will appear here", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._width = width
        self._height = height
        self._placeholder = placeholder_text
        self._pil_image = None
        self._photo = None
        self._zoom = 1.0
        self._image_id = None
        self._drag_start = None
        self._canvas_bg = ("#2b2b2b", "#1a1a2e")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Toolbar: centered [ Zoom out ] [ % ] [ Zoom in ]
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        toolbar.grid_columnconfigure(0, weight=1)
        toolbar.grid_columnconfigure(4, weight=1)
        ctk.CTkButton(toolbar, text="− Zoom out", command=self._zoom_out, width=100, height=28, corner_radius=6).grid(row=0, column=1, padx=(0, 4))
        self._zoom_label = ctk.CTkLabel(toolbar, text="100%", font=ctk.CTkFont(size=11), text_color="gray")
        self._zoom_label.grid(row=0, column=2, padx=8)
        ctk.CTkButton(toolbar, text="+ Zoom in", command=self._zoom_in, width=100, height=28, corner_radius=6).grid(row=0, column=3, padx=(4, 0))

        # Canvas + scrollbars (use tk.Frame so scrollbars work)
        canvas_container = tk.Frame(self, bg=self._canvas_bg[0])
        canvas_container.grid(row=1, column=0, sticky="nsew")
        canvas_container.grid_columnconfigure(0, weight=1)
        canvas_container.grid_rowconfigure(0, weight=1)

        self._v_scroll = tk.Scrollbar(canvas_container)
        self._v_scroll.grid(row=0, column=1, sticky="ns")
        self._h_scroll = tk.Scrollbar(canvas_container, orient=tk.HORIZONTAL)
        self._h_scroll.grid(row=1, column=0, sticky="ew")
        self._canvas = tk.Canvas(
            canvas_container,
            width=width,
            height=height,
            bg=self._canvas_bg[0],
            highlightthickness=0,
            yscrollcommand=self._v_scroll.set,
            xscrollcommand=self._h_scroll.set,
        )
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._v_scroll.config(command=self._canvas.yview)
        self._h_scroll.config(command=self._canvas.xview)

        self._canvas.create_text(width // 2, height // 2, text=placeholder_text, fill="gray", font=("", 13), tags="placeholder")
        self._canvas.create_image(0, 0, anchor="nw", tags="image")

        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._canvas.bind("<Button-4>", self._on_wheel_linux)
        self._canvas.bind("<Button-5>", self._on_wheel_linux)
        self._canvas.bind("<Button-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)

    def _on_wheel(self, event):
        if self._pil_image is None:
            return
        delta = event.delta
        if delta > 0:
            self._zoom_in()
        else:
            self._zoom_out()

    def _on_wheel_linux(self, event):
        if self._pil_image is None:
            return
        if event.num == 4:
            self._zoom_in()
        elif event.num == 5:
            self._zoom_out()

    def _on_press(self, event):
        self._drag_start = (event.x, event.y)

    def _on_drag(self, event):
        if self._drag_start is None:
            return
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        self._canvas.xview_scroll(-dx, "units")
        self._canvas.yview_scroll(-dy, "units")
        self._drag_start = (event.x, event.y)

    def _on_release(self, event):
        self._drag_start = None

    def _zoom_in(self):
        if self._pil_image is None:
            return
        self._zoom = min(self.MAX_ZOOM, self._zoom * self.ZOOM_STEP)
        self._redraw()

    def _zoom_out(self):
        if self._pil_image is None:
            return
        self._zoom = max(self.MIN_ZOOM, self._zoom / self.ZOOM_STEP)
        self._redraw()

    def _redraw(self):
        if self._pil_image is None:
            self._canvas.itemconfig("placeholder", state=tk.NORMAL)
            self._canvas.itemconfig("image", state=tk.HIDDEN)
            self._zoom_label.configure(text="—")
            return
        self._canvas.itemconfig("placeholder", state=tk.HIDDEN)
        self._canvas.itemconfig("image", state=tk.NORMAL)
        pil = self._pil_image
        w, h = pil.size
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw <= 1:
            cw = self._width
        if ch <= 1:
            ch = self._height
        # Limit display size to avoid huge PhotoImage (e.g. max 3000 px)
        max_side = 3000
        scale = max(self._zoom, 0.01)  # avoid 0-size display
        disp_w = int(w * scale)
        disp_h = int(h * scale)
        if disp_w > max_side or disp_h > max_side:
            r = max_side / max(disp_w, disp_h)
            disp_w = int(disp_w * r)
            disp_h = int(disp_h * r)
        if disp_w < 1 or disp_h < 1:
            disp_w, disp_h = max(1, disp_w), max(1, disp_h)
        disp_pil = pil.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(disp_pil)
        self._canvas.itemconfig("image", image=self._photo)
        # Virtual size: at least canvas size so we can center when image is smaller
        total_w = max(disp_w, cw)
        total_h = max(disp_h, ch)
        # Center image when smaller than view (vertical center if disp_h < ch, horizontal if disp_w < cw)
        img_x = (total_w - disp_w) // 2
        img_y = (total_h - disp_h) // 2
        self._canvas.coords("image", img_x, img_y)
        self._canvas.configure(scrollregion=(0, 0, total_w, total_h))
        self._zoom_label.configure(text=f"{int(self._zoom * 100)}%")
        # Show/hide scrollbars based on whether content is larger than canvas
        if total_w > cw or total_h > ch:
            self._h_scroll.grid()
            self._v_scroll.grid()
        else:
            self._h_scroll.grid_remove()
            self._v_scroll.grid_remove()

    def set_image(self, pil_image):
        """Set the image to display. None clears and shows placeholder."""
        self._pil_image = pil_image
        if pil_image is None:
            self._zoom = 1.0
        else:
            # Initial zoom: fit-to-view when image is larger than canvas, else 100%.
            # Never auto-increase above 100% (user must click Zoom in to zoom in).
            w, h = pil_image.size
            cw, ch = self._width, self._height
            fit = min(cw / w, ch / h)
            self._zoom = max(self.MIN_ZOOM, min(fit, 1.0))
        self._redraw()

    def get_image(self):
        """Return the current PIL image (or None)."""
        return self._pil_image
