"""
IgnisAI - Dashboard Centralizado de Monitoreo
Cubre: HU02 (video en vivo), HU03 (recuadros), HU06 (disparo de alerta),
HU07/HU09 (dashboard con últimas 10 detecciones), HU08 (clasificación
de veracidad), HU08/HU09 (métricas de confianza).

Captura de cámara vía WebRTC (streamlit-webrtc): permite usar la cámara
del celular, laptop o PC directamente desde el navegador, sin necesidad
de cámara física en el servidor.
"""
import os
import threading
import time

import av
import cv2
import requests
import streamlit as st
from streamlit_webrtc import VideoProcessorBase, RTCConfiguration, webrtc_streamer

import config
import database as db
from alerting import AlertManager
from detector import FireDetector


def _build_rtc_config() -> RTCConfiguration:
    """
    Construye la configuración ICE con TURN para que WebRTC funcione
    detrás del NAT de Railway. Prioriza credenciales Metered si están
    disponibles vía METERED_API_KEY; de lo contrario usa Open Relay
    (servidores TURN públicos gratuitos de Metered).
    """
    api_key = os.environ.get("METERED_API_KEY", "").strip()
    domain  = os.environ.get("METERED_DOMAIN", "").strip()
    if api_key and domain:
        try:
            resp = requests.get(
                f"https://{domain}/api/v1/turn/credentials?apiKey={api_key}",
                timeout=5,
            )
            if resp.ok:
                return RTCConfiguration({"iceServers": resp.json()})
        except Exception:
            pass

    # Open Relay — servidores TURN públicos gratuitos mantenidos por Metered.ca
    return RTCConfiguration({
        "iceServers": [
            {"urls": ["stun:stun.l.google.com:19302"]},
            {
                "urls": [
                    "turn:openrelay.metered.ca:80",
                    "turn:openrelay.metered.ca:443",
                    "turn:openrelay.metered.ca:443?transport=tcp",
                    "turn:openrelay.metered.ca:80?transport=tcp",
                ],
                "username": "openrelayproject",
                "credential": "openrelayproject",
            },
        ]
    })


@st.cache_resource
def _rtc_config() -> RTCConfiguration:
    return _build_rtc_config()


@st.cache_resource
def get_detector():
    return FireDetector()


class FireVideoProcessor(VideoProcessorBase):
    """
    Procesador de video WebRTC: recibe cada fotograma del navegador del
    cliente, ejecuta inferencia y devuelve el frame anotado.
    Corre en hilo propio — no puede llamar a st.* directamente.
    """

    def __init__(self):
        self._detector = get_detector()
        self._alert_mgr = AlertManager()
        self._lock = threading.Lock()

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        detections = self._detector.predict(img)
        img = self._detector.draw(img, detections)

        with self._lock:
            if self._alert_mgr.update(bool(detections)) and detections:
                mejor = max(detections, key=lambda d: d.confianza)
                ruta = AlertManager.guardar_fotograma(img)
                enviado = AlertManager.enviar_correo(ruta, mejor.clase, mejor.confianza)
                db.registrar_alerta(mejor.clase, mejor.confianza, ruta, enviado)

        return av.VideoFrame.from_ndarray(img, format="bgr24")


def _panel_alertas():
    """Panel lateral: últimas 10 detecciones, más recientes primero (HU07/HU09)."""
    col_titulo, col_refresh = st.columns([3, 1])
    with col_titulo:
        st.subheader("🚨 Últimas detecciones")
    with col_refresh:
        if st.button("↻", help="Actualizar panel de alertas"):
            st.rerun()

    alertas = db.ultimas_alertas(config.DASHBOARD_LAST_ALERTS)
    if not alertas:
        st.info("Sin detecciones registradas.")
        return

    for a in alertas:
        with st.container(border=True):
            c1, c2 = st.columns([3, 2])
            with c1:
                st.markdown(
                    f"**#{a['id']} · {a['clase'].upper()}**  \n"
                    f"{a['fecha']} {a['hora']}  \n"
                    f"Confianza: **{a['confianza']:.1f}%**"
                )
            with c2:
                if a["estado"] == "Pendiente":
                    if st.button("✅ Confirmar", key=f"conf_{a['id']}",
                                 use_container_width=True):
                        db.clasificar_alerta(a["id"], "Incendio Confirmado")
                        st.rerun()
                    if st.button("❌ Falsa Alarma", key=f"falsa_{a['id']}",
                                 use_container_width=True):
                        db.clasificar_alerta(a["id"], "Falsa Alarma")
                        st.rerun()
                else:
                    icono = "🔥" if a["estado"] == "Incendio Confirmado" else "🟢"
                    st.markdown(f"{icono} **{a['estado']}**")


