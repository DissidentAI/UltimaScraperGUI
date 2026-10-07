"""Runtime fixes for ultima-scraper-api 1.1.4, which no longer matches OnlyFans.

Imported for its side effects by ultima_scraper.ultima_scraper (CLI and GUI).
"""

from __future__ import annotations

from typing import Any

from ultima_scraper_api.apis.onlyfans.classes import auth_model, extras

_applied = False


def apply() -> None:
    global _applied
    if _applied:
        return
    _applied = True

    original_process_auth = extras.OnlyFansAuthenticator.process_auth

    async def process_auth(self: extras.OnlyFansAuthenticator):
        # /users/me now answers 200 {"isAuth": false} for an invalid or expired
        # session instead of an error, which the library took for a success.
        await original_process_auth(self)
        raw: Any = self.__raw__
        if isinstance(raw, dict) and raw.get("isAuth") is False:
            self.auth_details.active = False
            # "token" in the message stops the library's 10 retries.
            self.errors.append(
                extras.ErrorDetails(
                    {
                        "code": 401,
                        "message": "session token rejected by OnlyFans (isAuth=false)",
                    }
                )
            )
        return self

    extras.OnlyFansAuthenticator.process_auth = process_auth  # type: ignore[assignment]

    original_get_login_issues = auth_model.AuthModel.get_login_issues

    async def get_login_issues(self: auth_model.AuthModel) -> dict[str, Any]:
        # The login issues endpoint was removed (404) and login() then crashed
        # with KeyError: 'data'.
        response = await original_get_login_issues(self)
        if isinstance(response, dict) and "data" in response:
            return response
        return {"data": []}

    auth_model.AuthModel.get_login_issues = get_login_issues  # type: ignore[assignment]


apply()
