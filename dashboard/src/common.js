/* Shared helpers for the dashboard pages. Classic script (no modules) so pages work from file://. */
(function () {
  const FF = (window.FF = {});

  FF.LEVEL_NAMES = ["NONE", "WATCH", "ACT", "AVOID", "ALL_CLEAR"];
  FF.LEVEL_COLORS = {
    0: [120, 130, 145, 200],
    1: [234, 196, 53, 255],   // WATCH yellow
    2: [240, 128, 30, 255],   // ACT orange
    3: [214, 40, 57, 255],    // AVOID red
    4: [46, 160, 90, 255],    // ALL CLEAR green
  };
  FF.OUTCOME_COLORS = {
    parked: [150, 150, 160],
    waiting: [200, 200, 210],
    driving: [255, 255, 255],
    safe: [46, 180, 100],
    flooded: [214, 40, 57],
    stranded: [180, 100, 200],
  };

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = resolve;
      s.onerror = () => reject(new Error("Could not load " + src));
      document.head.appendChild(s);
    });
  }

  async function gunzipB64(b64) {
    const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const stream = new Blob([bin]).stream().pipeThrough(new DecompressionStream("gzip"));
    return new Uint8Array(await new Response(stream).arrayBuffer());
  }

  FF.runIndex = () => window.FFSA_RUN_INDEX || [];

  FF.loadRun = async function (runId) {
    window.FFSA_RUNS = window.FFSA_RUNS || {};
    if (!window.FFSA_RUNS[runId]) await loadScript(`public/runs/${runId}/bundle.js`);
    const run = window.FFSA_RUNS[runId];
    if (!run.depth) run.depth = await gunzipB64(run.depth_gz_b64);
    return run;
  };

  FF.clockLabel = function (meta, t) {
    const start = new Date(meta.start_local);
    const d = new Date(start.getTime() + t * 60000);
    // show the local (UTC+8) wall clock regardless of the viewer's timezone
    const local = new Date(d.getTime() + 8 * 3600000);
    const hh = String(local.getUTCHours()).padStart(2, "0");
    const mm = String(local.getUTCMinutes()).padStart(2, "0");
    return `${hh}:${mm}`;
  };

  /* Position of a car at time t, and its status. */
  FF.carState = function (car, t) {
    if (car.t_flooded != null && t >= car.t_flooded) return { status: "flooded", pos: FF.carPos(car, car.t_flooded) };
    if (car.t_safe != null && t >= car.t_safe) return { status: "safe", pos: FF.carPos(car, t) };
    const p = car.path;
    if (!p.length || t < p[0][2]) return { status: "parked", pos: car.home };
    const last = p[p.length - 1];
    if (t >= last[2]) return { status: car.outcome === "stranded_dry" ? "stranded" : "driving", pos: [last[0], last[1]] };
    return { status: "driving", pos: FF.carPos(car, t) };
  };

  FF.carPos = function (car, t) {
    const p = car.path;
    if (!p.length || t <= p[0][2]) return car.home;
    for (let i = 1; i < p.length; i++) {
      if (t <= p[i][2]) {
        const a = p[i - 1], b = p[i];
        const f = b[2] > a[2] ? (t - a[2]) / (b[2] - a[2]) : 1;
        return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
      }
    }
    const l = p[p.length - 1];
    return [l[0], l[1]];
  };

  /* Water depth frame -> RGBA ImageData. 0.15 m and 0.3 m bands are visibly distinct. */
  FF.depthImage = function (run, t) {
    const { H, W } = run.meta.grid;
    const off = t * H * W;
    const img = new ImageData(W, H);
    const px = img.data;
    const d = run.depth;
    for (let i = 0; i < H * W; i++) {
      const cm = d[off + i];
      const j = i * 4;
      if (cm < 5) { px[j + 3] = 0; continue; }
      if (cm < 15) {            // shallow: light blue, alpha grows with depth
        px[j] = 120; px[j + 1] = 190; px[j + 2] = 245; px[j + 3] = 40 + cm * 10;
      } else if (cm < 30) {     // >= 0.15 m: AVOID band
        px[j] = 40; px[j + 1] = 120; px[j + 2] = 230; px[j + 3] = 200;
      } else {                  // >= 0.3 m: cars float
        px[j] = 25; px[j + 1] = 40; px[j + 2] = 150; px[j + 3] = 230;
      }
    }
    return img;
  };

  FF.fmt = function (v, digits = 0, suffix = "") {
    if (v == null || Number.isNaN(v)) return "–";
    return Number(v).toFixed(digits) + suffix;
  };

  FF.rm = function (v) {
    if (v == null || Number.isNaN(v)) return "–";
    if (v >= 1e6) return "RM" + (v / 1e6).toFixed(2) + "m";
    if (v >= 1e3) return "RM" + Math.round(v / 1e3) + "k";
    return "RM" + Math.round(v);
  };

  /* "I moved my car" presses made by people on alert.html, shared across open pages. */
  FF.PRESS_KEY = "ffsa-live-presses";
  FF.livePresses = function () {
    try { return Number(localStorage.getItem(FF.PRESS_KEY) || 0); } catch (e) { return 0; }
  };
  FF.channel = "BroadcastChannel" in window ? new BroadcastChannel("ffsa") : null;
})();
