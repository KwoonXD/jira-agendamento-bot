# utils/messages.py
 
 from datetime import datetime
 
 def gerar_mensagem(loja, chamados):
 """
 Gera uma mensagem para um grupo de chamados da mesma loja,
 listando cada FSA sem data agendada e, ao final, exibindo
 uma única vez o bloco de endereço.
 """
 blocos = []
 endereco_info = None # Será preenchido com a tupla (end,estado,cep,cidade)
 
 for ch in chamados:
 # cabeçalho de cada FSA
 linhas = [
 f"*{ch['key']}*",
 f"Loja: {loja}",
 f"PDV: {ch.get('pdv','--')}",
 f"*ATIVO: {ch.get('ativo','--')}*",
 f"Problema: {ch.get('problema','--')}",
 "***"
 ]
 blocos.append("\n".join(linhas))
 
 # armazena endereço (último sobrescreve, mas todos pendentes têm o mesmo)
 endereco_info = (
 ch.get('endereco','--'),
 ch.get('estado','--'),
 ch.get('cep','--'),
 ch.get('cidade','--')
 )
 
 # após listar todos, adiciona o bloco de endereço apenas uma vez
 if endereco_info:
 blocos.append(
 "\n".join([
 f"Endereço: {endereco_info[0]}",
 f"Estado: {endereco_info[1]}",
 f"CEP: {endereco_info[2]}",
 f"Cidade: {endereco_info[3]}"
 ])
 )
 
 # une todos os blocos com linha em branco dupla
 return "\n\n".join(blocos)
 
 
 def verificar_duplicidade(chamados):
 """
 Retorna um set de tuplas (pdv, ativo) que aparecem mais de uma vez,
 para sinalizar duplicidade.
 """
 seen = {}
 duplicates = set()
 for ch in chamados:
 key = (ch.get("pdv"), ch.get("ativo"))
 if key in seen:
 duplicates.add(key)
 else:
 seen[key] = True
 return duplicates
