from pathlib import Path

from . import base as _base
from .base import *  # noqa: F403

Path(_base.DATABASES["default"]["NAME"]).parent.mkdir(parents=True, exist_ok=True)
