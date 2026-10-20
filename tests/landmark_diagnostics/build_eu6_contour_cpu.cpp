// CPU-only navigation rebuild from an already verified native loader input.
#include "esp/nav/PathFinder.h"
#include "esp/assets/MeshData.h"
#include <fstream>
#include <iostream>
#include <cmath>
#include <cstdint>
int main(int argc,char**argv){
 if(argc!=4)return 1;const std::string mode=argv[3];if(mode!="control"&&mode!="tight")return 8;
 std::ifstream in(argv[1],std::ios::binary);int32_t nv=0,nt=0;in.read((char*)&nv,4);in.read((char*)&nt,4);
 if(!in||nv<=0||nt<=0||nv>10000000||nt>20000000)return 2;
 esp::assets::MeshData mesh;mesh.vbo.reserve(nv);mesh.ibo.resize(size_t(nt)*3);
 for(int i=0;i<nv;++i){float xyz[3];in.read((char*)xyz,12);if(!in||!std::isfinite(xyz[0])||!std::isfinite(xyz[1])||!std::isfinite(xyz[2]))return 3;mesh.vbo.emplace_back(xyz[0],xyz[1],xyz[2]);}
 in.read((char*)mesh.ibo.data(),size_t(nt)*12);if(!in||in.peek()!=std::char_traits<char>::eof())return 4;
 for(auto i:mesh.ibo)if(i>=uint32_t(nv))return 5;
 esp::nav::NavMeshSettings settings;settings.setDefaults();settings.agentHeight=1.5f;settings.agentRadius=.1f;settings.cellSize=.05f;settings.cellHeight=.05f;settings.agentMaxClimb=.2f;settings.agentMaxSlope=45.f;settings.regionMinSize=20;settings.regionMergeSize=20;settings.edgeMaxLen=12.f;settings.edgeMaxError=mode=="control"?1.3f:.1f;settings.vertsPerPoly=6;settings.detailSampleDist=6;settings.detailSampleMaxError=1;settings.filterLowHangingObstacles=true;settings.filterLedgeSpans=true;settings.filterWalkableLowHeightSpans=true;
 esp::nav::PathFinder pf;if(!pf.build(settings,mesh))return 6;if(!pf.saveNavMesh(argv[2]))return 7;
 std::cout<<"CPU_NATIVE_BUILD_COMPLETE "<<nv<<" "<<nt<<"\n";return 0;
}
