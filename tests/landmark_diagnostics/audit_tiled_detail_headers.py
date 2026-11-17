"""Inspect frozen MSET/Detour headers using the exact checked-in native layouts."""
import json,struct,hashlib,datetime
from pathlib import Path
R=Path.cwd();O=R/"outputs/landmark-connectivity/d7-tiled-detail01-v1";reports=[]
set_header=struct.Struct("<3i5f2i");tile_header=struct.Struct("<Ii");mesh_header=struct.Struct("<5iI9i10f");assert set_header.size==40 and tile_header.size==8 and mesh_header.size==100
f32=lambda x:struct.unpack("<f",struct.pack("<f",x))[0]
fixture=(R/"outputs/landmark-connectivity/tiled-navmesh-fixture-v3/mixed_floor.navmesh").read_bytes();fixture_native=mesh_header.unpack_from(fixture,set_header.size+tile_header.size)
for mode in ["mixed"]:
 D=O/mode;raw=(D/"scene.navmesh").read_bytes();h=set_header.unpack_from(raw);assert h[0]==((ord("M")<<24)|(ord("S")<<16)|(ord("E")<<8)|ord("T")) and h[1]==1;assert h[2]==h[8] and h[6]==h[7]==2
 original_origin=json.loads((R/"outputs/landmark-connectivity/d7-tiled-prototype-v1"/mode/"native-summary.json").read_text())["origin"];assert h[3]==f32(original_origin[0]-.0125) and h[4]==f32(original_origin[1]) and h[5]==f32(original_origin[2]-.0125)
 tile_rows=[json.loads(line) for line in (D/"tiles.jsonl").read_text().splitlines()];expected={(r["x"],r["z"]):r for r in tile_rows if r["polygons"]};seen=set();refs=set();at=set_header.size;coarse=fine=0
 for i in range(h[2]):
  ref,size=tile_header.unpack_from(raw,at);at+=tile_header.size;assert ref and ref not in refs and size>=mesh_header.size;refs.add(ref);t=mesh_header.unpack_from(raw,at);assert t[0:2]==fixture_native[0:2] and t[4]==0;key=(t[2],t[3]);assert key in expected and key not in seen;seen.add(key);e=expected[key];assert t[6]==e["polygons"] and t[7]>0 and t[9]==t[6] and t[13]==0 and t[14]==t[6]
  assert t[15:18]==(f32(1.5),f32(.1),f32(.3));is_coarse=abs(e["cell_size"]-.05)<1e-8;assert is_coarse or abs(e["cell_size"]-.025)<1e-8;assert t[24]==(20.0 if is_coarse else 40.0);coarse+=is_coarse;fine+=not is_coarse;at+=size
 assert at==len(raw) and seen==set(expected);reports.append({"mode":mode,"active_tiles":h[2],"occupied_pool_slots":h[8],"coarse_tiles":coarse,"fine_tiles":fine,"body_height":1.5,"body_radius":.1,"max_climb":.3,"offmesh_connections":0,"mesh_sha256":hashlib.sha256(raw).hexdigest()})
p=O/"header-audit.json";assert not p.exists();p.write_text(json.dumps({"status":"PASS_ALL_TILE_BODY_HEADER_IDENTITY_AND_NO_OFFMESH_LINKS","conditions":reports,"layout_source_sha256":hashlib.sha256((R/"upstream/habitat-sim/src/deps/recastnavigation/Detour/Include/DetourNavMesh.h").read_bytes()).hexdigest(),"script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"time":datetime.datetime.now().isoformat(),"limits":"Header/serialization audit only, not sourcegeometry/motionacceptance."},indent=2)+"\n");print(reports)
