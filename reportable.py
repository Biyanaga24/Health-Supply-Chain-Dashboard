import streamlit as st
import pandas as pd
import requests
import re
from io import StringIO, BytesIO
from datetime import datetime, timedelta
from supabase import create_client
import openpyxl

# Page configuration
st.set_page_config(
    page_title="Health Program Commodities Supply Information",
    page_icon="📊",
    layout="wide"
)

# Supabase Configuration
SUPABASE_URL = "https://etjfrptbjecafupbbase.supabase.co"
SUPABASE_KEY = "sb_publishable_j0JwaJAJBuJO79-xh7RkYg_PFKqLK1H"
TABLE_NAME = "gashew_stock_status"

# Initialize Supabase client
@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# Initialize session state
if 'excel_data' not in st.session_state:
    st.session_state.excel_data = None
if 'sheet_data' not in st.session_state:
    st.session_state.sheet_data = None
if 'conversion_data' not in st.session_state:
    st.session_state.conversion_data = None
if 'merged_data' not in st.session_state:
    st.session_state.merged_data = None
if 'filtered_data' not in st.session_state:
    st.session_state.filtered_data = None
if 'excel_loaded' not in st.session_state:
    st.session_state.excel_loaded = False
if 'sheet_loaded' not in st.session_state:
    st.session_state.sheet_loaded = False
if 'conversion_loaded' not in st.session_state:
    st.session_state.conversion_loaded = False
if 'merge_clicked' not in st.session_state:
    st.session_state.merge_clicked = False
if 'excel_file' not in st.session_state:
    st.session_state.excel_file = None
if 'national_stock_data' not in st.session_state:
    st.session_state.national_stock_data = None
if 'pipeline_stock_data' not in st.session_state:
    st.session_state.pipeline_stock_data = None
if 'pipeline_editable_data' not in st.session_state:
    st.session_state.pipeline_editable_data = None
if 'items_data' not in st.session_state:
    st.session_state.items_data = None
if 'items_loaded' not in st.session_state:
    st.session_state.items_loaded = False
if 'items_merged_data' not in st.session_state:
    st.session_state.items_merged_data = None
if 'items_filtered_data' not in st.session_state:
    st.session_state.items_filtered_data = None
if 'items_merge_clicked' not in st.session_state:
    st.session_state.items_merge_clicked = False
if 'items_national_stock_data' not in st.session_state:
    st.session_state.items_national_stock_data = None
if 'items_file' not in st.session_state:
    st.session_state.items_file = None
if 'monthly_issue_data' not in st.session_state:
    st.session_state.monthly_issue_data = None
if 'selected_programs' not in st.session_state:
    st.session_state.selected_programs = []
if 'selected_sub_categories' not in st.session_state:
    st.session_state.selected_sub_categories = []
if 'selected_risk_levels' not in st.session_state:
    st.session_state.selected_risk_levels = []
if 'date_range' not in st.session_state:
    st.session_state.date_range = None
if 'a_amc_data' not in st.session_state:
    st.session_state.a_amc_data = {}
if 'supabase_loaded' not in st.session_state:
    st.session_state.supabase_loaded = False

# Default Google Sheet URLs
DEFAULT_MASTER_URL = "https://docs.google.com/spreadsheets/d/1XXLdIN6xwuAgmor-tkMgBgeDlxGqANFasshm6UVA6Wg/edit?gid=0#gid=0"
DEFAULT_CONVERSION_URL = "https://docs.google.com/spreadsheets/d/1XXLdIN6xwuAgmor-tkMgBgeDlxGqANFasshm6UVA6Wg/edit?gid=1596962045#gid=1596962045"

# --- Function to calculate Risk Level ---
def calculate_risk_level(current_mos, edd_date):
    """
    Calculate Risk Level based on Current MOS and EDD.
    """
    # If Current MOS is 0 or negative, return High risk
    if current_mos <= 0:
        return "High"

    # Convert EDD to datetime if it's a string
    if isinstance(edd_date, str):
        try:
            edd_date = pd.to_datetime(edd_date, errors='coerce')
        except:
            return "Medium"

    # If EDD is None or NaT, calculate based on Current MOS only
    if edd_date is None or pd.isna(edd_date):
        if current_mos < 2:
            return "High"
        elif current_mos < 4:
            return "Medium"
        else:
            return "Low"

    # Calculate months until EDD
    today = pd.Timestamp.now().normalize()
    months_until_edd = (edd_date - today).days / 30.44

    # Determine Risk Level based on both Current MOS and EDD
    if current_mos >= 4 and months_until_edd <= 2:
        return "Low"
    elif 2 <= current_mos < 4 and 2 <= months_until_edd <= 4:
        return "Medium"
    elif current_mos < 2 and months_until_edd > 4:
        return "High"
    else:
        if current_mos >= 4:
            return "Low"
        elif current_mos >= 2:
            return "Medium"
        else:
            return "High"

# --- Function to load Google Sheet as CSV ---
def load_google_sheet(sheet_url):
    """Convert Google Sheets sharing link to CSV export URL and load it."""
    try:
        if '/d/' in sheet_url:
            file_id = sheet_url.split('/d/')[1].split('/')[0]
        else:
            import re
            match = re.search(r'/d/([^/]+)', sheet_url)
            if match:
                file_id = match.group(1)
            else:
                raise ValueError("Could not extract file ID from URL")

        csv_url = f'https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv'

        response = requests.get(csv_url)
        response.raise_for_status()

        df = pd.read_csv(StringIO(response.text))

        if len(df.columns) > 0:
            first_col = df.columns[0]
            if df[first_col].dtype in ['int64', 'float64']:
                if (df[first_col] == range(1, len(df) + 1)).all():
                    df = df.drop(columns=[first_col])

        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"Failed to load Google Sheet: {e}")
        return None

# --- Function to format date columns (remove time) ---
def format_date_columns(df):
    """Format date columns to show only date without time."""
    if df is None or df.empty:
        return df

    date_columns = [col for col in df.columns if 'date' in col.lower() or 'delivery' in col.lower() or 'expiration' in col.lower() or 'expiry' in col.lower() or 'shelf life' in col.lower()]

    for col in date_columns:
        if col in df.columns:
            try:
                df[col] = pd.to_datetime(df[col], errors='coerce')
                df[col] = df[col].dt.strftime('%Y-%m-%d')
            except:
                pass

    return df

# --- Function to create Expiry Date column (MMM_YYYY format) ---
def create_expiry_date_column(df):
    """Create Expiry Date column from Shelf Life Expiration Date or Delivery Date in MMM_YYYY format."""
    if df is None or df.empty:
        return df

    expiry_col = None
    for col in df.columns:
        col_lower = col.lower()
        if 'expiration' in col_lower or 'expiry' in col_lower or 'shelf life' in col_lower or 'delivery' in col_lower:
            expiry_col = col
            break

    if expiry_col:
        try:
            df[expiry_col] = pd.to_datetime(df[expiry_col], errors='coerce')
            df[expiry_col] = df[expiry_col].dt.strftime('%Y-%m-%d')
            df['Expiry Date'] = pd.to_datetime(df[expiry_col], errors='coerce').dt.strftime('%b_%Y')
        except Exception as e:
            df['Expiry Date'] = ''
    else:
        df['Expiry Date'] = ''

    return df

# --- Function to calculate Plant Stock ---
def calculate_plant_stock(df):
    """Calculate Plant Stock by summing Unrestricted Stock, Stock in Quality Inspection, and Stock in Transit, or from Quantity column."""
    if df is None or df.empty:
        return df

    df['Plant Stock'] = 0

    # Check if this is Items.xlsx data (has Quantity column)
    quantity_col = None
    for col in df.columns:
        if 'quantity' in col.lower() or 'qty' in col.lower():
            quantity_col = col
            break

    if quantity_col:
        # Items.xlsx - use Quantity as Plant Stock
        df['Plant Stock'] = pd.to_numeric(df[quantity_col], errors='coerce').fillna(0)
        return df

    # Materials.xlsx - sum Unrestricted, Quality Inspection, and Transit
    unrestricted_col = None
    quality_inspection_col = None
    transit_col = None

    for col in df.columns:
        col_lower = col.lower()
        if 'unrestricted' in col_lower:
            unrestricted_col = col
        elif 'quality inspection' in col_lower or 'quality' in col_lower:
            quality_inspection_col = col
        elif 'transit' in col_lower:
            transit_col = col

    stock_columns = []
    if unrestricted_col and unrestricted_col in df.columns:
        df[unrestricted_col] = pd.to_numeric(df[unrestricted_col], errors='coerce').fillna(0)
        stock_columns.append(unrestricted_col)
    if quality_inspection_col and quality_inspection_col in df.columns:
        df[quality_inspection_col] = pd.to_numeric(df[quality_inspection_col], errors='coerce').fillna(0)
        stock_columns.append(quality_inspection_col)
    if transit_col and transit_col in df.columns:
        df[transit_col] = pd.to_numeric(df[transit_col], errors='coerce').fillna(0)
        stock_columns.append(transit_col)

    if stock_columns:
        df['Plant Stock'] = df[stock_columns].sum(axis=1)

    return df

