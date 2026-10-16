"""
IgnisAI - Motor de Inferencia (HU01 / HU03 / HU08 - Sprint 1)
Envoltura sobre YOLOv8 (Ultralytics). Si no hay pesos entrenados o la
librería no está instalada, opera en MODO SIMULACIÓN para permitir la
demostración funcional del MVP (interfaz, alertas, historial, reportes).
"""
import os
import time
import logging
import random

import cv2
import numpy as np

import config

# --- Logging de arranque del modelo (criterio de aceptación HU01) ---
os.makedirs(config.LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=config.LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("ignisai")


class Detection:
    """Resultado de una detección individual."""
    __slots__ = ("clase", "confianza", "bbox")

    def __init__(self, clase, confianza, bbox):
        self.clase = clase          # 'fuego' | 'humo'
        self.confianza = confianza  # 0.0 - 1.0
        self.bbox = bbox            # (x1, y1, x2, y2)


class FireDetector:
    """
    Motor de reconocimiento visual (HU01).
    - Carga local del archivo de pesos YOLOv8 (.pt).
    - Inferencia sobre fotogramas con umbral de confianza del 50% (HU03).
    - Registra en log el arranque exitoso del modelo (HU01).
    """

    def __init__(self, model_path: str = None):
        self.model_path = model_path or config.DEFAULT_MODEL_PATH
        self.model = None
        self.simulated = False
        self._load()

    def _load(self):
        try:
            from ultralytics import YOLO  # import diferido: dependencia pesada
            if os.path.exists(self.model_path):
                t0 = time.time()
                self.model = YOLO(self.model_path)
                logger.info(
                    "Arranque exitoso del modelo YOLOv8 '%s' en %.2f s",
                    os.path.basename(self.model_path), time.time() - t0,
                )
                return
            logger.warning("Pesos no encontrados en %s. Se activa modo simulación.",
                           self.model_path)
        except ImportError:
            logger.warning("Ultralytics no instalado. Se activa modo simulación.")
        except Exception as exc:  # pragma: no cover
            logger.error("Error al cargar el modelo: %s. Modo simulación.", exc)
        self.simulated = True
        logger.info("Arranque del motor de detección en MODO SIMULACIÓN.")

    # ------------------------------------------------------------------
    def predict(self, frame) -> list:
        """Devuelve la lista de detecciones con confianza >= umbral (HU03)."""
        if self.simulated:
            return self._simulate(frame)

        results = self.model.predict(frame, verbose=False,
                                     conf=config.CONFIDENCE_THRESHOLD)
        detections = []
        for r in results:
            names = r.names
            for box in r.boxes:
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                clase = str(names.get(cls_id, cls_id)).lower()
                # Solo clases objetivo del dominio (humo / fuego)
                if clase not in ("fuego", "humo", "fire", "smoke"):
                    continue
                clase = {"fire": "fuego", "smoke": "humo"}.get(clase, clase)
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detections.append(Detection(clase, conf, (x1, y1, x2, y2)))
        return detections

    def _simulate(self, frame):
        """
        Heurística HSV de respaldo: detecta regiones con colorimetría de
        llama (rojo/naranja) para demostrar el pipeline sin pesos entrenados.
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        m1 = cv2.inRange(hsv, (0, 120, 150), (12, 255, 255))
        m2 = cv2.inRange(hsv, (170, 120, 150), (180, 255, 255))
        mask = cv2.morphologyEx(m1 | m2, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections = []
        for c in contours:
            if cv2.contourArea(c) < 800:
                continue
            x, y, w, h = cv2.boundingRect(c)
            conf = min(0.99, 0.55 + random.uniform(0, 0.3))
            detections.append(Detection("fuego", conf, (x, y, x + w, y + h)))
        return detections

    # ------------------------------------------------------------------
    @staticmethod
    def draw(frame, detections):
        """
        HU03: recuadro de color sobre la zona de humo/fuego.
        HU08/HU09: texto con el % de confianza en el borde superior,
        legible y con contraste sobre el video.
        """
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            color = config.BOX_COLORS.get(det.clase, (0, 0, 255))
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = f"{det.clase.upper()} {det.confianza * 100:.0f}%"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 6, y1), color, -1)
            cv2.putText(frame, label, (x1 + 3, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        return frame
