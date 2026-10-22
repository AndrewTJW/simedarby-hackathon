/* Phone mock-up: shows the alerts one resident's street receives, at simulation time. */
(function () {
  const $ = (id) => document.getElementById(id);
  const S = { run: null, scenario: "S3", street: null, t: 0, lang: "en", playing: false, acc: 0, last: 0, pressedFor: new Set() };
  const UI = {
    en: { moved: "I moved my car", done: "Thanks, noted ✓", left: "min left", bm: "Bahasa Melayu", flooded: "Flooding expected now" },
    bm: { moved: "Saya sudah alihkan kereta", done: "Terima kasih, direkod ✓", left: "minit lagi", bm: "English", flooded: "Banjir dijangka sekarang" },
  };

  function init() {
    const idx = FF.runIndex();
    if (!idx.length) { $("chat").innerHTML = '<div class="msg">No runs exported yet.</div>'; return; }
    $("run").innerHTML = idx.map((r) => `<option>${r.run_id}</option>`).join("");
    $("run").onchange = () => loadRun($("run").value);
    $("scenario").onchange = () => { S.scenario = $("scenario").value; fillStreets(); render(true); };
    $("street").onchange = () => { S.street = Number($("street").value); render(true); };
    $("lang").onclick = () => { S.lang = S.lang === "en" ? "bm" : "en"; $("lang").textContent = UI[S.lang].bm; render(true); };
    $("play").onclick = () => { S.playing = !S.playing; $("play").textContent = S.playing ? "Pause" : "Play"; };
    $("scrub").oninput = () => setTime(Number($("scrub").value));
    $("reset").onclick = () => { try { localStorage.setItem(FF.PRESS_KEY, "0"); } catch (e) {} S.pressedFor.clear(); updatePresses(); render(true); };
    window.addEventListener("storage", (e) => { if (e.key === FF.PRESS_KEY) updatePresses(); });
    if (FF.channel) FF.channel.onmessage = (e) => {
      const d = e.data;
      if (d && d.type === "clock" && $("sync").checked && S.run && d.run === S.run.meta.run_id) {
        if (d.scenario !== S.scenario && S.run.meta.scenarios.includes(d.scenario)) {
          S.scenario = d.scenario; $("scenario").value = d.scenario; fillStreets();
        }
        setTime(d.t);
      }
      if (d && d.type === "press") updatePresses();
    };
    updatePresses();
    loadRun(new URLSearchParams(location.search).get("run") || idx[0].run_id);
    requestAnimationFrame(tick);
  }

  async function loadRun(id) {
    S.run = await FF.loadRun(id);
    $("run").value = id;
    const m = S.run.meta;
    $("scenario").innerHTML = m.scenarios.filter((s) => s !== "S0").map((s) => `<option>${s}</option>`).join("");
    S.scenario = m.scenarios.includes("S3") ? "S3" : m.scenarios[m.scenarios.length - 1];
    $("scenario").value = S.scenario;
    $("scrub").max = m.grid.T - 1;
    const b = [];
    if (m.world_synthetic) b.push('<span class="badge">Toy world (synthetic)</span>');
    if (m.storm_synthetic) b.push(`<span class="badge">${m.storm.includes("design") ? "Synthetic design storm" : "Synthetic storm"}</span>`);
    $("badges").innerHTML = b.join(" ");
    fillStreets();
    setTime(0);
  }

  function fillStreets() {
    const sc = S.run.scenarios[S.scenario];
    const streets = S.run.geo.streets.features.map((f) => f.properties);
    // streets that get an ACT first, ordered by number of cars told to move; default = the biggest
    const acts = {};
    sc.events.forEach((e) => { if (e.level === "ACT" && e.street >= 0) acts[e.street] = Math.max(acts[e.street] || 0, e.n_recipients); });
    const named = new URLSearchParams(location.search).get("street");
    const order = streets.slice().sort((a, b) => (acts[b.id] || -1) - (acts[a.id] || -1));
    $("street").innerHTML = order.map((s) => `<option value="${s.id}">${s.name}${acts[s.id] != null ? "" : " (no ACT)"}</option>`).join("");
    const pick = streets.find((s) => named && s.name.toLowerCase() === named.toLowerCase());
    S.street = pick ? pick.id : order[0].id;
    $("street").value = S.street;
  }

  function setTime(t) {
    S.t = Math.max(0, Math.min(S.run.meta.grid.T - 1, t));
    $("scrub").value = Math.floor(S.t);
    render(false);
  }

  function tick(now) {
    const dt = S.last ? (now - S.last) / 1000 : 0;
    S.last = now;
    if (S.playing && S.run) setTime(S.t + dt * 0.5); // standalone: 30× real time
    requestAnimationFrame(tick);
  }

  let shown = "";
  function render(force) {
    const run = S.run, m = run.meta, t = S.t;
    $("clock").textContent = `${FF.clockLabel(m, Math.floor(t))} · min ${Math.floor(t)}`;
    const name = run.geo.streets.features[S.street].properties.name;
    $("botSub").textContent = `bot · subscribed: ${name}`;
    const evs = run.scenarios[S.scenario].events.filter((e) => e.t <= t && (e.street === S.street));
    const key = evs.map((e) => e.t + e.level).join("|") + S.lang + [...S.pressedFor].join(",");
    if (force || key !== shown) {
      shown = key;
      $("chat").innerHTML = evs.map((e, i) => bubble(e, i)).join("") ||
        `<div class="msg"><div class="lv">${S.lang === "en" ? "SUBSCRIBED" : "LANGGANAN"}</div>` +
        `${S.lang === "en" ? "You will get flood alerts for" : "Anda akan menerima amaran banjir untuk"} ${name}.</div>`;
      $("chat").querySelectorAll("button.moved").forEach((b) => (b.onclick = () => press(b)));
      $("chat").scrollTop = $("chat").scrollHeight;
    }
    $("chat").querySelectorAll(".count").forEach((el) => {
      const left = Number(el.dataset.mins) - (t - Number(el.dataset.t));
      el.textContent = left > 0 ? `${Math.floor(left)}:${String(Math.floor((left % 1) * 60)).padStart(2, "0")} ${UI[S.lang].left}` : UI[S.lang].flooded;
    });
  }

  function bubble(e, i) {
    const u = UI[S.lang];
    const text = S.lang === "en" ? e.text_en : e.text_bm;
    const id = `${e.t}-${e.street}`;
    let extra = "";
    if (e.level === "ACT") {
      if (e.minutes != null) extra += `<div class="count" data-mins="${e.minutes}" data-t="${e.t}"></div>`;
      const done = S.pressedFor.has(id);
      extra += `<button class="moved" data-id="${id}" ${done ? "disabled" : ""}>${done ? u.done : u.moved}</button>`;
    }
    return `<div class="msg ${e.level}"><div class="lv">${e.level.replace("_", " ")}</div>${text}${extra}` +
      `<div class="tm">${FF.clockLabel(S.run.meta, e.t)}</div></div>`;
  }

  function press(btn) {
    S.pressedFor.add(btn.dataset.id);
    let n = FF.livePresses() + 1;
    try { localStorage.setItem(FF.PRESS_KEY, String(n)); } catch (e) {}
    if (FF.channel) FF.channel.postMessage({ type: "press", n });
    updatePresses();
    render(true);
  }

  function updatePresses() { $("presses").textContent = FF.livePresses(); }

  init();
})();
