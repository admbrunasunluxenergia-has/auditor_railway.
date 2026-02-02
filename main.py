import streamlit as st
import pandas as pd
import math
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
import io

# Configuração da Página
st.set_page_config(
    page_title="Auditor de Fatura Sunlux",
    page_icon="⚡",
    layout="wide"
)

# Estilos CSS Personalizados
st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    .stButton>button {
        background-color: #1B5E4F;
        color: white;
        width: 100%;
    }
    .stButton>button:hover {
        background-color: #14453a;
        color: white;
    }
    h1, h2, h3 {
        color: #1B5E4F;
    }
    .metric-card {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        text-align: center;
    }
    </style>
""", unsafe_allow_html=True)

# =================================================================================
# LÓGICA DE AUDITORIA
# =================================================================================

class AuditorFatura:
    FATOR_POTENCIA_MINIMO = 0.92
    LIMITE_ENERGIA_REATIVA = 0.5
    MULTA_ULTRAPASSAGEM_DEMANDA = 1.5
    
    @staticmethod
    def calcular_fator_potencia(ativo, reativo):
        if ativo == 0: return 1.0
        aparente = math.sqrt(ativo**2 + reativo**2)
        return round(ativo / aparente, 4)
    
    @staticmethod
    def analisar_fatura(fatura):
        # 1. Reativo
        limite_reativo = fatura['consumo_ativo'] * AuditorFatura.LIMITE_ENERGIA_REATIVA
        excedente_reativo = max(0, fatura['consumo_reativo'] - limite_reativo)
        multa_reativo = excedente_reativo * fatura['tarifa_energia']
        fp_conforme = fatura['fator_potencia'] >= AuditorFatura.FATOR_POTENCIA_MINIMO
        
        # 2. Demanda
        ultrapassagem = max(0, fatura['demanda_medida'] - fatura['demanda_contratada'])
        multa_ultrapassagem = ultrapassagem * AuditorFatura.MULTA_ULTRAPASSAGEM_DEMANDA * fatura['tarifa_demanda']
        utilizacao = (fatura['demanda_medida'] / fatura['demanda_contratada'] * 100) if fatura['demanda_contratada'] > 0 else 0
        
        # 3. Banco Capacitores
        qc_necessaria = 0
        qc_comercial = 0
        recomendacao_banco = 'NÃO'
        
        if fatura['fator_potencia'] < AuditorFatura.FATOR_POTENCIA_MINIMO:
            ang_atual = math.acos(fatura['fator_potencia'])
            ang_desejado = math.acos(AuditorFatura.FATOR_POTENCIA_MINIMO)
            qc_necessaria = fatura['consumo_ativo'] * (math.tan(ang_atual) - math.tan(ang_desejado))
            
            potencias = [5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 75, 100, 150, 200]
            qc_comercial = min([p for p in potencias if p >= qc_necessaria], default=potencias[-1])
            recomendacao_banco = 'SIM'

        return {
            'periodo': f"{fatura['mes']:02d}/{fatura['ano']}",
            'fp': fatura['fator_potencia'],
            'fp_conforme': fp_conforme,
            'multa_reativo': multa_reativo,
            'multa_ultrapassagem': multa_ultrapassagem,
            'utilizacao_demanda': utilizacao,
            'banco_capacitores': {
                'recomendacao': recomendacao_banco,
                'kvar_necessario': qc_necessaria,
                'kvar_comercial': qc_comercial
            }
        }

# =================================================================================
# GERADOR DE PDF
# =================================================================================

def gerar_pdf(dados_auditoria, dados_cliente):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=1.5*cm, leftMargin=1.5*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    # Estilos Personalizados
    estilo_titulo = ParagraphStyle(
        name='TituloSunlux', parent=styles['Heading1'],
        fontSize=24, textColor=colors.HexColor('#1B5E4F'), alignment=TA_CENTER, spaceAfter=12
    )
    estilo_secao = ParagraphStyle(
        name='Secao', parent=styles['Heading2'],
        fontSize=12, textColor=colors.white, backColor=colors.HexColor('#1B5E4F'),
        alignment=TA_CENTER, spaceBefore=10, spaceAfter=10, borderPadding=5
    )
    
    # Cabeçalho
    story.append(Paragraph("<b>SUNLUX</b>", estilo_titulo))
    story.append(Paragraph("ENERGIA E COMÉRCIO", styles['Heading2']))
    story.append(Spacer(1, 0.5*cm))
    
    # Dados do Cliente
    story.append(Paragraph("DADOS DO CLIENTE", estilo_secao))
    cliente_data = [
        ['Cliente:', dados_cliente['nome'], 'Grupo:', dados_cliente['grupo']],
        ['Concessionária:', dados_cliente['concessionaria'], 'Estado:', dados_cliente['estado']]
    ]
    t = Table(cliente_data, colWidths=[3*cm, 5*cm, 3*cm, 5*cm])
    t.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.5*cm))
    
    # Resumo
    story.append(Paragraph("RESUMO DA AUDITORIA", estilo_secao))
    resumo_data = [
        ['Economia Potencial Total', f"R$ {dados_auditoria['resumo']['economia_total']:.2f}"],
        ['Multas por Reativo', f"R$ {dados_auditoria['resumo']['total_multa_reativo']:.2f}"],
        ['Multas por Ultrapassagem', f"R$ {dados_auditoria['resumo']['total_multa_ultrapassagem']:.2f}"],
    ]
    t_resumo = Table(resumo_data, colWidths=[8*cm, 6*cm])
    t_resumo.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#1B5E4F')),
        ('TEXTCOLOR', (0,0), (0,-1), colors.white),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('GRID', (0,0), (-1,-1), 1, colors.white),
        ('PADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t_resumo)
    story.append(Spacer(1, 0.5*cm))
    
    # Detalhamento
    story.append(Paragraph("DETALHAMENTO TÉCNICO", estilo_secao))
    header = [['Período', 'Fator Pot.', 'Multa FP', 'Uso Dem.', 'Multa Dem.', 'Banco Cap.']]
    data = []
    for a in dados_auditoria['analises']:
        data.append([
            a['periodo'],
            f"{a['fp']:.2f}",
            f"R$ {a['multa_reativo']:.2f}",
            f"{a['utilizacao_demanda']:.0f}%",
            f"R$ {a['multa_ultrapassagem']:.2f}",
            f"{a['banco_capacitores']['kvar_comercial']} kVAr" if a['banco_capacitores']['recomendacao'] == 'SIM' else "-"
        ])
    
    t_detalhe = Table(header + data, colWidths=[2.5*cm, 2.5*cm, 3*cm, 2.5*cm, 3*cm, 2.5*cm])
    t_detalhe.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1B5E4F')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F5F5F5')]),
    ]))
    story.append(t_detalhe)
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# =================================================================================
# INTERFACE STREAMLIT
# =================================================================================

def main():
    st.title("⚡ Auditor de Fatura Sunlux")
    st.markdown("Sistema de análise de faturas de energia elétrica para condomínios e empresas.")
    
    # Sidebar - Dados do Cliente
    with st.sidebar:
        st.header("🏢 Dados do Cliente")
        nome = st.text_input("Nome do Cliente", "Condomínio Exemplo")
        grupo = st.selectbox("Grupo Tarifário", ["A", "B"])
        concessionaria = st.text_input("Concessionária", "CEPISA")
        estado = st.text_input("Estado", "PI")
        
        st.divider()
        st.header("👤 Responsáveis")
        sindico = st.text_input("Nome do Síndico")
        engenheiro = st.text_input("Nome do Engenheiro")
    
    # Área Principal - Inserção de Dados
    if 'faturas' not in st.session_state:
        st.session_state.faturas = []
    
    with st.expander("📝 Adicionar Nova Fatura", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            mes = st.number_input("Mês", 1, 12, datetime.now().month)
            ano = st.number_input("Ano", 2020, 2030, datetime.now().year)
        with col2:
            ativo = st.number_input("Consumo Ativo (kWh)", 0.0)
            reativo = st.number_input("Consumo Reativo (kVArh)", 0.0)
            dem_contratada = st.number_input("Demanda Contratada (kW)", 0.0)
        with col3:
            dem_medida = st.number_input("Demanda Medida (kW)", 0.0)
            tarifa_ener = st.number_input("Tarifa Energia (R$/kWh)", 0.0)
            tarifa_dem = st.number_input("Tarifa Demanda (R$/kW)", 0.0)
            
        if st.button("Adicionar Fatura"):
            fp = AuditorFatura.calcular_fator_potencia(ativo, reativo)
            fatura = {
                'mes': mes, 'ano': ano,
                'consumo_ativo': ativo, 'consumo_reativo': reativo,
                'demanda_contratada': dem_contratada, 'demanda_medida': dem_medida,
                'fator_potencia': fp,
                'tarifa_energia': tarifa_energia, 'tarifa_demanda': tarifa_demanda,
                'valor_total': 0 # Simplificado
            }
            st.session_state.faturas.append(fatura)
            st.success("Fatura adicionada com sucesso!")

    # Exibição de Resultados
    if st.session_state.faturas:
        st.divider()
        st.header("📊 Resultados da Análise")
        
        # Processamento
        analises = [AuditorFatura.analisar_fatura(f) for f in st.session_state.faturas]
        total_multa_reativo = sum(a['multa_reativo'] for a in analises)
        total_multa_ultrapassagem = sum(a['multa_ultrapassagem'] for a in analises)
        economia_total = total_multa_reativo + total_multa_ultrapassagem
        
        # Métricas
        col1, col2, col3 = st.columns(3)
        col1.metric("Economia Potencial Total", f"R$ {economia_total:.2f}")
        col2.metric("Multas por Reativo", f"R$ {total_multa_reativo:.2f}")
        col3.metric("Multas por Ultrapassagem", f"R$ {total_multa_ultrapassagem:.2f}")
        
        # Tabela Detalhada
        df_res = pd.DataFrame([{
            'Período': a['periodo'],
            'Fator Potência': f"{a['fp']:.2f}",
            'Multa Reativo (R$)': f"{a['multa_reativo']:.2f}",
            'Uso Demanda (%)': f"{a['utilizacao_demanda']:.1f}%",
            'Multa Demanda (R$)': f"{a['multa_ultrapassagem']:.2f}",
            'Banco Cap. (kVAr)': a['banco_capacitores']['kvar_comercial']
        } for a in analises])
        
        st.dataframe(df_res, use_container_width=True)
        
        # Botão Gerar PDF
        st.divider()
        dados_auditoria = {
            'analises': analises,
            'resumo': {
                'economia_total': economia_total,
                'total_multa_reativo': total_multa_reativo,
                'total_multa_ultrapassagem': total_multa_ultrapassagem
            }
        }
        dados_cliente = {'nome': nome, 'grupo': grupo, 'concessionaria': concessionaria, 'estado': estado}
        
        pdf_buffer = gerar_pdf(dados_auditoria, dados_cliente)
        st.download_button(
            label="📄 Baixar Relatório PDF Completo",
            data=pdf_buffer,
            file_name="relatorio_auditoria_sunlux.pdf",
            mime="application/pdf"
        )

if __name__ == "__main__":
    main()
