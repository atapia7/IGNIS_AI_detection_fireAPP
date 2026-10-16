"""
IgnisAI - Reporte de efectividad y precisión (HU11 - Sprint 4)
Gráfico automático (circular y barras) que separa alertas confirmadas
de falsas alarmas, consultando la base de datos del mes en curso, con
etiquetas numéricas por categoría.
"""
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

import database as db


def render():
    st.title("📊 Reporte de Efectividad y Precisión")

    mes_actual = datetime.now().strftime("%Y-%m")
    mes = st.text_input("Mes a evaluar (YYYY-MM)", value=mes_actual)

    resumen = db.resumen_efectividad(mes)
    confirmadas = resumen["Incendio Confirmado"]
    falsas = resumen["Falsa Alarma"]
    pendientes = resumen["Pendiente"]
    clasificadas = confirmadas + falsas

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔥 Incendios confirmados", confirmadas)
    c2.metric("🟢 Falsas alarmas", falsas)
    c3.metric("⏳ Pendientes", pendientes)
    precision = (confirmadas / clasificadas * 100) if clasificadas else 0.0
    c4.metric("🎯 Precisión operativa", f"{precision:.1f}%",
              help="Aciertos frente al total de alertas ya clasificadas")

    if clasificadas == 0:
        st.info("Aún no hay alertas clasificadas en el periodo seleccionado. "
                "Clasifique las detecciones desde el Dashboard.")
        return

    df = pd.DataFrame({
        "Categoría": ["Incendio Confirmado", "Falsa Alarma"],
        "Cantidad": [confirmadas, falsas],
    })

    g1, g2 = st.columns(2)
    with g1:
        fig = px.pie(df, names="Categoría", values="Cantidad", hole=0.35,
                     color="Categoría",
                     color_discrete_map={"Incendio Confirmado": "#e74c3c",
                                         "Falsa Alarma": "#2ecc71"},
                     title=f"Distribución de veracidad · {mes}")
        fig.update_traces(textinfo="label+value+percent")
        st.plotly_chart(fig, use_container_width=True)
    with g2:
        fig2 = px.bar(df, x="Categoría", y="Cantidad", text="Cantidad",
                      color="Categoría",
                      color_discrete_map={"Incendio Confirmado": "#e74c3c",
                                          "Falsa Alarma": "#2ecc71"},
                      title=f"Conteo por categoría · {mes}")
        st.plotly_chart(fig2, use_container_width=True)

    st.caption("Indicador de tesis: tasa de falsos positivos (FPR) objetivo ≤ 20%. "
               f"FPR actual del periodo: {(falsas / clasificadas * 100):.1f}%")
