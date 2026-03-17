class TextMixin:
    def to_text(self) -> str:
        return str(self)


class SerializeMixin:
    def serialize(self) -> dict:
        return {"type": type(self).__name__}


class Formatter(TextMixin, SerializeMixin):
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix

    def format(self, value: str) -> str:
        return f"{self.prefix}: {value}"
