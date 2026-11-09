"""3D presence only, never a STEP geometry/enclosure verdict."""
import re
from pathlib import Path
from kicad_tools.sexp import parse_string
from extrude.parse.kicad_pcb import _rows, _reference, _PARSE_LOCK


def inspect(text, board: Path, root: Path, repo_files=None):
    with _PARSE_LOCK:
        doc = parse_string(text)
    rows = []
    for fp in doc.children:
        if fp.name not in {'footprint','module'}:
            continue
        models = list(_rows(fp,'model'))
        statuses=[]
        for model in models:
            name = str(model.values[0])
            expanded = name.replace('${KIPRJMOD}',str(board.parent))
            candidate = (board.parent / expanded).resolve()
            if '$' in expanded or not candidate.is_relative_to(root.resolve()):
                status='not checked'
            else:
                exists = candidate.is_file() if repo_files is None else candidate.relative_to(root.resolve()).as_posix() in repo_files
                status='present' if exists else 'missing'
            statuses.append(dict(model=name,status=status))
        rows.append(dict(part=_reference(fp), models=statuses, status='referenced' if models else 'missing'))
    return dict(footprints=rows, step_export='not checked', enclosure_fit='not checked', part_height='not checked')