# --- Function to load data from Supabase ---
def load_supabase_data():
    """Load pipeline stock status data from Supabase."""
    try:
        response = supabase.table(TABLE_NAME).select('*').execute()
        if response.data:
            return pd.DataFrame(response.data)
        return None
    except Exception as e:
        st.error(f"Error loading from Supabase: {e}")
        return None

# --- Function to save only changed data to Supabase ---
def save_supabase_data(original_df, edited_df):
    """Save only changed rows to Supabase."""
    try:
        def safe_float(val):
            try:
                return float(val) if val and val != '' else 0
            except:
                return 0

        changed_records = []

        # Compare each row
        for idx, edited_row in edited_df.iterrows():
            material = str(edited_row.get('Material', ''))

            # Get original row for comparison
            original_row = original_df[original_df['Material'] == material]

            if not original_row.empty:
                # Check if any editable field changed
                original = original_row.iloc[0]
                changed = False

                # Check each editable field (excluding Risk Level which is auto-calculated)
                editable_fields = {
                    'adjusted_amc': 'Adjusted AMC',
                    'quantity': 'Quantity',
                    'edd': 'EDD',
                    'procurement_agency': 'Procurement Agency',
                    'pipeline_status': 'Pipeline Status',
                    'mitigation_plan': 'Mitigation Plan',
                    'risk_response_status': 'Risk Response Status',
                    'remark': 'Remark'
                }

                for db_field, display_field in editable_fields.items():
                    old_val = original.get(display_field, '')
                    new_val = edited_row.get(display_field, '')

                    # Convert to string for comparison
                    if str(old_val) != str(new_val):
                        changed = True
                        break

                if changed:
                    # Build record with only changed fields
                    record = {'material': material}

                    for db_field, display_field in editable_fields.items():
                        val = edited_row.get(display_field, '')
                        if db_field in ['adjusted_amc', 'quantity']:
                            record[db_field] = safe_float(val)
                        else:
                            record[db_field] = str(val) if val else ''

                    changed_records.append(record)
            else:
                # New record - insert all editable fields
                record = {'material': material}
                for db_field, display_field in editable_fields.items():
                    val = edited_row.get(display_field, '')
                    if db_field in ['adjusted_amc', 'quantity']:
                        record[db_field] = safe_float(val)
                    else:
                        record[db_field] = str(val) if val else ''
                changed_records.append(record)

        if not changed_records:
            return True, 0  # No changes

        # Save only changed records
        saved_count = 0
        for record in changed_records:
            # Check if record exists
            check = supabase.table(TABLE_NAME).select('*').eq('material', record.get('material')).execute()

            if check.data:
                # Update existing record
                supabase.table(TABLE_NAME).update(record).eq('material', record.get('material')).execute()
            else:
                # Insert new record
                supabase.table(TABLE_NAME).insert(record).execute()
            saved_count += 1

        return True, saved_count
    except Exception as e:
        st.error(f"Error saving to Supabase: {e}")
        return False, 0

