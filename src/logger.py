from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")
logger.add("logs/run_{time:YYYY-MM-DD}.log", level="DEBUG", rotation="10 MB")
