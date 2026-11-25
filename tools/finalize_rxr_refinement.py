"""Exact work-branch integration corrections; removed after source materialization."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = '5a03ef2aa980f6fc4ca8750756cb455c703105bf'
updates = {}


def old(path):
    return subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=ROOT).decode()


def replace(text, before, after, count=1):
    if text.count(before) != count:
        raise ValueError('Unexpected source: ' + before[:100])
    return text.replace(before, after)


def edit(path, transform):
    source = old(path)
    content = transform(source)
    if (ROOT / path).read_text() not in (source, content):
        raise ValueError('Refuse independent source change: ' + path)
    updates[path] = content


def run_patch(text):
    text = replace(text, 'def request(role, phase, payload, pin, profile, selected_ids):',
                   'def request(role, phase, payload, pin, profile, selected_ids, *, selection_mode="adaptive"):')
    text = replace(text, '        original_instruction=payload.get("original_instruction")\n',
                   '        original_instruction=payload.get("original_instruction"),\n        selection_mode=selection_mode\n')
    return replace(text, '        req = request(role, phase, payload, pins[role], src.profile, selections[role])',
                   '        req = request(role, phase, payload, pins[role], src.profile, selections[role],\n                      selection_mode=selection_mode)')


def role_patch(text):
    start = text.index('Repair entry gate:')
    end = text.index('### Oral repetition', start)
    paragraphs = text[start:end].rstrip()
    text = text[:start] + text[end:]
    return replace(text, '## P2 — Existing scene-dependent calibration',
                   paragraphs + '\n\n## P2 — Existing scene-dependent calibration')


def preservation_patch(text):
    text = replace(text, '    changed_templates = []\n', '    changed_templates = []\n    legacy_count = 0\n')
    text = replace(text, '    for path in files:\n        old = json.loads(git(\'show\', BASE + \':\' + path))',
        '    for path in files:\n'
        '        if "/legacy/" in path:\n'
        '            if (ROOT / path).read_bytes() != git("show", BASE + ":" + path):\n'
        '                raise ValueError("Historical RxR provenance changed: " + path)\n'
        '            legacy_count += 1\n'
        '            continue\n'
        '        old = json.loads(git(\'show\', BASE + \':\' + path))')
    return replace(text, 'rxr_templates_checked=len(files), changed_template_ids=sorted(changed_templates)',
                   'rxr_templates_checked=len(files) - legacy_count,\n                legacy_templates_checked=legacy_count, changed_template_ids=sorted(changed_templates)')


def injection_patch(text):
    return replace(text, '                    expects_detailed = is_fixed_core or is_first_dynamic',
        '                    expects_detailed = is_fixed_core or (\n'
        '                        c["template_id"] in ids[:2] if profile == "rxr-en-us" else is_first_dynamic)')


def metadata_patch(text):
    return replace(text, '            "host/rxr_assets.py",\n',
                   '            "host/rxr_assets.py",\n            "host/rxr_teaching.py",\n            "host/rxr_contract.py",\n')


def profile_patch(text):
    text = replace(text, 'self.assertEqual(len(rxr["files"]), 7)', 'self.assertEqual(len(rxr["files"]), 9)')
    return replace(text, 'self.assertEqual(len(metadata["files"]), 7)', 'self.assertEqual(len(metadata["files"]), 9)')


def test_patch(text):
    text = replace(text, 'from shared.identity import canonical\n', 'from shared.identity import canonical, ContractError\n')
    text = replace(text, 'with self.assertRaises(Exception):', 'with self.assertRaises(ContractError):', count=3)
    text = replace(text, "        self.assertEqual(report['rxr_templates_checked'], 143)",
                   "        self.assertEqual(report['rxr_templates_checked'], 143)\n        self.assertEqual(report['legacy_templates_checked'], 20)")
    return replace(text, "        self.assertIn('textual change is not a prerequisite', text)",
                   "        self.assertIn('textual change is not a prerequisite', text)\n"
                   "        generator = (ROOT / 'generator/dataset_rules/rxr_en_us.md').read_text()\n"
                   "        for marker in ('Repair entry gate:', 'Teaching delivery:'):\n"
                   "            self.assertLess(generator.index(marker), generator.index('## P2'))")


def readme_patch(text):
    text = replace(text, '## 入口文档\n',
        '## 入口文档\n\n- `docs/RXR_REFINEMENT.md`：当前 RxR 角色操作、证据修复、前两条完整动态教学、摘要保真与隔离验证说明。\n')
    text = replace(text, '## 当前工程状态\n',
        '## 当前工程状态\n\n'
        '**当前增量修复。** 在已完成的角色层次转换上，补充 P2 的触发条件、父框架、局部操作与保护边界；修正 006/023/027、Core 06 及相关诊断的教学证据，不改原始指令、候选正文、边界、检索权重和选例数量。RxR 前两条动态案例完整加载，其余摘要保留完整 source/candidate、五要素、条件、Handoff 与 Finding/repair；仅去除重复过程叙述和部分重复层结论。\n\n'
        '新增运行职责位于 `host/rxr_teaching.py`、`host/rxr_contract.py`；离线修复规格位于 `tools/rxr_teaching_alignment.py`。公共合同、Schema、通用 Prompt 与 R2R 路径不改，Host/Compiler 仅增加 RxR 条件派发。当前证据及文件归属以 `docs/RXR_REFINEMENT.md` 为准；以下段落保留此前结构转换的范围说明，不应误读为本轮仍未修改 Compiler 或教学投影。\n\n')
    return text


edit('host/run.py', run_patch)
edit('generator/dataset_rules/rxr_en_us.md', role_patch)
edit('tools/check_rxr_refinement.py', preservation_patch)
edit('tests/test_example_injection.py', injection_patch)
edit('tests/test_r2r_specialization.py', metadata_patch)
edit('tests/test_rxr_profile.py', profile_patch)
edit('tests/test_rxr_refinement.py', test_patch)
edit('README.md', readme_patch)
for name in ('RXR_ROLE_HIERARCHY', 'RXR_TEACHING_REPAIR', 'RXR_TEACHING_FOCUS', 'RXR_FINAL_CHECKS'):
    path = 'docs/' + name + '.md'
    edit(path, lambda text: text.split('\n', 1)[0] + '\n\n'
        '> Scope note: this document records the preceding conversion/calibration. The subsequent source-preserving evidence repairs and first-two-detailed Dynamic policy are specified in `docs/RXR_REFINEMENT.md`; do not treat the earlier projection/compiler freeze as the current refinement scope.\n\n'
        + text.split('\n', 1)[1].lstrip('\n'))
manifest = json.loads(old('provenance/rxr_role_conversion.json'))
raw = updates['generator/dataset_rules/rxr_en_us.md'].encode()
manifest['roles']['generator']['new_sha256'] = hashlib.sha256(raw).hexdigest()
manifest['roles']['generator']['new_bytes'] = len(raw)
updates['provenance/rxr_role_conversion.json'] = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
for path, content in updates.items():
    if path.endswith('.py'):
        compile(content, path, 'exec')
for path, content in updates.items():
    (ROOT / path).write_text(content)
print(json.dumps({'reviewed_integration_paths': sorted(updates)}))
