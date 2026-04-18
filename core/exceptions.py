class AutoFixError(Exception):
    pass


class IssueVagueError(AutoFixError):
    pass


class NotFixableError(AutoFixError):
    pass


class AdapterError(AutoFixError):
    pass


class AdapterNotConfiguredError(AutoFixError):
    pass
