import pandas as pd
from fpdf import FPDF

def chamados_to_csv(chamados, filename="chamados_exportados.csv"):
    df = pd.DataFrame(chamados)
    df.to_csv(filename, index=False)
    return filename

def chamados_to_pdf(chamados, filename="chamados_exportados.pdf"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    for chamado in chamados:
        pdf.multi_cell(0, 10,
            f"Chamado: {chamado['key']}\n"
            f"Loja: {chamado['loja']}\n"
            f"PDV: {chamado['pdv']}\n"
            f"Ativo: {chamado['ativo']}\n"
            f"Problema: {chamado['problema']}\n"
            f"Data Agendada: {chamado['data_agendada']}\n"
            f"Endereço: {chamado['endereco']}\n"
            f"Cidade: {chamado['cidade']} - {chamado['estado']} (CEP: {chamado['cep']})\n"
            "--------------------------------------------"
        )

    pdf.output(filename)
    return filename
