"""Public domain errors; never include provider or database exception text."""


class MemoryError(Exception):
    def __init__(self, code, message, status_code=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code


class Unauthorized(MemoryError):
    def __init__(self):
        super().__init__('unauthorized', 'Authentication required', 401)


class Forbidden(MemoryError):
    def __init__(self, message='Operation not permitted'):
        super().__init__('forbidden', message, 403)


class NotFound(MemoryError):
    def __init__(self):
        super().__init__('not_found', 'Resource not found', 404)


class Conflict(MemoryError):
    def __init__(self, message='Conflicting event or version'):
        super().__init__('conflict', message, 409)


DomainError = MemoryError
