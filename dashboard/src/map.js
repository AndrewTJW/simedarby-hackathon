/* Map replay page: water, streets by alert level, sensors, cars; play controls, KPIs, split view. */
(function () {
  const $ = (id) => document.getElementById(id);
  const S = {
    run: null, scenario: "S3", t: 0, playing: false, speed: 30, split: false, basemap: false,
    sensor: null, decks: {}, viewState: null, streetPaths: null, lastFrame: 0, acc: 0,
  };

  // ---------- setup -------------------------------------------------------------------------
  function init() {
    const idx = FF.runIndex();
    if (!idx.length) {
      $("feed").innerHTML = "<li>No runs exported yet. Run <code>python -m ffsa.cli --allow-placeholders sim</code>.</li>";
      return;
    }
    $("run").innerHTML = idx.map((r) => `<option value="${r.run_id}">${r.run_id}</option>`).join("");
    const want = new URLSearchParams(location.search).get("run");
    if (want && idx.some((r) => r.run_id === want)) $("run").value = want;
    $("run").onchange = () => loadRun($("run").value);
    $("play").onclick = () => setPlaying(!S.playing);
    $("speed").onchange = () => (S.speed = Number($("speed").value));
    $("scrub").oninput = () => setTime(Number($("scrub").value));
    $("scenario").onchange = () => { S.scenario = $("scenario").value; render(); };
    $("split").onchange = () => setSplit($("split").checked);
    $("basemap").onchange = () => { S.basemap = $("basemap").checked; render(); };
    window.addEventListener("storage", (e) => { if (e.key === FF.PRESS_KEY) render(); });
    if (FF.channel) FF.channel.onmessage = (e) => { if (e.data && e.data.type === "press") render(); };
    document.addEventListener("keydown", (e) => {
      if (e.target.tagName === "INPUT" && e.target.type !== "range") return;
      if (e.code === "Space") { e.preventDefault(); setPlaying(!S.playing); }
    });
    loadRun($("run").value);
    requestAnimationFrame(tick);
  }

  async function loadRun(id) {
    setPlaying(false);
    const run = await FF.loadRun(id);
    S.run = run;
    const m = run.meta;
    $("scenario").innerHTML = m.scenarios.map((s) => `<option>${s}</option>`).join("");
    S.scenario = m.scenarios.includes("S3") ? "S3" : m.scenarios[m.scenarios.length - 1];
    $("scenario").value = S.scenario;
    $("scrub").max = m.grid.T - 1;
    $("split").disabled = !(m.scenarios.includes("S0") && m.scenarios.includes("S3"));
    $("basemap").disabled = m.world_synthetic;
    $("basemap").parentElement.title = m.world_synthetic ? "The toy world is not a real place" : "";
    const b = [];
    if (m.world_synthetic) b.push('<span class="badge">Toy world (synthetic)</span>');
    if (m.storm_synthetic) b.push(`<span class="badge">${m.storm.includes("design") ? "Synthetic design storm" : "Synthetic storm"}</span>`);
    if (m.placeholders && m.placeholders.length) b.push(`<span class="badge" title="${m.placeholders.join(", ")}">PLACEHOLDER VALUES</span>`);
    b.push(`<span class="badge info">${m.n_sensors} sensors · compliance ${Math.round(m.compliance * 100)}% · seed ${m.seed}</span>`);
    $("badges").innerHTML = b.join(" ");
    S.streetPaths = run.geo.streets.features.flatMap((f) =>
      f.geometry.coordinates.map((path) => ({ path, id: f.properties.id, name: f.properties.name })));
    S.sensor = null;
    $("spark").hidden = true;
    $("sensorInfo").textContent = "Click a sensor dot on the map.";
    S.viewState = fitView(m.bounds);
    for (const k of Object.keys(S.decks)) { S.decks[k].finalize(); delete S.decks[k]; }
    setTime(0);
  }

  function fitView(bounds) {
    const el = $("mapA");
    const vp = new deck.WebMercatorViewport({ width: el.clientWidth || 800, height: el.clientHeight || 600 });
    const { longitude, latitude, zoom } = vp.fitBounds([[bounds[0], bounds[1]], [bounds[2], bounds[3]]], { padding: 30 });
    return { longitude, latitude, zoom, pitch: 0, bearing: 0 };
  }

  function getDeck(key, el) {
    if (!S.decks[key]) {
      S.decks[key] = new deck.Deck({
        parent: el, viewState: S.viewState, controller: true,
        onViewStateChange: ({ viewState }) => { S.viewState = viewState; render(); },
        getTooltip: tooltip,
        onClick: (info) => { if (info.layer && info.layer.id.startsWith("sensors")) selectSensor(info.object.properties.id); },
      });
    }
    return S.decks[key];
  }

  function tooltip({ object, layer }) {
    if (!object || !layer) return null;
    const t = S.t;
    if (layer.id.startsWith("streets")) {
      const sc = S.run.scenarios[layerScenario(layer.id)];
      const lvl = sc.timeline[t].street_level[object.id];
      return `${object.name}\n${FF.LEVEL_NAMES[lvl]}`;
    }
    if (layer.id.startsWith("sensors")) return `Sensor ${object.properties.id} (${object.properties.kind})`;
    if (layer.id.startsWith("safe")) return `Safe car park: ${object.properties.name}`;
    return null;
  }
  const layerScenario = (id) => id.split(":")[1];

  // ---------- time --------------------------------------------------------------------------
  function setPlaying(p) {
    S.playing = p;
    $("play").textContent = p ? "Pause" : "Play";
  }
  function setTime(t) {
    if (!S.run) return;
    S.t = Math.max(0, Math.min(S.run.meta.grid.T - 1, Math.round(t)));
    $("scrub").value = S.t;
    if (FF.channel) FF.channel.postMessage({ type: "clock", run: S.run.meta.run_id, scenario: S.scenario, t: S.t });
    render();
  }
  function tick(now) {
    const dt = S.lastFrame ? (now - S.lastFrame) / 1000 : 0;
    S.lastFrame = now;
    if (S.playing && S.run) {
      S.acc += (dt * S.speed) / 60; // speed× real time, in simulated minutes
      if (S.acc >= 1) {
        const step = Math.floor(S.acc);
        S.acc -= step;
        if (S.t + step >= S.run.meta.grid.T - 1) setPlaying(false);
        setTime(S.t + step);
      }
    }
    requestAnimationFrame(tick);
  }
  function setSplit(on) {
    S.split = on;
    $("wrapB").hidden = !on;
    $("maps").classList.toggle("split", on);
    if (!on && S.decks.B) { S.decks.B.finalize(); delete S.decks.B; }
    S.viewState = fitView(S.run.meta.bounds); // the map just changed width
    render();
  }

  // ---------- layers ------------------------------------------------------------------------
  function layers(scName) {
    const run = S.run, t = S.t, m = run.meta;
    const sc = run.scenarios[scName];
    const tl = sc.timeline[t];
    const L = [];
    if (S.basemap && !m.world_synthetic) {
      L.push(new deck.TileLayer({
        id: "basemap:" + scName,
        data: "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        minZoom: 0, maxZoom: 19, tileSize: 256,
        renderSubLayers: (props) => {
          const { west, south, east, north } = props.tile.bbox;
          return new deck.BitmapLayer(props, { data: null, image: props.data, bounds: [west, south, east, north] });
        },
      }));
    }
    L.push(new deck.GeoJsonLayer({
      id: "buildings:" + scName, data: run.geo.buildings, filled: true, stroked: false,
      getFillColor: [150, 156, 168, 110],
    }));
    L.push(new deck.BitmapLayer({
      id: "water:" + scName, image: FF.depthImage(run, t), bounds: m.bounds,
      textureParameters: { minFilter: "nearest", magFilter: "nearest" },
    }));
    L.push(new deck.PathLayer({
      id: "streets:" + scName, data: S.streetPaths, pickable: true, widthUnits: "pixels",
      getPath: (d) => d.path, getWidth: (d) => (tl.street_level[d.id] > 0 ? 5 : 3),
      getColor: (d) => FF.LEVEL_COLORS[tl.street_level[d.id]],
      updateTriggers: { getColor: [t, scName], getWidth: [t, scName] },
    }));
    L.push(new deck.TripsLayer({
      id: "trips:" + scName, data: sc.cars.filter((c) => c.path.length > 1),
      getPath: (c) => c.path.map((p) => [p[0], p[1]]), getTimestamps: (c) => c.path.map((p) => p[2]),
      getColor: [255, 255, 255], widthMinPixels: 2, trailLength: 8, currentTime: t, fadeTrail: true,
    }));
    const cars = sc.cars.map((c) => FF.carState(c, t));
    L.push(new deck.ScatterplotLayer({
      id: "cars:" + scName, data: cars, radiusUnits: "pixels", getRadius: 3.5, stroked: true, lineWidthMinPixels: 0.5,
      getLineColor: [30, 30, 30], getPosition: (d) => d.pos, getFillColor: (d) => FF.OUTCOME_COLORS[d.status],
      updateTriggers: { getPosition: t, getFillColor: t },
    }));
    const lvl = tl.sensor_level, depth = m.thresholds.drain_depth_m;
    L.push(new deck.ScatterplotLayer({
      id: "sensors:" + scName, data: run.geo.sensors.features, pickable: true, radiusUnits: "pixels",
      getRadius: (f) => (S.sensor === f.properties.id ? 9 : 7), stroked: true, lineWidthMinPixels: 2,
      getLineColor: [20, 20, 20], getPosition: (f) => f.geometry.coordinates,
      getFillColor: (f) => sensorColor(lvl[f.properties.id], depth),
      updateTriggers: { getFillColor: [t, scName], getRadius: S.sensor },
    }));
    L.push(new deck.ScatterplotLayer({
      id: "safe:" + scName, data: run.geo.safe_zones.features, pickable: true, radiusUnits: "pixels", getRadius: 11,
      getPosition: (f) => f.geometry.coordinates, getFillColor: [46, 160, 90], stroked: true, getLineColor: [255, 255, 255],
      lineWidthMinPixels: 2,
    }));
    L.push(new deck.TextLayer({
      id: "safeP:" + scName, data: run.geo.safe_zones.features, getPosition: (f) => f.geometry.coordinates,
      getText: () => "P", getSize: 14, getColor: [255, 255, 255], fontWeight: 700,
    }));
    return L;
  }

  function sensorColor(level, depth) {
    if (level == null) return [120, 120, 120];
    const f = Math.min(1.3, level / depth);
    if (f < 0.5) return [60, 170, 90];
    if (f < 0.8) return [234, 196, 53];
    if (f < 1.0) return [240, 128, 30];
    return [214, 40, 57];
  }

  // ---------- panel -------------------------------------------------------------------------
  function kpis(scName) {
    const run = S.run, t = S.t, m = run.meta, sc = run.scenarios[scName];
    const tl = sc.timeline[t];
    const atRisk = sc.summary.n_cars_at_risk;
    const scale = sc.summary.car_scale || 1;
    const leads = [];
    run.geo.streets.features.forEach((f) => {
      const tf = f.properties.t_flood;
      if (tf != null && tf <= t) leads.push(sc.street_lead[f.properties.id]);
    });
    const valid = leads.filter((v) => v != null && v >= 0).sort((a, b) => a - b);
    const median = valid.length ? valid[Math.floor((valid.length - 1) / 2)] : null;
    const missed = leads.length - valid.length;
    const avoided = m.per_car_rm != null ? tl.cars_moved_at_risk * m.per_car_rm * scale : null;
    return { tl, atRisk, median, missed, nFlooded: leads.length, avoided, live: FF.livePresses() };
  }

  function renderPanel() {
    const run = S.run, t = S.t, m = run.meta;
    const a = kpis(S.split ? "S3" : S.scenario);
    const b = S.split ? kpis("S0") : null;
    const cmp = (va, vb) => (b ? `${va} <small>vs S0 ${vb}</small>` : va);
    const ph = m.placeholders && m.placeholders.includes("damage.per_car_rm") ? " (placeholder)" : "";
    $("clock").textContent = `${FF.clockLabel(m, t)} · min ${t}`;
    $("kpis").innerHTML = [
      ["Rain now", FF.fmt(m.rain[t], 0, " mm/h")],
      ["Streets on ACT/AVOID", cmp(a.tl.streets_act, b && b.tl.streets_act)],
      ["Median lead time so far", cmp(FF.fmt(a.median, 0, " min"), b && FF.fmt(b.median, 0, " min"))],
      ["Flooded streets missed", cmp(`${a.missed}/${a.nFlooded}`, b && `${b.missed}/${b.nFlooded}`)],
      ["At-risk cars moved", cmp(`${a.tl.cars_moved_at_risk}/${a.atRisk}`, b && `${b.tl.cars_moved_at_risk}/${b.atRisk}`)],
      ["Cars flooded", cmp(a.tl.cars_flooded, b && b.tl.cars_flooded)],
      ["“I moved my car” presses", `${a.tl.presses}${a.live ? ` <small>+${a.live} live</small>` : ""}`],
      ["RM avoided" + ph, cmp(FF.rm(a.avoided), b && FF.rm(b.avoided))],
    ].map(([l, v]) => `<div class="kpi${b ? " compare" : ""}"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");

    const evs = run.scenarios[S.split ? "S3" : S.scenario].events.filter((e) => e.t <= t);
    $("feed").innerHTML = evs.slice(-40).reverse().map((e) =>
      `<li class="${e.level}"><span class="t">${FF.clockLabel(m, e.t)}</span><b>${e.level}</b> ${e.street_name}` +
      ` <span class="muted">(${e.n_recipients} cars)</span><br>${e.text_en}</li>`).join("") ||
      '<li class="muted">No alerts yet.</li>';
    if (S.sensor != null) drawSpark();
  }

  function selectSensor(id) {
    S.sensor = id;
    $("spark").hidden = false;
    render();
  }

  function drawSpark() {
    const run = S.run, sc = run.scenarios[S.split ? "S3" : S.scenario], id = S.sensor;
    const depth = run.meta.thresholds.drain_depth_m, crit = depth + run.meta.thresholds.car_float_m;
    const c = $("spark"), g = c.getContext("2d"), W = c.width, H = c.height, T = sc.timeline.length;
    const ink = getComputedStyle(document.body).color;
    g.clearRect(0, 0, W, H);
    const y = (v) => H - 10 - (Math.min(v, crit * 1.15) / (crit * 1.15)) * (H - 20);
    const x = (t) => (t / (T - 1)) * W;
    g.strokeStyle = "rgba(214,40,57,.6)"; g.setLineDash([5, 4]);
    g.beginPath(); g.moveTo(0, y(crit)); g.lineTo(W, y(crit)); g.stroke();
    g.strokeStyle = "rgba(128,128,128,.6)";
    g.beginPath(); g.moveTo(0, y(depth)); g.lineTo(W, y(depth)); g.stroke(); g.setLineDash([]);
    g.strokeStyle = "#1f6feb"; g.lineWidth = 2; g.beginPath();
    let started = false;
    sc.timeline.forEach((r, t) => {
      const v = r.sensor_level[id];
      if (v == null) return;
      started ? g.lineTo(x(t), y(v)) : g.moveTo(x(t), y(v));
      started = true;
    });
    g.stroke();
    g.strokeStyle = ink; g.lineWidth = 1; g.beginPath(); g.moveTo(x(S.t), 0); g.lineTo(x(S.t), H); g.stroke();
    const r = sc.timeline[S.t];
    const lv = r.sensor_level[id], ttf = r.sensor_ttf[id];
    const served = run.geo.streets.features.filter((f) => f.properties.sensors.includes(id)).map((f) => f.properties.name);
    $("sensorInfo").innerHTML = `<b>Sensor ${id}</b> · level ${FF.fmt(lv, 2, " m")} ` +
      `(${FF.fmt(lv != null ? (100 * Math.min(lv, depth)) / depth : null, 0, "% full")}) · TTF ${ttf == null ? "–" : FF.fmt(ttf, 0, " min")}` +
      `<br><span class="muted">Serves: ${served.join(", ") || "no streets"}. Dashed: drain top, flood level (+0.3 m).</span>`;
  }

  // ---------- render ------------------------------------------------------------------------
  function render() {
    if (!S.run) return;
    const left = S.split ? "S0" : S.scenario;
    $("labelA").textContent = left + scenarioTitle(left);
    getDeck("A", $("mapA")).setProps({ viewState: S.viewState, layers: layers(left) });
    if (S.split) {
      $("labelB").textContent = "S3" + scenarioTitle("S3");
      getDeck("B", $("mapB")).setProps({ viewState: S.viewState, layers: layers("S3") });
    }
    renderPanel();
  }
  const scenarioTitle = (s) => ({ S0: " · no alerts", S1: " · river-style broadcast", S2: " · street sensors, fixed threshold",
    S3: " · street sensors + rate of rise" })[s] || "";

  init();
})();
