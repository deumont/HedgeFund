export const connectionMessage='Verbindung unterbrochen. Gespeicherte Daten bleiben sichtbar; der Abruf wird automatisch wiederholt.'
const listeners=new Set<(message:string)=>void>()
let issue=''
export const getConnectionIssue=()=>issue
export function onConnectionChange(fn:(message:string)=>void){listeners.add(fn);return()=>{listeners.delete(fn)}}
function connection(online:boolean){const next=online?'':connectionMessage;if(next!==issue){issue=next;listeners.forEach(fn=>fn(issue))}}
export function isNetworkFailure(error:any){return error?.code==='network_unavailable'||error?.name==='AbortError'||/failed to fetch|fetch failed|load failed|network(?:error| request failed)|timed?\s*out|timeout|Verbindung unterbrochen\. Gespeicherte Daten/i.test(error?.message||String(error))}
export function errorMessage(error:any){return isNetworkFailure(error)?'':error?.message||'Anfrage fehlgeschlagen'}

// Supabase read RPCs use POST at the HTTP layer, but are safe to repeat. No
// administrative command, chat, password change or order submission is retried.
export function safeToRetry(input:RequestInfo|URL,init?:RequestInit){
 const method=(init?.method||(input instanceof Request?input.method:'GET')).toUpperCase()
 if(method==='GET'||method==='HEAD')return true
 const url=new URL(input instanceof Request?input.url:String(input),'https://atlas.invalid')
 return method==='POST'&&['/rest/v1/rpc/atlas_read_snapshot','/rest/v1/rpc/atlas_command_result'].includes(url.pathname)
}
export async function fetchWithPolicy(input:RequestInfo|URL,init?:RequestInit,fetcher:typeof fetch=fetch,
 wait=(ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms)),timeoutMs=12000):Promise<Response>{
 const retry=safeToRetry(input,init),signal=init?.signal||(input instanceof Request?input.signal:undefined)
 for(let attempt=0;;attempt++){
  const controller=new AbortController(),abort=()=>controller.abort()
  if(signal?.aborted)throw new DOMException('Request aborted','AbortError')
  signal?.addEventListener('abort',abort,{once:true})
  const timeout=setTimeout(abort,timeoutMs)
  try{
   const response=await fetcher(input,{...init,signal:controller.signal})
   if([429,502,503,504].includes(response.status)&&retry&&attempt<2){await response.body?.cancel();await wait(300*(attempt+1));continue}
   if([502,503,504].includes(response.status)){
    connection(false);throw Object.assign(new Error('Netzwerkdienst vorübergehend nicht erreichbar'),{code:'network_unavailable'})
   }
   connection(true);return response
  }catch(error){
   if(signal?.aborted)throw error
   if(!isNetworkFailure(error))throw error
   connection(false)
   if(!retry||attempt>=2)throw Object.assign(new Error(connectionMessage),{code:'network_unavailable'})
   await wait(300*(attempt+1))
  }finally{clearTimeout(timeout);signal?.removeEventListener('abort',abort)}
 }
}
