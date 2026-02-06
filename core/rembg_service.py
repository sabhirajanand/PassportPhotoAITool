"""
Background rembg service: long-running process that keeps rembg/onnx loaded.
Main app connects to it for fast background removal; service stays running
after the app closes so next launch is fast.
Models are stored in app folder only (U2NET_HOME set before any rembg import).
"""
import io
import os
import socket
import sys
from concurrent.futures import ThreadPoolExecutor

# Use app-local model dir only (must be set before any rembg import)
from installer import get_rembg_model_dir
os.environ["U2NET_HOME"] = str(get_rembg_model_dir())

from PIL import Image


REMBG_SERVICE_PORT = 38472
REMBG_SERVICE_HOST = "127.0.0.1"


def _read_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf


def _handle_request(conn, processor):
    """Handle one request: read PNG image, run triple-model removal, send RGBA PNG."""
    try:
        len_buf = _read_exact(conn, 4)
        if len(len_buf) != 4:
            return
        length = int.from_bytes(len_buf, "big")
        if length <= 0 or length > 50 * 1024 * 1024:  # 50 MB max
            return
        data = _read_exact(conn, length)
        if len(data) != length:
            return
        img = Image.open(io.BytesIO(data)).convert("RGB")
        # Triple-model pipeline (same as main app)
        mask_a = processor.get_mask_a(img)
        mask_b = processor.get_mask_b(img)
        mask_cloth = processor.get_mask_cloth(img)
        if mask_a is None or mask_b is None:
            return
        rgba = processor.combine_masks_and_cutout(
            img, mask_a, mask_b, mask_cloth=mask_cloth,
            alpha_matting=True,
            post_process_mask=True,
        )
        if rgba is None:
            return
        out = io.BytesIO()
        rgba.save(out, "PNG")
        out_bytes = out.getvalue()
        conn.send(len(out_bytes).to_bytes(4, "big"))
        conn.send(out_bytes)
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _write_rembg_error(msg):
    """Write service error (e.g. permission) so main app can show it."""
    try:
        err_file = get_rembg_model_dir().parent / "rembg_error.txt"
        err_file.write_text(msg, encoding="utf-8")
    except Exception:
        pass


def run_server(port=None):
    """Bind and listen first so clients see the service; then load processor and serve."""
    port = port or REMBG_SERVICE_PORT
    try:
        err_file = get_rembg_model_dir().parent / "rembg_error.txt"
        if err_file.exists():
            err_file.unlink()
    except Exception:
        pass
    # Bind and listen immediately so is_service_running() becomes True for other processes
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((REMBG_SERVICE_HOST, port))
    sock.listen(4)
    pid_file = get_rembg_model_dir().parent / "rembg_service.pid"
    try:
        pid_file.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass
    # Now load processor (slow); clients can already connect and will wait for accept()
    from core.processor import ImageProcessor
    processor = ImageProcessor()
    try:
        warm = Image.new("RGB", (32, 32), (255, 255, 255))
        processor.get_mask_a(warm)
        processor.get_mask_b(warm)
        processor.get_mask_cloth(warm)
    except (PermissionError, OSError) as e:
        _write_rembg_error(f"Permission error: {e}. Use model folder only: {get_rembg_model_dir()}")
        try:
            pid_file.unlink()
        except Exception:
            pass
        raise
    except Exception as e:
        _write_rembg_error(str(e))
        try:
            pid_file.unlink()
        except Exception:
            pass
        raise
    executor = ThreadPoolExecutor(max_workers=2)
    try:
        while True:
            conn, _ = sock.accept()
            executor.submit(_handle_request, conn, processor)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        try:
            if pid_file.exists():
                pid_file.unlink()
        except Exception:
            pass
        executor.shutdown(wait=False)
        sock.close()


def main():
    port = REMBG_SERVICE_PORT
    if "--port" in sys.argv:
        i = sys.argv.index("--port")
        if i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
    run_server(port)


if __name__ == "__main__":
    main()
