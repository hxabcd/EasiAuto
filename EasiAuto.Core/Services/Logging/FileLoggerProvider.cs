using System.Collections.Concurrent;
using Microsoft.Extensions.Logging;

namespace EasiAuto.Core.Services.Logging;

public sealed class FileLoggerProvider : ILoggerProvider
{
    private readonly string _logDirectory;
    private readonly ConcurrentDictionary<string, FileLogger> _loggers = new();
    private readonly LogLevel _minLevel;
    private bool _disposed;

    public FileLoggerProvider(string? logDirectory = null, LogLevel minLevel = LogLevel.Information)
    {
        _logDirectory = logDirectory ?? Path.Combine(AppContext.BaseDirectory, "logs");
        _minLevel = minLevel;
        CleanOldLogs();
    }

    public ILogger CreateLogger(string categoryName) =>
        _loggers.GetOrAdd(categoryName, name => new FileLogger(name, _logDirectory, _minLevel));

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _loggers.Clear();
    }

    private void CleanOldLogs()
    {
        try
        {
            if (!Directory.Exists(_logDirectory)) return;

            var cutoff = DateTime.Now.AddDays(-30);
            foreach (var file in Directory.GetFiles(_logDirectory, "EasiAuto_*.log"))
            {
                if (File.GetLastWriteTime(file) < cutoff)
                    File.Delete(file);
            }
        }
        catch
        {
            // ignored
        }
    }
}