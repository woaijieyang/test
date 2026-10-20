"""Offline reachability oracle: native greedy actions with legal-action A* fallback.
The model policy is never changed. Planning uses a separate simulator; only
actual primitive actions enter execution traces, without pose corrections.
"""
import heapq,itertools,math
import habitat_sim

class RobustOracle:
 def __init__(self,sim,planner,target,radius=.25,max_nodes=5000):
  self.sim=sim;self.planner=planner;self.target=target;self.radius=radius;self.max_nodes=max_nodes;self.plan=[];self.visits={};self.follower=sim.make_greedy_follower(goal_radius=radius,stop_key=0,forward_key=1,left_key=2,right_key=3);self.searches=0
 def snapshot(self,s):
  st=s.get_agent(0).get_state();return (st.position.copy(),st.rotation)
 def key(self,state):
  p,q=state;angle=(2*math.atan2(float(q.imag[1]),float(q.real)))%(2*math.pi);return tuple(round(float(v)*100) for v in p)+(round(angle*1800/math.pi)%3600,)
 def distance(self,p):
  q=habitat_sim.ShortestPath();q.requested_start=p;q.requested_end=self.target
  return float(q.geodesic_distance) if self.planner.pathfinder.find_path(q) else math.inf
 def transition(self,state,action):
  st=habitat_sim.AgentState();st.position=state[0];st.rotation=state[1];self.planner.get_agent(0).set_state(st);self.planner.step(action);new=self.snapshot(self.planner);p=new[0]
  if not all(math.isfinite(float(v)) for v in p) or not self.planner.pathfinder.is_navigable(p) or abs(float(p[1]-state[0][1]))>.5:return None
  if action==1 and math.dist(p,state[0])<1e-5:return None
  if not math.isfinite(self.distance(p)):return None
  return new
 def search(self,start):
  self.searches+=1;counter=itertools.count();queue=[(self.distance(start[0])/.25,0.,next(counter),start,[])];best={self.key(start):0.};expanded=0
  while queue and expanded<self.max_nodes:
   _,cost,_,state,path=heapq.heappop(queue);key=self.key(state)
   if cost>best.get(key,math.inf)+1e-9:continue
   if self.distance(state[0])<=self.radius:return path
   expanded+=1
   for action in (1,2,3):
    new=self.transition(state,action)
    if new is None:continue
    k=self.key(new);g=cost+(1. if action==1 else .15)
    if g>=best.get(k,math.inf)-1e-9:continue
    best[k]=g;heapq.heappush(queue,(g+self.distance(new[0])/.25,g,next(counter),new,path+[action]))
  raise RuntimeError('legal_action_search_exhausted:'+str(expanded))
 def next_action(self,target=None):
  state=self.snapshot(self.sim);key=self.key(state);self.visits[key]=self.visits.get(key,0)+1
  if self.distance(state[0])<=self.radius:return 0
  if self.plan:
   action=self.plan.pop(0)
   if self.transition(state,action) is not None:return action
   self.plan=[]
  action=None
  if self.visits[key]<3:
   try:action=self.follower.next_action_along(self.target)
   except habitat_sim.errors.GreedyFollowerError:pass
  if action in (1,2,3) and self.transition(state,action) is not None:return int(action)
  self.plan=self.search(state)
  return self.plan.pop(0) if self.plan else 0
