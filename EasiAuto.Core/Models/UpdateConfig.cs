using CommunityToolkit.Mvvm.ComponentModel;
using EasiAuto.Core.Enums;

namespace EasiAuto.Core.Models;

/// <summary>
/// 应用更新相关配置
/// </summary>
public partial class UpdateConfig : ObservableObject
{
    /// <summary>更新模式</summary>
    [ObservableProperty]
    public partial UpdateMode Mode { get; set; } = UpdateMode.CheckAndInstall;

    /// <summary>登录完成后检查更新</summary>
    [ObservableProperty]
    public partial bool ShouldCheckAfterLogin { get; set; } = true;

    /// <summary>更新目标通道</summary>
    [ObservableProperty]
    public partial UpdateChannel TargetUpdateChannel { get; set; } = UpdateChannel.Release;

    /// <summary>下载镜像源</summary>
    [ObservableProperty]
    public partial DownloadSource TargetDownloadSource { get; set; } = DownloadSource.Auto;

    /// <summary>上个版本号</summary>
    [ObservableProperty]
    public partial string? LastVersion { get; set; } = null;

    /// <summary>上次检查更新时间</summary>
    /// 
    [ObservableProperty]
    public partial DateTime? LastUpdateCheckTime { get; set; } = null;
}