using System.Collections.Specialized;
using System.ComponentModel;
using System.Reflection;
using System.Text.Json;
using CommunityToolkit.Mvvm.ComponentModel;
using EasiAuto.Core.Converters;
using EasiAuto.Core.Models;

namespace EasiAuto.Core.Services;

public class ConfigService
{
    private AppConfig? _config;
    private readonly JsonSerializerOptions _jsonOptions;
    private readonly List<IDisposable> _subscriptions = [];

    private static string ConfigFilePath =>
        Path.Combine(AppContext.BaseDirectory, "data", "AppConfig.json");

    public AppConfig Config => _config!;

    public ConfigService()
    {
        _jsonOptions = new JsonSerializerOptions
        {
            WriteIndented = true,
            PropertyNamingPolicy = null,
            Converters =
            {
                new PointJsonConverter(),
                new SizeJsonConverter(),
            },
        };
    }

    /// <summary>
    /// 加载配置文件。若文件不存在则创建默认配置。
    /// </summary>
    public void LoadConfig()
    {
        if (File.Exists(ConfigFilePath))
        {
            var json = File.ReadAllText(ConfigFilePath);
            _config = JsonSerializer.Deserialize<AppConfig>(json, _jsonOptions)
                      ?? new AppConfig();
        }
        else
        {
            _config = new AppConfig();
            SaveConfig();
        }

        SubscribeRecursive(_config);
    }

    /// <summary>
    /// 保存当前配置到文件。
    /// </summary>
    public void SaveConfig()
    {
        if (_config == null) return;

        var dir = Path.GetDirectoryName(ConfigFilePath);
        if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
            Directory.CreateDirectory(dir);

        var json = JsonSerializer.Serialize(_config, _jsonOptions);
        File.WriteAllText(ConfigFilePath, json);
    }

    /// <summary>
    /// 重置所有配置为默认值并保存。
    /// </summary>
    public void ResetAll()
    {
        UnsubscribeAll();
        _config = new AppConfig();
        SubscribeRecursive(_config);
        SaveConfig();
    }

    /// <summary>
    /// 按路径重置配置项为默认值。
    /// </summary>
    /// <param name="path">点号分隔的路径，如 <c>"Login.Timeout.Terminate"</c> 或 <c>"Login.Timeout"</c></param>
    /// <returns>路径有效则返回 true</returns>
    public bool ResetByPath(string path)
    {
        if (_config == null) return false;

        var parts = path.Split('.', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length == 0) return false;

        try
        {
            var defaultConfig = new AppConfig();

            object currentParent = _config;
            object defaultParent = defaultConfig;

            for (int i = 0; i < parts.Length - 1; i++)
            {
                var key = parts[i];
                var prop = currentParent.GetType().GetProperty(key,
                    BindingFlags.Public | BindingFlags.Instance);
                var defaultProp = defaultParent.GetType().GetProperty(key,
                    BindingFlags.Public | BindingFlags.Instance);

                if (prop == null || defaultProp == null)
                    return false;

                currentParent = prop.GetValue(currentParent)!;
                defaultParent = defaultProp.GetValue(defaultParent)!;
            }

            var lastKey = parts[^1];
            var targetProp = currentParent.GetType().GetProperty(lastKey,
                BindingFlags.Public | BindingFlags.Instance);
            var defaultTargetProp = defaultParent.GetType().GetProperty(lastKey,
                BindingFlags.Public | BindingFlags.Instance);

            if (targetProp == null || defaultTargetProp == null || !targetProp.CanWrite)
                return false;

            var defaultValue = defaultTargetProp.GetValue(defaultParent);
            targetProp.SetValue(currentParent, defaultValue);

            UnsubscribeAll();
            SubscribeRecursive(_config);
            SaveConfig();

            return true;
        }
        catch
        {
            return false;
        }
    }

    private void SubscribeRecursive(object obj)
    {
        if (obj is INotifyPropertyChanged inpc)
        {
            inpc.PropertyChanged += OnAnyPropertyChanged;
            _subscriptions.Add(new PropertyChangedSubscription(inpc, OnAnyPropertyChanged));
        }

        if (obj is INotifyCollectionChanged collection)
        {
            collection.CollectionChanged += OnCollectionChanged;
            _subscriptions.Add(new CollectionChangedSubscription(collection, OnCollectionChanged));
        }

        foreach (var prop in obj.GetType().GetProperties(
                     BindingFlags.Public | BindingFlags.Instance))
        {
            if (!prop.CanRead || prop.GetIndexParameters().Length > 0)
                continue;

            object? value;
            try
            {
                value = prop.GetValue(obj);
            }
            catch
            {
                continue;
            }

            if (value is ObservableObject)
                SubscribeRecursive(value);
        }
    }

    private void UnsubscribeAll()
    {
        foreach (var sub in _subscriptions)
            sub.Dispose();

        _subscriptions.Clear();
    }

    private void OnAnyPropertyChanged(object? sender, PropertyChangedEventArgs e) => SaveConfig();

    private void OnCollectionChanged(object? sender, NotifyCollectionChangedEventArgs e) => SaveConfig();

    private sealed class PropertyChangedSubscription : IDisposable
    {
        private readonly INotifyPropertyChanged _source;
        private readonly PropertyChangedEventHandler _handler;

        public PropertyChangedSubscription(INotifyPropertyChanged source,
            PropertyChangedEventHandler handler)
        {
            _source = source;
            _handler = handler;
        }

        public void Dispose() => _source.PropertyChanged -= _handler;
    }

    private sealed class CollectionChangedSubscription : IDisposable
    {
        private readonly INotifyCollectionChanged _source;
        private readonly NotifyCollectionChangedEventHandler _handler;

        public CollectionChangedSubscription(INotifyCollectionChanged source,
            NotifyCollectionChangedEventHandler handler)
        {
            _source = source;
            _handler = handler;
        }

        public void Dispose() => _source.CollectionChanged -= _handler;
    }
}