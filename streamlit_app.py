import json
from datetime import datetime

import streamlit as st

# Calculadora de preço de peças impressas em 3D (versão web, feita com Streamlit)
# A conta é a mesma do programa de terminal (calculadora_3d.py).
# Para rodar no computador: pip install streamlit  e depois  streamlit run streamlit_app.py

st.set_page_config(page_title="Calculadora de preço 3D", page_icon="🧮", layout="centered")


def brl(valor):
    # formata um número como dinheiro brasileiro: 1234.5 -> R$ 1.234,50
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "R$ " + texto


# ---------------- ARMAZENAMENTO ----------------
# Se existirem os "secrets" da planilha do Google, os dados são gravados lá e ficam
# guardados entre acessos (Mac, iPhone, etc.). Sem isso, valem só enquanto a página estiver aberta.
CONFIG_PADRAO = {
    "preco_energia": 0.90,        # R$ por kWh
    "potencia_impressora": 0.15,  # kW (150 W)
    "margem_lucro": 200.0,        # % sobre o custo da peça
    "taxa_shopee": 20.0,          # % de comissão
    "taxa_fixa_shopee": 4.50,     # R$ por item
    "embalagem": 1.50,            # R$ por pedido
}
FILAMENTOS_PADRAO = [
    {"nome": "PLA", "preco_kg": 100.00},
    {"nome": "PETG", "preco_kg": 70.00},
]
CABECALHO_HIST = ["Data", "Peça", "Canal", "Preço", "Lucro"]


def usa_planilha():
    try:
        return "gcp_service_account" in st.secrets and "planilha_url" in st.secrets
    except Exception:
        return False


@st.cache_resource
def abrir_planilha():
    import gspread

    gc = gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))
    planilha = gc.open_by_url(st.secrets["planilha_url"])

    def aba(nome):
        try:
            return planilha.worksheet(nome)
        except gspread.exceptions.WorksheetNotFound:
            return planilha.add_worksheet(title=nome, rows=1000, cols=6)

    return aba("dados"), aba("historico")


def carregar_tudo():
    filamentos = [dict(f) for f in FILAMENTOS_PADRAO]
    config = dict(CONFIG_PADRAO)
    historico = []
    if usa_planilha():
        aba_dados, aba_hist = abrir_planilha()
        texto = aba_dados.acell("A1").value
        if texto:
            dados = json.loads(texto)
            filamentos = dados.get("filamentos", filamentos)
            config.update(dados.get("config", {}))
        for linha in aba_hist.get_all_values()[1:]:
            if len(linha) >= 5 and linha[1]:
                historico.append(
                    {"nome": linha[1], "canal": linha[2], "preco": float(linha[3]), "lucro": float(linha[4])}
                )
    return filamentos, config, historico


def salvar_dados():
    if usa_planilha():
        aba_dados, _ = abrir_planilha()
        texto = json.dumps(
            {"filamentos": st.session_state.filamentos, "config": st.session_state.config},
            ensure_ascii=False,
        )
        aba_dados.update(values=[[texto]], range_name="A1")


def salvar_calculo(registro):
    if usa_planilha():
        _, aba_hist = abrir_planilha()
        if not aba_hist.get_all_values():
            aba_hist.append_row(CABECALHO_HIST, value_input_option="RAW")
        aba_hist.append_row(
            [datetime.now().strftime("%d/%m/%Y %H:%M"), registro["nome"], registro["canal"],
             round(registro["preco"], 2), round(registro["lucro"], 2)],
            value_input_option="RAW",
        )


def limpar_historico_salvo():
    if usa_planilha():
        _, aba_hist = abrir_planilha()
        aba_hist.clear()
        aba_hist.append_row(CABECALHO_HIST, value_input_option="RAW")


# ---------------- SENHA (opcional) ----------------
# Se existir "senha" nos secrets, o app só abre depois de digitá-la.
try:
    senha_certa = st.secrets["senha"] if "senha" in st.secrets else None
except Exception:
    senha_certa = None
if senha_certa and not st.session_state.get("liberado"):
    st.title("🧮 Calculadora de preço 3D")
    digitada = st.text_input("Senha", type="password")
    if digitada:
        if digitada == senha_certa:
            st.session_state.liberado = True
            st.rerun()
        else:
            st.error("Senha incorreta.")
    st.stop()

