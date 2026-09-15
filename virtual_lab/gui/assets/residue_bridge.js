// Mol* OrderedSet supports an Int32Array or an interval packed in a Float64.
function firstIndex(indices) {
    if (typeof indices !== 'number') return indices.length ? indices[0] : null;
    const f = new Float64Array([indices]); const pair = new Int32Array(f.buffer);
    return pair[1] > pair[0] ? pair[0] : null;
}
function residueFromLoci(loci) {
    if (!loci || loci.kind !== 'element-loci' || !loci.elements.length) return null;
    const e = loci.elements[0], u = e.unit;
    if (u.kind !== 0) return null;
    const index = firstIndex(e.indices); if (index === null) return null;
    const atom = u.elements[index], h = u.model.atomicHierarchy;
    const r = h.residueAtomSegments.index[atom], c = h.chainAtomSegments.index[atom];
    const ins = h.residues.pdbx_PDB_ins_code.value(r);
    return {structure_id: u.model.entryId, model_id: u.model.modelNum,
        chain_id: h.chains.auth_asym_id.value(c), auth_residue_number: h.residues.auth_seq_id.value(r),
        insertion_code: ins === '.' || ins === '?' ? '' : ins};
}
function residueLoci(structure, ref) {
    const elements = [];
    for (const unit of structure.units) {
        if (unit.kind !== 0 || unit.model.entryId.toUpperCase() !== ref.structure_id.toUpperCase() || unit.model.modelNum !== ref.model_id) continue;
        const h = unit.model.atomicHierarchy, indices = [];
        for (let i=0; i<unit.elements.length; i++) {
            const a=unit.elements[i], r=h.residueAtomSegments.index[a], c=h.chainAtomSegments.index[a];
            const ins=h.residues.pdbx_PDB_ins_code.value(r);
            if (h.chains.auth_asym_id.value(c) === ref.chain_id && h.residues.auth_seq_id.value(r) === ref.auth_residue_number && (ins === '.' || ins === '?' ? '' : ins) === (ref.insertion_code || '')) indices.push(i);
        }
        if (indices.length) elements.push({unit, indices: Int32Array.from(indices)});
    }
    return {kind: 'element-loci', structure, elements};
}
if (typeof module !== 'undefined') module.exports = {firstIndex,residueFromLoci,residueLoci};
