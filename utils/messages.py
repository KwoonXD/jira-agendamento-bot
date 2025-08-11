# utils/messages.py
from datetime import datetime

def _fmt_data_agendada(raw):
    if not raw:
        return "--"
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y %H:%M")
        except Exception:
            pass
    return str(raw)

def _classificar_tipo(ch):
    """Desktop se PDV == 300 ou se 'desktop' aparecer em ATIVO (case-insensitive)."""
    pdv = str(ch.get("pdv", "")).strip()
    ativo = str(ch.get("ativo", "")).lower()
    if pdv == "300" or "desktop" in ativo:
        return "Desktop"
    return "PDV"

def gerar_mensagem(loja, chamados, iso_desktop_url=None, iso_pdv_url=None, rat_url=None):
    """
    Mensagem por loja, listando FSAs e exibindo endereço uma única vez.
    Inclui Status, Data agendada e links (RAT sempre; ISO conforme Desktop/PDV).
    """
    blocos = []
    endereco_info = None

    for ch in chamados:
        tipo = _classificar_tipo(ch)
        iso_link = iso_desktop_url if tipo == "Desktop" else iso_pdv_url

        linhas = [
            f"*{ch.get('key','--')}*",
            f"Loja: {loja}",
            f"Status: {ch.get('status','--')}",
            f"PDV: {ch.get('pdv','--')}",
            f"*ATIVO: {ch.get('ativo','--')}*",
            f"Tipo de atendimento: {tipo}",
            f"Problema: {ch.get('problema','--')}",
            f"Data agendada: {_fmt_data_agendada(ch.get('data_agendada'))}",
        ]
        if rat_url:
            linhas.append(f"RAT: {rat_url}")
        if iso_link:
            linhas.append(f"ISO ({tipo}): {iso_link}")

        linhas.append("***")
        blocos.append("\n".join(linhas))

        endereco_info = (
            ch.get('endereco','--'),
            ch.get('estado','--'),
            ch.get('cep','--'),
            ch.get('cidade','--')
        )

    if endereco_info:
        blocos.append(
            "\n".join([
                f"Endereço: {endereco_info[0]}",
                f"Estado: {endereco_info[1]}",
                f"CEP: {endereco_info[2]}",
                f"Cidade: {endereco_info[3]}",
            ])
        )

    return "\n\n".join(blocos)

def verificar_duplicidade(chamados):
    seen, duplicates = {}, set()
    for ch in chamados:
        key = (ch.get("pdv"), ch.get("ativo"))
        if key in seen:
            duplicates.add(key)
        else:
            seen[key] = True
    return duplicates
