import {test} from 'node:test'
import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import ts from 'typescript'
async function module(name){
 const source=await readFile(new URL(`../src/${name}.ts`,import.meta.url),'utf8')
 const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText
 return import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'))
}
const {equityWindow,sessionEquity}=await module('equitySession')
const {loginError,requestConfirmation}=await module('authConfirmation')
const {recoveryIntent}=await module('authRecovery')
const point=(created_at,equity_u=3000000000)=>({created_at,equity_u,valuation_complete:1})

test('fixed Berlin window follows summer and winter time including DST day',()=>{
 assert.equal(new Date(equityWindow(new Date('2026-10-21T15:00Z')).start).toISOString(),'2026-10-21T13:30:00.000Z')
 const winter=equityWindow(new Date('2026-10-25T15:00Z'))
 assert.equal(new Date(winter.start).toISOString(),'2026-10-25T14:30:00.000Z')
 assert.equal(new Date(winter.end).toISOString(),'2026-10-25T17:30:00.000Z')
})

test('shows only current-day observations inside 15:30 through 18:30',()=>{
 const rows=['2026-10-20T14:00Z','2026-10-21T13:29:59Z','2026-10-21T13:30Z','2026-10-21T16:30Z','2026-10-21T16:30:01Z'].map(x=>point(x))
 const result=sessionEquity(rows,undefined,undefined,new Date('2026-10-21T18:00Z'))
 assert.deepEqual(result.rows.map(r=>r.created_at),['2026-10-21T13:30Z','2026-10-21T16:30Z'])
 assert.equal(result.end-result.start,3*60*60*1000)
})

test('never appends a late current valuation after 18:30',()=>{
 const result=sessionEquity([point('2026-10-21T16:29Z')],{equity_eur:9999},'2026-10-21T16:31Z',new Date('2026-10-21T16:32Z'))
 assert.equal(result.rows.length,1)
 assert.equal(result.rows[0].equity_u,3000000000)
})

test('empty before open and after Berlin midnight, including cached previous day payloads',()=>{
 const rows=[point('2026-10-21T14:00Z')]
 assert.equal(sessionEquity(rows,{equity_eur:3000},'2026-10-21T13:00Z',new Date('2026-10-21T13:10Z')).rows.length,0)
 const next=sessionEquity(rows,{equity_eur:3000},'2026-10-21T16:00Z',new Date('2026-10-21T22:05Z'))
 assert.equal(next.date,'2026-10-22')
 assert.equal(next.rows.length,0)
})

test('rejects future and malformed values and replaces duplicate timestamp with current point',()=>{
 const rows=[point('2026-10-21T15:00Z'),point('invalid'),point('2026-10-21T14:00Z'),point('2026-10-21T13:50Z',NaN)]
 const result=sessionEquity(rows,{equity_eur:2999,valuation_complete:false},'2026-10-21T14:00Z',new Date('2026-10-21T14:10Z'))
 assert.equal(result.rows.length,1)
 assert.equal(result.rows[0].equity_u,2999000000)
 assert.equal(result.rows[0].valuation_complete,false)
})

test('translates unconfirmed login errors and preserves actionable code',()=>{
 const error=loginError({code:'email_not_confirmed',message:'Email not confirmed'})
 assert.equal(error.code,'email_not_confirmed')
 assert.match(error.message,/bestätigt/)
 assert.equal(loginError({message:'Invalid login credentials'}).message,'Invalid login credentials')
})

test('requests signup confirmation for the entered email and current app origin',async()=>{
 const calls=[],client={auth:{resend:async x=>{calls.push(x);return {error:null}}}}
 await requestConfirmation(client,' ceo@example.test ','https://atlas.test')
 assert.deepEqual(calls,[{type:'signup',email:'ceo@example.test',options:{emailRedirectTo:'https://atlas.test/?auth=confirmed'}}])
 await assert.rejects(()=>requestConfirmation(client,'Atlas','https://atlas.test'))
 assert.equal(calls.length,1)
})

test('confirmation rate and delivery errors never claim success',async()=>{
 await assert.rejects(()=>requestConfirmation({auth:{resend:async()=>({error:{status:429}})}},'ceo@example.test','https://atlas.test'),/warten/)
 await assert.rejects(()=>requestConfirmation({auth:{resend:async()=>({error:{code:'email_address_not_authorized'}})}},'ceo@example.test','https://atlas.test'),/nicht freigegeben/)
})

test('expired signup links do not enter password recovery',()=>{
 const intent=recoveryIntent('https://atlas.test/?auth=confirmed#error=access_denied&error_code=otp_expired')
 assert.equal(intent.requested,false)
 assert.equal(intent.invalid,false)
 assert.equal(recoveryIntent('https://atlas.test/?auth=recovery#error=access_denied').invalid,true)
})
