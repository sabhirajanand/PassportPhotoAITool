# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for PassportPhotoCreator – standalone app (no Python required).
# Build: pyinstaller PassportPhotoCreator.spec
#
# Startup optimizations:
# - No heavy AI in hiddenimports (rembg/onnx/cv2/numpy); let PyInstaller pull them
#   from modules that import them. Use lazy imports in code for bg removal.
# - noarchive=True: faster startup (more disk, less unpack at runtime).
# - upx_exclude: heavy DLLs not UPX'd so they load faster.

import os
import sys

# CustomTkinter assets (themes, fonts) – required at runtime
import customtkinter as _ctk
_ctk_dir = os.path.dirname(_ctk.__file__)
ctk_datas = [
    (os.path.join(_ctk_dir, "assets"), "customtkinter/assets"),
]

# Metadata for pymatting/rembg when user runs background removal (lazy-loaded path)
from PyInstaller.utils.hooks import copy_metadata
metadata_datas = []
for pkg in ("pymatting", "rembg"):
    try:
        metadata_datas += copy_metadata(pkg)
    except Exception:
        pass

block_cipher = None

a = Analysis(
    ["launch.py"],
    pathex=[],
    binaries=[],
    datas=ctk_datas + metadata_datas,
    # Minimal hiddenimports: only what PyInstaller truly misses. No cv2/numpy/rembg/onnx
    # here so they are not forced at startup; they are included via import graph when used.
    hiddenimports=[
        "dotenv",
        "google.generativeai",
        "google.generativeai.types",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=True,  # faster startup (modules on disk, not in PYZ)
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PassportPhotoCreator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[
        "python*.dll",
        "onnxruntime*.dll",
        "opencv*.dll",
        "cv2*.pyd",
        "numpy*.pyd",
        "pywintypes*.dll",
    ],
    name="PassportPhotoCreator",
)
