import streamlit as st
import pandas as pd
import psycopg2
import os
from datetime import datetime
from fpdf import FPDF

# --- 0. PAGE CONFIG ---
st.set_page_config(page_title="Factory Manager", layout="wide")

# --- 1. DATABASE SETUP (CLOUD VERSION) ---
def get_connection():
    # Connect using Streamlit Secrets
    return psycopg2.connect(st.secrets["connections"]["postgresql"]["url"])

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # Workers Table (Postgres uses SERIAL instead of AUTOINCREMENT)
    c.execute('''CREATE TABLE IF NOT EXISTS workers
                 (id SERIAL PRIMARY KEY, 
                  name TEXT, 
                  designation TEXT, 
                  photo_filename TEXT,
                  daily_rate INTEGER DEFAULT 0)''')
    
    # Attendance Table
    c.execute('''CREATE TABLE IF NOT EXISTS attendance
                 (date TEXT, 
                  worker_id INTEGER, 
                  status TEXT, 
                  bundles_made INTEGER DEFAULT 0,
                  UNIQUE(date, worker_id))''') 
    
    # Stock Tables
    c.execute('''CREATE TABLE IF NOT EXISTS stock
                 (id SERIAL PRIMARY KEY, date TEXT, item_name TEXT, quantity INTEGER, notes TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS sold_stock
                 (id SERIAL PRIMARY KEY, date TEXT, item_name TEXT, quantity INTEGER, buyer_notes TEXT)''')
    
    conn.commit()
    conn.close()

init_db()

# --- 2. HELPER FUNCTIONS ---
def save_uploaded_file(uploaded_file, name):
    if not os.path.exists("images"):
        os.makedirs("images")
    file_extension = uploaded_file.name.split('.')[-1] if hasattr(uploaded_file, 'name') else "jpg"
    unique_filename = f"{name.replace(' ', '_')}_{int(datetime.now().timestamp())}.{file_extension}"
    file_path = os.path.join("images", unique_filename)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return unique_filename

def create_pdf(dataframe, title):
    class PDF(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 15)
            self.cell(0, 10, title, 1, 1, 'C')
            self.ln(5)
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    cols = dataframe.columns.tolist()
    for col in cols:
        pdf.cell(40, 10, str(col), 1)
    pdf.ln()
    for i, row in dataframe.iterrows():
        for col in cols:
            txt_val = str(row[col])
            pdf.cell(40, 10, txt_val, 1)
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- 3. MAIN APPLICATION UI ---
st.title("🏭 Tobacco Factory Manager (Cloud)")

# --- SIDEBAR ---
st.sidebar.title("Navigation")
menu = st.sidebar.radio("Go to:", 
    ["🏠 Dashboard", "Take Attendance", "Manage Stock (In)", "Sold Stock (Out)", "Worker Reports", "Manage Workers", "🛠 Tools: Edit/Delete"])

# --- PAGE: DASHBOARD (HOME) ---
if menu == "🏠 Dashboard":
    st.header("📈 Factory Overview")
    
    conn = get_connection()
    current_month_str = datetime.now().strftime("%Y-%m")
    
    df_bundles = pd.read_sql(f"SELECT SUM(bundles_made) as total FROM attendance WHERE date LIKE '{current_month_str}%'", conn)
    total_bundles = df_bundles['total'].fillna(0).iloc[0]
    
    df_stock = pd.read_sql(f"SELECT SUM(quantity) as total FROM stock WHERE date LIKE '{current_month_str}%'", conn)
    total_stock = df_stock['total'].fillna(0).iloc[0]
    
    df_sales = pd.read_sql(f"SELECT SUM(quantity) as total FROM sold_stock WHERE date LIKE '{current_month_str}%'", conn)
    total_sales = df_sales['total'].fillna(0).iloc[0]
    
    col1, col2, col3 = st.columns(3)
    col1.metric("📦 Production (Month)", f"{int(total_bundles)} Bundles")
    col2.metric("⬇️ Stock In", f"{int(total_stock)} Units")
    col3.metric("⬆️ Sales", f"{int(total_sales)} Units")
    
    st.divider()

    st.subheader("🏭 Current Stock Availability")
    df_in = pd.read_sql("SELECT item_name, SUM(quantity) as total_in FROM stock GROUP BY item_name", conn)
    df_out = pd.read_sql("SELECT item_name, SUM(quantity) as total_out FROM sold_stock GROUP BY item_name", conn)
    
    if not df_in.empty:
        df_inventory = pd.merge(df_in, df_out, on="item_name", how="left").fillna(0)
        df_inventory['Available_Stock'] = df_inventory['total_in'] - df_inventory['total_out']
        df_display = df_inventory[['item_name', 'Available_Stock', 'total_in', 'total_out']]
        df_display.columns = ['Item Name', 'Available Balance', 'Total In', 'Total Sold']
        st.dataframe(df_display, use_container_width=True)
    else:
        st.info("No stock data available yet.")

    conn.close()

