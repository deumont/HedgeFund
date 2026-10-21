import {test} from 'node:test'
import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import ts from 'typescript'
const source=await readFile(new URL('../src/transport.ts',import.meta.url),'utf8')
const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText
const {fetchWithPolicy,safeToRetry,onConnectionChange,getConnectionIssue,isNetworkFailure,errorMessage}=await import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'))
const pause=async()=>{}
test('GET and explicit read RPCs retry; writes and auth actions never retry',async()=>{
 assert.equal(safeToRetry('https://atlas.test/api/overview'),true)
 for(const name of ['atlas_read_snapshot','atlas_command_result'])assert.equal(safeToRetry('https://project.test/rest/v1/rpc/'+name,{method:'POST'}),true)
 for(const name of ['atlas_submit_command','other'])assert.equal(safeToRetry('https://project.test/rest/v1/rpc/'+name,{method:'POST'}),false)
 let calls=0
 const recovered=await fetchWithPolicy('/api/overview',undefined,async()=>{if(++calls<3)throw TypeError('Failed to fetch');return new Response('{}')},pause)
 assert.equal(recovered.ok,true);assert.equal(calls,3)
 for(const url of ['/api/chat','/api/action','https://project.test/rest/v1/rpc/atlas_submit_command','https://project.test/auth/v1/token']){
  let writes=0
  await assert.rejects(fetchWithPolicy(url,{method:'POST'},async()=>{writes++;throw TypeError('Failed to fetch')},pause),e=>isNetworkFailure(e))
  assert.equal(writes,1)
 }
})
test('network notice clears after recovery, with no raw fetch error',async()=>{
 const seen=[],off=onConnectionChange(x=>seen.push(x))
 await fetchWithPolicy('/api/overview',undefined,async()=>new Response('{}'),pause)
 await assert.rejects(fetchWithPolicy('/api/overview',undefined,async()=>{throw TypeError('Failed to fetch')},pause),e=>{assert.equal(errorMessage(e),'');return isNetworkFailure(e)})
 assert.match(getConnectionIssue(),/Gespeicherte Daten/)
 await fetchWithPolicy('/api/overview',undefined,async()=>new Response('{}'),pause)
 assert.equal(getConnectionIssue(),'');assert.equal(seen.at(-1),'');off()
 assert.equal(errorMessage(Error('Access denied')),'Access denied')
})
test('timeouts are bounded and 401/403 are returned without retries',async()=>{
 let calls=0
 await assert.rejects(fetchWithPolicy('/api/overview',undefined,async(input,init)=>{calls++;return new Promise((resolve,reject)=>init.signal.addEventListener('abort',()=>reject(new DOMException('Timed out','AbortError'))))},pause,5),e=>isNetworkFailure(e))
 assert.equal(calls,3)
 for(const status of [401,403]){
  let n=0;const r=await fetchWithPolicy('/api/overview',undefined,async()=>{n++;return new Response('{}',{status})},pause)
  assert.equal(r.status,status);assert.equal(n,1)
 }
})
