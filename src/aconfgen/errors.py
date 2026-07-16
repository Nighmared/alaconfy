"""Domain errors raised by aconfgen."""


class AconfgenError(Exception):
    """Base class for expected aconfgen failures."""


class ParseError(AconfgenError):
    """Raised when a source manpage cannot be interpreted."""

    def __init__(self, message: str, *, source: str | None = None, line: int | None = None) -> None:
        location = ""
        if source is not None:
            location += source
        if line is not None:
            location += f":{line}"
        if location:
            message = f"{location}: {message}"
        super().__init__(message)
