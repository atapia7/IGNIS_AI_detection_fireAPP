"""
IgnisAI - Autenticación y RBAC (HU04 - Sprint 2)
Control de Acceso Basado en Roles: Administrador, Operador, Gestor.
Bloquea y redirige a usuarios sin permisos que intenten acceder a
vistas restringidas.
"""
import streamlit as st

import database as db

# Vistas permitidas por rol (RBAC)
PERMISOS = {
    "Administrador": {"dashboard", "historial", "reportes", "usuarios", "configuracion"},
    "Operador":      {"dashboard", "historial"},
    "Gestor":        {"dashboard", "historial", "reportes"},
}


def usuario_actual():
    return st.session_state.get("usuario")


def login_form():
    """Pantalla de inicio de sesión de IgnisAI."""
    st.markdown(
        "<h1 style='text-align:center'>🔥 IgnisAI</h1>"
        "<p style='text-align:center'>Sistema de Detección Temprana de "
        "Incendios Forestales — Región Cusco, Perú</p>",
        unsafe_allow_html=True,
    )
    with st.form("login"):
        correo = st.text_input("Correo electrónico")
        password = st.text_input("Contraseña", type="password")
        enviado = st.form_submit_button("Iniciar sesión", use_container_width=True)
    if enviado:
        user = db.autenticar(correo, password)
        if user:
            st.session_state["usuario"] = user
            st.rerun()
        else:
            st.error("Credenciales inválidas. Verifique su correo y contraseña.")
    st.caption("Usuario inicial: admin@ignisai.pe / admin123 (cámbielo tras el primer acceso)")


def requiere_rol(vista: str) -> bool:
    """
    HU04: si el rol del usuario no tiene permiso sobre la vista,
    se bloquea el acceso y se redirige al dashboard.
    """
    user = usuario_actual()
    if user is None:
        return False
    if vista not in PERMISOS.get(user["rol"], set()):
        st.error("⛔ Acceso restringido: su rol no tiene permisos para esta sección. "
                 "Redirigiendo al panel principal…")
        st.session_state["vista"] = "dashboard"
        st.rerun()
        return False
    return True


def logout():
    st.session_state.pop("usuario", None)
    st.session_state.pop("vista", None)
    st.rerun()
