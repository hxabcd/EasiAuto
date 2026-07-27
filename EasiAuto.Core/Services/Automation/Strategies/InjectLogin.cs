using System.Diagnostics;
using EasiAuto.Core.Exceptions;
using EasiAuto.Core.Models;
using EasiAuto.Core.Models.Login;
using EasiAuto.Core.Services.Seewo;
using Microsoft.Extensions.Logging;

namespace EasiAuto.Core.Services.Automation.Strategies;

public class InjectLogin(
    ILogger<BaseLoginStrategy> logger,
    LoginConfig loginConfig,
    SeewoClient seewoClient)
    : BaseLoginStrategy(logger, loginConfig)
{
    protected override string GetStrategyName() => "Inject";

    protected override IReadOnlySet<Type> SupportedCredentials { get; }
        = new HashSet<Type> { typeof(PhonePasswordCredential), typeof(TokenCredential) };

    protected override bool CheckLoggedIn(LoginCredential credential)
    {
        throw new NotImplementedException();
    }

    protected override void Login(LoginCredential rawCredential, Process easiNoteProcess, nint easiNoteHwnd)
    {
        switch (rawCredential)
        {
            case PhonePasswordCredential phoneCred:
                var token = GetTokenViaPhonePassword(phoneCred.Phone, phoneCred.Password);
                LoginWithToken(token, easiNoteProcess, easiNoteHwnd);
                break;
            case TokenCredential tokenCred:
                LoginWithToken(tokenCred.Token, easiNoteProcess, easiNoteHwnd);
                break;
            default:
                throw new LoginCredentialTypeException("不支持的凭据种类", rawCredential.GetType().Name);
        }
    }

    protected string GetTokenViaPhonePassword(string phoneNumber, string password)
    {
        var result = seewoClient.LoginAsync(phoneNumber, password).GetAwaiter().GetResult();
        return result.Token;
    }

    protected void LoginWithToken(string token, Process easiNoteProcess, nint easiNoteHwnd)
    {
    }
}