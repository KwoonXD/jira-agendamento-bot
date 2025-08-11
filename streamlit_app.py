import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, date, time
from collections import defaultdict
from itertools import chain

from utils.jira_api import JiraAPI
from utils.messages import gerar_mensagem_whatsapp, verificar_duplicidade
from utils.export_utils import chamados_to_csv

# (Kanban) arrastar-e-soltar
try:
    from streamlit_sortables import sort_items  # pip: streamlit-sortables==0.3.1
    HAS_SORTABLES = True
except Exception:
    HAS_SORTABLES = False

# Links padrões
ISO_DESKTOP_URL = "https://drive.google.com/file/d/1GQ64blQmysK3rbM0s0Xlot89bDNAbj5L/view?usp=drive_link"
ISO_PDV_URL     = "https://drive.google.com/file/d/1vxfHUDlT3kDdMaN0HroA5Nm9_OxasTaf/view?usp=drive_link"
RAT_URL         = "https://drive.google.com/file/d/1_SG1RofIjoJLgwWYs0ya0fKlmVd74Lhn/view?usp=sharing"

# Página
st.set_page_config(page_title="Painel Field Service", layout="wide")
st_autorefresh(interval=90_000, key="auto_refresh")

if "history" not in st.session_state:
    st.session_state.history = []
if "global_filter" not in st.session_state:
    st.session_state.global_filter = ""

# Helpers
def parse_dt(raw):
    if not raw:
        return "Não definida"
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
        except Exception:
            pass
    return "Não definida"

def _contar_tipos(itens):
    desktop = 0
    for ch in itens:
        pdv_val = str(ch.get("pdv", "")).strip()
        ativo   = str(ch.get("ativo", "")).lower()
        if pdv_val == "300" or "desktop" in ativo:
            desktop += 1
    pdv = len(itens) - desktop
    return pdv, desktop

def is_desktop(ch):
    return str(ch.get("pdv","")).strip()=="300" or "desktop" in str(ch.get("ativo","")).lower()

def filtrar_detalhes(detalhes, only_pdv, only_desktop, busca_global):
    out=[]
    for ch in detalhes:
        d = is_desktop(ch)
        if only_pdv and d:
            continue
        if only_desktop and not d:
            continue
        if busca_global:
            blob = f"{ch.get('key','')} {ch.get('pdv','')} {ch.get('ativo','')} {ch.get('problema','')} {ch.get('endereco','')} {ch.get('cidade','')}".lower()
            if busca_global.lower() not in blob:
                continue
        out.append(ch)
    return out

AGEND_PRESETS = {
    "Manhã (09:00)": time(9, 0, 0),
    "Tarde (14:00)": time(14, 0, 0),
    "Noite (19:00)": time(19, 0, 0),
}

STATUS_STYLE = {
    "AGENDAMENTO": {"emoji": "🟨", "label": "PENDENTE",  "bg": "#FFF7CC"},
    "AGENDADO":    {"emoji": "🟩", "label": "AGENDADO",  "bg": "#D9F7D9"},
    "TEC-CAMPO":   {"emoji": "🟦", "label": "TEC‑CAMPO", "bg": "#D6E8FF"},
}
def status_badge(status_name: str) -> str:
    s = STATUS_STYLE.get(status_name.upper(), {"emoji":"⬜️","label":status_name,"bg":"#EEEEEE"})
    return f"""<span style="background:{s['bg']};padding:4px 8px;border-radius:8px;
               font-weight:600;font-size:12px">{s['emoji']} {s['label']}</span>"""

def group_title_with_badge(base_title: str, status_name: str) -> str:
    return f"{base_title} &nbsp;&nbsp; {status_badge(status_name)}"

# Jira
jira = JiraAPI(
    st.secrets["EMAIL"],
    st.secrets["API_TOKEN"],
    "https://delfia.atlassian.net",
)

PEND_JQL = 'project = FSA AND status = "AGENDAMENTO"'
AGEN_JQL = 'project = FSA AND status = "AGENDADO"'
TEC_JQL  = 'project = FSA AND status = "TEC-CAMPO"'

FIELDS = (
    "summary,customfield_14954,customfield_14829,customfield_14825,"
    "customfield_12374,customfield_12271,customfield_11993,"
    "customfield_11994,customfield_11948,customfield_12036,customfield_12279,status"
)

# Busca
pendentes_raw = jira.buscar_chamados(PEND_JQL, FIELDS)
agendados_raw = jira.buscar_chamados(AGEN_JQL, FIELDS)
tec_campo_raw = jira.buscar_chamados(TEC_JQL,  FIELDS)

