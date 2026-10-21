"""
app.py
------
Streamlit web interface for ribbed slab continuous design tool.
Allows interactive manipulation of reinforcement and continuous real-time checks.
"""

import streamlit as st
from ribbed_slab_design import ProjectInfo, RibbedSlab, Loads, DesignParams, RibbedSlabSystem

st.set_page_config(page_title="Ribbed Slab Design Tool", layout="wide")

st.title("Ribbed Slab Design Tool (BS 8110)")
st.markdown("Interactive design checker and formal PDF generator.")

with st.sidebar:
    st.header("1. Project Information")
    job_no = st.text_input("Job No.", value="IES-009-2024-ERICK & JACKLINE TATU CITY")
    designer = st.text_input("Designer", value="R.D.K")
    element = st.text_input("Element", value="ROOF TERRACE RIBBED SLAB")
    panel_ref = st.text_input("Panel Reference", value="PANEL 5 BETWEEN GRIDS 8-13/H-B")
    
    st.header("2. Materials")
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
    
    block_width_mm = st.number_input("Hollow Block Width (mm)", min_value=200.0, value=375.0, step=25.0)
    block_length_mm = st.number_input("Hollow Block Length (mm)", min_value=200.0, value=225.0, step=25.0)
    block_weight_kg = st.number_input("Weight of 1 Block (kg)", min_value=5.0, value=20.5, step=0.5)
    blocks_per_sqm = st.number_input("Blocks per m²", min_value=5.0, value=10.0, step=0.5)
    
    cover_mm = st.number_input("Cover (mm)", min_value=15.0, value=25.0, step=5.0)

with col2:
    st.subheader("4. Applied Loads & Moment Coefficients")
    finishes_kNm2 = st.number_input("Finishes (kN/m²)", min_value=0.0, value=2.50, step=0.1)
    solar_panels_kNm2 = st.number_input("Solar Panels / Partitions (kN/m²)", min_value=0.0, value=0.12, step=0.05)
    live_load_kNm2 = st.number_input("Live Load Qk (kN/m²)", min_value=0.0, value=5.0, step=0.5)
    
    span_type = st.selectbox("Span Type", ["End Span (Continuous)", "Interior Span (Continuous)", "Simply Supported"])
    if span_type == "End Span (Continuous)":
        c_sup, c_mid, c_sh = 0.086, 0.063, 0.6
    elif span_type == "Interior Span (Continuous)":
        c_sup, c_mid, c_sh = 0.063, 0.063, 0.5
    else:
        c_sup, c_mid, c_sh = 0.0, 0.125, 0.5

st.markdown("---")
st.subheader("5. Interactive Design Checking")
st.markdown("Adjust reinforcement below and check real-time compliance before generating the PDF.")

c_prov1, c_prov2, c_prov3 = st.columns(3)

with c_prov1:
    st.markdown("**Midspan (Bottom Steel)**")
    mid_bar_n = st.number_input("No. of bars (per rib)", min_value=1, value=3, step=1)
    mid_bar_dia = st.selectbox("Bar Diameter (mm)", [10.0, 12.0, 16.0, 20.0], index=1, key='mbd')

with c_prov2:
    st.markdown("**Supports (Top Steel)**")
    sup_bar_dia = st.selectbox("Bar Diameter (mm)", [10.0, 12.0, 16.0, 20.0], index=1, key='sbd')
    sup_bar_spacing = st.number_input("Spacing (mm c/c)", min_value=50.0, value=125.0, step=25.0)

with c_prov3:
    st.markdown("**Shear Links**")
    link_dia = st.selectbox("Link Diameter (mm)", [8.0, 10.0, 12.0], index=0)
    link_spacing = st.number_input("Link Spacing (mm c/c)", min_value=50.0, value=250.0, step=25.0)

# Real-time computation
proj = ProjectInfo(job_no=job_no, designer=designer, element=element, panel_ref=panel_ref)
slab = RibbedSlab(span_m=span_m, rib_width_mm=rib_width_mm, rib_depth_mm=rib_depth_mm, 
                  topping_mm=topping_mm, block_width_mm=block_width_mm, block_length_mm=block_length_mm,
                  block_weight_kg=block_weight_kg, blocks_per_sqm=blocks_per_sqm,
                  cover_mm=cover_mm, mid_bar_n=mid_bar_n, mid_bar_dia=mid_bar_dia,
                  sup_bar_dia=sup_bar_dia, sup_bar_spacing=sup_bar_spacing,
                  link_dia=link_dia, link_spacing=link_spacing)
loads = Loads(solar_panels_kNm2=solar_panels_kNm2, finishes_kNm2=finishes_kNm2, live_load_kNm2=live_load_kNm2)
params = DesignParams(fcu=fcu, fy=fy, fyv=fyv, coef_mid_moment=c_mid, coef_sup_moment=c_sup, coef_shear=c_sh)

sys = RibbedSlabSystem(proj, slab, loads, params)
sys.compute()
r = sys.res

st.markdown("#### Design Status")
d1, d2, d3, d4 = st.columns(4)

# Midspan Status
if r['mid_status'] == "PASS":
    d1.success(f"**Midspan: PASS**\n\nReq: {r['As_mid_req']:.1f} mm²\nProv: {r['As_mid_prov']:.1f} mm²")
else:
    d1.error(f"**Midspan: FAIL**\n\nReq: {r['As_mid_req']:.1f} mm²\nProv: {r['As_mid_prov']:.1f} mm²")

# Support Status
if r['sup_status'] == "PASS":
    d2.success(f"**Support: PASS**\n\nReq: {r['As_sup_req_pm']:.1f} mm²/m\nProv: {r['As_sup_prov_pm']:.1f} mm²/m")
else:
    d2.error(f"**Support: FAIL**\n\nReq: {r['As_sup_req_pm']:.1f} mm²/m\nProv: {r['As_sup_prov_pm']:.1f} mm²/m")

# Shear Status
if r['shear_status'] == "PASS":
    d3.success(f"**Shear: PASS**\n\nCondition: {r['shear_msg']}\nReq sv: {r['sv_req']:.1f} mm\nProv sv: {slab.link_spacing} mm")
else:
    d3.error(f"**Shear: FAIL**\n\nCondition: {r['shear_msg']}\nReq sv: {r['sv_req']:.1f} mm\nProv sv: {slab.link_spacing} mm")

# Deflection Status
if r['deflection_status'] == "PASS":
    d4.success(f"**Deflection: PASS**\n\nActual L/d: {r['actual_ratio']:.1f}\nAllowable: {r['allow_ratio']:.1f}")
else:
    d4.error(f"**Deflection: FAIL**\n\nActual L/d: {r['actual_ratio']:.1f}\nAllowable: {r['allow_ratio']:.1f}")

st.markdown("---")

if st.button("Generate Formal PDF Report", type="primary"):
    pdf_file = "Ribbed_Slab_Design_Report.pdf"
    sys.generate_pdf(pdf_file)
    with open(pdf_file, "rb") as f:
        st.download_button(
            label="Download PDF Calculation Report",
            data=f,
            file_name=pdf_file,
            mime="application/pdf"
        )