import streamlit as st
import pandas as pd
import psycopg2
import os
from fpdf import FPDF
from datetime import datetime

st.set_page_config(page_title="AutoReport Pro", layout="wide")

def get_conn():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

st.title("📊 Painel de Faturamento Real-Time")

# Simulação de Login Simples para o Protótipo
api_key = st.sidebar.text_input("Insira sua API KEY para acessar", type="password")

if api_key:
    conn = get_conn()
    # Busca o ID do usuário e o nome da empresa
    query_user = "SELECT id, empresa FROM usuarios WHERE api_key = %s"
    user_data = pd.read_sql(query_user, conn, params=(api_key,))
    
    if not user_data.empty:
        u_id = user_data.iloc[0]['id']
        empresa = user_data.iloc[0]['empresa']
        st.sidebar.success(f"Conectado: {empresa}")

        # Busca as vendas
        df = pd.read_sql(f"SELECT produto, quantidade, preco, (quantidade*preco) as total, data_venda FROM vendas_live WHERE usuario_id = {u_id} ORDER BY data_venda DESC", conn)
        conn.close()

        if not df.empty:
            # KPIs
            col1, col2 = st.columns(2)
            col1.metric("Faturamento Total", f"MT {df['total'].sum():,.2f}")
            col2.metric("Total de Itens", int(df['quantidade'].sum()))

            # Gráfico
            st.subheader("Fluxo de Vendas")
            df['data_venda'] = pd.to_datetime(df['data_venda'])
            st.line_chart(df.set_index('data_venda')['total'])

            # Tabela
            st.dataframe(df, use_container_width=True)
            
            # Botão de PDF
            if st.button("Gerar Relatório PDF"):
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", "B", 16)
                pdf.cell(40, 10, f"Relatório de Vendas - {empresa}")
                pdf_bytes = pdf.output(dest='S').encode('latin-1')
                st.download_button("Baixar Relatório", pdf_bytes, "relatorio.pdf")
        else:
            st.info("Ainda não existem vendas registadas para esta conta.")
    else:
        st.error("API KEY inválida ou não encontrada.")
else:
    st.warning("Aguardando API KEY no menu lateral...")

