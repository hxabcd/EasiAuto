import time

from loguru import logger

from EasiAuto.common.config import config

from .base import BaseAutomator


class UIAAutomator(BaseAutomator):
    """通过 UI Automation 自动定位组件位置来登录"""

    def login(self):
        from pywinauto import Application, Desktop

        logger.info("尝试自动登录")
        self.task_update.emit("正在自动登录")

        # 连接至希沃白板
        self.check()
        logger.info("连接 UI Automation 后端至希沃白板")
        self.progress_update.emit("连接后端至希沃白板")

        app = Application(backend="uia").connect(handle=self.hwnd)
        dlg = app.window(title="希沃白板")
        dlg.set_focus()  # 设置焦点为希沃白板窗口

        # 如果启动进入白板 (iwb)
        is_iwb = not config.Login.Directly
        if is_iwb:
            # 先进入登录界面
            self.check()
            logger.info("点击进入登录界面")
            self.progress_update.emit("进入登录界面")

            iwb_login_button = dlg.child_window(auto_id="ProfileButton", control_type="Button")
            iwb_login_button.click()
            time.sleep(config.Login.Timeout.EnterLoginUI)

            # 切换操作窗口为弹出的 IWBLogin
            self.check()
            logger.info("切换到登录界面")
            self.progress_update.emit("切换后端至登录界面")

            dlg = Desktop(backend="uia").window(auto_id="IWBLogin")

        # 切换至账号登录
        self.check()
        logger.info("定位并点击账号登录按钮")
        self.progress_update.emit("切换至账号登录页")

        account_login_button = dlg.child_window(
            auto_id="AccountRadioButton" if is_iwb else "AccountLoginRadioButton", control_type="RadioButton"
        )
        account_login_button.click()
        time.sleep(config.Login.Timeout.SwitchTab)

        # 定位登录控件
        self.check()
        logger.info("定位登录控件")
        account_login_page = dlg.child_window(
            auto_id="IwbAccountControl" if is_iwb else "PasswordLoginControl", control_type="Custom"
        )

        # 输入账号
        self.check()
        logger.info("定位输入框并填入账号")
        self.progress_update.emit("输入账号")
        logger.debug(f"账号：{self.account}")

        account_input = account_login_page.ComboBox.Edit
        account_input.set_edit_text(self.account)

        # 输入密码
        self.check()
        logger.info("定位输入框并填入密码")
        self.progress_update.emit("输入密码")
        logger.debug(f"密码：{self.safe_for_log_password}")
        password_input = account_login_page.child_window(auto_id="PasswordBox", control_type="Edit")
        password_input.set_edit_text(self.password)

        # 勾选同意用户协议
        self.check()
        logger.info("定位用户协议复选框并勾选")
        self.progress_update.emit("勾选同意用户协议")

        agreement_button = account_login_page.child_window(auto_id="AgreementCheckBox", control_type="CheckBox")
        if not agreement_button.get_toggle_state():
            agreement_button.toggle()

        # 登录
        self.check()
        logger.info("点击登录按钮")
        self.progress_update.emit("点击登录")

        login_button = account_login_page.child_window(auto_id="LoginButton", control_type="Button")
        login_button.click()

        self.progress_update.emit("登录完成")
        self.task_update.emit("完成")
