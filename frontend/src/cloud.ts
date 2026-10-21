import {createClient} from '@supabase/supabase-js'
import {recoveryIntent,requestReset,verifyRecovery,updateRecovery,recoveryMessage} from './authRecovery'
import {loginError,requestConfirmation} from './authConfirmation'
import {createReadCommands,createSnapshotReader} from './cloudReads'
import {fetchWithPolicy,isNetworkFailure} from './transport'

const env=import.meta.env
export const cloudMode= !['127.0.0.1','localhost'].includes(location.hostname)&&Boolean(env.VITE_SUPABASE_URL&&env.VITE_SUPABASE_PUBLISHABLE_KEY)
const initialRecovery=recoveryIntent(location.href)
let recovering=cloudMode&&(initialRecovery.requested||initialRecovery.invalid)
const recoveryListeners=new Set<(active:boolean)=>void>()
const supabase=cloudMode?createClient(env.VITE_SUPABASE_URL,env.VITE_SUPABASE_PUBLISHABLE_KEY,{global:{fetch:fetchWithPolicy}}):null
const readCommand=createReadCommands(async(id,path)=>{
 const {error}=await supabase!.rpc('atlas_submit_command',{p_id:id,p_method:'GET',p_path:path,p_body:{}})
 if(error)throw new Error(error.message)
},async id=>{
 const {data,error}=await supabase!.rpc('atlas_command_result',{p_id:id})
 if(error)throw new Error(error.message)
 return data
})
const snapshots=createSnapshotReader(async(path,etag)=>{
 const {data,error}=await supabase!.rpc('atlas_read_snapshot',{p_path:path,p_etag:etag})
 if(error)throw new Error(error.message)
 return data
},readCommand,()=>Date.now(),isNetworkFailure)
export let cloudCapturedAt:string|null=null
supabase?.auth.onAuthStateChange(event=>{if(event==='PASSWORD_RECOVERY'){recovering=true;recoveryListeners.forEach(fn=>fn(true))}})
export const isRecovering=()=>recovering
export function onRecoveryChange(fn:(active:boolean)=>void){recoveryListeners.add(fn);return()=>{recoveryListeners.delete(fn)}}
export async function checkRecovery(){if(!supabase||initialRecovery.invalid)throw new Error(recoveryMessage);return verifyRecovery(supabase)}
export async function sendReset(email:string){if(!supabase)throw new Error('Nur für den Cloud-Zugang verfügbar.');await requestReset(supabase,email,location.origin)}
export async function sendConfirmation(email:string){if(!supabase)throw new Error('Nur für den Cloud-Zugang verfügbar.');await requestConfirmation(supabase,email,location.origin)}
export async function saveRecoveredPassword(password:string,confirmation:string){
 if(!supabase||!recovering)throw new Error(recoveryMessage)
 await updateRecovery(supabase,password,confirmation)
 snapshots.clear();recovering=false;history.replaceState(null,'',location.pathname);recoveryListeners.forEach(fn=>fn(false))
}
export async function cancelRecovery(){
 await supabase?.auth.signOut();snapshots.clear();recovering=false;history.replaceState(null,'',location.pathname);recoveryListeners.forEach(fn=>fn(false))
}

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
  if(error)throw loginError(error)
  if(!await member()){await supabase.auth.signOut();throw new Error('Dieses Konto hat keinen ATLAS-Zugriff.')}
  return {authenticated:true}
 }
 if(path==='logout'){
  const {error}=await supabase.auth.signOut();if(error)throw new Error(error.message)
  snapshots.clear();return {authenticated:false}
 }
 if(body!==undefined){
  try{return await command(path,'POST',body)}catch(error){
   if(isNetworkFailure(error))throw new Error('Verbindung unterbrochen; die Bestätigung des Auftrags fehlt. Nicht erneut senden, bevor der gespeicherte Status geprüft wurde.')
   throw error
  }
 }
 const data=await snapshots.get(path),payload=data.payload
 if(path==='overview'){
  cloudCapturedAt=data.captured_at??null
  const fresh=data.heartbeat&&Date.now()-Date.parse(data.heartbeat)<90000
  return {...payload,worker_online:Boolean(fresh&&payload.worker_online),active_traders:fresh?payload.active_traders:0,
   cloud:{captured_at:data.captured_at,engine_connected:Boolean(fresh),transport_offline:Boolean(data.transport_offline)}}
 }
 return payload
}
