using System.Drawing;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Logging.Console;
using Pastel;

namespace EasiAuto.Core.Services.Logging;

public sealed class LoggingConsoleFormatter() : ConsoleFormatter("easiauto")
{
    private const string TimestampFormat = "yyyy-MM-dd HH:mm:ss.fff";

    public override void Write<TState>(
        in LogEntry<TState> logEntry,
        IExternalScopeProvider? scopeProvider,
        TextWriter textWriter)
    {
        var timestamp = DateTime.Now.ToString(TimestampFormat);
        var level = logEntry.LogLevel;
        var category = logEntry.Category;
        var message = logEntry.Formatter(logEntry.State, logEntry.Exception);

        var (levelColor, levelText) = level switch
        {
            LogLevel.Trace => (Color.Gray, "TRACE"),
            LogLevel.Debug => (Color.Gray, "DEBUG"),
            LogLevel.Information => (Color.LimeGreen, "INFO "),
            LogLevel.Warning => (Color.Orange, "WARN "),
            LogLevel.Error => (Color.Red, "ERROR"),
            LogLevel.Critical => (Color.White, "FATAL"),
            _ => throw new ArgumentOutOfRangeException(nameof(level))
        };

        var levelBg = level == LogLevel.Critical ? Color.DarkRed : default(Color?);

        var levelPart = $"[{levelText}]".Pastel(levelColor);
        if (levelBg.HasValue)
            levelPart = levelPart.PastelBg(levelBg.Value);

        textWriter.Write(timestamp);
        textWriter.Write(' ');
        textWriter.Write(levelPart);
        textWriter.Write(' ');
        textWriter.Write(category.Pastel(Color.Cyan));
        textWriter.Write(' ');
        textWriter.Write(message);

        if (logEntry.Exception != null)
        {
            textWriter.WriteLine();
            textWriter.Write(logEntry.Exception.ToString().Pastel(Color.Red));
        }

        textWriter.WriteLine();
    }
}