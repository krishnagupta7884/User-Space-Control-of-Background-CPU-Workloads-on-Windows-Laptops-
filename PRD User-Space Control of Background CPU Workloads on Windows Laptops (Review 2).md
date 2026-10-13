# PRD: User-Space Control of Background CPU Workloads on Windows Laptops (Review 2)

Oct 13, 2026 · @Krishna

This PRD defines an empirical study of what process priority, Windows Efficiency Mode and a latency-feedback controller can and cannot fix when a background job slows foreground work on Windows laptops. Review 2 is due 13 Oct 2026; the final submission is due 27 Oct 2026.

> **Use note:** Planning document only; nothing here is a result. Write your report, paper and slides yourselves, in your own words, and report only results from your own runs. Any value marked *initial* is a starting point to confirm in pilot runs.

## 1. Project summary

**Working title:** User-Space Control of Background CPU Workloads on Windows Laptops: What Priority, Efficiency Mode and Feedback Can Fix. An Empirical Study.

**Title decision:** Review 1 used a thermal-aware title. This version narrows the claim to what can be measured without special sensors. Confirm the new title and gap with your guide before presenting. If the guide wants 'thermal' kept, use it only for optional supporting telemetry, never as a causal claim.

**Description.** We build a small Python prototype with a fixed foreground benchmark, a repeatable CPU-bound background workload, a logger, a per-laptop baseline calibration and policies that control the background process. We compare no control, static low priority, a Windows Efficiency Mode-style setting (low priority plus EcoQoS) and a controller that adjusts priority from measured foreground latency. We measure foreground latency (p50, p95) and background completion time on up to two Windows laptops.

**Contribution type:** an empirical study plus a modest implemented controller. We do **not** claim a new scheduling algorithm or new thermal management.

## 2. Problem statement

When CPU-heavy background work runs beside a foreground task, the foreground task can slow down. Static low priority addresses competition for CPU time, but it never adapts, and it cannot address effects that priority does not control, such as processor power behaviour. Windows 11 already ships Efficiency Mode, which combines low priority with EcoQoS; Microsoft reports large responsiveness gains in its own tests. It is unclear, on ordinary laptops, how much slowdown remains after priority control, whether EcoQoS reduces it further, and whether feedback can win back background throughput without hurting the foreground. This project measures those three things. It does not assume any slowdown is caused by heat, and timing alone will never be described as proof of thermal throttling.

## 3. Goals, non-goals, research questions

### 3.1 Goals

- **G1.** Measure foreground benchmark latency alone and under sustained background load, with no control.
- **G2.** Build a user-space prototype: benchmark, workload, logger, calibrator, policies and analysis scripts.
- **G3.** Compare policies P0 to P3 (Section 8.2) on foreground p50/p95 latency and background completion time.
- **G4.** Repeat the protocol across runs and, if available, on a second laptop with its own baseline.
- **G5.** Keep configs, raw CSV logs, controller decisions and scripts so every reported number traces to data.

### 3.2 Non-goals

- Kernel code, drivers, or changes to the Windows scheduler or CPU governor.
- A new scheduling algorithm, or claiming to beat published methods tested on other hardware.
- Proving a slowdown is thermal, or separating thermal, frequency and contention effects exactly.
- Real-time guarantees, or a general tool that watches arbitrary applications. The foreground benchmark is a synthetic proxy.

### 3.3 Research questions and hypotheses

Hypotheses are expectations to test, not outcomes to assume.

- **RQ1 (residual slowdown).** How much does sustained background load slow the foreground benchmark, and how much slowdown remains under static low priority? *H1: load slows the foreground; the residual under P1 is smaller but may not be zero.*
- **RQ2 (EcoQoS).** Does adding EcoQoS (P2) reduce the residual compared with priority alone (P1)? *H2: possible, not assumed; either result is reported.*
- **RQ3 (feedback).** Does feedback (P3) recover background throughput relative to P1 while keeping foreground p95 close to P1's? *H3: P3's foreground p95 should sit between P0 and P1; its only possible advantage is shorter background completion time.*
- **RQ4 (cross-machine).** How consistent are the effects on two laptops after per-machine baselines? *H4: normalised results may be comparable, but two machines do not support generalisation.*

