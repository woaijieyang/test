"""Execute the unchanged native chunker and compare one/eight-shard coverage."""

import ast, math, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Shards(unittest.TestCase):
    def test_native_shards_preserve_language_filtered_identity(self):
        source = ROOT / "src/habitat_extensions/task.py"
        if not source.exists():
            self.skipTest("Source installation is gated on archive completion")
        tree = ast.parse(source.read_text())
        nodes = [
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name in ("split_list", "get_chunk")
        ]
        self.assertEqual(len(nodes), 2)
        ns = {"math": math}
        exec(
            compile(
                ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                "native-chunker",
                "exec",
            ),
            ns,
        )
        episodes = [
            {"episode_id": str(i), "language": "en-US" if i % 3 == 0 else "en-IN"}
            for i in range(1839)
        ]
        sets = []
        for count in (1, 8):
            observed = []
            for chunk in range(count):
                native = ns["get_chunk"](episodes, count, chunk)
                size = math.ceil(len(episodes) / count)
                self.assertEqual(native, episodes[chunk * size : (chunk + 1) * size])
                observed.extend(e["episode_id"] for e in native if e["language"] == "en-US")
            self.assertEqual(len(observed), len(set(observed)))
            sets.append(observed)
        self.assertEqual(sets[0], sets[1])


if __name__ == "__main__":
    unittest.main()
