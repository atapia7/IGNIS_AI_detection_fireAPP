"""
IgnisAI - Gestión de Múltiples Usuarios y Roles (HU04 - Sprint 2)
Formulario CRUD exclusivo del rol Administrador con campos obligatorios:
Nombre, Correo, Contraseña y Rol (Operador, Gestor, Administrador).
"""
import streamlit as st

import config
import database as db
import auth


def render():
    st.title("👥 Gestión de Usuarios y Roles")

    tab_crear, tab_gestionar = st.tabs(["➕ Registrar usuario", "✏️ Editar / Eliminar"])

    with tab_crear:
        with st.form("crear_usuario", clear_on_submit=True):
            nombre = st.text_input("Nombre *")
            correo = st.text_input("Correo *")
            password = st.text_input("Contraseña *", type="password")
            rol = st.selectbox("Rol *", config.ROLES)
            ok = st.form_submit_button("Registrar", use_container_width=True)
        if ok:
            if not (nombre and correo and password):
                st.error("Todos los campos (Nombre, Correo, Contraseña y Rol) "
                         "son obligatorios.")
            else:
                try:
                    db.crear_usuario(nombre, correo, password, rol)
                    st.success(f"Usuario '{nombre}' registrado con rol {rol}.")
                except Exception:
                    st.error("El correo ya se encuentra registrado.")

    with tab_gestionar:
        usuarios = db.listar_usuarios()
        if not usuarios:
            st.info("No hay usuarios registrados.")
            return
        st.dataframe(usuarios, use_container_width=True, hide_index=True)

        opciones = {f"#{u['id']} · {u['nombre']} ({u['rol']})": u for u in usuarios}
        sel = st.selectbox("Seleccione un usuario", list(opciones))
        u = opciones[sel]

        with st.form("editar_usuario"):
            nombre = st.text_input("Nombre", value=u["nombre"])
            correo = st.text_input("Correo", value=u["correo"])
            rol = st.selectbox("Rol", config.ROLES,
                               index=config.ROLES.index(u["rol"]))
            password = st.text_input("Nueva contraseña (opcional)", type="password")
            c1, c2 = st.columns(2)
            editar = c1.form_submit_button("💾 Guardar cambios",
                                           use_container_width=True)
            eliminar = c2.form_submit_button("🗑️ Eliminar usuario",
                                             use_container_width=True)
        if editar:
            db.editar_usuario(u["id"], nombre, correo, rol, password or None)
            st.success("Usuario actualizado.")
            st.rerun()
        if eliminar:
            actual = auth.usuario_actual()
            if actual and actual["id"] == u["id"]:
                st.error("No puede eliminar su propia cuenta activa.")
            else:
                db.eliminar_usuario(u["id"])
                st.success("Usuario eliminado.")
                st.rerun()
