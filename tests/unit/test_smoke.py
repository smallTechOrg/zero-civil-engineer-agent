def test_package_importable():
    from config.settings import get_settings  # noqa: F401
    from api._common import ok              # noqa: F401
    from db.models import Base              # noqa: F401
