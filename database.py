"""
IgnisAI - Capa de Almacenamiento y Lógica (SQLite)
Sprints 2, 3 y 4: usuarios/roles, alertas, clasificación de veracidad,
registro histórico y reportería.
"""
import re
import sqlite3
import hashlib
import secrets
from datetime import datetime
from contextlib import contextmanager

import config


@contextmanager
def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Crea las tablas y el usuario administrador por defecto."""
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                correo TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                rol TEXT NOT NULL CHECK (rol IN ('Administrador','Operador','Gestor')),
                creado_en TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alertas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,          -- YYYY-MM-DD
                hora TEXT NOT NULL,           -- HH:MM:SS
                clase TEXT NOT NULL,          -- fuego | humo
                confianza REAL NOT NULL,      -- % máximo alcanzado (HU08/HU09)
                imagen_path TEXT,             -- fotograma capturado
                estado TEXT NOT NULL DEFAULT 'Pendiente'
                    CHECK (estado IN ('Pendiente','Incendio Confirmado','Falsa Alarma')),
                correo_enviado INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS modelos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_archivo TEXT NOT NULL,
                ruta TEXT NOT NULL,
                tamano_mb REAL NOT NULL,
                cargado_por TEXT NOT NULL,
                cargado_en TEXT NOT NULL,
                activo INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS smtp_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),   -- fila única (config global)
                habilitado INTEGER NOT NULL DEFAULT 0,
                smtp_host TEXT NOT NULL DEFAULT 'smtp.gmail.com',
                smtp_port INTEGER NOT NULL DEFAULT 587,
                remitente TEXT NOT NULL DEFAULT '',
                app_password_cifrada TEXT NOT NULL DEFAULT '',
                destinatarios TEXT NOT NULL DEFAULT '',   -- separados por coma
                actualizado_por TEXT,
                actualizado_en TEXT
            );
            """
        )
        # Usuario administrador semilla (cambiar contraseña en producción)
        cur = conn.execute("SELECT COUNT(*) c FROM usuarios")
        if cur.fetchone()["c"] == 0:
            crear_usuario_conn(conn, "Administrador General",
                               "admin", "admin123", "Administrador")

        # Fila única de configuración SMTP (si aún no existe)
        conn.execute("INSERT OR IGNORE INTO smtp_config (id) VALUES (1)")


# ---------------------------------------------------------------
# HU04 - Gestión de Múltiples Usuarios y Roles (Sprint 2)
# ---------------------------------------------------------------
def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()


def crear_usuario_conn(conn, nombre, correo, password, rol):
    salt = secrets.token_hex(16)
    conn.execute(
        "INSERT INTO usuarios (nombre, correo, password_hash, salt, rol, creado_en) "
        "VALUES (?,?,?,?,?,?)",
        (nombre, correo.lower().strip(), _hash_password(password, salt), salt, rol,
         datetime.now().isoformat(timespec="seconds")),
    )


def crear_usuario(nombre, correo, password, rol):
    if rol not in config.ROLES:
        raise ValueError("Rol inválido")
    with get_conn() as conn:
        crear_usuario_conn(conn, nombre, correo, password, rol)


def editar_usuario(user_id, nombre, correo, rol, password=None):
    with get_conn() as conn:
        if password:
            salt = secrets.token_hex(16)
            conn.execute(
                "UPDATE usuarios SET nombre=?, correo=?, rol=?, password_hash=?, salt=? WHERE id=?",
                (nombre, correo.lower().strip(), rol,
                 _hash_password(password, salt), salt, user_id),
            )
        else:
            conn.execute("UPDATE usuarios SET nombre=?, correo=?, rol=? WHERE id=?",
                         (nombre, correo.lower().strip(), rol, user_id))


