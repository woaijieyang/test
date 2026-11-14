import pytest
from open_clip.tokenizer import SimpleTokenizer
from graphAdapter.map_memory.retrieval import query_adapter


def test_full_instruction_tail_and_actual_capacity_are_preserved():
    tokenizer=SimpleTokenizer(context_length=19)
    instruction='Walk past the chairs and through the corridor. '*30+'Stop beside the piano.'
    windows=query_adapter.window_instruction(instruction,tokenizer,overlap=5)
    original=tokenizer.encode(instruction);covered=set()
    for window in windows:
        assert window.token_ids[0]==tokenizer.sot_token_id and window.token_ids[-1]==tokenizer.eot_token_id
        assert len(window.token_ids)<=tokenizer.context_length
        assert tuple(window.token_ids[1:-1])==tuple(original[window.start:window.end])
        assert len(tokenizer.encode(window.text))+2<=tokenizer.context_length
        covered.update(range(window.start,window.end))
    assert covered==set(range(len(original))) and windows[-1].end==len(original)
    assert 'piano' in windows[-1].text


def test_windowing_is_deterministic_and_never_uses_truncating_call():
    tokenizer=SimpleTokenizer(context_length=11)
    class ExplicitOnly:
        context_length=11;sot_token_id=tokenizer.sot_token_id;eot_token_id=tokenizer.eot_token_id
        encode=tokenizer.encode;decode=tokenizer.decode
        def __call__(self,*a,**k):raise AssertionError('Silent truncation API must not be used')
    text='Go to the café, pass the blue sofa, then find the last doorway.'
    assert query_adapter.window_instruction(text,ExplicitOnly(),overlap=3)==query_adapter.window_instruction(text,ExplicitOnly(),overlap=3)


def test_invalid_window_policy_fails_instead_of_dropping_text():
    tokenizer=SimpleTokenizer(context_length=8)
    with pytest.raises(ValueError):query_adapter.window_instruction('go forward',tokenizer,overlap=6)
    with pytest.raises(ValueError):query_adapter.window_instruction('',tokenizer,overlap=2)
