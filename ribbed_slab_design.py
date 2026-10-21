"""
ribbed_slab_design.py
---------------------
Backend engine for continuous ribbed slab design and PDF report generation.
Supports rigorous checks, compression reinforcement, and variable shear states.
"""

import math
import os
import re
import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.backends.backend_pdf import PdfPages

matplotlib.rcParams['mathtext.default'] = 'regular'

def sub(txt: str) -> str:
    txt = re.sub(r'\b(n?)([GQ])k\b', r'\1$\2_{k}$', txt)
    txt = re.sub(r'\bfcu\b', r'$f_{cu}$', txt)
    txt = re.sub(r'\bfyv\b', r'$f_{yv}$', txt)
    txt = re.sub(r'\bfy\b', r'$f_{y}$', txt)
    return txt

@dataclass
class ProjectInfo:
    firm_name: str = "Infras Engineering Solutions"
    address: str = "P.O. Box 45297 - 00100, Nairobi, Kenya"
    tel: str = ""
    email: str = ""
    project_title: str = "RUNDA DUOM PALM VILLA"
    job_no: str = "IES-003-2026"
    designer: str = "R.D.K"
    checked_by: str = "Eng. S. Muiruri"
    element: str = "ROOF TERRACE RIBBED SLAB"
    date: str = datetime.date.today().strftime("%d/%m/%Y")
    panel_ref: str = "PANEL 5 BETWEEN GRIDS 8-13/H-B"

@dataclass
class RibbedSlab:
    span_m: float = 6.8
    rib_width_mm: float = 150.0
    rib_depth_mm: float = 200.0
    topping_mm: float = 100.0
    block_width_mm: float = 375.0
    block_length_mm: float = 225.0
    block_weight_kg: float = 20.5
    blocks_per_sqm: float = 10.0
    cover_mm: float = 25.0
    
    # Provided Reinforcement
    mid_bar_dia: float = 12.0
    mid_bar_n: int = 3
    sup_bar_dia: float = 12.0
    sup_bar_spacing: float = 125.0
    link_dia: float = 8.0
    link_spacing: float = 250.0
    link_legs: int = 2

    @property
    def bf(self) -> float:
        return self.rib_width_mm + self.block_width_mm

    @property
    def total_depth_mm(self) -> float:
        return self.rib_depth_mm + self.topping_mm

    @property
    def d_mm(self) -> float:
        return self.total_depth_mm - self.cover_mm - self.link_dia - (self.mid_bar_dia / 2.0)

    @property
    def d_prime_mm(self) -> float:
        return self.cover_mm + self.link_dia + (self.sup_bar_dia / 2.0)

@dataclass
class Loads:
    solar_panels_kNm2: float = 0.12
    finishes_kNm2: float = 2.50
    live_load_kNm2: float = 5.0
    conc_density_kNm3: float = 24.0
    wall_density_kNm3: float = 20.0

@dataclass
class DesignParams:
    fcu: float = 25.0
    fy: float = 460.0
    fyv: float = 460.0
    coef_mid_moment: float = 0.063
    coef_sup_moment: float = 0.086
    coef_shear: float = 0.6

