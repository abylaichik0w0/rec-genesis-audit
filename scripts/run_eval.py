import json
from pathlib import Path
from typing import Any

from src.env.audit_env import AuditEnv
from src.evaluator.reward import evaluate_submission
from src.generator.pipeline import generate_episode, save_episode
from src.policies.policies import (
    MarkAllAttackPolicy,
    OraclePolicy,
    RandomPolicy,
    RuleBasedPolicy,
)
from src.schemas import FindingsSubmission, Policy, TruthIssue


def evaluator_adapter(
    episode_dir: Path,
    submission: FindingsSubmission,
    inspection_steps: int,
) -> dict[str, Any]:
    truth_raw = json.loads((episode_dir / "truth.json").read_text(encoding="utf-8"))
    issues_list = truth_raw if isinstance(truth_raw, list) else truth_raw.get("issues", [])
    truth_issues = [TruthIssue(**item) for item in issues_list]

    policy_raw = json.loads((episode_dir / "policy.json").read_text(encoding="utf-8"))
    policy = Policy(**policy_raw)

    return evaluate_submission(
        raw_submission=submission,
        expected_episode_id=submission.episode_id,
        truth_issues=truth_issues,
        policy=policy,
        inspection_steps=inspection_steps,
    )


def main() -> None:
    seeds = [101, 102, 103, 104, 105]
    base_dir = Path("data/eval_episodes")
    base_dir.mkdir(parents=True, exist_ok=True)

    # 1. Генерируем реальные эпизоды
    ep_dirs: list[Path] = []
    for seed in seeds:
        ep_id = f"ep_real_{seed}"
        ep_dir = base_dir / ep_id
        episode = generate_episode(
            seed=seed,
            episode_id=ep_id,
            scenario_mode="full",
            num_base_invoices=25,
        )
        save_episode(episode, str(ep_dir))
        ep_dirs.append(ep_dir)

    policies = [
        RandomPolicy(max_explore_steps=5),
        RuleBasedPolicy(),
        MarkAllAttackPolicy(),
        OraclePolicy(),
    ]

    stats: dict[str, list[dict[str, float]]] = {p.name: [] for p in policies}
    demo_steps: list[dict[str, Any]] = []

    # 2. Прогоняем все 4 политики на каждом эпизоде
    for idx, ep_dir in enumerate(ep_dirs):
        for policy in policies:
            env = AuditEnv(evaluator_fn=evaluator_adapter)
            res = policy.run_episode(env, ep_dir, seed=seeds[idx])
            ev = env.last_eval_result or {}

            stats[policy.name].append(
                {
                    "reward": float(res["reward"]),
                    "f1": float(ev.get("f1", 0.0)),
                    "precision": float(ev.get("precision", 0.0)),
                    "recall": float(ev.get("recall", 0.0)),
                    "steps": float(env.steps_taken),
                }
            )

            # Сохраняем в плеер траектории первого реального эпизода (4 политики)
            if idx == 0:
                for step in env.trajectory:
                    d = step.model_dump()
                    d["episode_id"] = f"{d['episode_id']}_{policy.name}"
                    demo_steps.append(d)

    # 3. Выводим итоговую таблицу для README.md
    print(f"\n=== Evaluation Summary ({len(seeds)} generated episodes, 25 invoices each) ===\n")
    print("| Policy | Avg F1 | Avg Precision | Avg Recall | Avg Reward | Avg Steps |")
    print("| :--- | :---: | :---: | :---: | :---: | :---: |")
    for name, rows in stats.items():
        n = len(rows)
        avg_f1 = sum(r["f1"] for r in rows) / n
        avg_p = sum(r["precision"] for r in rows) / n
        avg_r = sum(r["recall"] for r in rows) / n
        avg_rew = sum(r["reward"] for r in rows) / n
        avg_steps = sum(r["steps"] for r in rows) / n
        print(
            f"| `{name}` | {avg_f1:.3f} | {avg_p:.3f} | {avg_r:.3f} | "
            f"{avg_rew:+.3f} | {avg_steps:.1f} |"
        )

    # 4. Сохраняем траектории для demo_ui
    out_path = Path("artifacts/trajectories.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in demo_steps:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nSaved {len(demo_steps)} real trajectory steps to {out_path}")


if __name__ == "__main__":
    main()