## 4. Novelty statement

Background regulation to protect foreground work, thermal-aware throttling, user-level contention control and feedback control of co-running workloads all have prior art, and Windows has a built-in Efficiency Mode. We do not claim these ideas are new. The potential contribution is narrower:

1. A same-hardware measurement of the **residual slowdown** left after priority control on Windows laptops.
2. A comparison of priority-only, priority plus EcoQoS, and latency feedback using one benchmark, one workload and one protocol.
3. A reproducible, driver-free user-space implementation with per-laptop baselines and a limited two-laptop check.

This is a **potential empirical contribution, not a proven novelty claim.** Write 'among the works we reviewed' and list the databases, queries and dates you searched (Google Scholar, IEEE Xplore, ACM DL). Do not claim no prior work exists.

## 5. Related work and positioning

Verify authors, venue and DOI on the publisher page before citing. 'Status' says what was actually read.

| Work | Setting | Idea | Overlap with us | Status |
| --- | --- | --- | --- | --- |
| Park, Lee & Cha, ISLPED 2018 | Mobile | Restricts background apps to protect foreground frame rate | Background regulation | Abstract read |
| Bhat, Gumussoy & Ogras, DATE 2019 | Phone study plus Odroid board | Thermal analysis; migrates power-hungry background work to protect foreground | Closest conceptual overlap; kernel-level, not a laptop | Full text read |
| Abe, Yamada & Kono, EuroSys 2008; IPSJ TACS 2011 | General OS | User-level background control without OS changes; foreground slowdown under 16.9% in their tests | User-space foreground protection | 2011 record read; check the link between the two papers |
| Lo et al., Heracles, ISCA 2015 | Datacenter | Feedback control of best-effort work beside latency-critical service | Feedback regulation | Summaries read |
| Iorga et al., RTAS 2020 | Small Linux boards | Frequency throttling and scaling dominate measured slowdowns; they control or discard them | Shows throttling confounds slowdown measurement | Full text read |
| Sikal et al., DATE 2022 | Many-core | Thermal and cache-contention aware management with ML | Thermal and contention considered together | Abstract and authors read |
| Liu et al., Energy 2022 | Laptop | Model-predictive control under skin-temperature limits | Laptop thermal control | Abstract only; check authors |
| PCCS, MICRO 2021 | SoC | Contention-slowdown model; does not model power or thermal throttling | Contention measurement context | Excerpt only; find full details |
| Microsoft, Task Manager Efficiency Mode (2022 blog) | Windows 11 | Low priority plus EcoQoS; vendor-reported responsiveness gains | **Strongest built-in competitor; our P2 baseline** | Vendor blog read |
| Process Lasso, ProBalance | Windows | Lowers priority of disruptive background processes | Practical competitor | Documentation only |
| Ren et al.; Jeon et al. 2026 (Phoenix) | Unknown | Not checked | Unknown | **Unverified: do not cite** |

**Action:** repair the shifted column headers in the Review 1 literature table, make each 'limitation' specific, and add the missing works above.

## 6. Review 2 requirements map

| # | Requirement | Section | Evidence to bring |
| --- | --- | --- | --- |
| 1 | Detailed methodology | 7, 8 | Methodology slides |
| 2 | Architecture or pipeline diagram | 9 | One drawn diagram |
| 3 | Major module descriptions | 10 | Module table |
| 4 | Workflow diagram per module | 10 | One small flowchart each |
| 5 | Dataset and collection procedure | 11 | CSV schema, sample file |
| 6 | Tools, technologies, algorithms | 12 | Tools table |
| 7 | Experimental plan and metrics | 8, 13 | Conditions, policies, formulas |
| 8 | At least 50% implemented, shown with valid outputs | 14 | Running modules, logs, plots |
| 9 | Challenges and remaining plan | 15 | Risk table, dated plan |

