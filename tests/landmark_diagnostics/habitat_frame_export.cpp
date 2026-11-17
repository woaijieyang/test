// Reproduce the frame construction used by Habitat CoordinateFrame and Magnum Quaternion.
#include <Eigen/Geometry>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <cstdint>
int main(int argc,char**argv){
 if(argc!=3)return 1;
 Eigen::Vector3f up(0,1,0),front(0,0,-1),frameUp(0,0,1),frameFront(0,1,0);
 Eigen::Quaternionf a=Eigen::Quaternionf::FromTwoVectors(up,frameUp);
 Eigen::Quaternionf q=(Eigen::Quaternionf::FromTwoVectors(a*front,frameFront)*a).inverse();
 float x=q.x(),y=q.y(),z=q.z(),w=q.w();
 float m[3][3]={{1-2*y*y-2*z*z,2*x*y-2*z*w,2*x*z+2*y*w},{2*x*y+2*z*w,1-2*x*x-2*z*z,2*y*z-2*x*w},{2*x*z-2*y*w,2*y*z+2*x*w,1-2*x*x-2*y*y}};
 std::ifstream f(argv[1],std::ios::binary);std::ofstream o(argv[2],std::ios::binary);uint32_t n=0;f.read((char*)&n,4);o.write((char*)&n,4);
 for(uint64_t i=0;i<uint64_t(n)*3;i++){float p[3],r[3];f.read((char*)p,12);for(int k=0;k<3;k++)r[k]=(m[k][0]*p[0]+m[k][1]*p[1])+m[k][2]*p[2];o.write((char*)r,12);}if(!f||!o)return 2;
 std::cout<<std::setprecision(10)<<q.coeffs().transpose()<<"\n";for(auto&row:m){for(float v:row)std::cout<<v<<" ";std::cout<<"\n";}
}
