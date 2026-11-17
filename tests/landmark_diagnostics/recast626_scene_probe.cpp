#include "Recast.h"
#include <fstream>
#include <iostream>
#include <vector>
#include <cmath>
#include <cstdint>
struct Watch {float x,y,z;};
int main(int argc,char**argv){
 if(argc!=5)return 1;float cs=std::stof(argv[2]),ch=std::stof(argv[3]);std::ifstream f(argv[1],std::ios::binary);uint32_t nt=0;f.read((char*)&nt,4);std::vector<float> v(nt*9);f.read((char*)v.data(),v.size()*4);if(!f)return 2;
 std::ifstream wf(argv[4]);std::vector<Watch>w;Watch q;while(wf>>q.x>>q.y>>q.z)w.push_back(q);
 int nv=nt*3;std::vector<int> idx(nv);for(int i=0;i<nv;i++)idx[i]=i;std::vector<unsigned char> areas(nt);float lo[3],hi[3];rcCalcBounds(v.data(),nv,lo,hi);int width,height;rcCalcGridSize(lo,hi,cs,&width,&height);rcContext ctx(false);rcHeightfield* hf=rcAllocHeightfield();if(!rcCreateHeightfield(&ctx,*hf,width,height,lo,hi,cs,ch))return 3;
 int wh=(int)ceilf(1.5f/ch),wc=(int)floorf(.3f/ch),wr=(int)ceilf(.1f/cs);rcMarkWalkableTriangles(&ctx,45,v.data(),nv,idx.data(),nt,areas.data());if(!rcRasterizeTriangles(&ctx,v.data(),nv,idx.data(),areas.data(),nt,*hf,wc))return 4;
 auto countHF=[&](const char*stage){std::vector<int>counts(w.size(),0);for(int z=0;z<height;z++)for(int x=0;x<width;x++){float px=lo[0]+(x+.5f)*cs,pz=lo[2]+(z+.5f)*cs;for(size_t k=0;k<w.size();k++){if(std::hypot(px-w[k].x,pz-w[k].z)>=.5f)continue;for(rcSpan*s=hf->spans[x+z*width];s;s=s->next){float py=lo[1]+s->smax*ch;if(s->area!=RC_NULL_AREA&&py<=w[k].y&&py>=w[k].y-2)counts[k]++;}}}std::cout<<stage;for(int c:counts)std::cout<<" "<<c;std::cout<<"\n";};
 countHF("raster");rcFilterLowHangingWalkableObstacles(&ctx,wc,*hf);countHF("low_hanging");rcFilterLedgeSpans(&ctx,wh,wc,*hf);countHF("ledge");rcFilterWalkableLowHeightSpans(&ctx,wh,*hf);countHF("low_height");rcCompactHeightfield* compact=rcAllocCompactHeightfield();if(!rcBuildCompactHeightfield(&ctx,wh,wc,*hf,*compact))return 5;
 auto countCH=[&](const char*stage,bool region){std::vector<int>counts(w.size(),0);for(int z=0;z<compact->height;z++)for(int x=0;x<compact->width;x++){float px=lo[0]+(x+.5f)*cs,pz=lo[2]+(z+.5f)*cs;const rcCompactCell& c=compact->cells[x+z*compact->width];for(size_t k=0;k<w.size();k++){if(std::hypot(px-w[k].x,pz-w[k].z)>=.5f)continue;for(unsigned int i=c.index;i<c.index+c.count;i++){float py=lo[1]+compact->spans[i].y*ch;if(compact->areas[i]!=RC_NULL_AREA&&(!region||compact->spans[i].reg!=0)&&py<=w[k].y&&py>=w[k].y-2)counts[k]++;}}}std::cout<<stage;for(int c:counts)std::cout<<" "<<c;std::cout<<"\n";};
 countCH("compact",false);if(!rcErodeWalkableArea(&ctx,wr,*compact))return 6;countCH("erosion",false);if(!rcBuildDistanceField(&ctx,*compact))return 7;if(!rcBuildRegions(&ctx,*compact,0,1600,1600))return 8;countCH("regions",true);rcFreeCompactHeightfield(compact);rcFreeHeightField(hf);return 0;
}
