"""
Launcher: show splash with logo and "Loading..." while loading the app in a background thread.
Entry point for best startup UX. Use this for PyInstaller; "python main.py" redirects here too.
"""
import sys
import threading
import time
from pathlib import Path

# Minimal imports so splash appears quickly
import tkinter as tk


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
    """Show splash window (tk), load main app in thread, then destroy splash and run app."""
    splash = tk.Tk()
    splash.title("PassportAI")
    splash.geometry("420x320")
    splash.resizable(False, False)
    splash.overrideredirect(False)

    # Dark theme to match app
    bg = "#1a1a2e"
    splash.configure(bg=bg)

    # Center on screen
    splash.update_idletasks()
    w, h = 420, 320
    sw = splash.winfo_screenwidth()
    sh = splash.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    splash.geometry(f"{w}x{h}+{x}+{y}")

    # Logo / title
    title = tk.Label(
        splash, text="PassportAI",
        font=("Segoe UI", 32, "bold"),
        fg="white", bg=bg,
    )
    title.pack(pady=(56, 8))

    # Subtitle
    tk.Label(
        splash, text="Passport photo tool",
        font=("Segoe UI", 11),
        fg="#94a3b8", bg=bg,
    ).pack(pady=(0, 24))

    # Loading label
    loading_label = tk.Label(
        splash, text="Loading…",
        font=("Segoe UI", 12),
        fg="#a5b4fc", bg=bg,
    )
    loading_label.pack(pady=8)

    # Simple animated dots (cycle every 400ms)
    dots = [".", "..", "..."]
    dot_index = [0]

    def update_dots():
        loading_label.configure(text="Loading" + dots[dot_index[0] % 3])
        dot_index[0] += 1
        if splash.winfo_exists():
            splash.after(400, update_dots)

    splash.after(200, update_dots)

    # Loading state: (done, initial_file)
    state = {"done": False, "initial_file": None}

    def load_in_background():
        try:
            import main  # Heavy imports (rembg, onnx, ctk, etc.) run here
            state["initial_file"] = main._get_initial_file_from_args()
        except Exception:
            pass
        state["done"] = True

    threading.Thread(target=load_in_background, daemon=True).start()

    # Poll until loading is done (so we're not inside splash.mainloop when we switch to app)
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
    """Entry point: installer check (frozen), then splash + load app."""
    if not _run_installer_if_frozen():
        sys.exit(0)
    _show_splash_and_launch()


if __name__ == "__main__":
    main()
