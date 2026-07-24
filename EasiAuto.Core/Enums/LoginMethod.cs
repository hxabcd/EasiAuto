using System.ComponentModel;

namespace EasiAuto.Core.Enums;

/// <summary>
/// 自动登录方式
/// </summary>
public enum LoginMethod
{
    [Description("固定位置")] Fixed = 0,
    /// 
    [Description("图像识别")] Cv = 1,
    [Description("自动定位")] Uia = 2,
    [Description("进程注入")] Inject = 3,
}