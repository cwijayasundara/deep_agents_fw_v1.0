# Reusable Evaluation Framework for LangChain v1 / LangGraph / DeepAgents Agents (Python)

Research date: 2026-11-01. Package versions were taken from the PyPI JSON API (`https://pypi.org/pypi/<pkg>/json`) and the npm registry on 2026-11-01:

| Package | Latest version | Upload date |
|---|---|---|
| langchain | 1.4.7 | 2026-10-21 |
| langgraph | 1.2.19 | 2026-10-30 |
| deepagents | 0.7.32 | 2026-10-23 |
| openevals | 0.2.2 | 2026-10-22 |
| agentevals | 0.0.9 | 2025-07-24 (no release in over 15 months) |
| langsmith (SDK) | 0.14.16 | 2026-10-29 |
| deepeval | 4.3.2 | 2026-10-27 |
| ragas | 0.4.3 | 2026-01-13 |
| inspect-ai | 0.3.287 | 2026-10-31 |
| langfuse (SDK) | 5.1.0 | 2026-10-30 |
| arize-phoenix / arize-phoenix-evals | 21.0.0 / 3.9.5 | 2026-10-30 / 2026-10-28 |
| mlflow | 3.17.2 | 2026-10-21 |
| promptfoo (npm) | 0.125.1 | date not captured |