# --- Function to create Pipeline Stock Status ---
def create_pipeline_stock_status(df, a_amc_data=None):
    """
    Create Health Program Commodities National and Pipeline Stock Status.
    """
    if df is None or df.empty:
        return None

    # First, ensure Plant Stock exists
    df = df.copy()

    if 'Plant Stock' not in df.columns:
        quantity_col = None
        for col in df.columns:
            if 'quantity' in col.lower() or 'qty' in col.lower():
                quantity_col = col
                break
        if quantity_col:
            df['Plant Stock'] = pd.to_numeric(df[quantity_col], errors='coerce').fillna(0)
        else:
            df['Plant Stock'] = 0

    # Find Material column
    material_col = None
    for col in df.columns:
        col_lower = col.lower()
        if 'material code' in col_lower or 'material' in col_lower:
            material_col = col
            break

    if not material_col:
        return None

    # Rename to 'Material' for consistency
    if material_col != 'Material':
        df['Material'] = df[material_col]

    # Find Material Description column
    material_desc_col = None
    for col in df.columns:
        col_lower = col.lower()
        if 'material descr' in col_lower or 'material description' in col_lower or 'description' in col_lower:
            material_desc_col = col
            break

    if material_desc_col and material_desc_col != 'Material Description':
        df['Material Description'] = df[material_desc_col]
    elif 'Material Description' not in df.columns:
        df['Material Description'] = ''

    # Find Plant Name column
    plant_name_col = None
    for col in df.columns:
        col_lower = col.lower()
        if col_lower == 'plant name':
            plant_name_col = col
            break

    if not plant_name_col:
        for col in df.columns:
            col_lower = col.lower()
            if 'plant' in col_lower:
                plant_name_col = col
                break

    if not plant_name_col:
        df['Plant Name'] = 'Default Plant'
        plant_name_col = 'Plant Name'
    else:
        if plant_name_col != 'Plant Name':
            df['Plant Name'] = df[plant_name_col]

    # Ensure Plant Stock is numeric
    df['Plant Stock'] = pd.to_numeric(df['Plant Stock'], errors='coerce').fillna(0)

    # Ensure Expiry Date exists
    if 'Expiry Date' not in df.columns:
        df['Expiry Date'] = ''
    else:
        df['Expiry Date'] = df['Expiry Date'].fillna('')

    # Filter to keep only rows where Plant Stock > 0
    df_filtered = df[df['Plant Stock'] > 0]

    if df_filtered.empty:
        return None

    # Group by Material, Material Description, Plant Name, and Expiry Date
    grouped = df_filtered.groupby(['Material', 'Material Description', 'Plant Name', 'Expiry Date'], as_index=False).agg({
        'Plant Stock': 'sum'
    })

    # Create pivot table
    pivot = grouped.pivot_table(
        index=['Material', 'Material Description'],
        columns='Plant Name',
        values='Plant Stock',
        fill_value=0,
        aggfunc='sum'
    ).reset_index()

    # Get all plant columns
    plant_columns = [col for col in pivot.columns if col not in ['Material', 'Material Description']]

    # Separate Head Office from other branches
    head_office_col = None
    branch_cols = []

    for col in plant_columns:
        if 'head' in col.lower() or 'HO' in col.upper() or 'head office' in col.lower():
            head_office_col = col
        else:
            branch_cols.append(col)

    # Calculate Hubs' SOH (sum of all branches except Head Office)
    pivot['Hubs\' SOH'] = pivot[branch_cols].sum(axis=1) if branch_cols else 0

    # Calculate NSOH
    pivot['NSOH'] = pivot[plant_columns].sum(axis=1)

    # Create Expiry Date string
    expiry_agg = grouped.groupby(['Material', 'Material Description', 'Expiry Date'], as_index=False).agg({
        'Plant Stock': 'sum'
    })

    def create_expiry_string(group):
        expiry_parts = []
        for idx in range(len(group)):
            row = group.iloc[idx]
            if pd.notna(row['Expiry Date']) and row['Expiry Date'] != '':
                stock_formatted = f"{row['Plant Stock']:,.0f}"
                expiry_parts.append(f"{stock_formatted} ({row['Expiry Date']})")

        if expiry_parts:
            expiry_parts.sort(key=lambda x: x.split('(')[1].strip(')') if '(' in x else '')
            return ', '.join(expiry_parts)
        return ''

    expiry_grouped = expiry_agg.groupby(['Material', 'Material Description'], as_index=False)

    expiry_strings = []
    for name, group in expiry_grouped:
        expiry_string = create_expiry_string(group)
        expiry_strings.append({
            'Material': name[0],
            'Material Description': name[1],
            'Expiry Date': expiry_string
        })

    expiry_df = pd.DataFrame(expiry_strings)
    final_df = pivot.merge(expiry_df, on=['Material', 'Material Description'], how='left')
    final_df['Expiry Date'] = final_df['Expiry Date'].fillna('')

    # Add A_AMC column from a_amc_data
    final_df['A_AMC'] = 0.0
    if a_amc_data:
        for idx, row in final_df.iterrows():
            material_desc = row['Material Description']
            if material_desc in a_amc_data:
                final_df.at[idx, 'A_AMC'] = float(a_amc_data[material_desc])

    # Add editable columns (will be filled from Supabase)
    final_df['Adjusted AMC'] = ''
    final_df['Quantity'] = ''
    final_df['EDD'] = ''
    final_df['Procurement Agency'] = ''
    final_df['Pipeline Status'] = ''
    final_df['Risk Level'] = ''
    final_df['Mitigation Plan'] = ''
    final_df['Risk Response Status'] = ''
    final_df['Remark'] = ''

    # Calculated columns
    final_df['Current MOS'] = 0.0
    final_df['Pipeline MOS'] = 0.0
    final_df['Total MOS'] = 0.0

    # Load only editable fields from Supabase (excluding Risk Level)
    saved_data = load_supabase_data()
    if saved_data is not None and not saved_data.empty:
        for idx, row in final_df.iterrows():
            material = row['Material']
            saved_row = saved_data[saved_data['material'] == material]
            if not saved_row.empty:
                # Load only editable fields
                final_df.at[idx, 'Adjusted AMC'] = str(saved_row.iloc[0].get('adjusted_amc', '')) if saved_row.iloc[0].get('adjusted_amc') else ''
                final_df.at[idx, 'Quantity'] = str(saved_row.iloc[0].get('quantity', '')) if saved_row.iloc[0].get('quantity') else ''
                final_df.at[idx, 'EDD'] = str(saved_row.iloc[0].get('edd', '')) if saved_row.iloc[0].get('edd') else ''
                final_df.at[idx, 'Procurement Agency'] = str(saved_row.iloc[0].get('procurement_agency', '')) if saved_row.iloc[0].get('procurement_agency') else ''
                final_df.at[idx, 'Pipeline Status'] = str(saved_row.iloc[0].get('pipeline_status', '')) if saved_row.iloc[0].get('pipeline_status') else ''
                final_df.at[idx, 'Mitigation Plan'] = str(saved_row.iloc[0].get('mitigation_plan', '')) if saved_row.iloc[0].get('mitigation_plan') else ''
                final_df.at[idx, 'Risk Response Status'] = str(saved_row.iloc[0].get('risk_response_status', '')) if saved_row.iloc[0].get('risk_response_status') else ''
                final_df.at[idx, 'Remark'] = str(saved_row.iloc[0].get('remark', '')) if saved_row.iloc[0].get('remark') else ''

    # Calculate MOS fields and Risk Level
    for idx, row in final_df.iterrows():
        adjusted_amc = row['Adjusted AMC']
        # Convert to float if it's a string
        if isinstance(adjusted_amc, str):
            try:
                adjusted_amc = float(adjusted_amc) if adjusted_amc else 0
            except:
                adjusted_amc = 0
        elif isinstance(adjusted_amc, (int, float)):
            adjusted_amc = float(adjusted_amc)
        else:
            adjusted_amc = 0

        current_mos = 0.0
        if adjusted_amc > 0:
            nsoh = float(row['NSOH']) if row['NSOH'] else 0
            quantity = row['Quantity']
            if isinstance(quantity, str):
                try:
                    quantity = float(quantity) if quantity else 0
                except:
                    quantity = 0
            elif isinstance(quantity, (int, float)):
                quantity = float(quantity)
            else:
                quantity = 0

            current_mos = round(nsoh / adjusted_amc, 2)
            final_df.at[idx, 'Current MOS'] = current_mos
            final_df.at[idx, 'Pipeline MOS'] = round(quantity / adjusted_amc, 2)
            final_df.at[idx, 'Total MOS'] = round((nsoh + quantity) / adjusted_amc, 2)
        else:
            final_df.at[idx, 'Current MOS'] = 0.0
            final_df.at[idx, 'Pipeline MOS'] = 0.0
            final_df.at[idx, 'Total MOS'] = 0.0

        # Calculate Risk Level based on Current MOS and EDD
        edd = row['EDD']
        final_df.at[idx, 'Risk Level'] = calculate_risk_level(current_mos, edd)

    # Keep only required columns
    keep_columns = [
        'Material', 'Material Description', 'Hubs\' SOH', 'NSOH', 'Expiry Date',
        'A_AMC', 'Adjusted AMC', 'Current MOS', 'Quantity', 'EDD', 
        'Pipeline MOS', 'Total MOS', 'Procurement Agency', 'Pipeline Status',
        'Risk Level', 'Mitigation Plan', 'Risk Response Status', 'Remark'
    ]

    # Insert Head Office after Hubs' SOH if it exists
    if head_office_col and head_office_col in final_df.columns:
        hubs_pos = keep_columns.index('Hubs\' SOH')
        keep_columns.insert(hubs_pos + 1, 'Head Office')

    # Filter to only keep these columns
    final_df = final_df[[col for col in keep_columns if col in final_df.columns]]
    final_df = final_df.sort_values('Material Description', ascending=True).reset_index(drop=True)

    return final_df

