import numpy as np
import pytest
from virtual_lab.biology.timing import growth_slowdown_frame


def trace():
    frames=np.arange(10,91);rates=np.full(len(frames),.02);rates[frames>=45]=.008
    return frames,rates


def test_detects_sustained_growth_drop_without_fluorescence():
    frames,rates=trace();result=growth_slowdown_frame(frames,rates)
    assert result['frame']==45
    assert result['reference_fractional_growth_per_min']==pytest.approx(.02)
    assert 'not an exact' in result['interpretation']


def test_transient_drop_is_not_onset_and_no_event_remains_unknown():
    frames,rates=trace();rates[(frames>=32)&(frames<36)]=.001
    assert growth_slowdown_frame(frames,rates)['frame']==45
    assert growth_slowdown_frame(frames,np.full(len(frames),.02))['frame'] is None


def test_last_supported_persistent_window_is_detectable():
    frames,rates=trace();rates[:]=.02;rates[frames>=86]=.005
    assert growth_slowdown_frame(frames,rates)['frame']==86


@pytest.mark.parametrize('fault',['nan','gap','fraction','zero_reference','too_short','duplicate'])
def test_invalid_timing_data_rejected(fault):
    frames,rates=trace();kwargs={}
    if fault=='nan':rates[0]=float('nan')
    if fault=='gap':frames=frames+1
    if fault=='fraction':kwargs['fraction']=1
    if fault=='zero_reference':rates[:]=0
    if fault=='too_short':frames=frames[:20];rates=rates[:20]
    if fault=='duplicate':frames[1]=frames[0]
    with pytest.raises(ValueError):growth_slowdown_frame(frames,rates,**kwargs)
