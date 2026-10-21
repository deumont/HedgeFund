type Row=Record<string,any>

export function equityWindow(now=new Date()){
 const parts=(date:Date)=>Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(date).filter(p=>p.type!=='literal').map(p=>[p.type,Number(p.value)]))
 const d=parts(now),probe=Date.UTC(d.year,d.month-1,d.day,12),local=parts(new Date(probe))
 // Both requested endpoints occur after Berlin's DST transition on that day.
 const offset=Date.UTC(local.year,local.month-1,local.day,local.hour,local.minute,local.second)-probe
 return {date:`${d.year}-${String(d.month).padStart(2,'0')}-${String(d.day).padStart(2,'0')}`,
         start:Date.UTC(d.year,d.month-1,d.day,15,30)-offset,end:Date.UTC(d.year,d.month-1,d.day,18,30)-offset}
}

export function sessionEquity(rows:Row[],_current?:Row,_asOf?:string,now=new Date()){
 const window=equityWindow(now),until=Math.min(window.end,now.getTime())
 const inWindow=(stamp:string)=>Number.isFinite(Date.parse(stamp))&&Date.parse(stamp)>=window.start&&Date.parse(stamp)<=until
 const points=new Map<number,Row>()
 for(const row of rows){
  if(row.equity_u!=null&&Number.isFinite(Number(row.equity_u))&&inWindow(row.created_at)){
   const observed=Date.parse(row.observed_at||row.created_at)
   if(!Number.isFinite(observed)||observed<window.start||observed>until)continue
   const slot=window.start+Math.floor((Date.parse(row.created_at)-window.start)/300000)*300000
   // First recorded value for the five-minute slot wins. Never append a live
   // portfolio estimate between slots or move a saved point on a UI refresh.
   if(!points.has(slot))points.set(slot,{...row,created_at:new Date(slot).toISOString(),observed_at:row.observed_at||row.created_at})
  }
 }
 return {...window,rows:[...points.values()].sort((a,b)=>Date.parse(a.created_at)-Date.parse(b.created_at))}
}
