from src.utils.logger import get_logger


def test_get_logger_returns_logger():
    """Ensure get_logger returns a logger instance with the expected name."""
    name = __name__
    logger = get_logger(name)
    assert logger.name == name 