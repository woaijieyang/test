#pragma once
// Tile pipeline follows frozen RecastDemo Sample_TileMesh; original Recast/Detour remain Zlib licensed.
// Compatibility fixture using the frozen Recast/Detour APIs and standard tile pipeline.
#include "Recast.h"
#include "DetourNavMesh.h"
#include "DetourNavMeshBuilder.h"
#include "DetourNavMeshQuery.h"
#include "DetourAlloc.h"
#include <vector>
#include <cstdlib>
#include <memory>
#include <fstream>
#include <iostream>
#include <cstring>
#include <cmath>
#include <stdexcept>
#include <string>
struct Geometry {std::vector<float> v;std::vector<int> t;};
void require(bool ok,const char* msg){if(!ok)throw std::runtime_error(msg);}
struct Work {rcHeightfield* solid=rcAllocHeightfield();rcCompactHeightfield* chf=rcAllocCompactHeightfield();rcContourSet* contours=rcAllocContourSet();rcPolyMesh* mesh=rcAllocPolyMesh();rcPolyMeshDetail* detail=rcAllocPolyMeshDetail();~Work(){rcFreeHeightField(solid);rcFreeCompactHeightfield(chf);rcFreeContourSet(contours);rcFreePolyMesh(mesh);rcFreePolyMeshDetail(detail);}};
struct TileSpec {int tx=0,ty=0;float world=1,cell=.05f;float origin[3]={0,-.1f,0};float ymax=3;};
rcConfig tileConfig(const TileSpec& s){
 rcConfig c{};c.cs=s.cell;c.ch=.05f;c.walkableSlopeAngle=45;c.walkableHeight=int(ceilf(1.5f/c.ch));c.walkableClimb=int(floorf(.3f/c.ch));c.walkableRadius=int(ceilf(.1f/c.cs));c.maxEdgeLen=int(12/c.cs);c.maxSimplificationError=1.3f;int region=int(roundf(1/c.cs));c.minRegionArea=region*region;c.mergeRegionArea=region*region;c.maxVertsPerPoly=6;c.tileSize=int(roundf(s.world/c.cs));c.borderSize=c.walkableRadius+3;c.width=c.tileSize+2*c.borderSize;c.height=c.width;c.detailSampleDist=6*c.cs;const char* detailArg=std::getenv("CASE1_DETAIL_ERROR_FACTOR");require(detailArg,"explicit detail error factor required");const float detailFactor=std::stof(detailArg);require(detailFactor==1.f||detailFactor==.1f,"only fixed control and predeclared candidate");c.detailSampleMaxError=c.ch*detailFactor;
 c.bmin[0]=s.origin[0]+s.tx*s.world-c.borderSize*c.cs;c.bmin[1]=s.origin[1];c.bmin[2]=s.origin[2]+s.ty*s.world-c.borderSize*c.cs;c.bmax[0]=s.origin[0]+(s.tx+1)*s.world+c.borderSize*c.cs;c.bmax[1]=s.ymax;c.bmax[2]=s.origin[2]+(s.ty+1)*s.world+c.borderSize*c.cs;return c;
}
unsigned char* makeTile(const Geometry& g,const TileSpec& spec,int& size,int& polygons){
 rcContext context;rcConfig c=tileConfig(spec);
 Work w;require(w.solid&&w.chf&&w.contours&&w.mesh&&w.detail,"allocation");require(rcCreateHeightfield(&context,*w.solid,c.width,c.height,c.bmin,c.bmax,c.cs,c.ch),"heightfield");int nv=int(g.v.size()/3),nt=int(g.t.size()/3);std::vector<unsigned char> areas(nt,0);rcMarkWalkableTriangles(&context,c.walkableSlopeAngle,g.v.data(),nv,g.t.data(),nt,areas.data());require(rcRasterizeTriangles(&context,g.v.data(),nv,g.t.data(),areas.data(),nt,*w.solid,c.walkableClimb),"rasterize");rcFilterLowHangingWalkableObstacles(&context,c.walkableClimb,*w.solid);rcFilterLedgeSpans(&context,c.walkableHeight,c.walkableClimb,*w.solid);rcFilterWalkableLowHeightSpans(&context,c.walkableHeight,*w.solid);require(rcBuildCompactHeightfield(&context,c.walkableHeight,c.walkableClimb,*w.solid,*w.chf),"compact");require(rcErodeWalkableArea(&context,c.walkableRadius,*w.chf),"erode");require(rcBuildDistanceField(&context,*w.chf),"distance");require(rcBuildRegions(&context,*w.chf,c.borderSize,c.minRegionArea,c.mergeRegionArea),"regions");require(rcBuildContours(&context,*w.chf,c.maxSimplificationError,c.maxEdgeLen,*w.contours),"contours");if(!w.contours->nconts){size=0;polygons=0;return nullptr;}require(rcBuildPolyMesh(&context,*w.contours,c.maxVertsPerPoly,*w.mesh),"polymesh");require(rcBuildPolyMeshDetail(&context,*w.mesh,*w.chf,c.detailSampleDist,c.detailSampleMaxError,*w.detail),"detail");for(int i=0;i<w.mesh->npolys;++i){if(w.mesh->areas[i]==RC_WALKABLE_AREA)w.mesh->areas[i]=0;w.mesh->flags[i]=1;}
 dtNavMeshCreateParams p{};p.verts=w.mesh->verts;p.vertCount=w.mesh->nverts;p.polys=w.mesh->polys;p.polyAreas=w.mesh->areas;p.polyFlags=w.mesh->flags;p.polyCount=w.mesh->npolys;p.nvp=w.mesh->nvp;p.detailMeshes=w.detail->meshes;p.detailVerts=w.detail->verts;p.detailVertsCount=w.detail->nverts;p.detailTris=w.detail->tris;p.detailTriCount=w.detail->ntris;p.walkableHeight=1.5f;p.walkableRadius=.1f;p.walkableClimb=.3f;p.tileX=spec.tx;p.tileY=spec.ty;p.tileLayer=0;rcVcopy(p.bmin,w.mesh->bmin);rcVcopy(p.bmax,w.mesh->bmax);p.cs=c.cs;p.ch=c.ch;p.buildBvTree=true;polygons=w.mesh->npolys;unsigned char* data=nullptr;require(dtCreateNavMeshData(&p,&data,&size),"create tile data");return data;
}
struct SetHeader {int magic,version,numTiles;dtNavMeshParams params;};struct TileHeader {dtTileRef tileRef;int dataSize;};
void save(const dtNavMesh* nav,const std::string& path){SetHeader h{};h.magic='M'<<24|'S'<<16|'E'<<8|'T';h.version=1;h.params=*nav->getParams();for(int i=0;i<nav->getMaxTiles();++i){auto t=nav->getTile(i);if(t&&t->header&&t->dataSize)++h.numTiles;}require(h.numTiles>0,"tile count");std::ofstream out(path,std::ios::binary);out.write((char*)&h,sizeof(h));for(int i=0;i<nav->getMaxTiles();++i){auto t=nav->getTile(i);if(!t||!t->header||!t->dataSize)continue;TileHeader th{};th.tileRef=nav->getTileRef(t);th.dataSize=t->dataSize;out.write((char*)&th,sizeof(th));out.write((char*)t->data,t->dataSize);}require(bool(out),"save");}
