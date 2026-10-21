export const recoveryMessage='Der Reset-Link ist abgelaufen oder ungültig. Bitte einen neuen Link anfordern.'
type AuthClient={auth:{resetPasswordForEmail:(email:string,options:{redirectTo:string})=>Promise<any>,getUser:()=>Promise<any>,updateUser:(data:{password:string})=>Promise<any>,signOut:()=>Promise<any>}}
export function recoveryIntent(url:string){
 const u=new URL(url),hash=new URLSearchParams(u.hash.slice(1))
 return {requested:u.searchParams.get('auth')==='recovery'||hash.get('type')==='recovery',invalid:Boolean(hash.get('error')||u.searchParams.get('error'))}
}
export function validatePassword(password:string,confirmation:string){
 if(password.length<12)throw new Error('Bitte mindestens 12 Zeichen verwenden.')
 if(password!==confirmation)throw new Error('Die Passwörter stimmen nicht überein.')
}
export async function requestReset(client:AuthClient,email:string,origin:string){
 email=email.trim()
 if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)||email.length>254)throw new Error('Bitte eine gültige E-Mail-Adresse eingeben.')
 const {error}=await client.auth.resetPasswordForEmail(email,{redirectTo:new URL('/?auth=recovery',origin).href})
 if(error)throw new Error(error.status===429?'Zu viele Anfragen. Bitte etwas warten und erneut versuchen.':error.message)
}
export async function verifyRecovery(client:AuthClient){
 const {data,error}=await client.auth.getUser()
 if(error||!data.user)throw new Error(recoveryMessage)
 return data.user
}
export async function updateRecovery(client:AuthClient,password:string,confirmation:string){
 validatePassword(password,confirmation)
 await verifyRecovery(client)
 const {error}=await client.auth.updateUser({password})
 if(error)throw new Error(error.message)
 await client.auth.signOut()
}
