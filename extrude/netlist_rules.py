"""Original conservative checks over native exported connectivity; no reviewer dependency."""
from collections import Counter, defaultdict
from kicad_tools.sexp import parse_string
from extrude.parse.kicad_pcb import _rows, _string_field, _PARSE_LOCK


def review(text):
    with _PARSE_LOCK:
        root = parse_string(text)
    boxes = list(_rows(root, 'components'))
    networks = list(_rows(root, 'nets'))
    if root.name != 'export' or len(boxes) != 1 or len(networks) != 1:
        return dict(status='unverified', findings=[])
    components = list(_rows(boxes[0], 'comp'))
    nets = list(_rows(networks[0], 'net'))
    if not components or not nets or not any(list(_rows(n,'node')) for n in nets):
        return dict(status='unverified', findings=[])
    findings = []
    def emit(rule, ref, pin, net, detail, action):
        # Native export is the evidence file; preserve source lines for each record.
        marker = f'(ref "{ref}")' if f'(ref "{ref}")' in text else f'(ref {ref})'
        line = text.count('\n', 0, max(0,text.find(marker)))+1
        findings.append(dict(rule=rule, part=ref, pin=pin, net=net, line=line,
                             consequence=detail, next_action=action))
    counts = Counter(_string_field(c,'ref') for c in components)
    for comp in components:
        ref = _string_field(comp,'ref')
        if counts[ref] > 1:
            emit('duplicate_reference',ref,None,None,'Physical reference is duplicated; connectivity is ambiguous.','Annotate unique references and export again.')
        if not _string_field(comp,'footprint') and not ref.startswith(('#','H')):
            emit('missing_footprint',ref,None,None,'No footprint is assigned.','Assign and verify the physical footprint or exclude this symbol from the board.')
    for net in nets:
        nodes = list(_rows(net,'node')); name = _string_field(net,'name')
        unique = {(_string_field(n,'ref'),_string_field(n,'pin')) for n in nodes}
        drivers = [n for n in nodes if _string_field(n,'pintype') in {'output','power_out','bidirectional','tri_state','open_collector','open_emitter'}]
        for n in nodes:
            kind = _string_field(n,'pintype'); function = _string_field(n,'pinfunction')
            if kind == 'no_connect' or function in {'NC','SBU1','SBU2'}:
                continue
            ref,pin = _string_field(n,'ref'),_string_field(n,'pin')
            if len(unique) == 1:
                emit('single_pin_net',ref,pin,name,'Net has only one physical pin; intent is not established by its name.','Check the pin function and either connect it or document a valid NC.')
                if kind in {'input','power_in'}:
                    emit('floating_input',ref,pin,name,'Input has no connected peer.','Check required bias or supply from symbol/datasheet.')
            elif kind in {'input','power_in'} and not drivers:
                emit('undriven_net',ref,pin,name,'No explicit driver is present in the exported net; passive bias may be intentional.','Inspect passive bias and source connectivity; this is a review candidate.')
    return dict(status='ran',findings=findings)