## 7. Methodology

The core is a controlled comparison of a fixed foreground benchmark under different background-control policies.

### 7.1 Foreground benchmark

A fixed, compute-only piece of work (initial: a small integer loop sized in pilots to take a few milliseconds) is run repeatedly in its own process. Each iteration is timed with `time.perf_counter_ns()` and logged with a timestamp. This measures the **effective run time of the benchmark**, not CPU frequency. Initial sampling interval about 200 ms; tune in pilots. Keep the benchmark identical across all policies.

### 7.2 Background workload

A CPU-bound job that does a **fixed amount of work** (so completion times are comparable), plus a timed mode for characterisation. **Use as many worker processes as logical cores** (or pin the foreground and background to the same core); one worker on a multi-core laptop may never compete with the foreground and would hide the effect. Record work completed, elapsed time and process IDs; terminate all workers cleanly at the end or on abort.

### 7.3 Per-laptop baseline calibration

Run the benchmark alone for 30 to 60 seconds and save the median, p95 and variability to `calibration.json`. Recalibrate on each laptop and after configuration changes. Slowdown ratio = recent foreground latency / baseline median (1.0 = baseline). Choose controller thresholds in pilots, then freeze them before final runs.

### 7.4 How data is obtained in user space

User space means we write **no kernel code and no drivers**. We use interfaces Windows exposes to ordinary programs, the same kind Task Manager uses.

| Data | Source | Own driver needed? | Role |
| --- | --- | --- | --- |
| Foreground latency | `time.perf_counter_ns()` around the benchmark | No | Primary signal and metric |
| CPU usage, process priority | `psutil` (Windows process APIs) | No | Logging, P1 and P3 actuation |
| EcoQoS state | Windows process power-throttling API via `ctypes` | No | P2 policy |
| Processor performance, temperature | Performance counters or WMI | No | Optional supporting context; availability, units and accuracy vary, so verify per laptop |
| Reference sensor readings | LibreHardwareMonitor or HWiNFO | Their own driver | Optional cross-check only; label as external |

If a sensor is missing, flat or implausible, write it as blank and do not use it to claim thermal throttling. Do not poll diagnostic counters at the benchmark's rate.

### 7.5 Accuracy across different laptops

No absolute limits such as '75 degrees' are used anywhere. Thresholds are ratios against each laptop's own baseline, the protocol is identical on both laptops, and each laptop gets its own calibration. Results are compared as normalised slowdowns. Normalisation does not make machines equivalent, so the claim is limited to 'tested on two laptops'.

## 8. Experimental plan

### 8.1 Conditions

| Condition | Setup | Purpose |
| --- | --- | --- |
| A: baseline | Foreground alone | Baseline latency and variability |
| B: sustained, no control | Foreground plus sustained background (this is P0) | Size of the slowdown |
| C: policy comparison | Same fixed background work under P0 to P3, separate runs | Compare policies |

### 8.2 Policies

- **P0, uncontrolled:** background at normal priority.
- **P1, static low priority:** background at below-normal for the whole run.
- **P2, static Efficiency Mode style:** below-normal plus EcoQoS on the background process. Needs Windows 11; if unavailable on a laptop, mark P2 'not run' there.
- **P3, latency feedback (our controller):** two states, normal and below-normal.
- **P4, optional ProBalance-style rule:** lower priority when the background's CPU share exceeds a threshold. Only if time allows.

**P3 rule (initial values, tuned in pilots then frozen):** every 1 s compute the median of recent foreground latencies divided by the baseline. If the ratio exceeds 1.15 for 3 consecutive intervals, set below-normal. If it stays below 1.05 for 5 intervals, restore normal. Use a minimum dwell time of 5 s after each change and log every measurement, state and switch. Expect some switching because protecting the foreground removes the signal; count the switches and report them.

