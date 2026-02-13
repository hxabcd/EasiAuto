# Minimal OpenCV Build for Python 3.13 (PyAutoGUI Optimized)

This directory contains a PowerShell script to compile a custom, lightweight OpenCV binary (`cv2.pyd`) optimized for use with `PyAutoGUI`'s `locateCenterOnScreen` (template matching) on Windows.

## 🎯 Features
- **Target**: Python 3.13 (cp313-win_amd64).
- **Size**: Extreme optimization (<5MB) via disabled dispatching.
- **Performance**: AVX2 baseline (Requires CPU > 2013).
- **Image Support**: Includes JPEG/PNG (critical for template matching), excludes TIFF/WebP/OpenEXR.

## 📋 Prerequisites
1. **Visual Studio 2022** with "Desktop development with C++".
2. **CMake** (3.20+).
3. **Git**.
4. **Python 3.13** (installed on system or via `uv` in script).

## 🚀 Usage

1. **Open Terminal**:
   Open "x64 Native Tools Command Prompt for VS 2022" (Search in Start Menu).

2. **Run Script**:
   Navigate to this directory and run:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\build_minimal.ps1
   ```

3. **Output**:
   The resulting binary will be located at:  
   `./opencv_minimal_build/build/lib/python3/Release/cv2.cp313-win_amd64.pyd`

## 📦 Integration with PyAutoGUI

To use this lightweight binary in your project without installing all of `opencv-python`:

1. **Copy** the `cv2.cp313-win_amd64.pyd` to your project root (or `site-packages`).
2. **Rename** it to `cv2.pyd` (optional, but convenient).
3. **Verify**:
   ```python
   import cv2
   print(cv2.__version__)
   # Should print 4.10.0 (or similar)
   ```
4. **PyAutoGUI**:
   PyAutoGUI will automatically detect and use `cv2` if it can be imported.
   ```python
   import pyautogui
   # Now uses your minimal cv2 for template matching!
   location = pyautogui.locateCenterOnScreen('image.png') 
   ```
