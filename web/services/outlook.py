import logging

from core.http_client import requests_lib as _requests

log = logging.getLogger("mant")

try:
    from msal import ConfidentialClientApplication
except ImportError:
    ConfidentialClientApplication = None


class OutlookClient:
    def __init__(self, cfg: dict):
        self.client_id = cfg.get("azure_client_id", "")
        self.client_secret = cfg.get("azure_client_secret", "")
        self.tenant_id = cfg.get("azure_tenant_id", "")
        self.calendar_id = cfg.get("outlook_calendar_id", "")
        self.user_upn = cfg.get("outlook_user_upn", "")
        self.notify_emails = [
            e.strip() for e in cfg.get("notify_emails", "").split(",") if e.strip()
        ]
        self.token = None

    def _graph_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def _user_path(self) -> str:
        if self.user_upn and self.user_upn.lower() != "me":
            return f"users/{self.user_upn}"
        return "me"

    def authenticate(self):
        if not ConfidentialClientApplication:
            raise RuntimeError("Instala msal: pip install msal")
        if not self.client_id:
            raise RuntimeError("Falta azure_client_id en la configuración.")
        if not self.client_secret:
            raise RuntimeError("Falta azure_client_secret en la configuración.")
        if not self.tenant_id:
            raise RuntimeError("Falta azure_tenant_id en la configuración.")
        if not self.user_upn or self.user_upn.lower() == "me":
            raise RuntimeError(
                "Con tokens de aplicación (client_credentials) debes indicar el UPN/email "
                "del usuario en 'UPN del buzón' (campo outlook_user_upn). "
                "Ejemplo: usuario@sicolsa.com"
            )

        msal_app = ConfidentialClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=self.client_secret,
        )
        result = msal_app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in result:
            raise RuntimeError(
                f"Autenticación Azure fallida: {result.get('error_description', result.get('error', 'desconocido'))}"
            )
        self.token = result["access_token"]
        log.info("Outlook: token obtenido correctamente")

    def create_event(self, subject: str, inicio_iso: str, fin_iso: str, attendees: list[str] | None = None) -> str:
        base = f"https://graph.microsoft.com/v1.0/{self._user_path()}"
        url = (
            f"{base}/calendars/{self.calendar_id}/events"
            if self.calendar_id
            else f"{base}/calendar/events"
        )

        body: dict = {
            "subject": subject,
            "start": {"dateTime": inicio_iso, "timeZone": "America/Bogota"},
            "end": {"dateTime": fin_iso, "timeZone": "America/Bogota"},
            "isReminderOn": True,
            "reminderMinutesBeforeStart": 30,
        }

        all_attendees = list(set((attendees or []) + self.notify_emails))
        if all_attendees:
            body["attendees"] = [
                {"emailAddress": {"address": email}, "type": "required"}
                for email in all_attendees
                if email
            ]

        r = _requests.post(url, headers=self._graph_headers(), json=body)
        if not r.ok:
            log.error(f"Outlook create_event error {r.status_code}: {r.text[:400]}")
        r.raise_for_status()
        log.info(f"Outlook: evento creado '{subject}'")
        return r.json().get("id")

    def send_email(self, destinatarios: list[str], subject: str, body_html: str) -> None:
        if not destinatarios:
            return
        url = f"https://graph.microsoft.com/v1.0/{self._user_path()}/sendMail"
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "HTML", "content": body_html},
                "toRecipients": [{"emailAddress": {"address": e}} for e in destinatarios if e],
            },
            "saveToSentItems": True,
        }
        r = _requests.post(url, headers=self._graph_headers(), json=payload)
        if not r.ok:
            log.error(f"Outlook send_email error {r.status_code}: {r.text[:400]}")
        r.raise_for_status()
        log.info(f"Correo enviado a {destinatarios} — '{subject}'")

    def delete_event(self, event_id: str) -> None:
        if not event_id:
            raise ValueError("event_id vacío")
        base = f"https://graph.microsoft.com/v1.0/{self._user_path()}"
        url = (
            f"{base}/calendars/{self.calendar_id}/events/{event_id}"
            if self.calendar_id
            else f"{base}/events/{event_id}"
        )
        r = _requests.delete(url, headers=self._graph_headers())
        if not r.ok:
            log.error(f"Outlook delete_event error {r.status_code}: {r.text[:400]}")
        r.raise_for_status()
        log.info(f"Outlook: evento eliminado '{event_id}'")
