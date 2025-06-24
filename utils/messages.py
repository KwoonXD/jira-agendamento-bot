from datetime import datetime

def gerar_mensagem(loja, chamados):
    blocos = []
    # Para coletar o endereço único (assumindo todos pendentes são do mesmo local)
    endereco_info = None

    for ch in chamados:
        # cabeçalho de cada FSA
        linhas = [
            f"{ch['key']}",
            f"Loja: {loja}",
            f"PDV: {ch.get('pdv','--')}",
            f"ATIVO: {ch.get('ativo','--')}",
            f"Problema: {ch.get('problema','--')}",
            f"Data Agendada: --",  # sempre “--” para pendentes
            "***"
        ]
        blocos.append("\n".join(linhas))

        # armazena o único endereço (o último sobrescreve, mas todos são iguais)
        endereco_info = (
            ch.get('endereco','--'),
            ch.get('estado','--'),
            ch.get('cep','--'),
            ch.get('cidade','--')
        )

    # no final, adiciona uma linha em branco e o bloco de endereço único
    if endereco_info:
        blocos.append(
            "\n".join([
                f"Endereço: {endereco_info[0]}",
                f"Estado: {endereco_info[1]}",
                f"CEP: {endereco_info[2]}",
                f"Cidade: {endereco_info[3]}"
            ])
        )

    # junta tudo com duas quebras de linha entre blocos
    return "\n\n".join(blocos)
