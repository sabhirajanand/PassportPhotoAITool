"""
Photoshop-style inline HSV color picker: vertical Hue strip + Saturation/Value 2D area.
"""
import colorsys
import re
import tkinter as tk
import numpy as np
from PIL import Image, ImageTk

import customtkinter as ctk


def hex_to_rgb(hex_str):
    hex_str = (hex_str or "#FFFFFF").strip().lstrip("#")
    if len(hex_str) == 6 and re.match(r"^[0-9A-Fa-f]+$", hex_str):
        return tuple(int(hex_str[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (1, 1, 1)


def rgb_to_hex(r, g, b):
    return "#{:02X}{:02X}{:02X}".format(int(r * 255), int(g * 255), int(b * 255))


def rgb_to_hsv(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return (h * 360, s * 100, v * 100)


def hsv_to_rgb(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h / 360.0, s / 100.0, v / 100.0)
    return (r, g, b)


class HSVPicker(ctk.CTkFrame):
    """
    Two-part picker: vertical Hue strip (right) + Saturation/Value square (left).
    Callback on_change(hex_str) when user picks a color. set_hex(hex_str) to set from outside.
    """

    HUE_STRIP_WIDTH = 24
    SV_BOX_SIZE = (180, 220)

    def __init__(self, parent, initial_hex="#FFFFFF", on_change=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.on_change = on_change
        self._h, self._s, self._v = rgb_to_hsv(*hex_to_rgb(initial_hex))
        self._sv_dragging = False
        self._hue_dragging = False
        self._sv_photo = None
        self._hue_photo = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Saturation (x) / Value (y) box — Value top=100, bottom=0; Saturation left=0, right=100
        sv_container = ctk.CTkFrame(self, fg_color=("gray90", "gray20"), corner_radius=8, width=self.SV_BOX_SIZE[0], height=self.SV_BOX_SIZE[1])
        sv_container.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        sv_container.grid_propagate(False)
        self.sv_canvas = tk.Canvas(
            sv_container, width=self.SV_BOX_SIZE[0], height=self.SV_BOX_SIZE[1],
            highlightthickness=0, bg=("#e8e8e8", "#2a2a2a")[0]
        )
        self.sv_canvas.pack(fill="both", expand=True)
        self.sv_canvas.bind("<Button-1>", self._on_sv_press)
        self.sv_canvas.bind("<B1-Motion>", self._on_sv_drag)
        self.sv_canvas.bind("<ButtonRelease-1>", self._on_sv_release)

        # Hue strip — vertical, top=0°, bottom=360°
        hue_container = ctk.CTkFrame(self, fg_color=("gray90", "gray20"), corner_radius=8, width=self.HUE_STRIP_WIDTH, height=self.SV_BOX_SIZE[1])
        hue_container.grid(row=0, column=1, sticky="nsew")
        hue_container.grid_propagate(False)
        self.hue_canvas = tk.Canvas(
            hue_container, width=self.HUE_STRIP_WIDTH, height=self.SV_BOX_SIZE[1],
            highlightthickness=0
        )
        self.hue_canvas.pack(fill="both", expand=True)
        self.hue_canvas.bind("<Button-1>", self._on_hue_press)
        self.hue_canvas.bind("<B1-Motion>", self._on_hue_drag)

        self._draw_hue_strip()
        self._draw_sv_box()
        self._draw_hue_thumb()
        self._draw_sv_thumb()

    def _draw_hue_strip(self):
        """Vertical rainbow gradient 0–360°."""
        w, h = self.HUE_STRIP_WIDTH, self.SV_BOX_SIZE[1]
        arr = np.zeros((h, w, 3), dtype=np.uint8)
        for i in range(h):
            hue = 360 * (1 - i / h)  # top=0, bottom=360
            r, g, b = hsv_to_rgb(hue, 100, 100)
            arr[i, :] = [int(r * 255), int(g * 255), int(b * 255)]
        img = Image.fromarray(arr, mode="RGB")
        self._hue_photo = ImageTk.PhotoImage(img)
        self.hue_canvas.delete("all")
        self.hue_canvas.create_image(0, 0, anchor="nw", image=self._hue_photo)

    def _draw_sv_box(self):
        """2D gradient: current H, S horizontal (0–100), V vertical (100–0)."""
        w, h = self.SV_BOX_SIZE[0], self.SV_BOX_SIZE[1]
        H = self._h
        arr = []
        for py in range(h):
            v = 100 * (1 - py / h)
            row = []
            for px in range(w):
                s = 100 * (px / w)
                r, g, b = hsv_to_rgb(H, s, v)
                row.append([int(r * 255), int(g * 255), int(b * 255)])
            arr.append(row)
        img = Image.fromarray(np.uint8(arr), mode="RGB")
        self._sv_photo = ImageTk.PhotoImage(img)
        self.sv_canvas.delete("sv_grad")
        self.sv_canvas.create_image(0, 0, anchor="nw", image=self._sv_photo, tags="sv_grad")

    def _draw_hue_thumb(self):
        """Small indicator on hue strip."""
        self.hue_canvas.delete("thumb")
        h = self.SV_BOX_SIZE[1]
        y = h * (1 - self._h / 360)
        y = max(2, min(h - 2, y))
        self.hue_canvas.create_rectangle(0, y - 2, self.HUE_STRIP_WIDTH, y + 2, outline="white", width=2, fill="black", tags="thumb")

    def _draw_sv_thumb(self):
        """Circle/dot on SV box at current S, V."""
        self.sv_canvas.delete("sv_thumb")
        w, h = self.SV_BOX_SIZE[0], self.SV_BOX_SIZE[1]
        x = w * (self._s / 100)
        y = h * (1 - self._v / 100)
        x = max(2, min(w - 2, x))
        y = max(2, min(h - 2, y))
        r = 5
        self.sv_canvas.create_oval(x - r, y - r, x + r, y + r, outline="white", width=2, tags="sv_thumb")
        self.sv_canvas.create_oval(x - r + 1, y - r + 1, x + r - 1, y + r - 1, outline="black", width=1, tags="sv_thumb")

    def _emit(self):
        hex_c = rgb_to_hex(*hsv_to_rgb(self._h, self._s, self._v))
        if self.on_change:
            self.on_change(hex_c)

    def _on_hue_press(self, event):
        self._hue_dragging = True
        self._set_hue_from_y(event.y)

    def _on_hue_drag(self, event):
        if self._hue_dragging:
            self._set_hue_from_y(event.y)

    def _set_hue_from_y(self, y):
        h = self.SV_BOX_SIZE[1]
        self._h = 360 * (1 - max(0, min(1, y / h)))
        self._draw_hue_thumb()
        self._draw_sv_box()
        self._draw_sv_thumb()
        self._emit()

    def _on_sv_press(self, event):
        self._sv_dragging = True
        self._set_sv_from_xy(event.x, event.y)

    def _on_sv_drag(self, event):
        if self._sv_dragging:
            self._set_sv_from_xy(event.x, event.y)

    def _on_sv_release(self, event):
        self._sv_dragging = False

    def _set_sv_from_xy(self, x, y):
        w, h = self.SV_BOX_SIZE[0], self.SV_BOX_SIZE[1]
        self._s = 100 * max(0, min(1, x / w))
        self._v = 100 * (1 - max(0, min(1, y / h)))
        self._draw_sv_thumb()
        self._emit()

    def set_hex(self, hex_str):
        """Set current color from hex (e.g. when Gemini suggests a color)."""
        r, g, b = hex_to_rgb(hex_str)
        self._h, self._s, self._v = rgb_to_hsv(r, g, b)
        self._draw_sv_box()
        self._draw_hue_thumb()
        self._draw_sv_thumb()