# --- PAGE: TOOLS (EDIT/DELETE) ---
elif menu == "🛠 Tools: Edit/Delete":
    st.header("🛠 Edit & Delete Data")
    tool_choice = st.selectbox("Select Data to Manage", ["Incoming Stock", "Sold Stock", "Workers"])
    conn = get_connection()
    
    if tool_choice == "Incoming Stock":
        st.subheader("Manage Incoming Stock")
        df = pd.read_sql("SELECT * FROM stock ORDER BY date DESC", conn)
        st.dataframe(df)
        row_id = st.number_input("Enter ID to Delete", min_value=0, step=1)
        if st.button("Delete Stock Entry"):
            c = conn.cursor()
            c.execute("DELETE FROM stock WHERE id=%s", (row_id,))
            conn.commit()
            st.success(f"Deleted ID {row_id}")
            st.rerun()

    elif tool_choice == "Sold Stock":
        st.subheader("Manage Sold Stock")
        df = pd.read_sql("SELECT * FROM sold_stock ORDER BY date DESC", conn)
        st.dataframe(df)
        row_id = st.number_input("Enter ID to Delete", min_value=0, step=1)
        if st.button("Delete Sale Entry"):
            c = conn.cursor()
            c.execute("DELETE FROM sold_stock WHERE id=%s", (row_id,))
            conn.commit()
            st.success(f"Deleted ID {row_id}")
            st.rerun()
            
    elif tool_choice == "Workers":
        st.subheader("Manage Workers")
        df = pd.read_sql("SELECT * FROM workers", conn)
        st.dataframe(df)
        row_id = st.number_input("Enter ID to Delete", min_value=0, step=1)
        if st.button("Delete Worker"):
            c = conn.cursor()
            c.execute("DELETE FROM attendance WHERE worker_id=%s", (row_id,))
            c.execute("DELETE FROM workers WHERE id=%s", (row_id,))
            conn.commit()
            st.success(f"Worker {row_id} Deleted")
            st.rerun()
    conn.close()

