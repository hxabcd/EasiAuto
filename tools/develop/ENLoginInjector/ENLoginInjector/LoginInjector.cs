using Cvte.EasiNote;
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Windows;
using System.Windows.Media;
using System.Windows.Threading;

namespace ENLoginInjector
{
	public static class LoginWindowLauncher
	{
		/// <summary>
		/// 唤起登录窗口（外部已经保证不需要校验是否已打开）
		/// 如需唤起用户中心等动作，调用 ENCommands.OpenUserCenter 并等待短暂同步。
		/// </summary>
		public static int Trigger(string settings)
		{
			LoginUtil.Log($"[{DateTime.Now}] Launcher: 开始唤起流程...\n");
			Application.Current.Dispatcher.Invoke(() =>
			{
				try
				{
					// 仅负责唤起/触发打开逻辑并做同步等待，不负责后续的登录调用
					if (ENCommands.OpenUserCenter.CanExecute(null))
					{
						ENCommands.OpenUserCenter.Execute(null);
						LoginUtil.Log("Launcher: 已执行唤起操作");
					}
					else
					{
						LoginUtil.Log("Launcher: ENCommands.OpenUserCenter 不可执行或不存在权限");
					}
				}
				catch (Exception ex)
				{
					LoginUtil.Log($"Launcher 致命错误: {ex}");
				}
			});
			return 0;
		}
	}

	public static class LoginPerformer
	{
		/// <summary>
		/// 执行登录逻辑（不负责唤起窗口，外部保证窗口已唤起）
		/// settings 格式与原版一致（例如 "user:password"），内部会切分并调用 Login 方法。
		/// </summary>
		public static int Trigger(string settings)
		{
			LoginUtil.Log($"[{DateTime.Now}] Performer: 开始执行登录流程...\n");
			Application.Current.Dispatcher.Invoke(() =>
			{
				try
				{
					Execute(settings);
				}
				catch (Exception ex)
				{
					LoginUtil.Log($"Performer 致命错误: {ex}");
				}
			});
			return 0;
		}

		private static void Execute(string args)
		{
			var parts = args.Split(':');

			// 实时获取窗口列表并寻找 IWBLoginWindow（外部已保证窗口会存在，但仍做一次查找）
			var loginWin = Application.Current.Windows.Cast<Window>().FirstOrDefault(w => w.GetType().Name == "IWBLoginWindow");
			if (loginWin == null)
			{
				LoginUtil.Log("Performer: 未找到 IWBLoginWindow（外部未正确唤起）");
				return;
			}
			LoginUtil.Log("Performer: 已捕获 IWBLoginWindow");

			object target = LoginUtil.FindControlWithLoginMethod(loginWin);
			if (target == null)
			{
				LoginUtil.Log("Performer: 视觉树遍历完成，未发现匹配 Login(a, b, c) 的控件");
				return;
			}

			LoginUtil.Log($"Performer: 定位成功: {target.GetType().FullName}");

			// 自动勾选协议 (使用反射处理 internal)
			try
			{
				var field = target.GetType().GetField("AgreementCheckBox", BindingFlags.NonPublic | BindingFlags.Instance);
				var checkBox = field?.GetValue(target) as System.Windows.Controls.Primitives.ToggleButton;
				if (checkBox != null) checkBox.IsChecked = true;
			}
			catch (Exception ex)
			{
				LoginUtil.Log($"Performer: 勾选协议时发生异常: {ex.Message}");
			}

			// 精确获取 Login 方法：3个参数
			var methods = target.GetType().GetMethods(BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.Instance);
			var loginMethod = methods.FirstOrDefault(m => m.Name == "Login" && m.GetParameters().Length == 3);

			if (loginMethod != null)
			{
				LoginUtil.Log("Performer: 正在执行 Invoke...");
				// 第三个参数传 null（与原版一致）
				loginMethod.Invoke(target, new object[] { parts[0], parts.Length > 1 ? parts[1] : string.Empty, null! });
				LoginUtil.Log("Performer: 登录指令已发送");
			}
			else
			{
				LoginUtil.Log("Performer: 无法确定 Login 方法的精确签名");
			}
		}
	}

	internal static class LoginUtil
	{
		//internal static readonly string LogPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Desktop), "easi_inject.log");

		internal static void DoEvents(int milliseconds)
		{
			DateTime end = DateTime.Now.AddMilliseconds(milliseconds);
			while (DateTime.Now < end)
			{
				DispatcherFrame frame = new DispatcherFrame();
				Dispatcher.CurrentDispatcher.BeginInvoke(DispatcherPriority.Background,
					new DispatcherOperationCallback(obj =>
					{
						((DispatcherFrame)obj).Continue = false;
						return null;
					}), frame);
				Dispatcher.PushFrame(frame);

				System.Threading.Thread.Sleep(10);
			}
		}

		internal static object FindControlWithLoginMethod(DependencyObject parent)
		{
			if (parent == null) return null;

			var methods = parent.GetType().GetMethods(BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.Instance);
			var targetMethod = methods.FirstOrDefault(m => m.Name == "Login" && m.GetParameters().Length == 3);
			if (targetMethod != null) return parent;

			for (int i = 0; i < VisualTreeHelper.GetChildrenCount(parent); i++)
			{
				var child = VisualTreeHelper.GetChild(parent, i);
				var result = FindControlWithLoginMethod(child);
				if (result != null) return result;
			}
			return null;
		}

		//internal static void Log(string t) => File.AppendAllText(LogPath, $"[{DateTime.Now}] {t}\n");
		//不创建日志文件，通过stdout返回输出
		internal static void Log(string t) => Console.WriteLine($"[{DateTime.Now}] {t}\n");
	}
}
