"""Deprecated module for holiday_import_service.

The implementation has moved to:

    app.managers.data_manager.integrations.holiday_import_service

Update all imports to use the new path. This module intentionally
raises an ImportError to surface any remaining usages.
"""

raise ImportError(
    "holiday_import_service has moved to "
    "app.managers.data_manager.integrations.holiday_import_service. "
    "Update your imports to the new location."
)
