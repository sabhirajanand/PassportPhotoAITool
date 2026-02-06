"""
First-run installer: download rembg models and register "Open with PassportAI" for images.
Runs when the app starts for the first time (no marker file). Asks user confirmation;
may require administrator permission for system-wide "Open with" (we use per-user where possible).
"""
import os
import platform
import subprocess
import sys
from pathlib import Path

# Image extensions we register for "Open with"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
MIME_TYPES_IMAGES = ("image/jpeg", "image/png", "image/webp", "image/bmp")


def _get_app_data_dir():
    """Platform-specific app data / config dir for marker and optional data."""
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return Path(base) / "PassportPhotoCreator"
    if system == "Darwin":
        return Path(os.path.expanduser("~/Library/Application Support/PassportPhotoCreator"))
    return Path(os.path.expanduser("~/.local/share/PassportPhotoCreator"))


def _get_install_marker_path():
    return _get_app_data_dir() / ".installed"


def get_rembg_model_dir():
    """Directory for rembg u2net models (same location as app data). Use this only; no ~/.u2net fallback."""
    return _get_app_data_dir() / "u2net"


def ensure_rembg_model_dir():
    """
    Create app model dir and set U2NET_HOME so rembg uses it only.
    Raises PermissionError or OSError if the directory cannot be created.
    """
    d = get_rembg_model_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError) as e:
        raise type(e)(f"Cannot create model folder at {d}. Fix permissions or run from a writable location.") from e
    os.environ["U2NET_HOME"] = str(d)


def is_first_run():
    """True if installer has not been run yet (no marker file)."""
    marker = _get_install_marker_path()
    return not marker.exists()


def _get_executable_command(executable_path_arg=None):
    """
    Return the command to run this app with a file path argument (for "Open with").
    executable_path_arg: when provided, use this as the app executable/script path
    (e.g. from main.py: sys.executable for frozen, or path to main.py for dev).
    """
    frozen = getattr(sys, "frozen", False)
    if frozen:
        # PyInstaller / cx_Freeze: sys.executable is the exe or app bundle binary
        exe = sys.executable
        return exe, f'"{exe}" "%1"'
    # Development: run Python with main.py
    if executable_path_arg:
        script = executable_path_arg
    else:
        script = Path(__file__).resolve().parent / "main.py"
    python = sys.executable
    return str(script), f'"{python}" "{script}" "%1"'


def _download_models():
    """Trigger download of all rembg models by creating sessions and running a tiny predict."""
    try:
        from rembg import new_session
        from PIL import Image
        # Tiny 2x2 image to trigger model load/download
        img = Image.new("RGB", (2, 2), (128, 128, 128))
        for name in ("u2net_human_seg", "u2net", "u2net_cloth_seg"):
            try:
                session = new_session(name)
                session.predict(img)
            except Exception:
                pass
    except Exception as e:
        raise RuntimeError(f"Model download failed: {e}") from e


def _register_open_with_windows(command_for_open_with):
    """Register 'Open with PassportAI' for image extensions (HKCU, no admin)."""
    try:
        import winreg
    except ImportError:
        return False
    # HKCU\Software\Classes\Applications\PassportPhotoCreator\shell\open\command
    app_name = "PassportPhotoCreator"
    try:
        key = winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            f"Software\\Classes\\Applications\\{app_name}\\shell\\open\\command",
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.SetValue(key, "", winreg.REG_SZ, command_for_open_with)
        key.Close()
        # Add to OpenWithList for each extension
        for ext in IMAGE_EXTENSIONS:
            ext_key_name = f"Software\\Classes\\{ext}\\OpenWithList\\{app_name}"
            try:
                ek = winreg.CreateKeyEx(
                    winreg.HKEY_CURRENT_USER,
                    ext_key_name,
                    0,
                    winreg.KEY_SET_VALUE,
                )
                winreg.SetValue(ek, "", winreg.REG_SZ, "")
                ek.Close()
            except Exception:
                pass
        return True
    except Exception:
        return False


