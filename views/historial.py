"""
IgnisAI - Registro histórico y exportación (Sprint 4)
HU10: tabla paginada con ID, Fecha, Hora, % Confianza y Estado, con
      filtros dinámicos por rango de fechas (Fecha Inicio / Fecha Fin).
HU12: exportación a CSV de los registros filtrados con nombre
      autogenerado (reporte_ignisai_DDMMYYYY.csv).
"""
from datetime import date, datetime

import pandas as pd
import streamlit as st

import config
import database as db


def render():
    st.title("🗂️ Registro Histórico de Alertas")

    # HU10: selectores de calendario para filtrado dinámico
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        fecha_inicio = st.date_input("Fecha Inicio", value=None, key="hist_ini")
    with c2:
        fecha_fin = st.date_input("Fecha Fin", value=None, key="hist_fin")

    registros = db.alertas_filtradas(fecha_inicio, fecha_fin)
    df = pd.DataFrame(registros)

    if df.empty:
        st.info("No existen registros de alertas para el rango seleccionado.")
        return

    # HU12: botón Exportar a CSV con los registros filtrados
    nombre_csv = datetime.now().strftime("reporte_ignisai_%d%m%Y.csv")
    with c3:
        st.write("")
        st.download_button(
            "⬇️ Exportar a CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name=nombre_csv,
            mime="text/csv",
            use_container_width=True,
        )

    # HU10: tabla paginada
    total = len(df)
    paginas = max(1, -(-total // config.HISTORY_PAGE_SIZE))
    pag = st.number_input("Página", min_value=1, max_value=paginas, value=1)
    ini = (pag - 1) * config.HISTORY_PAGE_SIZE
    st.dataframe(df.iloc[ini: ini + config.HISTORY_PAGE_SIZE],
                 use_container_width=True, hide_index=True)
    st.caption(f"{total} registros · Página {pag} de {paginas} · "
               f"Archivo de exportación: {nombre_csv}")
