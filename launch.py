"""
Launcher: show splash with logo, log window, and loading while setting up the app.
Entry point for best startup UX. Use this for PyInstaller; "python main.py" redirects here too.
"""
import os
import queue
import sys
import threading
import time
from pathlib import Path


# Minimal imports so splash appears quickly
import tkinter as tk
from tkinter import scrolledtext


def _run_installer_if_frozen():
    """First-run installer check (frozen app only). Returns False if user cancelled install."""
    if not getattr(sys, "frozen", False):
        return True
    try:
        from installer import is_first_run, run_installer_if_first_run
        if is_first_run():
            if not run_installer_if_first_run(executable_path_arg=None):
                return False
    except Exception:
        pass
    return True


def _show_splash_and_launch():
    """Show splash window with log area, load and set up app in thread, then run app."""
    splash = tk.Tk()
    splash.title("PassportAI")
    w, h = 500, 520
    splash.geometry(f"{w}x{h}")
    splash.resizable(True, True)
    splash.minsize(400, 400)
    splash.overrideredirect(False)

    # Dark theme to match app
    bg = "#1a1a2e"
    splash.configure(bg=bg)

    # Center on screen
    splash.update_idletasks()
    sw = splash.winfo_screenwidth()
    sh = splash.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    splash.geometry(f"{w}x{h}+{x}+{y}")

    # Logo / title
    title = tk.Label(
        splash, text="PassportAI",
        font=("Segoe UI", 28, "bold"),
        fg="white", bg=bg,
    )
    title.pack(pady=(24, 4))

    # Subtitle
    tk.Label(
        splash, text="Passport photo tool",
        font=("Segoe UI", 10),
        fg="#94a3b8", bg=bg,
    ).pack(pady=(0, 12))

    # Log area (thread-safe: background thread puts lines in queue; flush runs on main thread)
    log_frame = tk.Frame(splash, bg=bg)
    log_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))
    log_queue = queue.Queue()
    log_text = scrolledtext.ScrolledText(
        log_frame,
        height=14,
        font=("Consolas", 9),
        fg="#e2e8f0",
        bg="#0f172a",
        insertbackground="#e2e8f0",
        relief=tk.FLAT,
        padx=8,
        pady=8,
    )
    log_text.pack(fill=tk.BOTH, expand=True)
    log_text.configure(state=tk.DISABLED)

    def append_log(msg):
        log_queue.put(msg)

    def flush_log():
        try:
            while True:
                msg = log_queue.get_nowait()
                if not splash.winfo_exists():
                    return
                log_text.configure(state=tk.NORMAL)
                log_text.insert(tk.END, msg + "\n")
                log_text.see(tk.END)
                log_text.configure(state=tk.DISABLED)
        except queue.Empty:
            pass
        if splash.winfo_exists() and not state["done"]:
            splash.after(50, flush_log)

    splash.after(100, flush_log)

    # Loading state: (done, initial_file)
    state = {"done": False, "initial_file": None}

    def load_in_background():
        try:
            append_log("Starting PassportAI…")
            # Use app-local model dir only (no ~/.u2net); set before any rembg load
            try:
                from installer import ensure_rembg_model_dir, get_rembg_model_dir
                ensure_rembg_model_dir()
                append_log("Model folder: " + str(get_rembg_model_dir()))
            except (PermissionError, OSError) as e:
                from installer import get_rembg_model_dir
                os.environ["U2NET_HOME"] = str(get_rembg_model_dir())
                append_log("Permission error: " + str(e))
                append_log("Using model folder only: " + str(get_rembg_model_dir()))
            append_log("Loading main module…")
            import main  # Heavy imports (ctk, PIL, etc.) run here
            state["initial_file"] = main._get_initial_file_from_args()
            append_log("Main module loaded.")
            # Only check model file existence; models load in the background service
            append_log("Checking background removal models…")
            try:
                from installer import get_rembg_model_dir
                model_dir = get_rembg_model_dir()
                if model_dir.is_dir():
                    onnx = list(model_dir.glob("*.onnx"))
                    if onnx:
                        append_log(f"  Models found: {len(onnx)} file(s)")
                    else:
                        append_log("  No model files yet (service will download on first use).")
                else:
                    append_log("  No model cache yet (service will download on first use).")
            except Exception as e:
                append_log(f"  Note: {e}")
            append_log("Ready.")
        except Exception as e:
            append_log(f"Error: {e}")
        state["done"] = True

    threading.Thread(target=load_in_background, daemon=True).start()

    # Poll until loading is done
    while not state["done"]:
        splash.update()
        time.sleep(0.05)

    # Loading done: destroy splash so app will be the only Tk root, then run app
    try:
        splash.destroy()
    except Exception:
        pass

    try:
        from main import App
        app = App()
        app.update_idletasks()
        app.deiconify()
        app.lift()
        app.focus_force()
        try:
            app.attributes("-topmost", True)
            app.after(200, lambda: app.attributes("-topmost", False))
        except Exception:
            pass
        initial_file = state.get("initial_file")
        if initial_file:
            app.after(300, lambda p=initial_file: app._load_image(p))
        app.mainloop()
    except Exception:
        raise


def main():
    """Entry point: installer check (frozen), then splash + app; or run rembg service if --service."""
    if "--service" in sys.argv:
        from core.rembg_service import main as service_main
        service_main()
        sys.exit(0)
    if not _run_installer_if_frozen():
        sys.exit(0)
    _show_splash_and_launch()


if __name__ == "__main__":
    main()
