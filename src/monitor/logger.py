import sys
from pathlib import Path

from loguru import logger


def configure_logger(log_level: str = "INFO",
                     log_file: str = "./data/logs/jobsdb_{time}.log",
                     log_rotation: str = "1 week",
                     log_retention: str = "1 month") -> None:
    """配置 Loguru 日志系统"""

    # 移除默认的 stderr handler
    logger.remove()

    # 添加终端输出（带颜色和格式）
    logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
               "<level>{message}</level>",
        colorize=True,
    )

    # 添加文件输出（结构化 JSON）
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_file,
        level="DEBUG",  # 文件记录更详细
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation=log_rotation,
        retention=log_retention,
        encoding="utf-8",
        backtrace=True,
        diagnose=True,
    )

    # 单独的应用记录日志文件（JSON 格式）
    app_log_path = log_path.parent / "applications.json"
    logger.add(
        str(app_log_path),
        level="INFO",
        format="{extra[json]}",
        rotation="1 week",
        retention="1 month",
        encoding="utf-8",
        filter=lambda record: "application" in record.get("extra", {}),
        serialize=True,  # JSON 格式
    )

    logger.info("Logger configured successfully")


def get_logger():
    """获取 logger 实例"""
    return logger
