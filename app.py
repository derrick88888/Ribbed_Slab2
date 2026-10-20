"""
app.py
------
Streamlit web interface for ribbed slab continuous design tool.
"""

import streamlit as st
import datetime
from ribbed_slab_design import ProjectInfo, RibbedSlab, Loads, DesignParams, RibbedSlabSystem

st.set_page_config(page_title="Ribbed Slab Design Tool", layout="wide")

st.title("Ribbed Slab Design Tool (BS 8110)")
st.markdown("Generates a comprehensive design and PDF calculation report exactly matching the standard calculation format.")

# Session state initialization
if 'pdf_generated' not in st.session_state:
    st.session_state.pdf_generated = False
if 'pdf_filename' not in st.session_state:
    st.session_state.pdf_filename = ""

with st.sidebar:
    st.header("1. Project Information")
    job_no = st.text_input("Job No.", value="IES-009-2024-ERICK & JACKLINE TATU CITY")
    designer = st.text_input("Designer", value="RIDOK")
    element = st.text_input("Element", value="ROOF TERRACE RIBBED SLAB")
    panel_ref = st.text_input("Panel Reference", value="PANEL 5 BETWEEN GRIDS 8-13/H-B")
    
    st.header("2. Materials & Parameters")
    fcu = st.number_input("Concrete Grade fcu (N/mm²)", value=25.0, step=5.0)
    fy = st.number_input("Main Steel fy (N/mm²)", value=460.0, step=10.0)
    fyv = st.number_input("Link Steel fyv (N/mm²)", value=460.0, step=10.0)

col1, col2 = st.columns(2)

with col1:
    st.subheader("3. Geometry")
    span_m = st.number_input("Span L (m)", min_value=1.0, value=6.8, step=0.1)
    rib_width_mm = st.number_input("Rib Width bw (mm)", min_value=100.0, value=150.0, step=25.0)
    rib_depth_mm = st.number_input("Rib Depth (mm) [excl. topping]", min_value=100.0, value=200.0, step=25.0)
    topping_mm = st.number_input("Topping hf (mm)", min_value=40.0, value=100.0, step=10.0)
    
    block_width_mm = st.number_input("Hollow Block Width (mm) [determines rib spacing]", min_value=200.0, value=375.0, step=25.0)
    block_length_mm = st.number_input("Hollow Block Length (mm)", min_value=200.0, value=225.0, step=25.0)
    block_weight_kg = st.number_input("Weight of 1 Block (kg)", min_value=5.0, value=20.5, step=0.5)
    blocks_per_sqm = st.number_input("Blocks per m²", min_value=5.0, value=10.0, step=0.5)
    
    cover_mm = st.number_input("Cover (mm)", min_value=15.0, value=25.0, step=5.0)

with col2:
    st.subheader("4. Applied Loads")
    finishes_kNm2 = st.number_input("Finishes (kN/m²)", min_value=0.0, value=2.50, step=0.1)
    solar_panels_kNm2 = st.number_input("Solar Panels / Partitions (kN/m²)", min_value=0.0, value=0.12, step=0.05)
    live_load_kNm2 = st.number_input("Live Load Qk (kN/m²)", min_value=0.0, value=5.0, step=0.5)
    
    st.subheader("5. Design Options")
    span_type = st.selectbox("Span Type (BS 8110 Moment Coefficients)", 
                             options=["End Span (Continuous)", "Interior Span (Continuous)", "Simply Supported"])
    
    bar_dia_mm = st.selectbox("Midspan Bar Diameter (mm)", [10.0, 12.0, 16.0, 20.0, 25.0], index=1)
    support_bar_dia_mm = st.selectbox("Support Bar Diameter (mm)", [10.0, 12.0, 16.0, 20.0, 25.0], index=1)
    link_dia_mm = st.selectbox("Shear Link Diameter (mm)", [8.0, 10.0, 12.0], index=0)

if span_type == "End Span (Continuous)":
    c_sup = 0.086; c_mid = 0.063; c_sh = 0.6
elif span_type == "Interior Span (Continuous)":
    c_sup = 0.063; c_mid = 0.063; c_sh = 0.5
else:
    c_sup = 0.0; c_mid = 0.125; c_sh = 0.5

if st.button("Run Design & Generate PDF", type="primary"):
    proj = ProjectInfo(job_no=job_no, designer=designer, element=element, panel_ref=panel_ref)
    slab = RibbedSlab(span_m=span_m, rib_width_mm=rib_width_mm, rib_depth_mm=rib_depth_mm, 
                      topping_mm=topping_mm, block_width_mm=block_width_mm, block_length_mm=block_length_mm,
                      block_weight_kg=block_weight_kg, blocks_per_sqm=blocks_per_sqm,
                      cover_mm=cover_mm, bar_dia_mm=bar_dia_mm, support_bar_dia_mm=support_bar_dia_mm,
                      link_dia_mm=link_dia_mm)
    loads = Loads(solar_panels_kNm2=solar_panels_kNm2, finishes_kNm2=finishes_kNm2, live_load_kNm2=live_load_kNm2)
    params = DesignParams(fcu=fcu, fy=fy, fyv=fyv, coef_mid_moment=c_mid, coef_sup_moment=c_sup, coef_shear=c_sh)
    
    sys = RibbedSlabSystem(proj, slab, loads, params)
    sys.compute()
    
    pdf_file = "Ribbed_Slab_Design_Report.pdf"
    sys.generate_pdf(pdf_file)
    
    st.session_state.pdf_generated = True
    st.session_state.pdf_filename = pdf_file
    st.session_state.res = sys.res

if st.session_state.pdf_generated:
    st.success("Design completed successfully!")
    r = st.session_state.res
    
    st.subheader("Key Results Summary")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Ultimate UDL (per rib)", f"{r['udl']:.2f} kN/m")
    r2.metric("Max Moment", f"{max(r['M_mid'], r['M_sup']):.2f} kNm")
    r3.metric("Midspan Steel Prov", f"{r['num_bars_mid']}T{int(bar_dia_mm)}")
    r4.metric("Support Steel Prov", f"T{int(support_bar_dia_mm)}@{r['spacing_sup']:.0f}")
    
    with open(st.session_state.pdf_filename, "rb") as f:
        st.download_button(
            label="Download PDF Calculation Report",
            data=f,
            file_name=st.session_state.pdf_filename,
            mime="application/pdf"
        )