// Compatibility fixture using the frozen Recast/Detour APIs and standard tile pipeline.
#include "Recast.h"
#include "DetourNavMesh.h"
#include "DetourNavMeshBuilder.h"
#include "DetourNavMeshQuery.h"
#include "DetourAlloc.h"
#include <vector>
#include <memory>
#include <fstream>
#include <iostream>
#include <cstring>
#include <cmath>
#include <stdexcept>
#include <string>
#include "tiled_recast_builder.h"
void floorQuad(Geometry& g,float x0,float x1){int b=int(g.v.size()/3);float v[]={x0,0,-1,x1,0,-1,x1,0,2,x0,0,2};g.v.insert(g.v.end(),v,v+12);int t[]={b,b+2,b+1,b,b+3,b+2};g.t.insert(g.t.end(),t,t+6);}
Geometry geometry(const std::string& obstacle){Geometry g;if(obstacle=="gap"){floorQuad(g,-1,.8f);floorQuad(g,1.2f,3);}else floorQuad(g,-1,3);if(obstacle=="wall"){int b=int(g.v.size()/3);float v[]={1,0,-1,1,2.5f,-1,1,2.5f,2,1,0,2};g.v.insert(g.v.end(),v,v+12);int t[]={b,b+1,b+2,b,b+2,b+3};g.t.insert(g.t.end(),t,t+6);}return g;}
struct QueryResult {bool path,steps;int count;dtStatus status;};
QueryResult query(dtNavMesh* nav,bool reverse,bool testSteps){dtNavMeshQuery q;require(dtStatusSucceed(q.init(nav,2048)),"query init");dtQueryFilter filter;filter.setIncludeFlags(1);float a[3]={reverse?1.75f:.25f,0,.5f},b[3]={reverse?.25f:1.75f,0,.5f},ext[3]={.2f,.5f,.2f},start[3],end[3];dtPolyRef ar=0,br=0;require(dtStatusSucceed(q.findNearestPoly(a,ext,&filter,&ar,start))&&ar,"start poly");require(dtStatusSucceed(q.findNearestPoly(b,ext,&filter,&br,end))&&br,"end poly");dtPolyRef path[256];int count=0;auto status=q.findPath(ar,br,start,end,&filter,path,&count,256);bool connected=dtStatusSucceed(status)&&count>0&&path[count-1]==br;if(!testSteps)return {connected,false,count,status};float pos[3];std::memcpy(pos,start,sizeof(pos));dtPolyRef ref=ar;for(int i=0;i<6;++i){float desired[3]={pos[0]+(reverse?-.25f:.25f),pos[1],pos[2]},next[3];dtPolyRef visited[64];int n=0;require(dtStatusSucceed(q.moveAlongSurface(ref,pos,desired,&filter,next,visited,&n,64,true))&&n>0,"native move");ref=visited[n-1];require(dtStatusSucceed(q.getPolyHeight(ref,next,&next[1])),"native height");std::memcpy(pos,next,sizeof(pos));}bool reached=std::abs(pos[0]-end[0])<1e-5f&&std::abs(pos[1]-end[1])<1e-5f&&std::abs(pos[2]-end[2])<1e-5f;return {connected,reached,count,status};}
int main(int argc,char**argv){try{require(argc==2,"output directory required");std::string root=argv[1];std::ofstream records(root+"/native-results.jsonl");for(bool mixed: {false,true})for(const std::string obstacle: {"floor","wall","gap"}){auto g=geometry(obstacle);std::unique_ptr<dtNavMesh,void(*)(dtNavMesh*)> nav(dtAllocNavMesh(),dtFreeNavMesh);dtNavMeshParams p{};p.orig[0]=0;p.orig[1]=-.1f;p.orig[2]=0;p.tileWidth=1;p.tileHeight=1;p.maxTiles=2;p.maxPolys=256;require(dtStatusSucceed(nav->init(&p)),"mesh init");for(int tile=0;tile<2;++tile){int size=0;TileSpec spec;spec.tx=tile;spec.cell=mixed&&tile==1?.025f:.05f;int polygons=0;auto data=makeTile(g,spec,size,polygons);require(data&&polygons,"fixture tile nonempty");auto status=nav->addTile(data,size,DT_TILE_FREE_DATA,0,nullptr);if(dtStatusFailed(status)){dtFree(data);throw std::runtime_error("addTile");}}
 std::string name=std::string(mixed?"mixed_":"uniform_")+obstacle;save(nav.get(),root+"/"+name+".navmesh");std::ofstream geom(root+"/"+name+".geometry.bin",std::ios::binary);int nv=int(g.v.size()/3),nt=int(g.t.size()/3);geom.write((char*)&nv,4);geom.write((char*)&nt,4);geom.write((char*)g.v.data(),g.v.size()*4);geom.write((char*)g.t.data(),g.t.size()*4);
 bool expected=obstacle=="floor";auto f=query(nav.get(),false,expected),r=query(nav.get(),true,expected);records<<"{\"native_steps_tested\":"<<(expected?"true":"false")<<",\"case\":\""<<name<<"\",\"expected_connected\":"<<(expected?"true":"false")<<",\"forward_connected\":"<<(f.path?"true":"false")<<",\"reverse_connected\":"<<(r.path?"true":"false")<<",\"forward_steps_reached\":"<<(f.steps?"true":"false")<<",\"reverse_steps_reached\":"<<(r.steps?"true":"false")<<",\"forward_polys\":"<<f.count<<",\"reverse_polys\":"<<r.count<<",\"forward_status\":"<<f.status<<",\"reverse_status\":"<<r.status<<"}\n";records.flush();require(f.path==expected&&r.path==expected&&f.steps==expected&&r.steps==expected,"fixture semantic mismatch");}
 std::cout<<"NATIVE_FIXTURES_PASS 6\n";return 0;}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
