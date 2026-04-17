class AutoFixError(Exception):
    pass


class IssueVagueError(AutoFixError):
    pass


class NotFixableError(AutoFixError):
    pass


class DuplicatePRError(AutoFixError):
    pass


class PRTooLargeError(AutoFixError):
    pass


class CrossRepoError(AutoFixError):
    pass


class FixGenerationError(AutoFixError):
    pass


class SecurityScanError(AutoFixError):
    pass


class AdapterError(AutoFixError):
    pass


class AdapterNotConfiguredError(AutoFixError):
    pass
