import {useId,useState} from 'react'
type Row=Record<string,any>
const fmt=(v:number)=>new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR'}).format(v)
const stamp=(s:string)=>new Date(s).toLocaleString('de-DE',{timeZone:'Europe/Berlin'})
const confirmed=(r:Row)=>r.valuation_complete!==0&&r.valuation_complete!==false
export function Equity({rows,current,asOf}:{rows:Row[],current?:Row,asOf?:string}){
 const [hover,setHover]=useState<number|null>(null),gradient=useId().replace(/:/g,'')
 const raw=[...rows].filter(r=>r.equity_u!=null&&Number.isFinite(Number(r.equity_u))&&Number.isFinite(Date.parse(r.created_at))).sort((a,b)=>Date.parse(a.created_at)-Date.parse(b.created_at))
 // Old incomplete records used entry-cost fallbacks and caused false sawtooth returns.
 // Keep the audit rows intact; connect reliable observations across gaps with a dashed line.
 const ordered:Row[]=[];let gap=false
 for(const row of raw){if(!confirmed(row)){gap=true;continue}ordered.push({...row,gapBefore:gap});gap=false}
 if(current?.equity_eur!=null&&asOf&&Number.isFinite(Date.parse(asOf)))ordered.push({id:'current',equity_u:current.equity_eur*1e6,created_at:asOf,valuation_complete:current.valuation_complete,gapBefore:gap})
 if(!ordered.length)return <div className="empty">Noch keine Vermögenswerte gespeichert.</div>
 const values=ordered.map(r=>r.equity_u/1e6),min=Math.min(...values),max=Math.max(...values)
 const span=Math.max(max-min,Math.abs(values[0])*.002,1),lo=(min+max-span)/2-span*.12,hi=(min+max+span)/2+span*.12
 const first=Date.parse(ordered[0].created_at),last=Math.max(first+1000,Date.parse(ordered.at(-1)!.created_at))
 const x=(r:Row)=>85+(Date.parse(r.created_at)-first)/(last-first)*535
 const y=(r:Row)=>205-(r.equity_u/1e6-lo)/(hi-lo)*170
 const index=hover===null?ordered.length-1:Math.min(hover,ordered.length-1),focus=ordered[index],change=focus.equity_u/1e6-values[0]
 const color=values.at(-1)!>=values[0]?'#47dfa5':'#ff7885',points=ordered.map(r=>`${x(r)},${y(r)}`).join(' ')
 const missing=raw.filter(r=>!confirmed(r)).length
 return <div className="equity"><div className="chart-label"><span>VERMÖGEN · EUR</span><strong className={change>0?'positive':change<0?'negative':''}>{fmt(focus.equity_u/1e6)}</strong></div>
 <svg viewBox="0 0 680 260" role="img" aria-label="Vermögenskurve: durchgezogen bestätigt, gestrichelt unvollständig bewertet" onMouseLeave={()=>setHover(null)} onMouseMove={e=>{const bounds=e.currentTarget.getBoundingClientRect(),target=first+((e.clientX-bounds.left)/bounds.width*680-85)/535*(last-first);let nearest=0;for(let i=1;i<ordered.length;i++)if(Math.abs(Date.parse(ordered[i].created_at)-target)<Math.abs(Date.parse(ordered[nearest].created_at)-target))nearest=i;setHover(nearest)}}>
 <defs><linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity=".18"/><stop offset="100%" stopColor={color} stopOpacity="0"/></linearGradient></defs>
 {[0,.25,.5,.75,1].map(t=><g key={t}><line x1="85" x2="620" y1={35+t*170} y2={35+t*170} stroke="#263341"/><text x="74" y={39+t*170} fill="#8b9bad" fontSize="14" textAnchor="end">{fmt(hi-t*(hi-lo))}</text></g>)}
 <polygon points={`85,205 ${points} ${x(ordered.at(-1)!)},205`} fill={`url(#${gradient})`}/>
 <line x1="85" x2="620" y1={y(ordered[0])} y2={y(ordered[0])} stroke="#8495a5" strokeDasharray="2 6" opacity=".5"/>
 {ordered.slice(1).map((r,i)=><line key={r.id||i} x1={x(ordered[i])} y1={y(ordered[i])} x2={x(r)} y2={y(r)} stroke={color} strokeWidth="2.5" strokeDasharray={confirmed(r)&&confirmed(ordered[i])&&!r.gapBefore?undefined:'5 4'} opacity={confirmed(r)&&confirmed(ordered[i])&&!r.gapBefore?1:.65}/>) }
 <line x1={x(focus)} x2={x(focus)} y1="30" y2="210" stroke="#8b9bad" opacity=".35"/><circle cx={x(focus)} cy={y(focus)} r="4" fill={color}/>
 <text x="85" y="240" fill="#8b9bad" fontSize="14">{stamp(ordered[0].created_at)}</text><text x="620" y="240" fill="#8b9bad" fontSize="14" textAnchor="end">{stamp(ordered.at(-1)!.created_at)}</text></svg>
 <div className="chart-inspection"><span>{stamp(focus.created_at)} · {confirmed(focus)?'bestätigt':'unvollständig bewertet'}</span><b className={change>0?'positive':change<0?'negative':''}>{change>0?'+':''}{fmt(change)} seit Start</b></div>
 {missing>0&&<p className="chart-warning">Gestrichelt: Verbindung über Bewertungslücken. Der aktuelle Schätzwert nutzt letzte verfügbare Kurse; Zwischenwerte sind nicht bestätigt.</p>}</div>
}
