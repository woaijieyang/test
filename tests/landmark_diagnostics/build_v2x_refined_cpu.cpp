// CPU-only navigation rebuild from an already verified native loader input.
#include "esp/nav/PathFinder.h"
#include "esp/assets/MeshData.h"
#include <fstream>
#include <iostream>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <string>
#include <utility>
int main(int argc,char**argv){
 if(argc!=4)return 1;const std::string mode(argv[3]);if(mode!="control"&&mode!="half-horizontal")return 1;const bool refine=mode=="half-horizontal";
 std::ifstream in(argv[1],std::ios::binary);int32_t nv=0,nt=0;in.read((char*)&nv,4);in.read((char*)&nt,4);
 if(!in||nv<=0||nt<=0||nv>10000000||nt>20000000)return 2;
 esp::assets::MeshData mesh;mesh.vbo.reserve(nv);mesh.ibo.resize(size_t(nt)*3);
 for(int i=0;i<nv;++i){float xyz[3];in.read((char*)xyz,12);if(!in||!std::isfinite(xyz[0])||!std::isfinite(xyz[1])||!std::isfinite(xyz[2]))return 3;mesh.vbo.emplace_back(xyz[0],xyz[1],xyz[2]);}
 in.read((char*)mesh.ibo.data(),size_t(nt)*12);if(!in||in.peek()!=std::char_traits<char>::eof())return 4;
 for(auto i:mesh.ibo)if(i>=uint32_t(nv))return 5;
 esp::nav::NavMeshSettings settings;settings.setDefaults();settings.agentHeight=1.5f;settings.agentRadius=.1f;settings.cellSize=refine?.0125f:.025f;settings.cellHeight=.05f;settings.agentMaxClimb=.3f;settings.regionMinSize=refine?80:40;settings.regionMergeSize=refine?80:40;settings.edgeMaxError=refine?2.6f:1.3f;settings.detailSampleDist=refine?12.f:6.f;
 esp::nav::PathFinder pf;if(!pf.build(settings,mesh))return 6;if(!pf.saveNavMesh(argv[2]))return 7;
 std::cout<<"SETTINGS_JSON {"<<std::setprecision(17);bool first=true;
 const std::pair<const char*,double> fields[]={{"cell_size",settings.cellSize},{"cell_height",settings.cellHeight},{"agent_height",settings.agentHeight},{"agent_radius",settings.agentRadius},{"agent_max_climb",settings.agentMaxClimb},{"agent_max_slope",settings.agentMaxSlope},{"region_min_size",settings.regionMinSize},{"region_merge_size",settings.regionMergeSize},{"edge_max_len",settings.edgeMaxLen},{"edge_max_error",settings.edgeMaxError},{"verts_per_poly",settings.vertsPerPoly},{"detail_sample_dist",settings.detailSampleDist},{"detail_sample_max_error",settings.detailSampleMaxError},{"filter_low_hanging_obstacles",settings.filterLowHangingObstacles},{"filter_ledge_spans",settings.filterLedgeSpans},{"filter_walkable_low_height_spans",settings.filterWalkableLowHeightSpans}};
 for(const auto& f:fields){if(!first)std::cout<<",";first=false;std::cout<<"\""<<f.first<<"\":"<<f.second;}std::cout<<"}\n";return 0;
}
