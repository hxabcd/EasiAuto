using System.Text.Json.Serialization;
using CommunityToolkit.Mvvm.ComponentModel;

namespace EasiAuto.Core.Models;

/// <summary>
/// 统计数据
/// </summary>
public partial class StatisticsConfig : ObservableObject
{
    /// <summary>首次运行日期</summary>
    [ObservableProperty]
    public partial DateTime FirstRunDate { get; set; } = DateTime.UtcNow;

    /// <summary>登录总次数</summary>
    [ObservableProperty]
    public partial int LoginCounts { get; set; } = 0;

    /// <summary>登录成功次数</summary>
    [ObservableProperty]
    public partial int LoginSuccessCounts { get; set; } = 0;

    /// <summary>登录中断次数</summary>
    [ObservableProperty]
    public partial int LoginInterruptCounts { get; set; } = 0;

    /// <summary>本次实例启动时间</summary>
    [ObservableProperty]
    [field: JsonIgnore]
    public partial DateTime ThisInstanceLaunchTime { get; set; } = DateTime.UtcNow;

    /// <summary>总运行时间（秒）</summary>
    [ObservableProperty]
    public partial double TotalRunTime { get; set; } = 0;

    /// <summary>总登录耗时（秒）</summary>
    [ObservableProperty]
    public partial double TotalLoginTime { get; set; } = 0;

    /// <summary>最长单次登录耗时（秒）</summary>
    [ObservableProperty]
    public partial double MaxLoginTime { get; set; } = 0;

    /// <summary>各账号登录次数统计</summary>
    [ObservableProperty]
    public partial Dictionary<string, int> LoginCountsPerAccount { get; set; } = [];
}
