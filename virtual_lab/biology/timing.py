"""Growth-response timing proxies; never exact drug-delivery annotations."""
import numpy as np


def growth_slowdown_frame(frames, rates, fraction=.5, sustained=5):
    frames=np.asarray(frames);rates=np.asarray(rates,dtype=float)
    if frames.ndim!=1 or rates.shape!=frames.shape or len(frames)<30:
        raise ValueError('A complete one-dimensional growth trace is required.')
    if not np.isfinite(frames).all() or not np.isfinite(rates).all() or np.any(frames!=frames.astype(int)) or np.any(np.diff(frames)!=1):
        raise ValueError('Frames must be contiguous integers and growth rates finite.')
    if isinstance(fraction,bool) or not np.isfinite(fraction) or not 0<fraction<1:
        raise ValueError('Threshold must be a fraction between zero and one.')
    if isinstance(sustained,bool) or not isinstance(sustained,int) or sustained<1:
        raise ValueError('Persistence must be a positive number of frames.')
    if not set(range(10,91)).issubset(set(frames.tolist())):
        raise ValueError('Frames 10–90 are required by the timing protocol.')
    baseline=float(np.median(rates[(frames>=10)&(frames<=30)]))
    if baseline<=0:raise ValueError('Positive pre-response growth is required.')
    lookup=dict(zip(frames.tolist(),rates.tolist()));onset=None
    for frame in range(31,91-sustained+1):
        if all(lookup[f]<=baseline*fraction for f in range(frame,frame+sustained)):
            onset=frame;break
    return dict(frame=onset,reference_fractional_growth_per_min=baseline,
                threshold_fraction=fraction,sustained_frames=sustained,
                interpretation='Growth-response proxy; not an exact intervention timestamp')