# --- PAGE: MANAGE WORKERS ---
elif menu == "Manage Workers":
    st.header("👷 Manage Workers")
    with st.expander("Add New Worker", expanded=True):
        with st.form("add_worker_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("Worker Name")
                role_options = ["Labor", "Packer", "Roller", "Supervisor", "Loader", "Driver", "Other"]
                new_desig = st.selectbox("Designation", role_options)
            with col2:
                new_rate = st.number_input("Daily Wage (₹)", min_value=0, value=500)
            
            st.write("Worker Photo (Note: Photos may reset on Cloud free tier)")
            col_cam, col_upl = st.columns(2)
            with col_cam:
                camera_photo = st.camera_input("Take Photo")
            with col_upl:
                uploaded_photo = st.file_uploader("Or Upload Image", type=['jpg', 'png', 'jpeg'])
            
            submitted = st.form_submit_button("Add Worker")
            if submitted:
                if not new_name:
                    st.error("Please enter a name.")
                else:
                    final_photo_name = "default.png"
                    if camera_photo is not None:
                        final_photo_name = save_uploaded_file(camera_photo, new_name)
                    elif uploaded_photo is not None:
                        final_photo_name = save_uploaded_file(uploaded_photo, new_name)
                    
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute("INSERT INTO workers (name, designation, photo_filename, daily_rate) VALUES (%s, %s, %s, %s)", 
                              (new_name, new_desig, final_photo_name, new_rate))
                    conn.commit()
                    conn.close()
                    st.success(f"Worker {new_name} added!")

    st.divider()
    st.subheader("Current Workers List")
    conn = get_connection()
    df_workers = pd.read_sql("SELECT * FROM workers", conn)
    conn.close()
    if not df_workers.empty:
        for i, row in df_workers.iterrows():
            with st.container():
                c1, c2, c3 = st.columns([1, 2, 4])
                with c1:
                    img_path = os.path.join("images", row['photo_filename'])
                    if os.path.exists(img_path):
                        st.image(img_path, width=80)
                with c2:
                    st.write(f"**{row['name']}**")
                    st.caption(row['designation'])
                with c3:
                    st.metric("Daily Rate", f"₹{row['daily_rate']}")
                st.divider()

# --- PAGE: TAKE ATTENDANCE ---
elif menu == "Take Attendance":
    st.header("📅 Daily Attendance & Production")
    att_date = st.date_input("Select Date", datetime.now())
    conn = get_connection()
    workers = pd.read_sql("SELECT * FROM workers", conn)
    conn.close()
    
    if workers.empty:
        st.warning("No workers found.")
    else:
        with st.form("attendance_form"):
            st.write(f"Marking attendance for: **{att_date}**")
            attendance_data = {}
            bundle_data = {}
            for index, row in workers.iterrows():
                col1, col2, col3, col4 = st.columns([1, 2, 1, 2])
                with col1:
                    img_path = os.path.join("images", row['photo_filename'])
                    if os.path.exists(img_path):
                        st.image(img_path, width=60)
                with col2:
                    st.subheader(row['name'])
                    st.caption(row['designation'])
                with col3:
                    is_present = st.checkbox("Present", key=f"chk_{row['id']}")
                    attendance_data[row['id']] = "Present" if is_present else "Absent"
                with col4:
                    b_count = st.number_input(f"Bundles", min_value=0, key=f"bun_{row['id']}")
                    bundle_data[row['id']] = b_count
                st.divider()

            submit_att = st.form_submit_button("Save Attendance")
            if submit_att:
                conn = get_connection()
                c = conn.cursor()
                for worker_id, status in attendance_data.items():
                    b_qty = bundle_data[worker_id] if status == 'Present' else 0
                    query = """
                    INSERT INTO attendance (date, worker_id, status, bundles_made) 
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (date, worker_id) 
                    DO UPDATE SET status = EXCLUDED.status, bundles_made = EXCLUDED.bundles_made;
                    """
                    c.execute(query, (str(att_date), worker_id, status, b_qty))
                conn.commit()
                conn.close()
                st.success("Saved!")

# --- PAGE: MANAGE STOCK (IN) ---
elif menu == "Manage Stock (In)":
    st.header("📦 Material Stock (Incoming)")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Add NEW Stock")
        stock_date = st.date_input("Date Received", datetime.now(), key="stock_in_date")
        item_name = st.text_input("Item Name")
        qty = st.number_input("Quantity Received", min_value=0)
        notes = st.text_area("Notes")
        if st.button("Add Incoming Stock"):
            conn = get_connection()
            c = conn.cursor()
            c.execute("INSERT INTO stock (date, item_name, quantity, notes) VALUES (%s, %s, %s, %s)",
                      (str(stock_date), item_name, qty, notes))
            conn.commit()
            conn.close()
            st.success("Stock Added!")
    with col2:
        st.subheader("Incoming History")
        conn = get_connection()
        stock_df = pd.read_sql("SELECT * FROM stock ORDER BY date DESC", conn)
        conn.close()
        st.dataframe(stock_df)

# --- PAGE: SOLD STOCK (OUT) ---
elif menu == "Sold Stock (Out)":
    st.header("🚚 Sold Stock (Outgoing)")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Record Sale")
        sale_date = st.date_input("Date Sold", datetime.now(), key="sale_date")
        sale_item = st.text_input("Item Sold")
        sale_qty = st.number_input("Quantity Sold", min_value=0)
        buyer_notes = st.text_area("Buyer Details")
        if st.button("Record Sale"):
            conn = get_connection()
            c = conn.cursor()
            c.execute("INSERT INTO sold_stock (date, item_name, quantity, buyer_notes) VALUES (%s, %s, %s, %s)",
                      (str(sale_date), sale_item, sale_qty, buyer_notes))
            conn.commit()
            conn.close()
            st.success("Sale Recorded!")
    with col2:
        st.subheader("Sales History")
        conn = get_connection()
        sold_df = pd.read_sql("SELECT * FROM sold_stock ORDER BY date DESC", conn)
        conn.close()
        st.dataframe(sold_df)

# --- PAGE: REPORTS ---
elif menu == "Worker Reports":
    st.header("📊 Factory Reports")
    tab1, tab2, tab3 = st.tabs(["💰 Payroll & Production", "📆 Daily View", "📦 Stock Reports"])
    
    current_year = datetime.now().year
    current_month_index = datetime.now().month - 1
    c1, c2 = st.columns(2)
    with c1:
        year_list = [2024, 2025, 2026, 2027]
        d_y = year_list.index(current_year) if current_year in year_list else 1
        sel_year = st.selectbox("Select Year", year_list, index=d_y, key="rep_year")
    with c2:
        month_list = ["01-Jan", "02-Feb", "03-Mar", "04-Apr", "05-May", "06-Jun", 
                      "07-Jul", "08-Aug", "09-Sep", "10-Oct", "11-Nov", "12-Dec"]
        sel_month = st.selectbox("Select Month", month_list, index=current_month_index, key="rep_month")
    month_num = sel_month.split("-")[0]
    filter_date = f"{sel_year}-{month_num}"

    with tab1:
        st.subheader(f"Payroll for {sel_month} {sel_year}")
        conn = get_connection()
        query_payroll = f'''
        SELECT w.name as Name, w.daily_rate as Rate,
        COUNT(CASE WHEN a.status = 'Present' AND a.date LIKE '{filter_date}%' THEN 1 END) as Days_Worked,
        SUM(CASE WHEN a.date LIKE '{filter_date}%' THEN a.bundles_made ELSE 0 END) as Total_Bundles,
        (COUNT(CASE WHEN a.status = 'Present' AND a.date LIKE '{filter_date}%' THEN 1 END) * w.daily_rate) as Total_Salary
        FROM workers w LEFT JOIN attendance a ON w.id = a.worker_id GROUP BY w.id
        '''
        df_payroll = pd.read_sql(query_payroll, conn)
        conn.close()
        st.dataframe(df_payroll, use_container_width=True)
        if not df_payroll.empty:
            st.metric("Total Salary", f"₹{df_payroll['Total_Salary'].sum()}")
            pdf_bytes = create_pdf(df_payroll, f"Payroll - {sel_month} {sel_year}")
            st.download_button("📄 Download PDF", pdf_bytes, f"Payroll_{filter_date}.pdf", "application/pdf")

    with tab2:
        st.subheader("Daily Status")
        view_date = st.date_input("Select Date", datetime.now(), key="dv_date")
        conn = get_connection()
        query_daily = f"SELECT w.name, COALESCE(a.status, 'Not Marked') as Status, COALESCE(a.bundles_made, 0) as Bundles FROM workers w LEFT JOIN attendance a ON w.id = a.worker_id AND a.date = '{view_date}'"
        df_daily = pd.read_sql(query_daily, conn)
        conn.close()
        def color_status(val):
            return f'color: {"green" if val == "Present" else "red"}'
        st.dataframe(df_daily.style.applymap(color_status, subset=['Status']), use_container_width=True)

    with tab3:
        st.subheader("Stock Reports")
        col_in, col_out = st.columns(2)
        with col_in:
            st.write("⬇️ **Incoming**")
            conn = get_connection()
            df_in = pd.read_sql(f"SELECT date, item_name, quantity FROM stock WHERE date LIKE '{filter_date}%'", conn)
            st.dataframe(df_in)
            if not df_in.empty:
                pdf_in = create_pdf(df_in, f"Incoming - {sel_month}")
                st.download_button("Download PDF", pdf_in, f"In_{filter_date}.pdf", "application/pdf", key="d_in")
        with col_out:
            st.write("⬆️ **Sold**")
            df_out = pd.read_sql(f"SELECT date, item_name, quantity FROM sold_stock WHERE date LIKE '{filter_date}%'", conn)
            conn.close()
            st.dataframe(df_out)
            if not df_out.empty:
                pdf_out = create_pdf(df_out, f"Sold - {sel_month}")
                st.download_button("Download PDF", pdf_out, f"Out_{filter_date}.pdf", "application/pdf", key="d_out")
