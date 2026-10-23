"""Explicit extension adapters: python -m virtual_lab.extensions --help."""
import argparse
import os
from pathlib import Path
from virtual_lab.core.canonical import strict_json_loads

def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--workspace', required=True, type=Path,
        help='Explicit scratch/beta workspace; never choose production research storage')
    sub = parser.add_subparsers(dest='command', required=True)
    ode = sub.add_parser('simulate'); ode.add_argument('manifest'); ode.add_argument('--hours', type=float, default=1)
    predict = sub.add_parser('predict'); predict.add_argument('manifest'); predict.add_argument('inputs', help='JSON input object')
    instrument = sub.add_parser('import-csv'); instrument.add_argument('manifest'); instrument.add_argument('csv')
    assistant = sub.add_parser('assistant'); assistant.add_argument('endpoint'); assistant.add_argument('model')
    assistant.add_argument('prompt'); assistant.add_argument('--allow-network', action='store_true')
    args = parser.parse_args()
    from .models import import_ode, predict_linear
    from .instruments import CSVInstrument, save_extension_run
    from virtual_lab.core.ledger import GenesisLedger
    if args.command == 'simulate':
        from virtual_lab.gui.services.simulation_runner import RunConfig, run_simulation
        spec = import_ode(args.manifest, args.workspace / 'model-snapshots')
        result = run_simulation(RunConfig(model_id=spec.id, duration_h=args.hours, members=8, variation=0))
        result['kind'] = 'simulation_model'
    elif args.command == 'predict': result = predict_linear(args.manifest, strict_json_loads(args.inputs))
    elif args.command == 'import-csv': result = CSVInstrument(args.manifest).acquire(args.csv)
    else:
        from .assistant import AssistantEndpoint
        result = AssistantEndpoint(args.endpoint, args.model, os.environ.get('VIRTUALLAB_BYOM_API_KEY')).critique(
            args.prompt, allow_network=args.allow_network)
    args.workspace.mkdir(parents=True, exist_ok=True)
    ledger = GenesisLedger(str(args.workspace / 'genesis.db'))
    try: print(save_extension_run(result, args.workspace / 'extension-results', ledger))
    finally: ledger.conn.close()

if __name__ == '__main__': main()
