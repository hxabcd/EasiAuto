using EasiAuto.Core.Models.Login;

namespace EasiAuto.Core.Abstraction.Login;

public interface ILoginStrategy
{
    string StrategyName { get; }
    LoginResult Run(LoginCredential credential);
}
