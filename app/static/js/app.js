// Simple single-workspace UI. No login, tokens, or user accounts.
const $=id=>document.getElementById(id);
// Single-workspace conversation identifier, not an authentication token.
let conversationId=sessionStorage.getItem('atlas_conversation_id')||crypto.randomUUID();
sessionStorage.setItem('atlas_conversation_id',conversationId);
$('newChat').onclick=()=>{conversationId=crypto.randomUUID();sessionStorage.setItem('atlas_conversation_id',conversationId);$('messages').replaceChildren();toast('Started a new conversation')};

const toast=msg=>{const el=$('toast');el.textContent=msg;el.style.display='block';setTimeout(()=>el.style.display='none',4000)};
const api=async(path,options={})=>{const res=await fetch(path,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});const data=await res.json();if(!res.ok)throw Error(data.detail||'Request failed');return data};
function view(name){['chat','docs','approval','admin'].forEach(x=>{$(x+'View').classList.toggle('hidden',x!==name);$(x+'Tab').classList.toggle('active',x===name)});$('heading').textContent={chat:'Ask your organization\'s knowledge',docs:'Document management',approval:'Approval requests',admin:'Operational overview'}[name];if(name==='docs')loadDocs();if(name==='admin')loadMetrics();if(name==='approval')loadApprovals()}
$('chatTab').onclick=()=>view('chat');$('docsTab').onclick=()=>view('docs');$('adminTab').onclick=()=>view('admin');$('approvalTab').onclick=()=>view('approval');$('refreshApprovals').onclick=loadApprovals;
function addMessage(content,kind,sources=[]){const el=document.createElement('div');el.className='message '+kind;el.textContent=content;if(sources.length){const wrap=document.createElement('div');wrap.className='sources';sources.forEach(s=>{const d=document.createElement('details');const title=document.createElement('summary');title.textContent=`[${s.index}] ${s.title} — page ${s.page}`;const excerpt=document.createElement('p');excerpt.textContent=s.excerpt;d.append(title,excerpt);wrap.append(d)});el.append(wrap);const feedback=document.createElement('button');feedback.textContent='👍 Helpful';feedback.onclick=async()=>{try{await api('/api/feedback',{method:'POST',body:JSON.stringify({rating:1})});toast('Feedback saved')}catch(e){toast(e.message)}};el.append(feedback)}$('messages').append(el);$('messages').scrollTo({top:$('messages').scrollHeight,behavior:'smooth'})}
$('chatForm').onsubmit=async e=>{e.preventDefault();const q=$('question').value.trim();if(!q)return;addMessage(q,'user');$('question').value='';addMessage('Searching approved documents...','assistant');const loading=$('messages').lastElementChild;try{const r=await api('/api/chat',{method:'POST',body:JSON.stringify({question:q,conversation_id:conversationId})});loading.remove();addMessage(r.answer,'assistant',r.sources);if(r.status==='pending_approval'){const btn=document.createElement('button');btn.textContent='Review approval request →';btn.onclick=()=>view('approval');$('messages').lastElementChild.append(btn)}}catch(err){loading.textContent=err.message}};
document.querySelectorAll('[data-q]').forEach(b=>b.onclick=()=>{$('question').value=b.dataset.q;$('question').focus()});
async function loadDocs(){try{const r=await api('/api/documents');$('docs').replaceChildren(...r.documents.map(d=>{const row=document.createElement('div');row.textContent=`${d.title} — ${d.status} (v${d.current_version})`;return row}))}catch(e){$('docs').textContent=e.message}}
async function loadMetrics(){try{$('metrics').textContent=JSON.stringify(await api('/api/admin/metrics'),null,2);$('guardrailMetrics').textContent=JSON.stringify(await api('/api/admin/guardrails'),null,2)}catch(e){$('metrics').textContent=e.message}}
$('uploadForm').onsubmit=async e=>{e.preventDefault();const f=$('file').files[0];if(!f)return;if(f.size>10485760){toast('Maximum file size is 10 MB');return}try{const r=await api('/api/documents/uploads',{method:'POST',body:JSON.stringify({filename:f.name})});const up=await fetch(r.upload_url,{method:'PUT',headers:r.headers,body:f});if(!up.ok)throw Error('S3 upload failed');toast('Uploaded to S3. Processing document now...');await api('/api/documents/complete',{method:'POST',body:JSON.stringify({document_id:r.document_id})});toast('Document indexed in Pinecone!');loadDocs()}catch(err){toast(err.message)}};

// Admin approval workflow. DOM nodes use textContent (never untrusted innerHTML).
async function loadApprovals(){
  const root=$('approvalList');root.textContent='Loading approvals...';
  try{
    const response=await api('/api/approvals');
    if(!Array.isArray(response.approvals)) throw Error('Unexpected API response: approvals list missing');
    const approvals=response.approvals;
    const pending=approvals.filter(a=>String(a.status).trim().toLowerCase()==='pending').length;
    $('approvalSummary').textContent=`${pending} pending · ${approvals.length} total (most recent 100)`;
    root.replaceChildren();
    if(!approvals.length){root.textContent='No approval requests yet. Try asking the chatbot to delete a document.';return}
    for(const a of approvals){
      const card=document.createElement('article');card.className='approval-card';
      const header=document.createElement('div');header.className='approval-header';
      const title=document.createElement('strong');title.textContent=a.question;
      const badge=document.createElement('span');badge.className='approval-status '+a.status;badge.textContent=a.status;
      header.append(title,badge);card.append(header);
      const meta=document.createElement('p');meta.textContent=`Requested by ${a.requester} · ${new Date(a.created_at).toLocaleString()}`;card.append(meta);
      if(String(a.status).trim().toLowerCase()==='pending'){
        const actions=document.createElement('div');actions.className='approval-actions';
        for(const [label,approve] of [['Approve',true],['Reject',false]]){
          const button=document.createElement('button');button.textContent=label;button.className=approve?'approve-button':'reject-button';
          button.onclick=async()=>{
            const decision=approve?'approve':'reject';
            if(!confirm(`Are you sure you want to ${decision} this request? This records a decision only and does not execute the requested action.`))return;
            button.disabled=true;
            try{const r=await api(`/api/approvals/${encodeURIComponent(a.id)}/decision`,{method:'POST',body:JSON.stringify({approve})});toast(`Request ${r.status}. No action executed.`);await loadApprovals()}
            catch(e){toast(e.message);button.disabled=false}
          };
          actions.append(button);
        }
        card.append(actions);
      }else{
        const info=document.createElement('p');info.textContent=`Reviewed by ${a.reviewer||'unknown'} · ${a.reviewed_at?new Date(a.reviewed_at).toLocaleString():''} · No action executed`;card.append(info);
      }
      root.append(card);
    }
  }catch(e){root.textContent=`Unable to load approvals: ${e.message}. Check /api/approvals and your Uvicorn terminal.`;console.error('Approvals loading failed:',e)}
}