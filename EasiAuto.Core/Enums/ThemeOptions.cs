using System.ComponentModel;

namespace EasiAuto.Core.Enums;

/// <summary>
/// 应用主题选项
/// </summary>
public enum ThemeOptions
{
    [Description("跟随系统")] Auto = 0,
    [Description("浅色")] Light = 1,
    [Description("深色")] Dark = 2,
}