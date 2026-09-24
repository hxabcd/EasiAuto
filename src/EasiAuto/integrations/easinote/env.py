"""希沃白板启动环境检测

EasiNote5 由 `Cvte.EasiNote.Utils.HardwareRecognizer.IsIwb` 决定启动路径：
为真时进入白板/授课页，携带 IWB 版登录界面（需先点击“登录”按钮）；
为假时进入编辑路径，直接弹出 PC 版登录界面。
该值按以下顺序确定（后层覆盖前层）：

1. `Configs.fkv` 中 `DeviceInfo.Type` 的固定 GUID（IWB / PC）覆写；
2. 在线枚举到的希沃系 HID 触摸 MCU（`Cvte.Mcu.McuHunter.FindAll`）；
3. `Configs.fkv` 中 `DeviceCache.IsIwb` 的历史探测缓存。

本模块复刻上述判定，供登录流程自动匹配界面路径。

NOTE: 判定依据为 EasiNote5 5.2.4.9855 的反编译结果，白板升级后可能需要同步修订。
"""

from __future__ import annotations

import ctypes
import os
import re
from ctypes import wintypes
from pathlib import Path

from loguru import logger

# 设备类型覆写值（Configs.fkv: DeviceInfo.Type）
IWB_DEVICE_GUID = "228756AD-0620-497E-94FB-4022DB99C853"
PC_DEVICE_GUID = "07BFE486-A99E-430C-8CCE-8A9955417614"

# 希沃系 USB 厂商号（McuHunter.Vids）
SEEWO_MCU_VIDS = frozenset({0x1FF7, 0x222A})
# PID 区间（McuHunter.PidSubsection，闭区间）
SEEWO_MCU_PID_RANGES = ((1, 32), (3872, 3888), (3890, 3903))
# 接口键名（McuHunter.PchKey）
SEEWO_MCU_KEY_HINTS = ("mi_00", "col03")

# 定点设备表（McuHunter.DefineDeviceMcu，元组为 (pid, vid, key)）
# NOTE: 命中本表任一条目即视为希沃 MCU；EasiNote 另以 REV_xxxx 区分 McuVII / McuVIII
# 多屏型号，但该 REV 只影响"哪台设备被选为 DetectedMcu"，不改变是否进入白板路径的结论。
SEEWO_MCU_DEVICES = (
    (0x1FF7, 0x0F15, "mi_00&col02"),  # CommonMcu
    (0x0F15, 0x1FF7, "mi_00"),  # Mcu638 / Mcu551
    (0x0001, 0x1FF7, "col03"),  # McuTouch
    (0xAA55, 0x10E0, "col01"),  # Mcu309，老式 CV 触摸框
    (0x0F21, 0x1FF7, "mi_00&col02"),  # Mcu551B2
    (0x0F26, 0x1FF7, "mi_00"),  # McuV
    (0x0F50, 0x1FF7, "mi_00"),  # McuFourSidesInfraredBlackboard
    (0x0F28, 0x1FF7, "mi_00"),  # McuFlatFrogTouchFrame
    (0x0F27, 0x1FF7, "mi_00"),  # McuVIAbroad
    (0x0F33, 0x1FF7, "mi_00"),  # McuVI / McuVII 四边红外系列
    (0x0F33, 0x1FF7, ""),  # McuVII / McuVIII 系列，仅以 REV 区分型号
)
# NOTE: 另有合作方触摸框 VID_2757&PID_0100，命中时 IsRealSeewoIwb 仍为假，
# 即不会进入白板路径，故不计入匹配表。

# 启动模式参数
MODE_OPTIONS = frozenset({"-m", "--mode"})

# 希沃白板配置缓存（纯文本 KV，记录之间以单独的 ">" 行分隔）
_APPDATA = os.environ.get("APPDATA")
CONFIGS_FKV_PATH = Path(_APPDATA, "Seewo", "EasiNote5", "Data", "Configs.fkv") if _APPDATA else None

# 设备接口路径示例: \\?\hid#vid_1ff7&pid_0f33&mi_00#8&1&0&0000#{4d1e55b2-...}
_DEVICE_PATH_PATTERN = re.compile(r"vid_([0-9a-f]{4})&pid_([0-9a-f]{4})(?:&([^#]+))?", re.IGNORECASE)

_DIGCF_PRESENT = 0x02
_DIGCF_DEVICEINTERFACE = 0x10
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
# SP_DEVICE_INTERFACE_DETAIL_DATA 的 cbSize 为固定值（32 位 6，64 位 8），不可用 sizeof
_DETAIL_DATA_CB_SIZE = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", _GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


class McuDevice:
    """一台候选希沃 MCU 设备（对应 Cvte.Mcu.UsbId）

    Attributes:
        vid: USB 厂商号
        pid: USB 产品号
        key: 接口键名，如 "mi_00&col02"，可能为空
        path: 完整设备接口路径
    """

    def __init__(self, path: str) -> None:
        self.path = path
        match = _DEVICE_PATH_PATTERN.search(path)
        self.vid = int(match.group(1), 16) if match else -1
        self.pid = int(match.group(2), 16) if match else -1
        self.key = (match.group(3) or "") if match else ""

    def __repr__(self) -> str:
        return f"McuDevice(pid=0x{self.pid:04X}, vid=0x{self.vid:04X}, key={self.key!r})"

    def matches(self, pid: int, vid: int, key: str) -> bool:
        """是否与指定 MCU 特征一致（key 为空表示只比较 PID/VID）"""
        if self.pid != pid or self.vid != vid:
            return False
        if not key:
            return True
        return key.lower() in self.key.lower() or key.lower() in self.path.lower()

    def is_seewo_mcu(self) -> bool:
        """是否为希沃系触摸 MCU（等价于 McuHunter.FindAll 的过滤结果非空）"""
        if any(self.matches(pid, vid, key) for pid, vid, key in SEEWO_MCU_DEVICES):
            return True

        if self.vid not in SEEWO_MCU_VIDS:
            return False
        if not any(low <= self.pid <= high for low, high in SEEWO_MCU_PID_RANGES):
            return False

        return any(hint in self.key.lower() for hint in SEEWO_MCU_KEY_HINTS)


