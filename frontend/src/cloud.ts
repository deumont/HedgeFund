import {createClient} from '@supabase/supabase-js'

const env=import.meta.env
export const cloudMode= !['127.0.0.1','localhost'].includes(location.hostname)&&Boolean(env.VITE_SUPABASE_URL&&env.VITE_SUPABASE_PUBLISHABLE_KEY)
const supabase=cloudMode?createClient(env.VITE_SUPABASE_URL,env.VITE_SUPABASE_PUBLISHABLE_KEY):null
const cache=new Map<string,{etag:string,payload:any}>()
export let cloudCapturedAt:string|null=null

async function member(){
 const {data:user,error:userError}=await supabase!.auth.getUser()
 if(userError||!user.user)return false
 const {data,error}=await supabase!.from('atlas_members').select('user_id').eq('user_id',user.user.id).maybeSingle()
 if(error)throw new Error('Cloud-Zugriffsprüfung fehlgeschlagen: '+error.message)
 return Boolean(data)
}
function canonical(path:string){
 const [base,query]=path.split('?');if(!query)return base
 const params=new URLSearchParams(query);params.sort();return base+'?'+params.toString()
}
async function command(path:string,method:'GET'|'POST',body:any={}){
 const id=crypto.randomUUID()
 const {error}=await supabase!.rpc('atlas_submit_command',{p_id:id,p_method:method,p_path:path,p_body:body})
 if(error)throw new Error(error.message)
 // Only poll this exact command. A timeout must never replay an administrative action.
 for(let i=0;i<35;i++){
  await new Promise(resolve=>setTimeout(resolve,1000))
  const {data,error:readError}=await supabase!.rpc('atlas_command_result',{p_id:id})
  if(readError)throw new Error(readError.message)
  if(data.status==='completed')return data.result
  if(['failed','uncertain','expired'].includes(data.status))throw new Error(data.error||'Cloud-Auftrag nicht ausgeführt')
 }
 throw new Error('Auftrag gespeichert, Bestätigung noch ausstehend. Nicht erneut senden; Status im System Monitor prüfen.')
}

export async function cloudApi(rawPath:string,body?:any):Promise<any>{
 if(!supabase)throw new Error('Supabase nicht konfiguriert')
 const path=canonical(rawPath)
 if(path==='session')return {authenticated:await member()}
 if(path==='login'){
  const {error}=await supabase.auth.signInWithPassword({email:body.email,password:body.password})
  if(error)throw new Error(error.message)
  if(!await member()){await supabase.auth.signOut();throw new Error('Dieses Konto hat keinen ATLAS-Zugriff.')}
  return {authenticated:true}
 }
 if(path==='logout'){
  const {error}=await supabase.auth.signOut();if(error)throw new Error(error.message)
  cache.clear();return {authenticated:false}
 }
 if(body!==undefined)return command(path,'POST',body)
 const old=cache.get(path)
 const {data,error}=await supabase.rpc('atlas_read_snapshot',{p_path:path,p_etag:old?.etag||''})
 if(error)throw new Error(error.message)
 if(data.missing)return command(path,'GET')
 const payload=data.payload??old?.payload
 if(payload===undefined)throw new Error('Cloud-Snapshot fehlt')
 cache.set(path,{etag:data.etag,payload})
 if(path==='overview'){
  cloudCapturedAt=data.captured_at
  const fresh=data.heartbeat&&Date.now()-Date.parse(data.heartbeat)<90000
  return {...payload,worker_online:Boolean(fresh&&payload.worker_online),active_traders:fresh?payload.active_traders:0,
   cloud:{captured_at:data.captured_at,engine_connected:Boolean(fresh)}}
 }
 return payload
}
