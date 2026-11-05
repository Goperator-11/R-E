from copy import deepcopy
import itertools
import math

import pytest

from experiments.v33.revisit_reference import Action, ConnectionPolicy, allowed, candidates, first_flight, observation_key


@pytest.mark.parametrize("kw",[{"mode":"x"},{"mode":"none","trail":1},{"mode":"pad"},
    {"mode":"parity"},{"mode":"dup"},{"mode":"pad","delta":True},{"mode":"parity","lead":3,"trail":2},
    {"mode":"pad","delta":253},{"mode":"dup","trail":1.0},{"mode":"dup","trail":-1}])
def test_invalid_actions_rejected(kw):
    with pytest.raises(ValueError):Action(**kw)


@pytest.mark.parametrize("support",["unknown","unsupported"])
def test_no_signal_has_no_parity_but_compares_padding_and_duplicates(support):
    options=[Action(),Action("parity",lead=2),Action("parity",trail=2),Action("pad",delta=32),Action("dup",trail=2)]
    result=candidates(options,token_supplied=False,retry_accepted=False,decoder_support=support)
    assert result==(options[0],options[3],options[4])


@pytest.mark.parametrize("token,retry",[(True,False),(False,True),(True,True)])
def test_token_and_retry_remove_credit_only_choices(token,retry):
    options=[Action(),Action("parity",lead=1,trail=1),Action("parity",delta=7,trail=1),Action("parity",trail=1),
             Action("pad",trail=1),Action("pad",delta=7),Action("dup",lead=1),Action("dup",trail=1)]
    result=candidates(options,token_supplied=token,retry_accepted=retry,decoder_support="supported")
    assert result==(options[0],options[3],options[7])


def test_none_exists_without_templates_and_duplicate_options_are_removed():
    option=Action("dup",trail=1)
    assert candidates([option,option],token_supplied=False,retry_accepted=False,decoder_support="unknown")== (Action(),option)
    assert candidates([],token_supplied=True,retry_accepted=False,decoder_support="unknown")== (Action(),)


def test_one_bundle_budget_survives_retry_and_write_error():
    c=ConnectionPolicy(decoder_support="supported")
    c.reserve("first",Action("parity",lead=3,trail=1))
    assert c.receive_retry(accepted=True)
    for phase in ("retry","pto","followup","response"):
        assert c.choices(phase,[Action("parity",trail=1)])==(Action(),)
    before=deepcopy(c.__dict__)
    with pytest.raises(ValueError):c.reserve("retry",Action("parity",trail=1))
    assert c.__dict__==before
    c.reserve("retry",Action())
    assert not c.receive_retry(accepted=True)
    assert c.extras_reserved


def test_unused_first_budget_can_protect_retry_once():
    c=ConnectionPolicy(decoder_support="supported")
    c.reserve("first",Action())
    assert c.receive_retry(accepted=True)
    with pytest.raises(ValueError):c.reserve("retry",Action("parity",lead=1))
    c.reserve("retry",Action("parity",trail=1))
    assert c.extras_reserved
    with pytest.raises(ValueError):c.reserve("retry",Action())
    assert c.choices("pto",[Action("parity",trail=1)])==(Action(),)


def test_duplicate_budget_applies_to_nonfec_support():
    c=ConnectionPolicy(token_supplied=True)
    c.reserve("first",Action("dup",trail=2))
    assert c.receive_retry(accepted=True)
    assert c.choices("retry",[Action("dup",trail=2)])==(Action(),)


def test_raw_retry_and_late_retry_do_not_change_policy():
    c=ConnectionPolicy()
    c.reserve("first",Action())
    before=deepcopy(c.__dict__)
    assert not c.receive_retry(accepted=False)
    assert c.__dict__==before
    c.receive_peer_packet(processed=False)
    assert c.__dict__==before
    c.receive_peer_packet(processed=True)
    assert not c.receive_retry(accepted=True)


def test_invalid_token_closes_attempt_and_does_not_reset_budget():
    c=ConnectionPolicy(token_supplied=True,decoder_support="supported")
    c.reserve("first",Action("parity",trail=1))
    assert c.invalid_token()==dict(restart_without_token=True,reused_connection=False)
    with pytest.raises(ValueError):c.reserve("first",Action())
    assert c.extras_reserved and not c.receive_retry(accepted=True)
    fresh=ConnectionPolicy(token_supplied=False,decoder_support="supported")
    assert allowed(Action("parity",lead=2),fresh.token_supplied,False,fresh.decoder_support)


