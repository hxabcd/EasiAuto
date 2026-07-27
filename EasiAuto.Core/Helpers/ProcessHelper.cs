using System.Diagnostics;

namespace EasiAuto.Core.Helpers;

public static class ProcessHelper
{
    public static bool IsProcessRunning(string processName)
    {
        return Process.GetProcessesByName(processName).Length > 0;
    }

    public static Process? StartProcess(string path, string arguments)
    {
        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = path,
                Arguments = arguments,
                UseShellExecute = true
            };
            return Process.Start(startInfo);
        }
        catch
        {
            return null;
        }
    }

    public static bool StopProcess(string processName)
    {
        try
        {
            var processes = Process.GetProcessesByName(processName);
            foreach (var process in processes)
            {
                process.Kill();
                process.Dispose();
            }

            return true;
        }
        catch
        {
            return false;
        }
    }

    public static void Sleep(double secondTime)
    {
        Thread.Sleep(TimeSpan.FromSeconds(secondTime));
    }

    public static void Sleep(int secondTime)
    {
        Thread.Sleep(TimeSpan.FromSeconds(secondTime));
    }
}

