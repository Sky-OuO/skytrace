"""OAuth / 微信登录预留。

Authlib 已经装进依赖，供以后注册外部提供方。第 1–2 天不创建任何 OAuth 客户端，
也不暴露登录跳转。
"""

import authlib


def reserved_oauth_note() -> str:
    return f"Authlib {authlib.__version__} 已安装。当前不注册 OAuth 或微信登录。"
