using CommunityToolkit.Mvvm.ComponentModel;

namespace EasiAuto.Core.Models;

/// <summary>
/// 希沃白板相关配置
/// </summary>
public partial class EasiNoteConfig : ObservableObject
{
    /// <summary>自动路径</summary>
    [ObservableProperty]
    public partial bool UseAutoPath { get; set; } = true;

    /// <summary>自定义路径</summary>
    [ObservableProperty]
    public partial string CustomPath { get; set; } = @"C:\Program Files (x86)\Seewo\EasiNote5\swenlauncher\swenlauncher.exe";

    /// <summary>进程名</summary>
    [ObservableProperty]
    public partial string ProcessName { get; set; } = "EasiNote";

    /// <summary>窗口标题</summary>
    [ObservableProperty]
    public partial string WindowTitle { get; set; } = "希沃白板";

    /// <summary>启动参数</summary>
    [ObservableProperty]
    public partial string Args { get; set; } = "";

    /// <summary>查杀进程列表（英文逗号分隔）</summary>
    [ObservableProperty]
    public partial string ExtraKills { get; set; } = "";

    /// <summary>EasiNote 是否已修补</summary>
    [ObservableProperty]
    public partial bool IsEasiNotePatched { get; set; } = false;
}
