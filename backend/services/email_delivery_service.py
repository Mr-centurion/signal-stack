import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any, Optional

class EmailDeliveryService:
    """
    Handles briefing delivery via SMTP if configured in .env.
    If SMTP variables are not set, cleanly logs:
    'delivery skipped: SMTP not configured' and marks delivery skipped.
    """

    @property
    def is_configured(self) -> bool:
        return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER"))

    def send_brief_email(
        self,
        company_name: str,
        week_label: str,
        html_content: str,
        recipient_override: Optional[str] = None
    ) -> Dict[str, Any]:
        smtp_host = os.getenv("SMTP_HOST")
        smtp_port = int(os.getenv("SMTP_PORT", 587))
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")
        smtp_from = os.getenv("SMTP_FROM", "briefs@signalstack.local")
        recipient = recipient_override or os.getenv("RECIPIENT_EMAIL")

        # Guard: Check if SMTP variables exist
        if not smtp_host or not smtp_user:
            skip_msg = "delivery skipped: SMTP not configured"
            print(f"[DELIVERY] {company_name} ({week_label}): {skip_msg}")
            return {
                "delivered": False,
                "status": "skipped",
                "reason": skip_msg
            }

        if not recipient:
            skip_msg = "delivery skipped: No recipient email specified"
            print(f"[DELIVERY] {company_name} ({week_label}): {skip_msg}")
            return {
                "delivered": False,
                "status": "skipped",
                "reason": skip_msg
            }

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"Monday Morning Strategic Brief: {company_name} ({week_label})"
            msg["From"] = smtp_from
            msg["To"] = recipient

            part = MIMEText(html_content, "html")
            msg.attach(part)

            with smtplib.SMTP(smtp_host, smtp_port, timeout=15.0) as server:
                server.starttls()
                if smtp_password:
                    server.login(smtp_user, smtp_password)
                server.sendmail(smtp_from, [recipient], msg.as_string())

            success_msg = f"Delivered email to {recipient}"
            print(f"[DELIVERY SUCCESS] {company_name}: {success_msg}")
            return {
                "delivered": True,
                "status": "delivered",
                "recipient": recipient,
                "details": success_msg
            }
        except Exception as e:
            err_msg = f"Delivery failed: {str(e)}"
            print(f"[DELIVERY ERROR] {company_name}: {err_msg}")
            return {
                "delivered": False,
                "status": "failed",
                "error": err_msg
            }

email_delivery_service = EmailDeliveryService()
