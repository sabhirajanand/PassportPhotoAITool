"""
A4 print preview: Photoshop-style dialog — left = image preview, right = printing options.
Options: printer, margins, rows, printer settings; opens maximized.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import customtkinter as ctk
from PIL import Image

# A4 in mm
A4_W_MM = 210.0
A4_H_MM = 297.0
DEFAULT_MARGIN_MM = 2.0
GAP_MM = 1.5
COLS = 6
ASPECT_W, ASPECT_H = 3, 4
PREVIEW_DPI = 150
PRINT_DPI = 300
OPTIONS_PANEL_WIDTH = 300


def _mm_to_px(mm, dpi):
    return int(mm * dpi / 25.4)


def _compute_layout(rows, margin_mm, gap_mm):
    printable_w_mm = A4_W_MM - 2 * margin_mm
    printable_h_mm = A4_H_MM - 2 * margin_mm
    photo_w_mm = (printable_w_mm - (COLS - 1) * gap_mm) / COLS
    photo_h_mm = photo_w_mm * ASPECT_H / ASPECT_W
    required_h = rows * photo_h_mm + (rows - 1) * gap_mm
    if required_h > printable_h_mm:
        photo_h_mm = (printable_h_mm - (rows - 1) * gap_mm) / rows
        photo_w_mm = photo_h_mm * ASPECT_W / ASPECT_H
    return photo_w_mm, photo_h_mm


def _max_rows(margin_mm, gap_mm=GAP_MM):
    printable_h_mm = A4_H_MM - 2 * margin_mm
    photo_w_mm, photo_h_mm = _compute_layout(1, margin_mm, gap_mm)
    return max(1, int((printable_h_mm + gap_mm) / (photo_h_mm + gap_mm)))


def build_a4_sheet(pil_photo, rows, dpi=PREVIEW_DPI, margin_mm=DEFAULT_MARGIN_MM, gap_mm=GAP_MM):
    sheet_w_px = _mm_to_px(A4_W_MM, dpi)
    sheet_h_px = _mm_to_px(A4_H_MM, dpi)
    margin_px = _mm_to_px(margin_mm, dpi)
    gap_px = _mm_to_px(gap_mm, dpi)
    photo_w_mm, photo_h_mm = _compute_layout(rows, margin_mm, gap_mm)
    photo_w_px = _mm_to_px(photo_w_mm, dpi)
    photo_h_px = _mm_to_px(photo_h_mm, dpi)

    sheet = Image.new("RGB", (sheet_w_px, sheet_h_px), "white")
    img = pil_photo.convert("RGB") if pil_photo.mode != "RGB" else pil_photo
    thumb = img.resize((photo_w_px, photo_h_px), Image.Resampling.LANCZOS)

    for row in range(rows):
        for col in range(COLS):
            x = margin_px + col * (photo_w_px + gap_px)
            y = margin_px + row * (photo_h_px + gap_px)
            sheet.paste(thumb, (x, y))
    return sheet


def _get_printers():
    """Return list of (name, display_name) for dropdown. First is default."""
    try:
        if sys.platform == "darwin":
            out = subprocess.run(
                ["lpstat", "-p"], capture_output=True, text=True, timeout=5
            )
            if out.returncode == 0 and out.stdout:
                names = []
                for line in out.stdout.strip().splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and parts[0] == "printer":
                        names.append(parts[1])
                if names:
                    return [(n, n) for n in names]
        elif sys.platform.startswith("linux"):
            out = subprocess.run(
                ["lpstat", "-p"], capture_output=True, text=True, timeout=5
            )
            if out.returncode == 0 and out.stdout:
                names = []
                for line in out.stdout.strip().splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and parts[0] == "printer":
                        names.append(parts[1])
                if names:
                    return [(n, n) for n in names]
        elif sys.platform == "win32":
            try:
                import win32print
                printers = []
                for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS):
                    printers.append((p[2], p[2]))
                if printers:
                    return printers
            except ImportError:
                pass
    except Exception:
        pass
    return [("default", "Default printer")]


def _open_system_print_dialog(path):
    """Open OS print dialog with the given image file."""
    try:
        if sys.platform == "darwin":
            # Open in Preview and trigger Print (Cmd+P) so user gets full dialog
            subprocess.Popen(["open", "-a", "Preview", path], start_new_session=True)
            subprocess.run(
                [
                    "osascript",
                    "-e", "delay 1.5",
                    "-e", 'tell application "Preview" to activate',
                    "-e", "delay 0.5",
                    "-e", 'tell application "System Events" to keystroke "p" using command down',
                ],
                timeout=10, capture_output=True,
            )
        elif sys.platform == "win32":
            os.startfile(path, "print")
        else:
            subprocess.run(["xdg-open", path], timeout=5, capture_output=True)
    except Exception:
        pass


def _open_printer_settings():
    """Open system printer / printing preferences."""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "x-apple.systempreferences:com.apple.PrintingPrefs"], start_new_session=True)
        elif sys.platform == "win32":
            subprocess.Popen(["rundll32.exe", "printui.dll,PrintUIEntry", "/n"], start_new_session=True)
        else:
            subprocess.Popen(["system-config-printer"], start_new_session=True)
    except Exception:
        pass


class A4PrintPreviewWindow(ctk.CTkToplevel):
    """Photoshop-style: left = preview, right = printer, margins, rows, settings, Print/Close."""

    def __init__(self, parent, pil_photo, **kwargs):
        super().__init__(parent, **kwargs)
        self.title("Print — Passport photos on A4")
        self.pil_photo = pil_photo
        self._sheet_image = None
        self._ctk_img = None
        self._rows = 1
        self._margin_mm = DEFAULT_MARGIN_MM
        self._printers = _get_printers()
        self._max_rows_val = _max_rows(self._margin_mm)

        # Main horizontal split: left = preview, right = options
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, minsize=OPTIONS_PANEL_WIDTH)
        self.grid_rowconfigure(0, weight=1)

        # —— Left: preview ——
        preview_container = ctk.CTkFrame(self, fg_color="#2b2b2b", corner_radius=8)
        preview_container.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        preview_container.grid_columnconfigure(0, weight=1)
        preview_container.grid_rowconfigure(0, weight=1)
        self.preview_label = ctk.CTkLabel(preview_container, text="", fg_color="transparent")
        self.preview_label.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        # —— Right: options ——
        options_frame = ctk.CTkFrame(self, fg_color=("gray92", "gray18"), width=OPTIONS_PANEL_WIDTH, corner_radius=8, border_width=1, border_color=("gray80", "gray30"))
        options_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        options_frame.grid_propagate(False)
        options_frame.grid_columnconfigure(0, weight=1)
        opts = options_frame

        row = 0
        ctk.CTkLabel(opts, text="Print options", font=ctk.CTkFont(size=16, weight="bold")).grid(row=row, column=0, sticky="w", padx=16, pady=(16, 12))
        row += 1

        # Printer
        ctk.CTkLabel(opts, text="Printer:", font=ctk.CTkFont(size=13)).grid(row=row, column=0, sticky="w", padx=16, pady=(8, 4))
        row += 1
        self.printer_var = ctk.StringVar(value=self._printers[0][0] if self._printers else "default")
        self.printer_menu = ctk.CTkOptionMenu(
            opts, variable=self.printer_var, values=[p[1] for p in self._printers],
            width=OPTIONS_PANEL_WIDTH - 32, height=32, corner_radius=6
        )
        self.printer_menu.grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 12))
        row += 1

        # Margins (mm)
        ctk.CTkLabel(opts, text="Margin (mm):", font=ctk.CTkFont(size=13)).grid(row=row, column=0, sticky="w", padx=16, pady=(8, 4))
        row += 1
        margin_row = ctk.CTkFrame(opts, fg_color="transparent")
        margin_row.grid(row=row, column=0, sticky="w", padx=16, pady=(0, 12))
        self.margin_entry = ctk.CTkEntry(margin_row, width=80, height=32, placeholder_text=str(DEFAULT_MARGIN_MM))
        self.margin_entry.insert(0, str(int(DEFAULT_MARGIN_MM)))
        self.margin_entry.pack(side="left", padx=(0, 8))
        self.margin_entry.bind("<KeyRelease>", lambda e: self._on_margin_change())
        ctk.CTkLabel(margin_row, text="(all sides)", font=ctk.CTkFont(size=11), text_color="gray").pack(side="left")
        row += 1

        # Rows on sheet
        ctk.CTkLabel(opts, text="Rows on sheet:", font=ctk.CTkFont(size=13)).grid(row=row, column=0, sticky="w", padx=16, pady=(8, 4))
        row += 1
        row_control = ctk.CTkFrame(opts, fg_color="transparent")
        row_control.grid(row=row, column=0, sticky="w", padx=16, pady=(0, 12))
        ctk.CTkButton(row_control, text="−", width=40, height=36, corner_radius=8, command=self._decrease).pack(side="left", padx=(0, 4))
        self.rows_label = ctk.CTkLabel(row_control, text="1", font=ctk.CTkFont(size=18, weight="bold"), width=48)
        self.rows_label.pack(side="left", padx=4, pady=0)
        ctk.CTkButton(row_control, text="+", width=40, height=36, corner_radius=8, command=self._increase).pack(side="left", padx=(4, 0))
        self.rows_hint = ctk.CTkLabel(row_control, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self.rows_hint.pack(side="left", padx=4, pady=0)
        row += 1

        # Printer settings (paper type, quality, etc. — opens system dialog)
        ctk.CTkButton(
            opts, text="Printer settings…", command=_open_printer_settings,
            width=OPTIONS_PANEL_WIDTH - 32, height=32, corner_radius=8,
            fg_color="transparent", border_width=1
        ).grid(row=row, column=0, sticky="ew", padx=16, pady=(8, 12))
        row += 1

        ctk.CTkLabel(opts, text="Paper type, print quality, and other options are set in your system printer settings.", font=ctk.CTkFont(size=11), text_color="gray", wraplength=OPTIONS_PANEL_WIDTH - 32).grid(row=row, column=0, sticky="w", padx=16, pady=(0, 16))
        row += 1

        # Buttons at bottom of options
        opts.grid_rowconfigure(row, weight=1)
        btn_frame = ctk.CTkFrame(opts, fg_color="transparent")
        btn_frame.grid(row=row + 1, column=0, sticky="ew", padx=16, pady=(0, 16))
        btn_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(btn_frame, text="Print…", command=self._print_with_dialog, width=120, height=40, corner_radius=8, fg_color="#10b981").pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_frame, text="Close", command=self.destroy, width=80, height=40, corner_radius=8).pack(side="left")

        self._update_rows_hint()
        self._redraw()
        self.after(100, self._maximize)
        self.bind("<Configure>", self._on_resize)
        self._resize_job = None

    def _on_resize(self, event):
        if event.widget != self:
            return
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(150, self._redraw_after_resize)

    def _redraw_after_resize(self):
        self._resize_job = None
        self._redraw()

    def _maximize(self):
        try:
            self.update_idletasks()
            if sys.platform == "win32":
                self.state("zoomed")
            else:
                w = self.winfo_screenwidth()
                h = self.winfo_screenheight()
                self.geometry(f"{w}x{h}+0+0")
        except Exception:
            self.geometry("1200x800")

    def _get_margin_mm(self):
        try:
            v = float(self.margin_entry.get().strip())
            return max(0, min(25, v))
        except ValueError:
            return DEFAULT_MARGIN_MM

    def _on_margin_change(self):
        self._margin_mm = self._get_margin_mm()
        self._max_rows_val = _max_rows(self._margin_mm)
        self._update_rows_hint()
        if self._rows > self._max_rows_val:
            self._rows = self._max_rows_val
            self.rows_label.configure(text=str(self._rows))
        self._redraw()

    def _update_rows_hint(self):
        self.rows_hint.configure(text=f"(max {self._max_rows_val})")

    def _decrease(self):
        if self._rows > 1:
            self._rows -= 1
            self.rows_label.configure(text=str(self._rows))
            self._redraw()

    def _increase(self):
        if self._rows < self._max_rows_val:
            self._rows += 1
            self.rows_label.configure(text=str(self._rows))
            self._redraw()

    def _redraw(self):
        margin = self._get_margin_mm()
        self._sheet_image = build_a4_sheet(self.pil_photo, self._rows, margin_mm=margin)
        w, h = self._sheet_image.size
        # Size to fit left panel
        self.update_idletasks()
        pw = self.winfo_width() - OPTIONS_PANEL_WIDTH - 40
        ph = self.winfo_height() - 40
        if pw < 100:
            pw = 600
        if ph < 100:
            ph = 700
        r = min(pw / w, ph / h, 1.0)
        dw, dh = int(w * r), int(h * r)
        disp = self._sheet_image.resize((dw, dh), Image.Resampling.LANCZOS) if r < 1 else self._sheet_image
        dw, dh = disp.size
        self._ctk_img = ctk.CTkImage(light_image=disp, size=(dw, dh))
        self.preview_label.configure(image=self._ctk_img, text="")

    def _print_with_dialog(self):
        """Save at 300 DPI and open system print dialog so user can choose printer, paper, etc."""
        if self.pil_photo is None:
            return
        margin = self._get_margin_mm()
        sheet_300 = build_a4_sheet(self.pil_photo, self._rows, dpi=PRINT_DPI, margin_mm=margin)
        fd, path = tempfile.mkstemp(suffix=".png")
        try:
            os.close(fd)
            sheet_300.save(path)
            _open_system_print_dialog(path)
        except Exception:
            try:
                os.unlink(path)
            except Exception:
                pass

    def _print_direct(self):
        """Print directly to selected printer (no dialog). Kept for fallback."""
        if self._sheet_image is None:
            return
        margin = self._get_margin_mm()
        sheet_300 = build_a4_sheet(self.pil_photo, self._rows, dpi=PRINT_DPI, margin_mm=margin)
        fd, path = tempfile.mkstemp(suffix=".png")
        try:
            os.close(fd)
            sheet_300.save(path)
            printer = self.printer_var.get()
            if sys.platform == "win32":
                os.startfile(path, "print")
            else:
                if printer and printer != "default":
                    subprocess.run(["lp", "-d", printer, path], check=False)
                else:
                    subprocess.run(["lp", path], check=False)
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass


def open_a4_preview(parent, pil_photo):
    w = A4PrintPreviewWindow(parent, pil_photo)
    w.focus_set()
