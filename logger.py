import logging


class IgnoreFilter(logging.Filter):
    """
    Customized Log filter that ignores a given message text.
    """

    def __init__(self, ignored_message: str, name: str = "") -> None:
        super().__init__(name)
        self.ignored_message = ignored_message
        self.enabled = True

    def filter(self, record: logging.LogRecord) -> bool:
        if not self.enabled:
            return True
        return self.ignored_message not in record.getMessage()

    def set_ignored_message(self, message: str) -> None:
        """Set a new message pattern to ignore."""
        self.ignored_message = message

    def toggle_filter(self, enable: bool) -> None:
        """Enable or disable the filter."""
        self.enabled = enable

    def get_ignored_message(self) -> str:
        """Get the current ignored message pattern."""
        return self.ignored_message


def set_logger(name: str) -> logging.Logger:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("near_lake_framework").setLevel(logging.INFO)
    missing_shard_filter = IgnoreFilter("doesn't exist")
    logging.getLogger().addFilter(missing_shard_filter)
    return logging.getLogger(name)
