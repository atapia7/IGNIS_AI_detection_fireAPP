"""
IgnisAI - Dashboard Centralizado de Monitoreo
Cubre: HU02 (video en vivo), HU03 (recuadros), HU06 (disparo de alerta),
HU07/HU09 (dashboard con últimas 10 detecciones), HU08 (clasificación
de veracidad), HU08/HU09 (métricas de confianza).
"""
import os
import time

import cv2
import streamlit as st

import config
import database as db
from detector import FireDetector
from alerting import AlertManager


@st.cache_resource
def get_detector():
    return FireDetector()


@st.cache_resource
def get_alert_manager():
    return AlertManager()


def _panel_alertas():
    """Panel lateral: últimas 10 detecciones, más recientes primero (HU07/HU09)."""
    st.subheader("🚨 Últimas detecciones")
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
                # HU07/HU08: botones de acción rápida; desaparecen al clasificar
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
        ruta = alert_mgr.guardar_fotograma(frame)
        enviado = alert_mgr.enviar_correo(ruta, mejor.clase, mejor.confianza)
        db.registrar_alerta(mejor.clase, mejor.confianza, ruta, enviado)
        st.toast(f"🚨 Alerta registrada: {mejor.clase.upper()} "
                 f"({mejor.confianza*100:.0f}%)")
    return frame, detections


def render():
    st.title("📹 Dashboard Centralizado de Monitoreo")
    detector = get_detector()
    alert_mgr = get_alert_manager()

    if detector.simulated:
        st.warning("Motor en **modo simulación** (sin pesos YOLOv8 entrenados). "
                   "Cargue `models/best.pt` o súbalo desde Configuración para "
                   "activar la inferencia con CNN.")

    # Bloque central (video) + panel lateral (historial) — HU07/HU09
    col_video, col_alertas = st.columns([3, 1.4])

    with col_alertas:
        _panel_alertas()

    with col_video:
        fuente = st.radio("Fuente de video",
                          ["Cámara USB", "Archivo de video", "Imagen de prueba"],
                          horizontal=True)

        if fuente == "Cámara USB":
            iniciar = st.toggle("Iniciar monitoreo en vivo", value=False)
            placeholder = st.empty()
            fps_info = st.empty()
            if iniciar:
                cap = cv2.VideoCapture(config.CAMERA_INDEX)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
                if not cap.isOpened():
                    st.error("No se pudo abrir la cámara USB (índice "
                             f"{config.CAMERA_INDEX}). Verifique la conexión.")
                else:
                    t_prev = time.time()
                    while st.session_state.get("vista") == "dashboard":
                        ok, frame = cap.read()
                        if not ok:
                            st.error("Se perdió el flujo de video.")
                            break
                        frame = cv2.resize(frame,
                                           (config.FRAME_WIDTH, config.FRAME_HEIGHT))
                        frame, _ = _procesar_frame(frame, detector, alert_mgr)
                        # HU02: FPS estable >= 15
                        t_now = time.time()
                        fps = 1.0 / max(t_now - t_prev, 1e-6)
                        t_prev = t_now
                        placeholder.image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                                          channels="RGB", use_container_width=True)
                        fps_info.caption(f"FPS: {fps:.1f} · Resolución: "
                                         f"{config.FRAME_WIDTH}x{config.FRAME_HEIGHT}")
                    cap.release()

        elif fuente == "Archivo de video":
            up = st.file_uploader("Suba un video (mp4/avi)", type=["mp4", "avi", "mov"])
            if up:
                tmp = os.path.join(config.BASE_DIR, "assets", "tmp_video.mp4")
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

        else:  # Imagen de prueba (validación HU01: <= 15 s por imagen)
            up = st.file_uploader("Suba una imagen (jpg/png)", type=["jpg", "jpeg", "png"])
            if up:
                import numpy as np
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
