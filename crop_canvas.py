"""
Drag-to-select crop canvas: show image, draw selection, drag to move or resize (mobile-style).
Uses tk.Canvas for drawing and mouse events. Returns crop box in image coords.
"""
import tkinter as tk
from PIL import Image, ImageTk


HANDLE_R = 8
# Tk Canvas does not support 8-digit hex (alpha); use solid dark overlay
OVERLAY_COLOR = "#333333"
BORDER_COLOR = "#00a8ff"
BORDER_WIDTH = 2
HANDLE_COLOR = "#00a8ff"
HANDLE_OUTLINE = "#ffffff"


class CropCanvas(tk.Canvas):
    """
    Canvas showing an image and a draggable/resizable crop rectangle.
    - Drag inside rect to move.
    - Drag corners/edges to resize (aspect locked when ratio is set).
    - get_crop_box() returns (left, top, right, bottom) in original image coords.
    """

    def __init__(self, parent, width=500, height=500, **kwargs):
        super().__init__(parent, width=width, height=height, **kwargs)
        self._img_w = self._img_h = 0
        self._scale = 1.0
        self._offset_x = self._offset_y = 0
        self._display_w = self._display_h = 0
        self._photo = None
        self._image_id = None
        self._overlay_ids = []
        self._rect_id = None
        self._handle_ids = []
        self._ratio = None  # (w, h) or None for free
        self._drag = None  # "move" | "resize_nw" | "resize_n" | ...
        self._start_xy = None
        self._start_rect = None
        # Selection in display coords: [x1, y1, x2, y2]
        self._rect = [0, 0, width, height]
        self.configure(bg="#1a1a2e", highlightthickness=0)
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

    def set_ratio(self, ratio):
        """ratio = (w, h) or None for free."""
        self._ratio = ratio

    def set_image(self, pil_image):
        """Display PIL image; fit inside canvas and init selection to full image."""
        if pil_image is None:
            self._clear_image()
            return
        self._img_w, self._img_h = pil_image.size
        cw = int(self.cget("width"))
        ch = int(self.cget("height"))
        self._scale = min(cw / self._img_w, ch / self._img_h, 1.0)
        self._display_w = int(self._img_w * self._scale)
        self._display_h = int(self._img_h * self._scale)
        self._offset_x = (cw - self._display_w) // 2
        self._offset_y = (ch - self._display_h) // 2
        disp = pil_image.resize((self._display_w, self._display_h), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(disp)
        self._clear_image()
        self._image_id = self.create_image(self._offset_x, self._offset_y, image=self._photo, anchor="nw")
        self.lower(self._image_id)
        self._rect = [
            self._offset_x, self._offset_y,
            self._offset_x + self._display_w, self._offset_y + self._display_h,
        ]
        if self._ratio:
            self._constrain_rect_to_ratio()
        self._redraw_selection()

    def _clear_image(self):
        if self._image_id:
            self.delete(self._image_id)
            self._image_id = None
        self._delete_selection()

    def _delete_selection(self):
        for i in self._overlay_ids:
            self.delete(i)
        self._overlay_ids.clear()
        if self._rect_id:
            self.delete(self._rect_id)
            self._rect_id = None
        for i in self._handle_ids:
            self.delete(i)
        self._handle_ids.clear()

    def _constrain_rect_to_ratio(self):
        if not self._ratio:
            return
        rw, rh = self._ratio
        x1, y1, x2, y2 = self._rect
        w = x2 - x1
        h = y2 - y1
        if w <= 0 or h <= 0:
            return
        target_r = rw / rh
        if w / h > target_r:
            new_w = int(h * target_r)
            x1 = (x1 + x2 - new_w) // 2
            x2 = x1 + new_w
        else:
            new_h = int(w / target_r)
            y1 = (y1 + y2 - new_h) // 2
            y2 = y1 + new_h
        self._rect = [x1, y1, x2, y2]
        self._clamp_rect_to_image()

    def _clamp_rect_to_image(self):
        x1, y1, x2, y2 = self._rect
        x1 = max(self._offset_x, min(x1, self._offset_x + self._display_w - 1))
        y1 = max(self._offset_y, min(y1, self._offset_y + self._display_h - 1))
        x2 = max(x1 + 1, min(x2, self._offset_x + self._display_w))
        y2 = max(y1 + 1, min(y2, self._offset_y + self._display_h))
        self._rect = [x1, y1, x2, y2]

    def _redraw_selection(self):
        self._delete_selection()
        x1, y1, x2, y2 = self._rect
        cw = int(self.cget("width"))
        ch = int(self.cget("height"))
        # Dark overlay outside selection (4 rectangles)
        self._overlay_ids.append(self.create_rectangle(0, 0, cw, y1, fill=OVERLAY_COLOR, outline=""))
        self._overlay_ids.append(self.create_rectangle(0, y2, cw, ch, fill=OVERLAY_COLOR, outline=""))
        self._overlay_ids.append(self.create_rectangle(0, y1, x1, y2, fill=OVERLAY_COLOR, outline=""))
        self._overlay_ids.append(self.create_rectangle(x2, y1, cw, y2, fill=OVERLAY_COLOR, outline=""))
        self._rect_id = self.create_rectangle(x1, y1, x2, y2, outline=BORDER_COLOR, width=BORDER_WIDTH)
        # Handles at corners and mid-edges
        handles = [
            (x1, y1, "nw"), ((x1 + x2) // 2, y1, "n"), (x2, y1, "ne"),
            (x2, (y1 + y2) // 2, "e"), (x2, y2, "se"), ((x1 + x2) // 2, y2, "s"),
            (x1, y2, "sw"), (x1, (y1 + y2) // 2, "w"),
        ]
        for hx, hy, _ in handles:
            r = HANDLE_R
            self._handle_ids.append(
                self.create_oval(hx - r, hy - r, hx + r, hy + r, fill=HANDLE_COLOR, outline=HANDLE_OUTLINE, width=2)
            )
        if self._image_id:
            self.tag_lower(self._image_id)

    def _hit_handle(self, x, y):
        x1, y1, x2, y2 = self._rect
        handles = [
            (x1, y1, "nw"), ((x1 + x2) // 2, y1, "n"), (x2, y1, "ne"),
            (x2, (y1 + y2) // 2, "e"), (x2, y2, "se"), ((x1 + x2) // 2, y2, "s"),
            (x1, y2, "sw"), (x1, (y1 + y2) // 2, "w"),
        ]
        for hx, hy, name in handles:
            if (x - hx) ** 2 + (y - hy) ** 2 <= (HANDLE_R + 4) ** 2:
                return name
        return None

    def _inside_rect(self, x, y):
        x1, y1, x2, y2 = self._rect
        return x1 <= x <= x2 and y1 <= y <= y2

    def _on_press(self, event):
        h = self._hit_handle(event.x, event.y)
        if h:
            self._drag = "resize_" + h
        elif self._inside_rect(event.x, event.y):
            self._drag = "move"
        else:
            self._drag = "new"
            self._rect = [event.x, event.y, event.x, event.y]
        self._start_xy = (event.x, event.y)
        self._start_rect = list(self._rect)

    def _on_drag(self, event):
        if self._drag is None:
            return
        dx = event.x - self._start_xy[0]
        dy = event.y - self._start_xy[1]
        if self._drag == "move":
            self._rect = [
                self._start_rect[0] + dx, self._start_rect[1] + dy,
                self._start_rect[2] + dx, self._start_rect[3] + dy,
            ]
            self._clamp_rect_to_image()
        elif self._drag == "new":
            self._rect = [
                min(self._start_xy[0], event.x), min(self._start_xy[1], event.y),
                max(self._start_xy[0], event.x), max(self._start_xy[1], event.y),
            ]
            self._clamp_rect_to_image()
            if self._ratio:
                self._constrain_rect_to_ratio()
        elif self._drag and self._drag.startswith("resize_"):
            which = self._drag.replace("resize_", "")
            x1, y1, x2, y2 = list(self._start_rect)
            if "e" in which:
                x2 = event.x
            if "w" in which:
                x1 = event.x
            if "s" in which:
                y2 = event.y
            if "n" in which:
                y1 = event.y
            if x1 > x2:
                x1, x2 = x2, x1
            if y1 > y2:
                y1, y2 = y2, y1
            self._rect = [x1, y1, x2, y2]
            if self._ratio:
                self._constrain_rect_to_ratio()
            else:
                self._clamp_rect_to_image()
        self._redraw_selection()

    def _on_release(self, event):
        if self._drag == "new":
            x1, y1, x2, y2 = self._rect
            if abs(x2 - x1) < 20 or abs(y2 - y1) < 20:
                self._rect = [
                    self._offset_x, self._offset_y,
                    self._offset_x + self._display_w, self._offset_y + self._display_h,
                ]
                if self._ratio:
                    self._constrain_rect_to_ratio()
        self._drag = None
        self._redraw_selection()

    def get_crop_box(self):
        """Return (left, top, right, bottom) in original image pixel coords."""
        if self._scale <= 0:
            return (0, 0, self._img_w, self._img_h)
        x1, y1, x2, y2 = self._rect
        img_x1 = int((x1 - self._offset_x) / self._scale)
        img_y1 = int((y1 - self._offset_y) / self._scale)
        img_x2 = int((x2 - self._offset_x) / self._scale)
        img_y2 = int((y2 - self._offset_y) / self._scale)
        img_x1 = max(0, min(img_x1, self._img_w - 1))
        img_y1 = max(0, min(img_y1, self._img_h - 1))
        img_x2 = max(img_x1 + 1, min(img_x2, self._img_w))
        img_y2 = max(img_y1 + 1, min(img_y2, self._img_h))
        return (img_x1, img_y1, img_x2, img_y2)
