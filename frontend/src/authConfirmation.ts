type AuthError={code?:string,status?:number,message?:string}
type Client={auth:{resend:(params:{type:'signup',email:string,options:{emailRedirectTo:string}})=>Promise<any>}}

export function loginError(error:AuthError){
 const unconfirmed=error.code==='email_not_confirmed'||/email not confirmed/i.test(error.message||'')
 return Object.assign(new Error(unconfirmed?'Deine E-Mail-Adresse ist noch nicht bestätigt. Bitte den Bestätigungslink öffnen oder die Bestätigungsmail erneut anfordern.':error.message||'Anmeldung fehlgeschlagen.'),{code:unconfirmed?'email_not_confirmed':error.code})
}

export async function requestConfirmation(client:Client,email:string,origin:string){
 email=email.trim()
 if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)||email.length>254)throw new Error('Bitte eine gültige E-Mail-Adresse eingeben.')
 const {error}=await client.auth.resend({type:'signup',email,options:{emailRedirectTo:new URL('/?auth=confirmed',origin).href}})
 if(error)throw new Error(error.status===429?'Zu viele E-Mail-Anfragen. Bitte warten und später erneut versuchen.':error.code==='email_address_not_authorized'?'Der E-Mail-Versand ist für diese Adresse beim Anbieter noch nicht freigegeben. Bitte den Administrator kontaktieren.':error.message||'Bestätigungsmail konnte nicht angefordert werden.')
}