def _register_open_with_darwin(executable_path):
    """macOS: ensure app is associated. When built as .app, Info.plist should have CFBundleDocumentTypes."""
    # If running as script, we can't easily register; the built .app must have plist.
    # Try to register with Launch Services for the current executable (when frozen).
    if getattr(sys, "frozen", False) and ".app" in executable_path:
        # Re-register the app with Launch Services
        try:
            subprocess.run(["open", "-a", executable_path], capture_output=True, timeout=5)
        except Exception:
            pass
    return True


def _register_open_with_linux(executable_path, command_for_open_with):
    """Linux: install .desktop and set xdg-mime default for images (user-level)."""
    desktop_dir = Path.home() / ".local" / "share" / "applications"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    desktop_path = desktop_dir / "passport-photo-creator.desktop"
    # Exec: desktop expects Exec=... %f (single file). command_for_open_with has "%1" for Windows.
    frozen = getattr(sys, "frozen", False)
    if frozen:
        exec_line = f'"{sys.executable}" %f'
    else:
        exec_line = f'"{sys.executable}" "{executable_path}" %f'
    content = f"""[Desktop Entry]
Type=Application
Name=PassportAI
Comment=Passport photo creator
Exec={exec_line}
Icon=applications-graphics
Categories=Graphics;Viewer;
MimeType=image/jpeg;image/png;image/webp;image/bmp;
Terminal=false
"""
    try:
        desktop_path.write_text(content, encoding="utf-8")
        # Set as default for common image types (user-level)
        for mime in ("image/jpeg", "image/png", "image/webp", "image/bmp"):
            try:
                subprocess.run(
                    ["xdg-mime", "default", "passport-photo-creator.desktop", mime],
                    capture_output=True,
                    timeout=5,
                    cwd=str(desktop_dir),
                )
            except Exception:
                pass
        return True
    except Exception:
        return False


def register_open_with(executable_path_arg=None):
    """Register this app for 'Open with' on image files (platform-specific)."""
    script_path, command_for_open_with = _get_executable_command(executable_path_arg)
    system = platform.system()
    if system == "Windows":
        return _register_open_with_windows(command_for_open_with)
    if system == "Darwin":
        return _register_open_with_darwin(sys.executable if getattr(sys, "frozen", False) else script_path)
    if system == "Linux":
        return _register_open_with_linux(script_path, command_for_open_with)
    return False


def run_first_run_installer(executable_path_arg=None):
    """
    Run first-time setup: download models and register Open with.
    executable_path_arg: path to main.py when running in dev (for Open with command).
    """
    app_dir = _get_app_data_dir()
    app_dir.mkdir(parents=True, exist_ok=True)
    marker = _get_install_marker_path()

    # 1. Download models
    _download_models()

    # 2. Register Open with
    register_open_with(executable_path_arg)

    # 3. Mark as installed
    try:
        marker.write_text("1", encoding="utf-8")
    except Exception:
        pass


def run_installer_if_first_run(executable_path_arg=None):
    """
    If first run, show dialog and run installer. Returns True if installer ran (or was skipped),
    False if user cancelled.
    """
    if not is_first_run():
        return True
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        # Headless: run installer anyway
        run_first_run_installer(executable_path_arg)
        return True

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    msg = (
        "First run setup:\n\n"
        "This will download AI models (~50–100 MB) and add 'Open with PassportAI' "
        "for image files in the right-click menu.\n\n"
        "Administrator permission may be required for system-wide registration on some systems. "
        "Continue?"
    )
    ok = messagebox.askyesno("PassportAI – First run", msg, parent=root)
    root.destroy()
    if not ok:
        return False
    try:
        run_first_run_installer(executable_path_arg)
    except Exception as e:
        root2 = tk.Tk()
        root2.withdraw()
        messagebox.showerror("Setup error", str(e), parent=root2)
        root2.destroy()
        return True  # don't block app
    return True
