"""Redraw regenerated scientific data; no simulation output is altered."""
from pathlib import Path
import json, base64, csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch

OUT=Path(__file__).resolve().parent
FIG=OUT/'figures'; FIG.mkdir(exist_ok=True)
P=json.loads((OUT/'data/gallery_plots.json').read_text())
S=json.loads((OUT/'data/scenario_summary.json').read_text())
Q=json.loads((OUT/'data/policy_summary.json').read_text())
plt.rcParams.update({'font.size':9,'axes.titlesize':10,'axes.labelsize':9,
 'legend.fontsize':8,'font.family':'DejaVu Sans','axes.spines.top':False,
 'axes.spines.right':False,'pdf.fonttype':42,'savefig.bbox':'tight'})
COL={'Pb':'#155e75','Hg':'#9b3f6f','Cu':'#c77c16'}
names=['Fresh mat','Progressive loading','Increased source','Local damage','Delayed chemistry','Undersized mat']
scenario_ids=['fresh_mat','progressive_saturation','increased_leak','displaced_section','delayed_chemistry','undersized_mat']
def arr(v):
    if isinstance(v,dict) and 'bdata' in v:
        a=np.frombuffer(base64.b64decode(v['bdata']),dtype=v['dtype'])
        return a.reshape(tuple(int(i) for i in v['shape'].split(','))) if 'shape' in v else a
    return np.asarray(v,dtype=float)
def save(fig,name):
    fig.savefig(FIG/(name+'.pdf'))
    fig.savefig(FIG/(name+'.png'),dpi=170)
    plt.close(fig)
def get(s,h): return next(p for p in P if p['section'].startswith('Scenario '+s+':') and p['heading']==h)
def late_age(s):
    ages=[float(p['heading'].split(' at ')[-1].split()[0]) for p in P if p['section'].startswith('Scenario '+s+':') and p['heading'].startswith('Seabed residual flux at ')]
    return f'{3.0 if 3.0 in ages else max(ages):.1f}'

def final_age(s):
    return f"{max(float(p['heading'].split(' at ')[-1].split()[0]) for p in P if p['section'].startswith('Scenario '+s+':') and p['heading'].startswith('Seabed residual flux at ')):.1f}"

def heat(ax,plot,vmax=None,cmap='magma',title=None):
    t=plot['data'][0]; x,y,z=arr(t['x']),arr(t['y']),arr(t['z'])
    im=ax.imshow(z,origin='lower',extent=[x[0]-5,x[-1]+5,y[0]-5,y[-1]+5],vmin=0,vmax=vmax,cmap=cmap,aspect='equal')
    ax.set(xlabel='East (m)',ylabel='North (m)',title=title)
    return im

# Repository concept diagram, generated directly as a vector figure.
fig,ax=plt.subplots(figsize=(9,4.6)); ax.set(xlim=(0,10),ylim=(0,6));ax.axis('off')
layers=[(.5,4.1,5.4,.75,'#d9eef5','Overlying water: 2-D transport'),(.5,3.65,5.4,.3,'#b7cbd1','Upper permeable geotextile: 3 mm'),(.5,2.5,5.4,1.0,'#d8bd86','Reactive keratin core: 10 mm'),(.5,2.05,5.4,.3,'#b7cbd1','Lower permeable geotextile: 3 mm'),(.5,.8,5.4,1.1,'#9b8b7c','Contaminated sediment: prescribed source')]
for x,y,w,h,c,lab in layers:
    ax.add_patch(Rectangle((x,y),w,h,facecolor=c,edgecolor='white'))
    ax.text(x+w/2,y+h/2,lab,ha='center',va='center',fontsize=9)
for x in [1.0,5.4]:
    ax.annotate('',xy=(x,5.1),xytext=(x,1.0),arrowprops={'arrowstyle':'-|>','color':'#24445a','lw':1.6})
ax.text(3.2,5.35,'Residual sediment-to-water flux',ha='center',fontsize=11,color='#155e75')
for y,lab in [(4.25,'Synthetic measurements'),(2.8,'Interval estimates'),(1.35,'Maintenance recommendation')]:
    ax.add_patch(Rectangle((6.6,y-.38),3.1,.76,facecolor='#edf1f4',edgecolor='#6c8593'))
    ax.text(8.15,y,lab,ha='center',va='center',fontsize=9)
