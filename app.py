import streamlit as st
import pandas as pd
from sqlalchemy import text

# Initialize Connection
conn = st.connection("postgresql", type="sql")

# ==========================================
# 1. COMPONENT VALIDATION LOGIC
# ==========================================
def check_marks_limit(df, mark_col, max_val):
    invalid = df[df[mark_col] > max_val]
    return invalid

# ==========================================
# 2. FACULTY INTERFACE (CIE/ISE/Practical)
# ==========================================
def faculty_interface():
    st.header("👨‍🏫 Faculty Entry Portal")
    
    # Query assigned subjects (simulated filter)
    subjects_df = conn.query("SELECT * FROM subjects", ttl="1h")
    selected_sub = st.selectbox("Select Subject", subjects_df['code'].tolist())
    sub_info = subjects_df[subjects_df['code'] == selected_sub].iloc[0]

    if sub_info['course_type'] == 'Theory':
        # Faculty handles CIE and ISE
        c1, c2 = st.columns(2)
        f_cie = c1.file_uploader("Upload CIE CSV (ID, Marks, Attendance)", type=['csv'])
        f_ise = c2.file_uploader("Upload ISE CSV (ID, Marks)", type=['csv'])
        
        if f_cie:
            df = pd.read_csv(f_cie)
            # Validation logic
            invalid = check_marks_limit(df, 'marks', sub_info['cie_max'])
            if not invalid.empty:
                st.error(f"Error: Some CIE marks exceed {sub_info['cie_max']}")
            else:
                if st.button("Sync CIE to Cloud"):
                    with conn.session as s:
                        for _, row in df.iterrows():
                            s.execute(text("""
                                INSERT INTO marks_master (student_id, subject_code, cie_marks, attendance)
                                VALUES (:id, :code, :m, :att)
                                ON CONFLICT (student_id, subject_code) 
                                DO UPDATE SET cie_marks = :m, attendance = :att
                            """), params={"id": row['id'], "code": selected_sub, "m": row['marks'], "att": row['attendance']})
                        s.commit()
                    st.success("CIE Marks Synchronized.")

    else: # Practical logic
        st.info("Upload ISE and ESE for Practical Components")
        # Similar implementation for Practical CSVs...


# ==========================================
# 3. DEPUTY COE INTERFACE (Theory ESE)
# ==========================================
def coe_interface():
    st.header("🏛️ Deputy COE: Theory ESE Entry")
    # Query Theory subjects only
    theory_subs = conn.query("SELECT * FROM subjects WHERE course_type='Theory'", ttl="1h")
    target_sub = st.selectbox("Select Subject for ESE", theory_subs['code'].tolist())
    sub_info = theory_subs[theory_subs['code'] == target_sub].iloc[0]

    f_ese = st.file_uploader("Upload ESE Master CSV", type=['csv'])
    if f_ese:
        df = pd.read_csv(f_ese)
        # Handle 'AB' as string, validate numeric values
        if st.button("Finalize ESE Upload"):
            with conn.session as s:
                for _, row in df.iterrows():
                    s.execute(text("""
                        UPDATE marks_master 
                        SET ese_marks = :m 
                        WHERE student_id = :id AND subject_code = :code
                    """), params={"id": row['id'], "code": target_sub, "m": str(row['marks'])})
                s.commit()
            st.success("Theory ESE marks finalized in cloud.")



import streamlit as st
import pandas as pd
from sqlalchemy import text

# Assuming 'conn' is already initialized as:
# conn = st.connection("postgresql", type="sql")

def admin_dashboard():
    st.header("🛡️ Examination Controller Dashboard")
    
    # 1. Fetch Master Data
    subjects = conn.query("SELECT * FROM subjects", ttl="0")
    marks = conn.query("SELECT * FROM marks_master", ttl="0")
    
    if marks.empty:
        st.warning("No marks have been uploaded yet by Faculty or Deputy COE.")
        return

    # 2. Check for Missing Components
    st.subheader("📊 Data Completion Status")
    
    # We want to find if any CIE, ISE, or ESE is '0' or NULL
    # This logic identifies incomplete rows
    incomplete_cie = marks[marks['cie_marks'] == 0]
    incomplete_ise = marks[marks['ise_marks'] == 0]
    incomplete_ese = marks[marks['ese_marks'].astype(str) == '0']

    col1, col2, col3 = st.columns(3)
    col1.metric("Missing CIE", len(incomplete_cie))
    col2.metric("Missing ISE", len(incomplete_ise))
    col3.metric("Missing ESE", len(incomplete_ese))

    # 3. Validation: Marks vs Max Marks
    st.subheader("🚫 Validation Errors (Marks > Max)")
    
    # Merge marks with subject rules to compare
    merged = pd.merge(marks, subjects, left_on='subject_code', right_on='code')
    
    # Check for violations
    error_cie = merged[merged['cie_marks'] > merged['cie_max']]
    error_ise = merged[merged['ise_marks'] > merged['ise_max']]
    # ESE check (handles numeric conversion for 'AB')
    merged['ese_numeric'] = pd.to_numeric(merged['ese_marks'], errors='coerce').fillna(0)
    error_ese = merged[merged['ese_numeric'] > merged['ese_max']]

    if not error_cie.empty or not error_ise.empty or not error_ese.empty:
        st.error("Action Required: Some entries exceed the maximum allowed marks!")
        st.write(pd.concat([error_cie, error_ise, error_ese]))
    else:
        st.success("All uploaded marks are within valid limits.")

    # 4. Final Processing Trigger
    st.divider()
    st.subheader("🏁 Finalize Semester Results")
    
    ready_to_process = (len(incomplete_cie) == 0 and 
                        len(incomplete_ise) == 0 and 
                        len(incomplete_ese) == 0 and
                        len(error_cie) == 0)

    if ready_to_process:
        if st.button("Calculate SGPA & Generate Master Sheet", type="primary"):
            # Run your Protocol A / Protocol B logic here
            st.balloons()
            st.success("Final Result Sheet Generated!")
    else:
        st.button("Calculate SGPA", disabled=True, help="Complete all marks entry to enable.")
        st.info("The 'Calculate SGPA' button is disabled until all faculty and COE entries are 100% complete.")

# ==========================================
# 4. MAIN NAVIGATION
# ==========================================
def main():
    st.sidebar.title("🔐 KITS ERP Access Control")
    
    # 1. Select Role
    role = st.sidebar.selectbox("Access Role", 
                                ["Faculty Portal", "Deputy COE Portal", "Admin Dashboard"])
    
    # 2. Password Gatekeeper
    password_input = st.sidebar.text_input(f"Enter Password for {role}", type="password")
    
    # 3. Access Logic
    if role == "Admin Dashboard":
        if password_input == st.secrets["passwords"]["admin"]:
            admin_dashboard()
        elif password_input == "":
            st.info("Please enter the Admin password in the sidebar.")
        else:
            st.error("🚫 Access Denied: Incorrect Admin Password")

    elif role == "Deputy COE Portal":
        if password_input == st.secrets["passwords"]["coe"]:
            coe_interface()
        elif password_input == "":
            st.info("Please enter the Deputy COE password.")
        else:
            st.error("🚫 Access Denied: Incorrect COE Password")

    elif role == "Faculty Portal":
        if password_input == st.secrets["passwords"]["faculty"]:
            faculty_interface()
        elif password_input == "":
            st.info("Please enter the Faculty password.")
        else:
            st.error("🚫 Access Denied: Incorrect Faculty Password")

if __name__ == "__main__":
    main()
      
