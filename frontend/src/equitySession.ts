type Row=Record<string,any>

export function equityWindow(now=new Date()){
 const parts=(date:Date)=>Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(date).filter(p=>p.type!=='literal').map(p=>[p.type,Number(p.value)]))
 const d=parts(now),probe=Date.UTC(d.year,d.month-1,d.day,12),local=parts(new Date(probe))
 // Both requested endpoints occur after Berlin's DST transition on that day.
 const offset=Date.UTC(local.year,local.month-1,local.day,local.hour,local.minute,local.second)-probe
 return {date:`${d.year}-${String(d.month).padStart(2,'0')}-${String(d.day).padStart(2,'0')}`,
         start:Date.UTC(d.year,d.month-1,d.day,15,30)-offset,end:Date.UTC(d.year,d.month-1,d.day,18,30)-offset}
}

export function sessionEquity(rows:Row[],current?:Row,asOf?:string,now=new Date()){
 const window=equityWindow(now),until=Math.min(window.end,now.getTime())
 const inWindow=(stamp:string)=>Number.isFinite(Date.parse(stamp))&&Date.parse(stamp)>=window.start&&Date.parse(stamp)<=until
 const points=new Map<number,Row>()
 for(const row of rows){
  if(row.equity_u!=null&&Number.isFinite(Number(row.equity_u))&&inWindow(row.created_at))points.set(Date.parse(row.created_at),row)
 }
 if(current?.equity_eur!=null&&Number.isFinite(Number(current.equity_eur))&&asOf&&inWindow(asOf)){
  points.set(Date.parse(asOf),{id:'current',equity_u:Number(current.equity_eur)*1e6,created_at:asOf,valuation_complete:current.valuation_complete})
 }
 return {...window,rows:[...points.values()].sort((a,b)=>Date.parse(a.created_at)-Date.parse(b.created_at))}
}
