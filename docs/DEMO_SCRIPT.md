# Demo script (3 minutes)

Before the pitch, open `dashboard/index.html` and `dashboard/alert.html` side by side (no server or
internet needed) and pick the run **bbr / design_storm_PLACEHOLDER / seed 1**.

> Say it out loud once: **"The storm is a synthetic design storm and some inputs are placeholders.
> The map, roads, buildings and terrain are real."** The dashboard stamps this too.

| Time | Screen | Say / do |
|---|---|---|
| 0:00 | Map, minute 0 | "This is Bandar Bukit Raja: real OpenStreetMap roads and 3,100 homes on 30 m Copernicus terrain. A 3-hour, 139 mm storm is starting." |
| 0:20 | Play at 30× | Drains fill, sensors at the low points turn green → orange, streets go to **WATCH**. |
| 0:50 | Minute ~93 | S3 fires **ACT** on **Persiaran Setia Prima**, 16 min before it reaches 0.3 m. Switch to the phone: *"Move your car to High ground (27.8 m) now."* Ask a judge to press **"I moved my car"**; the counter on the map ticks up. |
| 1:20 | Map | Cars drive to the safe zones (green crosses; most are *assumed* car parks, labelled synthetic). The street hits 0.3 m. |
| 1:50 | Split S0 \| S3 | Same moment, no alerts vs street sensors: in S0 the car on Persiaran Setia Prima is under water; in S3 it moved. Show the KPIs: in this run 61% of at-risk cars reach safety with S3 vs 50% with no alerts. |
| 2:30 | Close | "Structural works take years. A message takes seconds." |

These are single-run numbers (one random seed), not Monte Carlo averages. Do not show `results.html`
in the BBR demo: it still holds toy-world charts until a BBR sweep is run
(`python -m ffsa.cli --allow-placeholders sweep --world bbr --config config/sweeps/bbr.yaml -n 30 --jobs 2`).

## Honest answers for likely questions

- **"Does it reproduce the real floods?"** Not yet. With the synthetic storm, the Jalan Makyong
  sections peak at 0.22 m, below the 0.3 m threshold, so we report 0 of 20 hits (`docs/VALIDATION.md`).
  The next step is a real rainfall record (GPM IMERG or JPS gauges).
- **"Where do the numbers come from?"** Every parameter is in `docs/ASSUMPTIONS.md` with a source or
  a stated assumption; placeholders are listed at the top.
- **"Why so many false alarms?"** About 88% of streets that get ACT do not reach 0.3 m. Heavy rain
  alone satisfies the confirmation rule; a street-specific threshold is future work. We have not
  tuned it away.
