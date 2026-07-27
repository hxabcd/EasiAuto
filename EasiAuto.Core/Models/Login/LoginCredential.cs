namespace EasiAuto.Core.Models.Login;

public abstract record LoginCredential
{
    private protected LoginCredential() { } // 仅允许同程序集内子类继承
}

public record PhonePasswordCredential(string Phone, string Password) : LoginCredential;

public record TokenCredential(string Token) : LoginCredential;