# ---------------- ESTADO ----------------
if "filamentos" not in st.session_state:
    fil, conf, hist = carregar_tudo()
    st.session_state.filamentos = fil
    st.session_state.config = conf
    st.session_state.historico = hist
    st.session_state.ultimo_salvo = json.dumps({"filamentos": fil, "config": conf}, sort_keys=True)
if "resultado" not in st.session_state:
    st.session_state.resultado = None


def contas_preco(gramas, horas, preco_kg, taxa_porcentagem, taxa_fixa):
    c = st.session_state.config
    custo_filamento = (gramas / 1000) * preco_kg
    custo_energia = horas * c["potencia_impressora"] * c["preco_energia"]
    custo_total = custo_filamento + custo_energia + c["embalagem"]

    # lucro é uma porcentagem do custo e é o mesmo em qualquer canal
    lucro = custo_total * c["margem_lucro"] / 100

    # o preço é 100%: a comissão ocupa uma parte e o resto cobre custo, taxa fixa e lucro
    porcentagem_resto = 100 - taxa_porcentagem
    preco_venda = (custo_total + taxa_fixa + lucro) * 100 / porcentagem_resto
    comissao = preco_venda * taxa_porcentagem / 100

    return {
        "custo_filamento": custo_filamento,
        "custo_energia": custo_energia,
        "embalagem": c["embalagem"],
        "custo_total": custo_total,
        "comissao": comissao,
        "taxa_fixa": taxa_fixa,
        "taxas_total": comissao + taxa_fixa,
        "lucro": lucro,
        "preco_venda": preco_venda,
    }


st.title("🧮 Calculadora de preço 3D")

aba_calc, aba_hist, aba_fil, aba_conf = st.tabs(
    ["Calcular", "Histórico", "Filamentos", "Configurações"]
)

# ---------------- CALCULAR ----------------
with aba_calc:
    nome_peca = st.text_input("Nome da peça", placeholder="Ex.: Suporte de celular")

    nomes_fil = [f["nome"] for f in st.session_state.filamentos]
    filamento_nome = st.selectbox("Filamento", nomes_fil)

    gramas = st.number_input("Quantidade de filamento (gramas)", min_value=0.0, value=0.0, step=1.0)

    col1, col2 = st.columns(2)
    horas = col1.number_input("Horas", min_value=0, value=0, step=1)
    minutos = col2.number_input("Minutos", min_value=0, max_value=59, value=0, step=1)

    canal = st.radio("Onde será vendida?", ["Shopee", "Por fora"], horizontal=True)

    if st.button("Calcular preço", type="primary", use_container_width=True):
        if not nome_peca.strip():
            st.error("Digite o nome da peça.")
        elif gramas <= 0:
            st.error("Digite a quantidade de filamento usada (maior que zero).")
        elif horas == 0 and minutos == 0:
            st.error("Digite o tempo de impressão.")
        else:
            cfg = st.session_state.config
            fil = next(f for f in st.session_state.filamentos if f["nome"] == filamento_nome)
            if canal == "Shopee":
                taxa_pct = cfg["taxa_shopee"]
                taxa_fixa = cfg["taxa_fixa_shopee"]
            else:
                taxa_pct = 0.0
                taxa_fixa = 0.0
            tempo_total = horas + minutos / 60
            r = contas_preco(gramas, tempo_total, fil["preco_kg"], taxa_pct, taxa_fixa)
            r["nome"] = nome_peca.strip()
            r["canal"] = canal
            r["taxa_pct"] = taxa_pct
            st.session_state.resultado = r
            registro = {"nome": r["nome"], "canal": canal, "preco": r["preco_venda"], "lucro": r["lucro"]}
            st.session_state.historico.append(registro)
            salvar_calculo(registro)

    r = st.session_state.resultado
    if r:
        st.divider()
        st.subheader(f"{r['nome']} ({r['canal']})")
        st.metric("Preço de venda", brl(r["preco_venda"]))
        st.write(f"**Custo total:** {brl(r['custo_total'])}")
        st.write(f"- Filamento: {brl(r['custo_filamento'])}")
        st.write(f"- Energia: {brl(r['custo_energia'])}")
        st.write(f"- Embalagem: {brl(r['embalagem'])}")
        if r["canal"] == "Shopee":
            st.write(f"**Taxas da Shopee:** {brl(r['taxas_total'])}")
            st.write(f"- Comissão ({r['taxa_pct']:g}%): {brl(r['comissao'])}")
            st.write(f"- Taxa fixa: {brl(r['taxa_fixa'])}")
        st.write(f"**Lucro:** {brl(r['lucro'])}")

