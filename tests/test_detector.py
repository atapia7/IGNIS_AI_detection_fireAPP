"""
Auditoría técnica IgnisAI — Suite de pruebas del motor de detección.

Cubre:
  - Modo simulación: fuego, humo, sin detección, determinismo, área relativa
  - Mapeo de clases: nombres en español, inglés, alias, índice de fallback
  - AlertManager: sostenido, cooldown, reset por interrupción
  - draw(): forma del frame de salida, sin crash
  - Casos límite: frames muy pequeños, frames con poco área de color
"""
import sys
import os
import time

import cv2
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

# Añadir raíz del proyecto al path para imports directos
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─────────────────────────────────────────────────────────────────
# Helpers de frames sintéticos
# ─────────────────────────────────────────────────────────────────

def _black(h=480, w=640):
    return np.zeros((h, w, 3), dtype=np.uint8)


def _fire_frame(h=480, w=640, patch_fraction=0.15):
    """Frame con parche naranja-rojo (HSV H=10, S=200, V=200)."""
    hsv = np.zeros((h, w, 3), dtype=np.uint8)
    ph, pw = int(h * patch_fraction), int(w * patch_fraction)
    r0, c0 = h // 4, w // 4
    hsv[r0:r0 + ph, c0:c0 + pw] = (10, 200, 200)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def _smoke_frame(h=480, w=640, patch_fraction=0.20):
    """Frame con parche gris de baja saturación (HSV H=0, S=10, V=150)."""
    hsv = np.zeros((h, w, 3), dtype=np.uint8)
    ph, pw = int(h * patch_fraction), int(w * patch_fraction)
    r0, c0 = h // 4, w // 4
    hsv[r0:r0 + ph, c0:c0 + pw] = (0, 10, 150)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def _tiny_fire_frame(h=480, w=640):
    """Parche naranja muy pequeño (< 0.2 % de área) — no debe detectarse."""
    hsv = np.zeros((h, w, 3), dtype=np.uint8)
    hsv[10:14, 10:14] = (10, 200, 200)  # ~16 px
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


# ─────────────────────────────────────────────────────────────────
# Fixture: detector en modo simulación
# ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def sim_det():
    from detector import FireDetector
    d = FireDetector(model_path="/nonexistent/path.pt")
    assert d.simulated, "No se activó el modo simulación con ruta inválida"
    return d


# ─────────────────────────────────────────────────────────────────
# 1. MODO SIMULACIÓN — detección de fuego
# ─────────────────────────────────────────────────────────────────

class TestSimulacionFuego:

    def test_frame_negro_sin_detecciones(self, sim_det):
        """Un frame completamente negro no debe generar ninguna detección."""
        assert sim_det.predict(_black()) == []

    def test_frame_fuego_detecta_fuego(self, sim_det):
        dets = sim_det.predict(_fire_frame())
        fuego = [d for d in dets if d.clase == "fuego"]
        assert len(fuego) >= 1, "Parche naranja grande debe detectarse como fuego"

    def test_frame_fuego_no_genera_humo(self, sim_det):
        dets = sim_det.predict(_fire_frame())
        humo = [d for d in dets if d.clase == "humo"]
        assert humo == [], "Un parche naranja no debe clasificarse como humo"

    def test_parche_muy_pequeno_ignorado(self, sim_det):
        """Área menor al 0.2 % del frame debe ignorarse (anti-ruido)."""
        dets = sim_det.predict(_tiny_fire_frame())
        assert dets == [], "Parche demasiado pequeño no debe generar detección"

    def test_confianza_en_rango_valido(self, sim_det):
        for d in sim_det.predict(_fire_frame()):
            assert 0.0 <= d.confianza <= 1.0, f"Confianza fuera de [0,1]: {d.confianza}"

    def test_confianza_minima_cumple_umbral(self, sim_det):
        """La simulación debe retornar confianzas ≥ 0.50 (umbral HU03)."""
        import config
        for d in sim_det.predict(_fire_frame()):
            assert d.confianza >= config.CONFIDENCE_THRESHOLD, (
                f"Confianza {d.confianza} < umbral {config.CONFIDENCE_THRESHOLD}"
            )

    def test_confianza_es_determinista(self, sim_det):
        """El mismo frame debe producir exactamente las mismas confianzas."""
        frame = _fire_frame()
        confs_a = sorted(d.confianza for d in sim_det.predict(frame))
        confs_b = sorted(d.confianza for d in sim_det.predict(frame))
        assert confs_a == confs_b, (
            f"Confianzas no deterministas: {confs_a} ≠ {confs_b}"
        )

    def test_bbox_dentro_del_frame(self, sim_det):
        frame = _fire_frame()
        h, w = frame.shape[:2]
        for d in sim_det.predict(frame):
            x1, y1, x2, y2 = d.bbox
            assert 0 <= x1 < x2 <= w, f"BBox X fuera de rango: {d.bbox}"
            assert 0 <= y1 < y2 <= h, f"BBox Y fuera de rango: {d.bbox}"

    def test_confianza_crece_con_area(self, sim_det):
        """Parche más grande → confianza mayor o igual."""
        small = _fire_frame(patch_fraction=0.08)
        large = _fire_frame(patch_fraction=0.30)
        dets_s = sim_det.predict(small)
        dets_l = sim_det.predict(large)
        if dets_s and dets_l:
            assert max(d.confianza for d in dets_l) >= max(d.confianza for d in dets_s)

    def test_frame_pequeno_umbrales_relativos(self, sim_det):
        """En un frame pequeño el umbral de área también escala."""
        small_frame = _fire_frame(h=120, w=160, patch_fraction=0.15)
        dets = sim_det.predict(small_frame)
        for d in dets:
            x1, y1, x2, y2 = d.bbox
            assert 0 <= x1 < x2 <= 160
            assert 0 <= y1 < y2 <= 120


