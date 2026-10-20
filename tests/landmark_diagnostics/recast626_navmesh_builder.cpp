#include "Recast.h"
#include "DetourNavMesh.h"
#include "DetourNavMeshBuilder.h"
#include "DetourAlloc.h"
#include <cstring>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <vector>
#include <cmath>
#include <cstdint>
struct Watch {float x,y,z;};
int main(int argc,char**argv){
 if(argc!=6)return 1;float cs=std::stof(argv[2]),ch=std::stof(argv[3]);std::ifstream f(argv[1],std::ios::binary);uint32_t nt=0;f.read((char*)&nt,4);std::vector<float> v(nt*9);f.read((char*)v.data(),v.size()*4);if(!f)return 2;
 std::ifstream wf(argv[4]);std::vector<Watch>w;Watch q;while(wf>>q.x>>q.y>>q.z)w.push_back(q);
 int nv=nt*3;std::vector<int> idx(nv);for(int i=0;i<nv;i++)idx[i]=i;std::vector<unsigned char> areas(nt);float lo[3],hi[3];rcCalcBounds(v.data(),nv,lo,hi);int width,height;rcCalcGridSize(lo,hi,cs,&width,&height);rcContext ctx(false);rcHeightfield* hf=rcAllocHeightfield();if(!rcCreateHeightfield(&ctx,*hf,width,height,lo,hi,cs,ch))return 3;
 int wh=(int)ceilf(1.5f/ch),wc=(int)floorf(.3f/ch),wr=(int)ceilf(.1f/cs);rcMarkWalkableTriangles(&ctx,45,v.data(),nv,idx.data(),nt,areas.data());if(!rcRasterizeTriangles(&ctx,v.data(),nv,idx.data(),areas.data(),nt,*hf,wc))return 4;
 auto countHF=[&](const char*stage){std::vector<int>counts(w.size(),0);for(int z=0;z<height;z++)for(int x=0;x<width;x++){float px=lo[0]+(x+.5f)*cs,pz=lo[2]+(z+.5f)*cs;for(size_t k=0;k<w.size();k++){if(std::hypot(px-w[k].x,pz-w[k].z)>=.5f)continue;for(rcSpan*s=hf->spans[x+z*width];s;s=s->next){float py=lo[1]+s->smax*ch;if(s->area!=RC_NULL_AREA&&py<=w[k].y&&py>=w[k].y-2)counts[k]++;}}}std::cout<<stage;for(int c:counts)std::cout<<" "<<c;std::cout<<"\n";};
 countHF("raster");rcFilterLowHangingWalkableObstacles(&ctx,wc,*hf);countHF("low_hanging");rcFilterLedgeSpans(&ctx,wh,wc,*hf);countHF("ledge");rcFilterWalkableLowHeightSpans(&ctx,wh,*hf);countHF("low_height");rcCompactHeightfield* compact=rcAllocCompactHeightfield();if(!rcBuildCompactHeightfield(&ctx,wh,wc,*hf,*compact))return 5;
 auto countCH=[&](const char*stage,bool region){std::vector<int>counts(w.size(),0);for(int z=0;z<compact->height;z++)for(int x=0;x<compact->width;x++){float px=lo[0]+(x+.5f)*cs,pz=lo[2]+(z+.5f)*cs;const rcCompactCell& c=compact->cells[x+z*compact->width];for(size_t k=0;k<w.size();k++){if(std::hypot(px-w[k].x,pz-w[k].z)>=.5f)continue;for(unsigned int i=c.index;i<c.index+c.count;i++){float py=lo[1]+compact->spans[i].y*ch;if(compact->areas[i]!=RC_NULL_AREA&&(!region||compact->spans[i].reg!=0)&&py<=w[k].y&&py>=w[k].y-2)counts[k]++;}}}std::cout<<stage;for(int c:counts)std::cout<<" "<<c;std::cout<<"\n";};
 countCH("compact",false);if(!rcErodeWalkableArea(&ctx,wr,*compact))return 6;countCH("erosion",false);if(!rcBuildDistanceField(&ctx,*compact))return 7;if(!rcBuildRegions(&ctx,*compact,0,1600,1600))return 8;countCH("regions",true);rcContourSet* contours=rcAllocContourSet();if(!rcBuildContours(&ctx,*compact,1.3f,int(12.0f/cs),*contours))return 9;
 rcPolyMesh* poly=rcAllocPolyMesh();if(!rcBuildPolyMesh(&ctx,*contours,6,*poly))return 10;
 rcPolyMeshDetail* detail=rcAllocPolyMeshDetail();if(!rcBuildPolyMeshDetail(&ctx,*poly,*compact,cs*6,ch,*detail))return 11;
 for(int i=0;i<poly->npolys;i++){if(poly->areas[i]==RC_WALKABLE_AREA)poly->areas[i]=0;if(poly->areas[i]==0)poly->flags[i]=1;}
 dtNavMeshCreateParams params{};params.verts=poly->verts;params.vertCount=poly->nverts;params.polys=poly->polys;params.polyAreas=poly->areas;params.polyFlags=poly->flags;params.polyCount=poly->npolys;params.nvp=poly->nvp;params.detailMeshes=detail->meshes;params.detailVerts=detail->verts;params.detailVertsCount=detail->nverts;params.detailTris=detail->tris;params.detailTriCount=detail->ntris;params.walkableHeight=1.5f;params.walkableRadius=.1f;params.walkableClimb=.3f;rcVcopy(params.bmin,poly->bmin);rcVcopy(params.bmax,poly->bmax);params.cs=cs;params.ch=ch;params.buildBvTree=true;
 unsigned char* data=nullptr;int size=0;if(!dtCreateNavMeshData(&params,&data,&size))return 12;dtNavMesh* nav=dtAllocNavMesh();if(dtStatusFailed(nav->init(data,size,DT_TILE_FREE_DATA)))return 13;
 struct Header{int magic,version,numTiles;dtNavMeshParams params;};struct TileHeader{dtTileRef ref;int size;};Header header{};header.magic='M'<<24|'S'<<16|'E'<<8|'T';header.version=1;const dtNavMesh* view=nav;
 for(int i=0;i<view->getMaxTiles();i++){const dtMeshTile* tile=view->getTile(i);if(tile&&tile->header&&tile->dataSize)header.numTiles++;}std::memcpy(&header.params,nav->getParams(),sizeof(dtNavMeshParams));FILE* output=std::fopen(argv[5],"wb");if(!output)return 14;std::fwrite(&header,sizeof(header),1,output);
 for(int i=0;i<view->getMaxTiles();i++){const dtMeshTile* tile=view->getTile(i);if(!tile||!tile->header||!tile->dataSize)continue;TileHeader t{};t.ref=view->getTileRef(tile);t.size=tile->dataSize;std::fwrite(&t,sizeof(t),1,output);std::fwrite(tile->data,tile->dataSize,1,output);}std::fclose(output);std::cout<<"mesh "<<poly->nverts<<" "<<poly->npolys<<"\n";
 dtFreeNavMesh(nav);rcFreePolyMeshDetail(detail);rcFreePolyMesh(poly);rcFreeContourSet(contours);rcFreeCompactHeightfield(compact);rcFreeHeightField(hf);return 0;
}
