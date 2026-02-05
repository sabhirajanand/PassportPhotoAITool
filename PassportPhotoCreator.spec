# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for PassportPhotoCreator – standalone app (no Python required).
# Build: pyinstaller PassportPhotoCreator.spec

import os
import sys

# CustomTkinter assets (themes, fonts) – required at runtime
import customtkinter as _ctk
_ctk_dir = os.path.dirname(_ctk.__file__)
ctk_datas = [
    (os.path.join(_ctk_dir, "assets"), "customtkinter/assets"),
]

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=ctk_datas,
    hiddenimports=[
        "customtkinter",
        "PIL",
        "PIL.Image",
        "PIL._tkinter_finder",
        "tkinter",
        "cv2",
        "numpy",
        "google.generativeai",
        "google.generativeai.types",
        "dotenv",
        "rembg",
        "rembg.bg",
        "rembg.sessions.u2net",
        "rembg.sessions.u2net_cloth_seg",
        "rembg.sessions.u2net_human_seg",
        "onnxruntime",
        "onnxruntime.capi",
        "onnxruntime.capi._pybind_state",
        "core",
        "core.ai_logic",
        "core.processor",
        "crop_canvas",
        "a4_print_preview",
        "hsv_picker",
        "installer",
        "zoom_pan_image",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
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
    upx_exclude=[],
    name="PassportPhotoCreator",
)