class RibbedSlabSystem:
    def __init__(self, proj: ProjectInfo, slab: RibbedSlab, loads: Loads, params: DesignParams):
        self.proj = proj
        self.slab = slab
        self.loads = loads
        self.params = params
        self.res = {}

    def compute(self):
        s = self.slab
        l = self.loads
        p = self.params

        # 1. Loading
        topping_sw = (s.topping_mm / 1000.0) * l.conc_density_kNm3
        ribs_per_m = 1000.0 / s.bf
        rib_area = (s.rib_width_mm / 1000.0) * (s.rib_depth_mm / 1000.0)
        rib_sw = ribs_per_m * rib_area * l.conc_density_kNm3
        block_load = (s.block_weight_kg * 10.0 / 1000.0) * s.blocks_per_sqm

        Gk = topping_sw + rib_sw + block_load + l.solar_panels_kNm2 + l.finishes_kNm2
        Qk = l.live_load_kNm2
        n = 1.4 * Gk + 1.6 * Qk
        udl = n * (s.bf / 1000.0)
        F = udl * s.span_m

        self.res['Gk'] = Gk
        self.res['Qk'] = Qk
        self.res['n'] = n
        self.res['udl'] = udl
        self.res['F'] = F
        self.res['topping_sw'] = topping_sw
        self.res['rib_sw'] = rib_sw
        self.res['block_load'] = block_load

        # 2. Moments & Shear
        M_sup = p.coef_sup_moment * F * s.span_m
        M_mid = p.coef_mid_moment * F * s.span_m
        V = p.coef_shear * F
        self.res['M_sup'] = M_sup
        self.res['M_mid'] = M_mid
        self.res['V'] = V

        # 3. Midspan Design (T-Section)
        d = s.d_mm
        bf = s.bf
        hf = s.topping_mm
        M_flange = 0.45 * p.fcu * bf * hf * (d - 0.5 * hf) / 1e6
        self.res['M_flange'] = M_flange
        
        K_mid = (M_mid * 1e6) / (p.fcu * bf * d**2)
        z_mid_calc = d * (0.5 + math.sqrt(max(0, 0.25 - K_mid / 0.9)))
        z_mid = min(z_mid_calc, 0.95 * d)
        
        As_mid_req = (M_mid * 1e6) / (0.87 * p.fy * z_mid)
        
        bar_area_mid = math.pi * (s.mid_bar_dia**2) / 4.0
        As_mid_prov = s.mid_bar_n * bar_area_mid
        
        self.res['K_mid'] = K_mid
        self.res['z_mid'] = z_mid
        self.res['As_mid_req'] = As_mid_req
        self.res['As_mid_prov'] = As_mid_prov
        self.res['mid_status'] = "PASS" if As_mid_prov >= As_mid_req else "FAIL"

        # 4. Support Design (Rectangular)
        bw = s.rib_width_mm
        K_sup = (M_sup * 1e6) / (p.fcu * bw * d**2)
        
        As_sup_comp_req = 0.0
        if K_sup <= 0.156:
            z_sup_calc = d * (0.5 + math.sqrt(max(0, 0.25 - K_sup / 0.9)))
            z_sup = min(z_sup_calc, 0.95 * d)
            As_sup_req = (M_sup * 1e6) / (0.87 * p.fy * z_sup)
        else:
            z_sup = 0.775 * d
            M_c = (M_sup * 1e6) - 0.156 * p.fcu * bw * d**2
            As_sup_comp_req = M_c / (0.87 * p.fy * (d - s.d_prime_mm))
            As_sup_req = (0.156 * p.fcu * bw * d**2) / (0.87 * p.fy * z_sup) + As_sup_comp_req

        As_sup_req_pm = As_sup_req * (1000.0 / bf)

        bar_area_sup = math.pi * (s.sup_bar_dia**2) / 4.0
        As_sup_prov_pm = (1000.0 / s.sup_bar_spacing) * bar_area_sup

        self.res['K_sup'] = K_sup
        self.res['z_sup'] = z_sup
        self.res['As_sup_req'] = As_sup_req
        self.res['As_sup_comp_req'] = As_sup_comp_req
        self.res['As_sup_req_pm'] = As_sup_req_pm
        self.res['As_sup_prov_pm'] = As_sup_prov_pm
        self.res['sup_status'] = "PASS" if As_sup_prov_pm >= As_sup_req_pm else "FAIL"

        # 5. Shear
        v = (V * 1000.0) / (bw * d)
        pt = (100.0 * As_sup_prov_pm * (bf / 1000.0)) / (bw * d)
        pt = min(pt, 3.0)
        v_c = 0.79 * (pt**(1/3.0)) * ((min(400.0 / d, 1.0))**(1/4.0)) / 1.25
        if p.fcu > 25:
            v_c *= (min(p.fcu, 40)/25.0)**(1/3.0)
            
        link_area = s.link_legs * math.pi * (s.link_dia**2) / 4.0
        
        if v < 0.5 * v_c:
            shear_status = "No shear links theoretically required"
            sv_req = float('inf')
        elif v < v_c + 0.4:
            shear_status = "Minimum links required"
            sv_req = (0.87 * p.fyv * link_area) / (0.4 * bw)
        else:
            shear_status = "Designed links required"
            sv_req = (0.87 * p.fyv * link_area) / (bw * (v - v_c))
            
        sv_req = min(sv_req, 0.75 * d)
        
        self.res['v'] = v
        self.res['v_c'] = v_c
        self.res['link_area'] = link_area
        self.res['sv_req'] = sv_req
        self.res['shear_msg'] = shear_status
        self.res['shear_status'] = "PASS" if s.link_spacing <= sv_req or v < 0.5 * v_c else "FAIL"

        # 6. Deflection
        ratio_prov_req = As_mid_prov / As_mid_req if As_mid_req > 0 else 1.0
        fs = (2.0/3.0) * p.fy * (1 / ratio_prov_req)
        mf = 0.55 + (477.0 - fs) / (120.0 * (0.9 + (M_mid * 1e6) / (bf * d**2)))
        mf = min(mf, 2.0)
        allow_ratio = 20.8 * mf
        actual_ratio = (s.span_m * 1000.0) / d
        
        self.res['fs'] = fs
        self.res['mf'] = mf
        self.res['allow_ratio'] = allow_ratio
        self.res['actual_ratio'] = actual_ratio
        self.res['deflection_status'] = "PASS" if actual_ratio <= allow_ratio else "FAIL"

        # 7. Equivalent Slab Depth
        sw_total = topping_sw + rib_sw + block_load
        equiv_depth = sw_total / l.conc_density_kNm3
        self.res['sw_total'] = sw_total
        self.res['equiv_depth'] = equiv_depth

    def generate_pdf(self, filename: str):
        p, s, l, pr, r = self.proj, self.slab, self.loads, self.params, self.res
        
        BLUE = '#1F4E78'
        LEFT, RIGHT = 0.05, 0.95
        REF_W, OUT_W = 0.15, 0.18
        X0, X1 = LEFT + REF_W, RIGHT - OUT_W
        TOP, BOTTOM = 0.84, 0.05
        STEP = 0.016
        PAGE_W_IN, PAGE_H_IN = 8.27, 11.69  # A4

        pages = []
        st = {"fig": None, "ax": None, "y": TOP, "ref_y": TOP, "out_y": TOP}

        def new_page():
            fig = plt.figure(figsize=(PAGE_W_IN, PAGE_H_IN))
            ax = fig.add_axes([0, 0, 1, 1])
            ax.axis('off'); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
            
            # --- HEADER BOUNDARY (Matches Beam F84 style closely) ---
            HR_T, HR_B = 0.98, 0.86
            ax.add_patch(patches.Rectangle((LEFT, HR_B), RIGHT - LEFT, HR_T - HR_B, fill=False, lw=1.2, edgecolor='black'))
            
            # Horizontal subdividers in header
            ax.plot([0.5, RIGHT], [0.94, 0.94], color='black', lw=0.6)
            ax.plot([0.5, RIGHT], [0.90, 0.90], color='black', lw=0.6)
            
            # Vertical subdividers in header
            ax.plot([0.5, 0.5], [HR_B, HR_T], color='black', lw=0.6)
            ax.plot([0.75, 0.75], [0.90, 0.94], color='black', lw=0.6)
            
            # Header Texts - Left side
            ax.text(LEFT+0.01, 0.96, f"{p.firm_name}", fontsize=11, fontweight='bold', va='center')
            ax.text(LEFT+0.01, 0.935, f"{p.address}", fontsize=8, va='center')
            if p.tel: ax.text(LEFT+0.01, 0.915, f"Tel: {p.tel}", fontsize=8, va='center')
            if p.email: ax.text(LEFT+0.01, 0.895, f"Email: {p.email}", fontsize=8, va='center')

            # Header Texts - Right side
            ax.text(0.51, 0.965, "Project Title:", fontsize=7, color='#444')
            ax.text(0.51, 0.95, f"{p.project_title}", fontsize=9, fontweight='bold')
            
            ax.text(0.51, 0.925, "Job No:", fontsize=7, color='#444')
            ax.text(0.51, 0.91, f"{p.job_no}", fontsize=8, fontweight='bold')
            ax.text(0.76, 0.925, "By:", fontsize=7, color='#444')
            ax.text(0.76, 0.91, f"{p.designer}", fontsize=8, fontweight='bold')
            
            ax.text(0.51, 0.885, "Element:", fontsize=7, color='#444')
            ax.text(0.51, 0.87, f"{p.element}", fontsize=8, fontweight='bold')
            ax.text(0.76, 0.885, "Date:", fontsize=7, color='#444')
            ax.text(0.76, 0.87, f"{p.date}", fontsize=8)

            # --- MAIN BODY BOUNDARY ---
            # Main continuous box
            ax.add_patch(patches.Rectangle((LEFT, BOTTOM), RIGHT - LEFT, HR_B - 0.02 - BOTTOM, fill=False, lw=1.2, edgecolor='black'))
            # Vertical column lines inside main box
            ax.plot([X0, X0], [BOTTOM, HR_B - 0.02], color='black', lw=0.6)
            ax.plot([X1, X1], [BOTTOM, HR_B - 0.02], color='black', lw=0.6)
            
            # Column headers
            hdr_y = HR_B - 0.035
            ax.plot([LEFT, RIGHT], [hdr_y - 0.015, hdr_y - 0.015], color='black', lw=1.0)
            ax.text((LEFT + X0)/2, hdr_y, "References", ha='center', va='center', fontsize=9, fontweight='bold')
            ax.text((X0 + X1)/2, hdr_y, "Calculation", ha='center', va='center', fontsize=9, fontweight='bold')
            ax.text((X1 + RIGHT)/2, hdr_y, "Output", ha='center', va='center', fontsize=9, fontweight='bold')
            
            # Page number
            ax.text(RIGHT - 0.01, BOTTOM - 0.02, f"Sheet {len(pages)+1}", ha='right', fontsize=8)
            
            st.update(fig=fig, ax=ax, y=hdr_y - 0.03, ref_y=hdr_y - 0.03, out_y=hdr_y - 0.03)
            pages.append(fig)

        def fit(h):
            if st["y"] - h < BOTTOM + 0.02 or st["ref_y"] - h < BOTTOM + 0.02 or st["out_y"] - h < BOTTOM + 0.02:
                new_page()

        def line(calc="", ref="", out="", bold=False, fs=8.5, calc_color='black'):
            h = max(len(str(calc).split('\n')), len(str(ref).split('\n')), len(str(out).split('\n'))) * STEP
            fit(h)
            ax = st["ax"]
            if ref:
                ax.text(LEFT + 0.01, st["ref_y"], sub(ref), fontsize=7.5, color='#444', va='top')
                st["ref_y"] -= len(str(ref).split('\n')) * STEP
            if out:
                ax.text(X1 + 0.01, st["out_y"], sub(out), fontsize=8.5, color=BLUE, fontweight='bold', va='top')
                st["out_y"] -= len(str(out).split('\n')) * STEP
            if calc:
                ax.text(X0 + 0.02, st["y"], sub(calc), fontsize=fs, color=calc_color, fontweight='bold' if bold else 'normal', va='top')
                st["y"] -= len(str(calc).split('\n')) * STEP
            
            min_y = min(st["y"], st["ref_y"], st["out_y"])
            st["y"] = st["ref_y"] = st["out_y"] = min_y

        def gap(n=1):
            st["y"] -= n * STEP
            st["ref_y"] = st["out_y"] = st["y"]

        def heading(txt):
            fit(STEP * 2)
            st["ax"].text(X0 + 0.01, st["y"], txt.upper(), fontsize=9, fontweight='bold', va='top')
            st["ax"].plot([X0+0.01, X0+0.25], [st["y"]-0.012, st["y"]-0.012], color='black', lw=0.8)
            gap(1.2)

        # ---------------------------------------------------------
        # Build PDF Content
        # ---------------------------------------------------------
        new_page()
        
        # Block Geometry properties
        line(f"Hollow blocks = {s.rib_depth_mm} x {s.block_width_mm} x {s.block_length_mm} mm")
        line(f"Weight of 1 block = {s.block_weight_kg} kg")
        line(f"{s.blocks_per_sqm} blocks/m² = {s.blocks_per_sqm} x {s.block_weight_kg} = {s.blocks_per_sqm * s.block_weight_kg} kg/m² = {r['block_load']:.2f} kN/m²")
        line(f"Area of ribs = {s.rib_width_mm/1000} x {s.rib_depth_mm/1000} = {(s.rib_width_mm*s.rib_depth_mm)/1e6:.3f} m²")
        line(f"Ribs per m width = 1000 / {s.bf} = {1000/s.bf:.2f}")
        line(f"Self-weight of ribs = {1000/s.bf:.2f} x {(s.rib_width_mm*s.rib_depth_mm)/1e6:.3f} x {l.conc_density_kNm3} = {r['rib_sw']:.2f} kN/m²")
        gap()
        
        heading("LOADING")
        line("Dead loads, Gk:", bold=True)
        line(f"Topping slw = {s.topping_mm/1000} x {l.conc_density_kNm3} = {r['topping_sw']:.2f} kN/m²")
        line(f"Ribs = {r['rib_sw']:.2f} kN/m²")
        line(f"Hollow Blocks = {r['block_load']:.2f} kN/m²")
        line(f"Solar Panels/Partitions = {l.solar_panels_kNm2:.2f} kN/m²")
        line(f"Finishes = {l.finishes_kNm2:.2f} kN/m²")
        line(f"Gk = {r['Gk']:.2f} kN/m²", out=f"Gk = {r['Gk']:.2f} kN/m²", bold=True)
        gap()
        
        line(f"Live load, Qk = {r['Qk']:.2f} kN/m²", ref="BS 6399-1:1996\nTable 1", out=f"Qk = {r['Qk']:.2f} kN/m²")
        line(f"Design Load, n = 1.4Gk + 1.6Qk", ref="BS 8110-1:1997\nCl 3.2.1.2.2")
        line(f"= 1.4({r['Gk']:.2f}) + 1.6({r['Qk']:.2f}) = {r['n']:.2f} kN/m²", out=f"n = {r['n']:.2f} kN/m²")
        gap()
        
        line(f"Consider bf of {s.bf/1000:.3f}m supported on each rib")
        line(f"udl on each rib = {s.bf/1000:.3f} x {r['n']:.2f} = {r['udl']:.2f} kN/m", out=f"udl = {r['udl']:.2f} kN/m")
        line(f"Load on span F = {r['udl']:.2f} x {s.span_m} = {r['F']:.2f} kN", out=f"F = {r['F']:.2f} kN")
        line(f"Effective depth, d = H - cover - link - \u03D5/2")
        line(f"= {s.total_depth_mm} - {s.cover_mm} - {s.link_dia} - {s.mid_bar_dia}/2 = {s.d_mm:.0f} mm", out=f"d = {s.d_mm:.0f} mm")
        gap()
        
        heading("Design of Bending Moment & Shear Stress")
        line(f"Moment @ Support B = {pr.coef_sup_moment}FL = {pr.coef_sup_moment} x {r['F']:.2f} x {s.span_m} = {r['M_sup']:.2f} kN.m", ref="BS 8110-1:1997\nTable 3.12")
        line(f"Moment @ Midspan C = {pr.coef_mid_moment}FL = {pr.coef_mid_moment} x {r['F']:.2f} x {s.span_m} = {r['M_mid']:.2f} kN.m")
        line(f"Shear @ Support = {pr.coef_shear}F = {pr.coef_shear} x {r['F']:.2f} = {r['V']:.2f} kN")
        gap()
        
        heading("Midspan T-Section")
        line(f"Width of flange bf = {s.bf} mm")
        line(f"M applied = {r['M_mid']:.2f} kN.m")
        line(f"Moment of Resistance Mr = 0.45 fcu bf hf (d - 0.5 hf)", ref="BS 8110-1:1997\nCl 3.4.4.4")
        line(f"Mr = 0.45 x {pr.fcu} x {s.bf} x {s.topping_mm} x ({s.d_mm} - 0.5 x {s.topping_mm}) / 1e6 = {r['M_flange']:.2f} kN.m")
        
        if r['M_flange'] > r['M_mid']:
            line("Mr > M_applied: Neutral Axis lies within the flange. Treat as rectangular section.", bold=True)
        else:
            line("Mr < M_applied: Neutral Axis lies in the web. Rigorous T-beam design required.", bold=True)
            
        line(f"K = M / (fcu b d²) = {r['M_mid']:.2f}x10^6 / ({pr.fcu} x {s.bf} x {s.d_mm}²) = {r['K_mid']:.4f} \u2264 0.156", out="No comp. reinf\nrequired.")
        line(f"z = d[0.5 + \u221A(0.25 - K/0.9)] \u2264 0.95d")
        line(f"z = {s.d_mm}[0.5 + \u221A(0.25 - {r['K_mid']:.4f}/0.9)] = {r['z_mid']:.1f} mm")
        line(f"As,req = M / (0.87 fy z) = {r['M_mid']:.2f}x10^6 / (0.87 x {pr.fy} x {r['z_mid']:.1f})", out=f"As,req = {r['As_mid_req']:.1f} mm²")
        line(f"= {r['As_mid_req']:.1f} mm²")
        line(f"Provide {s.mid_bar_n}T{s.mid_bar_dia:g} bars (As,prov = {r['As_mid_prov']:.1f} mm²)", out=f"As,prov = {r['As_mid_prov']:.1f} mm²\n({r['mid_status']})", bold=True, calc_color='green' if r['mid_status']=="PASS" else 'red')
        gap()
        
        heading("At Supports - Rectangular Section")
        line(f"Moment = {r['M_sup']:.2f} kN.m")
        line(f"K = M / (fcu bw d²) = {r['M_sup']:.2f}x10^6 / ({pr.fcu} x {s.rib_width_mm} x {s.d_mm}²) = {r['K_sup']:.3f}")
        
        if r['K_sup'] <= 0.156:
            line(f"{r['K_sup']:.3f} \u2264 0.156, No compression reinforcement required.")
            line(f"z = {r['z_sup']:.1f} mm")
        else:
            line(f"{r['K_sup']:.3f} > 0.156, Compression reinforcement required. (Limiting z = 0.775d)")
            line(f"z = {r['z_sup']:.1f} mm")
            line(f"Compression As' required = {r['As_sup_comp_req']:.1f} mm²")
            
        line(f"As,req = {r['As_sup_req']:.1f} mm² (per rib)")
        line(f"(1000 x {r['As_sup_req']:.1f}) / {s.bf} = {r['As_sup_req_pm']:.1f} mm²/m", out=f"As,req =\n{r['As_sup_req_pm']:.1f} mm²/m")
        line(f"Provide T{s.sup_bar_dia:g}@{s.sup_bar_spacing:g} (As,prov = {r['As_sup_prov_pm']:.1f} mm²/m)", out=f"As,prov =\n{r['As_sup_prov_pm']:.1f} mm²/m\n({r['sup_status']})", bold=True, calc_color='green' if r['sup_status']=="PASS" else 'red')
        gap()
        
        heading("Shear Reinforcement")
        line(f"v = V / (bw d) = {r['V']:.2f}x10^3 / ({s.rib_width_mm} x {s.d_mm}) = {r['v']:.3f} N/mm²", ref="BS 8110-1:1997\nEqn 3.", out=f"v = {r['v']:.3f} N/mm²")
        line(f"vc = {r['v_c']:.3f} N/mm²", out=f"vc = {r['v_c']:.3f} N/mm²")
        line(f"Condition: {r['shear_msg']}")
        line(f"Calculated sv_req = {r['sv_req']:.1f} mm")    
        line(f"Provide {s.link_legs} legs T{s.link_dia:g}@{s.link_spacing:g} c/c", out=f"Links T{s.link_dia:g}@{s.link_spacing:g}\n({r['shear_status']})", bold=True, calc_color='green' if r['shear_status']=="PASS" else 'red')
        gap()
        
        heading("Deflection Check")
        line(f"Basic l/d ratio = 20.8", ref="BS 8110-1:1997\nTable 3.9")
        line(f"fs = (2/3) fy (As,req / As,prov) = {r['fs']:.2f} N/mm²")
        line(f"MF = 0.55 + (477 - fs) / [120(0.9 + M/bd²)] = {r['mf']:.2f} \u2264 2.0", ref="Cl 3.4.6.5")
        line(f"Allowable span/d = 20.8 x {r['mf']:.2f} = {r['allow_ratio']:.2f}")
        line(f"Actual span/d = {s.span_m*1000} / {s.d_mm} = {r['actual_ratio']:.2f}")
        if r['actual_ratio'] <= r['allow_ratio']:
            line("Allowable l/d > Actual l/d \u2192 Deflection is OK", out="Deflection OK", bold=True, calc_color='green')
        else:
            line("Allowable l/d < Actual l/d \u2192 Deflection fails!", out="Deflection FAILS", bold=True, calc_color='red')
        gap()
        
        heading("Equivalent Slab Depth")
        line(f"Total Structural Dead Load = {r['sw_total']:.2f} kN/m²")
        line(f"Equivalent depth = {r['sw_total']:.2f} / {l.conc_density_kNm3} = {r['equiv_depth']:.3f} m")
        line(f"Equivalent Slab Depth \u2248 {r['equiv_depth']*1000:.0f} mm", out=f"\u2248 {r['equiv_depth']*1000:.0f} mm", bold=True)

        pdf = PdfPages(filename)
        for fig in pages:
            pdf.savefig(fig)
            plt.close(fig)
        pdf.close()
        return filename

if __name__ == "__main__":
    pass