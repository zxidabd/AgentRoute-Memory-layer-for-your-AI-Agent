"""Transactional email service supporting Resend API and SMTP fallback."""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
import httpx
from ..config import settings

logger = logging.getLogger("agentroute.email")


class EmailService:
    """Manages transactional emails via Resend REST API or standard SMTP."""

    RESEND_API_URL = "https://api.resend.com/emails"

    @classmethod
    def _get_from_header(cls) -> str:
        from_email = settings.resend_from_email.strip() if settings.resend_from_email else "noreply@agentroute.co"
        from_name = settings.smtp_from_name.strip() if settings.smtp_from_name else "AgentRoute-AI memory layer"
        if "<" in from_email:
            return from_email
        return f"{from_name} <{from_email}>"

    @classmethod
    def _send_smtp_fallback(cls, to_email: str, subject: str, html_body: str) -> bool:
        """Sends email via standard SMTP."""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = cls._get_from_header()
            msg["To"] = to_email

            part = MIMEText(html_body, "html")
            msg.attach(part)

            server_host = settings.smtp_server or "smtp.resend.com"
            server_port = settings.smtp_port or 587
            username = "resend" if "resend.com" in server_host else (settings.smtp_username or "resend")
            password = settings.smtp_password or settings.resend_api_key

            with smtplib.SMTP(server_host, server_port, timeout=10.0) as server:
                server.starttls()
                if password:
                    server.login(username, password)
                server.sendmail(msg["From"], [to_email], msg.as_string())
            logger.info(f"Email successfully delivered to {to_email} via SMTP.")
            return True
        except Exception as e:
            logger.warning(f"SMTP dispatch to {to_email} failed: {e}")
            return False

    @classmethod
    def _dispatch_email(cls, to_email: str, subject: str, html_body: str) -> bool:
        """Attempts Resend REST API dispatch first; falls back to SMTP if configured."""
        if settings.environment in ("testing", "test"):
            return True

        api_key = settings.resend_api_key.strip() if settings.resend_api_key else ""
        from_header = cls._get_from_header()

        # If it looks like a Resend API key (re_...), call Resend API
        if api_key.startswith("re_"):
            try:
                payload = {
                    "from": from_header,
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
                        logger.info(f"Delivered email to {to_email} via Resend. ID: {resp.json().get('id')}")
                        return True
                    elif resp.status_code in (403, 422) and "resend.dev" not in from_header:
                        logger.warning(f"Custom domain unverified in Resend. Retrying with verified onboarding@resend.dev...")
                        payload["from"] = "AgentRoute <onboarding@resend.dev>"
                        retry_resp = client.post(cls.RESEND_API_URL, json=payload, headers=headers)
                        if retry_resp.status_code in (200, 201):
                            logger.info(f"Delivered email to {to_email} via Resend fallback. ID: {retry_resp.json().get('id')}")
                            return True
            except Exception as exc:
                logger.warning(f"Resend HTTP request failed: {exc}, attempting SMTP fallback...")

        # Fallback to standard SMTP
        if settings.smtp_password:
            return cls._send_smtp_fallback(to_email, subject, html_body)

        # Simulation mode for local dev when no keys set
        print(f"\n================ [EMAIL DEV SIMULATION] ================")
        print(f"To: {to_email}")
        print(f"Subject: {subject}")
        print(f"========================================================\n")
        return True

    @classmethod
    def send_verification_email(cls, to_email: str, name: str, token: str, code: Optional[str] = None) -> bool:
        """
        Sends verification email with direct CTA button (https://domain/verify-email?token=...)
        and backup 6-digit confirmation code.
        """
        base = (settings.app_base_url or "http://localhost:8000").rstrip("/")
        verify_link = f"{base}/landing?token={token}&email={to_email}#verify-email"

        subject = "Confirm your AgentRoute Memory account"
        code_markup = ""
        if code:
            code_markup = f"""
            <div style="background: #0B0F17; border: 1px solid #38BDF8; border-radius: 8px; padding: 14px; text-align: center; margin: 20px 0;">
              <span style="font-size: 13px; color: #94A3B8; display: block; margin-bottom: 4px;">Or enter this 6-digit confirmation code:</span>
              <span style="font-family: 'JetBrains Mono', monospace, Courier; font-size: 28px; font-weight: 700; letter-spacing: 6px; color: #38BDF8;">{code}</span>
            </div>
            """

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0F172A; color: #F8FAFC; margin: 0; padding: 32px 16px; }}
            .card {{ max-width: 540px; margin: 0 auto; background: #1E293B; border: 1px solid #334155; border-radius: 12px; padding: 32px; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }}
            .brand {{ font-size: 20px; font-weight: 700; color: #8CCFD8; letter-spacing: -0.02em; margin-bottom: 24px; }}
            h2 {{ font-size: 22px; color: #F8FAFC; margin-top: 0; }}
            p {{ font-size: 15px; line-height: 1.6; color: #94A3B8; }}
            .btn-cta {{ display: inline-block; background: #635BFF; color: #FFFFFF !important; font-weight: 600; font-size: 15px; text-decoration: none; padding: 14px 32px; border-radius: 8px; margin: 24px 0; text-align: center; box-shadow: 0 2px 10px rgba(99,91,255,0.4); }}
            .footer {{ font-size: 12px; color: #64748B; margin-top: 32px; text-align: center; }}
          </style>
        </head>
        <body>
          <div class="card">
            <div class="brand">🧠 AgentRoute &bull; MemoryBrain</div>
            <h2>Verify your email address</h2>
            <p>Hello {name or "Developer"},</p>
            <p>Welcome to AgentRoute! Your 3-day full-access free trial is ready. Click the button below to confirm your email and immediately enter your workspace:</p>
            <div style="text-align: center;">
              <a href="{verify_link}" class="btn-cta">Verify Email &amp; Launch Workspace &rarr;</a>
            </div>
            {code_markup}
            <p style="font-size: 13px;">Direct link:<br><code style="color:#8CCFD8; word-break:break-all;">{verify_link}</code></p>
            <p style="font-size: 12px; color: #64748B;">This verification link expires in <strong>24 hours</strong>. If you did not create this account, you can safely ignore this email.</p>
            <div class="footer">&copy; AgentRoute &bull; AI Agent Memory Infrastructure</div>
          </div>
        </body>
        </html>
        """
        return cls._dispatch_email(to_email, subject, html_body)

    @classmethod
    def send_signup_verification(cls, to_email: str, name: str, code: str) -> bool:
        """Sends 6-digit confirmation code on user signup (calls send_verification_email)."""
        return cls.send_verification_email(to_email, name, token=code, code=code)

    @classmethod
    def send_password_reset(cls, to_email: str, reset_token: str, app_url: Optional[str] = None) -> bool:
        """Sends password reset link to user."""
        base = (app_url or settings.app_base_url or "http://localhost:8000").rstrip("/")
        reset_link = f"{base}/landing?reset_token={reset_token}&email={to_email}#reset-password"

        subject = "Reset your AgentRoute password"
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
            <div class="brand">🧠 AgentRoute</div>
            <h2>Password Reset Request</h2>
            <p>We received a request to reset the password for your developer account.</p>
            <div style="text-align: center;">
              <a href="{reset_link}" class="btn">Reset Password</a>
            </div>
            <p style="font-size: 13px;">Or copy and paste this link in your browser:<br><code style="color:#8CCFD8; word-break:break-all;">{reset_link}</code></p>
            <p style="font-size: 13px; color: #64748B;">This link is valid for <strong>1 hour</strong>.</p>
            <div class="footer">&copy; AgentRoute &bull; AI Agent Memory Infrastructure</div>
          </div>
        </body>
        </html>
        """
        return cls._dispatch_email(to_email, subject, html_body)

    @classmethod
    def send_welcome_email(cls, to_email: str, name: str, api_key: str) -> bool:
        """Sends welcome confirmation with developer quickstart hints."""
        subject = "Welcome to AgentRoute — Your Workspace is Ready"
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
            <div class="brand">🧠 AgentRoute</div>
            <h2>Account Verified &amp; 3-Day Trial Active!</h2>
            <p>Hello {name or "Developer"},</p>
            <p>Your workspace is now live. Your primary production API key has been provisioned:</p>
            <div class="key-box">{api_key}</div>
            <p>You can now ingest conversation turns and perform sub-25ms hybrid context recall across your AI agents.</p>
            <div class="footer">&copy; AgentRoute &bull; AI Agent Memory Infrastructure</div>
          </div>
        </body>
        </html>
        """
        return cls._dispatch_email(to_email, subject, html_body)

    @classmethod
    def send_contact_alert(cls, name: str, email: str, subject: str, message: str) -> bool:
        """Dispatches an inquiry notification to the business support inbox."""
        support_inbox = settings.support_email or "abdullahzaid509@gmail.com"
        alert_subject = f"[New Support Inquiry] {subject} - from {name}"
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: sans-serif; background: #f8fafc; color: #0f172a; padding: 24px;">
          <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 24px;">
            <h2 style="margin-top: 0; color: #4338ca;">New Support / Contact Inquiry</h2>
            <p><strong>From:</strong> {name} &lt;{email}&gt;</p>
            <p><strong>Subject:</strong> {subject}</p>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 16px 0;">
            <p><strong>Message:</strong></p>
            <div style="background: #f1f5f9; padding: 16px; border-radius: 6px; white-space: pre-wrap;">{message}</div>
          </div>
        </body>
        </html>
        """
        return cls._dispatch_email(support_inbox, alert_subject, html_body)

    @classmethod
    def send_contact_acknowledgment(cls, name: str, email: str, subject: str) -> bool:
        """Sends an automated acknowledgment to the user/visitor."""
        ack_subject = f"We received your message: {subject}"
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: sans-serif; background: #0f172a; color: #f8fafc; padding: 24px;">
          <div style="max-width: 520px; margin: 0 auto; background: #1e293b; border-radius: 8px; padding: 24px;">
            <h2 style="margin-top: 0; color: #8ccfd8;">AgentRoute Support</h2>
            <p>Hi {name},</p>
            <p>Thank you for reaching out. We have received your inquiry regarding <strong>"{subject}"</strong> and our engineering team will get back to you shortly.</p>
            <p style="font-size: 13px; color: #94a3b8;">Need urgent help? You can also reply directly to this email.</p>
            <p style="font-size: 12px; color: #64748b;">&copy; AgentRoute Support Team</p>
          </div>
        </body>
        </html>
        """
        return cls._dispatch_email(email, ack_subject, html_body)
