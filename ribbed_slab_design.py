"""
ribbed_slab_design.py
---------------------
Backend engine for continuous ribbed slab design and PDF report generation.
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
    job_no: str = "IES-009-2024-ERICK & JACKLINE TATU CITY"
    designer: str = "RIDOK"
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
    bar_dia_mm: float = 12.0
    support_bar_dia_mm: float = 12.0
    link_dia_mm: float = 8.0

    @property
    def bf(self) -> float:
        return self.rib_width_mm + self.block_width_mm

    @property
    def total_depth_mm(self) -> float:
        return self.rib_depth_mm + self.topping_mm

    @property
    def d_mm(self) -> float:
        return self.total_depth_mm - self.cover_mm - (self.bar_dia_mm / 2.0)

@dataclass
class Loads:
    solar_panels_kNm2: float = 0.12
    finishes_kNm2: float = 2.50
    live_load_kNm2: float = 5.0
    conc_density_kNm3: float = 24.0

@dataclass
class DesignParams:
    fcu: float = 25.0
    fy: float = 460.0
    fyv: float = 460.0
    coef_mid_moment: float = 0.063
    coef_sup_moment: float = 0.086
    coef_shear: float = 0.6
    link_legs: int = 2

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
        
        bar_area_mid = math.pi * (s.bar_dia_mm**2) / 4.0
        num_bars_mid = max(1, math.ceil(As_mid_req / bar_area_mid))
        As_mid_prov = num_bars_mid * bar_area_mid
        
        self.res['K_mid'] = K_mid
        self.res['z_mid'] = z_mid
        self.res['As_mid_req'] = As_mid_req
        self.res['num_bars_mid'] = num_bars_mid
        self.res['As_mid_prov'] = As_mid_prov

        # 4. Support Design (Rectangular)
        bw = s.rib_width_mm
        K_sup = (M_sup * 1e6) / (p.fcu * bw * d**2)
        z_sup_calc = d * (0.5 + math.sqrt(max(0, 0.25 - K_sup / 0.9)))
        z_sup = min(z_sup_calc, 0.95 * d)
        if K_sup > 0.156:
            z_sup = 0.775 * d
        As_sup_req = (M_sup * 1e6) / (0.87 * p.fy * z_sup)
        As_sup_req_pm = As_sup_req * (1000.0 / bf)

        bar_area_sup = math.pi * (s.support_bar_dia_mm**2) / 4.0
        spacing_sup = math.floor((1000.0 * bar_area_sup) / As_sup_req_pm / 25.0) * 25.0
        spacing_sup = min(spacing_sup, 300.0)
        As_sup_prov_pm = (1000.0 / spacing_sup) * bar_area_sup

        self.res['K_sup'] = K_sup
        self.res['z_sup'] = z_sup
        self.res['As_sup_req'] = As_sup_req
        self.res['As_sup_req_pm'] = As_sup_req_pm
        self.res['spacing_sup'] = spacing_sup
        self.res['As_sup_prov_pm'] = As_sup_prov_pm

        # 5. Shear
        v = (V * 1000.0) / (bw * d)
        pt = (100.0 * As_sup_prov_pm * (bf / 1000.0)) / (bw * d)
        pt = min(pt, 3.0)
        v_c = 0.79 * (pt**(1/3.0)) * ((min(400.0 / d, 1.0))**(1/4.0)) / 1.25
        # adjusting for concrete grade > 25
        if p.fcu > 25:
            v_c *= (min(p.fcu, 40)/25.0)**(1/3.0)
            
        link_area = p.link_legs * math.pi * (s.link_dia_mm**2) / 4.0
        if v > v_c + 0.4:
            sv_req = (0.87 * p.fyv * link_area) / (bw * (v - v_c))
        else:
            sv_req = (0.87 * p.fyv * link_area) / (0.4 * bw)
            
        sv_prov = math.floor(sv_req / 25.0) * 25.0
        sv_prov = min(sv_prov, 600.0)
        
        self.res['v'] = v
        self.res['v_c'] = v_c
        self.res['link_area'] = link_area
        self.res['sv_prov'] = sv_prov

        # 6. Deflection
        fs = (2.0/3.0) * p.fy * (As_mid_req / As_mid_prov)
        mf = 0.55 + (477.0 - fs) / (120.0 * (0.9 + (M_mid * 1e6) / (bf * d**2)))
        mf = min(mf, 2.0)
        allow_ratio = 20.8 * mf
        actual_ratio = (s.span_m * 1000.0) / d
        
        self.res['fs'] = fs
        self.res['mf'] = mf
        self.res['allow_ratio'] = allow_ratio
        self.res['actual_ratio'] = actual_ratio

        # 7. Equivalent Slab Depth
        sw_total = topping_sw + rib_sw + block_load
        equiv_depth = sw_total / l.conc_density_kNm3
        self.res['sw_total'] = sw_total
        self.res['equiv_depth'] = equiv_depth

    def generate_pdf(self, filename: str):
        p, s, l, pr, r = self.proj, self.slab, self.loads, self.params, self.res
        
        BLUE = '#1F4E78'
        LEFT, RIGHT = 0.05, 0.95
        REF_W, OUT_W = 0.13, 0.16
        X0, X1 = LEFT + REF_W, RIGHT - OUT_W
        TOP, BOTTOM = 0.88, 0.05
        STEP = 0.016
        PAGE_W_IN, PAGE_H_IN = 8.27, 11.69  # A4

        pages = []
        st = {"fig": None, "ax": None, "y": TOP, "ref_y": TOP, "out_y": TOP}

        def new_page():
            fig = plt.figure(figsize=(PAGE_W_IN, PAGE_H_IN))
            ax = fig.add_axes([0, 0, 1, 1])
            ax.axis('off'); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
            
            # Title block
            ROWS = [0.98, 0.95, 0.925, 0.90]
            ax.add_patch(patches.Rectangle((LEFT, ROWS[-1]), RIGHT - LEFT, ROWS[0] - ROWS[-1], fill=False, lw=1))
            
            ax.text(LEFT+0.01, ROWS[0]-0.012, f"JOB NO: {p.job_no}", fontsize=9, fontweight='bold')
            ax.text(LEFT+0.01, ROWS[1]-0.012, f"DESIGNER: {p.designer}", fontsize=9)
            ax.text(LEFT+0.5, ROWS[1]-0.012, f"DATE: {p.date}", fontsize=9)
            ax.text(LEFT+0.01, ROWS[2]-0.012, f"ELEMENT: {p.element}", fontsize=9, fontweight='bold')
            ax.text(LEFT+0.5, ROWS[2]-0.012, f"{p.panel_ref}", fontsize=9, fontweight='bold', color=BLUE)
            
            for y in ROWS[1:-1]:
                ax.plot([LEFT, RIGHT], [y, y], 'k-', lw=0.5)
                
            # Column headers
            hdr_y = ROWS[-1] - 0.02
            ax.plot([LEFT, RIGHT], [hdr_y, hdr_y], 'k-', lw=1)
            ax.plot([LEFT, RIGHT], [hdr_y - 0.02, hdr_y - 0.02], 'k-', lw=1)
            ax.text((LEFT + X0)/2, hdr_y - 0.01, "Design Ref.", ha='center', va='center', fontsize=8, fontweight='bold')
            ax.text((X0 + X1)/2, hdr_y - 0.01, "Calculations", ha='center', va='center', fontsize=8, fontweight='bold')
            ax.text((X1 + RIGHT)/2, hdr_y - 0.01, "Output", ha='center', va='center', fontsize=8, fontweight='bold')
            
            # Vertical lines
            ax.plot([LEFT, LEFT], [BOTTOM, ROWS[0]], 'k-', lw=1)
            ax.plot([RIGHT, RIGHT], [BOTTOM, ROWS[0]], 'k-', lw=1)
            ax.plot([X0, X0], [BOTTOM, hdr_y], 'k-', lw=0.5)
            ax.plot([X1, X1], [BOTTOM, hdr_y], 'k-', lw=0.5)
            ax.plot([LEFT, RIGHT], [BOTTOM, BOTTOM], 'k-', lw=1)
            
            st.update(fig=fig, ax=ax, y=hdr_y - 0.03, ref_y=hdr_y - 0.03, out_y=hdr_y - 0.03)
            pages.append(fig)

        def fit(h):
            if st["y"] - h < BOTTOM + 0.02 or st["ref_y"] - h < BOTTOM + 0.02 or st["out_y"] - h < BOTTOM + 0.02:
                new_page()

        def line(calc="", ref="", out="", bold=False, fs=8.5):
            h = max(len(str(calc).split('\n')), len(str(ref).split('\n')), len(str(out).split('\n'))) * STEP
            fit(h)
            ax = st["ax"]
            if ref:
                ax.text(LEFT + 0.01, st["ref_y"], sub(ref), fontsize=7, color='#555', va='top')
                st["ref_y"] -= len(str(ref).split('\n')) * STEP
            if out:
                ax.text(X1 + 0.01, st["out_y"], sub(out), fontsize=8, color=BLUE, fontweight='bold', va='top')
                st["out_y"] -= len(str(out).split('\n')) * STEP
            if calc:
                ax.text(X0 + 0.02, st["y"], sub(calc), fontsize=fs, fontweight='bold' if bold else 'normal', va='top')
                st["y"] -= len(str(calc).split('\n')) * STEP
            
            min_y = min(st["y"], st["ref_y"], st["out_y"])
            st["y"] = st["ref_y"] = st["out_y"] = min_y

        def gap(n=1):
            st["y"] -= n * STEP
            st["ref_y"] = st["out_y"] = st["y"]

        def heading(txt):
            fit(STEP * 2)
            st["ax"].text(X0 + 0.01, st["y"], txt, fontsize=10, fontweight='bold', va='top', color=BLUE)
            st["ax"].plot([X0+0.01, X0+0.2], [st["y"]-0.015, st["y"]-0.015], color=BLUE, lw=1)
            gap(1.5)

        # Draw 2D Isometric Block
        def draw_block_sketch(ax_inset):
            ax_inset.axis('off')
            ax_inset.set_xlim(-0.2, 1.2); ax_inset.set_ylim(-0.2, 1.2)
            # Simple 3D box projection
            pts = [(0.1, 0.3), (0.7, 0.3), (0.7, 0.6), (0.1, 0.6)] # Front
            ax_inset.add_patch(patches.Polygon(pts, fill=False, lw=1.2, edgecolor=BLUE))
            pts_top = [(0.1, 0.6), (0.3, 0.8), (0.9, 0.8), (0.7, 0.6)] # Top
            ax_inset.add_patch(patches.Polygon(pts_top, fill=False, lw=1.2, edgecolor=BLUE))
            pts_side = [(0.7, 0.3), (0.9, 0.5), (0.9, 0.8), (0.7, 0.6)] # Side
            ax_inset.add_patch(patches.Polygon(pts_side, fill=False, lw=1.2, edgecolor=BLUE))
            
            # Dimensions
            ax_inset.plot([0.1, 0.7], [0.2, 0.2], 'k-', lw=0.8)
            ax_inset.text(0.4, 0.15, f"{s.block_width_mm:g}", ha='center', fontsize=8)
            
            ax_inset.plot([0.75, 0.95], [0.25, 0.45], 'k-', lw=0.8)
            ax_inset.text(0.95, 0.35, f"{s.block_length_mm:g}", ha='left', fontsize=8)
            
            ax_inset.plot([0.95, 0.95], [0.5, 0.8], 'k-', lw=0.8)
            ax_inset.text(1.0, 0.65, f"{s.rib_depth_mm:g}", ha='left', va='center', fontsize=8)

        def draw_t_section(ax_inset):
            ax_inset.axis('off')
            ax_inset.set_xlim(-0.2, 1.2); ax_inset.set_ylim(-0.2, 1.2)
            w_flange = 0.8
            h_flange = 0.3
            w_web = 0.25
            h_web = 0.5
            x_c = 0.5
            
            # Flange
            ax_inset.add_patch(patches.Rectangle((x_c - w_flange/2, 0.7), w_flange, h_flange, fill=False, lw=1.2, edgecolor=BLUE))
            # Web
            ax_inset.add_patch(patches.Rectangle((x_c - w_web/2, 0.2), w_web, h_web, fill=False, lw=1.2, edgecolor=BLUE))
            # Erase middle line
            ax_inset.plot([x_c - w_web/2 + 0.01, x_c + w_web/2 - 0.01], [0.7, 0.7], color='white', lw=2)
            
            # Reinforcement dots
            ax_inset.plot([x_c - 0.05, x_c + 0.05], [0.25, 0.25], 'ro', markersize=4)
            
            # NA line
            ax_inset.plot([0.1, 0.9], [0.85, 0.85], 'k--', lw=0.8)
            ax_inset.text(0.05, 0.85, 'N', ha='right', va='center', fontsize=8)
            ax_inset.text(0.95, 0.85, 'A', ha='left', va='center', fontsize=8)
            
            # Dims
            ax_inset.text(0.5, 1.05, f"bf = {s.bf:g} mm", ha='center', fontsize=8)
            ax_inset.text(0.5, 0.1, f"bw = {s.rib_width_mm:g}", ha='center', fontsize=8)
            ax_inset.text(-0.05, 0.85, f"{s.topping_mm:g}", va='center', rotation=90, fontsize=8)
            ax_inset.text(-0.05, 0.45, f"{s.rib_depth_mm:g}", va='center', rotation=90, fontsize=8)

        def draw_detailing(ax_inset, is_midspan=True):
            ax_inset.axis('off')
            ax_inset.set_xlim(-0.2, 1.2); ax_inset.set_ylim(-0.2, 1.2)
            x_c = 0.5
            w_f = 1.0
            h_f = 0.3
            w_w = 0.3
            h_w = 0.5
            
            ax_inset.add_patch(patches.Rectangle((x_c - w_f/2, 0.7), w_f, h_f, fill=False, lw=1, edgecolor='k'))
            ax_inset.add_patch(patches.Rectangle((x_c - w_w/2, 0.2), w_w, h_w, fill=False, lw=1, edgecolor='k'))
            ax_inset.plot([x_c - w_w/2 + 0.01, x_c + w_w/2 - 0.01], [0.7, 0.7], color='white', lw=2)
            
            # Links
            ax_inset.add_patch(patches.Rectangle((x_c - w_w/2 + 0.05, 0.25), w_w - 0.1, h_w + h_f - 0.1, fill=False, lw=1, edgecolor=BLUE))
            
            # Bottom bars
            ax_inset.plot([x_c - 0.08, x_c, x_c + 0.08], [0.28, 0.28, 0.28], 'bo', markersize=3)
            # Mesh
            ax_inset.plot([0.1, 0.9], [0.9, 0.9], 'b--', lw=1)
            
            if is_midspan:
                ax_inset.text(0.5, 0.1, f"{r['num_bars_mid']}T{s.bar_dia_mm:g}", ha='center', fontsize=8, color=BLUE)
                ax_inset.text(0.9, 0.5, f"T{s.link_dia_mm:g}@{r['sv_prov']:g}", ha='left', fontsize=8, color=BLUE)
                ax_inset.text(0.5, 1.05, "SECTION AT MIDSPAN", ha='center', fontsize=9, fontweight='bold')
            else:
                # Top bars
                ax_inset.plot([0.2, 0.4, 0.6, 0.8], [0.85, 0.85, 0.85, 0.85], 'bo', markersize=3)
                ax_inset.text(0.5, 0.1, f"3T{s.bar_dia_mm:g}", ha='center', fontsize=8, color=BLUE)
                ax_inset.text(0.9, 0.5, f"T{s.link_dia_mm:g}@{r['sv_prov']:g}", ha='left', fontsize=8, color=BLUE)
                ax_inset.text(0.5, 1.05, "SECTION AT SUPPORT", ha='center', fontsize=9, fontweight='bold')
                ax_inset.text(0.5, 0.75, f"T{s.support_bar_dia_mm:g}@{r['spacing_sup']:g}", ha='center', fontsize=8, color=BLUE)

        # ---------------------------------------------------------
        # Build PDF Content
        # ---------------------------------------------------------
        new_page()
        
        # Geometry Sketches
        sk_h = 0.2
        fit(sk_h + 0.05)
        ax1 = st["ax"].inset_axes([X0, st["y"]-sk_h, 0.3, sk_h])
        draw_block_sketch(ax1)
        ax2 = st["ax"].inset_axes([X0+0.35, st["y"]-sk_h, 0.35, sk_h])
        draw_t_section(ax2)
        st["y"] -= sk_h + 0.02
        st["ref_y"] = st["out_y"] = st["y"]
        
        line(f"Hollow blocks = {s.block_depth_mm if hasattr(s, 'block_depth_mm') else s.rib_depth_mm}x{s.block_width_mm}x{s.block_length_mm}")
        line(f"Weight of 1 block = {s.block_weight_kg} kgs")
        line(f"{s.blocks_per_sqm} blocks/m² = {s.blocks_per_sqm} x {s.block_weight_kg} = {s.blocks_per_sqm * s.block_weight_kg} kg/m² = {r['block_load']:.2f} kN/m²")
        line(f"Area of ribs = {s.rib_width_mm/1000} x {s.rib_depth_mm/1000} = {(s.rib_width_mm*s.rib_depth_mm)/1e6:.3f} m²")
        line(f"{1000/s.bf:.2f} ribs/m = {(1000/s.bf)*(s.rib_width_mm*s.rib_depth_mm)/1e6:.3f} m²")
        line(f"slw of ribs = {(1000/s.bf)*(s.rib_width_mm*s.rib_depth_mm)/1e6:.3f} x {l.conc_density_kNm3} = {r['rib_sw']:.2f} kN/m²")
        gap()
        
        heading("LOADING")
        line("Dead loads:", bold=True)
        line(f"Topping slweight = {s.topping_mm/1000} x {l.conc_density_kNm3} = {r['topping_sw']:.2f} kN/m²")
        line(f"Ribs = {r['rib_sw']:.2f} kN/m²")
        line(f"Hollow Blocks = {r['block_load']:.2f} kN/m²")
        line(f"Solar Panels / Partitions = {l.solar_panels_kNm2:.2f} kN/m²")
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
        line(f"Effective depth, d = H - cover - \u03D5/2")
        line(f"= {s.total_depth_mm} - {s.cover_mm} - {s.bar_dia_mm}/2 = {s.d_mm:.0f} mm", out=f"d = {s.d_mm:.0f} mm")
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
        line(f"Provide {r['num_bars_mid']}T{s.bar_dia_mm:g} bars (As,prov = {r['As_mid_prov']:.1f} mm²)", out=f"As,prov = {r['As_mid_prov']:.1f} mm²", bold=True)
        gap()
        
        heading("At Supports - Rectangular Section")
        line(f"Moment = {r['M_sup']:.2f} kN.m")
        line(f"K = M / (fcu bw d²) = {r['M_sup']:.2f}x10^6 / ({pr.fcu} x {s.rib_width_mm} x {s.d_mm}²) = {r['K_sup']:.3f}")
        
        if r['K_sup'] <= 0.156:
            line(f"{r['K_sup']:.3f} \u2264 0.156, No compression reinforcement required.")
        else:
            line(f"{r['K_sup']:.3f} > 0.156, Compression reinforcement required. (Limiting z = 0.775d)")
            
        line(f"z = {r['z_sup']:.1f} mm")
        line(f"As,req = {r['M_sup']:.2f}x10^6 / (0.87 x {pr.fy} x {r['z_sup']:.1f}) = {r['As_sup_req']:.1f} mm²")
        line(f"{r['As_sup_req']:.1f} mm² \u2192 {s.bf} mm")
        line(f"? \u2192 1000 mm")
        line(f"(1000 x {r['As_sup_req']:.1f}) / {s.bf} = {r['As_sup_req_pm']:.1f} mm²/m", out=f"As,req =\n{r['As_sup_req_pm']:.1f} mm²/m")
        line(f"Provide T{s.support_bar_dia_mm:g}@{r['spacing_sup']:g} (As,prov = {r['As_sup_prov_pm']:.1f} mm²/m)", out=f"As,prov =\n{r['As_sup_prov_pm']:.1f} mm²/m", bold=True)
        gap()
        
        heading("Shear Reinforcement")
        line(f"v = V / (bw d) = {r['V']:.2f}x10^3 / ({s.rib_width_mm} x {s.d_mm}) = {r['v']:.3f} N/mm²", ref="BS 8110-1:1997\nEqn 3.", out=f"v = {r['v']:.3f} N/mm²")
        line(f"vc = {r['v_c']:.3f} N/mm²", out=f"vc = {r['v_c']:.3f} N/mm²")
        if r['v'] < r['v_c'] + 0.4:
            line(f"0.5vc < v < vc + 0.4 \u2192 Minimal links required.")
        else:
            line(f"v > vc + 0.4 \u2192 Designed shear links required.")
            
        line(f"Provide {pr.link_legs} legs T{s.link_dia_mm:g} (Asv = {r['link_area']:.1f} mm²)")
        line(f"sv = (Asv(0.87 fyv)) / (0.4 bw) = ({r['link_area']:.1f} x 0.87 x {pr.fyv}) / (0.4 x {s.rib_width_mm})")
        line(f"Provide links T{s.link_dia_mm:g}@{r['sv_prov']:g} c/c", out=f"Links T{s.link_dia_mm:g}@{r['sv_prov']:g}", bold=True)
        gap()
        
        heading("Deflection Check")
        line(f"Basic l/d ratio = 20.8", ref="BS 8110-1:1997\nTable 3.9")
        line(f"fs = (2/3) fy (As,req / As,prov) = 2/3 x {pr.fy} x ({r['As_mid_req']:.1f} / {r['As_mid_prov']:.1f}) = {r['fs']:.2f} N/mm²")
        line(f"MF = 0.55 + (477 - fs) / [120(0.9 + M/bd²)] = {r['mf']:.2f} \u2264 2.0", ref="Cl 3.4.6.5")
        line(f"Allowable span/d = 20.8 x {r['mf']:.2f} = {r['allow_ratio']:.2f}")
        line(f"Actual span/d = {s.span_m*1000} / {s.d_mm} = {r['actual_ratio']:.2f}")
        if r['actual_ratio'] <= r['allow_ratio']:
            line("Allowable l/d > Actual l/d \u2192 Deflection is OK", out="Deflection OK", bold=True)
        else:
            line("Allowable l/d < Actual l/d \u2192 Deflection fails!", out="Deflection FAILS", bold=True)
        gap()
        
        heading("Construction Details")
        sk_h2 = 0.25
        fit(sk_h2)
        ax3 = st["ax"].inset_axes([X0, st["y"]-sk_h2, 0.4, sk_h2])
        draw_detailing(ax3, is_midspan=True)
        ax4 = st["ax"].inset_axes([X0+0.42, st["y"]-sk_h2, 0.4, sk_h2])
        draw_detailing(ax4, is_midspan=False)
        st["y"] -= sk_h2 + 0.02
        st["ref_y"] = st["out_y"] = st["y"]
        
        heading("Equivalent Slab Depth")
        line(f"Topping slw = {r['topping_sw']:.2f} kN/m²")
        line(f"Ribs = {r['rib_sw']:.2f} kN/m²")
        line(f"Hollow blocks = {r['block_load']:.2f} kN/m²")
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
    # Test generation
    proj = ProjectInfo()
    slab = RibbedSlab()
    loads = Loads()
    params = DesignParams()
    sys = RibbedSlabSystem(proj, slab, loads, params)
    sys.compute()
    sys.generate_pdf("test_report.pdf")