def _procesar_frame(frame, detector, alert_mgr):
    """Ejecuta inferencia, dibuja recuadros y gestiona alertas sostenidas."""
    detections = detector.predict(frame)
    frame = detector.draw(frame, detections)

    if alert_mgr.update(bool(detections)):
        mejor = max(detections, key=lambda d: d.confianza)
        ruta = AlertManager.guardar_fotograma(frame)
        enviado = AlertManager.enviar_correo(ruta, mejor.clase, mejor.confianza)
        db.registrar_alerta(mejor.clase, mejor.confianza, ruta, enviado)
        st.toast(f"🚨 Alerta registrada: {mejor.clase.upper()} "
                 f"({mejor.confianza*100:.0f}%)")
    return frame, detections


def render():
    st.title("📹 Dashboard Centralizado de Monitoreo")
    # Si el cache tiene una instancia de una versión anterior de FireDetector
    # (sin el atributo supports_smoke), lo limpiamos para recrearla.
    if not hasattr(get_detector(), "supports_smoke"):
        get_detector.clear()
    detector = get_detector()

    if detector.simulated:
        st.warning("Motor en **modo simulación** (sin pesos YOLOv8 entrenados). "
                   "Cargue `models/best.pt` o súbalo desde Configuración para "
                   "activar la inferencia con CNN.")
    elif not getattr(detector, "supports_smoke", False):
        st.info("ℹ️ El modelo cargado detecta **solo fuego** (clase 'fire'). "
                "Para detección de humo se requiere un modelo entrenado con esa clase.")

    col_video, col_alertas = st.columns([3, 1.4])

    with col_alertas:
        _panel_alertas()

    with col_video:
        fuente = st.radio("Fuente de video",
                          ["Cámara del dispositivo", "Archivo de video", "Imagen de prueba"],
                          horizontal=True)

        # ------------------------------------------------------------------ #
        # HU02 — Cámara en vivo vía WebRTC                                   #
        # Captura el video desde el navegador del cliente (celular, laptop,  #
        # PC) y lo procesa en el servidor con YOLOv8 / modo simulación.      #
        # ------------------------------------------------------------------ #
        if fuente == "Cámara del dispositivo":
            st.info(
                "Permite el acceso a la cámara cuando el navegador lo solicite. "
                "Funciona con la cámara del celular, laptop o una cámara USB "
                "conectada al equipo desde el que accedes.",
                icon="📷",
            )
            ctx = webrtc_streamer(
                key="ignisai-fire-detection",
                video_processor_factory=FireVideoProcessor,
                rtc_configuration=_rtc_config(),
                media_stream_constraints={"video": True, "audio": False},
                async_processing=True,
            )
            if ctx.state.playing:
                st.success("Monitoreo activo — las alertas se registran automáticamente. "
                           "Pulsa **↻** en el panel lateral para actualizar las detecciones.")

        # ------------------------------------------------------------------ #
        # Archivo de video                                                    #
        # ------------------------------------------------------------------ #
        elif fuente == "Archivo de video":
            alert_mgr = AlertManager()
            up = st.file_uploader("Suba un video (mp4/avi)", type=["mp4", "avi", "mov"])
            if up:
                tmp = os.path.join(config.BASE_DIR, "assets", "tmp_video.mp4")
                os.makedirs(os.path.dirname(tmp), exist_ok=True)
                with open(tmp, "wb") as f:
                    f.write(up.read())
                if st.button("▶ Procesar video"):
                    cap = cv2.VideoCapture(tmp)
                    placeholder = st.empty()
                    while cap.isOpened():
                        ok, frame = cap.read()
                        if not ok:
                            break
                        frame = cv2.resize(frame,
                                           (config.FRAME_WIDTH, config.FRAME_HEIGHT))
                        frame, _ = _procesar_frame(frame, detector, alert_mgr)
                        placeholder.image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                                          channels="RGB", use_container_width=True)
                    cap.release()
                    st.success("Procesamiento del video finalizado.")

        # ------------------------------------------------------------------ #
        # Imagen de prueba (HU01: inferencia ≤ 15 s)                         #
        # ------------------------------------------------------------------ #
        else:
            import numpy as np
            up = st.file_uploader("Suba una imagen (jpg/png)", type=["jpg", "jpeg", "png"])
            if up:
                data = np.frombuffer(up.read(), np.uint8)
                frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
                t0 = time.time()
                detections = detector.predict(frame)
                frame = detector.draw(frame, detections)
                dur = time.time() - t0
                st.image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                         channels="RGB", use_container_width=True)
                st.caption(f"Tiempo de inferencia: {dur:.2f} s "
                           f"(criterio HU01: ≤ 15 s) · "
                           f"Detecciones: {len(detections)}")
                if detections and st.button("Registrar como alerta"):
                    mejor = max(detections, key=lambda d: d.confianza)
                    ruta = AlertManager.guardar_fotograma(frame)
                    db.registrar_alerta(mejor.clase, mejor.confianza, ruta, False)
                    st.success("Alerta registrada en el historial.")
                    st.rerun()
