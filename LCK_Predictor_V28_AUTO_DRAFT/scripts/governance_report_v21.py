from pathlib import Path
import importlib.util, json
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('lck_server_v21',ROOT/'server.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.v21_ensure_schema()
report=m.v21_governance_summary()
print(json.dumps(report,ensure_ascii=False,indent=2))