Sources: [PyPI openevals](https://pypi.org/project/openevals/), [PyPI agentevals](https://pypi.org/project/agentevals/), [PyPI langsmith](https://pypi.org/project/langsmith/), [PyPI deepeval](https://pypi.org/project/deepeval/), [PyPI ragas](https://pypi.org/project/ragas/), [PyPI inspect-ai](https://pypi.org/project/inspect-ai/), [PyPI langfuse](https://pypi.org/project/langfuse/), [PyPI arize-phoenix-evals](https://pypi.org/project/arize-phoenix-evals/), [PyPI mlflow](https://pypi.org/project/mlflow/), [PyPI deepagents](https://pypi.org/project/deepagents/), [PyPI langgraph](https://pypi.org/project/langgraph/), [PyPI langchain](https://pypi.org/project/langchain/), [npm promptfoo](https://www.npmjs.com/package/promptfoo)

---

## Q1. LangChain ecosystem: openevals, agentevals, LangSmith evaluate, pytest integration, datasets, experiments, pairwise, online evaluators

### Takeaway
`openevals` (0.2.2, Oct 2026) is the live, framework-light library. It now includes LLM-as-judge factories, a large prebuilt prompt catalog, code, JSON and string evaluators, multi-turn simulation, and the trajectory-match and trajectory-judge APIs. `agentevals` (0.0.9, Jul 2025) is effectively frozen but still holds the LangGraph graph-trajectory evaluators. Both libraries return plain `EvaluatorResult` dicts and run without LangSmith. Only the pytest/vitest logging, `evaluate()`, datasets, experiments, annotation queues and online evaluators need LangSmith, and self-hosted LangSmith requires an Enterprise license.

### Cited Findings
**openevals: LLM-as-judge**
- The factory is `create_llm_as_judge` (TS: `createLLMAsJudge`). Its parameters are `prompt` (f-string, LangChain/mustache template, or a function that returns messages), `model` (a `"provider:model"` string), `judge` (a chat model or client), `feedback_key`, `choices`, `continuous`, `use_reasoning`, `output_schema`, `system` and `few_shot_examples`. Passing a custom `output_schema` changes the return shape. Multimodal input goes through an `attachments` kwarg (images, audio and PDF are supported). — [openevals README](https://raw.githubusercontent.com/langchain-ai/openevals/main/README.md)
- Prebuilt prompts, grouped by area:
  - Quality: CONCISENESS, CORRECTNESS, HALLUCINATION, ANSWER_RELEVANCE, PLAN_ADHERENCE, CODE_CORRECTNESS (with and without reference), LAZINESS.
  - Safety: TOXICITY, FAIRNESS.
  - Security: PII_LEAKAGE, PROMPT_INJECTION, CODE_INJECTION.
  - Image: EXPLICIT_CONTENT, SENSITIVE_IMAGERY.
  - Voice: AUDIO_QUALITY, TRANSCRIPTION_ACCURACY, USER_INTERRUPTS, VOCAL_AFFECT.
  - RAG: RAG_HELPFULNESS, RAG_GROUNDEDNESS, RAG_RETRIEVAL_RELEVANCE. RAG correctness reuses CORRECTNESS_PROMPT.
  - Trajectory: TRAJECTORY_ACCURACY_PROMPT, TRAJECTORY_ACCURACY_PROMPT_WITH_REFERENCE.
  - Source: [openevals README](https://raw.githubusercontent.com/langchain-ai/openevals/main/README.md)

**openevals: deterministic, structured and code evaluators**
- `create_json_match_evaluator` takes `aggregator` ("average", "all" or None), `list_aggregator`, `exclude_keys`, `rubric` (an LLM judge per key), `model` and `use_reasoning`. `rubric` and `exclude_keys` apply only to top-level keys. — [openevals README](https://raw.githubusercontent.com/langchain-ai/openevals/main/README.md)
- `exact_match` (`openevals.exact`) returns the key `equal`. `levenshtein_distance` (`openevals.string.levenshtein`) returns `levenshtein_distance`. `create_embedding_similarity_evaluator` is also available. — [openevals README](https://raw.githubusercontent.com/langchain-ai/openevals/main/README.md)
- Code evaluators:
  - `openevals.code.pyright.create_pyright_evaluator` and `openevals.code.mypy.create_mypy_evaluator`.
  - `create_code_llm_as_judge`, with `code_extraction_strategy` ("llm" or "markdown_code_blocks") or a custom `code_extractor`.
  - E2B sandbox evaluators `create_e2b_pyright_evaluator` and `create_e2b_execution_evaluator`. These take a `sandbox`, `sandbox_project_directory` and `environment_variables`.
  - Source: [openevals README](https://raw.githubusercontent.com/langchain-ai/openevals/main/README.md)

**openevals: multi-turn simulation**
- `run_multiturn_simulation` takes these arguments:
  - `app`: takes a message and a `thread_id` kwarg, and returns a message with role and content.
  - `user`: takes the trajectory plus `thread_id` and `turn_counter`.
  - `max_turns`.
  - `stopping_condition(trajectory, turn_counter) -> bool`.
  - `trajectory_evaluators`: run at the end on `outputs=trajectory`.
  - `reference_outputs`.
  - `thread_id`: defaults to a UUID.
  - At least one of `max_turns` or `stopping_condition` is required. — [openevals README](https://raw.githubusercontent.com/langchain-ai/openevals/main/README.md)
- It returns a `MultiturnSimulationResult` with `evaluator_results` and `trajectory`. The simulator does not log feedback itself. — [openevals README](https://raw.githubusercontent.com/langchain-ai/openevals/main/README.md)
- `create_llm_simulated_user(system=..., model=... | client=..., fixed_responses=[...])` creates a simulated user. The fixed responses are played first, then the LLM takes over. The README notes that simulation techniques "changed with the release of 0.1.0". — [openevals README](https://raw.githubusercontent.com/langchain-ai/openevals/main/README.md)

**Trajectory evaluators (openevals and agentevals)**
- `create_trajectory_match_evaluator` (async: `create_async_trajectory_match_evaluator`) takes three settings:
  - `trajectory_match_mode`: `strict` (same messages and tool calls in the same order; content may differ), `unordered`, `subset` or `superset`.
  - `tool_args_match_mode`: `exact` (default), `ignore`, `subset` or `superset`.
  - `tool_args_match_overrides`: per-tool rules. Each rule is "exact", "ignore", a list of fields that must match, or a comparator function.
  - Source: [agentevals GitHub](https://github.com/langchain-ai/agentevals)
- `create_trajectory_llm_as_judge(prompt=TRAJECTORY_ACCURACY_PROMPT | TRAJECTORY_ACCURACY_PROMPT_WITH_REFERENCE, model=..., continuous, choices, system, few_shot_examples)` needs no reference trajectory. — [agentevals GitHub](https://github.com/langchain-ai/agentevals)
- The LangGraph graph-trajectory evaluators are:
  - `extract_langgraph_trajectory_from_thread` (in `agentevals.graph_trajectory.utils`): extracts the trajectory as the sequence of nodes visited.
  - `create_graph_trajectory_llm_as_judge`: a custom prompt must contain `{thread}`.
  - `graph_trajectory_strict_match` (in `agentevals.graph_trajectory.strict`).
  - Source: [agentevals GitHub](https://github.com/langchain-ai/agentevals)
- The trajectory-match and trajectory LLM-judge APIs also appear in the openevals README, which suggests they now ship in openevals as well. — [openevals README](https://raw.githubusercontent.com/langchain-ai/openevals/main/README.md)

**LangSmith integration**
- Setup: set `LANGSMITH_API_KEY` and `LANGSMITH_TRACING=true`. — [openevals README](https://raw.githubusercontent.com/langchain-ai/openevals/main/README.md)
- pytest: mark tests with `@pytest.mark.langsmith`, log with `t.log_inputs` / `t.log_outputs` / `t.log_reference_outputs` from `langsmith.testing`, and run `pytest ... --langsmith-output`. The evaluator's `feedback_key` names the feedback in LangSmith.
- Vitest/Jest: use `langsmith/vitest` or `langsmith/jest`, with `ls.describe`, `ls.test` and `ls.logFeedback`.
- `evaluate`: call `client.evaluate(target, data=..., evaluators=[...])`. An evaluator whose signature is only `inputs`, `outputs` and `reference_outputs` can be passed directly; any other signature needs a wrapper.
- Sources for the last three items: [openevals README](https://raw.githubusercontent.com/langchain-ai/openevals/main/README.md), [agentevals GitHub](https://github.com/langchain-ai/agentevals)

**LangSmith concepts**
- Evaluation modes:
  - Offline: benchmarking, regression, unit tests and backtesting.
  - Online: real production traces that have no reference outputs.
  - Source: [LangSmith evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts)
- Evaluators are workspace-level resources that can be attached to many tracing projects and datasets. The kinds are human, code, LLM-as-judge (with or without a reference; few-shot helps), pairwise (heuristic, LLM or human) and decision-model (typed questions). — [LangSmith evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts)
- Datasets:
  - Start with 10–20 hand-curated examples.
  - Grow them from historical traces (for example, runs with negative feedback) and from synthetic examples.
  - Splits can overlap: one example can belong to several splits.
  - A new version is created automatically when examples change. You can tag versions and pin a version in CI.
  - Source: [LangSmith evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts)
- An experiment holds one application version's outputs, scores and traces for a dataset, and experiments can be compared side by side. — [LangSmith evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts)
- Annotation queues:
  - Single-run queues grade a run against a rubric and support assertions that can later grade runs offline.
  - Pairwise queues support A/B judgments.
  - Queues support multiple reviewers and reservations, and annotated runs can be exported to datasets.
  - Source: [LangSmith evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts)
- Online evaluators: sampling rate, filters and spend limits are set per attached project or dataset, not on the evaluator. Threads group runs, and thread-level evaluators score multi-turn properties such as coherence and topic maintenance. — [LangSmith evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts)
- Regression testing can assert that a new version beats a baseline. Backtesting runs a new version against historical data. — [LangSmith evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts)

**Self-hosted LangSmith**
- Self-hosted LangSmith is available only with an Enterprise license. You get a key by contacting sales (support article updated 2025-10-30). — [LangChain support KB](https://support.langchain.com/articles/7011309930-how-do-i-obtain-a-self-hosted-langsmith-license-key)
- Deployment details:
  - Installed with Helm on Kubernetes (tested on GKE, AKS, EKS and OpenShift 4.14+).
  - Uses Postgres, Redis and ClickHouse; external databases are recommended.
  - Needs egress to `beacon.langchain.com` for license checks and usage reporting.
  - Source: [LangSmith Kubernetes self-hosting](https://docs.langchain.com/langsmith/kubernetes)

### Inferences
- The shared package should depend on `openevals` for judge and trajectory primitives. It should vendor or wrap only the graph-trajectory pieces of `agentevals`, because agentevals is stale (0.0.9, Jul 2025) and a hard pin is a risk.
- openevals evaluators are plain callables that take `inputs`, `outputs` and `reference_outputs` and return `{key, score, comment}`. That makes them usable as a backend-neutral evaluator contract. They can feed LangSmith, Langfuse, MLflow or a local JSON reporter, as long as the results are adapted.
- `@pytest.mark.langsmith` logging is optional. The same pytest tests can run with tracing off, so CI does not need LangSmith; it only adds experiment tracking.

### Gaps
- No exact release notes were found for openevals 0.2.x. It was not confirmed whether agentevals is officially deprecated in favour of openevals.
- LangSmith's "Align Evals" judge-calibration feature, and composite evaluators, were not covered on the fetched concepts page.
- The publish date of pairwise `evaluate_comparative` and its current API were not re-verified.

---

## Q2. How LangChain recommends evaluating deep agents

### Takeaway
LangChain's guidance comes from two posts: "Evaluating Deep Agents: Our Learnings" (Dec 2025) and "How we build evals for Deep Agents" (2026-03-26). It amounts to:
- Write bespoke per-test assertions instead of one shared dataset and evaluator.
- Use about 50% single-step decision tests, plus full-run tests that assert on the trajectory, the final response and the state or artifacts produced.
- Run multi-turn tests with early-fail gating or simulated users.
- Reset the environment for every test, and replay HTTP calls with VCR.
- Tag evals by category, run them with pytest in GitHub Actions, and score efficiency against an "ideal trajectory".

### Cited Findings
**"Evaluating Deep Agents: Our Learnings" (Dec 2025)**
- The lessons came from shipping four Deep Agents apps: the DeepAgents CLI, LangSmith Assist, a Personal Email Assistant and Agent Builder. — [LangChain blog, Dec 2025](https://www.langchain.com/blog/evaluating-deep-agents-our-learnings)
- Each test needs its own success logic, which may check the trajectory, the final message and the agent's state. — [LangChain blog, Dec 2025](https://www.langchain.com/blog/evaluating-deep-agents-our-learnings)
- Single-step evals:
  - About half of the test cases ran a single step to check the next decision (tool and arguments).
  - In LangGraph, you interrupt before the tools node and inspect the pending tool call.
  - The post's rationale: "Regressions often occur at individual decision points rather than across full execution sequences."
  - Source: [LangChain blog, Dec 2025](https://www.langchain.com/blog/evaluating-deep-agents-our-learnings)
- Full-run evals assert three things:
  - The trajectory: a tool was called at some point, in any order.
  - The final response quality, which matters more than the path for open-ended tasks.
  - Other state, such as files written or sources found.
  - Source: [LangChain blog, Dec 2025](https://www.langchain.com/blog/evaluating-deep-agents-our-learnings)
- Multi-turn evals: hardcoded follow-up inputs break when the agent deviates. Run one turn, check it, then continue or fail early. To test a later turn on its own, start from a seeded state. — [LangChain blog, Dec 2025](https://www.langchain.com/blog/evaluating-deep-agents-our-learnings)
- Environments:
  - Use a fresh environment for every test.
  - Terminal-Bench runs in Docker through Harbor, and the CLI eval uses a temporary directory per test.
  - External APIs are recorded and replayed with vcr (Python) or a fetch proxy (JS).
  - Source: [LangChain blog, Dec 2025](https://www.langchain.com/blog/evaluating-deep-agents-our-learnings)
- Example test (calendar agent, rule "never schedule meetings before 9am"). It asserts that:
  - the agent called `edit_file` on its memories file;
  - the final message confirms the update (checked by an LLM judge);
  - the memories file contains the rule (checked with a regex or an LLM judge).
  - Source: [LangChain blog, Dec 2025](https://www.langchain.com/blog/evaluating-deep-agents-our-learnings)

**"How we build evals for Deep Agents" (2026-03-26)**
- Authors: Trivedy, Daugherty, Yurtsev and Chase. Two principles: "More evals ≠ better agents" and "Every eval is a vector that shifts the behavior of your agentic system." — [LangChain blog, 2026-03-26](https://www.langchain.com/blog/how-we-build-evals-for-deep-agents)
- Each eval has a docstring and a category tag, and all runs go to a shared LangSmith project. SDK plumbing tests (prompt passthrough, interrupt config, subagent routing) are kept separate from capability evals. — [LangChain blog, 2026-03-26](https://www.langchain.com/blog/how-we-build-evals-for-deep-agents)
- Data sources:
  - Dogfooding, with traces mined using Polly/Insights or the LangSmith CLI. Open SWE traces are a major source.
  - Tasks adapted from BFCL and from Terminal Bench 2.0 (run through Harbor).
  - Hand-written behavior tests.
  - Source: [LangChain blog, 2026-03-26](https://www.langchain.com/blog/how-we-build-evals-for-deep-agents)
- Categories: `file_operations`, `retrieval`, `tool_use`, `memory`, `conversation`, `summarization` and `unit_tests`. Some evals take 10+ turns with a simulated user. — [LangChain blog, 2026-03-26](https://www.langchain.com/blog/how-we-build-evals-for-deep-agents)
- Metrics:
  - Correctness: custom assertions, exact match, or an LLM judge.
  - Step ratio: observed steps divided by ideal steps.
  - Tool-call ratio: observed tool calls divided by ideal tool calls.
  - Latency ratio: observed latency divided by ideal latency.
  - Solve rate: expected steps divided by observed latency, and 0 if the task is unsolved.
  - Worked example: the ideal run took 4 steps, 4 calls and about 8 s. An inefficient run took 6 steps, 5 calls and about 14 s, giving ratios of 1.5, 1.25 and 1.75 and a solve rate of about 0.29.
  - The approach is correctness first, then efficiency among the models that are accurate enough. For open-ended tasks, the ideal trajectory is approximated from the best model seen so far.
  - Source: [LangChain blog, 2026-03-26](https://www.langchain.com/blog/how-we-build-evals-for-deep-agents)
- Execution and cost: evals run with pytest in GitHub Actions, and tag-based subsets control cost. The eval code is open source at `libs/evals` in the deepagents repo, and many models are run, including `baseten:nvidia/zai-org/GLM-5`. — [LangChain blog, 2026-03-26](https://www.langchain.com/blog/how-we-build-evals-for-deep-agents)
- A May 2026 AWS write-up describes five evaluation patterns for deep agents using pytest and LangSmith. Only a third-party mirror was found. — [HKU SPACE AI Hub mirror](https://aihub.hkuspace.hku.hk/2026/05/29/evaluating-deep-agents-using-langsmith-on-aws/)

### Inferences
- The shared package needs four runner modes:
  1. `single_step`: run until the tools-node interrupt and assert on the pending `tool_calls`.
  2. `full_run`: assert on the trajectory, the final message and the state, including the DeepAgents virtual filesystem and any files.
  3. `multi_turn_scripted`: gate each turn and fail early.
  4. `multi_turn_simulated`: use openevals `run_multiturn_simulation`.
- Every run needs fresh-environment fixtures: a temp directory or sandbox backend, a fresh checkpointer or thread_id, and a VCR cassette.
- The `libs/evals` code in the deepagents repo is the closest reference implementation to copy patterns from.

### Gaps
- The `libs/evals` source in the deepagents repo was not inspected directly, so its exact fixtures and pytest markers are unconfirmed.
- The original AWS blog post was not fetched; only a mirror was found.

---

## Q3. Other frameworks: DeepEval, Ragas, Inspect AI, Langfuse, Phoenix, promptfoo, MLflow

### Takeaway
For self-hosting:
- Langfuse (core features MIT, including LLM-as-judge, datasets, experiments and annotation queues) and MLflow are the strongest fully self-hostable trace, dataset and online-eval backends.
- DeepEval has the richest agentic metric library (Task Completion, Tool Correctness, Argument Correctness, Step Efficiency, Plan Adherence and Plan Quality, plus G-Eval and DAG) and runs locally with a pytest runner. Its hosted UI is Confident AI.
- Ragas is strongest for RAG and has some tool metrics.
- Inspect AI is best for sandboxed agentic benchmark-style tasks.
- Phoenix is OTel-native and self-hostable.

A pragmatic stack is openevals and agentevals primitives, plus selective DeepEval and Ragas metrics behind a common interface, with Langfuse or MLflow (self-hosted) or LangSmith (Enterprise) as the system of record.

### Cited Findings
**DeepEval (4.3.2, 2026-10-27)**
- Metric families:
  - Custom: G-Eval, JevEval, DAG, Arena G-Eval.
  - Agent trajectory: Task Completion, Step Efficiency, Plan Adherence, Plan Quality.
  - Agent component: Tool Correctness, Argument Correctness.
  - RAG: Contextual Relevancy, Precision and Recall; Answer Relevancy; Faithfulness.
  - Multi-turn: Knowledge Retention, Role Adherence, Conversation Completeness, Conversation Relevancy.
  - Safety: Bias, Toxicity, PII Leakage, and others.
  - Source: [DeepEval metrics intro](https://deepeval.com/docs/metrics-introduction)
- Scoring:
  - Scores run from 0 to 1 with a reason. The default `threshold` is 0.5, and `threshold=None` runs score-only.
  - `strict_mode` forces a binary score.
  - A `flaky` metric's failure does not fail the test case.
  - Source: [DeepEval metrics intro](https://deepeval.com/docs/metrics-introduction)
- G-Eval generates evaluation steps from natural-language criteria. DAG is a decision-tree metric for objective or mixed criteria and can give deterministic scores. — [DeepEval metrics intro](https://deepeval.com/docs/metrics-introduction)
- Ways to run:
  - `evaluate()`, or `deepeval test run` (the native pytest runner for CI).
  - Trajectory metrics through `evals_iterator()`.
  - Component-level metrics with `@observe()` and `update_current_span()`.
  - A single metric with `metric.measure()`.
  - Confident AI provides the UI and production monitoring, and can turn failing traces into goldens.
  - Source: [DeepEval metrics intro](https://deepeval.com/docs/metrics-introduction)

**Ragas (0.4.3, 2026-01-13)**
- Metrics:
  - RAG: Context Precision, Context Recall, Context Entities Recall, Noise Sensitivity, Response Relevancy, Faithfulness.
  - NVIDIA: Answer Accuracy, Context Relevance, Response Groundedness.
  - Agents: Topic Adherence, Tool Call Accuracy, Tool Call F1, Agent Goal Accuracy.
  - General: Aspect Critic, Simple Criteria, Rubrics-based scoring, Instance-specific rubrics.
  - Also SQL and string/BLEU/ROUGE metrics.
  - Source: [Ragas available metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)

**Inspect AI (0.3.287, 2026-10-31; UK AISI and Meridian Labs)**
- An evaluation is a Task made of a Dataset (`input` and `target`), a Solver (`generate()` or an agent such as `react()`) and a Scorer (for example `model_graded_qa()`). — [Inspect AI](https://inspect.aisi.org.uk/)
- Other features:
  - Sandboxes: Docker, Kubernetes, Modal, Proxmox and others.
  - The Inspect View log viewer.
  - Eval sets with retries, limits and parallelism.
  - Over 200 ready-made benchmarks.
  - Support for running external agents such as Claude Code, Codex CLI and Gemini CLI. LangChain is not named.
  - Source: [Inspect AI](https://inspect.aisi.org.uk/)

**Langfuse (SDK 5.1.0, 2026-10-30)**
- Evaluation features: online and offline LLM-as-judge, decision-model and code evaluators, datasets and experiments (UI, SDK or OTel), annotation queues, scores through API/SDK, user feedback, and score analytics that include human-vs-AI agreement and judge calibration. — [Langfuse evaluation overview](https://langfuse.com/docs/evaluation/overview)
- For CI, the `langfuse/experiment-action` GitHub Action runs on `pull_request`. The experiment script raises `RegressionError` when a score breaks a threshold, which fails the job. It works with both cloud and self-hosted Langfuse. — [Langfuse evaluation overview](https://langfuse.com/docs/evaluation/overview)
- "All core Langfuse features and APIs are available in Langfuse OSS (MIT licensed) without any limits." Evaluators, annotation queues, datasets, experiments and the playground are not in the Enterprise list; Protected Prompt Labels is an Enterprise feature. — [Langfuse license key page](https://langfuse.com/self-hosting/license-key)

**Arize Phoenix (21.0.0; phoenix-evals 3.9.5)**
- Evals can run client-side through the SDKs or server-side, configured in the UI and attached to datasets. — [Phoenix LLM evals](https://arize.com/docs/phoenix/evaluation/llm-evals)
- Other features:
  - Code evaluators and LLM-judge evaluators.
  - Adapters for OpenAI, LiteLLM, LangChain and the AI SDK.
  - Prebuilt metrics for RAG and tool-calling agents.
  - Labels returned through tool calling and mapped to scores.
  - Executors with retry and dynamic concurrency.
  - Evaluator runs traced via OTel.
  - Source: [Phoenix LLM evals](https://arize.com/docs/phoenix/evaluation/llm-evals)

**MLflow (3.17.2, 2026-10-21)**
- `mlflow.genai.evaluate(data, predict_fn, scorers)` combines evaluation datasets, human feedback on traces, built-in and custom LLM judges, `@scorer` code scorers and production monitoring. — [MLflow GenAI eval & monitor](https://mlflow.org/docs/latest/genai/eval-monitor/)
- Judges:
  - Built-in judges include `Correctness`, `RetrievalGroundedness`, Safety and `Guidelines`.
  - Custom and trace-based judges can be defined.
  - "Automatic Judge Alignment" uses DSPy.
  - Judges are versioned, and `list_scorers`/`get_scorer` retrieve them.
  - Source: [MLflow scorers](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/)

**promptfoo (npm 0.125.1)**
- The version was confirmed from the npm registry. No feature pages were fetched; see Gaps.

### Inferences
| Framework | Best at | Self-host | Fit for a shared LangGraph eval package |
|---|---|---|---|
| openevals / agentevals | Judge factories, trajectory match, LangGraph graph trajectory, multi-turn sim | Library (no server) | Core primitives |
| LangSmith | Datasets, experiments, pytest logging, annotation queues, online evaluators; native LangGraph traces | Enterprise license only | Default backend if licensed |
| Langfuse | OSS traces, datasets, experiments, judges, annotation queues, CI action | Yes (MIT core) | Best self-hosted backend |
| MLflow GenAI | evaluate, judges with alignment, monitoring | Yes (OSS) | Alternative backend, especially for Databricks shops |
| DeepEval | Agentic and RAG metric library, G-Eval, DAG, pytest runner | Library is local; UI is Confident AI | Pull in metrics behind an adapter |
| Ragas | RAG metrics, rubric scoring, tool-call F1 | Library | RAG metrics adapter |
| Inspect AI | Sandboxed agentic benchmarks, log viewer | Fully local | Capability benchmarks and safety evals |
| Phoenix | OTel-native traces and evals | Yes | Alternative backend |

### Gaps
- The licenses for DeepEval, Ragas, Inspect, Phoenix (believed to be ELv2), promptfoo and MLflow were not verified on the pages fetched in this session.
- No promptfoo feature or ownership details were fetched. There are recollected reports of a 2026 acquisition by OpenAI that are unverified and should be confirmed before citing.
- The DeepEval ConversationSimulator, the Synthesizer, and Ragas test-set generation were not covered on the fetched pages; check their docs.

---

## Q4. Rubric-based grading best practices (binary checks, calibration, bias, reasoning judges)

### Takeaway
Use binary pass/fail judges with written critiques, one judge per dimension, and an "unknown" option. Calibrate each judge against labels from a single domain expert, using train/dev/test splits, and report TPR and TNR rather than raw agreement. Prefer deterministic graders wherever possible and grade outcomes rather than paths.

### Cited Findings
- Use binary pass/fail with a critique instead of 1–5 Likert scales, which are hard to act on. — [Hamel Husain, LLM judge guide](https://hamel.dev/blog/posts/llm-judge/)
- Process:
  - One principal domain expert does "critique shadowing", writing detailed critiques for each verdict.
  - Error analysis on about 30+ diverse traces comes first, until no new failure modes appear.
  - Fix pervasive errors in the system before building a judge.
  - Source: [Hamel Husain](https://hamel.dev/blog/posts/llm-judge/)
- Calibration:
  - Split labeled data into roughly 10–20% train (used for few-shot examples) and 40–45% each for dev and test.
  - Aim for 30–50 Pass and 30–50 Fail examples.
  - Freeze the prompt before running on the test set.
  - Measure TPR and TNR, not raw agreement: an always-pass judge scores 95% agreement at a 5% error rate while catching nothing.
  - Below about 60 labels, confidence intervals are too wide to draw conclusions.
  - One case reached over 90% agreement in three iterations.
  - Source: [Hamel Husain](https://hamel.dev/blog/posts/llm-judge/)
- Use the strongest judge model the budget allows. Avoid fine-tuning judges by default. Turn each fixed error into a regression test. — [Hamel Husain](https://hamel.dev/blog/posts/llm-judge/)
- Anthropic's agent eval guidance (2026-01-09):
  - Grader types: code (fast, objective, brittle), model (flexible, needs calibration) and human (gold standard, used sparingly).
  - Grade the outcome, not the exact path, and give partial credit for multi-part tasks.
  - Give LLM judges an "unknown" option and use a separate judge per dimension.
  - Make graders resistant to hacks.
  - Read transcripts to tell agent failures from grader false negatives.
  - Source: [Anthropic, Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- Tool support for calibration:
  - Langfuse score analytics compares human and AI agreement and has a judge-calibration guide. — [Langfuse](https://langfuse.com/docs/evaluation/overview)
  - MLflow has DSPy-based automatic judge alignment and judge versioning. — [MLflow scorers](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/)
  - openevals exposes `use_reasoning`, `few_shot_examples` and `choices`/`continuous` for judge configuration. — [openevals README](https://raw.githubusercontent.com/langchain-ai/openevals/main/README.md)
  - DeepEval's `strict_mode` forces binary scores, and DAG gives deterministic decision trees. — [DeepEval](https://deepeval.com/docs/metrics-introduction)

### Inferences
- Rubric schema for the package: `Rubric{criteria: [Criterion{id, question, pass_definition, fail_definition, examples[], allow_unknown}]}`. Each criterion maps to its own binary judge call, and scores are aggregated as a weighted pass fraction (an analytic rubric).
- Every registered judge should carry calibration metadata: a labeled set version, TPR, TNR and the judge model. CI should refuse to gate on judges that have not been calibrated.
- Bias mitigations (positional-bias swaps in pairwise judging, length-bias controls, and using a different model family from the agent's) are standard practice, but no primary source on them was fetched in this session. See Gaps.

### Gaps
- No primary sources were fetched on position, verbosity or self-preference bias, on whether reasoning models such as o-series or extended-thinking models make better judges, or on Eugene Yan's evaluator write-ups.

---

## Q5. Golden dataset creation (synthetic, trace mining, annotation queues, versioning, splits)

### Takeaway
Start small with 10–50 tasks drawn from real failures. Grow the set from production traces (negative feedback, dogfooding) and annotation queues, and fill coverage gaps with synthetic inputs varied by feature, scenario and persona. Version datasets immutably, pin versions in CI, use (possibly overlapping) splits, and balance positive and negative cases.

### Cited Findings
- LangSmith:
  - Start with 10–20 curated examples, then add examples from historical traces and synthetic templates.
  - Splits can overlap.
  - Versions are created automatically, can be tagged, and can be pinned in CI.
  - Annotation queues export reviewed runs to datasets.
  - Source: [LangSmith evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts)
- Anthropic:
  - 20–50 tasks drawn from real failures is a strong start.
  - Sources: manual pre-release checks, then the bug tracker and support queue.
  - Write unambiguous tasks with reference solutions.
  - Test both cases where a behavior should occur and cases where it shouldn't.
  - Capability evals graduate into regression suites once they saturate.
  - Source: [Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- Hamel Husain: build diverse data across features, scenarios and personas. Use real interactions where possible and LLM-generated inputs to fill gaps. — [Hamel Husain](https://hamel.dev/blog/posts/llm-judge/)
- LangChain Deep Agents: eval sources are dogfooding traces (mined with Polly/Insights or the LangSmith CLI, especially Open SWE), adapted benchmarks (BFCL, Terminal Bench 2.0) and hand-written tests. — [LangChain blog, 2026-03-26](https://www.langchain.com/blog/how-we-build-evals-for-deep-agents)
- DeepEval/Confident AI can turn failing production traces into goldens. — [DeepEval](https://deepeval.com/docs/metrics-introduction)

### Inferences
- The package should provide:
  - `datasets.from_traces(backend, filter)`: mine negative-feedback or low online-score traces into candidate examples.
  - `datasets.synthesize(dimensions={feature, scenario, persona}, n)`: generate synthetic inputs from a persona/scenario matrix.
  - An annotation export/import round-trip.
  - A local, git-versioned JSONL/YAML format (content-hashed) that syncs to the LangSmith, Langfuse or MLflow datasets.
- Each example carries `tags`/`category`, `split` (smoke, regression, capability, holdout), `env_fixture`, `reference_outputs` and `rubric_id` fields.

### Gaps
- The DeepEval Synthesizer, Ragas TestsetGenerator (knowledge-graph-based) and the LangSmith synthetic-generation APIs were not fetched in this session.

---

## Q6. CI/CD integration, eval-driven development, thresholds and gates, cost control

### Takeaway
Run evals as pytest in CI, gated by tags and splits. Use a cheap smoke and regression subset on every PR and the full or capability suite nightly. Gate on baseline comparison or absolute thresholds per metric, and run multiple trials where outcomes vary (pass^k for consistency). Control cost with tag subsets, single-step tests, VCR replay and spend limits on online evaluators.

### Cited Findings
- Deep Agents evals run with pytest in GitHub Actions, using tag subsets (for example `file_operations`, `tool_use`) to cut cost. — [LangChain blog, 2026-03-26](https://www.langchain.com/blog/how-we-build-evals-for-deep-agents)
- Single-step tests save tokens. VCR replay of external APIs makes runs reproducible. — [LangChain blog, Dec 2025](https://www.langchain.com/blog/evaluating-deep-agents-our-learnings)
- Regression gates:
  - LangSmith regression tests can assert that a version beats a baseline, and dataset versions can be pinned in CI. — [LangSmith concepts](https://docs.langchain.com/langsmith/evaluation-concepts)
  - Langfuse's `experiment-action` fails the PR when a script raises `RegressionError`. — [Langfuse](https://langfuse.com/docs/evaluation/overview)
  - DeepEval's `deepeval test run` provides thresholds and flaky metrics. — [DeepEval](https://deepeval.com/docs/metrics-introduction)
- pass@k is the chance of at least one success in k trials. pass^k is the chance that all k succeed: at a 75% per-trial rate, pass^3 is about 42%. Regression evals should be near 100%, while capability evals start low. — [Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- Online-evaluator sampling rates and spend limits are set per project. — [LangSmith concepts](https://docs.langchain.com/langsmith/evaluation-concepts)

### Inferences
Suggested CI tiers:
- **PR:** the `smoke` split, single-step tests and deterministic graders, with VCR on.
- **Merge to main:** the `regression` split with calibrated judges; gate at no metric drop below baseline minus tolerance.
- **Nightly:** the capability suite with k trials across candidate models, reporting efficiency ratios.

Cache judge results keyed on (judge version, input hash, output hash) to avoid paying for repeated judge calls.

### Gaps
- No primary source gave statistical guidance on tolerance or significance for gates (for example, bootstrap CIs on small datasets).

---

## Q7. Proposed architecture for a shared `evals` package

### Takeaway
Build a thin, backend-neutral core with these parts:
- A metric interface compatible with openevals `EvaluatorResult`.
- An evaluator registry.
- Runner adapters for LangChain v1 `create_agent`, generic LangGraph graphs and DeepAgents, covering single-step, full-run and multi-turn modes.
- Environment fixtures.
- A dataset format with sync adapters.
- Pluggable sinks: local JSON/HTML, LangSmith, Langfuse and MLflow.

### Cited Findings (design inputs)
- openevals evaluators take `inputs`, `outputs` and `reference_outputs` and return feedback with a key and score, and `client.evaluate` accepts them directly. — [openevals README](https://raw.githubusercontent.com/langchain-ai/openevals/main/README.md)
- `extract_langgraph_trajectory_from_thread` gives node-level trajectories for LangGraph. — [agentevals](https://github.com/langchain-ai/agentevals)
- Single-step evals use an interrupt before the tools node. State and file assertions are needed for DeepAgents. — [LangChain blog, Dec 2025](https://www.langchain.com/blog/evaluating-deep-agents-our-learnings)
- Efficiency metrics (step, tool-call and latency ratios, and solve rate) are measured against an ideal trajectory. — [LangChain blog, 2026-03-26](https://www.langchain.com/blog/how-we-build-evals-for-deep-agents)
- The Langfuse core (evaluators, datasets, experiments, queues) is MIT and self-hostable. Self-hosted LangSmith needs an Enterprise license. — [Langfuse](https://langfuse.com/self-hosting/license-key), [LangChain KB](https://support.langchain.com/articles/7011309930-how-do-i-obtain-a-self-hosted-langsmith-license-key)

### Inferences (proposed design)
```
evals/
  core/
    types.py        # EvalCase, AgentRun(trajectory: list[BaseMessage], final, state, files, node_path,
                    #   usage, latency), Score(key, value, passed, comment, metadata)
    metric.py       # Protocol: __call__(*, inputs, outputs, reference_outputs, run: AgentRun) -> Score|list[Score]
    registry.py     # @register("tool_correctness", kind="deterministic"|"llm_judge"|"human", version="1.2")
    rubric.py       # analytic rubric -> per-criterion binary judges (openevals create_llm_as_judge)
    calibration.py  # TPR/TNR vs human labels, stores judge cards
  metrics/
    deterministic/  # exact/json match, regex, file-exists, state-key asserts, trajectory_match (openevals)
    trajectory/     # strict/unordered/subset/superset, graph_trajectory, efficiency ratios, solve_rate
    judges/         # correctness, groundedness, plan_adherence, trajectory_accuracy (openevals prompts)
    rag/            # wrappers around openevals RAG_* + optional ragas/deepeval adapters
    adapters/       # deepeval_metric(...), ragas_metric(...) -> Metric protocol
  runners/
    langgraph.py    # run(graph, case, mode="single_step"|"full_run"); interrupt_before=["tools"]
    deepagents.py   # fresh backend/sandbox + virtual FS capture; subagent trace capture
    multiturn.py    # openevals run_multiturn_simulation + scripted-gated mode
    env.py          # pytest fixtures: tmpdir, sandbox, fresh checkpointer/thread_id, VCR cassettes
  datasets/
    schema.py       # JSONL/YAML, content-hashed versions, splits, tags, rubric_id
    synth.py, mine.py (from traces), sync/{langsmith,langfuse,mlflow}.py
  reporting/
    sinks/{local_json,html,junit,langsmith,langfuse,mlflow}.py
    compare.py      # baseline diff, pass@k / pass^k, thresholds -> exit code
  online/
    sampler.py      # sample prod traces, run registered reference-free judges, write scores back
  pytest_plugin.py  # markers: @evals.case(tags=[...], split="smoke"), --evals-backend, --evals-trials k
```
- Use a single trace format, OpenTelemetry/LangChain callbacks, so the same `AgentRun` can be built from a live run or from a stored production trace. That lets the online and offline evaluators share code.
- Make the backend a config switch (`EVALS_BACKEND=local|langsmith|langfuse|mlflow`) so teams can avoid managed-service lock-in.
- Pin `openevals` (≥0.2.2). Vendor the small graph-trajectory pieces from agentevals 0.0.9.

### Gaps
- No public reference implementation of a multi-team shared eval package for LangGraph was found. The design above is synthesized from the sources rather than copied from a single one.
