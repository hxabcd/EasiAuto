using System.Diagnostics;
using EasiAuto.Core.Exceptions;
using EasiAuto.Core.Models;
using EasiAuto.Core.Models.Login;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Definitions;
using FlaUI.UIA3;
using Microsoft.Extensions.Logging;
using static EasiAuto.Core.Helpers.ProcessHelper;

namespace EasiAuto.Core.Services.Automation.Strategies;

public class UiaLogin(ILogger<BaseLoginStrategy> logger, LoginConfig loginConfig)
    : BaseLoginStrategy(logger, loginConfig)
{
    protected override string GetStrategyName() => "Uia";

    protected override IReadOnlySet<Type> SupportedCredentials { get; }
        = new HashSet<Type> { typeof(PhonePasswordCredential) };

    protected override bool CheckLoggedIn(LoginCredential credential)
    {
        return false; // TODO
    }

    protected override void Login(LoginCredential rawCredential, Process easiNoteProcess, nint easiNoteHwnd)
    {
        var isIwb = LoginConfig.IsIwb;
        var credential = rawCredential as PhonePasswordCredential
                     ?? throw new LoginCredentialTypeException("不支持的凭据种类", rawCredential.GetType().Name);

        CurrentProgress = "尝试自动登录";
        CurrentProgress = "连接 UI Automation 后端至希沃白板";
        var app = FlaUI.Core.Application.Attach(easiNoteProcess);
        using var automation = new UIA3Automation();

        var window = app.GetMainWindow(automation) ?? throw new InvalidOperationException("找不到希沃白板窗口");
        window.Focus();

        // 如果从白板界面进入，先点登录按钮打开登录弹窗
        if (isIwb)
        {
            CurrentProgress = "点击进入登录界面";
            var iwbLoginButton = window.FindFirstDescendant(cf => cf.ByAutomationId("ProfileButton")
                                     .And(cf.ByControlType(ControlType.Button)))
                                 ?? throw new InvalidOperationException("找不到登录入口按钮");
            iwbLoginButton.Click();
            Sleep(LoginConfig.Timeout.EnterLoginUi);

            CurrentProgress = "切换到登录界面";
            // 从桌面层全树搜索登录弹窗
            var loginDialog = automation.GetDesktop()
                                  .FindFirstDescendant(cf => cf.ByAutomationId("IWBLogin"))
                              ?? throw new InvalidOperationException("找不到登录弹窗 IWBLogin");
            window = loginDialog.AsWindow();
        }

        // 切换到账号登录 Tab
        CurrentProgress = "定位并点击账号登录按钮";
        var accountLoginButton = window
                                     .FindFirstDescendant(cf =>
                                         cf.ByAutomationId(isIwb ? "AccountRadioButton" : "AccountLoginRadioButton")
                                             .And(cf.ByControlType(ControlType.RadioButton)))
                                 ?? throw new InvalidOperationException("找不到账号登录按钮");
        accountLoginButton.Click();
        Sleep(LoginConfig.Timeout.SwitchTab);

        // 定位登录表单
        CurrentProgress = "定位登录控件";
        var accountLoginPage = window
                                   .FindFirstDescendant(cf =>
                                       cf.ByAutomationId(isIwb ? "IwbAccountControl" : "PasswordLoginControl")
                                           .And(cf.ByControlType(ControlType.Custom)))
                               ?? throw new InvalidOperationException("找不到登录表单");

        // 输入账号
        CurrentProgress = "定位输入框并填入账号";
        var accountInput = accountLoginPage
                               .FindFirstDescendant(cf => cf.ByControlType(ControlType.ComboBox))
                               ?.FindFirstDescendant(cf => cf.ByControlType(ControlType.Edit))
                           ?? throw new InvalidOperationException("找不到账号输入框");
        accountInput.AsTextBox().Text = credential.Phone;

        // 输入密码
        CurrentProgress = "定位输入框并填入密码";
        var passwordInput = accountLoginPage
                                .FindFirstDescendant(cf => cf.ByAutomationId("PasswordBox")
                                    .And(cf.ByControlType(ControlType.Edit)))
                            ?? throw new InvalidOperationException("找不到密码输入框");
        passwordInput.AsTextBox().Text = credential.Password;

        // 勾选用户协议
        CurrentProgress = "定位用户协议复选框并勾选";
        var agreementCheckBox = accountLoginPage
                                    .FindFirstDescendant(cf => cf.ByAutomationId("AgreementCheckBox")
                                        .And(cf.ByControlType(ControlType.CheckBox)))
                                ?? throw new InvalidOperationException("找不到用户协议复选框");
        if (agreementCheckBox.AsCheckBox().ToggleState == ToggleState.Off)
        {
            agreementCheckBox.AsCheckBox().Toggle();
        }

        // 点击登录
        CurrentProgress = "点击登录按钮";
        var loginButton = accountLoginPage
                              .FindFirstDescendant(cf => cf.ByAutomationId("LoginButton")
                                  .And(cf.ByControlType(ControlType.Button)))
                          ?? throw new InvalidOperationException("找不到登录按钮");
        loginButton.Click();
    }
}