"""只读资源路径解析。"""

from EasiAuto.consts import EA_RESDIR


def get_resource(filename: str):
    """获取资源路径"""
    return str(EA_RESDIR / filename)
