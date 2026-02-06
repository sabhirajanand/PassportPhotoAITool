"""
Client for the background rembg service. Use when service is running for fast removal.
Ensures only one service runs: fixed port, start lock file, and wait for port after start.
"""
import io
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from PIL import Image


REMBG_SERVICE_PORT = int(os.environ.get("PASSPORT_REMBG_PORT", 38472))
REMBG_SERVICE_HOST = "127.0.0.1"
SOCKET_TIMEOUT = 120  # seconds for one removal
_WAIT_FOR_PORT_SEC = 90  # max wait after starting the process
_PORT_CHECK_INTERVAL = 1.0  # seconds between port checks

# Only one thread per process may run "start" logic; avoid multiple service processes
_start_lock = threading.Lock()


def remove_background_via_service(pil_image, port=REMBG_SERVICE_PORT):
    """
    Send image to the rembg service and return RGBA PIL Image, or None if service
    unavailable / error.
    """
    if pil_image is None:
        return None
    img = pil_image.convert("RGB") if pil_image.mode != "RGB" else pil_image
    out = io.BytesIO()
    img.save(out, "PNG")
    png_bytes = out.getvalue()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(SOCKET_TIMEOUT)
        sock.connect((REMBG_SERVICE_HOST, port))
        sock.send(len(png_bytes).to_bytes(4, "big"))
        sock.send(png_bytes)
        len_buf = b""
        while len(len_buf) < 4:
            chunk = sock.recv(4 - len(len_buf))
            if not chunk:
                sock.close()
                return None
            len_buf += chunk
        length = int.from_bytes(len_buf, "big")
        if length <= 0 or length > 50 * 1024 * 1024:
            sock.close()
            return None
        data = b""
        while len(data) < length:
            chunk = sock.recv(min(65536, length - len(data)))
            if not chunk:
                break
            data += chunk
        sock.close()
        if len(data) != length:
            return None
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except (socket.error, OSError, ValueError):
        return None


def is_service_running(port=REMBG_SERVICE_PORT):
    """Return True if the rembg service is accepting connections."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        sock.connect((REMBG_SERVICE_HOST, port))
        sock.close()
        return True
    except (socket.error, OSError):
        return False


def _service_start_lock_path():
    """Path for the lock file so only one launcher starts the service at a time."""
    from installer import get_rembg_model_dir
    return get_rembg_model_dir().parent / "rembg_service.starting"


def _wait_for_port(port, timeout_sec=_WAIT_FOR_PORT_SEC):
    """Return True if the port became available within timeout_sec."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if is_service_running(port):
            return True
        time.sleep(_PORT_CHECK_INTERVAL)
    return False


def _is_pid_running(pid):
    """Return True if a process with the given PID exists."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start_service_background(port=REMBG_SERVICE_PORT):
    """
    Start the rembg service as a detached background process. No-op if already running.
    Uses a lock file so only one process starts the service; waits for port before returning
    so re-launched apps see the same service.
    """
    with _start_lock:
        if is_service_running(port):
            return
        lock_path = _service_start_lock_path()
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            try:
                os.write(fd, str(os.getpid()).encode("utf-8"))
            finally:
                os.close(fd)
            we_created_lock = True
        except FileExistsError:
            we_created_lock = False
        if not we_created_lock:
            try:
                pid_str = lock_path.read_text(encoding="utf-8").strip()
                if pid_str.isdigit() and not _is_pid_running(int(pid_str)):
                    try:
                        lock_path.unlink()
                    except OSError:
                        pass
                    try:
                        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                        os.write(fd, str(os.getpid()).encode("utf-8"))
                        os.close(fd)
                        we_created_lock = True
                    except FileExistsError:
                        pass
            except Exception:
                pass
        if not we_created_lock:
            _wait_for_port(port)
            return
        try:
            creationflags = 0
            if sys.platform == "win32":
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0
            if getattr(sys, "frozen", False):
                cmd = [sys.executable, "--service", "--port", str(port)]
            else:
                cmd = [
                    sys.executable, "-m", "core.rembg_service", "--port", str(port)
                ]
            subprocess.Popen(
                cmd,
                creationflags=creationflags,
                start_new_session=True,
                cwd=Path(__file__).resolve().parent.parent,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _wait_for_port(port)
        finally:
            try:
                if we_created_lock and lock_path.exists():
                    lock_path.unlink()
            except OSError:
                pass