for y in [3.8,2.35]: ax.annotate('',xy=(8.15,y-.53),xytext=(8.15,y),arrowprops={'arrowstyle':'->','color':'#24445a'})
ax.text(8.15,.42,'Simulation only; human review required',ha='center',fontsize=8)
ax.text(3.2,.35,'Schematic; vertical dimensions exaggerated',ha='center',fontsize=8)
save(fig,'concept')

# Six timeline panels, retaining data outside older preview plot limits.
fig,axs=plt.subplots(3,2,figsize=(9,8.7),constrained_layout=True)
attenuation_min=min(float(np.min(arr(t['y']))) for s in 'ABCDEF'
                    for t in get(s,'Attenuation through time')['data'])
for s,n,ax in zip('ABCDEF',names,axs.flat):
    for t in get(s,'Attenuation through time')['data']:
        e=t['name'].split()[0];ax.plot(arr(t['x']),100*arr(t['y']),label=e,color=COL[e],lw=1.5)
    ax.set(title=f'{s}  {n}',xlabel='Mat age (years)',ylabel='Whole-hotspot attenuation (%)')
    ax.set_ylim(min(0,100*attenuation_min-1),101);ax.grid(alpha=.2);ax.legend(ncol=3,loc='lower left')
save(fig,'attenuation_all')
fig,axs=plt.subplots(3,2,figsize=(9,8.7),constrained_layout=True)
for s,n,ax in zip('ABCDEF',names,axs.flat):
    for t in get(s,'Media saturation through time')['data']:
        e=t['name'].split()[0];ax.plot(arr(t['x']),100*arr(t['y']),label=e,color=COL[e],lw=1.5)
    ax.set(title=f'{s}  {n}',xlabel='Mat age (years)',ylabel='Fraction of nominal capacity (%)')
    ax.set_ylim(-2,103);ax.grid(alpha=.2);ax.legend(ncol=3,loc='upper left')
save(fig,'saturation_all')

fig,axs=plt.subplots(3,1,figsize=(9,7),sharex=True,constrained_layout=True)
for summary in S:
    timeline=summary['timeline']; years=[p['elapsed_years'] for p in timeline]
    for ax,key,label in zip(axs,['mean_fouling_index','mean_integrity_index','mean_coverage_fraction'],
                            ['Fouling index','Physical integrity','Hotspot coverage']):
        ax.plot(years,[p[key] for p in timeline],label=summary['scenario'].replace('_',' '))
        ax.set_ylabel(label);ax.grid(alpha=.2);ax.set_ylim(-.03,1.03)
axs[-1].set_xlabel('Mat age (years)')
axs[0].legend(ncol=2,fontsize=7)
save(fig,'condition_all')

# All recorded source maps, with shared scale within each nominal-age group.
for age in ['0.0','3.0','final']:
    ages={s:('0.0' if age=='0.0' else final_age(s) if age=='final' else late_age(s)) for s in 'ABCDEF'}
    selected=[get(s,f'Seabed residual flux at {ages[s]} yr') for s in 'ABCDEF']
    vmax=max(np.nanmax(arr(p['data'][0]['z'])) for p in selected)
    fig,axs=plt.subplots(3,2,figsize=(9,8.4),constrained_layout=True)
    for s,n,ax,p in zip('ABCDEF',names,axs.flat,selected):
        im=heat(ax,p,vmax,title=f'{s}  {n}, {ages[s]} yr')
    fig.colorbar(im,ax=axs.ravel().tolist(),shrink=.65,label='Residual Pb flux (µg m$^{-2}$ d$^{-1}$)')
    save(fig,'flux_'+age.replace('.',''))

