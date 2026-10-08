"""One real role run through DockerOpenClawRunner.run, no conductor cycle.
Keeps a copy of the run's openclaw state dir so the system prompt can be read.
Usage: python verify_driver.py <role> <keep_dir> <prompt>"""
import asyncio
import shutil
import sys
from pathlib import Path

from conductor import runner as runner_mod
from conductor.config import load_config
from conductor.runner import DockerOpenClawRunner

role, keep, prompt = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
cfg = load_config()
_real_rmtree = shutil.rmtree


def _keep_then_remove(path, *a, **k):
    if Path(path).exists():
        shutil.copytree(path, keep / Path(path).name, dirs_exist_ok=True)
    _real_rmtree(path, *a, **k)


runner_mod.shutil.rmtree = _keep_then_remove
r = DockerOpenClawRunner(
    pinned_config_dir=cfg.pinned_config_dir, openclaw_state_dir=cfg.openclaw_state_dir,
    workspace_root=cfg.workspace_root, secrets_env_file=cfg.secrets_env_file,
    thinking_state_root=cfg.thinking_state_root,
)
charter = (Path("agents") / role / "role.md").read_text(encoding="utf-8")
res = asyncio.run(r.run(role, prompt, model=cfg.models[role], timeout_seconds=300, charter=charter))
print("STATUS", res.status, "ok", res.ok, "cost", res.cost_usd, "err", res.error)
print("ANSWER", res.final_answer)
