from . import risks, settings, start

__all__ = [
    "start",
    "settings",
    "risks",
    "get_routers",
]


def get_routers() -> tuple:
    return (
        start.router,
        settings.router,
        risks.router,
    )