# All spatial comparison families at archived late window, common paired scales.
spatial=[]
for s,n in zip('ABCDEF',names):
    fig,axs=plt.subplots(2,2,figsize=(9,6.3),constrained_layout=True)
    p0=get(s,f'Water concentration WITHOUT the mat at {late_age(s)} yr')
    p1=get(s,f'Water concentration WITH the mat at {late_age(s)} yr')
    z0=arr(p0['data'][0]['z']);z1=arr(p1['data'][0]['z'])
    vmax=max(np.nanmax(z0),np.nanmax(z1))
    im=heat(axs[0,0],p0,vmax,title='Without mat')
    heat(axs[0,1],p1,vmax,title='With mat')
    fig.colorbar(im,ax=list(axs[0]),shrink=.75,label='Pb (ng L$^{-1}$)')
    ratio_plot=get(s,f'Remaining fraction of the untreated plume at {late_age(s)} yr')
    ratio_max=max(1,float(np.nanmax(arr(ratio_plot['data'][0]['z']))))
    im=heat(axs[1,0],ratio_plot,ratio_max,'viridis','With / without concentration')
    fig.colorbar(im,ax=axs[1,0],shrink=.7,label='Ratio (not a risk metric)')
    im=heat(axs[1,1],get(s,f'Effective reactive cover at {late_age(s)} yr'),1,'YlGn','Effective reactive cover')
    fig.colorbar(im,ax=axs[1,1],shrink=.7,label='Fraction of cell area')
    fig.suptitle(f'{s}  {n}: spatial fields at {late_age(s)} yr',fontsize=11)
    save(fig,'spatial_'+s)
    summary=next(q for q in S if q['scenario']==scenario_ids[ord(s)-ord('A')])
    window=next(w for w in summary['windows'] if w['years']==float(late_age(s)))
    metrics=window['elements']['Pb']
    spatial.append({'scenario':s,'age_years':window['years'],
        'window_hours':window['window_s']/3600,
        'no_mat_kg_per_window':metrics['source_bare_kg'],
        'with_mat_kg_per_window':metrics['source_with_kg'],
        'spatial_flux_reduction_percent':100*metrics['area_attenuation'],
        'peak_without_ng_per_l':float(np.nanmax(z0)),
        'peak_with_ng_per_l':float(np.nanmax(z1)),
        'peak_ratio':float(np.nanmax(z1)/np.nanmax(z0))})
