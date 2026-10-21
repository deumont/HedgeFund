type Row=Record<string,any>
const stamp=(s:string)=>new Date(s).toLocaleString('de-DE',{timeZone:'Europe/Berlin'})
const sourceName=(s:Row)=>{if(s.title&&!s.title.startsWith('http'))return s.title;try{const u=new URL(s.url);return `${u.hostname} · ${u.pathname.split('/').filter(Boolean).pop()||'Originalquelle'}`}catch{return 'Quelle öffnen'}}
export function AgentResearch({profile,research=[],monitor}:{profile:Row,research?:Row[],monitor?:Row}){
 if(profile.approach!=='news')return null
 const desk=profile.desk
 return <section className="panel"><div className="panel-head"><div><h3>{profile.focus||'Eigene Nachrichtenrecherche'}</h3><span>{profile.department==='research'?'Forschung · keine Orderberechtigung':'Eigenständiger Paper-Trader'}</span></div></div><div className="report-copy">
 {desk&&<><p>Beobachtet {desk.watchlist.join(', ')} und selbst recherchierte passende Aktien.</p><p>{desk.catalyst_check}</p></>}
 {monitor&&<><p><b>Nachrichtenüberwachung</b> · {stamp(monitor.checked_at)}<br/>{monitor.symbols.join(', ')} · {monitor.relevant_articles} relevante Meldungen. Feedprüfung jede Minute; Web-Hintergrundrecherche stündlich im Handel, soweit Budget und Quellen verfügbar.</p>{monitor.assessment?.error&&<p className="negative">Letzte Nachrichtenbewertung: {monitor.assessment.error}</p>}</>}
 {research.map(r=><article key={r.id}><h3>Eigene Web-Recherche · {stamp(r.created_at)}</h3><p style={{whiteSpace:'pre-wrap'}}>{r.report.replace(/\[([^\]]+)\]\(https?:\/\/[^)]+\)/g,'$1').replace(/\*\*/g,'')}</p><details><summary>{r.sources?.length||0} recherchierte Quellen ansehen</summary><div className="research-sources">{[...(r.sources||[])].sort((a,b)=>Number(b.cited)-Number(a.cited)).map((s:Row)=><a key={s.url} href={s.url} title={s.url} target="_blank" rel="noopener noreferrer">{sourceName(s)} ↗</a>)}</div></details><small>Abruf dokumentiert. Veröffentlichungszeiten und Aussagen des Webberichts sind nicht unabhängig bestätigt; kein alleiniger Einstiegsbeleg.</small></article>)}
 {!research.length&&<p>Noch keine gespeicherte Web-Recherche. Ergebnisse und Quellen erscheinen nach erfolgreicher Ausführung.</p>}
 </div></section>
}
