"""各业务模块共用的 API 响应格式。"""


def ok(data=None, message="ok"):
    return {"code": 0, "message": message, "data": data}
