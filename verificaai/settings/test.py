from .base import *  # noqa: F403
from .base import ALLOWED_HOSTS as BASE_ALLOWED_HOSTS
from .base import DATABASES as BASE_DATABASES

ALLOWED_HOSTS = [*BASE_ALLOWED_HOSTS, "testserver"]
DATABASES = {"default": {**BASE_DATABASES["default"], "NAME": ":memory:"}}
