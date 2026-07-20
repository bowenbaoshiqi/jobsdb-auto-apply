class JobsDBError(Exception):
    """JobsDB 相关错误基类"""
    pass


class LoginError(JobsDBError):
    """登录失败"""
    pass


class SessionExpiredError(JobsDBError):
    """会话已过期"""
    pass


class CaptchaDetectedError(JobsDBError):
    """检测到验证码"""
    pass


class ApplyError(JobsDBError):
    """投递失败"""
    pass


class JobNotFoundError(JobsDBError):
    """职位未找到"""
    pass


class RateLimitError(JobsDBError):
    """频率限制"""
    pass


class DetectionSuspectedError(JobsDBError):
    """怀疑被检测"""
    pass


class NavigationError(JobsDBError):
    """页面导航失败"""
    pass


class ElementNotFoundError(JobsDBError):
    """元素未找到"""
    pass