# ─────────────────────────────────────────────────────────────────
# 2. MODO SIMULACIÓN — detección de humo
# ─────────────────────────────────────────────────────────────────

class TestSimulacionHumo:

    def test_frame_humo_detecta_humo(self, sim_det):
        dets = sim_det.predict(_smoke_frame())
        humo = [d for d in dets if d.clase == "humo"]
        assert len(humo) >= 1, (
            "Parche gris de baja saturación debe detectarse como humo. "
            "Este test falla en la implementación original (bug corregido)."
        )

    def test_frame_humo_no_detecta_fuego(self, sim_det):
        """El gris no es naranja; no debe producir detección de fuego."""
        dets = sim_det.predict(_smoke_frame())
        fuego = [d for d in dets if d.clase == "fuego"]
        assert fuego == [], "Frame gris no debe clasificarse como fuego"

    def test_supports_smoke_en_simulacion(self, sim_det):
        assert sim_det.supports_smoke is True


# ─────────────────────────────────────────────────────────────────
# 3. MODO SIMULACIÓN — iluminación variable
# ─────────────────────────────────────────────────────────────────

class TestCondicionesIluminacion:

    def test_fuego_oscurecido_no_detectado(self, sim_det):
        """Naranja muy oscuro (V < umbral) no debe detectarse."""
        hsv = np.zeros((480, 640, 3), dtype=np.uint8)
        hsv[100:200, 100:300] = (10, 200, 80)  # V=80 < 150 → bajo umbral
        frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        dets = sim_det.predict(frame)
        fuego = [d for d in dets if d.clase == "fuego"]
        assert fuego == [], "Naranja oscuro (V<150) no debe detectarse como fuego"

    def test_naranja_saturacion_baja_no_detectado(self, sim_det):
        """Naranja de baja saturación (lavado) no debe detectarse como fuego."""
        hsv = np.zeros((480, 640, 3), dtype=np.uint8)
        hsv[100:250, 100:350] = (10, 60, 200)  # S=60 < 120
        frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        dets = sim_det.predict(frame)
        fuego = [d for d in dets if d.clase == "fuego"]
        assert fuego == [], "Naranja con S<120 no debe detectarse como fuego"

    def test_humo_brillante_no_detectado(self, sim_det):
        """Blanco puro (V>210) supera el límite superior del rango de humo."""
        hsv = np.zeros((480, 640, 3), dtype=np.uint8)
        hsv[100:300, 100:400] = (0, 5, 250)  # V=250 > 210
        frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        dets = sim_det.predict(frame)
        humo = [d for d in dets if d.clase == "humo"]
        assert humo == [], "Blanco puro (V>210) no debe detectarse como humo"


# ─────────────────────────────────────────────────────────────────
# 4. MAPEO DE CLASES (con modelo mockeado)
# ─────────────────────────────────────────────────────────────────

def _make_mock_box(cls_id, conf, bbox=(10, 10, 100, 100)):
    box = MagicMock()
    box.conf = [conf]
    box.cls = [cls_id]
    box.xyxy = [bbox]
    return box


def _make_mock_result(cls_id, class_name, conf=0.80):
    result = MagicMock()
    result.names = {cls_id: class_name}
    result.boxes = [_make_mock_box(cls_id, conf)]
    return result


