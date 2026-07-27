using Cvte.EasiNote;
using Cvte.EasiNote.Account;
using Cvte.EasiNote.Account.Auth.Authenticators;
using Cvte.EasiNote.Account.Auth.Login;
using Cvte.EasiNote.Account.Auth.LoginToken;
using Cvte.EasiNote.Account.Datum;
using Cvte.EasiNote.Utils;
using Newtonsoft.Json;
using System.IO.Pipes;
using System.Reflection;
using System.Windows;

namespace SeewoPipeBridge
{
    public class LoginData
    {
        public int statusCode { get; set; }
        public string token { get; set; }
        public string userId { get; set; }
        public string userName { get; set; }
        public string nickName { get; set; }
        public string phone { get; set; }
        public string result { get; set; }
        public string message { get; set; }
    }

    public static class SeewoPipeBridge
    {

        public static void StartBridge()
        {
            _ = Task.Run(() => StartLoginInfoPipe());
            Task.Run(async delegate ()
            {
                while (true)
                {
                    using (NamedPipeServerStream pipe = new NamedPipeServerStream("SeewoOpenTokenPipe", PipeDirection.In, 1))
                    {
                        try
                        {
                            pipe.WaitForConnection();
                            using (StreamReader reader = new StreamReader(pipe))
                            {
                                string jsonData = await reader.ReadLineAsync();
                                if (!string.IsNullOrEmpty(jsonData))
                                {
                                    LoginData data = JsonConvert.DeserializeObject<LoginData>(jsonData);

                                    if (data != null && data.statusCode == 202 && !string.IsNullOrEmpty(data.token))
                                    {
                                        var loginedInfo = new LoginedInfo(
                                            data.token,
                                            data.userId ?? "",
                                            data.userId ?? "",
                                            data.nickName ?? "",
                                            "",
                                            data.phone ?? "",
                                            ""
                                        );

                                        var authenticator = new QrCodeTokenAuthenticator(loginedInfo);

                                        await Application.Current.Dispatcher.InvokeAsync(async () =>
                                        {
                                            try
                                            {
                                                var response = await AccountLoginFactory.CloudLoginProvider.LoginAsync(authenticator);

                                                if (response != null && response.Success)
                                                {
                                                    bool isIwbMode = HardwareRecognizer.IsIwb;

                                                    INotifyProvider notifyProvider = null;
                                                    try
                                                    {
                                                        Type cloudApiType = Type.GetType("Cvte.EasiNote.Cloud.CloudApi, EasiNote.Api");
                                                        if (cloudApiType != null)
                                                        {
                                                            var notifyProviderProp = cloudApiType.GetProperty("NotifyIconProvider",
                                                                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
                                                            if (notifyProviderProp != null)
                                                            {
                                                                notifyProvider = notifyProviderProp.GetValue(null) as INotifyProvider;
                                                            }
                                                        }
                                                    }
                                                    catch { }

                                                    Window targetWindow = null;
                                                    foreach (Window w in Application.Current.Windows)
                                                    {
                                                        string typeName = w.GetType().Name;
                                                        if (isIwbMode && (typeName == "DisplayWindow" || typeName.Contains("Display")))
                                                        {
                                                            targetWindow = w;
                                                            break;
                                                        }
                                                        else if (!isIwbMode && (typeName.Contains("MainEditingTab") || typeName.Contains("PcHub")))
                                                        {
                                                            targetWindow = w;
                                                            break;
                                                        }
                                                    }

                                                    if (targetWindow == null && notifyProvider != null)
                                                    {
                                                        if (isIwbMode)
                                                            notifyProvider.ShowIWBLoginWindow(true);
                                                        else
                                                            notifyProvider.ShowPcHubWindow(false);

                                                        foreach (Window w in Application.Current.Windows)
                                                        {
                                                            string typeName = w.GetType().Name;
                                                            if (isIwbMode && (typeName == "DisplayWindow" || typeName.Contains("Display")))
                                                            {
                                                                targetWindow = w;
                                                                break;
                                                            }
                                                            else if (!isIwbMode && (typeName.Contains("MainEditingTab") || typeName.Contains("PcHub")))
                                                            {
                                                                targetWindow = w;
                                                                break;
                                                            }
                                                        }
                                                    }

                                                    Window loginWindow = null;
                                                    foreach (Window w in Application.Current.Windows)
                                                    {
                                                        string typeName = w.GetType().Name;
                                                        if (typeName == "LoginWindow" || typeName.Contains("Login"))
                                                        {
                                                            loginWindow = w;
                                                            break;
                                                        }
                                                    }

                                                    Type selectorType = null;
                                                    if (isIwbMode)
                                                        selectorType = Type.GetType("Cvte.EasiNote.UI.LoginIdentifySelection.IdentitySelector.IwbUserIdentitySelector, EasiNote.UI");
                                                    else
                                                        selectorType = Type.GetType("Cvte.EasiNote.UI.LoginIdentifySelection.IdentitySelector.PcUserIdentitySelector, EasiNote.UI");

                                                    if (selectorType != null)
                                                    {
                                                        var selector = Activator.CreateInstance(selectorType, new object[] { loginWindow });
                                                        var initMethod = selectorType.GetMethod("InitializeSelector");
                                                        initMethod?.Invoke(selector, null);
                                                    }

                                                    var provider = AccountLoginFactory.CloudLoginProvider;
                                                    var isAuthProperty = provider.GetType().GetProperty("IsAuth",
                                                        BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                                                    if (isAuthProperty != null && !(bool)isAuthProperty.GetValue(provider))
                                                    {
                                                        isAuthProperty.SetValue(provider, true);
                                                    }

                                                    if (targetWindow != null)
                                                    {
                                                        targetWindow.Show();
                                                        targetWindow.Topmost = true;
                                                        targetWindow.Topmost = false;
                                                        targetWindow.Activate();
                                                    }

                                                    var notifyProviderField = provider.GetType().GetField("NotifyProvider",
                                                        BindingFlags.NonPublic | BindingFlags.Instance);
                                                    if (notifyProviderField != null)
                                                    {
                                                        var internalNotifyProvider = notifyProviderField.GetValue(provider);
                                                        if (internalNotifyProvider != null)
                                                        {
                                                            var raiseMethod = internalNotifyProvider.GetType().GetMethod("RaiseUserLogined");
                                                            raiseMethod?.Invoke(internalNotifyProvider, null);
                                                        }
                                                    }
                                                }
                                            }
                                            catch { }
                                        });
                                    }
                                }
                            }
                        }
                        catch
                        {
                            await Task.Delay(500);
                        }
                    }
                    await Task.Delay(500);
                }
            });
        }

        private static async Task StartLoginInfoPipe()
        {
            while (true)
            {
                try
                {
                    using (var pipe = new NamedPipeServerStream("SeewoLoginInfoPipe", PipeDirection.Out, 1))
                    {
                        pipe.WaitForConnection();

                        var info = await GetCurrentLoginInfoAsync();
                        string json = JsonConvert.SerializeObject(info);

                        using (var writer = new StreamWriter(pipe))
                        {
                            await writer.WriteLineAsync(json);
                            await writer.FlushAsync();
                        }
                    }
                }
                catch { }
                await Task.Delay(500);
            }
        }

        public static async Task<LoginData> GetCurrentLoginInfoAsync()
        {
            var result = new LoginData
            {
                statusCode = 0,
                message = "未登录"
            };

            try
            {
                var fetchResponse = await AccountDatumFactory.AccountInfoHandler.FetchUserInfoAsync();
                if (fetchResponse == null || !fetchResponse.Success)
                    return result;

                var accountInfo = AccountServices.AccountInfo;

                string nickName = GetProp(accountInfo, "Nickname") ?? "";
                string userId = GetProp(accountInfo, "UserId")
                    ?? GetProp(accountInfo, "Uid")
                    ?? GetProp(accountInfo, "UserResourceId")
                    ?? "";
                string phone = GetProp(accountInfo, "Phone")
                    ?? GetProp(accountInfo, "PhoneNumber")
                    ?? "";
                string userName = GetProp(accountInfo, "UserName")
                    ?? GetProp(accountInfo, "Username")
                    ?? phone;

                string token = TokenFactory.AuthTokenProvider.CurrentToken;

                result.statusCode = 202;
                result.token = token;
                result.userId = userId;
                result.userName = userName;
                result.nickName = nickName;
                result.phone = phone;
                result.result = "https://e.seewo.com";
                result.message = "已登录";
            }
            catch
            {
                result.statusCode = -1;
                result.message = "获取失败";
            }

            return result;
        }

        public static LoginData GetCurrentLoginInfo()
        {
            return GetCurrentLoginInfoAsync().GetAwaiter().GetResult();
        }

        private static string GetProp(object obj, string name)
        {
            var prop = obj.GetType().GetProperty(name, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
            return prop?.GetValue(obj)?.ToString();
        }
    }
}