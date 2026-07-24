using CommunityToolkit.Mvvm.ComponentModel;

namespace EasiAuto.Core.Models;

/// <summary>
/// ClassIsland 相关配置
/// </summary>
public partial class ClassIslandConfig : ObservableObject
{
    /// <summary>自动获取 ClassIsland 的路径</summary>
    [ObservableProperty]
    public partial bool UseAutoPath { get; set; } = true;

    /// <summary>自定义 ClassIsland 的路径</summary>
    [ObservableProperty]
    public partial string CustomPath { get; set; } = "";

    /// <summary>默认显示名称</summary>
    [ObservableProperty]
    public partial string DefaultDisplayName { get; set; } = "自动登录希沃白板";

    /// <summary>默认提前时长（秒）</summary>
    [ObservableProperty]
    public partial int DefaultPreTime { get; set; } = 300;
}
