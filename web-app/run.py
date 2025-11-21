"""Entry point for running the pitch detector web app."""

# pylint: disable=import-error

import os
from __init__ import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT"))
    app.run(host="0.0.0.0", port=port)
