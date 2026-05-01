"""Verify Google Service Account credentials load + print client_email to share sheets with."""
import sys

try:
    from app.services.sheets_service import service_account_email
except Exception as e:
    print(f"FAILED to import: {e}")
    sys.exit(1)


def main() -> int:
    try:
        email = service_account_email()
    except Exception as e:
        print(f"FAILED ({type(e).__name__}): {e}")
        print("\nFix: set GOOGLE_SERVICE_ACCOUNT_JSON in backend/.env to either:")
        print("  - the absolute path of your service-account .json file (recommended), or")
        print("  - the inline JSON wrapped in single quotes.")
        return 1
    print(f"OK -- service account loaded.\nShare your Google Sheets with: {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
