"use strict";
// CHODBAK web: the browser can't see other apps, so the "duty post" is this tab. Leave it (switch tab,
// minimise, click another app) and the havaldar strikes: audio plays from the background, a notification
// and the floating PiP guard shout over other apps, and the full overlay is waiting when you come back.

const API = "https://api.sarvam.ai";
// name -> [how the model should write it, Sarvam language code, button label]
const LANGS = {
  hinglish: ["Hinglish (Hindi-English mix, Roman script)", "hi-IN", "Hinglish"],
  hindi: ["Hindi in Devanagari script", "hi-IN", "हिन्दी"],
  english: ["Indian English", "en-IN", "English"],
  bengali: ["Bengali in Bengali script", "bn-IN", "বাংলা"],
  gujarati: ["Gujarati in Gujarati script", "gu-IN", "ગુજરાતી"],
  kannada: ["Kannada in Kannada script", "kn-IN", "ಕನ್ನಡ"],
  malayalam: ["Malayalam in Malayalam script", "ml-IN", "മലയാളം"],
  marathi: ["Marathi in Devanagari script", "mr-IN", "मराठी"],
  odia: ["Odia in Odia script", "od-IN", "ଓଡ଼ିଆ"],
  punjabi: ["Punjabi in Gurmukhi script", "pa-IN", "ਪੰਜਾਬੀ"],
  tamil: ["Tamil in Tamil script", "ta-IN", "தமிழ்"],
  telugu: ["Telugu in Telugu script", "te-IN", "తెలుగు"],
};
const VOICES = { hinglish: "shubh", hindi: "aditya", english: "rahul", bengali: "soham", gujarati: "manan", kannada: "gokul",
  malayalam: "mani", marathi: "rupali", odia: "advait", punjabi: "kabir", tamil: "vijay", telugu: "kavitha" };
// Bulbul v3 delivery per level; level 3 also goes through a gain + compressor so it sounds like shouting
const EMOTION = { 1: { pace: 1.15, temperature: 0.6 }, 2: { pace: 0.9, temperature: 0.9 }, 3: { pace: 1.35, temperature: 1.0 } };
const MOODS = {
  1: "a stern, firm first warning",
  2: "deeply disappointed and guilt-tripping, like a parent who expected better: start with a heavy sigh (Haaye..., Hmm...), use slow trailing pauses (...), mention someone they love watching right now",
  3: "maximum fury, SHOUTING: short punchy bursts, lots of exclamation marks, a few words in CAPS, stretched words like Kyaaaa?! and Nalaaayak!",
};
const FALLBACK = {
  1: "Saavdhan! Back to work right now. Chodi mat kar!",
  2: "Haaye... Oye nalayak! Sharma ji ka beta never opens other tabs. Dekh, sab disappointed hain.",
  3: "NIKAL us tab se, nikamme! Chappal ready hai. WAPAS KAAM PE!",
};
const HEADERS = { 1: ["SAAVDHAN!", "#f5d742"], 2: ["RUK JA, NALAYAK!", "#f59342"], 3: ["KHATRA! KHATRA!", "#e83b3b"] };
const LEVEL_SFX = { 1: "faaa", 2: "cat_laugh", 3: "metal_pipe" };
const SFX_ALL = ["faaa", "cat_laugh", "metal_pipe", "ye_le"];
const GRACE = 1000, NAG_EVERY = 8000, RESET_AFTER = 10 * 60000, CHAI_EVERY = 25 * 60000;
const MOM_HINGLISH = "Mummy ko abhi phone lagaun kya?";
const HOSTAGE_STATES = ["zinda (for now)", "ghabraya hua", "ro raha hai", "last rites chal rahe hain", "kalma padh raha hai"];
const FAMILY = [
  ["Pinky Aunty", "beta duty post chhod ke kahan gaye?? 🙄"],
  ["Bade Papa", "Sharma ji ka beta toh aaj 14 ghante padha"],
  ["Mummy", "Seen ✓✓"],
  ["Chachi", "maine toh pehle hi bola tha ye haath se nikal gaya"],
  ["Nani", "🙏🙏 bhagwan sadbuddhi de"],
  ["Fufaji", "hamare zamane mein reels nahi hoti thi"],
  ["Cousin Rinku", "😂😂😂 pakde gaye"],
  ["Mausi", "forwarded: 10 SIGNS YOUR CHILD IS ADDICTED TO REELS"],
];
const GUARD = [
  ".....HHHHHH.....", "...HHhhhhhhHH...", "..HhhhhhhhhhhH..", "..HHHHHHHHHHHH..", ".HHHHHHHHHHHHHH.", "...SSSSSSSSSS...",
  "...SBBSSSSBBS...", "...SSKSSSSKSS...", "...SSSSssSSSS...", "...SMMMMMMMMS...", "...SSSRRRRSSS...", "....SSRRRRSS....",
  ".....SSSSSS.....", "...GGGGGGGGGG...", "..GGGgGGGGgGGG..", "..GGGGGGGGGGGG..",
];
const CHAPPAL = ["....bb.........", "...b..b........", "..b....b.......", "WWWWWWWWWWWWWW.", "WwwwwwwwwwwwwWW", "WWWWWWWWWWWWWW."];
const PALETTE = { H: "#4b5341", h: "#6e7860", S: "#e0ac69", s: "#b8834a", B: "#2b1d0e", K: "#111111", M: "#3b2a1a",
  R: "#7a1010", G: "#55603f", g: "#d4af37", b: "#2a6fdb", W: "#8b5a2b", w: "#a87444" };

