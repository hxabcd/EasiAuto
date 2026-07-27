using System.Runtime.InteropServices;

namespace EasiAuto.Core.Helpers;

public static class UserSimulationHelper
{
    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);

    private const uint INPUT_MOUSE = 0;
    private const uint INPUT_KEYBOARD = 1;
    private const uint MOUSEEVENTF_MOVE = 0x0001;
    private const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    private const uint MOUSEEVENTF_LEFTUP = 0x0004;
    private const uint MOUSEEVENTF_ABSOLUTE = 0x8000;
    private const uint MOUSEEVENTF_VIRTUALDESK = 0x4000;
    private const uint KEYEVENTF_KEYUP = 0x0002;
    private const uint KEYEVENTF_UNICODE = 0x0004;

    [StructLayout(LayoutKind.Sequential)]
    private struct INPUT
    {
        public uint type;
        public INPUTUNION u;
    }

    [StructLayout(LayoutKind.Explicit)]
    private struct INPUTUNION
    {
        [FieldOffset(0)]
        public MOUSEINPUT mi;
        [FieldOffset(0)]
        public KEYBDINPUT ki;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MOUSEINPUT
    {
        public int dx;
        public int dy;
        public uint mouseData;
        public uint dwFlags;
        public uint time;
        public nint dwExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct KEYBDINPUT
    {
        public ushort wVk;
        public ushort wScan;
        public uint dwFlags;
        public uint time;
        public nint dwExtraInfo;
    }

    /// <summary>
    /// 移动鼠标到屏幕绝对坐标并点击左键
    /// </summary>
    public static void SendMouseClick(int x, int y)
    {
        var screenW = WindowHelper.GetPhysicalScreenWidth();
        var screenH = WindowHelper.GetPhysicalScreenHeight();

        // 标准化到 0-65535 范围
        var nx = (int)(x * 65536.0 / screenW);
        var ny = (int)(y * 65536.0 / screenH);

        var inputs = new INPUT[3];

        // 移动鼠标
        inputs[0].type = INPUT_MOUSE;
        inputs[0].u.mi.dx = nx;
        inputs[0].u.mi.dy = ny;
        inputs[0].u.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK;

        // 按下左键
        inputs[1].type = INPUT_MOUSE;
        inputs[1].u.mi.dwFlags = MOUSEEVENTF_LEFTDOWN;

        // 释放左键
        inputs[2].type = INPUT_MOUSE;
        inputs[2].u.mi.dwFlags = MOUSEEVENTF_LEFTUP;

        SendInput(3, inputs, Marshal.SizeOf<INPUT>());
    }

    /// <summary>
    /// 通过 Unicode 包输入文本
    /// </summary>
    public static void SendTextEntry(string text)
    {
        foreach (var ch in text)
        {
            var inputs = new INPUT[2];

            // 按下
            inputs[0].type = INPUT_KEYBOARD;
            inputs[0].u.ki.wScan = ch;
            inputs[0].u.ki.dwFlags = KEYEVENTF_UNICODE;

            // 释放
            inputs[1].type = INPUT_KEYBOARD;
            inputs[1].u.ki.wScan = ch;
            inputs[1].u.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP;

            SendInput(2, inputs, Marshal.SizeOf<INPUT>());
        }
    }

    /// <summary>
    /// 发送虚拟键按键
    /// </summary>
    public static void SendKeyPress(ushort vkCode)
    {
        var inputs = new INPUT[2];

        inputs[0].type = INPUT_KEYBOARD;
        inputs[0].u.ki.wVk = vkCode;

        inputs[1].type = INPUT_KEYBOARD;
        inputs[1].u.ki.wVk = vkCode;
        inputs[1].u.ki.dwFlags = KEYEVENTF_KEYUP;

        SendInput(2, inputs, Marshal.SizeOf<INPUT>());
    }

}
