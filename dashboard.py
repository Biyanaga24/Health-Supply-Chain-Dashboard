import streamlit as st
import pandas as pd
import numpy as np
import math
import plotly.express as px
import plotly.graph_objects as go

# ---------------------------------------------------
# PAGE SETUP
# ---------------------------------------------------
st.set_page_config(page_title="Health Program Supply Chain Dashboard", layout="wide")
st.title("Health Program Supply Chain Dashboard")

# ---------------------------------------------------
# FUNCTIONS
# ---------------------------------------------------
def clean_df(df):
    df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
    df.columns = df.columns.str.strip()
    df = df.replace({None:"", "None":""}).fillna("")
    return df

def format_qty(col):
    col = pd.to_numeric(col, errors="coerce")
    col = col.apply(lambda x: math.ceil(x) if pd.notna(x) else x)
    return col.apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "")

def format_mos(col):
    col = pd.to_numeric(col, errors="coerce").round(2)
    return col.apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")

def categorize_stock(nmos):
    try:
        x=float(nmos)
        if x<1:
            return "Stock Out"
        elif x<6:
            return "Understock"
        elif x<=18:
            return "Normal Stock"
        else:
            return "Overstock"
    except:
        return ""

# ---------------------------------------------------
# LOAD GOOGLE SHEETS
# ---------------------------------------------------
@st.cache_data
def load_google(sheet_id):
    url=f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    sheets=pd.read_excel(url,sheet_name=None,header=2)
    return {name:clean_df(df) for name,df in sheets.items()}

# ---------------------------------------------------
# LOAD EXTERNAL EXCEL
# ---------------------------------------------------
@st.cache_data
def load_external(file):
    sheets=pd.read_excel(file,sheet_name=None)
    dfs=[clean_df(df) for df in sheets.values() if "Material Description" in df.columns]
    return pd.concat(dfs,ignore_index=True)

# ---------------------------------------------------
# LOAD DATA
# ---------------------------------------------------
sheet_id="14VvZ7IyOmpM4SZrY5_ArHDgLkeFN4inW"
google_sheets=load_google(sheet_id)

uploaded_file=st.file_uploader("Upload Stock Excel File",type=["xlsx"])

if uploaded_file is None:
    st.warning("Upload stock Excel file")
    st.stop()

df_external=load_external(uploaded_file)

# ---------------------------------------------------
# PROGRAM SELECTION
# ---------------------------------------------------
sheet_name=st.sidebar.selectbox("Program",list(google_sheets.keys()))
df_google=google_sheets[sheet_name]

required_cols=[
'Material Description','AMC',
'GIT_PO','GIT_Qty','GIT_MOS',
'LC_PO','LC_Qty','LC_MOS',
'WB_PO','WB_Qty','WB_MOS',
'TMD_PO','TMD_Qty','TMD_MOS'
]

df_google=df_google[[c for c in required_cols if c in df_google.columns]]

# ---------------------------------------------------
# MERGE
# ---------------------------------------------------
df=df_external.merge(df_google,on="Material Description",how="inner")

if 'S/N' in df.columns:
    df=df.drop(columns=['S/N'])

# ---------------------------------------------------
# FORMAT
# ---------------------------------------------------
qty_cols=['AMC','GIT_Qty','LC_Qty','WB_Qty','TMD_Qty']
mos_cols=['NMOS','GIT_MOS','LC_MOS','WB_MOS','TMD_MOS']

for c in qty_cols:
    if c in df.columns:
        df[c]=format_qty(df[c])

for c in mos_cols:
    if c in df.columns:
        df[c]=format_mos(df[c])

# ---------------------------------------------------
# NMOS
# ---------------------------------------------------
if 'NSOH' in df.columns and 'AMC' in df.columns:
    nsoh=pd.to_numeric(df['NSOH'],errors='coerce')
    amc=pd.to_numeric(df['AMC'].str.replace(',',''),errors='coerce')
    nmos=np.where(amc!=0,nsoh/amc,np.nan)
    df['NMOS']=format_mos(pd.Series(nmos))

# ---------------------------------------------------
# STOCK STATUS
# ---------------------------------------------------
df['Stock Status']=df['NMOS'].apply(categorize_stock)