# --- Function to create National Stock Status as Pivot Table ---
def create_national_stock_status(df, include_nsoh=True, include_expiry=True, is_issue_data=False):
    """
    Create Health Program National Stock Status as a pivot table.
    """
    if df is None or df.empty:
        return None

    # First, ensure Plant Stock exists - calculate it from Quantity if needed
    df = df.copy()

    # Check if Plant Stock exists, if not, calculate it from Quantity
    if 'Plant Stock' not in df.columns:
        quantity_col = None
        for col in df.columns:
            if 'quantity' in col.lower() or 'qty' in col.lower():
                quantity_col = col
                break
        if quantity_col:
            df['Plant Stock'] = pd.to_numeric(df[quantity_col], errors='coerce').fillna(0)
        else:
            df['Plant Stock'] = 0

    # Find Material column
    material_col = None
    for col in df.columns:
        col_lower = col.lower()
        if 'material code' in col_lower or 'material' in col_lower:
            material_col = col
            break

    if not material_col:
        return None

    # Rename to 'Material' for consistency
    if material_col != 'Material':
        df['Material'] = df[material_col]

    # Find Material Description column
    material_desc_col = None
    for col in df.columns:
        col_lower = col.lower()
        if 'material descr' in col_lower or 'material description' in col_lower or 'description' in col_lower:
            material_desc_col = col
            break

    if material_desc_col and material_desc_col != 'Material Description':
        df['Material Description'] = df[material_desc_col]
    elif 'Material Description' not in df.columns:
        df['Material Description'] = ''

    # Find Plant Name column - prioritize "Plant Name" over "Plant"
    plant_name_col = None
    for col in df.columns:
        col_lower = col.lower()
        if col_lower == 'plant name':
            plant_name_col = col
            break

    # If "Plant Name" not found, try "Plant"
    if not plant_name_col:
        for col in df.columns:
            col_lower = col.lower()
            if 'plant' in col_lower:
                plant_name_col = col
                break

    # If no Plant column found, use a default
    if not plant_name_col:
        df['Plant Name'] = 'Default Plant'
        plant_name_col = 'Plant Name'
    else:
        if plant_name_col != 'Plant Name':
            df['Plant Name'] = df[plant_name_col]

    # Ensure Plant Stock is numeric
    df['Plant Stock'] = pd.to_numeric(df['Plant Stock'], errors='coerce').fillna(0)

    # Ensure Expiry Date exists (fill NaN with empty string for grouping)
    if 'Expiry Date' not in df.columns:
        df['Expiry Date'] = ''
    else:
        df['Expiry Date'] = df['Expiry Date'].fillna('')

    # Filter to keep only rows where Plant Stock > 0
    df_filtered = df[df['Plant Stock'] > 0]

    # If no data remains, return None
    if df_filtered.empty:
        return None

    # Group by Material, Material Description, Plant Name, and Expiry Date to sum stock
    grouped = df_filtered.groupby(['Material', 'Material Description', 'Plant Name', 'Expiry Date'], as_index=False).agg({
        'Plant Stock': 'sum'
    })

    # Create pivot table with Plant Names as columns
    pivot = grouped.pivot_table(
        index=['Material', 'Material Description'],
        columns='Plant Name',
        values='Plant Stock',
        fill_value=0,
        aggfunc='sum'
    ).reset_index()

    # Get all plant columns
    plant_columns = [col for col in pivot.columns if col not in ['Material', 'Material Description']]

    # Separate Head Office from other branches
    head_office_col = None
    branch_cols = []

    for col in plant_columns:
        if 'head' in col.lower() or 'HO' in col.upper() or 'head office' in col.lower():
            head_office_col = col
        else:
            branch_cols.append(col)

    # Calculate Hubs' SOH (sum of all branches except Head Office)
    hubs_soh_col_name = 'Total Issue' if is_issue_data else 'Hubs\' SOH'
    pivot[hubs_soh_col_name] = pivot[branch_cols].sum(axis=1) if branch_cols else 0

    # Calculate NSOH (sum of all plants including Head Office)
    if include_nsoh:
        pivot['NSOH'] = pivot[plant_columns].sum(axis=1)

    # Reorder columns - Hubs' SOH and Head Office should come before NSOH
    new_column_order = ['Material', 'Material Description']

    # Add Hubs' SOH (or Total Issue)
    new_column_order.append(hubs_soh_col_name)

    # Add Head Office if it exists and NOT issue data
    if head_office_col and not is_issue_data:
        new_column_order.append(head_office_col)

    # Add all branch columns (excluding Head Office)
    new_column_order.extend([col for col in plant_columns if col != head_office_col])

    # Add NSOH after branches
    if include_nsoh:
        new_column_order.append('NSOH')

    # Add Expiry Date if included
    if include_expiry:
        # Create Expiry Date string for each material
        expiry_agg = grouped.groupby(['Material', 'Material Description', 'Expiry Date'], as_index=False).agg({
            'Plant Stock': 'sum'
        })

        def create_expiry_string(group):
            expiry_parts = []
            for idx in range(len(group)):
                row = group.iloc[idx]
                if pd.notna(row['Expiry Date']) and row['Expiry Date'] != '':
                    stock_formatted = f"{row['Plant Stock']:,.0f}"
                    expiry_parts.append(f"{stock_formatted} ({row['Expiry Date']})")

            if expiry_parts:
                expiry_parts.sort(key=lambda x: x.split('(')[1].strip(')') if '(' in x else '')
                return ', '.join(expiry_parts)
            return ''

        expiry_grouped = expiry_agg.groupby(['Material', 'Material Description'], as_index=False)

        expiry_strings = []
        for name, group in expiry_grouped:
            expiry_string = create_expiry_string(group)
            expiry_strings.append({
                'Material': name[0],
                'Material Description': name[1],
                'Expiry Date': expiry_string
            })

        expiry_df = pd.DataFrame(expiry_strings)
        final_df = pivot.merge(expiry_df, on=['Material', 'Material Description'], how='left')
        final_df['Expiry Date'] = final_df['Expiry Date'].fillna('')

        # Add Expiry Date to column order
        new_column_order.append('Expiry Date')
    else:
        final_df = pivot.copy()

    # Reorder columns
    existing_columns = [col for col in new_column_order if col in final_df.columns]
    remaining_columns = [col for col in final_df.columns if col not in existing_columns]
    final_column_order = existing_columns + remaining_columns

    final_df = final_df[final_column_order]
    final_df = final_df.sort_values('Material Description', ascending=True).reset_index(drop=True)

    return final_df

# --- Function to create Plant Stock Vs Issue Quantity ---
def create_plant_stock_vs_issue(stock_df, issue_df):
    """
    Create Plant Stock Vs Issue Quantity comparison table.
    """
    if stock_df is None or stock_df.empty:
        return None, None
    if issue_df is None or issue_df.empty:
        return None, None

    # Function to normalize branch name (remove code in parentheses)
    def normalize_branch_name(name):
        if not name:
            return name
        normalized = re.sub(r'\s*\([^)]*\)$', '', name)
        return normalized.strip()

    # Create copies
    stock_df = stock_df.copy()
    issue_df = issue_df.copy()

    # Get all branch columns from stock data
    stock_skip_cols = ['Material', 'Material Description', 'Hubs\' SOH', 'NSOH', 'Expiry Date', 'A_AMC', 'Adjusted AMC', 'Current MOS', 'Quantity', 'EDD', 'Pipeline MOS', 'Total MOS', 'Procurement Agency', 'Pipeline Status', 'Risk Level', 'Mitigation Plan', 'Risk Response Status', 'Remark']
    stock_branches = [col for col in stock_df.columns if col not in stock_skip_cols]

    # Get all branch columns from issue data
    issue_skip_cols = ['Material', 'Material Description', 'Total Issue']
    issue_branches = [col for col in issue_df.columns if col not in issue_skip_cols]

    # Normalize branch names and create mapping
    stock_branch_map = {}
    for col in stock_branches:
        normalized = normalize_branch_name(col)
        stock_branch_map[col] = normalized

    issue_branch_map = {}
    for col in issue_branches:
        normalized = normalize_branch_name(col)
        issue_branch_map[col] = normalized

    # Rename columns in stock_df
    for old, new in stock_branch_map.items():
        if old != new:
            stock_df.rename(columns={old: new}, inplace=True)

    # Rename columns in issue_df
    for old, new in issue_branch_map.items():
        if old != new:
            issue_df.rename(columns={old: new}, inplace=True)

    # Get all unique normalized branch names
    all_branches = list(set(stock_branch_map.values()) | set(issue_branch_map.values()))
    all_branches = sorted(all_branches)

    # Create result DataFrame
    result_data = []

    # Get all materials from stock data
    materials = stock_df[['Material', 'Material Description']].copy()

    for idx, row in materials.iterrows():
        material = row['Material']
        material_desc = row['Material Description']

        new_row = {'Material': material, 'Material Description': material_desc}

        for branch in all_branches:
            # Get Plant Stock from stock data
            plant_stock = 0
            if branch in stock_df.columns:
                stock_row = stock_df[stock_df['Material'] == material]
                if not stock_row.empty:
                    plant_stock = stock_row.iloc[0].get(branch, 0)

            # Get Issue Quantity from issue data
            issue_qty = 0
            if branch in issue_df.columns:
                issue_row = issue_df[issue_df['Material'] == material]
                if not issue_row.empty:
                    issue_qty = issue_row.iloc[0].get(branch, 0)

            # Add two columns for each branch: Plant Stock and Issue Qty
            new_row[f'{branch}_Plant_Stock'] = plant_stock
            new_row[f'{branch}_Issue_Qty'] = issue_qty

        result_data.append(new_row)

    result_df = pd.DataFrame(result_data)
    result_df = result_df.sort_values('Material Description', ascending=True).reset_index(drop=True)

    return result_df, all_branches