@pytest.fixture()
def model_det():
    """Detector con modelo YOLO falso (sin archivo real)."""
    from detector import FireDetector
    d = FireDetector(model_path="/nonexistent/path.pt")
    d.simulated = False
    d.model = MagicMock()
    return d


def _predict_with(model_det, cls_id, class_name, conf=0.80):
    model_det.model.predict.return_value = [_make_mock_result(cls_id, class_name, conf)]
    return model_det.predict(_black())


class TestMapeoClases:

    def test_fire_en_ingles(self, model_det):
        dets = _predict_with(model_det, 0, "fire")
        assert len(dets) == 1 and dets[0].clase == "fuego"

    def test_fuego_en_espanol(self, model_det):
        dets = _predict_with(model_det, 0, "fuego")
        assert len(dets) == 1 and dets[0].clase == "fuego"

    def test_flame_alias(self, model_det):
        dets = _predict_with(model_det, 0, "flame")
        assert len(dets) == 1 and dets[0].clase == "fuego"

    def test_smoke_en_ingles(self, model_det):
        dets = _predict_with(model_det, 1, "smoke")
        assert len(dets) == 1 and dets[0].clase == "humo"

    def test_humo_en_espanol(self, model_det):
        dets = _predict_with(model_det, 1, "humo")
        assert len(dets) == 1 and dets[0].clase == "humo"

    def test_fallback_indice_fuego(self, model_det):
        """Nombre desconocido pero índice 0 → TARGET_CLASSES['fire'] → 'fuego'."""
        dets = _predict_with(model_det, 0, "unknown_fire_class")
        assert len(dets) == 1 and dets[0].clase == "fuego"

    def test_fallback_indice_humo(self, model_det):
        """Nombre desconocido pero índice 1 → TARGET_CLASSES['smoke'] → 'humo'."""
        dets = _predict_with(model_det, 1, "unknown_smoke_class")
        assert len(dets) == 1 and dets[0].clase == "humo"

    def test_clase_desconocida_descartada(self, model_det):
        """Índice y nombre no mapeados → descartado silenciosamente."""
        dets = _predict_with(model_det, 99, "person")
        assert dets == []

    def test_confianza_preservada(self, model_det):
        dets = _predict_with(model_det, 0, "fire", conf=0.73)
        assert abs(dets[0].confianza - 0.73) < 1e-6

    def test_bbox_preservado(self, model_det):
        result = _make_mock_result(0, "fire")
        result.boxes[0].xyxy = [(5, 10, 200, 300)]
        model_det.model.predict.return_value = [result]
        dets = model_det.predict(_black())
        assert dets[0].bbox == (5, 10, 200, 300)

    def test_supports_smoke_false_sin_clase_humo(self, model_det):
        model_det.model.names = {0: "fire"}
        assert model_det.supports_smoke is False

    def test_supports_smoke_true_con_clase_smoke(self, model_det):
        model_det.model.names = {0: "fire", 1: "smoke"}
        assert model_det.supports_smoke is True


# ─────────────────────────────────────────────────────────────────
# 5. draw() — no crash, forma correcta
# ─────────────────────────────────────────────────────────────────

class TestDraw:
    from detector import Detection as Det

    def test_sin_detecciones_no_modifica_shape(self):
        from detector import FireDetector
        frame = _black()
        result = FireDetector.draw(frame.copy(), [])
        assert result.shape == frame.shape

    def test_con_deteccion_fuego(self):
        from detector import FireDetector, Detection
        frame = _black()
        dets = [Detection("fuego", 0.85, (10, 50, 200, 200))]
        result = FireDetector.draw(frame.copy(), dets)
        assert result.shape == frame.shape
        # El frame debe haber cambiado (se dibujó algo)
        assert not np.array_equal(result, frame)

    def test_con_deteccion_humo(self):
        from detector import FireDetector, Detection
        frame = _black()
        dets = [Detection("humo", 0.70, (30, 30, 150, 150))]
        result = FireDetector.draw(frame.copy(), dets)
        assert result.shape == frame.shape

    def test_multiples_detecciones(self):
        from detector import FireDetector, Detection
        frame = _black()
        dets = [
            Detection("fuego", 0.91, (10, 10, 100, 100)),
            Detection("humo",  0.65, (200, 200, 400, 350)),
        ]
        result = FireDetector.draw(frame.copy(), dets)
        assert result.shape == frame.shape

    def test_bbox_en_borde_del_frame(self):
        """draw() no debe lanzar excepción si el bbox toca el borde."""
        from detector import FireDetector, Detection
        frame = _black()
        h, w = frame.shape[:2]
        dets = [Detection("fuego", 0.80, (0, 0, w, h))]
        FireDetector.draw(frame.copy(), dets)  # no debe lanzar


