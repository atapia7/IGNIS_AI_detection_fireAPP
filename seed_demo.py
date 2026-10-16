"""Genera datos de demostración para presentar los Sprints 3 y 4."""
import random
from datetime import datetime, timedelta
import database as db

db.init_db()
estados = ["Incendio Confirmado", "Falsa Alarma", "Pendiente"]
base = datetime.now()
with db.get_conn() as conn:
    for i in range(25):
        dt = base - timedelta(days=random.randint(0, 20),
                              hours=random.randint(0, 23))
        conn.execute(
            "INSERT INTO alertas (fecha, hora, clase, confianza, estado, correo_enviado) "
            "VALUES (?,?,?,?,?,1)",
            (dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S"),
             random.choice(["fuego", "humo"]),
             round(random.uniform(52, 98), 2),
             random.choices(estados, weights=[5, 2, 2])[0]),
        )
print("25 alertas de demostración insertadas.")
