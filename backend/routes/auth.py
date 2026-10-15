import os
import requests
from datetime import timedelta
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from models.db import db, Admin, Driver, OTP, Notification, utcnow
from routes.auth_utils import hash_password, check_password, generate_token, generate_otp
from errors import ConflictError
from validators import validate_email, validate_phone, validate_username, validate_password
from notifications import notify
from extensions import limiter

auth_bp = Blueprint("auth", __name__)

# Section 4 (brute-force protection): PER-ACCOUNT lockout, layered on top of
# the IP-based rate limit on this endpoint. IP rate limiting alone doesn't
# stop a distributed attempt (many IPs, one target account) - this does,
# because it's keyed by the account, not the caller's address.
LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 15


def _lockout_response(account):
    """Returns a (response, status) tuple if `account` is currently locked, else None."""
    if account.locked_until and account.locked_until > utcnow():
        remaining_min = max(1, int((account.locked_until - utcnow()).total_seconds() // 60) + 1)
        return jsonify({
            "error": f"Too many failed login attempts. Try again in about {remaining_min} minute(s).",
            "code": "ACCOUNT_LOCKED",
        }), 423
    return None


def _register_failed_attempt(account):
    account.failed_login_attempts = (account.failed_login_attempts or 0) + 1
    if account.failed_login_attempts >= LOCKOUT_THRESHOLD:
        account.locked_until = utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
    db.session.commit()


def _register_successful_login(account):
    if account.failed_login_attempts or account.locked_until:
        account.failed_login_attempts = 0
        account.locked_until = None
        db.session.commit()

# ---------------------------------------------------------- OTP tuning
# Email-only: no SMS provider is wired up in this build (no SMS API key was
# supplied), so phone-based OTP delivery is not offered - see README.
OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_REQUEST_COOLDOWN_SECONDS = 60


def try_send_email(to_address, subject, body):
    """Send a transactional email through Brevo. Returns True only on success."""
    api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("BREVO_SENDER_EMAIL")
    sender_name = os.getenv("BREVO_SENDER_NAME", "CarbonTrack Logistics")

    if not api_key or not sender_email:
        current_app.logger.warning(
            "Brevo is not configured; transactional email was not sent."
        )
        return False

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": to_address}],
        "subject": subject,
        "textContent": body,
    }

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        if response.status_code not in (200, 201, 202):
            current_app.logger.error(
                "Brevo rejected transactional email (HTTP %s).",
                response.status_code,
            )
            return False
        return True
    except requests.RequestException:
        current_app.logger.exception("Brevo transactional email request failed.")
        return False

