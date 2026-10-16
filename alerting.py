"""
IgnisAI - Alertas automáticas vía correo electrónico (HU06 - Sprint 2)
- Se dispara cuando la detección se mantiene constante > 5 segundos.
- Asunto estandarizado: "ALERTA IGNISAI: Posible incendio detectado".
- Cuerpo con el fotograma capturado (recuadro dibujado), fecha y hora.
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


def _enviar_smtp(cfg: dict, msg) -> None:
    """
    Intenta enviar el mensaje con STARTTLS (puerto configurado, por defecto 587).
    Si falla, reintenta con SMTP_SSL en puerto 465, que algunos proveedores
    cloud bloquean menos que STARTTLS.
    """
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
    Resuelve la configuración SMTP vigente: prioriza la guardada desde la
    web (HU06, cifrada en la base de datos); si no está habilitada, recae
    en las variables de entorno definidas al arrancar la aplicación.
    Devuelve None si no hay ninguna configuración utilizable.
    """
    guardada = db.get_smtp_config(incluir_password=True)
    if guardada and guardada["habilitado"] and guardada["remitente"] and guardada["app_password"]:
        return {
            "host": guardada["smtp_host"],
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


class AlertManager:
    """Controla la lógica de detección sostenida y el envío de correos."""

    def __init__(self):
        self.detection_started_at = None   # inicio de la racha de detección
        self.last_email_at = 0.0           # anti-spam (cooldown)

    def update(self, has_detection: bool) -> bool:
        """
        Actualiza la máquina de estados de detección sostenida.
        Devuelve True si corresponde disparar una alerta (>= 5 s sostenidos
        y fuera del periodo de enfriamiento).
        """
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

    # ------------------------------------------------------------------
    @staticmethod
    def guardar_fotograma(frame) -> str:
        """Guarda el fotograma anotado como evidencia visual de la alerta."""
        os.makedirs(os.path.join(config.BASE_DIR, "assets"), exist_ok=True)
        nombre = datetime.now().strftime("alerta_%Y%m%d_%H%M%S.jpg")
        ruta = os.path.join(config.BASE_DIR, "assets", nombre)
        cv2.imwrite(ruta, frame)
        return ruta

    @staticmethod
    def enviar_correo(imagen_path: str, clase: str, confianza: float) -> bool:
        """Envía la notificación SMTP con la evidencia adjunta (HU06)."""
        cfg = _config_activa()
        if cfg is None:
            logger.warning("SMTP no configurado: alerta registrada sin envío de correo.")
            return False

        ahora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        msg = MIMEMultipart()
        msg["Subject"] = config.EMAIL_SUBJECT
        msg["From"] = cfg["user"]
        msg["To"] = ", ".join(cfg["destinatarios"])

        cuerpo = (
            f"Se ha detectado una posible amenaza de tipo '{clase.upper()}' "
            f"con una confianza del {confianza * 100:.1f}%.\n\n"
            f"Fecha y hora de la detección: {ahora}\n\n"
            "Se adjunta el fotograma exacto capturado por la cámara con el "
            "recuadro de detección dibujado.\n\n"
            "-- Sistema de Detección Temprana de Incendios Forestales IgnisAI"
        )
        msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

        try:
            with open(imagen_path, "rb") as f:
                img = MIMEImage(f.read(), name=os.path.basename(imagen_path))
                msg.attach(img)
            _enviar_smtp(cfg, msg)
            logger.info("Correo de alerta enviado a %s (config: %s)", msg["To"], cfg["origen"])
            return True
        except Exception as exc:
            logger.error("Fallo en el envío del correo de alerta: %s", exc)
            return False

    @staticmethod
    def enviar_correo_prueba():
        """
        Envía un correo de prueba con la configuración recién guardada desde
        la interfaz (HU06). Devuelve (ok: bool, mensaje: str) para mostrar
        el resultado exacto en la vista de Configuración.
        """
        cfg = _config_activa()
        if cfg is None:
            return False, ("No hay una configuración SMTP habilitada. Guarde primero el "
                           "correo remitente, la Contraseña de Aplicación y los destinatarios.")

        ahora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        msg = MIMEMultipart()
        msg["Subject"] = "IgnisAI: correo de prueba de configuración"
        msg["From"] = cfg["user"]
        msg["To"] = ", ".join(cfg["destinatarios"])
        msg.attach(MIMEText(
            "Este es un correo de prueba generado desde el módulo de Configuración "
            "de IgnisAI para verificar el envío de alertas (HU06).\n\n"
            f"Fecha y hora de la prueba: {ahora}\n\n"
            "Si ha recibido este mensaje, la configuración SMTP es correcta y el "
            "sistema podrá notificar automáticamente las detecciones sostenidas.",
            "plain", "utf-8",
        ))
        try:
            _enviar_smtp(cfg, msg)
            logger.info("Correo de prueba enviado a %s", msg["To"])
            return True, f"Correo de prueba enviado correctamente a {msg['To']}."
        except smtplib.SMTPAuthenticationError:
            return False, ("Autenticación rechazada por el servidor SMTP. Verifique que el "
                           "correo remitente y la Contraseña de Aplicación (16 caracteres) "
                           "sean correctos y que la verificación en dos pasos esté activa "
                           "en la cuenta de Google.")
        except Exception as exc:
            return False, f"No se pudo enviar el correo de prueba: {exc}"
