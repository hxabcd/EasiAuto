using Microsoft.Extensions.Logging;

namespace EasiAuto.Core.Services.Logging;

public sealed class FileLogger(string category, string logDirectory, LogLevel minLevel) : ILogger
{
    private readonly Lock _lock = new();

    private string _currentDate = string.Empty;
    private string _currentFilePath = string.Empty;

    public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

    public bool IsEnabled(LogLevel logLevel) => logLevel >= minLevel;

    public void Log<TState>(
        LogLevel logLevel,
        EventId eventId,
        TState state,
        Exception? exception,
        Func<TState, Exception?, string> formatter)
    {
        if (!IsEnabled(logLevel)) return;

        var message = formatter(state, exception);
        var timestamp = DateTime.Now;
        var dateKey = timestamp.ToString("yyyyMMdd");
        var line =
            $"{timestamp:yyyy-MM-dd HH:mm:ss.fff} [{logLevel.ToString().ToUpperInvariant()}] [{category}] {message}";

        if (exception != null)
            line += $"{Environment.NewLine}{exception}";

        lock (_lock)
        {
            if (dateKey != _currentDate)
            {
                _currentDate = dateKey;
                _currentFilePath = Path.Combine(logDirectory, $"EasiAuto_{dateKey}.log");
                Directory.CreateDirectory(logDirectory);
            }

            File.AppendAllText(_currentFilePath, line + Environment.NewLine);
        }
    }
}