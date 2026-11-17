// Diagnostic derived navigation surface only; source scene geometry is never an output.
#include "DetourNavMesh.h"
#include <fstream>
#include <iostream>
#include <vector>
#include <cstring>
#include <cmath>
#include <cassert>
#include <iomanip>
struct SetHeader {int magic,version,numTiles;dtNavMeshParams params;};
struct TileHeader {dtTileRef ref;int size;};
static size_t align4(size_t v){return (v+3)&~size_t(3);}
int main(int argc,char**argv){
 if(argc!=5)return 1;float from=std::stof(argv[3]),to=std::stof(argv[4]);if(!(to>from&&to-from<.02f))return 2;
 std::ifstream f(argv[1],std::ios::binary);std::vector<unsigned char> data((std::istreambuf_iterator<char>(f)),{});if(data.size()<sizeof(SetHeader))return 3;
 SetHeader set;std::memcpy(&set,data.data(),sizeof(set));if(set.magic!=('M'<<24|'S'<<16|'E'<<8|'T')||set.version!=1||set.numTiles<1)return 4;
 size_t cursor=sizeof(set);int changes=0;std::cout<<std::setprecision(12)<<"{\"from_y\":"<<from<<",\"to_y\":"<<to<<",\"changed_float_offsets\":[";
 for(int t=0;t<set.numTiles;++t){
  if(cursor+sizeof(TileHeader)>data.size())return 5;TileHeader tile;std::memcpy(&tile,data.data()+cursor,sizeof(tile));cursor+=sizeof(tile);size_t start=cursor;
  if(tile.size<int(sizeof(dtMeshHeader))||start+tile.size>data.size())return 6;dtMeshHeader h;std::memcpy(&h,data.data()+start,sizeof(h));
  if(h.magic!=DT_NAVMESH_MAGIC||h.version!=DT_NAVMESH_VERSION||h.offMeshConCount!=0||std::fabs(h.walkableHeight-1.5f)>1e-6||std::fabs(h.walkableRadius-.1f)>1e-6)return 7;
  size_t vs=start+align4(sizeof(h));size_t ds=vs+align4(sizeof(float)*3*h.vertCount)+align4(sizeof(dtPoly)*h.polyCount)+align4(sizeof(dtLink)*h.maxLinkCount)+align4(sizeof(dtPolyDetail)*h.detailMeshCount);
  size_t end=ds+align4(sizeof(float)*3*h.detailVertCount)+align4(4*h.detailTriCount)+align4(sizeof(dtBVNode)*h.bvNodeCount)+align4(sizeof(dtOffMeshConnection)*h.offMeshConCount);if(end!=start+tile.size)return 8;
  for(int group=0;group<2;++group){size_t base=group?ds:vs;int count=group?h.detailVertCount:h.vertCount;
   for(int i=0;i<count;++i){size_t at=base+sizeof(float)*(i*3+1);float y;std::memcpy(&y,data.data()+at,sizeof(y));if(y!=from)continue;
    // Same quantization bucket: preserve original BV tree and tile bounds conservatively.
    if(to<h.bmin[1]||to>h.bmax[1]||int((y-h.bmin[1])*h.bvQuantFactor)!=int((to-h.bmin[1])*h.bvQuantFactor))return 9;
    if(changes++)std::cout<<",";std::cout<<at;std::memcpy(data.data()+at,&to,sizeof(to));
   }
  }
  cursor+=tile.size;
 }
 if(cursor!=data.size()||changes==0)return 10;std::ifstream exists(argv[2]);if(exists.good())return 11;std::ofstream out(argv[2],std::ios::binary);out.write((char*)data.data(),data.size());if(!out)return 12;std::cout<<"],\"changed_floats\":"<<changes<<",\"all_other_bytes_preserved\":true,\"bv_quantization_preserved\":true}\n";
}
