import argparse
import sys
from virtual_lab.core.provenance_export import explain_provenance

def main():
    parser = argparse.ArgumentParser(description="Verify and explain the provenance of a .vlab bundle.")
    parser.add_argument("bundle", help="Path to the .vlab bundle to verify.")
    
    args = parser.parse_args()
    
    report = explain_provenance(args.bundle)
    print(report)
    
    if "Error:" in report or "[WARNING]" in report:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