// ---- storage (per browser; never leaves it) ----------------------------------------------------
const store = {
  get(k, d = null) { try { const v = localStorage.getItem("chodbak_" + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("chodbak_" + k, JSON.stringify(v)); } catch { /* private mode: works, just forgets */ } },
};
const todayKey = () => new Date().toDateString();

const S = {
  key: store.get("key"), lang: store.get("lang"), face: store.get("face"),
  onDuty: false, away: false, awayTimer: null, struck: false, strikes: 0, level: 0,
  today: (store.get("today") || {}).d === todayKey() ? store.get("today").n : 0,
  goodSince: Date.now(), nextChai: Date.now() + CHAI_EVERY, lastNag: 0, hostageHp: 0,
  lastTaunt: FALLBACK[3], pip: null, onReturn: [], banks: {},
};

const $ = (q) => document.querySelector(q);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const pick = (a) => a[Math.floor(Math.random() * a.length)];
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

function sprite(rows, px, flip = false) {
  const c = document.createElement("canvas");
  c.width = rows[0].length * px; c.height = rows.length * px; c.className = "sprite";
  const g = c.getContext("2d");
  (flip ? [...rows].reverse() : rows).forEach((row, y) => [...row].forEach((ch, x) => {
    if (PALETTE[ch]) { g.fillStyle = PALETTE[ch]; g.fillRect(x * px, y * px, px, px); }
  }));
  return c;
}

// ---- audio ---------------------------------------------------------------------------------------
let ctx;
function audio() { ctx ??= new AudioContext(); if (ctx.state === "suspended") ctx.resume(); return ctx; }
function out(level) {
  const a = audio();
  if (level !== 3) return a.destination;
  const gain = a.createGain(); gain.gain.value = 2.5;
  const comp = a.createDynamicsCompressor();
  comp.threshold.value = -28; comp.knee.value = 6; comp.ratio.value = 12;
  gain.connect(comp).connect(a.destination);
  return gain;
}
const buffers = new Map();
function load(url) {
  if (!buffers.has(url)) buffers.set(url, fetch(url).then((r) => { if (!r.ok) throw new Error(url); return r.arrayBuffer(); })
    .then((b) => audio().decodeAudioData(b)));
  return buffers.get(url);
}
function playBuffer(buf, level = 1, maxSec) {
  return new Promise((res) => {
    const s = audio().createBufferSource();
    s.buffer = buf; s.connect(out(level)); s.onended = res;
    maxSec ? s.start(0, 0, maxSec) : s.start();
    setTimeout(res, (maxSec || buf.duration) * 1000 + 1500); // never hang if the browser keeps sound locked
  });
}
async function playUrl(url, level = 1, maxSec) { try { await playBuffer(await load(url), level, maxSec); } catch { /* missing file: skip */ } }
async function playB64(b64, level) {
  try {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    await playBuffer(await audio().decodeAudioData(bytes.buffer), level);
  } catch { /* undecodable: skip */ }
}
const sfx = (name) => playUrl(`sfx/${name || pick(SFX_ALL)}.mp3`, 1, 2.5); // clips are padded; cut them

function beep(freq, start, dur, type = "square", vol = 0.05, toFreq) {
  const a = audio(), o = a.createOscillator(), g = a.createGain();
  o.type = type; o.frequency.setValueAtTime(freq, start);
  if (toFreq) o.frequency.linearRampToValueAtTime(toFreq, start + dur * 0.45);
  g.gain.value = vol; o.connect(g).connect(a.destination); o.start(start); o.stop(start + dur);
}
function cookerSiti(whistles = 3) { // pressure cooker: rising hiss, then the scream
  let t = audio().currentTime;
  for (let i = 0; i < whistles; i++, t += 1.15) beep(1400, t, 0.9, "sawtooth", 0.035, 3000);
}
function ring() { // Indian ringback: double tone
  let t = audio().currentTime;
  for (let i = 0; i < 3; i++, t += 2) { beep(440, t, 1.2, "sine", 0.06); beep(480, t, 1.2, "sine", 0.06); }
}

// ---- Sarvam (called straight from the browser with the visitor's own key) ------------------------
async function sarvam(path, json, form) {
  if (!S.key) throw new Error("no key");
  const headers = { "api-subscription-key": S.key };
  if (json) headers["content-type"] = "application/json";
  const r = await fetch(API + path, { method: "POST", headers, body: form || JSON.stringify(json) });
  if (!r.ok) throw new Error("Sarvam " + r.status);
  return r.json();
}
async function liveTaunt(level) {
  const threat = level >= 2 ? "You are holding their AI coding agent hostage. Threaten that if they stay distracted, you will delete it or force it to write spaghetti code and push to main. " : "";
  const system = "You are CHODBAK, a furious old-school desi army havaldar and PT sir overseeing a desi student who must stay focused. " +
    'Your catchphrase is "Chodi mat kar!". The student just left their study tab. ' +
    `This is warning ${level} of 3: be ${MOODS[level]}. ` +
    `Bark at them in ${LANGS[S.lang][0]} (keep that script, don't romanize), sprinkled with desi drill-ground shouts ` +
    "(Saavdhan!, Oye!, Nalayak, Nikamma, Chal bhaag) and desi references (Sharma ji ka beta, chappal, log kya kahenge, board exams, mummy). " +
    "Swearing is fine. " + threat +
    "Use only English and that Indian language: no German or any other foreign words. No slurs, no threats of real violence against people. " +
    "It will be read aloud by a voice actor, so let punctuation carry the emotion (... for sighs, ! for shouting). At most 2 short sentences. Output only the line itself.";
  const r = await sarvam("/v1/chat/completions", { model: "sarvam-105b-conversations",
    messages: [{ role: "system", content: system }, { role: "user", content: "Taunt me." }] });
  const text = (r.choices?.[0]?.message?.content || "").trim().replace(/^"|"$/g, "");
  if (!text) throw new Error("empty");
  return text;
}
async function tts(text, level) {
  const r = await sarvam("/text-to-speech", { text: text.slice(0, 2500), language_code: LANGS[S.lang][1], speaker: VOICES[S.lang],
    model: "bulbul:v3", output_audio_codec: "wav", ...EMOTION[level] });
  return r.audios[0];
}
async function bankTaunt() { // pre-recorded angry lines in taunts/<lang>/ (made by chodbak.py --make-taunts)
  S.banks[S.lang] ??= fetch(`taunts/${S.lang}/taunts.json`).then((r) => r.json()).catch(() => [FALLBACK[3]]);
  const list = await S.banks[S.lang];
  const i = Math.floor(Math.random() * list.length);
  return [list[i], `taunts/${S.lang}/${String(i).padStart(2, "0")}.mp3`];
}
async function momLine() {
  try { const r = await fetch(`taunts/${S.lang}/mom.txt`); if (!r.ok) throw 0; return [(await r.text()).trim(), `taunts/${S.lang}/mom.mp3`]; }
  catch { return [MOM_HINGLISH, null]; }
}

// ---- watching the duty post -----------------------------------------------------------------------
function leaving() {
  if (!S.onDuty || S.away) return;
  if (S.pip && S.pip.document.hasFocus()) return; // clicked the floating guard, not a distraction
  S.away = true;
  S.awayTimer = setTimeout(() => { S.awayTimer = null; if (S.away && !S.struck) strike(); }, GRACE);
  renderPip();
}
function returned() {
  if (!S.away) return;
  clearTimeout(S.awayTimer); S.awayTimer = null; S.away = false;
  if (S.struck) {
    S.struck = false; S.goodSince = Date.now(); S.nextChai = S.goodSince + CHAI_EVERY;
    S.onReturn.splice(0).forEach((f) => f()); // chappal, gossip: things that only work if you can see them
    if (S.level) $("#overlay .card")?.classList.add("shake");
  }
  setStatus(S.level === 3 ? "alarm" : "on");
  renderPip();
}
document.addEventListener("visibilitychange", () => (document.hidden ? leaving() : returned()));
window.addEventListener("blur", () => setTimeout(() => { if (!document.hasFocus()) leaving(); }, 120)); // iframes keep hasFocus()
window.addEventListener("focus", returned);

async function strike() {
  S.struck = true; S.lastNag = Date.now();
  const level = S.strikes = Math.min(S.strikes + 1, 3);
  S.today += 1; store.set("today", { d: todayKey(), n: S.today });
  renderStats(); setStatus("alarm");
  showOverlay(level);
  notify(HEADERS[level][0], "Wapas aa! Chodi mat kar!");
  const meme = sfx(LEVEL_SFX[level]);
  if (level === 2) S.onReturn.push(familyGossip);
  if (level === 3) { cookerSiti(); S.onReturn.push(throwChappal); }
  let text, voice;
  try { text = await liveTaunt(level); voice = await tts(text, level); }
  catch { [text, voice] = await bankTaunt(); } // no key / offline: pre-recorded line
  S.lastTaunt = text; setBody(text); renderPip(); notify(HEADERS[level][0], text);
  await meme;
  await (voice.startsWith("taunts/") ? playUrl(voice, level) : playB64(voice, level));
  if (level === 3) { // the last taunt, cold and disappointed after all the shouting
    const [mom, url] = await momLine();
    S.mom = mom; setBody(`${text}\n\n${mom}`); callingToast(); notify("📞 CALLING MUMMY...", mom);
    if (url) await playUrl(url, 2);
  }
}
async function nag() { // still away after strike 3: a fresh pre-recorded taunt, no API calls
  S.lastNag = Date.now();
  S.hostageHp = Math.min(S.hostageHp + 1, HOSTAGE_STATES.length - 1);
  const [text, url] = await bankTaunt();
  S.lastTaunt = text; setBody(S.mom ? `${text}\n\n${S.mom}` : text); renderHostage(); renderPip();
  notify("KHATRA! KHATRA!", text);
  cookerSiti(1);
  await sfx(); await playUrl(url, 3);
}
setInterval(() => {
  const now = Date.now();
  if (S.onDuty && S.away && S.struck && S.strikes === 3 && now - S.lastNag >= NAG_EVERY) nag();
  if (S.onDuty && !S.away) {
    if (now - S.goodSince > RESET_AFTER && S.level === 0) S.strikes = 0;
    if (now >= S.nextChai) { S.nextChai = now + CHAI_EVERY; chaiToast(); }
  }
  renderStats();
}, 1000);

// ---- UI: status, stats, overlays, toasts ----------------------------------------------------------
function setStatus(mode, text) {
  const s = $("#status");
  s.className = mode === "off" ? "" : mode;
  s.textContent = text || ({ off: "OFF DUTY. Open your work below, then report for duty.",
    on: `ON DUTY (${LANGS[S.lang]?.[2]}). Stay on this tab. Chodi mat kar!`, alarm: "KHATRA! You left the duty post." })[mode];
}
function renderStats() {
  $("#strikes").textContent = S.strikes; $("#today").textContent = S.today;
  const secs = S.onDuty && !S.away ? Math.floor((Date.now() - S.goodSince) / 1000) : 0;
  $("#focus").textContent = `${String(Math.floor(secs / 60)).padStart(2, "0")}:${String(secs % 60).padStart(2, "0")}`;
}
function notify(title, body) {
  if (document.hasFocus() || !("Notification" in window) || Notification.permission !== "granted") return;
  try { new Notification(`CHODBAK · ${title}`, { body, icon: $("#favicon").href, tag: "chodbak", renotify: true }); } catch { /* some browsers need a service worker */ }
}

function card(color) {
  const ov = $("#overlay");
  ov.innerHTML = "";
  const c = el("div", "card"); c.style.borderColor = color;
  const left = el("div", "left"), right = el("div", "right");
  c.append(left, right); ov.append(c); ov.classList.remove("hidden");
  return [c, left, right];
}
function closeOverlay() { $("#overlay").classList.add("hidden"); $("#overlay").innerHTML = ""; S.level = 0; }

function framedPhoto(dataUrl) { // gold frame, maroon mount, marigold toran: all chunky pixels
  const c = document.createElement("canvas"), g = c.getContext("2d"), img = new Image();
  img.onload = () => {
    const scale = Math.min(220 / img.width, 220 / img.height), iw = img.width * scale, ih = img.height * scale;
    const b = 20, top = 26, w = iw + 2 * b, h = ih + 2 * b;
    c.width = w; c.height = h + top;
    const rect = (x, y, rw, rh, col) => { g.fillStyle = col; g.fillRect(x, y, rw, rh); };
    rect(0, top, w, h, "#5a2d0c"); rect(6, top + 6, w - 12, h - 12, "#d4af37"); rect(14, top + 14, w - 28, h - 28, "#7a1010");
    for (let x = 10; x < w - 10; x += 16) { rect(x, top + 8, 4, 4, "#fff1a8"); rect(x, top + h - 12, 4, 4, "#fff1a8"); }
    g.drawImage(img, b, top + b, iw, ih);
    for (let i = 0, x = 0; x < w; i++, x += 12) {
      rect(x, 8, 12, 12, i % 2 ? "#ff8c00" : "#ffc300");
      if (i % 3 === 1) rect(x + 3, 20, 6, 12, "#2e8b3a");
    }
  };
  img.src = dataUrl;
  c.className = "face";
  return c;
}

function showOverlay(level) {
  S.level = level;
  const [header, color] = HEADERS[level];
  const [c, left, right] = card(color);
  if (level === 2 && S.face) {
    left.append(framedPhoto(S.face), el("div", "pix", `<span style="font-size:24px;color:#ffc300">DISAPPOINTED HAIN<br>TUJHSE.</span>`));
  } else left.append(sprite(GUARD, 10));
  right.innerHTML = `<div class="small">C H O D B A K</div><h2 style="color:${color}">${header}</h2>
    <div class="meta">WARNING ${level}/3 &gt; you left the duty post</div>
    <div class="meta">LOG KYA KAHENGE? aaj ${S.today} baar bhaage.</div>
    <div class="meta hostage" style="color:#e83b3b"></div>
    <div class="body">...</div><div class="catch" style="color:${color}">CHODI MAT KAR!</div><div class="row"></div>`;
  renderHostage();
  const row = right.querySelector(".row");
  if (level < 3) {
    const ok = el("button", "primary", "JI SIR! WAPAS KAAM PE"); ok.style.background = color;
    ok.onclick = closeOverlay; row.append(ok);
  } else {
    const status = el("div", "pix", 'Bol: "SORRY MUMMY" (only way out)'); status.style.cssText = "font-size:22px;width:100%;color:#aaa";
    row.before(status);
    if (S.key && navigator.mediaDevices?.getUserMedia && window.MediaRecorder) {
      const mic = el("button", "primary", "🎤 BOLO (3 SEC)"); mic.style.background = color;
      mic.onclick = () => listen(mic, status, row); row.append(mic);
    } else typeApology(status, row, 'Type kar: "sorry mummy"');
    c.classList.add("shake");
  }
}
function setBody(text) { const b = $("#overlay .body"); if (b) b.textContent = text; }
function renderHostage() {
  const h = $("#overlay .hostage");
  if (h) h.textContent = S.level >= 2 ? `HOSTAGE: your coding agent > ${HOSTAGE_STATES[S.hostageHp]}` : "";
}

const saidSorryMummy = (t) => /s[oa]+r+[yie]+|सॉरी|सॉरि/i.test(t) && /mumm|mumy|mommy|\bmom\b|mamma|\bmaa?\b|amma|\baai\b|\bbebe\b|\bammi\b|मम्मी/i.test(t);
async function listen(mic, status, row) {
  mic.disabled = true; status.textContent = "SUN RAHA HOON... bol!"; status.style.color = "#7ee081";
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const rec = new MediaRecorder(stream), chunks = [];
    rec.ondataavailable = (e) => chunks.push(e.data);
    const stopped = new Promise((r) => (rec.onstop = r));
    rec.start(); await sleep(3000); rec.stop(); await stopped;
    stream.getTracks().forEach((t) => t.stop());
    const form = new FormData();
    form.append("file", new File(chunks, "sorry.webm", { type: "audio/webm" }));
    form.append("model", "saaras:v3"); form.append("mode", "translit"); form.append("language_code", "unknown");
    const heard = (await sarvam("/speech-to-text", null, form)).transcript || "";
    if (saidSorryMummy(heard)) return forgiven();
    status.textContent = `Suna: "${heard.slice(0, 40)}". ZOR SE! "SORRY MUMMY"`; status.style.color = "#e83b3b";
    sfx("cat_laugh"); $("#overlay .card").classList.remove("shake"); void $("#overlay .card").offsetWidth; $("#overlay .card").classList.add("shake");
    mic.disabled = false;
  } catch {
    mic.remove(); typeApology(status, row, 'Mic nahi mila. Type kar: "sorry mummy"');
  }
}
function typeApology(status, row, msg) {
  status.textContent = msg;
  const input = el("input"); input.placeholder = "sorry mummy"; input.style.maxWidth = "320px";
  input.onkeydown = (e) => { if (e.key === "Enter" && saidSorryMummy(input.value)) forgiven(); };
  row.append(input); setTimeout(() => input.focus(), 50);
}
function forgiven() { // mummy forgives, the strikes reset, the hostage breathes
  S.strikes = 0; S.hostageHp = 0; S.mom = null; closeOverlay(); renderStats(); setStatus("on"); renderPip();
  toast(`<div class="t" style="color:#7ee081">MAAF KIYA.</div><div class="m">Ab chodi mat karna.</div>`, "#7ee081", 5);
}