### 8.3 Pilot go/no-go gate (do this first)

| Check | Pass condition (initial) | If it fails |
| --- | --- | --- |
| Contention exists | P0 median latency is clearly above baseline (for example 1.2 or more) | Add workers up to the logical core count or pin to the same core; if still none, report it and change the condition |
| Benchmark is stable | Baseline run-to-run variation is small (for example under 5%) | Change loop size or sampling interval; close other apps |
| Priority matters | P1 differs visibly from P0 | Check the priority was actually applied |
| Clean shutdown | No leftover processes after normal and aborted runs | Fix cleanup before any final run |

### 8.4 Controls and confounders

- Same power mode and plugged-in state for all comparable runs; record Windows version, CPU model and whether it has performance and efficiency cores.
- Close other apps; record Windows background activity; do not silently drop runs.
- Same work amount for every policy; rotate or randomise policy order between repetitions.
- Cool-down between sustained runs; record starting temperature only if a sensor is credible.
- Safety: hard flat surface, vents clear, never disable fans or thermal protection, stop if the laptop behaves abnormally.

### 8.5 Run budget (per laptop, initial)

A: 5 runs of about 2 min. C: 4 policies x 5 repetitions x about 5 min plus 3 min cool-down, roughly 2.7 hours; P4 adds about 40 min. Total about 3 hours without P4. Fallback: 3 repetitions, stated in the report.

## 9. Architecture diagram (redraw cleanly, then number and caption it)

```
          +-----------------------------+
          | M6 Experiment runner        |
          | (conditions, policies, reps)|
          +--------------+--------------+
                         |
        +----------------+----------------+
        v                                 v
+---------------+                +----------------+
| M2 Background |                | M3 Foreground  |
| workload      |                | benchmark      |
+-------+-------+                +--------+-------+
        ^ priority / EcoQoS               | latency samples
        |                                 v
+-------+--------+   baseline    +----------------+
| M5 Policy and  |<--------------+ M4 Calibrator  |
| controller     |               +----------------+
+-------+--------+
        | decisions, CPU usage, optional sensors
        v
+---------------+     +---------------------+
| M1 Logger     |---->| Raw CSV and configs |
+---------------+     +----------+----------+
                                 v
                      Analysis: tables and plots
```

## 10. Modules and workflows

Draw one small flowchart per module from its workflow line. A module counts as complete only when its acceptance test passes on real runs.

| Module | Purpose | Workflow | Acceptance test |
| --- | --- | --- | --- |
| M1 Logger | Write timings, CPU use, policy state and events to CSV | Read metrics, timestamp, append row, repeat, flush on stop | Valid CSV with fixed columns; missing sensors are blank, never invented |
| M2 Background workload | Repeatable CPU-bound work | Read config, start N workers, do fixed work, stop on request, record completion | Finishes, stops cleanly, same work every run; no leftover processes |
| M3 Foreground benchmark | Primary responsiveness signal | Load config, run fixed work, time it, wait for next interval, log | Stable baseline; sample count and variance reported |
| M4 Calibrator | Per-laptop baseline | Run alone 30 to 60 s, compute median and p95, check stability, save JSON | `calibration.json` values can be recomputed from raw samples |
| M5 Policies and controller | Apply P0 to P3 | Load baseline and thresholds, read recent latency, apply persistence and hysteresis rules, set priority or EcoQoS, log | P0 changes nothing; P1 stays low; P2 sets EcoQoS; P3 switches only per the rules; safe if the process exits |
| M6 Runner and analysis | Run experiments, produce results | Load plan, start logger, benchmark and workload, enable policy, run, clean up, save, analyse | A run can be repeated from its config; scripts regenerate the metrics |

