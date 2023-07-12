""" Module defining custom exceptions, designed to return user-friendly error
    messaging to the end-user.

"""
from harmony.util import HarmonyException


class HyBIGException(HarmonyException):
    """Base service exception."""
    def __init__(self, message=None):
        super().__init__(message, 'sds/harmony-browse-image-generator')


class HyBIGInvalidMessage(HarmonyException):
    """Input Harmony Message could not be used as presented."""
    def __init__(self, message=None):
        super().__init__(message, 'sds/harmony-browse-image-generator')


class HyBIGValueError(HarmonyException):
    """Input was incorrect for the routine."""
    def __init__(self, message=None):
        super().__init__(message, 'sds/harmony-browse-image-generator')
