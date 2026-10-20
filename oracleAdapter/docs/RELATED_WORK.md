# Related work and applicability review

Status: source review and module development; no new full-cohort result or algorithmic novelty established. Oracle planning and Landmark adaptation are separate interventions. The archived 3062-task proof is a reference result, not a result of this module.

## Source and implementation comparison

| Method / source | Type and privileged information | Movement assumptions and failure behavior | Actual code / reusable component | Adaptation cost and evidence boundary |
|---|---|---|---|---|
| [Habitat GreedyGeodesicFollower](https://aihabitat.org/docs/habitat-sim/habitat_sim.nav.GreedyGeodesicFollower.html), [issue1689](https://github.com/facebookresearch/habitat-sim/issues/1689) | Goal follower; native pose, navmesh, goal | Fits turn-prefix+forward primitives to geodesic progress; collision penalty; alternating-turn thrashing detection. Error remains possible. Not a complete action-space planner. | `src/esp/nav/GreedyFollower.cpp`, Python `nav/greedy_geodesic_follower.py`; use installed native implementation as named baseline. | Low integration cost. Current runtime0.1.7 must be compared with reviewed current HEAD, not silently upgraded. Core code inspected; new-module native reproduction pending. |
| [Habitat-Lab ShortestPathFollower](https://github.com/facebookresearch/habitat-lab) | Action teacher; simulator pose/goal | Wrapper behavior on follower error and scene reset matters; STOP-on-error is not success. | `habitat/tasks/nav/shortest_path_follower.py`; reference follower example | Current tree has changed package layout. Bind installed0.1.7 source separately; do not infer protocol from current docs. |
| [VLN-CE](https://github.com/jacobkrantz/VLN-CE), [paper](https://arxiv.org/abs/2004.02857) | Continuous data/expert trajectory infrastructure | Discrete graph reachability and executable continuous motion are different. The compatibility follower documents older0.1.4 dataset-generation behavior. | `habitat_extensions/shortest_path_follower.py`, dataset/task definitions; official CE reference/GT assets reused read-only. | Medium: preserve Guide/Follower/language/IDs and original sensor/action contracts. CEabsence does not establish an author's filtering reason. |
| [Discrete-Continuous-VLN](https://github.com/YicongHong/Discrete-Continuous-VLN) | Adapted graph + predicted waypoints; graph/reference geometry or panoramic perception depending on component | Released graph adds new nodes and changes positions. Traversability claim is under author VLN-CE configuration. | Adapted graph asset; `habitat_extensions/task.py`, `common/environments.py`, waypoint code | Graph-construction code remains unchecked in repository checklist; graph-walk entry crossed out. No invented construction recipe.461 IDs and current geometry must be audited individually. |
| [ETPNav](https://github.com/MarSaKi/ETPNav), [paper](https://arxiv.org/html/2304.03047v3) | Topological planner + local Tryout controller; learned waypoint/perception and pose | `single_step_control` detects collision, randomly chooses a left/right escape ordering, then primitive turns/forward. `teleport` exists separately and must never leak into uninterrupted execution. | `vlnce_baselines/common/environments.py:340–425`, `models/graph_utils.py` | A fixed/seeding-explicit recovery idea may be compared, but public whole controller has different input/goal semantics. Not selected as an additional initial candidate; no model replacement. |
| [Sim2Sim-VLNCE](https://github.com/jacobkrantz/Sim2Sim-VLNCE), [paper](https://arxiv.org/html/2204.09667v2) | Oracle/local/teleport branches explicitly separated; Oracle has navmesh and waypoint | Paper describes A*-based Oracle. Checked `SPFEnv` invokes native follower `find_path`, then single-step fallback;0.15m radius,40-step cap, final heading alignment. This is not evidence of a reusable complete A* implementation. | `Sim2Sim/environments.py:152–286`; `graph-oracle_policy.yaml` selects SPFEnv; environment pins habitat-sim0.1.7; habitat-lab gitlink d6ed1c0… | Medium/high: inspect actual dependency chain, do not import teleport mode or change goal radius/actions silently. Local map-and-plan branch uses depth and separate map/controller dependencies. |
| [OMPL](https://ompl.kavrakilab.org/planners.html) | Geometric planners versus control planners with state propagator | A geometric path is not an executable sequence of the three native actions. Control propagation and state validity must be supplied; approximate solutions must remain distinguishable. | `control/StatePropagator.h`, KPIECE/SST source, source-locked BSD library | High. No install or invented continuous controls. Not selected for initial implementation until a valid native discrete-control propagator and fair budget comparison exist. |
| [Hybrid A*](https://robotics.stanford.edu/~ddolgov/papers/dolgov_gpp_stair08.pdf) | Heading-aware motion-primitive search | Continuous representatives in discrete cells; car steering/reverse constraints differ from turn-in-place Habitat. Cell merging itself loses distinctions; not a cure for all state aliasing. | State/primitive design and heuristics are prior art; no code copied. | Research comparison only. Exact-label hypothesis is not claimed novel and may cost substantially more search. |
| [Landmark-RxR paper](https://proceedings.neurips.cc/paper/2021/file/0602940f23884f782058efac46f64b0f-Paper.pdf), [repo](https://github.com/hekj/Landmark-RxR) | Fine-grained English Guide subinstructions/subpaths; ordered landmark occurrences | Original section4 reinitializes after a failed intermediate landmark,3m threshold and10 discrete steps. It is not unconditional per-subsegment reset and not10 continuous .25m actions. | Actual repo tree at frozen commit contains README only. Reuse existing authorized annotation assets, not nonexistent evaluator code. | A(original reinitialization) and B(uninterrupted native) must be separate. Missing implementation details remain unknown. Original A scores are not presently reproduced. |
| [RxR](https://github.com/google-research-datasets/RxR) | Guide/Follower annotations, camera pose traces | instruction_id identifies Guide; demonstration_id identifies Follower. Initial heading radians; camera extrinsics/pose differ from agent-foot position. | Official schemas, existing guide/follower/pose assets and version notes; no161GB re-download. | Need raw-version provenance and round-trip coordinate tests. Do not infer identity from text or nearest coordinates. |

Full commit IDs, file hashes, URLs and licenses: `../src/oracle/configs/sources/upstream-lock.json`. Sources were fetched from their frozen commits, not from mutable paths. Source snapshots remain outside active implementation. MIT/BSD references have not been bulk copied into the module; the Landmark repository supplies no code license in its checked tree, and RxRdata license is CC-BY4.0. Dataset/scene redistribution is not part of this work.

## Selected hypotheses and limits

H1: lossless labels may avoid known false pruning by rounded position/yaw keys. Minimal controlled change: label identity only; keep task, transitions, feasibility, costs and budget equal. A small deterministic counterexample now demonstrates that adding a forward-legal bit still does not make a rounded key sufficient. This is a CPU algorithmic counterexample, not fresh Habitat proof or novelty. Full native state sufficiency and performance remain to be tested.

H2: stable identity plus occurrence-constrained official reference guidance may preserve required landmarks better than independent point matching or terminal shortcuts. Mapping changes are measured separately from planner changes. First implementation only checks exact discrete subpath occurrence coverage; it does not invent missing continuous correspondences.

At initial hypothesis registration no portfolio had been selected. The subsequent fixed guarded-prefix portfolio is now implemented, source-frozen and tested as recorded below; that earlier planning state is superseded. No learned controller, new sensor, new native action, geometry change or alternative motion acceptance is adopted. Sampling/HybridA*/ETP recovery are reviewed alternatives, not an indiscriminate stack.

## Evidence and execution sequence

1. Typed contracts, actual import binding, lossless-context keys and bounded candidate search.
2. Complete identity-only ledgers for461 missing viewpoints,8034 unmatched records and33954 subpath order checks, preserving unresolved reasons.
3. Reproduce archived real-native alias and motion-prediction counterexamples through this module; test independent geometry implementations/contact certificates separately.
4. Freeze explicit development lists, two finite candidates, fair cost budgets and mapping×planner comparisons before native development runs.
5. Only a selected frozen method can enter full3062/33954 runs. Every restored path needs actual execution and independent replay. Whole-route(B) never borrows resets or orientation replacement from(A).

The historical validation data have already been inspected. Report this as reconstruction research and controlled comparisons; do not claim blind generalization. Innovation, complete feasibility and full acceptance remain unestablished.

## Checked evidence from the first module runs

- Identity ledger: all33954 records retained;25920 exact installedCE Guide matches;8034 absent from checked CEroles/splits/scene+trajectory IDs after normalization.461 missing graph IDs are classified as365 with officialcontinuous-reference anchors and96 without directcorrespondence; rename/merge/substitution remains unproven.
- OriginalRxR Guide provenance: after checking canonical shared annotation directories, the three missing rawGuide files were acquired once from the officialpublic bucket (96,507,569bytes, SHA/ETag/generation saved, ownedread-only cache). All33954 source IDs, scene/split/language/path_id andordered viewpointpaths match, includingall8034 missingCE records.710 text differences vanish under boundaryquote/whitespace normalization; textwasnever usedtoinferidentity. HistoricalCE exclusion reason remainsunknown.
- Exact subpath coverage initially required sharedboundary occurrences. train:43144 containsan explicitcc03…→7389… boundaryedgeinthe originalfullpath, outsideboth adjacent subpaths. A separate connector mapping preserves thatedge andall10subinstructions:33953 originalexact mappings unchanged,1explicitconnector,0regressions. This isnot newmotion success or anOracle algorithmgain.
- Native aliasrecheck:25archived pairs,100native calls including replay,25same-rounded-key/different-legal-forward cases reproduced undernativeexportedgeometry/currentexact-linear checks.4positivecontacts cross-checked by rational witnesses; no changeinold/currentlegality onthese pairs. Replay usedseparate simulatorinstances inthe sameprocess; itisnot a mathematicalindependence orcompleteness claim.
- The first aliasprobe failedbeforemotion because Landmarkprofiles omitformal-profile scene_path fields. Itsfailure/sourcearchive remains. The correctedrun binds sceneidentitythroughnative-loader catalog; no physicalconditionwasrelaxed.

Sim2Sim's useof'A*' shouldnot beinterpreted automatically ascompleteaction-spaceA*: geodesicnavmesh search andaction-fitting aredifferentlevels. Thechecked config/env/native dependencychain—not README wording—governs reproducibility.

Whole-route teachers, the fixed12-task state-key comparison, strict official-action reexecution and the fixed133-task portfolio/ablation are implemented and completed. The uniform3062/33954 continuous-reference run is active, and its final acceptance remains pending. No formal model run or publication is triggered by these component results.

## Fixed development comparison and negative result

`outputs/oracleAdapter/route-development-v1-serialization-retry` contains 24 executions and separate-process replay. The evidence-bound report at `route-development-paired-report-v1` verifies the archived source, manifest, task/environment/privilege identity, result/audit hashes and complete pairs before aggregation. All failures remain in denominators and cost quantiles.

| Objective/cohort | Quantized+forward-bit control | Lossless pose labels | Recovery/regression | CPU seconds (control/candidate) |
|---|---:|---:|---:|---:|
| Endpoint115 ordered references | 4/8 | 4/8 | 0/0 | 174.505/189.071 |
| Landmark v11 ordered occurrences | 1/4 | 1/4 | 0/0 | 51.702/80.414 |

1009 actual actions were replayed. These tasks were historically inspected development examples, not blind validation. Separating aliased states has a valid counterexample motivation, but this experiment does not show improved route coverage; more lossless search states can exhaust the declared budget. The common cost/depth Pareto correction is shared by both arms and is not attributed to the state-key factor. Greedy C++ internal probes are not instrumented; report wall/CPU cost alongside incomplete adapter-call counts. No novel algorithm contribution is established.

## Official RxR action protocol is not the current Case1 protocol

The pinned VLN-CE [RxR English task configuration](https://github.com/jacobkrantz/VLN-CE/blob/729d141b2ee10628061ada74dd3a5b9f70faeba5/habitat_extensions/config/rxr_vlnce_english_task.yaml) explicitly sets 30-degree turns, body height0.88m/radius0.18m, slidingFalse, sensor height0.88m, 79-degree HFOV and LOOK_UP/LOOK_DOWN in its possible action list. The checked R2R task configuration instead sets 15-degree turns and slidingTrue. This distinction must not be erased by citing the generic task YAML for RxR. The additional checked RxR YAML has SHA256 `698478619a7678cc0f07fa0d846426d749526f4cee294d6367a707262211fbfb`.

Current research deliberately retains the user-fixed 1.5m/0.1m body,15-degree native actions, slidingTrue and strict source/step gates. Expanding an official30-degree turn into two15-degree actions is only a candidate action translation; different sliding and intermediate height projection mean execution equivalence is unproven. Official GT schema and complete per-record availability are audited separately. Do not change the target protocol to make demonstrations pass.


## Original A versus current B: reproducibility boundary

The source-backed paper-A evidence configuration is `configs/protocols/landmark_paper_a_evidence.json`, deliberately not adopted for execution. The read-only `audit-landmark-protocol-readiness` reports dataset cardinality and unresolved implementation details; it never reinterprets B traces as A scores. Released complete task counts match the paper, while subinstruction counts differ by71/5/1 across train/seen/unseen. All33954 and all166663 released subpaths remain.89 source subpaths exceed10 graph edges; this does not establish failure within the paper's success region.

| Dimension | Paper A | Frozen current B |
|---|---|---|
| Required targets | Annotated landmarks with reinitialization evaluation | Every supplied reference occurrence, including landmark boundaries; a stronger reference scope |
| Actions/budget | Panoramic discrete viewpoint decisions;10 steps per subtrajectory | Native0.25m/15degrees;1500 actual actions per reference and10000 per task, declared finite search ceilings |
| Reset | Intermediate failure triggers reinitialization | No intermediate reset |
| Evidence | Source protocol checked; original evaluator not released; implementation details unresolved | Full actual-motion and independent replay queue running; final acceptance pending |
| Comparability | Do not report original SA/SSA/LN without reproducing the protocol | Do not convert strict-route passes into paper-A or model scores |

Paper source: https://proceedings.neurips.cc/paper/2021/file/0602940f23884f782058efac46f64b0f-Paper.pdf ; SHA256eb206b9f8ab9b7a5234e564db5f163141ea80c5bcf1ed8a691e72d0cc89c8a0a. Source readiness evidence is `outputs/oracleAdapter/landmark-paper-a-readiness-v1`.


## Current evidence-based contribution assessment

| Claim | Comparable evidence | Interpretation and remaining limit |
|---|---|---|
| Lossless labels repair rounded-key aliasing |25 actual state pairs have different legal successors despite the old same key; lossless labels distinguish them |Correctness motivation established for these examples; not a proof of sufficient Markov state or planner completeness |
| Lossless labels improve coverage |Fixed12-task paired comparison:0 recovery/0 regression; CPU increased in both cohorts |Coverage benefit not established; do not claim algorithmic improvement from the counterexample alone |
| Fixed guarded suggestions plus search improve over guarded suggestions alone |Same133 tasks and official-action information:51 to90 accepted,39 recovery/0 regression |Conventional deterministic fallback is useful in this development scope; actual CPU445.828 to2530.914s, so not equal-compute evidence |
| Combination versus pure search |Same physical133 tasks:90 versus54; CPU2530.914 versus4645.626s |Pure search lacks official actions. This is an information ablation, not same-information algorithm superiority |
| Combination captures complementary behavior |All single-method successes retained;8 tasks fail in both single arms and pass after actual combined execution |Executed combination benefit, not a posthoc union. Does not establish novelty or unseen generalization |
| Landmark source adaptation |One explicit source connector preserves all10 subinstructions;33953 unchanged.461/8034 ledgers and original/CE graph provenance are explicit |Mapping-accounting repair, separate from Oracle gains. No full native repair count follows from identity auditing |
| Novel research contribution |Rounded-state issues, bounded action search and fixed portfolios are conventional concepts |No novel algorithm claim established. Packaging, stronger logging and more compute are not algorithm innovation |

The registered reference-purpose official-prefix capability is distinct from the Landmark-purpose capability. Both use the existing `teachers.ordered:execute`; the reference variant lacks landmark-annotation privilege and was already accepted by the runtime contract. Adding its missing registry description does not change runtime navigation. New local metadata is not hot-synced into the frozen server run.


## Full endpoint historical overlap: preserve the negative result

The complete3062 current endpoint subset is1934 strict passes/1128 finite failures, below the historical2225 count. Hash-verified comparison of the listed input/target/start/profile/native-geometry fields found no mismatches.295 historical-only passes are current budget failures;4 current-only passes occur in the RxR official-prior branch. Old strict replay witnesses remain their original evidence, not copied current successes. Historical wall/CPU and complete privilege/planner-state equivalence are not established, so this is descriptive overlap, not a matched-budget algorithm effect. No posthoc union is registered as a method. Full ledger/report: outputs/oracleAdapter/endpoint-history-overlap-v1.
