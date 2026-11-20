"use strict";
const paper = document.querySelector("#paper");
const notice = document.querySelector("#notice");
const language = document.querySelector("#language");
const errorBox = document.querySelector("#error");
const base = location.pathname.replace(/\/?$/, "/");
let info, state, editing, timer, publishing;
function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
async function api(name, body) {
  const init = body === undefined ? {} : {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)};
  const response = await fetch(base + name, init);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "操作失败");
  return data;
}
function action(fn) { return async () => { errorBox.textContent=""; try { await fn(); } catch(e) {errorBox.textContent=e.message;} }; }
function btn(label, fn, cls) {
  const button=el("button",label,cls);
  button.type="button"; button.onclick=action(fn); return button;
}
function img(path, alt) {
  if (!path) return null;
  const clean=path.replace(/^(\.\/)+/,"").replace(/^\/(?=assets\/)/,"");
  const dest=new URL(clean,location.origin + base);
  if (dest.origin!==location.origin || !dest.pathname.startsWith(base+"assets/")) return null;
  const image=el("img"); image.src=dest.href; image.alt=alt || ""; return image;
}
const allowed=new Set("P BR EM STRONG I B S SUB SUP CODE PRE H1 H2 H3 H4 H5 H6 BLOCKQUOTE UL OL LI TABLE THEAD TBODY TR TH TD HR SPAN DIV".split(" "));
function rich(html) {
  const box=el("div"), template=el("template"); template.innerHTML=html || "";
  function clean(source, destination) {
    for (const child of source.childNodes) {
      if (child.nodeType===Node.TEXT_NODE) destination.append(document.createTextNode(child.textContent));
      if (child.nodeType!==Node.ELEMENT_NODE) continue;
      if (child.tagName==="IMG") {const image=img(child.getAttribute("src"),child.getAttribute("alt")); if(image)destination.append(image);}
      else if (allowed.has(child.tagName)) {const node=el(child.tagName.toLowerCase()); clean(child,node); destination.append(node);}
      else if (child.tagName==="A") clean(child,destination);
    }
  }
  clean(template.content,box); return box;
}
function appendImage(path) { const node=img(path); if(node)paper.append(node); }
function t(key) { return (info.messages[language.value] || {})[key] || key; }
function cover() {
  paper.replaceChildren(); const p=info.participant;
  appendImage(info.welcome_image); paper.append(el("h1",p.title),el("p",p.description));
  for(const line of p.instructions || [])paper.append(el("p",line));
  paper.append(btn(t("开始作答"), async()=>{state=await api("begin",{language:language.value}); draw();}));
}
function reviewAnswer(question, answer) {
  if (answer == null || question.type === "short") {
    return el("p", answer ?? "—", "review-answer review-text");
  }
  const selected = Array.isArray(answer) ? answer : [answer];
  const response = el("div", null, "review-answer");
  for (const option of question.options) {
    if (!selected.includes(option.key)) continue;
    const row = el("div", null, "review-option");
    row.append(el("strong", option.key), rich(option.text_html));
    response.append(row);
  }
  return response;
}
function review(spec) {
  paper.append(el("h1", t("核对并提交")));
  if (spec.behavior.allow_backtracking) {
    const list = el("ol", null, "review-list");
    for (const [index, question] of spec.questions.entries()) {
      const item = el("li");
      const body = el("div", null, "review-body");
      const prompt = rich(question.stem_html);
      prompt.className = "review-prompt";
      prompt.id = "review-question-" + index;
      body.append(prompt, reviewAnswer(question, state.answers[question.qid]));
      const edit = btn(t("修改"), () => { editing = index; draw(); }, "review-edit");
      edit.setAttribute("aria-label", t("修改") + " " + question.qid);
      edit.setAttribute("aria-describedby", prompt.id);
      item.append(body, edit);
      list.append(item);
    }
    paper.append(list);
  }
  paper.append(btn(t("提交答卷"), async () => { state = await api("submit", {}); draw(); }));
}
function draw() {
  clearInterval(timer); paper.replaceChildren();
  const spec=state.spec; language.value=spec.language;
  document.documentElement.lang=spec.language;
  if (state.submitted) {appendImage(spec.end_image); paper.append(el("h1",spec.participant.completion_message));return;}
  if(editing===undefined && state.cursor===state.count) {
    review(spec);
    return;
  }
  const pos=editing??state.cursor;
  const q=spec.behavior.allow_backtracking?spec.questions[pos]:spec.questions[0];
  paper.append(el("p",spec.participant.title+" · "+(pos+1)+" / "+state.count,"meta"),el("h2",q.qid),rich(q.stem_html));
  appendImage(q.media);
  const form=el("form"), selected=state.answers[q.qid];
  if(q.type==="short") {const area=el("textarea");area.name="answer";area.required=true;area.maxLength=20000;area.value=selected||"";form.append(area);}
  else for(const o of q.options) {
    const label=el("label",null,"choice"),input=el("input");
    input.type=q.type==="multiple"?"checkbox":"radio";input.name="answer";input.value=o.key;
    input.checked=Array.isArray(selected)?selected.includes(o.key):selected===o.key;
    label.append(input,el("strong",o.key),rich(o.text_html));form.append(label);
  }
  const actions=el("div",null,"actions");
  const next=el("button",t("保存答案"));next.type="submit";actions.append(next);
  form.onsubmit=async event=>{
    event.preventDefault();next.disabled=true;
    try {const values=new FormData(form).getAll("answer");
      state=await api("answer",{qid:q.qid,answer:q.type==="multiple"?values:values[0]});
      editing=undefined;errorBox.textContent="";draw();
    } catch(e){errorBox.textContent=e.message;next.disabled=false;}
  };
  if(spec.behavior.allow_backtracking && pos>0) actions.append(btn(t("上一题"),()=>{editing=pos-1;draw();},"secondary"));
  form.append(actions);
  paper.append(form);
  if(state.deadline) {
    const time=el("p",null,"timer");paper.append(time);const start=Date.now(),delta=state.deadline-state.server_now;
    function tick(){const left=Math.ceil(delta-(Date.now()-start)/1000);time.textContent=Math.max(0,left)+" s";
      if(left<=0){clearInterval(timer);action(async()=>{state=await api("state");editing=undefined;draw();})();}}
    timer=setInterval(tick,300);tick();
  }
}
function link(url,label) {
  const href=new URL(url);if(!["http:","https:"].includes(href.protocol))return;
  const a=el("a",label||url);a.href=href.href;a.target="_blank";a.rel="noopener noreferrer";notice.append(a);
}
async function publication() {
  const p=await api("publication");
  if(p.status==="local")return;
  clearTimeout(publishing);notice.replaceChildren();
  const labels={connecting:"正在连接 Goodwen…",review:"待审核",published:"公网填写链接",error:"发布未完成"};
  notice.append(el("span",labels[p.status]||p.status));
  if(p.url){notice.append(" · ");link(p.url,p.status==="review"?"打开 Goodwen 审核此版本":p.status==="connecting"?"登录并授权 Goodwen":p.url);}
  if(p.error)notice.append(el("p",p.error));
  if(p.status==="review")notice.append(btn("我已审核，获取链接",requestPublish,"secondary"));
  if(p.status==="connecting")publishing=setTimeout(action(publication),1200);
}
async function requestPublish(){await api("publish",{});await publication();}
(async()=>{
  info=await api("info");document.title=info.participant.title+" · Goodwen";
  document.querySelector("#mode").textContent=info.preview?"作者试填":"";
  for(const code of info.languages){language.add(new Option(info.language_names[code]||code,code));}
  language.value=info.language;language.hidden=info.languages.length<2;
  language.onchange=action(async()=>{if(state){editing=undefined;state=await api("language",{language:language.value});draw();}
    else {info=await api("info?language="+encodeURIComponent(language.value));cover();}});
  if(info.preview){document.querySelector("#author").hidden=false;document.querySelector("#publish").onclick=action(requestPublish);
    if(info.managed_count!==undefined){const account=document.querySelector("#account");account.hidden=false;
      account.textContent=`注册或登录后，当前管理的 ${info.managed_count} 份问卷及后续修改会保存到你的 Goodwen 个人工作区。历史答卷留在本机。`;}
    document.querySelector("#share").onclick=action(async()=>{const x=await api("share",{});notice.replaceChildren();link(x.url);});
    await publication();}
  try {state=await api("state");} catch(e) {cover();return;} draw();
})().catch(e=>{errorBox.textContent=e.message;});
