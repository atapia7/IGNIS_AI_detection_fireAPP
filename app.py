"""
IgnisAI - Sistema de Detección Temprana de Incendios Forestales
Punto de entrada de la aplicación (Streamlit).

Ejecutar:  streamlit run app.py
Usuario inicial:  admin@ignisai.pe / admin123
"""
import streamlit as st

import database as db
import auth

st.set_page_config(
    page_title="IgnisAI - Detección Temprana de Incendios",
    page_icon="🔥",
    layout="wide",
)

db.init_db()

# ---------------------------------------------------------------
# Autenticación (HU04)
# ---------------------------------------------------------------
if auth.usuario_actual() is None:
    auth.login_form()
    st.stop()

user = auth.usuario_actual()

# ---------------------------------------------------------------
# Navegación lateral con RBAC
# ---------------------------------------------------------------
VISTAS = {
    "dashboard": ("📹 Dashboard de Monitoreo", "views.dashboard"),
    "historial": ("🗂️ Registro Histórico", "views.historial"),
    "reportes": ("📊 Reportes de Efectividad", "views.reportes"),
    "usuarios": ("👥 Gestión de Usuarios", "views.usuarios"),
    "configuracion": ("⚙️ Configuración", "views.configuracion"),
}

permitidas = [k for k in VISTAS if k in auth.PERMISOS[user["rol"]]]
st.session_state.setdefault("vista", "dashboard")

with st.sidebar:
    st.markdown("## 🔥 IgnisAI")
    st.caption(f"Sesión: **{user['nombre']}**  \nRol: `{user['rol']}`")
    st.divider()
    for clave in permitidas:
        etiqueta, _ = VISTAS[clave]
        if st.button(etiqueta, use_container_width=True,
                     type="primary" if st.session_state["vista"] == clave else "secondary"):
            st.session_state["vista"] = clave
            st.rerun()
    st.divider()
    if st.button("🚪 Cerrar sesión", use_container_width=True):
        auth.logout()

# ---------------------------------------------------------------
# Render de la vista activa (con verificación RBAC - HU04)
# ---------------------------------------------------------------
vista = st.session_state["vista"]
if vista not in permitidas:
    # Bloqueo y redirección para roles no autorizados
    st.session_state["vista"] = "dashboard"
    vista = "dashboard"

import importlib

modulo = importlib.import_module(VISTAS[vista][1])
modulo.render()
