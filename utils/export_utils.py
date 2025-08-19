import pandas as pd
from fpdf import FPDF


def chamados_to_csv(chamados, filename="chamados_exportados.csv"):
    """
    Exporta uma lista de chamados (list[dict]) para CSV.
    """
    if not chamados:
        # Garante um CSV válido mesmo sem dados
        pd.DataFrame([{}]).to_csv(filename, index=False)
        return filename

    df = pd.DataFrame(chamados)
    df.to_csv(filename, index=False)
    return filename


def chamados_to_pdf(chamados, filename="chamados_exportados.pdf"):
    """
    Exporta uma lista de chamados (list[dict]) para PDF num layout simples.
    Compatível com fpdf (1.x) e fpdf2 (2.x).
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Título
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "Relatório de Chamados", ln=1, align="C")
    pdf.ln(2)

    pdf.set_font("Arial", size=11)

    if not chamados:
        pdf.multi_cell(0, 8, "Nenhum chamado para exportar.")
        pdf.output(filename)
        return filename

    for chamado in chamados:
        key = chamado.get("key", "--")
        loja = chamado.get("loja", "--")
        pdv = chamado.get("pdv", "--")
        ativo = chamado.get("ativo", "--")
        problema = chamado.get("problema", "--")
        data_agendada = chamado.get("data_agendada", "--")
        endereco = chamado.get("endereco", "--")
        cidade = chamado.get("cidade", "--")
        estado = chamado.get("estado", "--")
        cep = chamado.get("cep", "--")

        bloco = (
            f"Chamado: {key}\n"
            f"Loja: {loja}\n"
            f"PDV: {pdv}\n"
            f"Ativo: {ativo}\n"
            f"Problema: {problema}\n"
            f"Data Agendada: {data_agendada}\n"
            f"Endereço: {endereco}\n"
            f"Cidade: {cidade} - {estado} (CEP: {cep})\n"
            "--------------------------------------------"
        )
        pdf.multi_cell(0, 8, bloco)
        pdf.ln(1)

    pdf.output(filename)
    return filename
