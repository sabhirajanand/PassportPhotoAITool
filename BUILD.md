# Building the standalone app

PassportPhotoCreator can be built as a **standalone executable** that runs without a Python installation. PyInstaller bundles Python, your code, and dependencies into a single folder (or file).

## Prerequisites

- Python 3.9+ with the project dependencies installed:
  ```bash
  pip install -r requirements.txt
  pip install pyinstaller
  ```
- Enough disk space for the build (hundreds of MB for rembg/onnxruntime).

## Build (all platforms)

```bash
# From the project root
pyinstaller PassportPhotoCreator.spec
```

Or use the script:

```bash
chmod +x build.sh
./build.sh
```

Output:

- **Windows:** `dist/PassportPhotoCreator/PassportPhotoCreator.exe` (and DLLs in the same folder).
- **macOS:** `dist/PassportPhotoCreator/PassportPhotoCreator` (run this binary, or wrap in a `.app` if desired).
- **Linux:** `dist/PassportPhotoCreator/PassportPhotoCreator`.

Run the executable from inside `dist/PassportPhotoCreator/` (it must stay next to its bundled files). Do not move the executable alone.

## Building a Windows .exe from macOS (or Linux)

PyInstaller does **not** support cross-compilation: you cannot build a Windows executable on a Mac. To get a Windows build from your Mac:

1. **Push your project to GitHub** (create a repo and push if you haven’t).
2. **Use the included GitHub Actions workflow:**
   - Go to your repo → **Actions** → **“Build Windows executable”**.
   - Click **“Run workflow”** (or push to `main` to trigger it automatically).
3. When the run finishes, open the run and **download the artifact** `PassportPhotoCreator-Windows`.
4. Unzip it on a Windows machine. Inside you’ll have `PassportPhotoCreator.exe` and the rest of the bundle; run the `.exe` from that folder.

The workflow (`.github/workflows/build-windows.yml`) runs PyInstaller on a Windows runner and uploads the built app as a zip.

## First run (standalone)

On first launch, the app will:

1. Ask to run the **first-run installer**: download rembg models and register “Open with PassportPhotoCreator” for image files.
2. After that, it starts normally. You can use **Open with** from the OS to open an image directly in the app.

## Gemini API key (optional)

For “Suggested by Gemini” background color, the app looks for a Gemini API key in:

- A `.env` file in the **current working directory** when you start the app, or
- An `.env` file next to the executable (inside `dist/PassportPhotoCreator/`).

Create `.env` with:

```
GEMINI_API_KEY=your_key_here
```

If no key is found, the Gemini suggestion option is simply unavailable.

## Single-file build (optional)

The default spec uses **one-folder** mode (recommended for rembg/onnxruntime). For a single executable:

1. In `PassportPhotoCreator.spec`, remove the `COLLECT` block and change `EXE(..., exclude_binaries=True)` to `exclude_binaries=False`, and add `a.binaries` and `a.datas` to the `EXE()` call.
2. Expect a larger file and slower startup (extraction to a temp dir each run).

Keeping the one-folder layout is more reliable and faster to start.

## macOS “Open with” and .app bundle

- **Open with** on macOS is registered by the first-run installer (when run as the built app). It uses the path of the executable you run.
- To ship a proper **.app** bundle, create a bundle (e.g. with `py2app` or a script) that:
  - Puts the `PassportPhotoCreator` folder contents inside `YourApp.app/Contents/MacOS/`.
  - Sets the main executable in `Info.plist` and adds `CFBundleDocumentTypes` for image types so “Open with” works from Finder.

## Troubleshooting

- **ModuleNotFoundError:** Add the missing module to `hiddenimports` in `PassportPhotoCreator.spec` and rebuild.
- **rembg / onnxruntime errors:** Ensure you build on the same OS (and ideally same OS version) as the target. Use the default one-folder build.
- **Console window on Windows:** The spec uses `console=False`. If you need a console for debugging, set `console=True` in the spec and rebuild.