## 11. Dataset and data collection

No external dataset. The dataset is the logs from your own runs; until runs are done it is planned, not collected.

- **Run metadata:** laptop ID, CPU, Windows version, power mode, plugged-in state, condition, policy, repetition, start time, workload and controller settings, exclusions with reasons.
- **Per-sample CSV columns:**

```
run_id, timestamp_ms, laptop_id, condition, policy, repetition,
foreground_latency_ms, baseline_latency_ms, slowdown_ratio,
cpu_total_pct, background_cpu_pct, background_priority, ecoqos_on,
background_work_completed, controller_action, temperature_c (blank if unavailable)
```

- **Storage and integrity:** one folder per run (CSV plus config snapshot), a master run index, Git for code. Never edit raw logs; log reruns and exclusions; every reported number must be reproducible from raw logs and scripts.

## 12. Tools and algorithms

| Item | Choice | Reason |
| --- | --- | --- |
| Language | Python 3 | Fast to build and debug |
| Processes | `multiprocessing`, `subprocess` | Separate benchmark, workload and controller; clean shutdown |
| CPU and priority | `psutil` | Process priority and CPU usage on Windows |
| EcoQoS | `ctypes` (or `pywin32`) calling the process power-throttling API | Needed for P2; psutil does not expose it |
| Timing | `time.perf_counter_ns()` | High-resolution elapsed time |
| Logging | `csv`, `json` | Reproducible raw data |
| Analysis | `pandas`, `matplotlib` | Metrics and plots |
| Version control | Git | Code and config history |
| Algorithms | Median smoothing, persistence thresholds, hysteresis, two-state priority control | Simple and explainable |

## 13. Evaluation metrics

All reported values must come from saved logs. Compute foreground metrics over the window where the background job is active.

- **Foreground latency:** p50 and p95 per run, then the median and spread across repetitions.
- **Normalised slowdown:** p50 (or p95) in the condition divided by the same laptop's baseline; percentage slowdown is (ratio minus 1) x 100.
- **Residual slowdown (RQ1):** the normalised slowdown that remains under P1.
- **Background completion time and throughput:** time to finish the fixed work, or work per second if time-limited.
- **Controller behaviour:** number and timing of priority switches, share of intervals above the slowdown threshold, controller CPU overhead.
- **Optional telemetry:** temperature or processor-performance summaries only if the sensor is verified; correlation is not causation.
- **Cross-laptop:** compare normalised slowdowns and policy outcomes, noting hardware differences.
- **Statistics:** at least 5 repetitions (3 fallback); report medians and interquartile range; never discard outliers silently.

**Primary comparison:** P0, P1, P2 and P3 under the same sustained workload. Define before looking at final data what trade-off is acceptable (for example P3's foreground p95 within a stated margin of P1's, with shorter background completion time).

## 14. Implementation progress and Review 2 evidence

Team-assigned percentages do not by themselves satisfy the course's '50% implemented' rule. Confirm the definition with your guide and show real outputs.

| Component | Weight | Evidence needed | Target by Review 2 |
| --- | --- | --- | --- |
| M3 benchmark | 12% | Timing samples and baseline variance | Yes |
| M2 background workload | 12% | Starts, finishes, stops cleanly | Yes |
| M1 logger | 10% | Valid CSV during a run | Yes |
| M4 calibrator | 8% | `calibration.json` matching raw data | Yes |
| P0 and P1 runs | 12% | Both run end to end with CSVs | Yes |
| Runner and analysis | 13% | Plot of latency over time per condition | Partial (manual run, one plot) |
| Pilot go/no-go checks | 5% | Results of Section 8.3 | Yes |
| P2 EcoQoS policy | 8% | EcoQoS verified on the process | If time |
| P3 controller | 15% | Switches per the rules, decisions logged | If time |
| Second laptop | 5% | Core runs on another laptop | Later |

