namespace EasiAuto.Core.Services.Logging;

public sealed class LoggingScope(object? state, Action onDispose) : IDisposable
{
    public object? State { get; } = state;

    public void Dispose() => onDispose();
}