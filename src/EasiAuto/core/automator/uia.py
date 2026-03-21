import time

from EasiAuto.common.config import config

from .base import BaseAutomator


class UIAAutomator(BaseAutomator):
    """通过 UI Automation 自动定位组件位置来登录"""

    def login(self):
        from pywinauto import Application, Desktop

        # 连接至希沃白板
        self.check_interruption()
        self.update_progress("连接后端至希沃白板")

        app = Application(backend="uia").connect(handle=self.easinote_hwnd)
        dlg = app.window(title="希沃白板")
        dlg.set_focus()  # 设置焦点为希沃白板窗口

        # 进入登录界面
        if config.Login.IsIwb:
            self.check_interruption()
            self.update_progress("进入登录界面")

            iwb_login_button = dlg.child_window(auto_id="ProfileButton", control_type="Button")
            iwb_login_button.click()
            time.sleep(config.Login.Timeout.EnterLoginUI)

            # 切换操作窗口为弹出的 IWBLogin
            self.check_interruption()
            self.update_progress("切换后端至登录界面")

            dlg = Desktop(backend="uia").window(auto_id="IWBLogin")

        # 切换至账号登录页
        self.check_interruption()
        self.update_progress("切换至账号登录页")

        account_login_button = dlg.child_window(
            auto_id="AccountRadioButton" if config.Login.IsIwb else "AccountLoginRadioButton",
            control_type="RadioButton",
        )
        account_login_button.click()
        time.sleep(config.Login.Timeout.SwitchTab)

        # 定位登录控件
        self.check_interruption()
        self.update_progress("定位登录控件")

        account_login_page = dlg.child_window(
            auto_id="IwbAccountControl" if config.Login.IsIwb else "PasswordLoginControl", control_type="Custom"
        )

        # 输入账号
        self.check_interruption()
        self.update_progress("输入账号")

        account_input = account_login_page.ComboBox.Edit
        account_input.set_edit_text(self.account)

        # 输入密码
        self.check_interruption()
        self.update_progress("输入密码")

        password_input = account_login_page.child_window(auto_id="PasswordBox", control_type="Edit")
        password_input.set_edit_text(self.password)

        # 勾选同意用户协议
        self.check_interruption()
        self.update_progress("勾选同意用户协议")

        agreement_button = account_login_page.child_window(auto_id="AgreementCheckBox", control_type="CheckBox")
        if not agreement_button.get_toggle_state():
            agreement_button.toggle()

        # 点击登录按钮
        self.check_interruption()
        self.update_progress("点击登录按钮")

        login_button = account_login_page.child_window(auto_id="LoginButton", control_type="Button")
        login_button.click()
