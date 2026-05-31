from __future__ import annotations

import uvicorn

from dynamicrunner.api.app import create_app
from dynamicrunner.config import get_settings


def main() -> None:
    settings = get_settings()
    app = create_app(settings=settings)
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
