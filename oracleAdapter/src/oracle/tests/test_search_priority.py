import math
import unittest

from oracle.contracts import Budget, Failure
from oracle.planners.action_space import search


class SearchPriority(unittest.TestCase):
    def kwargs(self):
        edges={(0,1):1,(0,2):2,(1,1):4,(2,1):3}
        return dict(initial=0,actions=(1,2),transition=lambda s,a:edges.get((s,a)),
                    key=lambda s:s,reached=lambda s:s==3,
                    heuristic=lambda s:{0:0.,1:2.,2:1.,3:0.,4:10.}[s],
                    action_costs={1:1.,2:2.},budget=Budget(2,4,5,10.))

    def test_fixed_priority_changes_order_not_action_cost_or_goal(self):
        baseline=search(**self.kwargs(),priority_weight=1.)
        candidate=search(**self.kwargs(),priority_weight=2.)
        self.assertEqual(baseline.failure,Failure.SEARCH_BUDGET)
        self.assertEqual(candidate.failure,Failure.NONE)
        self.assertEqual(candidate.actions,(2,1))
        self.assertEqual(candidate.cost,3.)
        self.assertEqual(candidate.expansions,2)
        self.assertEqual(candidate.transition_calls,4)
        self.assertEqual(baseline.stop_reason,'expansion_limit')
        self.assertEqual(candidate.stop_reason,'goal_reached')

    def test_default_is_explicit_control_weight_one(self):
        a=search(**self.kwargs());b=search(**self.kwargs(),priority_weight=1.)
        for field in ['actions','states','failure','expansions','transition_calls','cost','stop_reason','diagnostics']:
            self.assertEqual(getattr(a,field),getattr(b,field))

    def test_priority_parameter_rejects_invalid_or_silent_boolean_values(self):
        for weight in [True,False,0.,.9,-1.,math.nan,math.inf,'2']:
            with self.subTest(weight=weight),self.assertRaises(ValueError):
                search(**self.kwargs(),priority_weight=weight)

    def test_accounting_does_not_add_transition_queries(self):
        calls=[]
        def transition(s,a):
            calls.append((s,a))
            return {(0,1):1,(0,2):1,(1,1):2,(1,2):1}.get((s,a))
        r=search(0,actions=(1,2),transition=transition,key=lambda s:s,
                 reached=lambda s:s==2,heuristic=lambda s:0.,action_costs={1:1.,2:1.},
                 budget=Budget(10,20,10,10.),priority_weight=2.)
        self.assertEqual(r.actions,(1,1))
        self.assertEqual(len(calls),r.transition_calls)
        self.assertEqual(r.diagnostics['dominated_candidates'],2)
        self.assertEqual(r.diagnostics['unique_state_keys'],3)
        self.assertEqual(r.diagnostics['generated_labels'],3)

    def test_transition_budget_has_distinct_stop_reason(self):
        args=self.kwargs();args['budget']=Budget(20,1,5,10.)
        r=search(**args,priority_weight=2.)
        self.assertEqual(r.failure,Failure.SEARCH_BUDGET)
        self.assertEqual(r.stop_reason,'transition_limit')
