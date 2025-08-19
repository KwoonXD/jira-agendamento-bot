# utils/export_utils.py
from __future__ import annotations

import io
import pandas as pd
import streamlit as st
from typing import List, Dict


def exportar_para_excel(chamados: List[Dict], filename: str = "chamados.xlsx"):
    """
    Converte lista de dicts em Excel e mostra um botão de download no Streamlit.
    """
    if not chamados:
        st.warning("Nada para exportar.")
        return

    df = pd.DataFrame(chamados)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Chamados")

    st.download_button(
        "⬇️ Download Excel",
        data=buffer.getvalue(),
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