# ---------------------------------------------------
# RISK OF STOCK OUT
# ---------------------------------------------------
def risk(row):
    try:
        nmos=float(row['NMOS'])
        git=float(row.get('GIT_MOS',0))
        lc=float(row.get('LC_MOS',0))
        wb=float(row.get('WB_MOS',0))
        tmd=float(row.get('TMD_MOS',0))

        if nmos<4 and git==0:
            return "Risk of Stock Out"
        elif nmos<6 and lc==0 and wb==0:
            return "Risk of Stock Out"
        elif nmos<7 and lc==0 and wb==0 and tmd==0:
            return "Risk of Stock Out"
        else:
            return ""
    except:
        return ""

df['Risk of Stock']=df.apply(risk,axis=1)

# ---------------------------------------------------
# FILTERS
# ---------------------------------------------------
materials=["All"]+sorted(df['Material Description'].unique())
status=["All"]+sorted(df['Stock Status'].dropna().unique())

material_filter=st.sidebar.selectbox("Material",materials)
status_filter=st.sidebar.selectbox("Stock Status",status)

df_filtered=df.copy()

if material_filter!="All":
    df_filtered=df_filtered[df_filtered['Material Description']==material_filter]

if status_filter!="All":
    df_filtered=df_filtered[df_filtered['Stock Status']==status_filter]

# ---------------------------------------------------
# TABS
# ---------------------------------------------------
tab1,tab2=st.tabs(["Stock Table","KPIs"])

# ---------------------------------------------------
# TABLE
# ---------------------------------------------------
with tab1:

    hidden_cols=df_filtered.columns[1:22].tolist()

    if 'Expiry' in df_filtered.columns:
        hidden_cols.append('Expiry')

    st.dataframe(
        df_filtered,
        use_container_width=True,
        hide_index=True,
        column_config={c:{"hide":True} for c in hidden_cols}
    )

# ---------------------------------------------------
# KPIs
# ---------------------------------------------------
with tab2:

    nmos=pd.to_numeric(df_filtered['NMOS'],errors='coerce').dropna()

    availability=(nmos>1).mean()*100
    sap=((nmos>=6)&(nmos<=18)).mean()*100

    col1,col2=st.columns(2)

    def gauge(value,title):

        return go.Figure(go.Indicator(
            mode="gauge+number",
            value=value,
            number={'suffix':"%"},
            title={'text':title},
            gauge={'axis':{'range':[0,100]}}
        ))

    with col1:
        st.plotly_chart(gauge(availability,"Availability"))

    with col2:
        st.plotly_chart(gauge(sap,"Stock According to Plan"))

    # ---------------------------------------------------
    # PIE CHART
    # ---------------------------------------------------
    status_counts=df_filtered['Stock Status'].value_counts()

    fig=px.pie(
        values=status_counts.values,
        names=status_counts.index,
        hole=0.5,
        color=status_counts.index,
        color_discrete_map={
        "Stock Out":"red",
        "Understock":"yellow",
        "Normal Stock":"green",
        "Overstock":"skyblue"
        }
    )

    st.plotly_chart(fig,use_container_width=True)

    # ---------------------------------------------------
    # HORIZONTAL STACKED BAR
    # ---------------------------------------------------
    if all(c in df_filtered.columns for c in ['Hubs','Head Office','NSOH']):

        hubs=pd.to_numeric(df_filtered['Hubs'],errors='coerce').sum()
        ho=pd.to_numeric(df_filtered['Head Office'],errors='coerce').sum()
        nsoh=pd.to_numeric(df_filtered['NSOH'],errors='coerce').sum()

        hubs_pct=hubs/nsoh*100
        ho_pct=ho/nsoh*100

        fig_bar=go.Figure()

        fig_bar.add_bar(
        y=["Stock"],
        x=[hubs],
        orientation='h',
        name=f"Hubs {hubs_pct:.1f}% ({int(hubs):,})"
        )

        fig_bar.add_bar(
        y=["Stock"],
        x=[ho],
        orientation='h',
        name=f"Head Office {ho_pct:.1f}% ({int(ho):,})"
        )

        fig_bar.update_layout(
        barmode='stack',
        title="Share of NSOH: Hubs vs Head Office"
        )

        st.plotly_chart(fig_bar,use_container_width=True)

# ---------------------------------------------------
# DOWNLOAD
# ---------------------------------------------------
st.download_button(
"Download Data",
df_filtered.to_csv(index=False),
"stock_data.csv"
)
