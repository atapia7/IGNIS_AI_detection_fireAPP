"""
IgnisAI - Motor de Inferencia (HU01 / HU03 / HU08 - Sprint 1)
Envoltura sobre YOLOv8 (Ultralytics). Si no hay pesos entrenados o la
librería no está instalada, opera en MODO SIMULACIÓN para permitir la
demostración funcional del MVP (interfaz, alertas, historial, reportes).
"""
import os
import time
import logging

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

# Mapa canónico: cualquier nombre del modelo → clase interna
_NAME_MAP = {
    "fire":  "fuego",
    "fuego": "fuego",
    "flame": "fuego",
    "smoke": "humo",
    "humo":  "humo",
}


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
            from ultralytics import YOLO
            if os.path.exists(self.model_path):
                t0 = time.time()
                self.model = YOLO(self.model_path)
                class_names = list(self.model.names.values())
                logger.info(
                    "Arranque exitoso del modelo YOLOv8 '%s' en %.2f s. Clases: %s",
                    os.path.basename(self.model_path), time.time() - t0, class_names,
                )
                found = {n.lower() for n in class_names}
                if not ({"fire", "fuego", "flame"} & found):
                    logger.warning(
                        "El modelo no contiene clases de fuego reconocidas. "
                        "Clases encontradas: %s. Revise el archivo de pesos.",
                        class_names,
                    )
                if not ({"smoke", "humo"} & found):
                    logger.warning(
                        "El modelo no contiene clase de humo (%s). "
                        "La detección de humo no estará disponible.",
                        class_names,
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

    @property
    def supports_smoke(self) -> bool:
        """True si el modelo actual puede detectar humo."""
        if self.simulated:
            return True
        return any(n.lower() in ("smoke", "humo") for n in self.model.names.values())

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
                raw = str(names.get(cls_id, "")).lower()

                # 1) Mapeo por nombre (fuego / humo / fire / smoke / flame)
                clase = _NAME_MAP.get(raw)

                # 2) Fallback por índice usando TARGET_CLASSES de config
                if clase is None:
                    raw_fallback = config.TARGET_CLASSES.get(cls_id, "")
                    clase = _NAME_MAP.get(raw_fallback.lower())

                if clase is None:
                    continue

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detections.append(Detection(clase, conf, (x1, y1, x2, y2)))
        return detections

    def _simulate(self, frame):
        """
        Heurística HSV de respaldo: detecta regiones con colorimetría de
        llama (rojo/naranja) y humo (gris de baja saturación).
        Confianza determinista basada en proporción del área detectada.
        """
        h, w = frame.shape[:2]
        frame_area = h * w
        min_area = max(500, frame_area * 0.002)  # mínimo 0.2 % del fotograma

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Fuego: tono naranja/rojo (H ∈ [0,18] ∪ [170,180]), alta saturación y brillo
        m1 = cv2.inRange(hsv, (0,   120, 150), (18,  255, 255))
        m2 = cv2.inRange(hsv, (170, 120, 150), (180, 255, 255))
        fire_mask = cv2.morphologyEx(m1 | m2, cv2.MORPH_OPEN,
                                     np.ones((5, 5), np.uint8))

        # Humo: gris de baja saturación con brillo medio
        smoke_raw = cv2.inRange(hsv, (0, 0, 90), (180, 45, 210))
        smoke_mask = cv2.morphologyEx(smoke_raw, cv2.MORPH_OPEN,
                                      np.ones((7, 7), np.uint8))

        detections = []
        for mask, clase in ((fire_mask, "fuego"), (smoke_mask, "humo")):
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)
            for c in contours:
                area = cv2.contourArea(c)
                if area < min_area:
                    continue
                x, y, cw, ch = cv2.boundingRect(c)
                # Confianza determinista: área relativa → [0.50, 0.92]
                conf = min(0.92, 0.50 + (area / frame_area) * 15)
                detections.append(Detection(clase, conf, (x, y, x + cw, y + ch)))
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
