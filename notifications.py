# Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)

"""Status/error messaging helpers.

Desktop toast / Notification Center banners were removed intentionally —
status is shown in the control window instead.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("AmpliFi Teleport for Desktop")


def show_toast(title, message, icon_path=None):
    """No-op. Kept so existing call sites stay valid without showing banners."""
    logger.debug("Toast suppressed: %s — %s", title, message)