function toast(html, color, secs) {
  const t = el("div", "toast", html); t.style.borderColor = color;
  $("#toasts").append(t);
  if (secs) setTimeout(() => t.remove(), secs * 1000);
  return t;
}
function familyGossip() { // Rishtedaar alert: fake family WhatsApp group lights up
  const t = toast(`<div><div class="t" style="color:#25d366">FAMILY GROUP (47)</div><div class="m muted">muted? nahi.</div><div class="msgs"></div></div>`, "#25d366");
  [...FAMILY].sort(() => Math.random() - 0.5).slice(0, 4).forEach(([who, msg], i) => setTimeout(() => {
    t.querySelector(".msgs").append(el("div", "wa", `<div class="who">${esc(who)}</div><div class="m">${esc(msg)}</div>`));
    i === 0 ? sfx("ye_le") : beep(880, audio().currentTime, 0.12, "sine", 0.05);
  }, 1500 + i * 1400));
  setTimeout(() => t.remove(), 14000);
}
function callingToast() { // fake call. Mummy is never actually called. Probably.
  const t = toast(`<div style="font-size:40px">📞</div><div><div class="t" style="color:#e83b3b">CALLING MUMMY...</div><div class="m">tring tring...</div></div>`, "#e83b3b", 12);
  ring();
  setTimeout(() => { t.querySelector(".m").textContent = "LINE BUSY. Agli baar pakka."; }, 6500);
}
function chaiToast() {
  toast(`<div style="font-size:40px">☕</div><div><div class="t" style="color:#7ee081">SHABAASH!</div><div class="m">25 min focus. Chai break kamaya.</div></div>`, "#2e8b3a", 10);
  beep(660, audio().currentTime, 0.15, "sine", 0.06); beep(990, audio().currentTime + 0.18, 0.2, "sine", 0.06);
}
function throwChappal() { // a spinning pixel chappal arcs across the whole screen
  const c = sprite(CHAPPAL, 9, false); c.classList.add("chappal"); document.body.append(c);
  const W = innerWidth, H = innerHeight, fromRight = Math.random() < 0.5, t0 = performance.now(), dur = 1100;
  (function frame(now) {
    const t = Math.min(1, (now - t0) / dur);
    const x = -150 + (W + 300) * (fromRight ? 1 - t : t), y = H * 0.65 - Math.sin(t * Math.PI) * H * 0.5;
    c.style.transform = `translate(${x}px, ${y}px) rotate(${t * 1080}deg)`;
    t < 1 ? requestAnimationFrame(frame) : c.remove();
  })(t0);
  beep(180, audio().currentTime + 0.5, 0.15, "square", 0.08);
}