**Review 2 demo package:** the benchmark and workload running together; a CSV for alone versus under load; a latency-over-time plot; a P1 run if it works; `calibration.json`; the pilot check results; and an honest note on what remains. Do not claim anything is complete unless you can run it.

## 15. Risks and plan

| Risk | Likelihood / impact | Mitigation |
| --- | --- | --- |
| No contention with the chosen workers | High / High | Workers equal to logical cores or same-core pinning; pilot gate first |
| Noisy benchmark | Medium / High | Tune loop size, close apps, report variability |
| Feedback does not beat static priority | High / Medium | Expected on foreground latency; report the throughput trade-off honestly |
| Priority switching oscillates | Medium / Medium | Hysteresis, persistence, dwell time; count switches |
| EcoQoS not available (not Windows 11) | Medium / Medium | Mark P2 not run; keep P0, P1, P3 |
| Cleanup fails after interruption | Medium / High | `try/finally`, stop signals, test aborted runs |
| Other Windows activity | High / Medium | Record conditions, repeat, rotate policy order |
| Second laptop unavailable | Low / Medium | State the single-laptop limitation |
| Timeline too short | High / High | Priority order: benchmark, workload, logger, calibration, P0/P1, pilot gates, analysis, P3, P2 |

| Window | Deliverable |
| --- | --- |
| 13 Oct (Review 2) | Benchmark, workload, logger, calibrator, P0/P1 runs, pilot checks, one plot, honest status |
| 14 to 15 Oct | P2 and P3 implemented; tune on pilots; freeze thresholds |
| 16 to 19 Oct | Full runs on laptop 1 (about 3 hours machine time) |
| 19 to 22 Oct | Laptop 2 runs; analysis and figures |
| 22 to 25 Oct | Report and paper in your own words (start sections early); reference check |
| 26 Oct | Consistency check and demo rehearsal |
| 27 Oct | Submit; no new features |

**Cut first if behind:** P4, P2, the second laptop's full runs, optional sensors. **Never cut:** raw data, P0/P1/P3 comparison, honest limitations.

## 16. Comparison with existing approaches

We compare policies on the same hardware with the same benchmark and workload. We do not compare against numbers from papers on other platforms, because they are not comparable, and we do not claim to beat kernel-modification, model-based, learning-based or commercial systems.

| Approach | Needs kernel or driver change | Needs training or model | Relationship to this project |
| --- | --- | --- | --- |
| Kernel or governor modification (Bhat 2019) | Yes | Model parameters | Prior art; out of scope |
| Thermal or MPC models (Liu 2022, Park 2018) | Varies | Yes | Prior art; we use no thermal model |
| ML or learning-based management (Sikal 2022) | Varies | Yes | Prior art; no training here |
| User-level contention control (Abe) | No | No | Closest research relative; contention only |
| Windows Efficiency Mode | No | No | Built-in baseline (P2) |
| ProBalance-style tools | No | No | Practical prior art; optional P4 |
| **This prototype (P3)** | No | No | Latency-feedback priority control, measured against P0 to P2 |

**Our limits:** synthetic benchmark, the controller reads that benchmark directly, priority is a coarse actuator, no guarantees, two laptops at most.

## 17. Requirements

- **FR1:** log foreground timings with timestamps and run IDs. **FR2:** run and cleanly stop a repeatable background workload. **FR3:** log CPU use and the active policy. **FR4:** calibrate and save a baseline per laptop. **FR5:** support P0 to P3. **FR6:** log every controller decision and priority change. **FR7:** save config and raw data per run. **FR8:** produce metric tables and plots. **FR9:** represent missing optional sensors as blank.
- **NFR1:** user space only. **NFR2:** measure controller overhead. **NFR3:** reproducible from saved code, configs and logs. **NFR4:** safe operation (Section 8.4). **NFR5:** Windows 10 or 11 with standard Python packages.

## 18. Answers to the Review 1 questions

