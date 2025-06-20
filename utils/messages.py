from datetime import datetime

def gerar_mensagem(loja, chamados):
    blocos = []
    for ch in chamados:
        data_agendada = ch.get('data_agendada')
        data_formatada = datetime.strptime(data_agendada, "%Y-%m-%dT%H:%M:%S.%f%z").strftime('%d/%m/%Y %H:%M') if data_agendada else '--'
        blocos.append(
            f"*{ch['key']}*\n"
            f"*Loja:* {loja}\n"
            f"*PDV:* {ch['pdv']}\n"
            f"*ATIVO:* {ch['ativo']}\n"
            f"*Problema:* {ch['problema']}\n"
            f"*Data Agendada:* {data_formatada}\n*****"
        )
    blocos.append(
        f"*Endereço:* {chamados[0]['endereco']}\n"
        f"*Estado:* {chamados[0]['estado']}\n"
        f"*CEP:* {chamados[0]['cep']}\n"
        f"*Cidade:* {chamados[0]['cidade']}"
    )
    return "\n".join(blocos)
