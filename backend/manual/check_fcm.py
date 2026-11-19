"""Checks the real Firebase setup — no phone needed.

1. Reads FIREBASE_CREDENTIALS_FILE (from .env) and gets a real access token
   from Google (proves the service-account key is valid).
2. Asks FCM to VALIDATE (not deliver) a message to a made-up device token.
   FCM answering "invalid registration token" proves the key, the project
   and our message format are all accepted. Nothing is sent anywhere.

Optional, once the Android app exists and gives you a real device token:
   --token <device token>          validate a message to that real device
   --token <device token> --send   actually deliver a test notification

Run from the backend folder:
    .venv\\Scripts\\python manual\\check_fcm.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import fcm  # noqa: E402
from app.core.config import settings  # noqa: E402


async def main() -> None:
    if not fcm.is_configured():
        raise SystemExit("FIREBASE_CREDENTIALS_FILE is not set in backend/.env")
    try:
        creds = fcm._load_credentials()
    except fcm.FcmConfigError as exc:
        raise SystemExit(f"FAIL: {exc}")
    print(f"Key file: OK (project '{creds.project_id}', account {creds.client_email.split('@')[0]}@...)")

    token = sys.argv[sys.argv.index("--token") + 1] if "--token" in sys.argv else "not-a-real-device-token-" + "x" * 40
    real_send = "--send" in sys.argv and "--token" in sys.argv
    try:
        result = await fcm.send(token, "Test from AI Task Manager", "If you see this, push works.",
                                {"type": "test"}, validate_only=not real_send)
    except fcm.FcmConfigError as exc:
        raise SystemExit(f"FAIL: Google rejected the credentials: {exc}")
    print("Access token from Google: OK")

    if "--token" not in sys.argv:
        if result.outcome == "invalid_token":
            print("FCM: accepted our credentials, project and message format "
                  "(it rejected the made-up device token, as expected).")
            print("RESULT: Firebase is set up correctly. Push will work once the app registers a device.")
        else:
            print(f"UNEXPECTED: FCM answered '{result.outcome}': {result.detail}")
            print("Most likely: the Cloud Messaging API isn't enabled for this project yet "
                  "(see the setup steps), or the key is from a different project.")
        return
    action = "delivered to" if real_send else "validated for"
    print(f"FCM: message {action} the device -> {result.outcome} {result.detail}")


if __name__ == "__main__":
    print(f"(settings: FIREBASE_CREDENTIALS_FILE={Path(settings.firebase_credentials_file).name or '-'})")
    asyncio.run(main())
