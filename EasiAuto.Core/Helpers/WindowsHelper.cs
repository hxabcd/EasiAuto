using System.Diagnostics;
using System.Drawing;
using System.Runtime.InteropServices;
namespace EasiAuto.Core.Helpers;

public static class WindowHelper
{
    public static nint GetWindowHandle(string windowTitle)
    {
        return FindWindow(null, windowTitle);
    }

    public static nint GetWindowHandle(string className, string windowTitle)
    {
        return FindWindow(className, windowTitle);
    }

    public static nint GetProcessMainWindowHandle(string processName)
    {
        var processes = Process.GetProcessesByName(processName);
        return processes.Length > 0 ? processes[0].MainWindowHandle : nint.Zero;
    }


    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    private static extern nint FindWindow(string? lpClassName, string lpWindowName);

    /// <summary>
    /// 获取屏幕物理宽度（像素）
    /// </summary>
    public static int GetPhysicalScreenWidth()
    {
        return GetSystemMetrics(78); // SM_CXVIRTUALSCREEN
    }

    /// <summary>
    /// 获取屏幕物理高度（像素）
    /// </summary>
    public static int GetPhysicalScreenHeight()
    {
        return GetSystemMetrics(79); // SM_CYVIRTUALSCREEN
    }

    /// <summary>
    /// 获取系统缩放比例（DPI / 96）
    /// </summary>
    public static float GetScale()
    {
        using var g = Graphics.FromHwnd(nint.Zero);
        nint hdc = g.GetHdc();
        var dpi = GetDeviceCaps(hdc, 88); // LOGPIXELSX
        g.ReleaseHdc();
        return dpi / 96f;
    }

    [DllImport("user32.dll")]
    private static extern int GetSystemMetrics(int nIndex);

    [DllImport("gdi32.dll")]
    private static extern int GetDeviceCaps(nint hdc, int nIndex);
}