| Teacher's question | Short answer |
| --- | --- |
| How do you stay accurate across laptops with different limits? | Per-laptop baseline, ratio-based thresholds (no absolute temperatures), identical protocol, results compared as normalised slowdowns, and the claim limited to the laptops tested. |
| How exactly will you implement it? | Six modules (Section 10): benchmark, background workload, logger, calibrator, policies and controller, runner and analysis, in Python with `psutil` and a Windows API call for EcoQoS. |
| How is it better than existing work (mobile, server, embedded; kernel changes, thermal models, deep RL)? | We do not claim to beat them; they run on other hardware and need kernel changes, models or training. We measure, on the same laptops, what priority, Efficiency Mode and feedback achieve, and report the result either way. |
| Can you get the data without kernel access? | Yes for the primary signal: it is the benchmark's own timing, plus `psutil` CPU use and priority. Temperature and performance counters are optional and checked per laptop. We write no driver or kernel code. |
| What is the novelty? | A narrow empirical one: the residual slowdown after priority control, and a same-hardware comparison of priority, EcoQoS and feedback. The broader ideas have prior art. |

## 19. Threats to validity

- **Synthetic foreground:** the benchmark is a proxy, not a real application.
- **Controller sees the benchmark directly:** a deployed tool would need an application-level responsiveness signal.
- **Cause of slowdown:** timing alone cannot identify thermal, frequency or contention causes; no causal split is claimed.
- **Runtime noise:** Python overhead, other processes, turbo behaviour and hybrid performance and efficiency cores can shift timings.
- **Environment:** power mode, AC or battery, ambient temperature, fan profile, updates and scans can move results; fix and log them.
- **Coarse actuator:** priority does not guarantee CPU time or a latency target.
- **Two laptops at most:** results describe only the tested machines.
- **Optional sensors:** may be missing, coarse or inaccurate; never fill gaps with estimates.

## 20. References to verify and cite

Check authors, year, venue, pages and DOI on the publisher page for every entry; add DOIs only after checking. Every cited source must be listed and every listed source cited.

- Park, J., Lee, S., & Cha, H. (2018). App-oriented thermal management of mobile devices. ISLPED 2018.
- Bhat, G., Gumussoy, S., & Ogras, U. Y. (2019). Power and thermal analysis of commercial mobile platforms: Experiments and case studies. DATE 2019.
- Abe, Y., Yamada, H., & Kono, K. (2008). Enforcing appropriate process execution for exploiting idle resources from outside operating systems. EuroSys 2008.
- Abe, Y., Yamada, H., & Kono, K. (2011). User-level enforcement of appropriate background process execution. IPSJ Transactions on Advanced Computing Systems, 4(2), 94-113. (The record I read lists no DOI; confirm how it relates to the 2008 paper.)
- Lo, D., Cheng, L., Govindaraju, R., Ranganathan, P., & Kozyrakis, C. (2015). Heracles: Improving resource efficiency at scale. ISCA 2015.
- Iorga, D., Sorensen, T., Wickerson, J., & Donaldson, A. F. (2020). Slow and steady: Measuring and tuning multicore interference. RTAS 2020.
- Sikal, M. B., Khdr, H., Rapp, M., & Henkel, J. (2022). Thermal- and cache-aware resource management based on ML-driven cache contention prediction. DATE 2022.
- Liu et al. (2022). Model predictive control of portable electronic devices under skin temperature constraints. Energy, 260. (Complete the author list.)
- PCCS processor-centric contention-aware slowdown model, MICRO 2021. (Find the exact authors and details before citing.)
- Microsoft. Reduce process interference with Task Manager Efficiency Mode (Performance and Diagnostics blog, 2022); Microsoft Learn documentation for process and thread power throttling.
- Process Lasso (Bitsum). ProBalance documentation.

Do not cite Ren et al. or *Phoenix* (2026) until the exact paper is found and read.
