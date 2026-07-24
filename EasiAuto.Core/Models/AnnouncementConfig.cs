using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;

namespace EasiAuto.Core.Models;

/// <summary>
/// 公告相关设置
/// </summary>
public partial class AnnouncementConfig : ObservableObject
{
    /// <summary>已隐藏的公告 ID 列表</summary>
    [ObservableProperty]
    public partial ObservableCollection<string> HiddenAnnouncementIds { get; set; } = [];
}