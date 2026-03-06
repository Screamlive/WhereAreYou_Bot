"""Compatibility shim for legacy imports.

This keeps `import db_repo` stable while the implementation lives in `app.db.db_repo`.
"""

import sys

from app.db import db_repo as _impl

# Expose the implementation module object directly so runtime attribute writes
# (for example, tests overriding DB_NAME) keep working as before.
sys.modules[__name__] = _impl
