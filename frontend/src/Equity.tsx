import {useId,useState} from 'react'
import {sessionEquity} from './equitySession'
type Row=Record<string,any>
const fmt=(v:number)=>new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR'}).format(v)
const stamp=(s:string)=>new Date(s).toLocaleString('de-DE',{timeZone:'Europe/Berlin'})
const confirmed=(r:Row)=>r.valuation_complete!==0&&r.valuation_complete!==false
export function Equity({rows,current,asOf}:{rows:Row[],current?:Row,asOf?:string}){
 const [hover,setHover]=useState<number|null>(null),gradient=useId().replace(/:/g,'')
 const session=sessionEquity(rows,current,asOf),raw=session.rows
 const ordered:Row[]=raw.map((row,i)=>({...row,gapBefore:i>0&&Date.parse(row.created_at)-Date.parse(raw[i-1].created_at)>300000}))
 if(!ordered.length)return <div className="empty">Heute noch keine Vermögenswerte zwischen 15:30 und 18:30 Uhr gespeichert. Europe/Berlin.</div>
 const values=ordered.map(r=>r.equity_u/1e6),min=Math.min(...values),max=Math.max(...values)
 const span=Math.max(max-min,Math.abs(values[0])*.002,1),lo=(min+max-span)/2-span*.12,hi=(min+max+span)/2+span*.12
 const first=session.start,last=session.end
 const x=(r:Row)=>85+(Date.parse(r.created_at)-first)/(last-first)*535
 const y=(r:Row)=>205-(r.equity_u/1e6-lo)/(hi-lo)*170
 const index=hover===null?ordered.length-1:Math.min(hover,ordered.length-1),focus=ordered[index],change=focus.equity_u/1e6-values[0]
 const color=values.at(-1)!>=values[0]?'#47dfa5':'#ff7885',points=ordered.map(r=>`${x(r)},${y(r)}`).join(' ')
 const missing=raw.filter(r=>!confirmed(r)).length
 return <div className="equity"><div className="chart-label"><span>HEUTE · VERMÖGEN · EUR</span><strong className={change>0?'positive':change<0?'negative':''}>{fmt(focus.equity_u/1e6)}</strong></div>
 <svg viewBox="0 0 680 260" role="img" aria-label="Vermögenskurve: durchgezogen bestätigt, gestrichelt unvollständig bewertet" onMouseLeave={()=>setHover(null)} onMouseMove={e=>{const bounds=e.currentTarget.getBoundingClientRect(),target=first+((e.clientX-bounds.left)/bounds.width*680-85)/535*(last-first);let nearest=0;for(let i=1;i<ordered.length;i++)if(Math.abs(Date.parse(ordered[i].created_at)-target)<Math.abs(Date.parse(ordered[nearest].created_at)-target))nearest=i;setHover(nearest)}}>
 <defs><linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity=".18"/><stop offset="100%" stopColor={color} stopOpacity="0"/></linearGradient></defs>
 {[0,.25,.5,.75,1].map(t=><g key={t}><line x1="85" x2="620" y1={35+t*170} y2={35+t*170} stroke="#263341"/><text x="74" y={39+t*170} fill="#8b9bad" fontSize="14" textAnchor="end">{fmt(hi-t*(hi-lo))}</text></g>)}
 <polygon points={`${x(ordered[0])},205 ${points} ${x(ordered.at(-1)!)},205`} fill={`url(#${gradient})`}/>
 <line x1={x(ordered[0])} x2={x(ordered.at(-1)!)} y1={y(ordered[0])} y2={y(ordered[0])} stroke="#8495a5" strokeDasharray="2 6" opacity=".5"/>
 {ordered.slice(1).map((r,i)=><line key={r.id||i} x1={x(ordered[i])} y1={y(ordered[i])} x2={x(r)} y2={y(r)} stroke={color} strokeWidth="2.5" strokeDasharray={confirmed(r)&&confirmed(ordered[i])&&!r.gapBefore?undefined:'5 4'} opacity={confirmed(r)&&confirmed(ordered[i])&&!r.gapBefore?1:.65}/>) }
 {ordered.map((r,i)=><circle key={r.id||i} cx={x(r)} cy={y(r)} r="2.5" fill={confirmed(r)?color:'#0e1821'} stroke={color} strokeWidth="1.4"><title>{stamp(r.created_at)} · {fmt(r.equity_u/1e6)} · erfasst {stamp(r.observed_at||r.created_at)} · {confirmed(r)?'bestätigt':'letzter verifizierter Kurs'}</title></circle>)}
 <line x1={x(focus)} x2={x(focus)} y1="30" y2="210" stroke="#8b9bad" opacity=".35"/><circle cx={x(focus)} cy={y(focus)} r="4" fill={color}/>
 {['15:30','16:30','17:30','18:30'].map((label,i)=><text key={label} x={85+i*535/3} y="240" fill="#8b9bad" fontSize="14" textAnchor={i===0?'start':i===3?'end':'middle'}>{label}</text>)}</svg>
 <div className="chart-inspection"><span>{stamp(focus.created_at)} · {confirmed(focus)?'bestätigt':'Schätzwert'} · erfasst {stamp(focus.observed_at||focus.created_at)}</span><b className={change>0?'positive':change<0?'negative':''}>{change>0?'+':''}{fmt(change)} seit erstem Tageswert</b></div>
 <p className="chart-warning">Ein gespeicherter Festpunkt je fünf Minuten. Fehlende Messungen bleiben Lücken.{missing>0?' Gestrichelt: Schätzwerte mit letzten verifizierten Kursen; keine aktuellen Ausführungskurse.':''}</p></div>
}
