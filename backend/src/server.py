import os

from dotenv import load_dotenv

from src.app import create_app


# =========================================================
# LOAD ENVIRONMENT VARIABLES
# =========================================================

load_dotenv()


# =========================================================
# CREATE FLASK APPLICATION
# =========================================================

app = create_app()


# =========================================================
# START DEVELOPMENT SERVER
# =========================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,

        # Keep debug mode enabled during development.
        debug=True,

        # Important:
        #
        # Flask's automatic reloader creates another
        # Python process. That would start the background
        # scheduler twice.
        #
        # Therefore we disable only the reloader.
        use_reloader=False
    )