// ---- floating guard (Document Picture-in-Picture: stays on top of other apps; Chrome/Edge) --------
async function floatGuard() {
  if (!("documentPictureInPicture" in window)) {
    toast(`<div><div class="t">NOT HERE</div><div class="m">The floating guard needs Chrome or Edge on desktop.</div></div>`, "#f59342", 6);
    return;
  }
  if (S.pip) return;
  S.pip = await documentPictureInPicture.requestWindow({ width: 280, height: 300 });
  S.pip.document.head.innerHTML = `<style>body{margin:0;font-family:"Nirmala UI",system-ui,sans-serif;color:#f2e8cf;background:#14141c;
    display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;height:100vh;text-align:center;padding:10px;box-sizing:border-box;border:6px solid #7ee081}
    body.alarm{background:#3a0d0d;border-color:#e83b3b} img{image-rendering:pixelated;width:96px} b{font:28px Consolas,monospace;letter-spacing:2px}
    p{margin:0;font-size:13px;font-weight:700;max-height:110px;overflow:auto}</style>`;
  S.pip.addEventListener("pagehide", () => { S.pip = null; });
  renderPip();
}
function renderPip() {
  if (!S.pip) return;
  const alarm = S.away && S.strikes > 0, d = S.pip.document;
  d.body.className = alarm ? "alarm" : "";
  d.body.innerHTML = `<img src="${sprite(GUARD, 6).toDataURL()}" alt=""><b style="color:${alarm ? "#e83b3b" : "#7ee081"}">${
    !S.onDuty ? "OFF DUTY" : alarm ? HEADERS[S.strikes][0] : S.away ? "DEKH RAHA HOON..." : "ON DUTY"}</b>
    <p>${alarm ? esc(S.lastTaunt) + "<br><br>WAPAS AA! Go back to the CHODBAK tab." : S.onDuty ? "Chodi mat kar!" : ""}</p>`;
}

