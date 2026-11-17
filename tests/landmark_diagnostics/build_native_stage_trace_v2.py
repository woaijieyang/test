"""Instrument native build stages in an isolated copy without changing construction semantics."""
import os,sys,json,subprocess,shlex,shutil,hashlib
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.nice(15)
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
import psutil
usage=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:usage[i])])
R=ROOT;B=R/'upstream/habitat-sim/build';O=R/'outputs/landmark-connectivity/native-stage-trace-xc-v2';C=R/'.cache/native-stage-trace-xc-v2';O.mkdir(exist_ok=False);C.mkdir(exist_ok=False);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
record={'status':'BUILDING_INSTRUMENTED_BINDING','commands':[],'script_sha256':digest(__file__)}
def note(**kw):record.update(kw);atomic_json(O/'state.json',record)
def run(args):
 record['commands'].append(args);note()
 with (O/'build.log').open('ab') as log:subprocess.run(args,cwd=R,stdout=log,stderr=subprocess.STDOUT,check=True)
try:
 source=R/'upstream/habitat-sim/src/esp/nav/PathFinder.cpp';archive=B/'esp/nav/libnav.a';originals={str(p):digest(p) for p in [source,archive,B/'build.ninja',B/'compile_commands.json']};old=source.read_text();s=old.replace('#include <numeric>','#include <numeric>\n#include <fstream>\n#include <sstream>\n#include <iomanip>\n#include <cstdlib>',1)
 marker='  // Step 2. Rasterize input polygon soup.'
 index=s.index(marker,s.index('PathFinder::Impl::build('));index=s.rfind('  //\n',0,index)
 insertion=r"""
  // Case1 diagnostic-only observer. It never modifies any build array/settings.
  const char* traceEnv = std::getenv("CASE1_NAV_TRACE_PREFIX");
  const char* watchEnv = std::getenv("CASE1_NAV_TRACE_WATCH");
  bool traceEnabled = traceEnv && watchEnv &&
      std::string(traceEnv).rfind("/data/zy/vln/case1/outputs/", 0) == 0;
  double watch[3] = {0, 0, 0};
  if (traceEnabled) {
    std::istringstream input(watchEnv);
    traceEnabled = bool(input >> watch[0] >> watch[1] >> watch[2]);
  }
  static unsigned int traceCall = 0;
  std::string traceStem;
  if (traceEnabled) {
    traceStem = std::string(traceEnv) + "-" + std::to_string(++traceCall);
    std::ofstream meshOut(traceStem + ".bin", std::ios::binary);
    meshOut.write(reinterpret_cast<const char*>(&nverts), sizeof(nverts));
    meshOut.write(reinterpret_cast<const char*>(&ntris), sizeof(ntris));
    meshOut.write(reinterpret_cast<const char*>(verts), 3 * nverts * sizeof(float));
    meshOut.write(reinterpret_cast<const char*>(tris), 3 * ntris * sizeof(int));
    std::ofstream meta(traceStem + "-config.txt");
    meta << std::setprecision(12) << cfg.cs << " " << cfg.ch << " "
         << cfg.walkableHeight << " " << cfg.walkableClimb << " "
         << cfg.walkableRadius << " " << cfg.minRegionArea << " "
         << cfg.bmin[0] << " " << cfg.bmin[1] << " " << cfg.bmin[2] << "\n";
  }
  auto traceRaw = [&](const char* stage) {
    if (!traceEnabled || !ws.solid) return;
    std::ofstream out(traceStem + "-raw.csv", std::ios::app);
    out << std::setprecision(12);
    const int cx = int(std::floor((watch[0]-cfg.bmin[0])/cfg.cs));
    const int cz = int(std::floor((watch[2]-cfg.bmin[2])/cfg.cs));
    for (int z=std::max(0,cz-12);z<=std::min(cfg.height-1,cz+12);++z)
      for (int x=std::max(0,cx-12);x<=std::min(cfg.width-1,cx+12);++x)
        for (const rcSpan* sp=ws.solid->spans[x+z*cfg.width];sp;sp=sp->next)
          if (std::abs((cfg.bmin[1]+sp->smax*cfg.ch)-watch[1])<2.0)
            out << stage << "," << x << "," << z << ","
                << cfg.bmin[1]+sp->smin*cfg.ch << ","
                << cfg.bmin[1]+sp->smax*cfg.ch << "," << int(sp->area) << "\n";
  };
  auto traceCompact = [&](const char* stage) {
    if (!traceEnabled || !ws.chf) return;
    std::ofstream out(traceStem + "-compact.csv", std::ios::app);
    out << std::setprecision(12);
    const int cx = int(std::floor((watch[0]-cfg.bmin[0])/cfg.cs));
    const int cz = int(std::floor((watch[2]-cfg.bmin[2])/cfg.cs));
    for (int z=std::max(0,cz-12);z<=std::min(cfg.height-1,cz+12);++z)
      for (int x=std::max(0,cx-12);x<=std::min(cfg.width-1,cx+12);++x) {
        const rcCompactCell& cell=ws.chf->cells[x+z*cfg.width];
        for (unsigned int i=cell.index;i<cell.index+cell.count;++i) {
          const rcCompactSpan& sp=ws.chf->spans[i];
          if (std::abs((cfg.bmin[1]+sp.y*cfg.ch)-watch[1])<2.0)
            out << stage << "," << x << "," << z << ","
                << cfg.bmin[1]+sp.y*cfg.ch << "," << int(sp.h) << ","
                << int(ws.chf->areas[i]) << "," << int(sp.reg) << ","
                << rcGetCon(sp,0) << "," << rcGetCon(sp,1) << ","
                << rcGetCon(sp,2) << "," << rcGetCon(sp,3) << "\n";
        }
      }

    if (std::string(stage) == "regions") {
      // Observe exact directed reachability in the eroded compact graph.
      // This does not change the graph or any region ID.
      std::vector<int> spanX(ws.chf->spanCount), spanZ(ws.chf->spanCount);
      for (int z=0;z<cfg.height;++z) for (int x=0;x<cfg.width;++x) {
        const rcCompactCell& cell=ws.chf->cells[x+z*cfg.width];
        for (unsigned int j=cell.index;j<cell.index+cell.count;++j) {
          spanX[j]=x; spanZ[j]=z;
        }
      }
      std::vector<unsigned int> seen(ws.chf->spanCount,0);
      unsigned int stamp=0;
      std::ofstream reach(traceStem + "-reachability.csv");
      reach << std::setprecision(12);
      for (int z=std::max(0,cz-12);z<=std::min(cfg.height-1,cz+12);++z)
        for (int x=std::max(0,cx-12);x<=std::min(cfg.width-1,cx+12);++x) {
          const rcCompactCell& cell=ws.chf->cells[x+z*cfg.width];
          for (unsigned int seed=cell.index;seed<cell.index+cell.count;++seed) {
            if (ws.chf->areas[seed]==RC_NULL_AREA || ws.chf->spans[seed].reg!=0 ||
                std::abs(cfg.bmin[1]+ws.chf->spans[seed].y*cfg.ch-watch[1])>=0.2) continue;
            ++stamp; std::vector<unsigned int> queue(1,seed); seen[seed]=stamp;
            int minX=x,maxX=x,minZ=z,maxZ=z;
            unsigned int minY=ws.chf->spans[seed].y,maxY=minY,nonzeroRegion=0;
            for (size_t pos=0;pos<queue.size();++pos) {
              unsigned int current=queue[pos];const rcCompactSpan& sp=ws.chf->spans[current];
              const int qx=spanX[current],qz=spanZ[current];
              minX=std::min(minX,qx);maxX=std::max(maxX,qx);
              minZ=std::min(minZ,qz);maxZ=std::max(maxZ,qz);
              minY=std::min(minY,(unsigned int)sp.y);maxY=std::max(maxY,(unsigned int)sp.y);
              if (sp.reg!=0) ++nonzeroRegion;
              for (int dir=0;dir<4;++dir) {
                const int con=rcGetCon(sp,dir); if(con==RC_NOT_CONNECTED)continue;
                const int nx=qx+rcGetDirOffsetX(dir),nz=qz+rcGetDirOffsetY(dir);
                if(nx<0||nz<0||nx>=cfg.width||nz>=cfg.height)continue;
                const rcCompactCell& neighbor=ws.chf->cells[nx+nz*cfg.width];
                unsigned int ni=neighbor.index+con;
                if(ni>=ws.chf->spanCount||seen[ni]==stamp||ws.chf->areas[ni]==RC_NULL_AREA)continue;
                seen[ni]=stamp;queue.push_back(ni);
              }
            }
            reach<<seed<<","<<x<<","<<z<<","<<queue.size()<<","<<nonzeroRegion<<","
                 <<minX<<","<<maxX<<","<<minZ<<","<<maxZ<<","
                 <<cfg.bmin[1]+minY*cfg.ch<<","<<cfg.bmin[1]+maxY*cfg.ch<<"\n";
          }
        }
    }
  };
"""
 s=s[:index]+insertion+s[index:]
 a='  if (bs.filterLowHangingObstacles)';s=s.replace(a,'  traceRaw("rasterized");\n'+a,1)
 a='    rcFilterLowHangingWalkableObstacles(&ctx, cfg.walkableClimb, *ws.solid);';s=s.replace(a,a+'\n  traceRaw("low_hanging");',1)
 a='    rcFilterLedgeSpans(&ctx, cfg.walkableHeight, cfg.walkableClimb, *ws.solid);';s=s.replace(a,a+'\n  traceRaw("ledge");',1)
 a='    rcFilterWalkableLowHeightSpans(&ctx, cfg.walkableHeight, *ws.solid);';s=s.replace(a,a+'\n  traceRaw("low_height");',1)
 s=s.replace('  // Erode the walkable area by agent radius.','  traceCompact("compacted");\n  // Erode the walkable area by agent radius.',1)
 s=s.replace('  // // (Optional) Mark areas.','  traceCompact("eroded");\n  // // (Optional) Mark areas.',1)
 a='  // // Partition the walkable surface into simple regions without holes.';s=s.replace(a,'  traceCompact("regions");\n'+a,1)
 patched=C/'PathFinder.cpp';patched.write_text(s);item=next(x for x in json.loads((B/'compile_commands.json').read_text()) if x['file']==str(source));args=shlex.split(item['command']);obj=C/'PathFinder.cpp.o';args[args.index('-o')+1]=str(obj);args[args.index('-c')+1]=str(patched);args.insert(1,'-I'+str(source.parent));run(args)
 private=C/'libnav.a';shutil.copy2(archive,private);run(['/usr/bin/ar','r',str(private),str(obj)]);run(['/usr/bin/ranlib',str(private)])
 members=subprocess.check_output(['/usr/bin/ar','t',str(archive)],text=True).splitlines();assert members==subprocess.check_output(['/usr/bin/ar','t',str(private)],text=True).splitlines();changed=[]
 for name in members:
  h=lambda x:hashlib.sha256(subprocess.check_output(['/usr/bin/ar','p',str(x),name])).hexdigest()
  if h(archive)!=h(private):changed.append(name)
 assert changed==['PathFinder.cpp.o']
 installed=R/'runtime/awarevln/lib/python3.10/site-packages/habitat_sim';pkg=C/'habitat_sim';pkg.mkdir();(pkg/'_ext').mkdir()
 for p in installed.iterdir():
  if p.name not in ['_ext','__pycache__']:(pkg/p.name).symlink_to(p,target_is_directory=p.is_dir())
 receipt=json.loads((R/'outputs/landmark-connectivity/recast626-isolated-binding-v1/validation.json').read_text());args=list(receipt['commands'][0]);target=pkg/'_ext/habitat_sim_bindings.cpython-310-x86_64-linux-gnu.so';args[args.index('-o')+1]=str(target);assert args.count(str(archive))>=1;args=[str(private) if x==str(archive) else x for x in args];run(args)
 assert originals=={p:digest(p) for p in originals};note(status='BINDING_READY_NOT_SCENE_VALIDATED',binding=str(target),binding_sha256=digest(target),originals_unchanged=originals,changed_archive_members=changed)
except Exception as e:note(status='FAILED',error=repr(e));raise
