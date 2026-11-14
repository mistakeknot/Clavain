#!/usr/bin/env python3
"""Read bb's current per-thread pool decision without exposing its bearer.

Exit codes: 0 eligible, 1 ineligible, 2 configuration error, 3 legacy
provider-wide eligibility, 4 transient timeout/transport/server failure.
"""
from http.client import HTTPException
import json
import os
import sys
from urllib.parse import urlencode, urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args):
        return None


def main() -> int:
    provider = sys.argv[1] if len(sys.argv) == 2 else "unknown"
    thread_id = os.environ.get("BB_THREAD_ID", "")
    server_url = os.environ.get("BB_SERVER_URL", "")
    try:
        if len(sys.argv) != 2:
            raise ValueError("provider required")
        url = urlsplit(server_url)
        if (url.scheme not in ("http", "https") or not url.hostname or
                url.username is not None or url.password is not None or
                url.path not in ("", "/") or url.query or url.fragment or not thread_id or
                (url.scheme == "http" and url.hostname not in ("localhost", "127.0.0.1", "::1"))):
            raise ValueError("invalid bb origin")
        route = server_url.rstrip("/") + "/api/v1/plugins/account-pool/http"
        if provider == "claude":
            token = (os.environ.get("ANTHROPIC_AUTH_TOKEN") if os.environ.get("ANTHROPIC_BASE_URL") == route
                     else os.environ.get("CODEX_POOL_AUTH_TOKEN"))
        elif provider == "codex":
            token = (os.environ.get("CODEX_POOL_AUTH_TOKEN") if os.environ.get("CODEX_POOL_AUTH_TOKEN") and os.environ.get("CODEX_OPENAI_BASE_URL") == route + "/v1"
                     else os.environ.get("ANTHROPIC_AUTH_TOKEN"))
        else:
            raise ValueError("invalid provider")
        if not token:
            raise ValueError("missing pool token")
        endpoint = route + "/availability?" + urlencode({"threadId": thread_id})
        request = Request(
            endpoint,
            headers={"x-bb-account-pool-token": token},
        )
        with build_opener(NoRedirect).open(request, timeout=5) as response:
            decision = json.load(response)
        if (isinstance(decision, dict) and set(decision) == {"claude", "codex"} and
                all(type(decision[name]) is bool for name in ("claude", "codex"))):
            return 3 if decision[provider] else 1
        availability = decision.get("availability")
        if (decision.get("threadId") != thread_id or not isinstance(availability, dict) or
                type(availability.get(provider)) is not bool):
            raise ValueError("invalid bb eligibility response")
        return 0 if availability[provider] else 1
    except HTTPError as error:
        status = 4 if 500 <= error.code < 600 else 2
    except (URLError, OSError, HTTPException):
        status = 4
    except Exception:
        status = 2
    if status == 4:
        print(f"Error: transient bb account-pool eligibility probe failure for {provider}", file=sys.stderr)
    else:
        print(f"Error: cannot establish current bb account-pool eligibility for {provider}", file=sys.stderr)
    return status


if __name__ == "__main__":
    sys.exit(main())