# ─────────────────────────────────────────────────────────────────
# 6. AlertManager — lógica de tiempo y cooldown
# ─────────────────────────────────────────────────────────────────

class TestAlertManager:

    @pytest.fixture(autouse=True)
    def mgr(self):
        from alerting import AlertManager
        self.mgr = AlertManager()

    def test_sin_deteccion_retorna_false(self):
        assert self.mgr.update(False) is False

    def test_primera_deteccion_no_dispara(self):
        """La primera detección inicia el temporizador sin disparar la alerta."""
        assert self.mgr.update(True) is False

    def test_deteccion_sostenida_dispara(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "ALERT_SUSTAIN_SECONDS", 0)
        monkeypatch.setattr(config, "ALERT_COOLDOWN_SECONDS", 9999)
        self.mgr.update(True)
        assert self.mgr.update(True) is True

    def test_cooldown_bloquea_segundo_disparo(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "ALERT_SUSTAIN_SECONDS", 0)
        monkeypatch.setattr(config, "ALERT_COOLDOWN_SECONDS", 9999)
        self.mgr.update(True)
        self.mgr.update(True)          # primer disparo
        assert self.mgr.update(True) is False  # bloqueado por cooldown

    def test_cooldown_cero_permite_repetir(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "ALERT_SUSTAIN_SECONDS", 0)
        monkeypatch.setattr(config, "ALERT_COOLDOWN_SECONDS", 0)
        self.mgr.update(True)
        self.mgr.update(True)          # primer disparo
        self.mgr.update(True)          # reinicia temporizador
        assert self.mgr.update(True) is True   # dispara de nuevo

    def test_interrupcion_resetea_temporizador(self, monkeypatch):
        """Una interrupción (False) debe resetear el temporizador de sostenido."""
        import config
        monkeypatch.setattr(config, "ALERT_SUSTAIN_SECONDS", 0)
        monkeypatch.setattr(config, "ALERT_COOLDOWN_SECONDS", 9999)
        self.mgr.update(True)
        self.mgr.update(True)          # dispara, pone cooldown
        self.mgr.update(False)         # resetea timer
        assert self.mgr.detection_started_at is None

    def test_disparo_setea_last_email_at(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "ALERT_SUSTAIN_SECONDS", 0)
        monkeypatch.setattr(config, "ALERT_COOLDOWN_SECONDS", 9999)
        before = self.mgr.last_email_at
        self.mgr.update(True)
        self.mgr.update(True)
        assert self.mgr.last_email_at > before


# ─────────────────────────────────────────────────────────────────
# 7. Carga del modelo real (si existe)
# ─────────────────────────────────────────────────────────────────

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "best.pt")

@pytest.mark.skipif(not os.path.exists(MODEL_PATH), reason="best.pt no disponible")
class TestModeloReal:

    @pytest.fixture(autouse=True)
    def real_det(self):
        from detector import FireDetector
        self.det = FireDetector(model_path=MODEL_PATH)
        assert not self.det.simulated, "Debería cargar el modelo real"

    def test_modelo_carga_exitosamente(self):
        assert self.det.model is not None

    def test_modelo_tiene_clase_fire(self):
        names = list(self.det.model.names.values())
        from detector import _NAME_MAP
        assert any(n.lower() in _NAME_MAP for n in names), (
            f"Modelo no tiene clases reconocidas. Clases: {names}"
        )

    def test_modelo_solo_una_clase(self):
        """Documenta la limitación conocida: modelo actual solo tiene 'fire'."""
        names = list(self.det.model.names.values())
        assert len(names) == 1, (
            f"Se esperaba 1 clase ('fire') pero el modelo tiene: {names}. "
            "Si el modelo ahora soporta humo, actualizar este test."
        )

    def test_supports_smoke_es_false(self):
        assert self.det.supports_smoke is False, (
            "El modelo actual no tiene clase de humo — supports_smoke debe ser False"
        )

    def test_frame_negro_no_produce_detecciones(self):
        dets = self.det.predict(_black())
        assert dets == [], "Frame negro no debe producir detecciones con el modelo real"

    def test_inferencia_retorna_lista(self):
        frame = _fire_frame()
        dets = self.det.predict(frame)
        assert isinstance(dets, list)
        for d in dets:
            assert d.clase in ("fuego", "humo")
            assert 0.0 <= d.confianza <= 1.0