// ---- first run: key, language, photo ----------------------------------------------------------------
function setupKey(next) {
  const [, left, right] = card("#d4af37");
  left.append(sprite(GUARD, 10));
  right.innerHTML = `<div class="small">C H O D B A K</div><h2 style="color:#d4af37">NAYI BHARTI</h2>
    <div class="body" style="font-weight:400;font-size:18px">The havaldar's voice comes from <b>Sarvam AI</b>. Paste your free key from
    <a href="https://dashboard.sarvam.ai" target="_blank" rel="noopener" style="color:#d4af37">dashboard.sarvam.ai</a> → API Keys.
    It's stored only in this browser and sent only to api.sarvam.ai.<br><br>No key? He still shouts pre-recorded taunts in your language.</div>
    <input id="keyIn" type="password" placeholder="sk_..." autocomplete="off"><div class="row"></div>`;
  $("#keyIn").value = S.key || "";
  const save = el("button", "primary", "SAVE"), skip = el("button", "", "SKIP (pre-recorded only)");
  save.onclick = () => { S.key = $("#keyIn").value.trim() || null; store.set("key", S.key); next(); };
  $("#keyIn").onkeydown = (e) => e.key === "Enter" && save.onclick();
  skip.onclick = () => { S.key = null; store.set("key", null); next(); };
  right.querySelector(".row").append(save, skip);
}
function setupLang(next) { // asks innocently; the answer decides which language mummy gets "called" in
  const [, left, right] = card("#d4af37");
  left.append(sprite(GUARD, 10));
  right.innerHTML = `<div class="small">C H O D B A K</div><h2 style="color:#d4af37">NAYI BHARTI</h2>
    <div class="body" style="font-weight:400">Recruit registration.<br><br>Ghar pe kaunsi bhasha bolte ho?</div><div class="grid"></div>`;
  for (const [name, [, , label]] of Object.entries(LANGS)) {
    const b = el("button", "", esc(label));
    if (name === S.lang) b.style.background = "#d4af37";
    b.onclick = () => { S.lang = name; store.set("lang", name); next(); };
    right.querySelector(".grid").append(b);
  }
}
function setupPhoto(next) { // asks for a photo and doesn't say why; it comes back at strike 2
  const [, left, right] = card("#d4af37");
  left.append(sprite(GUARD, 10));
  right.innerHTML = `<div class="small">C H O D B A K</div><h2 style="color:#d4af37">NAYI BHARTI</h2>
    <div class="body" style="font-weight:400">Recruit registration, last step.<br><br>Upload a photo of someone whose opinion matters to you.<br><br>Kyun? Classified. Bas upload kar.
    <br><span class="muted" style="font-size:14px">It stays in this browser.</span></div>
    <input type="file" id="faceIn" accept="image/*" class="hidden"><div class="row"></div>`;
  const choose = el("button", "primary", "PHOTO CHUNO"), later = el("button", "", "BAAD MEIN");
  choose.onclick = () => $("#faceIn").click();
  later.onclick = next;
  $("#faceIn").onchange = () => {
    const f = $("#faceIn").files[0]; if (!f) return;
    const img = new Image();
    img.onload = () => { // shrink to 220px so it fits in localStorage
      const s = Math.min(1, 220 / Math.max(img.width, img.height)), c = document.createElement("canvas");
      c.width = img.width * s; c.height = img.height * s; c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      S.face = c.toDataURL("image/jpeg", 0.85); store.set("face", S.face); URL.revokeObjectURL(img.src); next();
    };
    img.src = URL.createObjectURL(f);
  };
  right.querySelector(".row").append(choose, later);
}
function setup(done) { setupKey(() => setupLang(() => setupPhoto(() => { closeOverlay(); done?.(); }))); }

