import streamlit as st
import pandas as pd
import numpy as np
import math
import plotly.express as px
import plotly.graph_objects as go

# ---------------------------------------------------
# Page Setup
# ---------------------------------------------------
st.set_page_config(page_title="Health Program Supply Chain Dashboard", layout="wide")
st.title("Health Program Supply Chain Dashboard")

# ---------------------------------------------------
# Utility Functions
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

def format_po(col):
    col = pd.to_numeric(col, errors="coerce").round(0)
    return col.apply(lambda x: f"{int(x)}" if pd.notna(x) else "")

def format_mos(col):
    col = pd.to_numeric(col, errors="coerce").round(2)
    return col.apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")

def categorize_stock(nmos):
    try:
        x = float(nmos)
        if x < 1:
            return "Stock Out"
        elif x < 6:
            return "Understock"
        elif x <= 18:
            return "Normal Stock"
        else:
            return "Overstock"
    except:
        return ""

# ---------------------------------------------------
# Load Google Sheets
# ---------------------------------------------------
@st.cache_data
def load_google(sheet_id):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    sheets = pd.read_excel(url, sheet_name=None, header=2)
    return {name: clean_df(df) for name, df in sheets.items()}

# ---------------------------------------------------
# Load External Excel
# ---------------------------------------------------
@st.cache_data
def load_external(path):
    sheets = pd.read_excel(path, sheet_name=None)
    dfs = [clean_df(df) for df in sheets.values() if "Material Description" in df.columns]
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

# ---------------------------------------------------
# Load Data
# ---------------------------------------------------
sheet_id = "14VvZ7IyOmpM4SZrY5_ArHDgLkeFN4inW"
external_path = r"C:\Users\BIYENSA.NEGERA\Hp_medicines_Stock_Final.xlsx"

google_sheets = load_google(sheet_id)
df_external = load_external(external_path)

if df_external.empty:
    st.error("External Excel contains no valid data.")
    st.stop()

# ---------------------------------------------------
# Sidebar Program Selection
# ---------------------------------------------------
sheet_name = st.sidebar.selectbox("Program", list(google_sheets.keys()))
df_google = google_sheets[sheet_name]

# ---------------------------------------------------
# Required Columns
# ---------------------------------------------------
required_cols = [
'Material Description','AMC',
'GIT_PO','GIT_Qty','GIT_MOS',
'LC_PO','LC_Qty','LC_MOS',
'WB_PO','WB_Qty','WB_MOS',
'TMD_PO','TMD_Qty','TMD_MOS',"Status"
]

df_google = df_google[[c for c in required_cols if c in df_google.columns]]

# ---------------------------------------------------
# Merge
# ---------------------------------------------------
df = df_external.merge(df_google, on="Material Description", how="inner")

if 'S/N' in df.columns:
    df = df.drop(columns=['S/N'])

df = df.set_index("Material Description")

# ---------------------------------------------------
# ---------------------------------------------------
# Format Columns
# ---------------------------------------------------
po_cols = ['GIT_PO','LC_PO','WB_PO','TMD_PO']
qty_cols = ['AMC','GIT_Qty','LC_Qty','WB_Qty','TMD_Qty']
mos_cols = ['NMOS','GIT_MOS','LC_MOS','WB_MOS','TMD_MOS']

# Keep PO columns as text without decimals
for c in po_cols:
    if c in df.columns:
        df[c] = df[c].apply(lambda x: str(int(x)) if pd.notna(x) and isinstance(x, (float, int)) else str(x).replace("nan",""))

# Format quantity and MOS columns
for c in qty_cols:
    if c in df.columns:
        df[c] = format_qty(df[c])

for c in mos_cols:
    if c in df.columns:
        df[c] = format_mos(df[c])

# ---------------------------------------------------
# Calculate NMOS
# ---------------------------------------------------
if 'NSOH' in df.columns and 'AMC' in df.columns and 'NMOS' not in df.columns:
    nsoh = pd.to_numeric(df['NSOH'], errors='coerce')
    amc = pd.to_numeric(df['AMC'].str.replace(',',''), errors='coerce')
    nmos = np.where(amc!=0, nsoh/amc, np.nan)
    df['NMOS'] = format_mos(pd.Series(nmos, index=df.index))

# ---------------------------------------------------
# Calculate TMOS
# ---------------------------------------------------
mos_numeric = pd.DataFrame()
for c in mos_cols:
    if c in df.columns:
        mos_numeric[c] = pd.to_numeric(df[c], errors="coerce")
if not mos_numeric.empty:
    df['TMOS'] = format_mos(mos_numeric.sum(axis=1))

# ---------------------------------------------------
# Stock Status
# ---------------------------------------------------
df['Stock Status'] = df['NMOS'].apply(categorize_stock)
df = df.reset_index()

# ---------------------------------------------------
# Risk of Stock
# ---------------------------------------------------
def calculate_risk(row):
    try:
        nmos = float(row['NMOS']) if row['NMOS'] not in ["", None] else np.nan
        git_mos = float(row['GIT_MOS']) if row.get('GIT_MOS', "") not in ["", None] else np.nan
        lc_mos = float(row['LC_MOS']) if row.get('LC_MOS', "") not in ["", None] else np.nan
        wb_mos = float(row['WB_MOS']) if row.get('WB_MOS', "") not in ["", None] else np.nan
        tmd_mos = float(row['TMD_MOS']) if row.get('TMD_MOS', "") not in ["", None] else np.nan

        # Rule 1
        if nmos < 4 and git_mos == 0:
            return "Risk of Stock Out"
        # Rule 2
        elif nmos < 6 and lc_mos == 0 and wb_mos == 0:
            return "Risk of Stock Out"
        # Rule 3
        elif nmos < 7 and lc_mos == 0 and wb_mos == 0 and tmd_mos == 0:
            return "Risk of Stock Out"
        else:
            return ""
    except:
        return ""