with (OUT/'data/spatial_summary.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(spatial[0]));w.writeheader();w.writerows(spatial)

# Extracted profiles retain their vertical coordinate (including carrier offset).
fig,axs=plt.subplots(3,2,figsize=(9,8.3),constrained_layout=True)
for s,n,ax in zip('ABCDEF',names,axs.flat):
    t=get(s,'Pb sorbed load through the core, per tile')['data'][0]
    x,y,z=arr(t['x']),arr(t['y']),arr(t['z'])
    im=ax.pcolormesh(x,y,z,shading='nearest',cmap='cividis')
    ax.set(title=f'{s}  {n}',xlabel='Tile index',ylabel='Height from mat base (mm)')
    fig.colorbar(im,ax=ax,label='Pb sorbed (mg kg$^{-1}$)')
save(fig,'profiles_all')
fig=plt.figure(figsize=(9,3.8))
for i,(key,title) in enumerate([('Pb sorbed load through the core, per tile','Final Pb distribution through the core'),('Water concentration WITH the mat at 3.0 yr','Three-year Pb water concentration')]):
    ax=fig.add_subplot(1,2,i+1,projection='3d');t=get('B',key)['data'][0]
    x,y,z=arr(t['x']),arr(t['y']),arr(t['z']);xx,yy=np.meshgrid(x,y)
    ax.plot_surface(xx,yy,z,cmap='viridis',linewidth=0,antialiased=True)
    ax.set_title(title,fontsize=10,pad=12)
    ax.set_xlabel('Tile index' if i==0 else 'East (m)',labelpad=4)
    ax.set_ylabel('Mat height (mm)' if i==0 else 'North (m)',labelpad=4)
    ax.set_zlabel('Pb (mg/kg)' if i==0 else 'Pb (ng/L)',labelpad=3)
    ax.tick_params(labelsize=7)
save(fig,'surfaces')

# Shared lower-left coordinates; baseline and centred partial coverage.
fig,axs=plt.subplots(1,2,figsize=(9,4.4),constrained_layout=True)
for ax,coverage,nx,title in [(axs[0],1.0,3,'Baseline: 100% footprint'),(axs[1],.45,2,'Undersized: 45% footprint')]:
    ax.set_aspect('equal')
    ax.add_patch(Rectangle((260,180),80,80,facecolor='#fae0b5',edgecolor='#9d5e16',lw=2))
    side=80*np.sqrt(coverage); x0=260+(80-side)/2; y0=180+(80-side)/2
    for j in range(nx):
        for i in range(nx):
            ax.add_patch(Rectangle((x0+i*side/nx,y0+j*side/nx),side/nx,side/nx,facecolor='#155e7530',edgecolor='#155e75'))
    ax.set(xlim=(250,350),ylim=(170,270),xlabel='East (m)',ylabel='North (m)',title=title)
    ax.grid(alpha=.15)
save(fig,'geometry')

# Whole-hotspot emissions for all policies; separate active/retrieved inventories.
fig,axs=plt.subplots(1,3,figsize=(9,3.2),constrained_layout=True)
ordered=sorted(Q,key=lambda q:['none','fixed','evidence_informed'].index(q['policy']))
labs=['No mat','Calendar','Evidence']
values=[[q['hotspot_into_water_kg']['Pb'] for q in ordered],
        [q['layer_ledger']['Pb']['retained_in_mat_kg']+q['layer_ledger']['Pb']['retained_in_retrieved_media_kg'] for q in ordered],
        [q['service_cost_eur']/1e6 for q in ordered]]
for ax,vals,title,unit in zip(axs,values,['Whole-hotspot Pb emission','Active + retrieved column Pb','Assumed service expenditure'],['kg','kg','EUR million']):
    bars=ax.bar(labs,vals,color=['#8c969d','#155e75','#bd7953']);ax.set(title=title,ylabel=unit);ax.grid(axis='y',alpha=.15)
    for b,v in zip(bars,vals):ax.annotate(f'{v:.3g}',(b.get_x()+b.get_width()/2,b.get_height()),xytext=(0,4),textcoords='offset points',ha='center',fontsize=8)
    ax.margins(y=.2)
save(fig,'policy')

# Scale and illustrative priority, redrawn from the exact gallery arrays.
t=get('B','Area to cover, against what a mat can lay')['data'][0]
fig,ax=plt.subplots(figsize=(8.5,3.4),constrained_layout=True)
areas=arr(t['y']);labels=['Demo\n0.64 ha','Bornholm\nprimary','Bornholm\nextended','Gotland\ndesignated','Skagerrak\ndesignated']
bars=ax.bar(labels,areas,color='#155e75');ax.set_yscale('log');ax.set_ylabel('Designated or modelled area (km²)');ax.grid(axis='y',alpha=.2)
for b,a in zip(bars,areas):ax.text(b.get_x()+b.get_width()/2,a*1.4,f'{a:g}' if a<1 else f'{a:,.1f}',ha='center',fontsize=8)
ax.set_ylim(.002,8000);save(fig,'scale')
t=get('B','Which hectares: candidate pilot areas by receptor proximity')['data'][0]
fig,ax=plt.subplots(figsize=(8.5,3),constrained_layout=True)
labs=['Generic industrial harbour','Kolberger Heide','Bay of Lübeck','Bornholm primary'];v=arr(t['x'])
ax.barh(labs,v,color=['#155e75','#ba8c38','#b34d54','#ba8c38']);ax.invert_yaxis();ax.set_xlabel('Illustrative priority score (dimensionless)');ax.set_xlim(0,2.8)
for i,x in enumerate(v):ax.text(x+.04,i,f'{x:.2f}',va='center')
save(fig,'priority')
t=get('B','Documented dumping areas, for scale')['data']
fig,ax=plt.subplots(figsize=(8,5),constrained_layout=True)
for tr in t:
    x,y=arr(tr['x']),arr(tr['y'])
    if tr.get('fill'):ax.fill(x,y,color='#deedf3',edgecolor='#a3c1d1',lw=.7)
    else:
        ax.scatter(x,y,s=55,c='#b45942',zorder=3)
        for xx,yy,lab in zip(x,y,tr.get('text',[])):
            import re
            lab=re.sub('<[^>]+>',' ',str(lab))
            ax.annotate(lab,(xx,yy),xytext=(6,5),textcoords='offset points',fontsize=7)
ax.set(xlabel='Longitude (degrees east)',ylabel='Latitude (degrees north)',title='Regional context from repository schematic')
ax.grid(alpha=.2);save(fig,'context')

# Independent numerical studies are regenerated by the repository tools.
import shutil
for stem,folder in [('reactive_numerical_audit','numerical-audit'),('timescale_audit','timescale-audit')]:
    for ext in ['pdf','png','json']:
        source=OUT.parent/'results'/folder/(stem+'.'+ext)
        if source.exists(): shutil.copy2(source,(FIG if ext!='json' else OUT/'data')/source.name)
print('Created',len(list(FIG.glob('*.pdf'))),'vector figure files')