// ---- duty post: notes / PDF / YouTube ---------------------------------------------------------------
const notes = $("#notes");
notes.value = store.get("notes", "");
notes.oninput = () => store.set("notes", notes.value);
document.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => {
  document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
  notes.classList.toggle("hidden", b.dataset.tab !== "notes");
  $("#pdfPane").classList.toggle("hidden", b.dataset.tab !== "pdf");
  $("#ytPane").classList.toggle("hidden", b.dataset.tab !== "youtube");
}));
$("#pdfFile").onchange = () => {
  const f = $("#pdfFile").files[0]; if (!f) return;
  $("#pdfPane").className = ""; $("#pdfPane").innerHTML = `<iframe title="PDF" src="${URL.createObjectURL(f)}"></iframe>`;
};
$("#ytGo").onclick = () => {
  const id = ($("#ytUrl").value.match(/(?:v=|youtu\.be\/|embed\/|shorts\/|live\/)([\w-]{11})/) || [])[1];
  if (!id) { $("#ytUrl").style.borderColor = "#e83b3b"; return; }
  $("#ytPane").className = "";
  $("#ytPane").innerHTML = `<iframe title="YouTube lecture" src="https://www.youtube-nocookie.com/embed/${id}" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>`;
};

// ---- controls -----------------------------------------------------------------------------------------
function goOnDuty() {
  audio(); // unlock sound now, while we have a click, so it can shout from a background tab later
  if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
  S.onDuty = true; S.away = false; S.goodSince = Date.now(); S.nextChai = S.goodSince + CHAI_EVERY;
  $("#duty").textContent = "OFF DUTY"; $("#duty").classList.remove("primary");
  setStatus("on"); renderPip();
}
$("#duty").onclick = () => {
  if (S.onDuty) {
    S.onDuty = false; clearTimeout(S.awayTimer); S.away = false;
    $("#duty").textContent = "REPORT FOR DUTY"; $("#duty").classList.add("primary");
    setStatus("off"); renderPip(); return;
  }
  S.lang ? goOnDuty() : setup(goOnDuty);
};
$("#pip").onclick = floatGuard;
$("#settings").onclick = () => setup();

// pixel guard as logo + favicon
$("#logo").getContext("2d").drawImage(sprite(GUARD, 1), 0, 0);
$("#favicon").href = sprite(GUARD, 4).toDataURL();
renderStats();
if (!S.lang) setup();
// ?test=1|2|3 previews a strike (handy for screenshots)
const testLevel = +new URLSearchParams(location.search).get("test");
if (testLevel >= 1 && testLevel <= 3 && S.lang) { S.strikes = testLevel - 1; S.onDuty = true; S.away = true; strike(); }