def read_config_value(name: str) -> str | None:
    """从希沃白板 Configs.fkv 读取指定键的值，不存在时返回 None

    文件格式为若干记录，每条记录为「键行 + 若干值行」，记录之间以单独的 ">" 行分隔；
    以 ">" 开头的其他行是注释（如 "> 配置文件"）。
    """
    path = CONFIGS_FKV_PATH
    if path is None or not path.is_file():
        return None

    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as e:
        logger.debug(f"读取希沃白板配置失败: {e}")
        return None

    lines: list[str] = []
    for line in text.splitlines():
        if line == ">":
            if len(lines) >= 2 and lines[0] == name:
                return "\n".join(lines[1:])
            lines.clear()
        elif line.startswith(">"):
            continue
        else:
            lines.append(line)

    return None


def enum_hid_devices() -> list[McuDevice]:
    """枚举当前在线的 HID 设备（等价于 Cvte.Mcu.HidDevices.GetDevices）"""
    try:
        hid = ctypes.WinDLL("hid.dll")
        setupapi = ctypes.WinDLL("setupapi.dll")
    except OSError as e:
        logger.debug(f"加载 HID 相关动态库失败: {e}")
        return []

    guid = _GUID()
    hid.HidD_GetHidGuid(ctypes.byref(guid))

    setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
    setupapi.SetupDiGetClassDevsW.argtypes = [
        ctypes.POINTER(_GUID),
        wintypes.LPCWSTR,
        wintypes.HWND,
        wintypes.DWORD,
    ]
    # 该函数无 ANSI/Unicode 之分，导出名不带后缀
    setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.POINTER(_GUID),
        wintypes.DWORD,
        ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA),
    ]
    setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]

    device_info = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(guid), None, None, _DIGCF_PRESENT | _DIGCF_DEVICEINTERFACE
    )
    if device_info in (None, _INVALID_HANDLE_VALUE):
        logger.debug("获取 HID 设备列表失败")
        return []

    devices: list[McuDevice] = []
    try:
        interface = _SP_DEVICE_INTERFACE_DATA()
        interface.cbSize = ctypes.sizeof(_SP_DEVICE_INTERFACE_DATA)

        index = 0
        while setupapi.SetupDiEnumDeviceInterfaces(
            device_info, None, ctypes.byref(guid), index, ctypes.byref(interface)
        ):
            index += 1

            required = wintypes.DWORD(0)
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                device_info, ctypes.byref(interface), None, 0, ctypes.byref(required), None
            )
            if not required.value:
                continue

            buffer = ctypes.create_string_buffer(required.value)
            ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD))[0] = _DETAIL_DATA_CB_SIZE
            if setupapi.SetupDiGetDeviceInterfaceDetailW(
                device_info, ctypes.byref(interface), buffer, required.value, None, None
            ):
                # DevicePath 为 WCHAR 数组（位于 cbSize 之后），按 NUL 结尾读取
                path = ctypes.wstring_at(ctypes.addressof(buffer) + ctypes.sizeof(wintypes.DWORD))
                devices.append(McuDevice(path))
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(device_info)

    return devices


def detect_is_iwb() -> bool:
    """检测希沃白板在本机默认启动时是否进入白板（IWB）路径

    判定顺序与 EasiNote5 一致：配置覆写 > 硬件探测 > 缓存兜底。
    """
    device_type = (read_config_value("DeviceInfo.Type") or "").strip().strip("{}").upper()
    if device_type == IWB_DEVICE_GUID:
        logger.info("[环境] 由希沃白板配置判定为白板设备")
        return True
    if device_type == PC_DEVICE_GUID:
        logger.info("[环境] 由希沃白板配置判定为普通电脑")
        return False

    for device in enum_hid_devices():
        if device.is_seewo_mcu():
            logger.info(f"[环境] 检测到希沃触摸设备: {device!r}")
            return True

    if (read_config_value("DeviceCache.IsIwb") or "").strip().lower() == "true":
        logger.info("[环境] 由希沃白板设备缓存判定为白板设备")
        return True

    logger.info("[环境] 未检测到希沃触摸设备，判定为普通电脑")
    return False


def parse_start_mode(args: str) -> str | None:
    """解析启动参数中显式指定的启动模式（小写），未指定时返回 None"""
    tokens = args.split()
    for index, token in enumerate(tokens):
        if token.lower() in MODE_OPTIONS:
            return tokens[index + 1].lower() if index + 1 < len(tokens) else None
    return None


def resolve_is_iwb(args: str = "") -> bool:
    """判断以指定参数启动希沃白板后是否进入白板（IWB）路径

    与 EasiNote5 的决策顺序一致：命令行 `-m` 显式指定时优先，否则按机器环境检测。
    """
    mode = parse_start_mode(args)
    if mode == "display":
        logger.info(f"[环境] 由启动参数判定为白板界面: {args!r}")
        return True
    if mode == "edit":
        logger.info(f"[环境] 由启动参数判定为普通界面: {args!r}")
        return False

    return detect_is_iwb()
