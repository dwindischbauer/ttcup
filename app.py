import streamlit as st
import pandas as pd
import re
import sqlite3
from io import BytesIO
from datetime import datetime

# --- Configuration & Setup ---
st.set_page_config(page_title="Running Club Tracker", page_icon="🏃‍♂️", layout="wide")

# --- Helper Functions ---
def time_to_seconds(t_str):
    try:
        parts = t_str.split(':')
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except Exception:
        pass
    return 0

def parse_strava_data(raw_text):
    data = []
    
    # Strategy 1: Tab-separated (if copied directly from a table)
    if '\t' in raw_text:
        for line in raw_text.split('\n'):
            parts = [p.strip() for p in line.split('\t') if p.strip()]
            if len(parts) >= 3:
                time_str = None
                date_str = None
                name = None
                rank = 999
                
                for p in parts:
                    if not time_str and re.match(r'^(\d{1,2}:)?\d{1,2}:\d{2}(\.\d+)?$', p):
                        time_str = p
                    elif not date_str and re.search(r'([A-Z][a-z]{2}\s\d{1,2},\s\d{4}|\d{1,2}\s[A-Z][a-z]{2}\s\d{4}|\d{1,2}/\d{1,2}/\d{4})', p):
                        date_str = p
                    elif not name and re.match(r'^[A-Za-z\s\.\-]+$', p) and len(p) > 2:
                        name = p
                    elif rank == 999 and re.match(r'^\d+$', p):
                        rank = int(p)
                
                if time_str and date_str:
                    if not name and len(parts) > 0:
                        name = parts[0] if not re.match(r'^\d+$', parts[0]) else (parts[1] if len(parts) > 1 else "Unknown")
                    
                    data.append({
                        'Original Rank': rank if rank != 999 else 1,
                        'Athlete Name': name,
                        'Date': date_str,
                        'Time': time_str
                    })
        if data:
            return pd.DataFrame(data).drop_duplicates(subset=['Athlete Name', 'Date', 'Time'])

    # Strategy 2: Heuristic Line-by-Line Parsing
    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
    i = 0
    while i < len(lines):
        rank = None
        name = None
        
        if re.match(r'^\d+$', lines[i]):
            rank = int(lines[i])
            if i + 1 < len(lines):
                name = lines[i+1]
                start_search = i + 2
        else:
            name = lines[i]
            rank = 1
            start_search = i + 1
            
        if name and len(name) > 2:
            if name.upper() in ['PRO', 'SUBSCRIBER'] and start_search < len(lines):
                name = lines[start_search]
                start_search += 1
            
            date_str = None
            time_str = None
            
            for j in range(start_search, min(start_search + 10, len(lines))):
                if not date_str:
                    date_match = re.search(r'([A-Z][a-z]{2}\s\d{1,2},\s\d{4}|\d{1,2}\s[A-Z][a-z]{2}\s\d{4}|\d{1,2}/\d{1,2}/\d{4})', lines[j])
                    if date_match:
                        date_str = date_match.group(1)
                
                if not time_str and re.match(r'^(\d{1,2}:)?\d{1,2}:\d{2}(\.\d+)?$', lines[j]):
                    time_str = lines[j]
                    
                if date_str and time_str:
                    data.append({
                        'Original Rank': rank if rank else 1,
                        'Athlete Name': name,
                        'Date': date_str,
                        'Time': time_str
                    })
                    i = j
                    break
        i += 1
        
    df = pd.DataFrame(data)
    if not df.empty:
        df = df[df['Athlete Name'].str.len() > 3]
        df = df.drop_duplicates(subset=['Athlete Name', 'Date', 'Time'])
    return df

def save_to_db(df, db_name='race_results.db'):
    conn = sqlite3.connect(db_name)
    df.to_sql('race_results', conn, if_exists='append', index=False)
    conn.close()

def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Monthly Results')
    return output.getvalue()

# --- Main Streamlit UI ---
st.title("🏃‍♂️ Running Club Competition Tracker")
st.markdown("Paste your raw Strava segment leaderboard text below. The app will automatically extract the data, filter it, calculate points, and allow you to mark 'Over 45' athletes.")

