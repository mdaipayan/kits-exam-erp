import streamlit as st
import pandas as pd
import numpy as np
from sqlalchemy import text

# ==========================================
# 1. INITIALIZATION & HELPERS
# ==========================================
conn = st.connection("postgresql", type="sql")

def check_marks_limit(df, mark_col, max_val):
    """Returns rows where marks exceed the allowed maximum."""
    return df[df[mark_col] > max_val]

def sync_to_supabase(df, sub_code, component, has_attendance=False, is_ese=False):
    """Handles the heavy lifting of updating the cloud database."""
    with conn.session as s:
        for _, row in df.iterrows():
            # Handle ESE as string (for 'AB'), others as numeric
            val = str(row['marks']) if is_ese else float(row['marks'])
            att = float(row['attendance']) if has_attendance else 0
            
            query = text(f"""
                INSERT INTO marks_master (student_id, subject_code, {component}, attendance)
                VALUES (:id, :code, :val, :att)
                ON CONFLICT (student_id, subject_code) 
                DO UPDATE SET {component} = :val {" , attendance = :att" if has_attendance else ""}
            """)
            s.execute(query, params={"id": str(row['id']), "code": sub_code, "val": val, "att": att})
        s.commit()
    st.success(f"Successfully synchronized {len(df)} records for {component}!")

# ==========================================
# 2. THE GRADING ENGINE (Logic Layer)
# ==========================================
class kits_grading_engine:
    @staticmethod
    def calculate_relative_thresholds(marks, total_max, p_threshold):
        """Calculates D-grade boundary based on statistics."""
        if len(marks) < 30: # Absolute Grading for small batches
            return 0.40 * total_max
        
        avg = np.mean(marks)
        std = np.std(marks)
        relative_d = avg - 1.5 * std
        
        # Clamp between 30% and P-threshold
        return max(0.30 * total_max, min(relative_d, p_threshold))

    @staticmethod
    def assign_grade(mark, threshold, total_max):
        """Standard relative grading distribution."""
        if mark < threshold: return 'F'
        # Simple linear distribution for A+ to C
        # In your final version, you can insert the full Mean/Sigma table here
        if mark >= 0.9 * total_max: return 'A+'
        if mark >= 0.8 * total_max: return 'A'
        if mark >= threshold: return 'D'
        return 'F'

# ==========================================
# 3. INTERFACE: FACULTY PORTAL
# ==========================================
def faculty_interface():
    st.header("👨‍🏫 Faculty Mark Entry Portal")
    
    subjects_df = conn.query("SELECT * FROM subjects", ttl="1h")
    selected_code = st.selectbox("Select Subject", subjects_df['code'].tolist())
    sub_info = subjects_df[subjects_df['code'] == selected_code].iloc[0]

    st.info(f"Subject: {sub_info['name']} | Type: {sub_info['course_type']}")

    # Split logic for Theory vs Practical
    is_theory = sub_info['course_type'] == 'Theory'
    
    col1, col2 = st.columns(2)
    
    with col1:
        comp1 = "CIE" if is_theory else "Practical ISE"
        max1 = sub_info['cie_max'] if is_theory else sub_info['ise_max']
        db_col1 = "cie_marks" if is_theory else "ise_marks"
        
        f1 = st.file_uploader(f"Upload {comp1} (Max: {max1})", type=['csv'], key="f1")
        if f1:
            df = pd.read_csv(f1)
            df.columns = df.columns.str.strip().lower()
            if not check_marks_limit(df, 'marks', max1).empty:
                st.error("Validation Error: Marks exceed maximum!")
            elif st.button(f"Sync {comp1}"):
                sync_to_supabase(df, selected_code, db_col1, has_attendance=True)

    with col2:
        comp2 = "ISE" if is_theory else "Practical ESE"
        max2 = sub_info['ise_max'] if is_theory else sub_info['ese_max']
        db_col2 = "ise_marks" if is_theory else "ese_marks"
        
        f2 = st.file_uploader(f"Upload {comp2} (Max: {max2})", type=['csv'], key="f2")
        if f2:
            df = pd.read_csv(f2)
            df.columns = df.columns.str.strip().lower()
            if not check_marks_limit(df, 'marks', max2).empty:
                st.error("Validation Error: Marks exceed maximum!")
            elif st.button(f"Sync {comp2}"):
                sync_to_supabase(df, selected_code, db_col2, is_ese=(not is_theory))

# ==========================================
# 4. INTERFACE: DEPUTY COE (Theory ESE)
# ==========================================
def coe_interface():
    st.header("🏛️ Deputy COE: Theory ESE Entry")
    theory_subs = conn.query("SELECT * FROM subjects WHERE course_type='Theory'", ttl="0")
    target_sub = st.selectbox("Select Subject", theory_subs['code'].tolist())
    sub_info = theory_subs[theory_subs['code'] == target_sub].iloc[0]

    f_ese = st.file_uploader("Upload ESE CSV (id, marks)", type=['csv'])
    if f_ese:
        df = pd.read_csv(f_ese)
        df.columns = df.columns.str.strip().lower()
        if st.button("Finalize ESE Upload"):
            sync_to_supabase(df, target_sub, 'ese_marks', is_ese=True)

