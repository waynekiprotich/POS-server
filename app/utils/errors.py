class ApiError(Exception):
    """Error that carries a message the interface can show directly."""

    status_code = 400

    def __init__(self, message, status_code=None, field=None, details=None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.field = field
        self.details = details

    def to_dict(self):
        payload = {"error": self.message}
        if self.field:
            payload["field"] = self.field
        if self.details:
            payload["details"] = self.details
        return payload


class NotFound(ApiError):
    status_code = 404


class Conflict(ApiError):
    status_code = 409


class Forbidden(ApiError):
    status_code = 403


class Unauthorized(ApiError):
    status_code = 401
