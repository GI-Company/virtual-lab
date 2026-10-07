"""Rebuild the benchmark from Shalem et al. Supplementary Table 1 (requires xlrd).

Usage: python extract_pgk1.py /path/to/msb200859-s2.xls
No network requests, fit-quality selection, or sample substitution.
"""
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
import xlrd

source=Path(sys.argv[1]);sheet=xlrd.open_workbook(str(source)).sheet_by_name('Sheet1')
matches=[i for i in range(sheet.nrows) if sheet.cell_value(i,0)=='YCR012W']
if len(matches)!=1:raise ValueError('Expected exactly one YCR012W row')
index=matches[0]
assert sheet.cell_value(0,13)=='normalized decay profile reference'
assert 'refernce2' in sheet.cell_value(0,52)
rows=[]
for replicate,split,columns in [('1','train',range(13,22)),('2','holdout',range(52,58))]:
 for col in columns:
  minute=float(re.search(r't\s*=\s*(\d+)',sheet.cell_value(1,col))[1])
  rows.append(dict(sample_id=f'S1:YCR012W:ref{replicate}:t{minute:g}',replicate=replicate,
      split=split,time_min=minute,value=sheet.cell_value(index,col)))
out=Path(__file__).parent
with (out/'pgk1_decay.csv').open('w') as f:
 writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
metadata=dict(dataset_id='Shalem2008-S1-PGK1-reference',title='Yeast PGK1 mRNA decay after transcription shutoff',
 gene='PGK1',systematic_id='YCR012W',organism='Saccharomyces cerevisiae',strain='Y262 rpb1-1',
 condition='Reference transcription arrest by temperature shift; no added chemical stress',
 source_url='https://pmc.ncbi.nlm.nih.gov/articles/instance/2583085/bin/msb200859-s2.xls',
 download_url='https://www.ebi.ac.uk/europepmc/webservices/rest/PMC2583085/supplementaryFiles',
 source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source_sheet='Sheet1',source_excel_row=index+1,
 source_zero_based_columns={'train':list(range(13,22)),'holdout':list(range(52,58))},
 citation='Shalem et al. (2008), Molecular Systems Biology 4:223, doi:10.1038/msb.2008.59, Supplementary Table 1',
 paper_url='https://pmc.ncbi.nlm.nih.gov/articles/PMC2583085/',geo_accession='GSE12221',value_scale='linear',
 processing='Author-provided normalized relative abundance; baseline already scaled to one in the supplementary table.',
 split_rule='Reference profile trains; reference2 (identified by authors as control) is held out. Fixed before fitting these curves.',
 selection_rule='PGK1 was chosen before inspecting fit quality. Source switched from GEO intensities to explicit author-normalized curves to avoid unresolved preprocessing discrepancy, not to optimize holdout performance.',
 csv_sha256=hashlib.sha256((out/'pgk1_decay.csv').read_bytes()).hexdigest(),retrieved_at='2026-09-26',
 author_training_half_life_min=sheet.cell_value(index,23),
 limitations=['A single gene and condition from one publication; no independent-laboratory validation.',
 'Input values are author-processed relative abundances, not raw measurements or a new wet-lab experiment.',
 'Each curve uses its own measured baseline. Baseline points are excluded from fit and metrics.',
 'Held-out positive times span 5–30 minutes; training spans 5–60 minutes.',
 'GEO intensity transformation was not reconciled with the supplement; this benchmark uses only the explicitly normalized supplemental curves.',
 'No inferred protein, drug-response, human, or clinical parameters.'])
(out/'pgk1_decay.json').write_text(json.dumps(metadata,indent=2)+'\n')
print('Extracted',len(rows),'values from Excel row',index+1)