# ==========================================
# 5. INTERFACE: ADMIN DASHBOARD
# ==========================================
def admin_dashboard():
    st.header("🛡️ Examination Controller Dashboard")
    subjects = conn.query("SELECT * FROM subjects", ttl="0")
    marks = conn.query("SELECT * FROM marks_master", ttl="0")
    
    if marks.empty:
        st.warning("Awaiting data uploads...")
        return

    # Data Status Metrics
    incomplete_ese = marks[marks['ese_marks'].astype(str) == '0']
    st.metric("Pending ESE Entries", len(incomplete_ese))

   # Inside admin_dashboard() function, under "Final Processing Trigger":
    if st.button("Calculate SGPA & Generate Master Sheet", type="primary"):
        st.write("### ⚙️ Processing Final Tabulation...")
        
        # 1. Prepare Data
        df = pd.merge(marks, subjects, left_on='subject_code', right_on='code')
        df['ese_numeric'] = pd.to_numeric(df['ese_marks'], errors='coerce').fillna(0)
        df['total_marks'] = df['cie_marks'] + df['ise_marks'] + df['ese_numeric']
        
        # 2. Set Hurdles and Boundaries
        # Hurdle: ESE must be >= 20% of Max ESE
        df['ese_hurdle_passed'] = df['ese_numeric'] >= (0.2 * df['ese_max'])
        
        # Boundary: For this logic, we use 40% as the D-grade boundary
        # (You can replace '40' with your kits_grading_engine.calculate_relative_thresholds)
        df['passing_boundary'] = 0.40 * df['total_max']

        # 3. Identify Grace Eligibility (Per Student)
        # Requirement: Student must have cleared the ESE hurdle in ALL subjects
        ese_status = df.groupby('student_id')['ese_hurdle_passed'].all().reset_index()
        ese_status.columns = ['student_id', 'eligible_for_grace']
        df = pd.merge(df, ese_status, on='student_id')

        # 4. Preliminary Grading & Grace Identification
        def compute_final_grade(row):
            # If they failed the ESE Hurdle, it's an automatic F
            if not row['ese_hurdle_passed']:
                return 'F'
            
            # If they naturally passed
            if row['total_marks'] >= row['passing_boundary']:
                # (Insert full A+ to D logic here)
                return 'D' 
            
            # Grace Candidate: 
            # Needs <= 3 marks AND is eligible (passed all ESE hurdles)
            gap = row['passing_boundary'] - row['total_marks']
            if row['eligible_for_grace'] and gap <= 3:
                return 'Grace_Candidate'
            
            return 'F'

        df['temp_grade'] = df.apply(compute_final_grade, axis=1)

        # 5. Apply the "Max 2 Subjects" Rule
        grace_counts = df[df['temp_grade'] == 'Grace_Candidate'].groupby('student_id').size().reset_index()
        grace_counts.columns = ['student_id', 'num_grace_needed']
        df = pd.merge(df, grace_counts, on='student_id', how='left').fillna({'num_grace_needed': 0})

        def finalize_grade(row):
            if row['temp_grade'] == 'Grace_Candidate':
                if row['num_grace_needed'] <= 2:
                    return 'D*' # Award Grace
                else:
                    return 'F'  # Too many grace subjects needed
            return row['temp_grade']

        df['final_grade'] = df.apply(finalize_grade, axis=1)

        # 6. Generate Master View
        master_sheet = df.pivot(index='student_id', columns='code', values='final_grade')
        
        # Highlighting for the Admin
        def color_grades(val):
            if val == 'D*': return 'color: blue; font-weight: bold'
            if val == 'F': return 'color: red'
            return ''

        st.subheader("📋 Final Tabulation Register (Provisional)")
        st.dataframe(master_sheet.style.applymap(color_grades), use_container_width=True)
        
        st.balloons()
        st.download_button("📥 Download Official CSV", master_sheet.to_csv(), "KITS_Master_Sheet.csv")
# ==========================================
# 6. MAIN NAVIGATION
# ==========================================
def main():
    st.sidebar.title("🎓 KITS Exam Cloud ERP")
    role = st.sidebar.selectbox("Role", ["Faculty Portal", "Deputy COE Portal", "Admin Dashboard"])
    pwd = st.sidebar.text_input("Password", type="password")

    # Access Logic
    if pwd == "":
        st.info("Enter password to proceed.")
    elif role == "Admin Dashboard" and pwd == st.secrets["passwords"]["admin"]:
        admin_dashboard()
    elif role == "Deputy COE Portal" and pwd == st.secrets["passwords"]["coe"]:
        coe_interface()
    elif role == "Faculty Portal" and pwd == st.secrets["passwords"]["faculty"]:
        faculty_interface()
    else:
        st.error("Incorrect Password.")

if __name__ == "__main__":
    main()