df['Risk of Stock'] = df.apply(calculate_risk, axis=1)

# ---------------------------------------------------
# Sidebar Filters
# ---------------------------------------------------
materials = ["All"] + sorted(df['Material Description'].unique())
statuses = ["All"] + sorted(df['Stock Status'].replace("",np.nan).dropna().unique())
risk_filter_options = ["All", "Risk of Stock Out"]

material_filter = st.sidebar.selectbox("Material Description", materials)
status_filter = st.sidebar.selectbox("Stock Status", statuses)
risk_filter = st.sidebar.selectbox("Risk of Stock", risk_filter_options)

df_filtered = df.copy()
if material_filter != "All":
    df_filtered = df_filtered[df_filtered['Material Description']==material_filter]
if status_filter != "All":
    df_filtered = df_filtered[df_filtered['Stock Status']==status_filter]
if risk_filter != "All":
    df_filtered = df_filtered[df_filtered['Risk of Stock']==risk_filter]

# ---------------------------------------------------
# Tabs
# ---------------------------------------------------
tab1, tab2 = st.tabs(["Stock Table","KPIs"])

# ---------------------------------------------------
# TAB 1 TABLE
# ---------------------------------------------------
with tab1:

    # Reorder columns: NMOS after AMC, Risk of Stock after Stock Status
    cols = list(df_filtered.columns)
    if 'NMOS' in cols and 'AMC' in cols:
        cols.insert(cols.index('AMC') + 1, cols.pop(cols.index('NMOS')))
    if 'Risk of Stock' in cols and 'Stock Status' in cols:
        cols.insert(cols.index('Stock Status') + 1, cols.pop(cols.index('Risk of Stock')))
    df_filtered = df_filtered[cols]

    def color_row(row):
        colors = {
            "Stock Out":"background-color:red;color:white",
            "Understock":"background-color:yellow",
            "Normal Stock":"background-color:green;color:white",
            "Overstock":"background-color:skyblue"
        }
        styles=['']*len(row)
        idx=row.index.get_loc('Material Description')
        styles[idx]=colors.get(row['Stock Status'],'')
        return styles

    styled = df_filtered.style.apply(color_row, axis=1)

    # Hide columns 2–22 by default but expandable
    hidden_cols = df_filtered.columns[1:22].tolist()
    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        height=(len(df_filtered)+1)*35,
        column_config={col: {"hide": True} for col in hidden_cols}  # Streamlit >=1.26.0
    )

# ---------------------------------------------------
# TAB 2 KPIs & Pie Chart
# ---------------------------------------------------
with tab2:

    nmos = pd.to_numeric(df_filtered['NMOS'], errors='coerce').dropna()
    availability = (nmos>1).mean()*100 if len(nmos)>0 else 0
    sap = ((nmos>=6)&(nmos<=18)).mean()*100 if len(nmos)>0 else 0

    availability_target = 100
    sap_target = 65
    col1, col2 = st.columns(2)

    def create_kpi_fig(value, target, title):
        display_color = 'red' if value < target else 'black'
        return go.Figure(go.Indicator(
            mode="gauge+number",
            value=value,
            number={
                'suffix': "%",
                'font': {'size': 36, 'color': display_color, 'family': 'Arial', 'weight':'bold'}
            },
            title={
                'text': f"<b>{title} KPI</b>",
                'font': {'size': 24, 'family': 'Arial', 'weight':'bold'}
            },
            gauge={
                'axis': {'range':[0,100]},
                'bar': {'color':'skyblue'},
                'bgcolor': "lightgray",
                'borderwidth': 2,
                'bordercolor': "gray"
            }
        ))

    with col1:
        fig_availability = create_kpi_fig(availability, availability_target, "Availability")
        st.plotly_chart(fig_availability, use_container_width=True)
    with col2:
        fig_sap = create_kpi_fig(sap, sap_target, "SAP")
        st.plotly_chart(fig_sap, use_container_width=True)

    # ---------------------------
    # Stock Status Pie Chart
    # ---------------------------
    try:
        status_counts = df_filtered['Stock Status'].replace("", np.nan).dropna().value_counts()
        status_counts = status_counts.astype(int)
        if not status_counts.empty:
            total_count = status_counts.sum()
            fig = px.pie(
                values=status_counts.values,
                names=status_counts.index.astype(str),
                hole=0.5,
                color=status_counts.index.astype(str),
                color_discrete_map={
                    "Stock Out":"red",
                    "Understock":"yellow",
                    "Normal Stock":"green",
                    "Overstock":"skyblue"
                },
            )
            fig.update_traces(
                textposition='inside',
                textinfo='percent+value',
                insidetextfont={'size':16, 'color':'black'}
            )
            fig.add_annotation(
                dict(
                    text=f"Total:<br>{total_count}",
                    x=0.5, y=0.5, showarrow=False,
                    font_size=20,
                    font_color='black'
                )
            )
            fig.update_layout(
                title={'text':"<b>Stock Status</b>", 'x':0.5, 'xanchor':'center', 'font':{'size':24}},
                legend_title_text='Status',
                legend={'font':{'size':14}}
            )
            st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Pie chart could not be displayed: {e}")

# ---------------------------------------------------
# Download
# ---------------------------------------------------
st.divider()
st.download_button(
    "Download Filtered Data",
    df_filtered.to_csv(index=False),
    "stock_dashboard.csv",
    "text/csv"
)
