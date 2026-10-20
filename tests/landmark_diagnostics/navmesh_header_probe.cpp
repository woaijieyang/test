#include "DetourNavMesh.h"
#include <fstream>
#include <iostream>
#include <iomanip>
struct SetHeader {int magic,version,numTiles;dtNavMeshParams params;};
struct TileHeader {dtTileRef ref;int size;};
int main(int argc,char**argv){
 if(argc!=2)return 1;std::ifstream f(argv[1],std::ios::binary);SetHeader h{};f.read((char*)&h,sizeof(h));
 if(!f||h.magic!=('M'<<24|'S'<<16|'E'<<8|'T')||h.version!=1||h.numTiles<1)return 2;
 std::cout<<std::setprecision(9)<<"[";
 for(int i=0;i<h.numTiles;i++){
  TileHeader t{};f.read((char*)&t,sizeof(t));dtMeshHeader m{};if(t.size<(int)sizeof(m))return 3;f.read((char*)&m,sizeof(m));
  if(!f||m.magic!=DT_NAVMESH_MAGIC||m.version!=DT_NAVMESH_VERSION)return 4;
  if(i)std::cout<<",";
  std::cout<<"{\"height\":"<<m.walkableHeight<<",\"radius\":"<<m.walkableRadius<<",\"climb\":"<<m.walkableClimb<<",\"bv_quant_factor\":"<<m.bvQuantFactor<<",\"poly_count\":"<<m.polyCount<<",\"vertex_count\":"<<m.vertCount<<"}";
  f.seekg(t.size-sizeof(m),std::ios::cur);
 }
 std::cout<<"]\n";return f?0:5;
}
