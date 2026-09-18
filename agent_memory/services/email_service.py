"""Resend transactional email service for signup verification and password reset."""

import logging
from typing import Optional, Dict, Any
import httpx
from ..config import settings

logger = logging.getLogger("memorybrain.email")


class EmailService:
    """Manages transactional emails via Resend REST API."""

    RESEND_API_URL = "https://api.resend.com/emails"

    @classmethod
    def _send_resend(cls, to_email: str, subject: str, html_body: str) -> bool:
        """Internal helper to dispatch email via Resend."""
        api_key = settings.resend_api_key.strip() if settings.resend_api_key else ""
        from_email = settings.resend_from_email.strip() if settings.resend_from_email else "MemoryBrain <onboarding@resend.dev>"

        if not api_key:
            logger.info(
                f"[RESEND SIMULATION] Email to {to_email} | Subject: {subject}"
            )
            print(f"\n================ [RESEND DEV NOTIFICATION] ================")
            print(f"To: {to_email}")
            print(f"Subject: {subject}")
            print(f"Content Summary: (API Key not set - simulated delivery)")
            print(f"===========================================================\n")
            return True

        try:
            payload = {
                "from": from_email,
                "to": [to_email],
                "subject": subject,
                "html": html_body
            }
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(cls.RESEND_API_URL, json=payload, headers=headers)
                if resp.status_code in (200, 201):
                    logger.info(f"Successfully sent email to {to_email} via Resend. ID: {resp.json().get('id')}")
                    return True
                else:
                    logger.error(f"Resend error ({resp.status_code}): {resp.text}")
                    return False
        except Exception as exc:
            logger.error(f"Failed to dispatch email to {to_email}: {exc}")
            return False

    @classmethod
    def send_signup_verification(cls, to_email: str, name: str, code: str) -> bool:
        """Sends 6-digit confirmation code on user signup."""
        subject = f"Verify your MemoryBrain account — Code: {code}"
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0F172A; color: #F8FAFC; margin: 0; padding: 32px 16px; }}
            .card {{ max-width: 520px; margin: 0 auto; background: #1E293B; border: 1px solid #334155; border-radius: 12px; padding: 32px; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }}
            .brand {{ font-size: 20px; font-weight: 700; color: #8CCFD8; letter-spacing: -0.02em; margin-bottom: 24px; }}
            h2 {{ font-size: 22px; color: #F8FAFC; margin-top: 0; }}
            p {{ font-size: 15px; line-height: 1.6; color: #94A3B8; }}
            .code-box {{ background: #0B0F17; border: 1px solid #38BDF8; border-radius: 8px; padding: 18px; text-align: center; margin: 28px 0; }}
            .code {{ font-family: 'JetBrains Mono', monospace, Courier; font-size: 32px; font-weight: 700; letter-spacing: 8px; color: #38BDF8; }}
            .footer {{ font-size: 12px; color: #64748B; margin-top: 32px; text-align: center; }}
          </style>
        </head>
        <body>
          <div class="card">
            <div class="brand">🧠 MemoryBrain.ai</div>
            <h2>Confirm your email address</h2>
            <p>Hello {name or "Developer"},</p>
            <p>Welcome to MemoryBrain. Please use the following 6-digit verification code to confirm your email and activate your long-term agent memory workspace:</p>
            <div class="code-box">
              <div class="code">{code}</div>
            </div>
            <p style="font-size: 13px;">This code will expire in <strong>15 minutes</strong>. If you did not create this account, you can safely ignore this email.</p>
            <div class="footer">&copy; MemoryBrain Platform &bull; Context Infrastructure for Autonomous AI Fleets</div>
          </div>
        </body>
        </html>
        """
        return cls._send_resend(to_email, subject, html_body)

    @classmethod
    def send_password_reset(cls, to_email: str, reset_token: str, app_url: Optional[str] = None) -> bool:
        """Sends password reset link to user."""
        base = (app_url or settings.app_base_url or "http://localhost:8000").rstrip("/")
        reset_link = f"{base}/landing?reset_token={reset_token}&email={to_email}#reset-password"

        subject = "Reset your MemoryBrain password"
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0F172A; color: #F8FAFC; margin: 0; padding: 32px 16px; }}
            .card {{ max-width: 520px; margin: 0 auto; background: #1E293B; border: 1px solid #334155; border-radius: 12px; padding: 32px; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }}
            .brand {{ font-size: 20px; font-weight: 700; color: #8CCFD8; letter-spacing: -0.02em; margin-bottom: 24px; }}
            h2 {{ font-size: 22px; color: #F8FAFC; margin-top: 0; }}
            p {{ font-size: 15px; line-height: 1.6; color: #94A3B8; }}
            .btn {{ display: inline-block; background: #635BFF; color: #FFFFFF !important; font-weight: 600; font-size: 15px; text-decoration: none; padding: 12px 28px; border-radius: 6px; margin: 24px 0; text-align: center; }}
            .footer {{ font-size: 12px; color: #64748B; margin-top: 32px; text-align: center; }}
          </style>
        </head>
        <body>
          <div class="card">
            <div class="brand">🧠 MemoryBrain.ai</div>
            <h2>Password Reset Request</h2>
            <p>We received a request to reset the password for your MemoryBrain developer account.</p>
            <p>Click the button below to choose a new password:</p>
            <div style="text-align: center;">
              <a href="{reset_link}" class="btn">Reset Password</a>
            </div>
            <p style="font-size: 13px;">Or copy and paste this link in your browser:<br><code style="color:#8CCFD8; word-break:break-all;">{reset_link}</code></p>
            <p style="font-size: 13px; color: #64748B;">This link is valid for <strong>1 hour</strong>. If you did not request a password reset, you can safely ignore this email.</p>
            <div class="footer">&copy; MemoryBrain Platform &bull; Context Infrastructure for Autonomous AI Fleets</div>
          </div>
        </body>
        </html>
        """
        return cls._send_resend(to_email, subject, html_body)

    @classmethod
    def send_welcome_email(cls, to_email: str, name: str, api_key: str) -> bool:
        """Sends welcome confirmation with developer quickstart hints."""
        subject = "Welcome to MemoryBrain — Your Workspace is Ready"
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0F172A; color: #F8FAFC; margin: 0; padding: 32px 16px; }}
            .card {{ max-width: 520px; margin: 0 auto; background: #1E293B; border: 1px solid #334155; border-radius: 12px; padding: 32px; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }}
            .brand {{ font-size: 20px; font-weight: 700; color: #8CCFD8; letter-spacing: -0.02em; margin-bottom: 24px; }}
            h2 {{ font-size: 22px; color: #F8FAFC; margin-top: 0; }}
            p {{ font-size: 15px; line-height: 1.6; color: #94A3B8; }}
            .key-box {{ background: #0B0F17; border: 1px solid #334155; border-radius: 6px; padding: 12px; font-family: monospace; color: #34D399; word-break: break-all; margin: 16px 0; }}
            .footer {{ font-size: 12px; color: #64748B; margin-top: 32px; text-align: center; }}
          </style>
        </head>
        <body>
          <div class="card">
            <div class="brand">🧠 MemoryBrain.ai</div>
            <h2>Account Verified &amp; Active!</h2>
            <p>Hello {name or "Developer"},</p>
            <p>Your MemoryBrain account is now verified. Your primary production API key has been provisioned:</p>
            <div class="key-box">{api_key}</div>
            <p>You can now ingest conversation turns and perform sub-25ms hybrid context recall across your AI agents.</p>
            <div class="footer">&copy; MemoryBrain Platform &bull; Context Infrastructure for Autonomous AI Fleets</div>
          </div>
        </body>
        </html>
        """
        return cls._send_resend(to_email, subject, html_body)
