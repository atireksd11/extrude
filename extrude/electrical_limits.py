"""Arithmetic with explicitly sourced operating bounds, never inferred from part names.

Optional .extrude/electrical-limits.json supplies named numeric inputs. Each input
must carry {value, path, line}; path/line must identify a saved source in this
revision. These are engineering assumptions, not measured board behavior.
"""
from math import isfinite


def evaluate(config, read_source):
    rows=[]
    def inputs(values):
        result={}; evidence=[]
        for name,item in values.items():
            value=item['value']; path=item['path']; line=item['line']
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value) or value<0:
                raise ValueError('Operating bounds must be finite nonnegative numbers')
            text=read_source(path)
            if not isinstance(line,int) or line<1 or line>len(text.splitlines()):
                raise ValueError('Operating bound has no source line')
            result[name]=value
            evidence.append(dict(path=path,line=line,part='operating assumption',pin=None,value=value,
                                 quantity=name,quote=text.splitlines()[line-1]))
        return result,evidence
    for case in config.get('fuses',[]):
        v,ev=inputs(case['inputs'])
        load=sum(value for name,value in v.items() if name.startswith('load_a_'))
        if not any(name.startswith('load_a_') for name in v) or v['hold_a']<=0:
            raise ValueError('Fuse needs positive derated hold current and at least one load bound')
        ratio=load/v['hold_a']
        if ratio>=.8:
            rows.append(dict(rule='power.fuse_margin',severity='warning',summary=f"{case['part']}: load bound {load:.4g} A / hold {v['hold_a']:.4g} A = {ratio:.1%} utilization.",
                consequence='Low fuse hold-current headroom can cause nuisance trips; ambient derating and startup are consequential.',
                next_action='Verify the sourced load scenario, temperature derating and inrush against the exact fuse curve.',evidence=ev,measurements=dict(load_a=load,hold_a=v['hold_a'],utilization=ratio)))
    for case in config.get('drives',[]):
        v,ev=inputs(case['inputs'])
        if any(v[key]<=0 for key in ('led_resistance_ohm','base_resistance_ohm','coil_a','forced_beta')):
            raise ValueError('Drive resistances, load and forced beta must be positive')
        led=max(0,(v['drive_v']-v['indicator_vf']-v['opto_vf'])/v['led_resistance_ohm'])
        base=min(led*v['ctr_min'],max(0,(v['collector_v']-v['opto_vce']-v['base_vbe'])/v['base_resistance_ohm']))
        capacity=base*v['forced_beta'];margin=capacity/v['coil_a']-1
        if margin<.5:
            rows.append(dict(rule='power.drive_margin',severity='warning',summary=f"{case['part']}: LED {led*1000:.3g} mA, base {base*1000:.3g} mA, estimated drive margin {margin:.1%}.",
                consequence='Optocoupler CTR limits base drive; relay pickup may be unreliable at worst-case gain and temperature.',
                next_action='Verify CTR at the actual LED current and temperature, saturation assumptions and relay pickup current; increase guaranteed drive margin.',evidence=ev,
                measurements=dict(led_a=led,base_a=base,capacity_a=capacity,margin=margin)))
    return rows
