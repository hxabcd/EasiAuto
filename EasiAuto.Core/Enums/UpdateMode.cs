using System.ComponentModel;

namespace EasiAuto.Core.Enums;

/// <summary>
/// 应用更新模式
/// </summary>
public enum UpdateMode
{
    [Description("从不自动更新")] Never = 0,
    [Description("自动检查更新并通知")] CheckAndNotify = 1,
    [Description("自动检查更新并下载")] CheckAndDownload = 2,
    [Description("自动检查更新并安装")] CheckAndInstall = 3,
}