# --- Function to create Monthly Issue Data ---
def create_monthly_issue_data(df, start_date=None, end_date=None):
    """
    Create Monthly Issue Data table.
    """
    if df is None or df.empty:
        return None

    df = df.copy()

    # Find Material Description column
    material_desc_col = None
    for col in df.columns:
        col_lower = col.lower()
        if 'material descr' in col_lower or 'material description' in col_lower or 'description' in col_lower:
            material_desc_col = col
            break

    if not material_desc_col:
        return None

    # Find Quantity column
    quantity_col = None
    for col in df.columns:
        if 'quantity' in col.lower() or 'qty' in col.lower():
            quantity_col = col
            break

    if not quantity_col:
        return None

    # Find Delivery Date column
    date_col = None
    for col in df.columns:
        col_lower = col.lower()
        if 'delivery' in col_lower or 'date' in col_lower:
            date_col = col
            break

    if not date_col:
        return None

    # Ensure Quantity is numeric
    df[quantity_col] = pd.to_numeric(df[quantity_col], errors='coerce').fillna(0)

    # Convert Delivery Date to datetime
    try:
        df['Delivery_Date'] = pd.to_datetime(df[date_col], errors='coerce')
        df['Month-Year'] = df['Delivery_Date'].dt.strftime('%b-%Y')
    except:
        df['Month-Year'] = ''

    # Apply date range filter if provided
    if start_date is not None and end_date is not None:
        mask = (df['Delivery_Date'] >= pd.to_datetime(start_date)) & (df['Delivery_Date'] <= pd.to_datetime(end_date))
        df = df[mask]
    elif start_date is not None:
        mask = (df['Delivery_Date'] >= pd.to_datetime(start_date))
        df = df[mask]
    elif end_date is not None:
        mask = (df['Delivery_Date'] <= pd.to_datetime(end_date))
        df = df[mask]

    # Filter out rows with no date
    df = df[df['Month-Year'] != '']

    if df.empty:
        return None

    # Group by Material Description and Month-Year
    grouped = df.groupby([material_desc_col, 'Month-Year'], as_index=False).agg({
        quantity_col: 'sum'
    })

    # Pivot to get Month-Year as columns
    pivot = grouped.pivot_table(
        index=material_desc_col,
        columns='Month-Year',
        values=quantity_col,
        fill_value=0,
        aggfunc='sum'
    ).reset_index()

    # Sort columns by date (Month-Year)
    date_columns = [col for col in pivot.columns if col != material_desc_col]
    try:
        sorted_dates = sorted(date_columns, key=lambda x: pd.to_datetime(x, format='%b-%Y') if x != '' else pd.Timestamp.min)
        pivot = pivot[[material_desc_col] + sorted_dates]
    except:
        pass

    # Calculate Actual AMC (Average of all months)
    month_columns = [col for col in pivot.columns if col != material_desc_col]
    if month_columns:
        pivot['Actual AMC (A_AMC)'] = pivot[month_columns].sum(axis=1) / len(month_columns)
        pivot['Actual AMC (A_AMC)'] = pivot['Actual AMC (A_AMC)'].round(2)
    else:
        pivot['Actual AMC (A_AMC)'] = 0

    pivot = pivot.sort_values(material_desc_col, ascending=True).reset_index(drop=True)

    return pivot

# --- Function to apply conversion mapping ---
def apply_conversion_mapping(excel_df, conversion_df):
    """Apply conversion mapping if columns exist."""
    if excel_df is None or conversion_df is None:
        return excel_df

    excel_df.columns = excel_df.columns.str.strip()
    conversion_df.columns = conversion_df.columns.str.strip()

    from_col = None
    to_col = None
    ratio_col = None

    for col in conversion_df.columns:
        col_lower = col.lower()
        if col_lower == 'from' or col_lower == 'material from':
            from_col = col
        elif col_lower == 'to' or col_lower == 'material to':
            to_col = col
        elif col_lower == 'ratio' or col_lower == 'conversion ratio':
            ratio_col = col

    if from_col is None or to_col is None or ratio_col is None:
        return excel_df

    conversion_df[from_col] = conversion_df[from_col].astype(str).str.strip()
    conversion_df[to_col] = conversion_df[to_col].astype(str).str.strip()
    conversion_df[ratio_col] = pd.to_numeric(conversion_df[ratio_col], errors='coerce')
    conversion_df = conversion_df.dropna(subset=[ratio_col])

    if conversion_df.empty:
        return excel_df

    result_df = excel_df.copy()

    # Find material column
    material_col = None
    for col in result_df.columns:
        if 'material' in col.lower():
            material_col = col
            break

    if not material_col:
        return excel_df

    result_df[material_col] = result_df[material_col].astype(str).str.strip()

    from_to_map = dict(zip(conversion_df[from_col], conversion_df[to_col]))
    from_ratio_map = dict(zip(conversion_df[from_col], conversion_df[ratio_col]))

    materials_to_convert = set(from_to_map.keys())

    converted_rows = []
    for idx in range(len(result_df)):
        row = result_df.iloc[idx]
        material = row[material_col]
        if material in materials_to_convert:
            new_material = from_to_map[material]
            ratio = from_ratio_map[material]

            new_row = row.copy()
            new_row[material_col] = new_material

            quantity_cols = [col for col in result_df.columns if 'qty' in col.lower() or 'quantity' in col.lower() or 'amount' in col.lower() or 'stock' in col.lower()]
            for col in quantity_cols:
                if col in result_df.columns and pd.api.types.is_numeric_dtype(result_df[col]):
                    new_row[col] = row[col] * ratio

            converted_rows.append(new_row)

    result_df = result_df[~result_df[material_col].isin(materials_to_convert)]

    if converted_rows:
        converted_df = pd.DataFrame(converted_rows)
        result_df = pd.concat([result_df, converted_df], ignore_index=True)

    return result_df

# --- Function to merge data ---
def merge_data(excel_df, sheet_df):
    if excel_df is None or sheet_df is None:
        return None

    excel_df.columns = excel_df.columns.str.strip()
    sheet_df.columns = sheet_df.columns.str.strip()

    # Find material column in Excel
    excel_material_col = None
    for col in excel_df.columns:
        if 'material' in col.lower():
            excel_material_col = col
            break

    if not excel_material_col:
        st.error("Excel must contain a 'Material' column.")
        return None

    # Check if sheet has required columns
    required_sheet = {"Material", "Program", "Sub_Category"}
    if not required_sheet.issubset(sheet_df.columns):
        st.error("Google Sheet must contain 'Material', 'Program', and 'Sub_Category' columns.")
        return None

    # Rename Excel material column to 'Material' for merging
    excel_df = excel_df.copy()
    if excel_material_col != 'Material':
        excel_df['Material'] = excel_df[excel_material_col]

    excel_df["Material"] = excel_df["Material"].astype(str).str.strip()
    sheet_df["Material"] = sheet_df["Material"].astype(str).str.strip()

    sheet_lookup = sheet_df[["Material", "Program", "Sub_Category"]].drop_duplicates(subset="Material")

    merged = excel_df.merge(sheet_lookup, on="Material", how="inner")

    return merged

# --- Auto-load Google Sheets ---
@st.cache_data
def auto_load_google_sheets():
    master_df = load_google_sheet(DEFAULT_MASTER_URL)
    conversion_df = load_google_sheet(DEFAULT_CONVERSION_URL)
    return master_df, conversion_df

# --- Main app logic ---
if not st.session_state.sheet_loaded:
    with st.spinner("Loading Google Sheets automatically..."):
        master_df, conversion_df = auto_load_google_sheets()
        if master_df is not None and not master_df.empty:
            st.session_state.sheet_data = master_df
            st.session_state.sheet_loaded = True
        if conversion_df is not None and not conversion_df.empty:
            st.session_state.conversion_data = conversion_df
            st.session_state.conversion_loaded = True

