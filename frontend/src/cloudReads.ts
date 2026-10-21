type Snapshot={missing?:boolean,etag?:string,payload?:any,captured_at?:string,heartbeat?:string}
type CommandResult={status:string,result?:any,error?:string}

// Resume the same read after a timeout; polling must not fill the queue with
// another command every time React refreshes the page. Never used for writes.
export function createReadCommands(submit:(id:string,path:string)=>Promise<void>,poll:(id:string)=>Promise<CommandResult>,
 wait=()=>new Promise<void>(resolve=>setTimeout(resolve,1000)),uuid=()=>crypto.randomUUID(),attempts=35){
 const pending=new Map<string,{id:string,promise?:Promise<any>}>()
 return (path:string):Promise<any>=>{
  let item=pending.get(path)
  if(item?.promise)return item.promise
  const fresh=!item
  if(!item){item={id:uuid()};pending.set(path,item)}
  const current=item
  current.promise=(async()=>{
   if(fresh){try{await submit(current.id,path)}catch(e){pending.delete(path);throw e}}
   for(let i=0;i<attempts;i++){
    await wait()
    const data=await poll(current.id)
    if(data.status==='completed'){pending.delete(path);return data.result}
    if(['failed','uncertain','expired'].includes(data.status)){
     pending.delete(path);throw new Error(data.error||'Datenabruf nicht ausgeführt')
    }
   }
   throw new Error('Datenabruf läuft noch. Die Seite prüft denselben Auftrag erneut.')
  })().finally(()=>{current.promise=undefined})
  return current.promise
 }
}

export function createSnapshotReader(read:(path:string,etag:string)=>Promise<Snapshot>,refresh:(path:string)=>Promise<any>,clock=()=>Date.now()){
 const cache=new Map<string,Snapshot>(),running=new Map<string,Promise<any>>()
 let generation=0
 function update(path:string){
  const active=running.get(path);if(active)return active
  const started=generation
  const promise=refresh(path).then(payload=>{
   if(started===generation)cache.set(path,{...cache.get(path),etag:'',payload})
   return payload
  }).finally(()=>{if(running.get(path)===promise)running.delete(path)})
  running.set(path,promise);return promise
 }
 return {
  clear(){generation++;cache.clear();running.clear()},
  async get(path:string):Promise<Snapshot>{
   const old=cache.get(path),started=generation
   const data=await read(path,old?.etag||'')
   if(data.missing){const payload=await update(path);return {payload}}
   const payload=data.payload??old?.payload
   if(payload===undefined)throw new Error('Cloud-Snapshot fehlt')
   const snapshot={...data,payload}
   if(started===generation)cache.set(path,snapshot)
   const interactive=/^agents\/\d+(?:\/history.*)?$/.test(path)||path.startsWith('calendar')||['trading-floor','closeout','team'].includes(path)||path.startsWith('research')
   if(interactive&&data.heartbeat&&clock()-Date.parse(data.heartbeat)<90000&&clock()-Date.parse(data.captured_at||'')>15000){
    // A usable snapshot is shown immediately, even if the engine is slow or a
    // background refresh fails. The next view poll picks up the new snapshot.
    void update(path).catch(()=>{})
   }
   return snapshot
  }
 }
}
