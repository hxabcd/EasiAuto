using System;
using System.Linq;
using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Data.Core;
using Avalonia.Data.Core.Plugins;
using Avalonia.Markup.Xaml;
using EasiAuto.Core.Enums;
using EasiAuto.Core.Services;
using EasiAuto.Core.Services.Seewo;
using EasiAuto.Core.Services.Automation.Strategies;
using EasiAuto.ViewModels;
using EasiAuto.Views;
using Microsoft.Extensions.DependencyInjection;

namespace EasiAuto;

public partial class App : Application
{
    public static IServiceProvider Services { get; private set; } = null!;

    public override void Initialize()
    {
        AvaloniaXamlLoader.Load(this);
    }

    public override void OnFrameworkInitializationCompleted()
    {
        var services = new ServiceCollection();

        // 注册服务
        services.AddSingleton(sp =>
        {
            var configService = new ConfigService();
            configService.LoadConfig();
            return configService;
        });
        services.AddTransient(sp =>
            sp.GetRequiredService<ConfigService>().Config.Login);
        services.AddSingleton<SeewoClient>();
        services.AddSingleton<EasiNotePatcher>();
        services.AddTransient<InjectLogin>();
        services.AddTransient<UiaLogin>();
        services.AddTransient<BaseLoginStrategy>(sp =>
        {
            var config = sp.GetRequiredService<ConfigService>().Config.Login;
            return config.Method switch
            {
                LoginMethod.Inject => sp.GetRequiredService<InjectLogin>(),
                LoginMethod.Uia => sp.GetRequiredService<UiaLogin>(),
                _ => sp.GetRequiredService<InjectLogin>(),
            };
        });

        Services = services.BuildServiceProvider();

        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            desktop.MainWindow = new MainWindow
            {
                DataContext = new MainWindowViewModel(),
            };
        }

        base.OnFrameworkInitializationCompleted();
    }
}