# --- Sidebar ---
with st.sidebar:
    if st.session_state.sheet_loaded and st.session_state.sheet_data is not None:
        st.markdown("**Program Filter**")
        programs = sorted(st.session_state.sheet_data['Program'].dropna().unique().tolist())
        selected_programs = st.multiselect(
            "",
            options=programs,
            default=st.session_state.selected_programs,
            key='program_filter_sidebar_new',
            placeholder="Select Program(s)"
        )
        st.session_state.selected_programs = selected_programs

    if st.session_state.sheet_loaded and st.session_state.sheet_data is not None:
        st.markdown("**Sub Category Filter**")
        sub_categories = sorted(st.session_state.sheet_data['Sub_Category'].dropna().unique().tolist())
        selected_sub_categories = st.multiselect(
            "",
            options=sub_categories,
            default=st.session_state.selected_sub_categories,
            key='sub_category_filter_sidebar_new',
            placeholder="Select Sub Category(s)"
        )
        st.session_state.selected_sub_categories = selected_sub_categories

    # Risk Level Filter - only show if pipeline data is available
    if st.session_state.pipeline_stock_data is not None and not st.session_state.pipeline_stock_data.empty:
        st.markdown("**Risk Level Filter**")
        risk_levels = ['Low', 'Medium', 'High']
        selected_risk_levels = st.multiselect(
            "",
            options=risk_levels,
            default=st.session_state.selected_risk_levels,
            key='risk_level_filter_sidebar',
            placeholder="Select Risk Level(s)"
        )
        st.session_state.selected_risk_levels = selected_risk_levels

    st.markdown("---")

    # 📁 Upload Materials.xlsx
    st.markdown("**📁 Upload Materials.xlsx**")
    uploaded_file = st.file_uploader(
        "",
        type=['xlsx', 'xls'],
        key='materials_upload_sidebar'
    )

    if uploaded_file is not None:
        if not st.session_state.excel_loaded or st.session_state.excel_file != uploaded_file.name:
            try:
                df = pd.read_excel(uploaded_file)
                df.columns = df.columns.str.strip()

                first_col = df.columns[0]
                if df[first_col].dtype in ['int64', 'float64']:
                    if (df[first_col] == range(1, len(df) + 1)).all():
                        df = df.drop(columns=[first_col])

                st.session_state.excel_data = df
                st.session_state.excel_loaded = True
                st.session_state.excel_file = uploaded_file.name
                st.success(f"✅ Loaded {len(df)} rows from Excel!")

                if st.session_state.conversion_loaded and st.session_state.conversion_data is not None:
                    with st.spinner("Applying conversion mapping..."):
                        converted_df = apply_conversion_mapping(df, st.session_state.conversion_data)
                        st.session_state.excel_data = converted_df

                if st.session_state.sheet_loaded:
                    with st.spinner("Performing INNER JOIN with Google Sheet master list..."):
                        merged = merge_data(st.session_state.excel_data, st.session_state.sheet_data)
                        if merged is not None and not merged.empty:
                            merged = format_date_columns(merged)
                            merged = calculate_plant_stock(merged)
                            merged = create_expiry_date_column(merged)

                            if 'Material Description' in merged.columns:
                                merged = merged.sort_values('Material Description', ascending=True).reset_index(drop=True)
                            elif 'Material' in merged.columns:
                                merged = merged.sort_values('Material', ascending=True).reset_index(drop=True)

                            pipeline_df = create_pipeline_stock_status(merged)
                            st.session_state.pipeline_stock_data = pipeline_df

                            national_df = create_national_stock_status(merged)
                            st.session_state.national_stock_data = national_df

                            st.session_state.merged_data = merged
                            st.session_state.filtered_data = merged.copy()
                            st.session_state.merge_clicked = True
                            st.success(f"✅ Found {len(merged)} matching rows!")
                            st.rerun()
                        else:
                            st.session_state.merge_clicked = False
                            st.warning("⚠️ No matching Materials found in Google Sheet")

            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.session_state.excel_data = None
                st.session_state.excel_loaded = False
                st.session_state.merge_clicked = False

    st.markdown("---")

    # 📦 Issue Data
    st.markdown("**📦 Upload Items.xlsx**")
    items_file = st.file_uploader(
        "",
        type=['xlsx', 'xls'],
        key='items_upload_sidebar'
    )

    if items_file is not None:
        if st.session_state.items_file != items_file.name:
            try:
                df = pd.read_excel(items_file)
                df.columns = df.columns.str.strip()

                st.session_state.items_data = df
                st.session_state.items_loaded = True
                st.session_state.items_file = items_file.name
                st.success(f"✅ Loaded {len(df)} rows from {items_file.name}!")

                if st.session_state.conversion_loaded and st.session_state.conversion_data is not None:
                    with st.spinner("Applying conversion mapping..."):
                        converted_df = apply_conversion_mapping(df, st.session_state.conversion_data)
                        st.session_state.items_data = converted_df

                if st.session_state.sheet_loaded:
                    with st.spinner("Merging with master list..."):
                        merged = merge_data(st.session_state.items_data, st.session_state.sheet_data)
                        if merged is not None and not merged.empty:
                            merged = format_date_columns(merged)

                            if 'Material Descr' in merged.columns:
                                merged = merged.sort_values('Material Descr', ascending=True).reset_index(drop=True)
                            elif 'Material Description' in merged.columns:
                                merged = merged.sort_values('Material Description', ascending=True).reset_index(drop=True)
                            elif 'Material' in merged.columns:
                                merged = merged.sort_values('Material', ascending=True).reset_index(drop=True)

                            if st.session_state.selected_programs:
                                merged = merged[merged['Program'].isin(st.session_state.selected_programs)]

                            if st.session_state.selected_sub_categories:
                                merged = merged[merged['Sub_Category'].isin(st.session_state.selected_sub_categories)]

                            items_national_df = create_national_stock_status(merged, include_nsoh=False, include_expiry=False, is_issue_data=True)
                            st.session_state.items_national_stock_data = items_national_df

                            st.session_state.items_merged_data = merged
                            st.session_state.items_filtered_data = merged.copy()
                            st.session_state.items_merge_clicked = True
                            st.success(f"✅ Found {len(merged)} matching rows!")

                            monthly_df = create_monthly_issue_data(merged)
                            if monthly_df is not None and not monthly_df.empty:
                                a_amc_dict = {}
                                for idx, row in monthly_df.iterrows():
                                    desc = row.get('Material Descr') or row.get('Material Description')
                                    amc = row.get('Actual AMC (A_AMC)', 0)
                                    if desc:
                                        a_amc_dict[desc] = amc
                                st.session_state.a_amc_data = a_amc_dict

                                if st.session_state.pipeline_stock_data is not None and st.session_state.merged_data is not None:
                                    updated_pipeline = create_pipeline_stock_status(
                                        st.session_state.merged_data, 
                                        st.session_state.a_amc_data
                                    )
                                    st.session_state.pipeline_stock_data = updated_pipeline

                            st.rerun()
                        else:
                            st.session_state.items_merge_clicked = False
                            st.warning("⚠️ No matching Materials found in Google Sheet master list.")

            except Exception as e:
                st.error(f"❌ Error loading file: {str(e)}")
                st.session_state.items_data = None
                st.session_state.items_loaded = False
                st.session_state.items_merge_clicked = False

# --- Main Dashboard Content ---
st.markdown("""
    <style>
        @keyframes subtlePulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.01); }
            100% { transform: scale(1); }
        }
        .title-times-roman {
            font-family: 'Times New Roman', Times, serif;
            background: linear-gradient(135deg, #0b2b44, #1a4a6e);
            padding: 18px 30px;
            border-radius: 12px;
            font-size: 2.2rem;
            font-weight: bold;
            color: white;
            display: inline-block;
            margin-bottom: 15px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            animation: subtlePulse 3s ease-in-out infinite;
            letter-spacing: 1px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .risk-section-title {
            font-size: 1.1rem;
            font-weight: 600;
            color: #0b2b44;
            margin-bottom: 10px;
            padding-left: 5px;
        }
        .risk-metric-card {
            background: white;
            padding: 12px 18px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            text-align: center;
            border-left: 5px solid #ccc;
            transition: transform 0.2s;
            flex: 0 1 auto;
            min-width: 120px;
            max-width: 180px;
        }
        .risk-metric-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 4px 15px rgba(0,0,0,0.12);
        }
        .risk-metric-card .risk-label {
            font-size: 0.9rem;
            color: #666;
            font-weight: 500;
        }
        .risk-metric-card .risk-value {
            font-size: 1.8rem;
            font-weight: bold;
            margin: 3px 0;
        }
        .risk-metric-card .risk-sub {
            font-size: 0.8rem;
            color: #888;
        }
        .risk-low { border-left-color: #4caf50; }
        .risk-medium { border-left-color: #ff9800; }
        .risk-high { border-left-color: #f44336; }
        .risk-low .risk-value { color: #4caf50; }
        .risk-medium .risk-value { color: #ff9800; }
        .risk-high .risk-value { color: #f44336; }
        .colored-subheader {
            background: linear-gradient(135deg, #e8f4f8, #b8d8e8);
            padding: 12px 20px;
            border-radius: 8px;
            border-left: 5px solid #0b2b44;
            margin: 20px 0 15px 0;
            font-weight: bold;
            color: #0b2b44;
            font-size: 1.3rem !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }
        .colored-subheader-green {
            background: linear-gradient(135deg, #e8f5e9, #c8e6c9);
            border-left-color: #2e7d32;
            color: #1b5e20;
        }
        .colored-subheader-purple {
            background: linear-gradient(135deg, #f3e5f5, #e1bee7);
            border-left-color: #6a1b9a;
            color: #4a148c;
        }
        .colored-subheader-orange {
            background: linear-gradient(135deg, #fff3e0, #ffe0b2);
            border-left-color: #e65100;
            color: #bf360c;
        }
        .colored-subheader-teal {
            background: linear-gradient(135deg, #e0f2f1, #b2dfdb);
            border-left-color: #00695c;
            color: #004d40;
        }
        .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
            font-size: 1.1rem !important;
            font-weight: 600 !important;
        }
    </style>
    <div class="title-times-roman">🏥 Health Program Commodities Supply Information</div>
""", unsafe_allow_html=True)

