import {test} from 'node:test'
import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import ts from 'typescript'
const source=await readFile(new URL('../src/cloudReads.ts',import.meta.url),'utf8')
const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText
const {createReadCommands,createSnapshotReader}=await import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'))
const at=Date.parse('2026-10-21T15:00:00Z')
const stale={etag:'old',captured_at:new Date(at-60000).toISOString(),heartbeat:new Date(at).toISOString(),payload:{days:[21]}}

test('stale calendar renders immediately and concurrent views share one background read',async()=>{
 let finish,count=0
 const reader=createSnapshotReader(async()=>stale,()=>{count++;return new Promise(resolve=>{finish=resolve})},()=>at)
 assert.deepEqual((await reader.get('calendar?month=2026-10')).payload,{days:[21]})
 assert.deepEqual((await reader.get('calendar?month=2026-10')).payload,{days:[21]})
 assert.equal(count,1);finish({days:[21,22]});await new Promise(resolve=>setImmediate(resolve))
})
test('failed background refresh retains readable data and offline snapshots need no commands',async()=>{
 let count=0
 const reader=createSnapshotReader(async()=>({...stale,heartbeat:new Date(at-120000).toISOString()}),async()=>{count++;throw Error('offline')},()=>at)
 assert.deepEqual((await reader.get('agents/76')).payload,stale.payload);assert.equal(count,0)
 const failing=createSnapshotReader(async()=>stale,async()=>{throw Error('slow engine')},()=>at)
 assert.deepEqual((await failing.get('calendar')).payload,stale.payload)
 await new Promise(resolve=>setImmediate(resolve))
 assert.deepEqual((await failing.get('calendar')).payload,stale.payload)
})
test('missing snapshots wait for one shared read and ETag reads retain cached content',async()=>{
 let finish,count=0
 const reader=createSnapshotReader(async()=>({missing:true}),()=>{count++;return new Promise(resolve=>{finish=resolve})},()=>at)
 const first=reader.get('agents/76'),second=reader.get('agents/76')
 await new Promise(resolve=>setImmediate(resolve));assert.equal(count,1)
 finish({profile:{id:76}})
 assert.deepEqual((await first).payload,(await second).payload)
 let calls=0
 const etag=createSnapshotReader(async(path,tag)=>{calls++;return calls===1?{...stale,heartbeat:undefined}:{...stale,payload:null,etag:tag,heartbeat:undefined}},async()=>{},()=>at)
 await etag.get('calendar');assert.deepEqual((await etag.get('calendar')).payload,stale.payload)
})
test('read timeout resumes same command ID instead of submitting duplicates',async()=>{
 const submitted=[],polled=[];let complete=false
 const load=createReadCommands(async(id,path)=>{submitted.push({id,path})},async id=>{polled.push(id);return complete?{status:'completed',result:{days:[21]}}:{status:'processing'}},async()=>{},()=> 'fixed-id',1)
 const first=load('calendar'),second=load('calendar');assert.equal(first,second)
 await assert.rejects(first,/Datenabruf läuft noch/)
 complete=true;assert.deepEqual(await load('calendar'),{days:[21]})
 assert.equal(submitted.length,1);assert.deepEqual(polled,['fixed-id','fixed-id'])
})
test('expired reads fail explicitly and a later request may create a new read',async()=>{
 let submitted=0
 const load=createReadCommands(async()=>{submitted++},async()=>({status:'expired',error:'Abgelaufen'}),async()=>{},()=>String(submitted),1)
 await assert.rejects(load('calendar'),/Abgelaufen/)
 await assert.rejects(load('calendar'),/Abgelaufen/)
 assert.equal(submitted,2)
})

test('temporary network failure keeps dated cached data and recovers on next read',async()=>{
 let calls=0
 const reader=createSnapshotReader(async()=>{calls++;if(calls===2)throw new TypeError('Failed to fetch');return {...stale,heartbeat:undefined,payload:{value:calls}}},async()=>{},()=>at)
 assert.equal((await reader.get('overview')).payload.value,1)
 const offline=await reader.get('overview')
 assert.equal(offline.payload.value,1);assert.equal(offline.captured_at,stale.captured_at);assert.equal(offline.transport_offline,true)
 const restored=await reader.get('overview');assert.equal(restored.payload.value,3);assert.equal(restored.transport_offline,undefined)
})
test('authorization failures never fall back to private cached snapshots',async()=>{
 let calls=0
 const reader=createSnapshotReader(async()=>{if(calls++)throw Error('Access denied');return stale},async()=>{},()=>at)
 await reader.get('overview');await assert.rejects(reader.get('overview'),/Access denied/)
 reader.clear();await assert.rejects(reader.get('overview'),/Access denied/)
})
