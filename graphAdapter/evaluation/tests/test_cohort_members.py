import pytest
from graphAdapter.evaluation.cohort_runner import choose_members

def test_exact_declared_order_and_full_identity():
 a=('r2r','scene/one.glb','1','-');b=('r2r','scene/two.glb','1','-')
 allowed=[dict(identity=a,row={'id':'a'}),dict(identity=b,row={'id':'b'})]
 assert choose_members([dict(member=b),dict(member=a)],'r2r',allowed)==[allowed[1],allowed[0]]
 with pytest.raises(ValueError,match='Duplicate'):choose_members([dict(member=a),dict(member=a)],'r2r',allowed)
 with pytest.raises(ValueError,match='sealed A'):choose_members([dict(member=('r2r','other','1','-'))],'r2r',allowed)

def test_incomplete_identity_is_not_guessed():
 with pytest.raises(ValueError,match='four-field'):choose_members([dict(member=['r2r','1'])],'r2r',[])