# Display Risk Level Metrics as cards with title
if st.session_state.pipeline_stock_data is not None and not st.session_state.pipeline_stock_data.empty:
    pipeline_df = st.session_state.pipeline_stock_data

    low_count = len(pipeline_df[pipeline_df['Risk Level'] == 'Low'])
    medium_count = len(pipeline_df[pipeline_df['Risk Level'] == 'Medium'])
    high_count = len(pipeline_df[pipeline_df['Risk Level'] == 'High'])
    total_count = len(pipeline_df)

    st.markdown('<div class="risk-section-title">📊 Risk Level Summary</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        st.markdown(f"""
        <div class="risk-metric-card risk-low">
            <div class="risk-label">🟢 Low Risk</div>
            <div class="risk-value">{low_count}</div>
            <div class="risk-sub">{low_count/total_count*100:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="risk-metric-card risk-medium">
            <div class="risk-label">🟠 Medium Risk</div>
            <div class="risk-value">{medium_count}</div>
            <div class="risk-sub">{medium_count/total_count*100:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="risk-metric-card risk-high">
            <div class="risk-label">🔴 High Risk</div>
            <div class="risk-value">{high_count}</div>
            <div class="risk-sub">{high_count/total_count*100:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)

# Create tabs
tab1, tab2, tab3 = st.tabs(["📊 Stock Data", "📦 Complete Issue Data", "📊 Plant Stock Vs Issue Quantity"])

# Tab 1: Stock Data
with tab1:
    if st.session_state.merge_clicked and st.session_state.merged_data is not None:
        data_to_use = st.session_state.filtered_data if st.session_state.filtered_data is not None else st.session_state.merged_data

        st.markdown('<div class="colored-subheader">🏥 National and Pipeline Stock Status</div>', unsafe_allow_html=True)

        if st.session_state.pipeline_stock_data is not None and not st.session_state.pipeline_stock_data.empty:
            display_pipeline = st.session_state.pipeline_stock_data.copy()

            if st.session_state.selected_risk_levels:
                display_pipeline = display_pipeline[display_pipeline['Risk Level'].isin(st.session_state.selected_risk_levels)]

            original_pipeline = display_pipeline.copy()

            with st.form(key="pipeline_form"):
                edited_df = st.data_editor(
                    display_pipeline,
                    use_container_width=True,
                    height=500,
                    hide_index=True,
                    column_config={
                        "Adjusted AMC": st.column_config.NumberColumn("Adjusted AMC", help="Enter Adjusted AMC"),
                        "Quantity": st.column_config.NumberColumn("Quantity", help="Enter Pipeline Quantity"),
                        "EDD": st.column_config.TextColumn("EDD", help="Estimated Delivery Date"),
                        "Procurement Agency": st.column_config.TextColumn("Procurement Agency"),
                        "Pipeline Status": st.column_config.TextColumn("Pipeline Status"),
                        "Risk Level": st.column_config.TextColumn("Risk Level", help="Auto-calculated"),
                        "Mitigation Plan": st.column_config.TextColumn("Mitigation Plan"),
                        "Risk Response Status": st.column_config.TextColumn("Risk Response Status"),
                        "Remark": st.column_config.TextColumn("Remark"),
                    },
                    disabled=["Material", "Material Description", "Hubs' SOH", "Head Office", "NSOH", "Expiry Date", "A_AMC", "Current MOS", "Pipeline MOS", "Total MOS", "Risk Level"]
                )

                col1, col2, col3 = st.columns([1, 1, 4])
                with col1:
                    save_button = st.form_submit_button("💾 Save Changes")

                if save_button:
                    for idx, row in edited_df.iterrows():
                        adjusted_amc = row.get('Adjusted AMC', 0)
                        if isinstance(adjusted_amc, str):
                            try:
                                adjusted_amc = float(adjusted_amc) if adjusted_amc else 0
                            except:
                                adjusted_amc = 0
                        elif isinstance(adjusted_amc, (int, float)):
                            adjusted_amc = float(adjusted_amc)
                        else:
                            adjusted_amc = 0

                        current_mos = 0.0
                        if adjusted_amc > 0:
                            nsoh = float(row.get('NSOH', 0)) if row.get('NSOH') else 0
                            quantity = row.get('Quantity', 0)
                            if isinstance(quantity, str):
                                try:
                                    quantity = float(quantity) if quantity else 0
                                except:
                                    quantity = 0
                            elif isinstance(quantity, (int, float)):
                                quantity = float(quantity)
                            else:
                                quantity = 0

                            current_mos = round(nsoh / adjusted_amc, 2)
                            edited_df.at[idx, 'Current MOS'] = current_mos
                            edited_df.at[idx, 'Pipeline MOS'] = round(quantity / adjusted_amc, 2)
                            edited_df.at[idx, 'Total MOS'] = round((nsoh + quantity) / adjusted_amc, 2)
                        else:
                            edited_df.at[idx, 'Current MOS'] = 0.0
                            edited_df.at[idx, 'Pipeline MOS'] = 0.0
                            edited_df.at[idx, 'Total MOS'] = 0.0

                        edd = row.get('EDD', '')
                        edited_df.at[idx, 'Risk Level'] = calculate_risk_level(current_mos, edd)

                    with st.spinner("Saving changes to Supabase..."):
                        success, saved_count = save_supabase_data(original_pipeline, edited_df)
                        if success:
                            if saved_count > 0:
                                st.success(f"✅ {saved_count} row(s) saved successfully!")
                            else:
                                st.info("ℹ️ No changes detected to save.")
                            st.session_state.pipeline_stock_data = edited_df
                            st.rerun()
                        else:
                            st.error("❌ Failed to save changes. Please try again.")

            csv_pipeline = display_pipeline.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Pipeline Stock Status as CSV",
                data=csv_pipeline,
                file_name="Pipeline_Stock_Status.csv",
                mime="text/csv",
                key="pipeline_download"
            )

            with st.expander("ℹ️ About this table"):
                st.markdown("""
                **National and Pipeline Stock Status**

                - **Risk Level**: Auto-calculated based on Current MOS and EDD
                  - **Low**: Current MOS >= 4 and EDD <= 2 months
                  - **Medium**: 2 <= Current MOS < 4 and 2 <= EDD <= 4 months
                  - **High**: Current MOS < 2 and EDD > 4 months
                """)
        else:
            st.info("No pipeline stock status data available")

        st.markdown('<div class="colored-subheader colored-subheader-green">🏥 National Stock Status</div>', unsafe_allow_html=True)

        if st.session_state.national_stock_data is not None and not st.session_state.national_stock_data.empty:
            display_national = st.session_state.national_stock_data.copy()
            st.dataframe(display_national, use_container_width=True, height=500, hide_index=True)

            csv_national = display_national.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download National Stock Status as CSV",
                data=csv_national,
                file_name="Health_Program_National_Stock_Status.csv",
                mime="text/csv"
            )
        else:
            st.info("No national stock status data available")

        st.markdown('<div class="colored-subheader colored-subheader-purple">📊 Stock Data with Plant Stock and Expiry Date</div>', unsafe_allow_html=True)

        display_df = data_to_use
        index_columns = ['Index', 'Ser No', 'S.No', 'S. No', 'Unnamed: 0']
        display_columns = [col for col in display_df.columns if col not in index_columns]
        display_df = display_df[display_columns]

        columns_to_hide = ['Program', 'Sub_Category']
        display_columns = [col for col in display_df.columns if col not in columns_to_hide]
        display_df = display_df[display_columns]
        display_df = display_df.reset_index(drop=True)

        st.dataframe(display_df, use_container_width=True, height=600, hide_index=True)

        csv = display_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Stock Data as CSV",
            data=csv,
            file_name="Stock_Data.csv",
            mime="text/csv"
        )

        with st.expander("ℹ️ Data Status"):
            st.write(f"Master Sheet loaded: {st.session_state.sheet_loaded}")
            if st.session_state.sheet_loaded and st.session_state.sheet_data is not None:
                st.write(f"Master Sheet rows: {len(st.session_state.sheet_data)}")
            st.write(f"Materials.xlsx loaded: {st.session_state.excel_loaded}")
            if st.session_state.excel_loaded and st.session_state.excel_data is not None:
                st.write(f"Materials.xlsx rows: {len(st.session_state.excel_data)}")
            st.write(f"Items.xlsx loaded: {st.session_state.items_loaded}")
            if st.session_state.items_loaded and st.session_state.items_data is not None:
                st.write(f"Items.xlsx rows: {len(st.session_state.items_data)}")
            st.write(f"Matching rows found: {st.session_state.merge_clicked}")
            if st.session_state.merge_clicked and st.session_state.merged_data is not None:
                st.write(f"Total matching rows: {len(st.session_state.merged_data)}")

    elif st.session_state.excel_loaded and st.session_state.sheet_loaded:
        st.warning("⚠️ No Materials from your Excel file were found in the Google Sheet master list.")
    elif st.session_state.sheet_loaded:
        st.info("📤 Please upload your Materials.xlsx file to see matching materials")
    else:
        st.warning("⏳ Loading Google Sheets... Please wait or refresh the page")

