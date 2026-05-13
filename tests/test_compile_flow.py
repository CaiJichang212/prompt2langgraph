import json
from pathlib import Path
import prompt2langgraph as pt2lg

# Load workflow
workflow = pt2lg.WorkflowSpec.model_validate(
    json.loads((Path('tests/fixtures/linear_llm.json')).read_text(encoding='utf-8'))
)

# Compile
result = pt2lg.compile_workflow(workflow, out_dir=Path('/tmp/test_compile'))

# Check manifest
manifest = json.loads((result.output_dir / 'manifest.json').read_text(encoding='utf-8'))
print('Manifest keys:', list(manifest.keys()))
print('Has policy_summary:', 'policy_summary' in manifest)
if 'policy_summary' in manifest:
    print('Policy summary keys:', list(manifest['policy_summary'].keys()))
    print('Node policies:', list(manifest['policy_summary']['node_policies'].keys()))

# Check compile_report
report = json.loads((result.output_dir / 'compile_report.json').read_text(encoding='utf-8'))
print('\nCompile report keys:', list(report.keys()))
print('Has binding_summary:', 'binding_summary' in report)
if 'binding_summary' in report:
    print('Binding summary keys:', list(report['binding_summary'].keys()))
    print('Executor bindings:', list(report['binding_summary']['executor_bindings'].keys()))

# Check timings
print('\nTimings:', list(report['timings_ms'].keys()))
