"""Render manuscript result tables directly from audited, regenerated JSON."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'manuscript'
NAMES=['fresh_mat','progressive_saturation','increased_leak','displaced_section','delayed_chemistry','undersized_mat']
S={s['scenario']:s for s in json.loads((OUT/'data/scenario_summary.json').read_text())}
P={p['policy']:p for p in json.loads((OUT/'data/policy_summary.json').read_text())}
A=json.loads((OUT/'verification/scenario_audit.json').read_text())
LETTERS=dict(zip(NAMES,'ABCDEF'))

def f(value): return f'{value:.4g}'
def pct(value): return f'{100*value:.2f}'
def row(values): return ' & '.join(map(str,values))+r' \\'+'\n'
def table(caption,label,spec,headers,rows):
    return (r'\begin{table}[htbp]\centering\small'+'\n'+
        '\\caption{'+caption+'}\\label{'+label+'}\n'+
        '\\begin{tabular}{'+spec+'}\\toprule\n'+row(headers)+r'\midrule'+'\n'+
        ''.join(row(r) for r in rows)+r'\bottomrule\end{tabular}\end{table}'+'\n\n')

b=S['progressive_saturation']; bm=b['final']; pb=P['none']; pc=P['fixed']; pe=P['evidence_informed']
abstract=r'''A thin modular reactive mat is investigated as a means of reducing contaminant flux from a contaminated sediment source. The software combines one-dimensional reactive transport in a keratin core, geotextile resistance, independent tile-condition variables, two-dimensional coastal transport, synthetic observations, interval estimates and maintenance recommendations. This report documents all operating assumptions, the supplied keratin literature, six regenerated scenarios, three servicing policies and independent numerical checks.

'''
abstract+=f"In the six-year baseline, whole-hotspot attenuation is {pct(bm['attenuation']['Pb'])}\\% for Pb, {pct(bm['attenuation']['Hg'])}\\% for Hg and {pct(bm['attenuation']['Cu'])}\\% for Cu. The corresponding sorbed fractions of nominal capacity are {pct(bm['saturation_fraction']['Pb'])}\\%, {pct(bm['saturation_fraction']['Hg'])}\\% and {pct(bm['saturation_fraction']['Cu'])}\\%. Physical resistance, chemical storage and effective area therefore require separate interpretation. Six-year cumulative whole-hotspot Pb emission is {f(pb['hotspot_into_water_kg']['Pb'])}~kg without a mat, {f(pc['hotspot_into_water_kg']['Pb'])}~kg with calendar servicing and {f(pe['hotspot_into_water_kg']['Pb'])}~kg with evidence-informed servicing. These are synthetic source comparisons, not measured remediation yields.\n\n"
abstract+=r'''The plot audit identified coordinate and area-weighting errors, off-by-one integration, out-of-range snapshot labels, an inconsistent barrier reference, and observation-clock and attribution defects. The corrected implementation was tested and all affected scenarios, figures and manuscript values regenerated. Remaining abrupt changes correspond to prescribed interventions, constitutive capacity locking or phase-dependent coastal statistics; numerical sensitivity is reported explicitly. The column and plume budgets close individually, but the area-mixed long-term source is not a fully coupled sediment--mat--water inventory.

The three supplied articles contain useful laboratory data but do not validate the finished mat in seawater. The default capacities of 1, 2.5 and 3~mg\,g$^{-1}$ for Pb, Hg and Cu remain operating assumptions. Laboratory mercury uptake by modified human hair and high batch removal by a keratin composite are documented with their different materials and experimental conditions. The resulting demonstrator supports hypothesis testing and experimental planning; field efficacy, ecological benefit and a reliable economic servicing advantage remain unestablished.
'''
(OUT/'abstract.tex').write_text(abstract,encoding='utf-8')

text=r'''\section{Regenerated demonstrator results}
\label{sec:results}
\subsection{Scenario design and performance measures}
All reported results are synthetic and were regenerated after the scientific revision. The shared seed is 20260908. A model year is 365.25 days. The baseline uses a 10~mm core with 4~kg\,m$^{-2}$ dry loading, nine tiles and complete geometric coverage of the hypothetical hotspot. Scenario F changes both geometry and transport and is therefore a compound stress case.

'''
changes=[('Fresh mat',1,'Baseline source and fresh medium.'),('Progressive loading',6,'Same physical configuration, longer exposure.'),('Increased source',6,'At year 2, porewater concentrations triple and seepage doubles.'),('Local damage',4,'Displacement at year 1.5; another tile loses 35\\% integrity at year 2.2.'),('Delayed chemistry',4,'75-day lab delay, probe dropout at years 1--1.25 and subsequent drift.'),('Undersized mat',4,'45\\% footprint, four tiles, 2~mm core, 10\\% edge bypass and tripled seepage.')]
text+=table('Configured six-scenario experiments.','tab:scenarios','llrp{.48\\linewidth}', ['ID','Scenario','Years','Change'],[[l,*r] for l,r in zip('ABCDEF',changes)])
text+=r'''The principal attenuation is the whole-hotspot quantity
\begin{equation}
A_{\mathrm{area},e}(t)=1-\frac{\int_{\Omega_h}J_{\mathrm{res},e}(x,y,t)\,\mathrm{d}A}{|\Omega_h|J_{\mathrm{bare},e}(t)}.
\end{equation}
It includes uncovered area, physical damage and bypass. The raw-column attenuation remains a separate diagnostic. The barrier-only comparator applies the same area weighting to the exact stationary discrete column with uptake disabled. Its difference from transient total attenuation is a diagnostic increment, not an isolated measurement of chemistry: transient porewater storage also contributes.

The endpoint concentration ratio is $R_{\max,e}=\max c_{\mathrm{with},e}/\max c_{\mathrm{bare},e}$. Its two maxima need not occur in the same cell. Neither source attenuation nor this ratio is a toxicity or compliance metric. Retained column mass comprises porewater and sorbed inventory; the active and retrieved parts are recorded separately.

\subsection{Final states and chemical contribution}
'''
rows=[]
for name in NAMES:
    q=S[name]['final'];rows.append([LETTERS[name]]+[pct(q['attenuation'][e]) for e in ['Pb','Hg','Cu']]+[pct(q['saturation_fraction'][e]) for e in ['Pb','Hg','Cu']])
text+=table('Final whole-hotspot attenuation and nominal sorbed-capacity use (percent). No statistical confidence interval is implied.','tab:all-metals','lrrrrrr',['Scenario',r'$A_{\rm Pb}$',r'$A_{\rm Hg}$',r'$A_{\rm Cu}$',r'$q_{\rm Pb}/q_{\max}$',r'$q_{\rm Hg}/q_{\max}$',r'$q_{\rm Cu}/q_{\max}$'],rows)
rows=[]
for name in NAMES:
    q=S[name];l=q['layer_ledger']['Pb'];rows.append([LETTERS[name],pct(q['final']['mean_coverage_fraction']),f(l['retained_in_mat_kg']),f(l['retained_in_retrieved_media_kg']),len(q['services']),q['observation_count']])
text+=table('Final footprint after physical condition, Pb column inventories and monitoring workload. Coverage excludes edge/fouling bypass; records include explicit missing results.','tab:scenario-results','lrrrrr',['Scenario','Coverage (\\%)','Active Pb (kg)','Retrieved Pb (kg)','Services','Records'],rows)
text+=r'''Increasing occupancy does not imply full exhaustion. A low accessible concentration or partition slope can hold the equilibrium load below the allocated capacity. Conversely, decreasing effective coverage can worsen hotspot emission even if surviving columns remain effective. The scenario-D time series now resolves the local physical events at their true times. Any accepted service changes active-media inventory and restores the serviced tile's condition; retrieved mass remains in its separate ledger.

\figpage{attenuation_all}{Whole-hotspot attenuation in all six regenerated scenarios. The common 0--101\% axis includes the complete response of the undersized design. Event-time discontinuities are retained rather than smoothed.}{fig:attenuation}
\figpage{saturation_all}{Sorbed inventory as a fraction of allocated nominal capacity. The profiles are deterministic simulations; low capacity use can coexist with little incremental uptake.}{fig:saturation}
\figpage{condition_all}{Mean fouling, physical integrity and actual hotspot coverage through time. Coverage and bypass are distinct: a nominally intact footprint can still lose effective performance as fouling diverts flow.}{fig:condition}
'''
text+=table('Six-year baseline decomposition using a common discrete transport operator and hotspot weighting. Differences are percentage points.','tab:barrier','lrrr',['Element','Total (\\%)','Barrier reference (\\%)','Difference (pp)'],[[e,pct(bm['attenuation'][e]),pct(bm['barrier_only_attenuation'][e]),f(100*(bm['attenuation'][e]-bm['barrier_only_attenuation'][e]))] for e in ['Pb','Hg','Cu']])
text+=r'''The baseline chemical increment is much smaller than the total attenuation. Cumulative storage and an endpoint increment answer different questions: mass retained during an earlier uptake transient can remain in the core even when the later flux approaches a resistance-controlled regime. Subtracting an approximate continuum barrier from a discrete transient result previously introduced small misleading differences, especially for Cu; the revised reference removes that operator mismatch.

\subsection{Spatial source and water transport}
All standard plume windows last 24 hours. The comparison below uses a three-year mat state when that age is within the scenario horizon, and the actual one-year endpoint for A. The source is held fixed during each window and the water starts clean. The final-age source plate in Appendix~\ref{app:spatial} additionally shows each scenario endpoint.
'''
rows=[]
for name in NAMES:
    q=S[name];window=next((w for w in q['windows'] if w['years']==3),q['windows'][-1]);m=window['elements']['Pb']
    rows.append([LETTERS[name],f(window['years']),f(m['source_bare_kg']),f(m['source_with_kg']),pct(m['area_attenuation']),f(m['peak_bare_ng_l']),f(m['peak_with_ng_l']),f(m['peak_ratio'])])
text+=table('Pb comparison at the stated mat age. Source is kg per 24-hour window; endpoint concentration maxima are ng/L.','tab:spatial-results','lrrrrrrr',['ID','Age (yr)','Bare kg','Mat kg','Reduction (\\%)','Bare peak','Mat peak',r'$R_{\max}$'],rows)
text+=r'''Unlike the previous geometry, the configured damaged tiles intersect the hotspot. Their source changes are therefore represented spatially. Scenario E changes observation timing rather than material coefficients; equality with a matched physical trajectory is expected whenever the policy produces the same servicing history. Scenario F leaves 55\% of the hotspot geometrically uncovered before bypass, so its column performance cannot be presented as whole-area performance.

\figpage{flux_30}{Regenerated residual Pb source maps at three years, or the actual one-year endpoint for A, with one shared source scale. Ages are shown in each panel.}{fig:fluxlate}
\figpage{spatial_B}{Baseline B at three years: matched with/without endpoint water concentrations, their cellwise ratio, and effective reactive cover.}{fig:spatialB}
\figpage{profiles_all}{Final Pb profiles through the core for every scenario. Colours show local sorbed load in mg per kg of core; panel scales are stated separately. Similar tiles are deterministic columns, not independent experimental replicates.}{fig:profiles}
\begin{figure}[htbp]\centering\includegraphics[width=\linewidth]{figures/surfaces.pdf}
\caption{Baseline Pb load through the core and the three-year endpoint plume shown as surfaces. Height denotes different labelled quantities; concentration is not seabed elevation.}\label{fig:surfaces}\end{figure}

\subsection{Three maintenance policies on a common emission basis}
The comparison uses identical physical assumptions, seed and scheduled campaigns. All policies integrate the same whole-hotspot residual source, including uncovered and bypassed area. Calendar service is triggered on the next decision boundary after its interval is reached. Evidence-informed service depends on arrived compatible measurements, their quality, attribution and uncertainty. The economic column below is the assumed service ledger; it excludes full lifecycle costs.
'''
rows=[]
for key,label in [('none','No mat'),('fixed','Calendar'),('evidence_informed','Evidence')]:
    q=P[key];rows.append([label]+[f(q['hotspot_into_water_kg'][e]) for e in ['Pb','Hg','Cu']]+[len(q['services']),f(q['service_cost_eur'])])
text+=table('Six-year cumulative whole-hotspot emission (kg), service events and assumed service expenditure.','tab:policies','lrrrrr',['Policy','Pb emitted','Hg emitted','Cu emitted','Services','Cost (EUR)'],rows)
text+=table('Pb inventory accounting in the policy comparison. Column inputs and outputs use the full tile-column control volume and are not added to the area-mixed emission above.','tab:policy-ledger','lrrrr',['Policy','Column input (kg)','Active (kg)','Retrieved (kg)','Column out (kg)'],[[label]+[f(P[key]['layer_ledger']['Pb'][v]) for v in ['released_from_sediment_kg','retained_in_mat_kg','retained_in_retrieved_media_kg','boundary_out_kg']] for key,label in [('none','No mat'),('fixed','Calendar'),('evidence_informed','Evidence')]])
text+=r'''\figpage{policy}{Policy comparison using whole-hotspot Pb emission for every policy. Active plus retrieved column inventory is shown separately. Costs are assumed service expenditure, not total project cost or profit.}{fig:policy}
Sparse Pb/Hg chemistry constrains evidence-informed decisions. Cu is simulated but not observed, and missing Cu no longer contributes evidence of performance loss. Unknown source and flux intervals are identified explicitly; no interval midpoint is a field measurement. Recommendations to sample or inspect do not adapt the future campaign schedule in this demonstrator. This comparison therefore does not establish the value of an optimised monitoring programme.

\subsection{Integration and conservation checks}
The regenerated audit compares final timeline flux with the integrated spatial source for every element and policy, validates every plume age against its simulation horizon, checks observation-ID uniqueness, and checks all individual column and water ledgers. Initial samples are unadvanced; the integration ends at the exact requested time, including a partial last step. The zero-sorption reference is tested against independent stationary face balances and grid refinement, and nonlinear transient profiles against an adaptive ODE reference.
'''
rows=[]
for a in A:
    if a['policy']=='evidence_informed':
        rows.append([LETTERS[a['scenario']],f(a['maximum_ledger_relative_imbalance']),f(max(a['final_timeline_source_relative_error'].values())),str(a['all_window_ages_valid']),str(a['unique_observation_ids'])])
text+=table('Audit of regenerated scenario outputs. Relative errors are dimensionless. Conservation and agreement are numerical checks, not material validation.','tab:scenario-audit','lrrll',['ID','Worst budget error','Source agreement error','Valid ages','Unique IDs'],rows)
text+=r'''\input{numerical_results}
'''
(OUT/'results.tex').write_text(text,encoding='utf-8')
print('Rendered abstract and current result tables from audited JSON.')
