using Microsoft.Win32;

namespace EasiAuto.Core.Helpers;

public static class EasiNoteHelper
{
    public static string? GetEasiNotePathFromReg()
    {
        var path = Registry.GetValue(
            @"HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Seewo\EasiNote5",
            "ExePath",
            null
        );
        return path as string;
    }
}

public enum EasiNotePathSource
{
    Auto,
    Custom,
    Default
}