# Agrupamentos
grouped_agendados = defaultdict(lambda: defaultdict(list))
for issue in agendados_raw:
    f = issue.get("fields", {})
    loja = f.get("customfield_14954", {}).get("value") or "Loja Desconhecida"
    grouped_agendados[parse_dt(f.get("customfield_12036"))][loja].append(issue)

grouped_tec_campo = defaultdict(lambda: defaultdict(list))
for issue in tec_campo_raw:
    f = issue.get("fields", {})
    loja = f.get("customfield_14954", {}).get("value") or "Loja Desconhecida"
    grouped_tec_campo[parse_dt(f.get("customfield_12036"))][loja].append(issue)

agrup_pend = jira.agrupar_chamados(pendentes_raw)

raw_by_loja = defaultdict(list)
for i in chain(pendentes_raw, agendados_raw, tec_campo_raw):
    loja = i["fields"].get("customfield_14954", {}).get("value") or "Loja Desconhecida"
    raw_by_loja[loja].append(i)

# Header
st.title("Painel Field Service")

c1, c2, c3, c4 = st.columns([4,1.2,1.2,1.2])
with c1:
    st.session_state.global_filter = st.text_input(
        "Filtro global (FSA, PDV, ativo, problema, endereço, cidade...)",
        value=st.session_state.global_filter,
        placeholder="ex: 303 / CPU / Fortaleza / FSA-123"
    )
with c2: st.metric("PENDENTES", len(pendentes_raw))
with c3: st.metric("AGENDADOS", len(agendados_raw))
with c4: st.metric("TEC‑CAMPO", len(tec_campo_raw))

st.divider()

