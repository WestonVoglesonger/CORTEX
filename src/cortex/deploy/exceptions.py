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