# Tab 2: Complete Issue Data
with tab2:
    st.markdown('<div class="colored-subheader colored-subheader-orange">📦 Complete Issue Data</div>', unsafe_allow_html=True)

    if st.session_state.items_loaded and st.session_state.items_merged_data is not None:
        items_data = st.session_state.items_merged_data

        st.markdown('<div class="colored-subheader colored-subheader-teal" style="margin-top:10px;">📅 Filter by Delivery Date Range</div>', unsafe_allow_html=True)

        date_col = None
        for col in items_data.columns:
            col_lower = col.lower()
            if 'delivery' in col_lower or 'date' in col_lower:
                date_col = col
                break

        if date_col:
            try:
                items_data['Delivery_Date'] = pd.to_datetime(items_data[date_col], errors='coerce')
                min_date = items_data['Delivery_Date'].min()
                max_date = items_data['Delivery_Date'].max()

                if pd.notna(min_date) and pd.notna(max_date):
                    col1, col2 = st.columns(2)
                    with col1:
                        start_date = st.date_input(
                            "Start Date",
                            value=min_date,
                            min_value=min_date,
                            max_value=max_date,
                            key='start_date_complete'
                        )
                    with col2:
                        end_date = st.date_input(
                            "End Date",
                            value=max_date,
                            min_value=min_date,
                            max_value=max_date,
                            key='end_date_complete'
                        )

                    if start_date and end_date:
                        mask = (items_data['Delivery_Date'] >= pd.to_datetime(start_date)) & (items_data['Delivery_Date'] <= pd.to_datetime(end_date))
                        filtered_items = items_data[mask]

                        if not filtered_items.empty:
                            st.markdown('<div class="colored-subheader colored-subheader-green">🏥 Hubs Issue Data</div>', unsafe_allow_html=True)

                            items_national_df = create_national_stock_status(filtered_items, include_nsoh=False, include_expiry=False, is_issue_data=True)
                            st.session_state.items_national_stock_data = items_national_df

                            if items_national_df is not None and not items_national_df.empty:
                                display_national = items_national_df.copy()
                                st.dataframe(display_national, use_container_width=True, height=500, hide_index=True)

                                csv_national = display_national.to_csv(index=False).encode('utf-8')
                                st.download_button(
                                    label="📥 Download Hubs Issue Data as CSV",
                                    data=csv_national,
                                    file_name="Hubs_Issue_Data.csv",
                                    mime="text/csv"
                                )
                            else:
                                st.info("No hubs issue data available for the selected date range")

                            st.markdown('<div class="colored-subheader colored-subheader-teal">📊 Monthly Issue Data & Actual AMC</div>', unsafe_allow_html=True)

                            monthly_df = create_monthly_issue_data(filtered_items, start_date, end_date)

                            if monthly_df is not None and not monthly_df.empty:
                                st.dataframe(monthly_df, use_container_width=True, height=500, hide_index=True)

                                csv_monthly = monthly_df.to_csv(index=False).encode('utf-8')
                                st.download_button(
                                    label="📥 Download Monthly Issue Data as CSV",
                                    data=csv_monthly,
                                    file_name="Monthly_Issue_Data.csv",
                                    mime="text/csv"
                                )

                                a_amc_dict = {}
                                for idx, row in monthly_df.iterrows():
                                    desc = row.get('Material Descr') or row.get('Material Description')
                                    amc = row.get('Actual AMC (A_AMC)', 0)
                                    if desc:
                                        a_amc_dict[desc] = amc
                                st.session_state.a_amc_data = a_amc_dict

                                if st.session_state.pipeline_stock_data is not None and st.session_state.merged_data is not None:
                                    updated_pipeline = create_pipeline_stock_status(
                                        st.session_state.merged_data, 
                                        st.session_state.a_amc_data
                                    )
                                    st.session_state.pipeline_stock_data = updated_pipeline
                            else:
                                st.info("No monthly issue data available for the selected date range")

                            st.markdown('<div class="colored-subheader colored-subheader-purple">📊 Complete Issue Data</div>', unsafe_allow_html=True)

                            display_df = filtered_items.copy()
                            index_columns = ['Index', 'Ser No', 'S.No', 'S. No', 'Unnamed: 0', 'Delivery_Date']
                            display_columns = [col for col in display_df.columns if col not in index_columns]
                            display_df = display_df[display_columns]

                            columns_to_hide = ['Program', 'Sub_Category']
                            display_columns = [col for col in display_df.columns if col not in columns_to_hide]
                            display_df = display_df[display_columns]
                            display_df = display_df.reset_index(drop=True)

                            st.dataframe(display_df, use_container_width=True, height=600, hide_index=True)

                            csv = display_df.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                label="📥 Download Complete Issue Data as CSV",
                                data=csv,
                                file_name="Complete_Issue_Data.csv",
                                mime="text/csv"
                            )
                        else:
                            st.warning("No data found for the selected date range")
                    else:
                        st.info("Please select both start and end dates")
                else:
                    st.info("No valid dates found in the Delivery Date column")
            except Exception as e:
                st.error(f"Error processing dates: {str(e)}")
                st.info("Please ensure the Delivery Date column contains valid dates")
        else:
            st.info("No Delivery Date column found in the data")

    elif st.session_state.items_loaded:
        st.warning("⚠️ No matching Materials found.")
    else:
        st.info("📤 Please upload your Items.xlsx file using the sidebar uploader to view Complete Issue Data")

# Tab 3: Plant Stock Vs Issue Quantity
with tab3:
    st.markdown('<div class="colored-subheader colored-subheader-purple">📊 Plant Stock Vs Issue Quantity</div>', unsafe_allow_html=True)

    if st.session_state.national_stock_data is not None and not st.session_state.national_stock_data.empty and st.session_state.items_national_stock_data is not None and not st.session_state.items_national_stock_data.empty:

        stock_data = st.session_state.national_stock_data.copy()
        issue_data = st.session_state.items_national_stock_data.copy()

        comparison_df, branches = create_plant_stock_vs_issue(stock_data, issue_data)

        if comparison_df is not None and not comparison_df.empty and branches is not None and len(branches) > 0:
            st.dataframe(comparison_df, use_container_width=True, height=500, hide_index=True)

            col1, col2 = st.columns(2)
            with col1:
                csv = comparison_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Export as CSV",
                    data=csv,
                    file_name="Plant_Stock_Vs_Issue_Quantity.csv",
                    mime="text/csv",
                    key="export_csv"
                )
            with col2:
                try:
                    with BytesIO() as buffer:
                        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                            comparison_df.to_excel(writer, sheet_name='Data', index=False)
                        buffer.seek(0)
                        st.download_button(
                            label="📥 Export as Excel",
                            data=buffer,
                            file_name="Plant_Stock_Vs_Issue_Quantity.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="export_excel"
                        )
                except Exception as e:
                    st.error(f"Error exporting to Excel: {e}")
                    st.info("You can still download as CSV")
        else:
            st.info("No branches found for comparison.")
    else:
        st.info("📤 Please load both Materials.xlsx and Items.xlsx files to view the comparison.")
