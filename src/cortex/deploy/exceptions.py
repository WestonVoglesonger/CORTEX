"""
Deployment exceptions.

Custom exceptions for device deployment failures with actionable error messages.
"""


class DeploymentError(Exception):
    """
    Raised when deployment fails at any step.

    Examples:
        - SSH connection failed
        - Build failed on device
        - Adapter failed to start
        - Validation failed
    """
    pass


class CleanupError(Exception):
    """
    Raised when cleanup fails (rare, since cleanup should not raise).

    Note: cleanup() method should return CleanupResult with errors
    instead of raising this exception. This exception exists for
    catastrophic failures where returning a result is impossible.
    """
    pass
