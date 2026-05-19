from __future__ import annotations


class EditError(Exception):
    def __init__(
        self,
        error_type: str,
        reason: str,
        *,
        start: str | None = None,
        end: str | None = None,
    ) -> None:
        super().__init__(reason)
        self.error_type = error_type
        self.reason = reason
        self.start = start
        self.end = end

    def to_dict(self) -> dict[str, str]:
        payload = {
            "type": self.error_type,
            "reason": self.reason,
        }
        if self.start is not None:
            payload["start"] = self.start
        if self.end is not None:
            payload["end"] = self.end
        return payload