def eliminar_usuario(user_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM usuarios WHERE id=?", (user_id,))


def listar_usuarios():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, nombre, correo, rol, creado_en FROM usuarios ORDER BY id")]


def autenticar(correo, password):
    """Devuelve el usuario si las credenciales son válidas; None en caso contrario."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM usuarios WHERE correo=?",
                           (correo.lower().strip(),)).fetchone()
    if row and _hash_password(password, row["salt"]) == row["password_hash"]:
        return {"id": row["id"], "nombre": row["nombre"],
                "correo": row["correo"], "rol": row["rol"]}
    return None


# ---------------------------------------------------------------
# Alertas: HU06 (registro), HU07/HU08 (veracidad), HU09 (confianza)
# ---------------------------------------------------------------
def registrar_alerta(clase, confianza, imagen_path=None, correo_enviado=False):
    now = datetime.now()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO alertas (fecha, hora, clase, confianza, imagen_path, correo_enviado) "
            "VALUES (?,?,?,?,?,?)",
            (now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"),
             clase, round(confianza * 100, 2), imagen_path, int(correo_enviado)),
        )
        return cur.lastrowid


def ultimas_alertas(n=10):
    """HU09/HU07 dashboard: últimas N detecciones, más recientes primero."""
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM alertas ORDER BY id DESC LIMIT ?", (n,))]


def clasificar_alerta(alerta_id, estado):
    """HU07/HU08: 'Incendio Confirmado' o 'Falsa Alarma'. Actualización inmediata."""
    if estado not in ("Incendio Confirmado", "Falsa Alarma"):
        raise ValueError("Estado inválido")
    with get_conn() as conn:
        conn.execute("UPDATE alertas SET estado=? WHERE id=?", (estado, alerta_id))


# ---------------------------------------------------------------
# HU10 / HU11 / HU12 - Registro histórico, reportería y exportación
# ---------------------------------------------------------------
def alertas_filtradas(fecha_inicio=None, fecha_fin=None):
    q = "SELECT id AS 'ID Alerta', fecha AS Fecha, hora AS Hora, clase AS Clase, " \
        "confianza AS '% Confianza', estado AS 'Estado de Veracidad' FROM alertas WHERE 1=1"
    params = []
    if fecha_inicio:
        q += " AND fecha >= ?"
        params.append(str(fecha_inicio))
    if fecha_fin:
        q += " AND fecha <= ?"
        params.append(str(fecha_fin))
    q += " ORDER BY id DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(q, params)]


def resumen_efectividad(mes: str = None):
    """HU11: conteo de confirmadas vs falsas alarmas (por defecto, mes en curso)."""
    mes = mes or datetime.now().strftime("%Y-%m")
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT estado, COUNT(*) c FROM alertas "
            "WHERE substr(fecha,1,7)=? GROUP BY estado", (mes,)).fetchall()
    resumen = {"Incendio Confirmado": 0, "Falsa Alarma": 0, "Pendiente": 0}
    for r in rows:
        resumen[r["estado"]] = r["c"]
    return resumen


# ---------------------------------------------------------------
# HU05 - Registro de modelos cargados
# ---------------------------------------------------------------
def registrar_modelo(nombre_archivo, ruta, tamano_mb, cargado_por):
    with get_conn() as conn:
        conn.execute("UPDATE modelos SET activo=0")
        conn.execute(
            "INSERT INTO modelos (nombre_archivo, ruta, tamano_mb, cargado_por, cargado_en) "
            "VALUES (?,?,?,?,?)",
            (nombre_archivo, ruta, tamano_mb, cargado_por,
             datetime.now().isoformat(timespec="seconds")),
        )


def modelo_activo():
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM modelos WHERE activo=1 ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------
# HU06 (opcional) - Configuración del correo de alertas desde la web
# ---------------------------------------------------------------
_CORREO_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validar_app_password(app_password: str) -> str:
    """
    Valida la Contraseña de Aplicación de Google: 16 caracteres alfanuméricos.
    Acepta el formato con espacios que muestra Google ('abcd efgh ijkl mnop')
    y lo normaliza. Devuelve la cadena de 16 caracteres sin espacios, o
    lanza ValueError con el mensaje a mostrar en la interfaz.
    """
    limpia = app_password.replace(" ", "").strip()
    if len(limpia) != 16:
        raise ValueError(
            f"La Contraseña de Aplicación debe tener 16 caracteres (se recibieron {len(limpia)}). "
            "Cópiela tal como la muestra Google en myaccount.google.com/apppasswords.")
    if not limpia.isalnum():
        raise ValueError("La Contraseña de Aplicación solo debe contener letras y números.")
    return limpia


def validar_destinatarios(texto: str) -> list:
    """Valida una lista de correos separados por coma. Devuelve la lista limpia."""
    correos = [c.strip().lower() for c in texto.split(",") if c.strip()]
    if not correos:
        raise ValueError("Debe indicar al menos un correo destinatario de las alertas.")
    invalidos = [c for c in correos if not _CORREO_RE.match(c)]
    if invalidos:
        raise ValueError(f"Correo(s) con formato inválido: {', '.join(invalidos)}")
    return correos


def guardar_smtp_config(remitente, app_password, destinatarios_texto,
                         habilitado, actualizado_por,
                         smtp_host="smtp.gmail.com", smtp_port=587):
    """
    Guarda la configuración del correo de alertas (HU06), cifrando la
    Contraseña de Aplicación antes de persistirla. Lanza ValueError si
    algún campo no pasa las validaciones.
    """
    remitente = remitente.strip().lower()
    if not _CORREO_RE.match(remitente):
        raise ValueError("El correo remitente no tiene un formato válido.")
    if smtp_host == "resend":
        app_password_ok = app_password.strip()
        if not app_password_ok:
            raise ValueError("Debes ingresar la Resend API Key.")
    else:
        app_password_ok = validar_app_password(app_password)
    destinatarios = validar_destinatarios(destinatarios_texto)

    with get_conn() as conn:
        conn.execute(
            "UPDATE smtp_config SET habilitado=?, smtp_host=?, smtp_port=?, "
            "remitente=?, app_password_cifrada=?, destinatarios=?, "
            "actualizado_por=?, actualizado_en=? WHERE id=1",
            (int(habilitado), smtp_host, int(smtp_port), remitente, app_password_ok,
             ",".join(destinatarios), actualizado_por,
             datetime.now().isoformat(timespec="seconds")),
        )


def get_smtp_config(incluir_password=False):
    """
    Devuelve la configuración SMTP vigente como diccionario:
    {habilitado, smtp_host, smtp_port, remitente, destinatarios (list),
     actualizado_por, actualizado_en, [app_password]}.
    La contraseña descifrada solo se incluye si `incluir_password=True`
    (uso interno de `alerting.py`); la interfaz web nunca la solicita.
    """
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM smtp_config WHERE id=1").fetchone()
    if row is None:
        return None
    data = dict(row)
    data["destinatarios"] = [d for d in data["destinatarios"].split(",") if d]
    data["habilitado"] = bool(data["habilitado"])
    if incluir_password:
        data["app_password"] = data["app_password_cifrada"]
    data.pop("app_password_cifrada", None)
    return data


def limpiar_smtp_config(actualizado_por):
    """Elimina la configuración de correo (deshabilita y borra credenciales)."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE smtp_config SET habilitado=0, remitente='', "
            "app_password_cifrada='', destinatarios='', "
            "actualizado_por=?, actualizado_en=? WHERE id=1",
            (actualizado_por, datetime.now().isoformat(timespec="seconds")),
        )
