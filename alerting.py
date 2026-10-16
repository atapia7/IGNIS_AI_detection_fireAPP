"""
IgnisAI - Alertas automáticas vía correo electrónico (HU06 - Sprint 2)
- Se dispara cuando la detección se mantiene constante > 5 segundos.
- Asunto estandarizado: "ALERTA IGNISAI: Posible incendio detectado".
- Soporta dos proveedores: Resend (API HTTP, recomendado en cloud) y
  Gmail SMTP (para uso local).
"""
import os
import time
import smtplib
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

import cv2

import config
import database as db

logger = logging.getLogger("ignisai")


# ---------------------------------------------------------------
# Envío vía Resend (HTTP API — funciona en cualquier cloud)
# ---------------------------------------------------------------
def _enviar_resend(cfg: dict, subject: str, body: str, imagen_path: str = None) -> None:
    import resend as _resend
    _resend.api_key = cfg["password"]
    params = {
        "from": cfg["user"],
        "to": cfg["destinatarios"],
        "subject": subject,
        "text": body,
    }
    if imagen_path and os.path.exists(imagen_path):
        with open(imagen_path, "rb") as f:
            contenido = list(f.read())
        params["attachments"] = [{
            "filename": os.path.basename(imagen_path),
            "content": contenido,
        }]
    _resend.Emails.send(params)


# ---------------------------------------------------------------
# Envío vía SMTP (Gmail u otro servidor)
# ---------------------------------------------------------------
def _enviar_smtp(cfg: dict, msg) -> None:
    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as s:
            s.starttls()
            s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
    except Exception as e_starttls:
        logger.warning("STARTTLS falló (%s), reintentando con SSL/465…", e_starttls)
        with smtplib.SMTP_SSL(cfg["host"], 465, timeout=15) as s:
            s.login(cfg["user"], cfg["password"])
            s.send_message(msg)


def _config_activa():
    """
    Resuelve la configuración de correo vigente.
    Prioriza la guardada desde la web; si no está habilitada recae en
    las variables de entorno. Devuelve None si no hay configuración.
    """
    guardada = db.get_smtp_config(incluir_password=True)
    if guardada and guardada["habilitado"] and guardada["remitente"] and guardada["app_password"]:
        return {
            "host": guardada["smtp_host"],      # 'resend' o 'smtp.gmail.com'
            "port": guardada["smtp_port"],
            "user": guardada["remitente"],
            "password": guardada["app_password"],
            "destinatarios": guardada["destinatarios"],
            "origen": "web",
        }
    if config.SMTP_USER and config.SMTP_PASSWORD and config.ALERT_RECIPIENTS:
        return {
            "host": config.SMTP_HOST,
            "port": config.SMTP_PORT,
            "user": config.SMTP_USER,
            "password": config.SMTP_PASSWORD,
            "destinatarios": config.ALERT_RECIPIENTS,
            "origen": "entorno",
        }
    return None


def _despachar(cfg: dict, subject: str, body: str, imagen_path: str = None) -> None:
    """Despacha el correo al proveedor correcto según cfg['host']."""
    if cfg["host"] == "resend":
        _enviar_resend(cfg, subject, body, imagen_path)
    else:
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = cfg["user"]
        msg["To"] = ", ".join(cfg["destinatarios"])
        msg.attach(MIMEText(body, "plain", "utf-8"))
        if imagen_path and os.path.exists(imagen_path):
            with open(imagen_path, "rb") as f:
                img = MIMEImage(f.read(), name=os.path.basename(imagen_path))
                msg.attach(img)
        _enviar_smtp(cfg, msg)


class AlertManager:
    """Controla la lógica de detección sostenida y el envío de correos."""

    def __init__(self):
        self.detection_started_at = None
        self.last_email_at = 0.0

    def update(self, has_detection: bool) -> bool:
        now = time.time()
        if not has_detection:
            self.detection_started_at = None
            return False
        if self.detection_started_at is None:
            self.detection_started_at = now
            return False
        sostenida = now - self.detection_started_at >= config.ALERT_SUSTAIN_SECONDS
        fuera_cooldown = now - self.last_email_at >= config.ALERT_COOLDOWN_SECONDS
        if sostenida and fuera_cooldown:
            self.last_email_at = now
            self.detection_started_at = None
            return True
        return False

    @staticmethod
    def guardar_fotograma(frame) -> str:
        os.makedirs(os.path.join(config.BASE_DIR, "assets"), exist_ok=True)
        nombre = datetime.now().strftime("alerta_%Y%m%d_%H%M%S.jpg")
        ruta = os.path.join(config.BASE_DIR, "assets", nombre)
        cv2.imwrite(ruta, frame)
        return ruta

    @staticmethod
    def enviar_correo(imagen_path: str, clase: str, confianza: float) -> bool:
        cfg = _config_activa()
        if cfg is None:
            logger.warning("Correo no configurado: alerta registrada sin envío.")
            return False
        ahora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        body = (
            f"Se ha detectado una posible amenaza de tipo '{clase.upper()}' "
            f"con una confianza del {confianza * 100:.1f}%.\n\n"
            f"Fecha y hora de la detección: {ahora}\n\n"
            "Se adjunta el fotograma exacto capturado por la cámara con el "
            "recuadro de detección dibujado.\n\n"
            "-- Sistema de Detección Temprana de Incendios Forestales IgnisAI"
        )
        try:
            _despachar(cfg, config.EMAIL_SUBJECT, body, imagen_path)
            logger.info("Correo de alerta enviado a %s (config: %s)",
                        ", ".join(cfg["destinatarios"]), cfg["origen"])
            return True
        except Exception as exc:
            logger.error("Fallo en el envío del correo de alerta: %s", exc)
            return False

    @staticmethod
    def enviar_correo_prueba():
        cfg = _config_activa()
        if cfg is None:
            return False, ("No hay configuración de correo habilitada. "
                           "Configure el proveedor y guarde primero.")
        ahora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        body = (
            "Este es un correo de prueba generado desde el módulo de Configuración "
            "de IgnisAI para verificar el envío de alertas (HU06).\n\n"
            f"Fecha y hora de la prueba: {ahora}\n\n"
            "Si ha recibido este mensaje, la configuración es correcta y el "
            "sistema podrá notificar automáticamente las detecciones sostenidas."
        )
        try:
            _despachar(cfg, "IgnisAI: correo de prueba de configuración", body)
            logger.info("Correo de prueba enviado a %s", ", ".join(cfg["destinatarios"]))
            return True, f"Correo de prueba enviado correctamente a {', '.join(cfg['destinatarios'])}."
        except Exception as exc:
            return False, f"No se pudo enviar el correo de prueba: {exc}"