# Sidebar
with st.sidebar:
    st.header("Ações")
    if st.button("↩️ Desfazer última ação"):
        if st.session_state.history:
            action = st.session_state.history.pop()
            reverted = 0
            for key in action["keys"]:
                trans = jira.get_transitions(key)
                rev_id = next((t["id"] for t in trans if t.get("to", {}).get("name") == action["from"]), None)
                if rev_id and jira.transicionar_status(key, rev_id).status_code == 204:
                    reverted += 1
            st.success(f"Revertido: {reverted} FSAs → {action['from']}")
        else:
            st.info("Nenhuma ação para desfazer.")

    st.markdown("---")
    st.header("Transição de Chamados (em massa)")
    lojas_pend = set(agrup_pend.keys())
    lojas_ag   = set(chain.from_iterable(stores.keys() for stores in grouped_agendados.values())) if grouped_agendados else set()
    lojas_tc   = set(chain.from_iterable(stores.keys() for stores in grouped_tec_campo.values())) if grouped_tec_campo else set()
    lojas = sorted(lojas_pend | lojas_ag | lojas_tc)
    loja_sel = st.selectbox("Selecione a loja:", ["—"] + lojas)

    if loja_sel != "—":
        em_campo = st.checkbox("Técnico está em campo? (agendar + mover/registrar)", value=False)

        if em_campo:
            st.markdown("**Dados de Agendamento (manual)**")
            preset_sel = st.selectbox("Janela (hoje)", list(AGEND_PRESETS.keys()), index=1)
            data_sel = st.date_input("Data do Agendamento", value=date.today())
            hora_sel = st.time_input("Hora", value=AGEND_PRESETS[preset_sel])
            tem_tecnico = st.checkbox("Possui técnico definido?", value=True)
            tecnico = st.text_input("Dados do técnico (Nome-CPF-RG-TEL)") if tem_tecnico else ""
            motivo_sem_tecnico = None
            if not tem_tecnico:
                motivo_sem_tecnico = st.selectbox(
                    "Motivo sem técnico",
                    ["Sem cobertura na região", "Sem confirmação do técnico", "Janela da loja", "Outro"]
                )

            dt_iso = datetime.combine(data_sel, hora_sel).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
            extra_ag = {"customfield_12036": dt_iso}
            if tecnico:
                extra_ag["customfield_12279"] = {
                    "type":"doc","version":1,
                    "content":[{"type":"paragraph","content":[{"type":"text","text":tecnico}]}]
                }

            keys_pend  = [i["key"] for i in pendentes_raw if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
            keys_ag    = [i["key"] for i in agendados_raw  if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
            keys_tc    = [i["key"] for i in tec_campo_raw  if i["fields"].get("customfield_14954", {}).get("value") == loja_sel]
            all_keys   = keys_pend + keys_ag + keys_tc

            label_btn = f"Agendar {'e mover → Tec-Campo' if tem_tecnico else 'e comentar sem técnico'} ({len(all_keys)} FSAs)"
            if st.button(label_btn):
                errors=[]; moved=0; comentados=0

                for k in keys_pend:
                    trans = jira.get_transitions(k)
                    agid  = next((t["id"] for t in trans if "agend" in t["name"].lower()), None)
                    if agid:
                        r = jira.transicionar_status(k, agid, fields=extra_ag)
                        if r.status_code != 204:
                            errors.append(f"{k}⏳{r.status_code}")

                for k in all_keys:
                    if tem_tecnico:
                        r = jira.transition_by_name(k, "tec-campo")
                        if r is not None and r.status_code == 204:
                            moved += 1
                        elif r is not None:
                            errors.append(f"{k}➡️{r.status_code}")
                    else:
                        if motivo_sem_tecnico:
                            c = jira.add_comment(k, f"[BOT] Agendado sem técnico. Motivo: {motivo_sem_tecnico}")
                            if c is not None and c.status_code in (200, 201):
                                comentados += 1

                if errors:
                    st.error("Erros:"); [st.code(e) for e in errors]
                else:
                    msg = f"{len(keys_pend)} agendados. "
                    if tem_tecnico: msg += f"{moved} movidos → Tec-Campo."
                    else: msg += f"{comentados} comentário(s) registrados."
                    st.success(msg)

# Abas
abas = ["PENDENTES", "AGENDADOS", "TEC-CAMPO", "KANBAN (arrastar & soltar)"]
tab1, tab2, tab3, tab4 = st.tabs(abas)
jira_base = "https://delfia.atlassian.net/browse/"

# ——— COMPONENTE: bloco por loja (keys únicas via widget_ns) ——————————————
def bloco_por_loja(status_nome: str, loja: str, detalhes_raw: list, widget_ns: str):
    colA, colB, colC = st.columns(3)
    with colA:
        only_pdv = st.toggle("Somente PDV", key=f"{widget_ns}-pdv-toggle", value=False)
    with colB:
        only_desktop = st.toggle("Somente Desktop", key=f"{widget_ns}-desk-toggle", value=False)
    with colC:
        st.caption("Filtro global aplicado")

    detalhes = filtrar_detalhes(detalhes_raw, only_pdv, only_desktop, st.session_state.global_filter)

    texto = gerar_mensagem_whatsapp(loja, detalhes, ISO_DESKTOP_URL, ISO_PDV_URL, RAT_URL)
    st.code(texto, language="text")

    if detalhes:
        st.markdown(
            "*FSAs:* " + ", ".join(f"[{d['key']}]({jira_base}{d['key']})" for d in detalhes),
            unsafe_allow_html=True
        )
    else:
        st.info("Nenhum chamado após filtros.")

    exp_col1, exp_col2 = st.columns([1,6])
    with exp_col1:
        if st.button("⬇️ Exportar CSV", key=f"{widget_ns}-export-csv"):
            fname = chamados_to_csv(detalhes, filename=f"{loja}-{status_nome.lower()}.csv")
            st.success(f"Arquivo gerado: {fname}")
    with exp_col2:
        st.caption("")

    st.markdown("---")

    with st.form(key=f"{widget_ns}-form-ag-rapido"):
        st.subheader("⚡ Agendamento rápido (HOJE)")
        sel = st.multiselect("Selecione FSAs", [d["key"] for d in detalhes], key=f"{widget_ns}-sel")
        preset = st.radio("Janela", list(AGEND_PRESETS.keys()), horizontal=True, index=1, key=f"{widget_ns}-preset")
        mover_tc = st.checkbox("Mover para TEC‑CAMPO após agendar", value=False, key=f"{widget_ns}-mv-tc")
        tecnico = st.text_input("Dados do técnico (Nome-CPF-RG-TEL) [opcional]", key=f"{widget_ns}-tec")
        enviar = st.form_submit_button("Agendar selecionados")
        if enviar and sel:
            dt_iso = datetime.combine(date.today(), AGEND_PRESETS[preset]).strftime("%Y-%m-%dT%H:%M:%S.000-0300")
            extra_ag = {"customfield_12036": dt_iso}
            if tecnico:
                extra_ag["customfield_12279"] = {
                    "type":"doc","version":1,
                    "content":[{"type":"paragraph","content":[{"type":"text","text":tecnico}]}]
                }
            erros, ok_ag, ok_tc = [], 0, 0
            for k in sel:
                trans = jira.get_transitions(k)
                agid  = next((t["id"] for t in trans if "agend" in t["name"].lower()), None)
                if agid:
                    r = jira.transicionar_status(k, agid, fields=extra_ag)
                    if r.status_code == 204:
                        ok_ag += 1
                    else:
                        erros.append(f"{k}⏳{r.status_code}")
                        continue
                if mover_tc:
                    t = jira.transition_by_name(k, "tec-campo")
                    if t is not None and t.status_code == 204:
                        ok_tc += 1
                    elif t is not None:
                        erros.append(f"{k}➡️{t.status_code}")
            if erros:
                st.error("Erros:"); [st.code(e) for e in erros]
            else:
                st.success(f"{ok_ag} agendados.{(' ' + str(ok_tc) + ' movidos → Tec‑Campo.') if mover_tc else ''}")

# Tab: Pendentes
with tab1:
    titulo = group_title_with_badge(f"Chamados PENDENTES ({len(pendentes_raw)})", "AGENDAMENTO")
    st.markdown(titulo, unsafe_allow_html=True)
    if not pendentes_raw:
        st.warning("Nenhum chamado em AGENDAMENTO.")
    else:
        for loja, itens in sorted(agrup_pend.items()):
            qtd_pdv, qtd_desktop = _contar_tipos(itens)
            base = f"{loja} — {len(itens)} chamado(s) ({qtd_pdv} PDV • {qtd_desktop} Desktop)"
            header = group_title_with_badge(base, "AGENDAMENTO")
            with st.expander(header, expanded=False):
                bloco_por_loja("pendentes", loja, itens, widget_ns=f"pend-{loja}")

# Tab: Agendados
with tab2:
    titulo = group_title_with_badge(f"Chamados AGENDADOS ({len(agendados_raw)})", "AGENDADO")
    st.markdown(titulo, unsafe_allow_html=True)
    if not agendados_raw:
        st.info("Nenhum chamado em AGENDADO.")
    else:
        for date_key, stores in sorted(grouped_agendados.items()):
            total = sum(len(v) for v in stores.values())
            st.subheader(f"{date_key} — {total} chamado(s)")
            for loja, iss in sorted(stores.items()):
                detalhes = jira.agrupar_chamados(iss)[loja]
                qtd_pdv, qtd_desktop = _contar_tipos(detalhes)
                dup_keys = [d["key"] for d in detalhes if (d["pdv"], d["ativo"]) in verificar_duplicidade(detalhes)]
                tag_str = f" [Dup: {', '.join(dup_keys)}]" if dup_keys else ""
                base = f"{loja} — {len(iss)} chamado(s) ({qtd_pdv} PDV • {qtd_desktop} Desktop){tag_str}"
                header = group_title_with_badge(base, "AGENDADO")
                with st.expander(header, expanded=False):
                    bloco_por_loja("agendados", loja, detalhes, widget_ns=f"ag-{date_key}-{loja}")

# Tab: Tec-Campo
with tab3:
    titulo = group_title_with_badge(f"Chamados TEC‑CAMPO ({len(tec_campo_raw)})", "TEC-CAMPO")
    st.markdown(titulo, unsafe_allow_html=True)
    if not tec_campo_raw:
        st.info("Nenhum chamado em TEC‑CAMPO.")
    else:
        for date_key, stores in sorted(grouped_tec_campo.items()):
            total = sum(len(v) for v in stores.values())
            st.subheader(f"{date_key} — {total} chamado(s)")
            for loja, iss in sorted(stores.items()):
                detalhes = jira.agrupar_chamados(iss)[loja]
                qtd_pdv, qtd_desktop = _contar_tipos(detalhes)
                base = f"{loja} — {len(iss)} chamado(s) ({qtd_pdv} PDV • {qtd_desktop} Desktop)"
                header = group_title_with_badge(base, "TEC-CAMPO")
                with st.expander(header, expanded=False):
                    bloco_por_loja("tec-campo", loja, detalhes, widget_ns=f"tc-{date_key}-{loja}")

# Tab: Kanban
with tab4:
    st.subheader("Kanban por Loja (arraste os FSAs entre colunas para transicionar)")
    if not HAS_SORTABLES:
        st.error("Instale o pacote: streamlit-sortables==0.3.1")
    else:
        cka, ckb = st.columns([2, 3])
        with cka:
            preset = st.selectbox("Janela (hoje) para novos AGENDADOS", list(AGEND_PRESETS.keys()), index=1)
        with ckb:
            tecnico = st.text_input("Dados do técnico (Nome-CPF-RG-TEL) [opcional]")
        dt_iso_default = datetime.combine(date.today(), AGEND_PRESETS[preset]).strftime("%Y-%m-%dT%H:%M:%S.000-0300")

        lojas_all = sorted(raw_by_loja.keys())
        loja_kanban = st.selectbox("Loja", ["—"] + lojas_all, index=1 if lojas_all else 0)

        if loja_kanban == "—" or not lojas_all:
            st.info("Selecione uma loja.")
        else:
            def status_of(issue):
                return (issue.get("fields",{}).get("status",{}) or {}).get("name","").upper()

            pend_keys = [i["key"] for i in raw_by_loja[loja_kanban] if status_of(i)=="AGENDAMENTO"]
            agen_keys = [i["key"] for i in raw_by_loja[loja_kanban] if status_of(i)=="AGENDADO"]
            tecc_keys = [i["key"] for i in raw_by_loja[loja_kanban] if status_of(i)=="TEC-CAMPO"]

            original = [
                {"header": "🟨 AGENDAMENTO", "items": pend_keys},
                {"header": "🟩 AGENDADO",    "items": agen_keys},
                {"header": "🟦 TEC‑CAMPO",   "items": tecc_keys},
            ]

            custom_css = """
            .sortable-component{gap:1rem}
            .sortable-container{background:#F7F7F9;border:1px solid #e5e7eb;border-radius:12px;padding:10px;min-height:280px}
            .sortable-container-header{font-weight:700;padding:6px 8px}
            .sortable-item{background:white;border:1px solid #e5e7eb;border-radius:10px;padding:8px 10px;margin:6px 0}
            """

            st.caption("Dica: arraste e, ao finalizar, clique em **Aplicar mudanças**.")
            sorted_struct = sort_items(original, multi_containers=True, custom_style=custom_css)

            if st.button("Aplicar mudanças"):
                pos = {}
                for cont in sorted_struct:
                    colname = "AGENDAMENTO" if "AGENDAMENTO" in cont["header"] else ("AGENDADO" if "AGENDADO" in cont["header"] else "TEC-CAMPO")
                    for key in cont["items"]:
                        pos[key] = colname

                erros, ok_agendar, ok_tc, ok_back = [], 0, 0, 0
                for key in (pend_keys + agen_keys + tecc_keys):
                    desired = pos.get(key)
                    if not desired:
                        continue
                    cur_issue = jira.get_issue(key)
                    cur_status = (cur_issue.get("fields",{}).get("status",{}) or {}).get("name","").upper()
                    if desired == cur_status:
                        continue

                    if desired == "AGENDADO":
                        extra_ag = {"customfield_12036": dt_iso_default}
                        if tecnico:
                            extra_ag["customfield_12279"] = {
                                "type":"doc","version":1,
                                "content":[{"type":"paragraph","content":[{"type":"text","text":tecnico}]}]
                            }
                        trans = jira.get_transitions(key)
                        agid  = next((t["id"] for t in trans if "agend" in t["name"].lower()), None)
                        if not agid:
                            erros.append(f"{key}: transição 'Agendar' não encontrada")
                            continue
                        r = jira.transicionar_status(key, agid, fields=extra_ag)
                        if r.status_code == 204: ok_agendar += 1
                        else: erros.append(f"{key}⏳{r.status_code}")

                    elif desired == "TEC-CAMPO":
                        r = jira.transition_by_name(key, "tec-campo")
                        if r is not None and r.status_code == 204: ok_tc += 1
                        elif r is not None: erros.append(f"{key}➡️{r.status_code}")
                        else: erros.append(f"{key}: transição para Tec‑Campo não encontrada")

                    elif desired == "AGENDAMENTO":
                        r = jira.transition_by_name(key, "agendamento")
                        if r is not None and r.status_code == 204: ok_back += 1
                        elif r is not None: erros.append(f"{key}↩️{r.status_code}")
                        else: erros.append(f"{key}: transição para Agendamento não encontrada")

                if erros:
                    st.error("Erros ao aplicar mudanças:"); [st.code(e) for e in erros]
                else:
                    st.success(f"OK: {ok_agendar}→AGENDADO, {ok_tc}→TEC‑CAMPO, {ok_back}→AGENDAMENTO")

st.markdown("---")
st.caption(f"Última atualização: {datetime.now():%d/%m/%Y %H:%M:%S}")