# ---------------- HISTÓRICO ----------------
with aba_hist:
    if not st.session_state.historico:
        st.info("Nenhuma peça calculada ainda.")
    else:
        linhas = [
            {
                "Peça": h["nome"],
                "Canal": h["canal"],
                "Preço": brl(h["preco"]),
                "Lucro": brl(h["lucro"]),
            }
            for h in st.session_state.historico
        ]
        st.table(linhas)
        if st.button("Limpar histórico"):
            st.session_state.historico = []
            limpar_historico_salvo()
            st.rerun()

# ---------------- FILAMENTOS ----------------
with aba_fil:
    st.write("Preço por kg de cada filamento:")
    for i, f in enumerate(st.session_state.filamentos):
        novo = st.number_input(
            f"{f['nome']} (R$/kg)", min_value=0.0, value=float(f["preco_kg"]), step=1.0, key=f"preco_fil_{i}"
        )
        st.session_state.filamentos[i]["preco_kg"] = novo

    st.divider()
    st.write("Cadastrar novo filamento")
    novo_nome = st.text_input("Nome do filamento", key="novo_fil_nome")
    novo_preco = st.number_input("Preço por kg (R$)", min_value=0.0, value=0.0, step=1.0, key="novo_fil_preco")
    if st.button("Adicionar filamento"):
        if not novo_nome.strip():
            st.error("Digite o nome do filamento.")
        elif novo_preco <= 0:
            st.error("Digite o preço por kg (maior que zero).")
        elif novo_nome.strip().lower() in [f["nome"].lower() for f in st.session_state.filamentos]:
            st.error("Esse filamento já existe.")
        else:
            st.session_state.filamentos.append({"nome": novo_nome.strip(), "preco_kg": novo_preco})
            salvar_dados()
            st.session_state.ultimo_salvo = json.dumps(
                {"filamentos": st.session_state.filamentos, "config": st.session_state.config}, sort_keys=True
            )
            st.rerun()

# ---------------- CONFIGURAÇÕES ----------------
with aba_conf:
    cfg = st.session_state.config
    cfg["preco_energia"] = st.number_input("Preço da energia (R$/kWh)", min_value=0.0, value=float(cfg["preco_energia"]), step=0.05)
    cfg["potencia_impressora"] = st.number_input("Consumo da impressora (kW)", min_value=0.0, value=float(cfg["potencia_impressora"]), step=0.01)
    cfg["margem_lucro"] = st.number_input("Margem de lucro (% sobre o custo)", min_value=0.0, value=float(cfg["margem_lucro"]), step=10.0)
    cfg["taxa_shopee"] = st.number_input(
        "Comissão da Shopee (%)", min_value=0.0, max_value=99.99, value=float(cfg["taxa_shopee"]), step=1.0,
        help="Precisa ficar abaixo de 100%.",
    )
    cfg["taxa_fixa_shopee"] = st.number_input("Taxa fixa da Shopee (R$ por item)", min_value=0.0, value=float(cfg["taxa_fixa_shopee"]), step=0.5)
    cfg["embalagem"] = st.number_input("Embalagem (R$ por pedido)", min_value=0.0, value=float(cfg["embalagem"]), step=0.5)
    if usa_planilha():
        st.caption("As alterações de configurações e filamentos ficam guardadas na planilha.")
    else:
        st.caption("Estes valores voltam ao padrão se a página for recarregada ou fechada.")

# grava na planilha quando filamentos ou configurações mudaram
estado_atual = json.dumps(
    {"filamentos": st.session_state.filamentos, "config": st.session_state.config}, sort_keys=True
)
if estado_atual != st.session_state.ultimo_salvo:
    salvar_dados()
    st.session_state.ultimo_salvo = estado_atual
