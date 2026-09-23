"""
Quick standalone check: sends one text query straight through the real
Houndify SDK (vendor/houndify/houndify.py) using the credentials in .env,
and prints the raw CommandResponse JSON it gets back.

Usage:
    python3 check_houndify_sdk.py "How much does the bike weigh"
    python3 check_houndify_sdk.py                     # uses a default query
    python3 check_houndify_sdk.py "How much does the bike weigh" --request-info vendor/houndify/requestInfo_X47.json
"""
import sys
import json
import argparse

sys.path.insert(0, "vendor/houndify")
import houndify  # noqa: E402  (must come after sys.path insert)

from config.settings import settings  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", default="What are your business hours?")
    parser.add_argument(
        "--request-info",
        help="Path to a requestInfo JSON file (e.g. vendor/houndify/requestInfo_X47.json). "
             "If not given, falls back to a bare Latitude/Longitude placeholder with no "
             "DeviceInfo.DeviceModel and no matching UserID.",
    )
    args = parser.parse_args()

    if not settings.houndify_client_id or not settings.houndify_client_key:
        raise SystemExit(
            "HOUNDIFY_CLIENT_ID / HOUNDIFY_CLIENT_KEY are not set in .env -- "
            "check your .env file."
        )

    if args.request_info:
        with open(args.request_info) as f:
            requestInfo = json.load(f)
        print(f"[check_houndify_sdk] Loaded requestInfo from {args.request_info} "
              f"(DeviceInfo.DeviceModel={(requestInfo.get('DeviceInfo') or {}).get('DeviceModel')!r}, "
              f"UserID={requestInfo.get('UserID')!r})\n")
    else:
        requestInfo = {
            # Placeholder location -- no DeviceInfo.DeviceModel and no real UserID.
            # Pass --request-info to use a real device-context file instead.
            "Latitude": 12.9716,
            "Longitude": 77.5946,
        }
        print("[check_houndify_sdk] No --request-info given -- using bare placeholder "
              "(no DeviceInfo.DeviceModel, no real UserID)\n")

    user_id = requestInfo.get("UserID") or "test_user"

    client = houndify.TextHoundClient(
        settings.houndify_client_id,
        settings.houndify_client_key,
        user_id,
        requestInfo,
    )

    print(f"Query: {args.query!r}\n")
    try:
        response = client.query(args.query)
    except Exception as e:
        print(f"ERROR calling Houndify: {type(e).__name__}: {e}")
        if "CERTIFICATE" in str(e).upper() or "SSL" in str(e).upper():
            print(
                "\nThis looks like the SSL certificate error mentioned in your "
                "email -- tell me and I'll apply the same unverified-SSL-context "
                "fix to vendor/houndify/houndify.py."
            )
        raise SystemExit(1)

    print(json.dumps(response, indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
