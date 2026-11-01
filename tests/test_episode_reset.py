"""Execute the real reset slice with synthetic state; no model or GPU required."""

import ast, sys, types, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def reset_slice(text):
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        start = end = None
        for i, item in enumerate(node.body):
            if isinstance(item, ast.Assign):
                rendered = ast.unparse(item)
                if rendered == "stats_episodes[ep_id] = infos[i]":
                    start = i + 1
                if rendered == "observations[i] = envs.reset_at(i)[0]":
                    end = i
        if start is not None and end is not None:
            return ast.Module(body=node.body[start:end], type_ignores=[])
    raise AssertionError("Could not find official episode reset boundary")


class Reset(unittest.TestCase):
    def trainer_tree(self):
        source = ROOT / "src/vlnce_baselines/awarevln_trainer.py"
        if not source.exists():
            self.skipTest("Source installation is gated on archive completion")
        return ast.parse(source.read_text())

    def test_recording_interface_matches_runtime(self):
        sys.path.insert(0, str(ROOT / "src"))
        from case1_runtime.trace import TraceRecorder

        names = {
            node.func.attr
            for node in ast.walk(self.trainer_tree())
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in ("recorder", "TraceRecorder")
        }
        for name in names:
            self.assertTrue(callable(getattr(TraceRecorder, name, None)), name)

    def test_input_receipt_precedes_generation(self):
        nodes = [node for node in ast.walk(self.trainer_tree()) if isinstance(node, ast.Call)]

        def line(owner, name):
            found = [
                node.lineno
                for node in nodes
                if isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == owner
                and node.func.attr == name
            ]
            self.assertEqual(len(found), 1)
            return found[0]

        self.assertLess(line("recorder", "begin_model_call"), line("model", "generate"))
        self.assertLess(line("model", "generate"), line("recorder", "finish_model_call"))

    def test_state_cannot_cross_episode_boundary(self):
        source = ROOT / "src/vlnce_baselines/awarevln_trainer.py"
        if not source.exists():
            self.skipTest("Source installation is gated on archive completion")
        fake = types.SimpleNamespace(seed=lambda _: None, manual_seed=lambda _: None)
        ended = []
        state = dict(
            hamlet=types.SimpleNamespace(end_episode=lambda episode: ended.append(episode)),
            ep_id="episode-A",
            queue_actions=[1, 1],
            last_reasoning="old",
            last_reason_step=8,
            frame_id=10,
            reason_stuck_num=2,
            reasoning_context="old",
            raw_output_content="old",
            random=fake,
            np=types.SimpleNamespace(random=fake),
            torch=fake,
            config=types.SimpleNamespace(TASK_CONFIG=types.SimpleNamespace(SEED=100)),
        )
        exec(
            compile(
                ast.fix_missing_locations(reset_slice(source.read_text())),
                "official-reset-slice",
                "exec",
            ),
            state,
        )
        self.assertEqual(ended, ["episode-A"])
        for name, value in [
            ("queue_actions", []),
            ("last_reasoning", ""),
            ("last_reason_step", 0),
            ("frame_id", 0),
            ("reason_stuck_num", 0),
            ("reasoning_context", ""),
            ("raw_output_content", ""),
        ]:
            self.assertEqual(state[name], value, name)


if __name__ == "__main__":
    unittest.main()
