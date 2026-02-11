<#
.SYNOPSIS
    Compiles a minimal OpenCV (cv2) binary for Python 3.13 designed for PyAutoGUI usage.

.DESCRIPTION
    Automates the entire workflow:
    1. Checks for system requirements (CMake, Compiler).
    2. Sets up a temporary build environment using `uv`.
    3. Clones OpenCV source (latest stable).
    4. Configures CMake with aggressive minimization flags.
    5. Builds and extracts the artifact.

.NOTES
    Author: Antigravity
    Target: Windows x64 / Python 3.13
    Runtime: ~5-15 minutes depending on hardware.
#>

$ErrorActionPreference = "Stop"

# Configuration
$OpenCVGitBranch = "4.10.0" 
$WorkDir = "$PWD\opencv_minimal_build"
$SourceDir = "$WorkDir\opencv"
$BuildDir = "$WorkDir\build"
$VenvDir = "$WorkDir\.venv"

Write-Host ">>> Starting Minimal OpenCV Build for Python 3.13..." -ForegroundColor Cyan
Write-Host ">>> Working Directory: $WorkDir" -ForegroundColor Gray

# --- 1. Pre-flight Checks ---
if (-not (Get-Command "cmake" -ErrorAction SilentlyContinue)) {
    Write-Error "CMake not found. Please install CMake and add it to PATH."
}

# Check for uv
if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    Write-Host ">>> uv not found. Installing via pip..." -ForegroundColor Yellow
    pip install uv
}

# --- 2. Environment Setup (uv) ---
if (-not (Test-Path $WorkDir)) { New-Item -ItemType Directory -Path $WorkDir | Out-Null }
Set-Location $WorkDir

Write-Host ">>> Creating Python 3.13 virtual environment..." -ForegroundColor Cyan
uv venv $VenvDir --python 3.13

# Add venv to path for this session
$Env:PATH = "$VenvDir\Scripts;$Env:PATH"
$Env:VIRTUAL_ENV = $VenvDir

Write-Host ">>> Installing build dependencies (numpy>=2.0.0)..." -ForegroundColor Cyan
# Numpy 2.0 headers are compatible with 1.x binaries (mostly), but critically needed for 3.13 support
uv pip install "numpy>=2.0.0" setuptools wheel

# --- 3. Source Retrieval ---
if (-not (Test-Path $SourceDir)) {
    Write-Host ">>> Cloning OpenCV source ($OpenCVGitBranch)..." -ForegroundColor Cyan
    git clone --depth 1 --branch $OpenCVGitBranch https://github.com/opencv/opencv.git $SourceDir
}

# --- 4. CMake Configuration ---
# Get Python paths dynamically from the currently active venv
$PyExec = python -c "import sys; print(sys.executable)"
# Use extensive suppression to minimize size
$CMakeArgs = @(
    "-S", "$SourceDir",
    "-B", "$BuildDir",
    "-G", "Visual Studio 18 2026",
    "-A", "x64",
    "-D", "CMAKE_BUILD_TYPE=Release",
    
    # CRITICAL: Build only core modules
    "-D", "BUILD_LIST=core,imgproc,imgcodecs,python3", 
    
    # Python Configuration
    "-D", "BUILD_opencv_python3=ON",
    "-D", "PYTHON3_EXECUTABLE=$PyExec",
    
    # Optimization & Size reduction
    "-D", "BUILD_SHARED_LIBS=OFF",   # Static linking into one .pyd
    "-D", "WITH_STATIC_CRT=OFF",     # Dynamically link CRT (match Python)
    "-D", "CV_TRACE=OFF",            # Disable internal tracing
    "-D", "OPENCV_ENABLE_NONFREE=OFF",

    # Exclude Heavy Modules
    "-D", "BUILD_opencv_dnn=OFF",
    "-D", "BUILD_opencv_video=OFF",
    "-D", "BUILD_opencv_videoio=OFF",
    "-D", "BUILD_opencv_highgui=OFF",
    "-D", "BUILD_opencv_objdetect=OFF",
    "-D", "BUILD_opencv_features2d=OFF",
    "-D", "BUILD_opencv_calib3d=OFF",
    "-D", "BUILD_opencv_flann=OFF",
    "-D", "BUILD_opencv_photo=OFF",
    "-D", "BUILD_opencv_gapi=OFF",
    "-D", "BUILD_opencv_ml=OFF",
    
    # Test & Examples
    "-D", "BUILD_TESTS=OFF",
    "-D", "BUILD_PERF_TESTS=OFF",
    "-D", "BUILD_EXAMPLES=OFF",
    "-D", "BUILD_DOCS=OFF",
    "-D", "BUILD_JAVA=OFF",
    "-D", "BUILD_opencv_java=OFF",
    
    # Media Support (Only critical image formats)
    "-D", "WITH_FFMPEG=OFF",
    "-D", "WITH_GSTREAMER=OFF",
    "-D", "WITH_DSHOW=OFF",
    "-D", "WITH_MSMF=OFF",
    "-D", "WITH_DIRECTX=OFF",
    "-D", "WITH_V4L=OFF",
    "-D", "WITH_OPENCL=OFF",
    "-D", "WITH_CUDA=OFF",
    "-D", "WITH_EIGEN=OFF",
    "-D", "WITH_PROTOBUF=OFF",
    "-D", "WITH_QUIRC=OFF",
    "-D", "WITH_ADE=OFF",
    "-D", "WITH_TIFF=OFF",
    "-D", "WITH_OPENEXR=OFF",
    "-D", "WITH_WEBP=OFF",
    "-D", "WITH_JASPER=OFF",
    "-D", "WITH_1394=OFF",

    # KEEP BASIC IMAGE SUPPORT (For PyAutoGUI template loading)
    "-D", "WITH_JPEG=ON",
    "-D", "WITH_PNG=ON"
)

Write-Host ">>> Configuring CMake..." -ForegroundColor Cyan
& cmake @CMakeArgs

# --- 5. build ---
Write-Host ">>> Building Release Target..." -ForegroundColor Cyan
& cmake --build $BuildDir --config Release --parallel $Env:NUMBER_OF_PROCESSORS

# --- 6. Artifact Extraction ---
$BuildArtifacts = Get-ChildItem -Path "$BuildDir\lib\python3\Release" -Filter "*.pyd" -Recurse
if ($BuildArtifacts) {
    $Artifact = $BuildArtifacts | Select-Object -First 1
    Write-Host "`n>>> BUILD SUCCESSFUL!" -ForegroundColor Green
    Write-Host "Artifact Location: $($Artifact.FullName)" -ForegroundColor White
    Write-Host "Size: $([math]::Round($Artifact.Length / 1MB, 2)) MB" -ForegroundColor Yellow
} else {
    Write-Error "Build finished but no .pyd artifact found in $BuildDir"
}
