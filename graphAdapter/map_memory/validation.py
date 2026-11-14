"""Named CPU component contracts;live shadow G13 and deployment scope stay explicit."""
from pathlib import Path
import sys,json,subprocess,xml.etree.ElementTree as ET,os
ROOT=Path(__file__).resolve().parents[3]
def run_cpu(out):
    out=Path(out).absolute();out.mkdir(parents=True,exist_ok=False)
    tests=ROOT/"src/graphAdapter/map_memory/tests"
    names=["test_geometry.py","test_storage.py","test_service.py","test_perception.py",
           "test_service_integration.py","test_visualization.py","test_evaluation.py","test_scene_assets.py","test_lifecycle.py","test_routing.py","test_mapping_interfaces.py"]
    command=[str(ROOT/"runtime/graph_memory/perception/bin/python"),"-I","-B",str(Path(__file__).resolve()),
        "--worker","--out",str(out),*[str(tests/name)for name in names]]
    with(out/"pytest.log").open("x")as log:result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    cases=[]
    if(out/"junit.xml").exists():
        for case in ET.parse(out/"junit.xml").findall(".//testcase"):
            failed=case.find("failure");error=case.find("error");skip=case.find("skipped")
            cases.append(dict(id=case.attrib["name"],status="FAIL"if failed is not None or error is not None else"SKIP"if skip is not None else"PASS",
                expected="All named source/contract assertions hold",actual=(failed.text if failed is not None else error.text if error is not None else"Named assertions satisfied"),
                scope="CPU_actual_components_or_explicit_camera_fixtures"))
    report=dict(successful=result.returncode==0,exit_code=result.returncode,tests=cases,
        scope="CPUcontracts only;not complete stage001 deployment/navigation",
        deployment_shadow_G13="NOT_RUN_BY_CPU_SUITE",native_model_capability="separate recorded-source model evidence",
        command=command)
    (out/"test_results.json").write_text(json.dumps(report,indent=2))
    return report

def worker(out,paths):
    sys.path.insert(0,str(ROOT/"runtime/graph_memory/package_root"))
    # CPU controller tests need host APIs;the private model worker does not use this entry.
    sys.path.insert(1,str(ROOT/'src'))
    from graphAdapter.observation_pose.production import SITE
    sys.path.insert(0,str(SITE))
    sys.path.insert(0,str(ROOT/"vendor_sources/EvoMemNav"))
    os.environ["CUDA_VISIBLE_DEVICES"]="-1";os.environ["NUMBA_NUM_THREADS"]="4"
    import pytest
    return pytest.main([*paths,"-q","--basetemp",str(Path(out)/"artifacts"),
        "-o","cache_dir="+str(ROOT/".cache/graph001-check"),"--junitxml",str(Path(out)/"junit.xml")])

if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument("--worker",action="store_true");parser.add_argument("--out",required=True);parser.add_argument("paths",nargs="*")
    args=parser.parse_args()
    raise SystemExit(worker(args.out,args.paths)if args.worker else(0 if run_cpu(args.out)["successful"]else 1))
