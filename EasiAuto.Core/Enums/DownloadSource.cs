using System.ComponentModel;

namespace EasiAuto.Core.Enums;

/// <summary>
/// 下载镜像源
/// </summary>
public enum DownloadSource
{
    [Description("自动选择")] Auto = 0,
    [Description("GitHub")] Github = 1,
    [Description("ghproxy")] Ghproxy = 2,
    [Description("ghfast")] Ghfast = 3,
}