# 最小化 OpenCV 构建（面向 PyAutoGUI）

此目录包含一个 PowerShell 脚本，使用 AI 生成，用于在 Windows 上编译轻量版 OpenCV Python 二进制（`cv2*.pyd`）。

脚本主要面向 `pyautogui/pyscreeze` 的模板匹配场景，支持 Python 3.12+。

## 功能特点

- 默认目标版本：Python `3.12`
- 输出文件：`cv2.cp<pyver>-win_amd64.pyd`
- 自动检测工具链（`Visual Studio` / `Ninja` 回退）
- 支持手动指定 CMake 生成器
- 构建失败时提供清晰报错

## 前置要求

1. Windows x64
2. CMake（建议 3.20+）
3. Git
4. `uv`（脚本可自动安装）
5. 可用的 C++ 工具链（满足其一）：
   - Visual Studio 2022/2026，勾选 `使用 C++ 的桌面开发`
   - 包含 MSVC x64/x86 工具和 Windows SDK

## 构建命令

在仓库根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\develop\minimal_opencv\build_minimal.ps1
```

显式指定 Python 版本（等价）：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\develop\minimal_opencv\build_minimal.ps1 -PythonVersion 3.12
```

如果需要强制指定生成器（例如 VS 2026）：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\develop\minimal_opencv\build_minimal.ps1 -PythonVersion 3.12 -CMakeGenerator "Visual Studio 18 2026"
```

## 输出位置

默认工作目录：

```text
./opencv_minimal_build_py312/
```

典型产物路径：

```text
./opencv_minimal_build_py312/build/lib/python3/Release/cv2.cp312-win_amd64.pyd
```

脚本还会在 `build/` 下递归查找 `.pyd` 并打印最终路径。

## 脚本参数

- `-PythonVersion`（字符串，默认：`3.12`）
- `-CMakeGenerator`（字符串，默认：`auto`）

## 体积说明

当前默认策略偏向兼容性：

- `BUILD_LIST=core,imgproc,imgcodecs,python3`
- 启用 JPEG/PNG

这样能保证 `python3` 绑定稳定，并兼容常见图像加载流程。

## 常见错误

### `No usable C++ toolchain found for OpenCV build`

安装 Visual Studio Build Tools / Community，并勾选 C++ 工作负载后重试。

### CMake 配置阶段出现 `Invalid character escape '\U'`

当前脚本已把 Python 库路径转换为 CMake 安全的 `/` 格式。
如果仍出现，请删除 `opencv_minimal_build_py<ver>/build` 后重试。

### `Build output directory not found ...`

通常是前面的 configure/build 已失败导致。
请优先查看该报错之前第一条 CMake 错误信息。

### CMake 的 deprecation/dev warning

这是 OpenCV/CMake 上游警告，通常不影响最终产物生成。

## 快速验证

构建完成后，在 Python 3.12 运行环境中执行：

```python
import cv2
print(cv2.__version__)
print(cv2.__file__)
```

## 与 PyAutoGUI 集成

把 `cv2.cp312-win_amd64.pyd` 放到当前运行时可导入的位置（项目运行路径或环境的 site-packages）。

当 `import cv2` 成功后，`pyautogui` / `pyscreeze` 会自动使用 OpenCV。
