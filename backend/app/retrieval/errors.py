class DocumentError(Exception):
    """Document problem with a safe, public-facing message and HTTP status."""

    def __init__(self, kind: str, public_message: str, status_code: int = 422):
        super().__init__(f"{kind}: {public_message}")
        self.kind = kind
        self.public_message = public_message
        self.status_code = status_code
