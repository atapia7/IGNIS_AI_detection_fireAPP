"""
IgnisAI - Interfaz de configuración y actualización del modelo (HU05 - Sprint 2)
- Vista restringida a administradores (RBAC).
- Solo acepta archivos con extensión válida de YOLO (.pt / .onnx) de
  tamaño <= 150 MB.
- Al cargar exitosamente muestra: "Modelo actualizado correctamente".
"""
import os

import streamlit as st

import config
import database as db
import auth
from alerting import AlertManager
from views.dashboard import get_detector


def render():
    st.title("⚙️ Configuración del Sistema")

    flash = st.session_state.pop("smtp_flash", None)
    if flash:
        for tipo, mensaje in flash:
            getattr(st, tipo)(mensaje)

    st.subheader("Actualización del modelo de Inteligencia Artificial")
    modelo = db.modelo_activo()
    if modelo:
        st.info(f"Modelo activo: **{modelo['nombre_archivo']}** "
                f"({modelo['tamano_mb']:.1f} MB) · cargado por "
                f"{modelo['cargado_por']} el {modelo['cargado_en']}")
    else:
        st.info("No hay un modelo cargado desde la interfaz. El sistema usa "
                f"`{config.DEFAULT_MODEL_PATH}` si existe; de lo contrario, "
                "opera en modo simulación.")

    up = st.file_uploader(
        "Subir nuevo archivo de pesos YOLO (.pt / .onnx, máx. 150 MB)",
        type=[e.lstrip(".") for e in config.VALID_MODEL_EXTENSIONS],
    )
    if up is not None:
        tam_mb = up.size / (1024 * 1024)
        ext = os.path.splitext(up.name)[1].lower()
        if ext not in config.VALID_MODEL_EXTENSIONS:
            st.error("Extensión inválida: solo se aceptan archivos de pesos YOLO.")
        elif tam_mb > config.MAX_MODEL_SIZE_MB:
            st.error(f"El archivo pesa {tam_mb:.1f} MB y excede el límite "
                     f"de {config.MAX_MODEL_SIZE_MB} MB.")
        else:
            os.makedirs(config.MODELS_DIR, exist_ok=True)
            destino = os.path.join(config.MODELS_DIR, "best.pt")
            with open(destino, "wb") as f:
                f.write(up.read())
            user = auth.usuario_actual()
            db.registrar_modelo(up.name, destino, round(tam_mb, 2),
                                user["correo"] if user else "sistema")
            # Recargar el motor de detección con los nuevos pesos
            get_detector.clear()
            st.success("✅ Modelo actualizado correctamente")

    st.divider()
    st.subheader("Parámetros de detección y alertas")
    c1, c2 = st.columns(2)
    with c1:
        st.metric("Umbral de confianza (HU03)",
                  f"{config.CONFIDENCE_THRESHOLD*100:.0f}%")
        st.metric("Detección sostenida para alerta (HU06)",
                  f"{config.ALERT_SUSTAIN_SECONDS} s")
    with c2:
        st.metric("Resolución de video (HU02)",
                  f"{config.FRAME_WIDTH}x{config.FRAME_HEIGHT}")
        st.metric("FPS mínimo (HU02)", config.MIN_FPS)

    st.divider()
    st.subheader("✉️ Correo de alertas (HU06 — opcional)")

    smtp_cfg = db.get_smtp_config()

    # Estado actual
    if smtp_cfg and smtp_cfg["habilitado"] and smtp_cfg["remitente"]:
        proveedor_actual = "resend" if smtp_cfg["smtp_host"] == "resend" else "gmail"
        st.success(
            f"✅ Alertas habilitadas · {'Resend' if proveedor_actual == 'resend' else 'Gmail'} · "
            f"**{smtp_cfg['remitente']}** → {', '.join(smtp_cfg['destinatarios'])}"
        )
        st.caption(f"Última actualización: {smtp_cfg['actualizado_por']} · {smtp_cfg['actualizado_en']}")
    elif smtp_cfg and smtp_cfg["remitente"]:
        st.warning("⏸️ Configuración guardada pero **deshabilitada**.")
    else:
        st.info("Sin configurar. Las alertas se registran en la base de datos pero no se envía correo.")

    # Selector de proveedor (fuera del form para refrescar campos dinámicamente)
    proveedor_guardado = "Resend (nube)" if (smtp_cfg and smtp_cfg["smtp_host"] == "resend") else "Gmail SMTP (local)"
    proveedor = st.radio(
        "Proveedor de correo",
        ["Resend (nube)", "Gmail SMTP (local)"],
        index=0 if proveedor_guardado == "Resend (nube)" else 1,
        horizontal=True,
        help="Resend usa HTTPS — funciona en Railway y cualquier cloud. Gmail SMTP funciona en local.",
    )
    usar_resend = proveedor == "Resend (nube)"

    if usar_resend:
        st.caption(
            "Resend es un servicio de email por API (no SMTP). "
            "Crea tu cuenta gratis en [resend.com](https://resend.com) → API Keys → Create API Key. "
            "El correo remitente debe estar verificado en tu cuenta Resend."
        )
    else:
        st.caption(
            "Gmail SMTP requiere una **Contraseña de Aplicación de 16 caracteres** "
            "(no la contraseña normal). Generarla en "
            "[myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)."
        )

    with st.form("form_smtp"):
        c1, c2 = st.columns(2)
        with c1:
            remitente = st.text_input(
                "Correo remitente",
                value=(smtp_cfg["remitente"] if smtp_cfg else ""),
                placeholder="alertas@tudominio.com" if usar_resend else "alertas.ignisai@gmail.com",
            )
        with c2:
            destinatarios = st.text_input(
                "Destinatarios (separados por coma)",
                value=(", ".join(smtp_cfg["destinatarios"]) if smtp_cfg else ""),
                placeholder="guardaparques@cusco.gob.pe",
            )

        if usar_resend:
            credencial = st.text_input(
                "Resend API Key",
                type="password",
                placeholder="re_xxxxxxxxxxxxxxxxxxxxxxxxxx",
                help="Déjalo en blanco para conservar la clave ya guardada.",
            )
            smtp_host = "resend"
            smtp_port = 0
        else:
            credencial = st.text_input(
                "Contraseña de Aplicación de Google (16 caracteres)",
                type="password",
                placeholder="xxxx xxxx xxxx xxxx",
                help="Déjala en blanco para conservar la ya guardada.",
            )
            with st.expander("Opciones avanzadas del servidor SMTP"):
                a1, a2 = st.columns(2)
                with a1:
                    smtp_host = st.text_input(
                        "Servidor SMTP",
                        value=(smtp_cfg["smtp_host"] if smtp_cfg and smtp_cfg["smtp_host"] != "resend"
                               else "smtp.gmail.com"),
                    )
                with a2:
                    smtp_port = st.number_input(
                        "Puerto",
                        value=int(smtp_cfg["smtp_port"] if smtp_cfg and smtp_cfg["smtp_host"] != "resend"
                                  else 587),
                        min_value=1, max_value=65535, step=1,
                    )

        if smtp_cfg and smtp_cfg["remitente"]:
            st.caption("🔒 Credencial ya guardada. Completa el campo solo si quieres reemplazarla.")

        habilitado = st.checkbox(
            "Habilitar el envío automático de alertas por correo",
            value=bool(smtp_cfg and smtp_cfg["habilitado"]),
        )

        bc1, bc2 = st.columns(2)
        with bc1:
            guardar = st.form_submit_button("💾 Guardar configuración", use_container_width=True)
        with bc2:
            guardar_y_probar = st.form_submit_button(
                "💾📨 Guardar y enviar correo de prueba", use_container_width=True)

    if guardar or guardar_y_probar:
        try:
            if credencial.strip():
                password_a_guardar = credencial.strip()
            elif smtp_cfg and smtp_cfg["remitente"]:
                actual = db.get_smtp_config(incluir_password=True)
                password_a_guardar = actual["app_password"]
                if not password_a_guardar:
                    raise ValueError("No hay credencial guardada. Ingrésala nuevamente.")
            else:
                raise ValueError("Debes ingresar la credencial la primera vez que configuras el correo.")

            db.guardar_smtp_config(
                remitente=remitente,
                app_password=password_a_guardar,
                destinatarios_texto=destinatarios,
                habilitado=habilitado,
                actualizado_por=(auth.usuario_actual() or {}).get("correo", "sistema"),
                smtp_host=smtp_host,
                smtp_port=int(smtp_port),
            )
            mensajes = [("success", "✅ Configuración de correo guardada correctamente.")]
            if guardar_y_probar:
                with st.spinner("Enviando correo de prueba…"):
                    ok, mensaje = AlertManager.enviar_correo_prueba()
                mensajes.append(("success" if ok else "error", mensaje))
            st.session_state["smtp_flash"] = mensajes
            st.rerun()
        except ValueError as e:
            st.error(f"⚠️ {e}")

    if smtp_cfg and smtp_cfg["remitente"]:
        pc1, pc2 = st.columns(2)
        with pc1:
            if st.button("📨 Enviar correo de prueba", use_container_width=True):
                with st.spinner("Enviando correo de prueba…"):
                    ok, mensaje = AlertManager.enviar_correo_prueba()
                st.session_state["smtp_flash"] = [("success" if ok else "error", mensaje)]
                st.rerun()
        with pc2:
            if st.button("🗑️ Eliminar configuración de correo", use_container_width=True):
                db.limpiar_smtp_config((auth.usuario_actual() or {}).get("correo", "sistema"))
                st.session_state["smtp_flash"] = [("success", "Configuración de correo eliminada.")]
                st.rerun()

    st.divider()
    st.subheader("Log del sistema (HU01)")
    if os.path.exists(config.LOG_FILE):
        with open(config.LOG_FILE, encoding="utf-8") as f:
            lineas = f.readlines()[-20:]
        st.code("".join(lineas) or "Log vacío.", language="text")
    else:
        st.caption("Aún no se ha generado el archivo de log.")