raw_text = st.text_area("Paste Strava Leaderboard Data Here:", height=200, placeholder="1\nJohn Doe\nAug 14, 2025\n...\n5:32")

col1, col2 = st.columns(2)
with col1:
    months = {
        "January": 1, "February": 2, "March": 3, "April": 4, 
        "May": 5, "June": 6, "July": 7, "August": 8, 
        "September": 9, "October": 10, "November": 11, "December": 12
    }
    selected_month_name = st.selectbox("Filter Month", list(months.keys()), index=datetime.now().month - 1)
    filter_month = months[selected_month_name]
    
with col2:
    filter_year = st.number_input("Filter Year", min_value=2000, max_value=2100, value=datetime.now().year, step=1)

if st.button("Parse & Process Data", type="primary"):
    if not raw_text.strip():
        st.warning("Please paste some data into the text area first.")
    else:
        with st.spinner("Extracting data..."):
            df = parse_strava_data(raw_text)
            if df.empty:
                st.error("Could not parse any valid data. Please ensure you copied the Strava leaderboard text directly.")
            else:
                st.session_state['parsed_df'] = df
                st.success(f"Successfully extracted {len(df)} records from the raw text!")

if 'parsed_df' in st.session_state:
    df = st.session_state['parsed_df']
    
    df['Parsed Date'] = pd.to_datetime(df['Date'], errors='coerce')
    filtered_df = df.dropna(subset=['Parsed Date']).copy()
    filtered_df = filtered_df[(filtered_df['Parsed Date'].dt.month == filter_month) & 
                              (filtered_df['Parsed Date'].dt.year == filter_year)]
    
    if filtered_df.empty:
        st.info(f"No runs found for {selected_month_name} {filter_year} in the parsed data.")
    else:
        st.divider()
        st.subheader(f"🏆 Results for {selected_month_name} {filter_year}")
        
        filtered_df['Seconds'] = filtered_df['Time'].apply(time_to_seconds)
        filtered_df = filtered_df.sort_values('Seconds', ascending=True).reset_index(drop=True)
        filtered_df['Race Rank'] = filtered_df.index + 1
        
        filtered_df['Points'] = filtered_df['Race Rank'].apply(lambda x: 51 - x if x <= 50 else 0)
        filtered_df['Over 45'] = False
        filtered_df['Date'] = filtered_df['Parsed Date'].dt.strftime('%Y-%m-%d')
        
        display_cols = ['Race Rank', 'Athlete Name', 'Date', 'Time', 'Points', 'Over 45', 'Original Rank', 'Seconds']
        display_df = filtered_df[display_cols]
        
        st.markdown("Feel free to tick the **'Over 45'** checkbox for relevant athletes. Changes are tracked automatically.")
        
        editor_key = f"editor_{selected_month_name}_{filter_year}"
        
        edited_df = st.data_editor(
            display_df,
            key=editor_key,
            column_config={
                "Over 45": st.column_config.CheckboxColumn("Over 45?", default=False),
                "Race Rank": st.column_config.NumberColumn("Race Rank", disabled=True),
                "Points": st.column_config.NumberColumn("Points", disabled=True),
                "Athlete Name": st.column_config.TextColumn("Athlete Name", disabled=True),
                "Date": st.column_config.TextColumn("Date", disabled=True),
                "Time": st.column_config.TextColumn("Time", disabled=True),
                "Original Rank": st.column_config.NumberColumn("Strava Rank", disabled=True),
                "Seconds": None
            },
            hide_index=True,
            use_container_width=True
        )
        
        col_save, col_dl = st.columns(2)
        
        with col_save:
            if st.button("💾 Save to Database (SQLite)", use_container_width=True):
                try:
                    final_save_df = edited_df.drop(columns=['Seconds'], errors='ignore')
                    save_to_db(final_save_df)
                    st.success("Results appended to `race_results.db` successfully!")
                except Exception as e:
                    st.error(f"Error saving to database: {e}")
                    
        with col_dl:
            final_export_df = edited_df.drop(columns=['Seconds'], errors='ignore')
            excel_data = convert_df_to_excel(final_export_df)
            st.download_button(
                label="📊 Download as Excel",
                data=excel_data,
                file_name=f"Race_Results_{selected_month_name}_{filter_year}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
