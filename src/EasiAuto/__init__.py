"""EasiAuto - 一款自动登录希沃白板的小工具"""

__version__ = "1.1.1"
__author__ = "hxabcd"

import sys

from .consts import IS_DEV, VENDOR_PATH

if IS_DEV:
    from loguru import logger

    logger.debug(rf"""
  _____          _    _         _        
 | ____|__ _ ___(_)  / \  _   _| |_ ___  
 |  _| / _` / __| | / _ \| | | | __/ _ \ 
 | |__| (_| \__ \ |/ ___ \ |_| | || (_) |
 |_____\__,_|___/_/_/   \_\__,_|\__\___/ 
EasiAuto v{__version__}
You are running in development environment.
Author: {__author__}
Github Repo: https://github.com/hxabcd/EasiAuto""")

    if str(VENDOR_PATH) not in sys.path:
        sys.path.insert(0, str(VENDOR_PATH))
