"""
A4 print preview: Photoshop-style dialog — left = image preview, right = printing options.
Options: printer, margins, rows, printer settings; opens maximized.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk

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
    """Return list of (name, display_name) for dropdown. Raises on error (no fallback)."""
    if sys.platform == "darwin" or sys.platform.startswith("linux"):
        out = subprocess.run(
            ["lpstat", "-p"], capture_output=True, text=True, timeout=5
        )
        if out.returncode != 0:
            err = (out.stderr or out.stdout or "lpstat failed").strip()
            raise RuntimeError(f"Could not list printers: {err}")
        names = []
        for line in (out.stdout or "").strip().splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] == "printer":
                names.append(parts[1])
        if not names:
            raise RuntimeError("No printers found. Install CUPS / add a printer.")
        return [(n, n) for n in names]

    if sys.platform == "win32":
        try:
            import win32print
        except ImportError as e:
            raise RuntimeError(
                "pywin32 is required to list printers on Windows. "
                "Install with: pip install pywin32"
            ) from e
        # PRINTER_ENUM_LOCAL works reliably; CONNECTIONS/NETWORK can fail on some systems
        flags = win32print.PRINTER_ENUM_LOCAL
        printers = []
        try:
            # Level 1: returns tuple (flags, description, name, comment) per printer
            for p in win32print.EnumPrinters(flags, None, 1):
                name = p[2] if isinstance(p, (tuple, list)) else p.get("pPrinterName")
                if name:
                    printers.append((name, name))
        except Exception:
            pass
        if not printers:
            try:
                # Level 2: returns list of dicts with 'pPrinterName'
                for p in win32print.EnumPrinters(flags, None, 2):
                    name = p.get("pPrinterName") if isinstance(p, dict) else (p[2] if len(p) > 2 else None)
                    if name:
                        printers.append((name, name))
            except Exception:
                pass
        if not printers:
            # Last resort: use default printer if enumeration returned nothing
            try:
                default_name = win32print.GetDefaultPrinter()
                if default_name:
                    printers.append((default_name, default_name))
            except Exception:
                pass
        if not printers:
            raise RuntimeError(
                "No printers found. Check that printers are installed and shared, "
                "and that Windows Print Spooler service is running."
            )
        return printers

    raise RuntimeError(f"Unsupported platform for printer list: {sys.platform}")


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


def _open_printer_settings_system():
    """Open system printer / printing preferences (used on non-Windows or when pywin32 dialog not used)."""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "x-apple.systempreferences:com.apple.PrintingPrefs"], start_new_session=True)
        elif sys.platform == "win32":
            subprocess.Popen(
                ["explorer", "shell:::{A8A91A66-3A7D-4424-8D24-04E180695C7A}"],
                start_new_session=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
        else:
            subprocess.Popen(["system-config-printer"], start_new_session=True)
    except Exception:
        pass


def _open_printer_properties_win32(printer_name, parent_hwnd=None):
    """Open printer properties dialog (DocumentProperties) for this print job. Returns modified DEVMODE or None."""
    import win32print
    if not printer_name or printer_name == "default":
        return None
    hprinter = win32print.OpenPrinter(printer_name)
    try:
        info = win32print.GetPrinter(hprinter, 2)
        devmode = info.get("pDevMode")
        if devmode is None:
            return None
        # Show the dialog: current devmode in/out, DM_IN_PROMPT to display the dialog
        mode = (
            getattr(win32print, "DM_IN_BUFFER", 1)
            | getattr(win32print, "DM_OUT_BUFFER", 2)
            | getattr(win32print, "DM_IN_PROMPT", 4)
        )
        win32print.DocumentProperties(
            parent_hwnd or 0,
            hprinter,
            printer_name,
            devmode,
            devmode,
            mode,
        )
        return devmode
    finally:
        win32print.ClosePrinter(hprinter)


class A4PrintPreviewWindow(ctk.CTkToplevel):
    """Photoshop-style: left = preview, right = printer, margins, rows, settings, Print/Close."""

    def __init__(self, parent, pil_photo, **kwargs):
        super().__init__(parent, **kwargs)
        self.title("Print — Passport photos on A4")
        self.pil_photo = pil_photo
        self._sheet_image = None
        self._rows = 1
        self._margin_mm = DEFAULT_MARGIN_MM
        self._printer_error = None
        self._devmode = None  # Windows: DEVMODE from printer properties dialog
        try:
            self._printers = _get_printers()
        except Exception as e:
            self._printers = [("default", "Default printer")]
            self._printer_error = str(e)
        self._max_rows_val = _max_rows(self._margin_mm)

        # Main horizontal split: left = preview, right = options
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, minsize=OPTIONS_PANEL_WIDTH)
        self.grid_rowconfigure(0, weight=1)

        # —— Left: preview (Canvas so image is clipped, centered, never overflows) ——
        self.preview_container = ctk.CTkFrame(self, fg_color="#2b2b2b", corner_radius=8)
        self.preview_container.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        self.preview_container.grid_columnconfigure(0, weight=1)
        self.preview_container.grid_rowconfigure(0, weight=1)
        self.preview_inner = ctk.CTkFrame(self.preview_container, fg_color="transparent")
        self.preview_inner.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.preview_inner.grid_columnconfigure(0, weight=1)
        self.preview_inner.grid_rowconfigure(0, weight=1)
        self.preview_canvas = tk.Canvas(
            self.preview_inner, bg="#2b2b2b", highlightthickness=0
        )
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        self._photo = None  # keep ref so image is not garbage-collected

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
        self.printer_menu.grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 4))
        row += 1
        if self._printer_error:
            self.printer_error_label = ctk.CTkLabel(
                opts, text=self._printer_error, font=ctk.CTkFont(size=11),
                text_color=("red", "#f87171"), wraplength=OPTIONS_PANEL_WIDTH - 32
            )
            self.printer_error_label.grid(row=row, column=0, sticky="w", padx=16, pady=(0, 12))
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

        # Printer settings (paper, quality, orientation — on Windows opens DocumentProperties)
        ctk.CTkButton(
            opts, text="Printer settings…", command=self._open_printer_settings,
            width=OPTIONS_PANEL_WIDTH - 32, height=32, corner_radius=8,
            fg_color="transparent", border_width=1
        ).grid(row=row, column=0, sticky="ew", padx=16, pady=(8, 12))
        row += 1

        ctk.CTkLabel(opts, text="Paper size, type, quality, color mode, DPI, and orientation in Printer settings are applied to this print job.", font=ctk.CTkFont(size=11), text_color="gray", wraplength=OPTIONS_PANEL_WIDTH - 32).grid(row=row, column=0, sticky="w", padx=16, pady=(0, 16))
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
        self.after(250, self._redraw)  # redraw after layout so preview fits and centers
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
        if w <= 0 or h <= 0:
            return
        self.update_idletasks()
        # Use canvas size so preview is always clipped to visible area; scale to fit, center
        cw = max(1, self.preview_canvas.winfo_width())
        ch = max(1, self.preview_canvas.winfo_height())
        if cw <= 10 or ch <= 10:
            cw = max(cw, self.winfo_width() - OPTIONS_PANEL_WIDTH - 24)
            ch = max(ch, self.winfo_height() - 24)
        r = min(cw / w, ch / h)
        dw = max(1, min(int(w * r), cw))
        dh = max(1, min(int(h * r), ch))
        disp = self._sheet_image.resize((dw, dh), Image.Resampling.LANCZOS)
        self.preview_canvas.delete("all")
        self._photo = ImageTk.PhotoImage(disp)
        cx, cy = cw // 2, ch // 2
        self.preview_canvas.create_image(cx, cy, image=self._photo, anchor="center")

    def _open_printer_settings(self):
        """On Windows: open DocumentProperties dialog for selected printer and store DEVMODE. Else: open system prefs."""
        if sys.platform == "win32":
            try:
                printer = self.printer_var.get()
                # Get HWND for modal dialog; 0 is valid (dialog still shows)
                parent_hwnd = 0
                try:
                    parent_hwnd = self.winfo_id()
                except Exception:
                    pass
                self._devmode = _open_printer_properties_win32(printer, parent_hwnd)
            except Exception:
                _open_printer_settings_system()
        else:
            _open_printer_settings_system()

    def _print_direct_windows(self):
        """Print directly to selected printer. Uses DEVMODE from Printer settings so paper, quality, color, DPI, etc. are applied. Image fits to page."""
        import win32print
        import win32ui
        from PIL import ImageWin

        # GetDeviceCaps indices for printable area (pixels)
        HORZRES = 8
        VERTRES = 10

        printer = self.printer_var.get()
        if not printer or printer == "default":
            return
        margin = self._get_margin_mm()
        sheet = build_a4_sheet(
            self.pil_photo,
            self._rows,
            dpi=PRINT_DPI,
            margin_mm=margin,
        )
        if sheet.mode != "RGB":
            sheet = sheet.convert("RGB")

        hdc = None
        raw_hdc = None

        try:
            # Create DC with user's DEVMODE so all settings apply (paper type, quality, color, DPI, orientation, etc.)
            if self._devmode is not None:
                try:
                    import win32gui
                    # CreateDC with DEVMODE = driver uses exactly these settings for this job
                    raw_hdc = win32gui.CreateDC("WINSPOOL", printer, self._devmode)
                    if raw_hdc:
                        hdc = win32ui.CreateDCFromHandle(raw_hdc)
                except Exception:
                    pass
            if hdc is None:
                # No DEVMODE or CreateDC failed: use default printer DC
                hdc = win32ui.CreateDC()
                hdc.CreatePrinterDC(printer)
                if self._devmode is not None:
                    try:
                        hdc.SetDevMode(self._devmode)
                    except Exception:
                        pass

            hdc.StartDoc("A4 Photo Sheet")
            hdc.StartPage()

            # Fit to page: draw image scaled to printer's printable area
            hdc_handle = hdc.GetHandleOutput()
            try:
                page_width = win32print.GetDeviceCaps(hdc_handle, HORZRES)
                page_height = win32print.GetDeviceCaps(hdc_handle, VERTRES)
            except AttributeError:
                import ctypes
                gdi32 = ctypes.windll.gdi32
                page_width = gdi32.GetDeviceCaps(hdc_handle, HORZRES)
                page_height = gdi32.GetDeviceCaps(hdc_handle, VERTRES)
            if page_width <= 0:
                page_width = sheet.width
            if page_height <= 0:
                page_height = sheet.height

            dib = ImageWin.Dib(sheet)
            dib.draw(hdc.GetHandleOutput(), (0, 0, page_width, page_height))

            hdc.EndPage()
            hdc.EndDoc()
        finally:
            # DeleteDC: only one of these (raw_hdc owns the DC when we used CreateDC with DEVMODE)
            if raw_hdc is not None:
                try:
                    import win32gui
                    win32gui.DeleteDC(raw_hdc)
                except Exception:
                    pass
            elif hdc is not None:
                try:
                    hdc.DeleteDC()
                except Exception:
                    pass

    def _print_with_dialog(self):
        """Windows: print silently to selected printer with stored DEVMODE. Other OSes: open system print dialog."""
        if self.pil_photo is None:
            return
        if sys.platform == "win32":
            try:
                self._print_direct_windows()
            except Exception:
                # Fallback: save and open shell print dialog
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
        else:
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