@pytest.mark.parametrize("operation",[lambda c:c.receive_retry(accepted=True),lambda c:c.choices("retry",[]),
    lambda c:c.reserve("pto",Action()),lambda c:c.invalid_token(),lambda c:c.reserve("first",Action("parity",trail=1))])
def test_invalid_transitions_are_atomic(operation):
    c=ConnectionPolicy()
    before=deepcopy(c.__dict__)
    with pytest.raises(ValueError):operation(c)
    assert c.__dict__==before


def test_token_presence_is_never_server_validation_or_resumption():
    keys=set()
    for token,retry,server,tls in itertools.product((False,True),(False,True),(None,False,True),(None,False,True)):
        key=observation_key("example.invalid:443",token_supplied=token,retry_accepted=retry,
                            server_initially_validated=server,tls_resumed=tls)
        keys.add(key)
        if tls is None:assert key[2]=="unknown"
        if token and server is None and not retry:assert key[1]=="token_unknown"
    assert len(keys)==27
    assert observation_key("example.invalid:443",token_supplied=True,retry_accepted=False,
        server_initially_validated=False,tls_resumed=True)==("example.invalid:443","token_unvalidated","resumed")


@pytest.mark.parametrize("bad",[1,"yes",[],float("nan")])
def test_inputs_do_not_accept_truthiness(bad):
    with pytest.raises(ValueError):ConnectionPolicy(token_supplied=bad)
    with pytest.raises(ValueError):observation_key("x",token_supplied=False,retry_accepted=False,server_initially_validated=bad,tls_resumed=False)


@pytest.mark.parametrize("loss",[0,.02,.08,.15,1])
def test_delivery_matches_independent_closed_forms_and_exact_bytes(loss):
    for k in range(1,5):
        sizes=[1200+17*i for i in range(k)]
        for total in range(5):
            for lead in range(total+1):
                for mode in ("parity","dup","pad"):
                    action=Action(mode,lead=lead,trail=total-lead) if total else Action()
                    out=first_flight(k,action,loss,original_sizes=sizes,parity_size=1360,decoder_support="supported")
                    if mode=="dup":
                        copies=[1+sum(j%k==i for j in range(total)) for i in range(k)]
                        expected=math.prod(1-loss**n for n in copies)
                        expected_bytes=sum(sizes[i]*copies[i] for i in range(k))
                    elif mode=="parity":
                        n=k+total-lead
                        expected=sum(math.comb(n,j)*(1-loss)**j*loss**(n-j) for j in range(k,n+1))
                        expected_bytes=sum(sizes)+total*1360
                    else:
                        expected=(1-loss)**k
                        expected_bytes=sum(sizes)+total*1360
                    assert out["p_complete"]==pytest.approx(expected,abs=1e-12)
                    assert out["probability_mass"]==pytest.approx(1,abs=1e-12)
                    assert out["sent_bytes"]==expected_bytes
                    assert out["expected_physical_bytes"]==pytest.approx(expected_bytes*(1-loss),abs=1e-8)
                    assert out["hct_ms"] is None


def test_hold_support_and_k1_duplicate_equivalence():
    for p in (.08,.15):
        for k in range(1,5):
            lead=first_flight(k,Action("parity",lead=2),p,original_sizes=[1280]*k,parity_size=1338,
                              decoder_support="supported",hold_lead=True)
            trail=first_flight(k,Action("parity",trail=2),p,original_sizes=[1280]*k,parity_size=1338,decoder_support="supported")
            assert lead["p_complete"]==pytest.approx(trail["p_complete"],abs=1e-12)
        values=[]
        for mode in ("parity","dup"):
            values.append(first_flight(1,Action(mode,trail=1),p,original_sizes=[1280],parity_size=1325,decoder_support="supported")["p_complete"])
        assert values[0]==values[1]


@pytest.mark.parametrize("support",["unknown","unsupported"])
def test_forced_parity_diagnostic_assigns_zero_recovery_without_support(support):
    out=first_flight(2,Action("parity",trail=4),.15,original_sizes=[1280,1280],parity_size=1338,decoder_support=support,hold_lead=True)
    assert out["p_complete"]==pytest.approx(.85**2)
    assert not allowed(Action("parity",trail=4),False,False,support)


@pytest.mark.parametrize("loss",[True,-.1,1.1,float("nan"),float("inf")])
def test_invalid_loss_does_not_create_probabilities(loss):
    with pytest.raises(ValueError):first_flight(2,Action(),loss,original_sizes=[1280,1280],parity_size=1338,decoder_support="unknown")
