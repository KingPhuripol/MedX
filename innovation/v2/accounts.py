"""Create five synthetic-workspace access credentials without printing secrets.

python -m innovation.v2.accounts --output .secrets/principals.json
Distribute individual tokens privately. They authenticate prototype roles only.
"""
import argparse
import json
import os
from pathlib import Path
import secrets


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--workspace',default='team')
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    principals=[{'subject':subject,'role':role,'workspace':args.workspace,'token':secrets.token_urlsafe(32)}
        for subject,role in [('intake-1','intake'),('intake-2','intake'),('reviewer-1','physician'),
                             ('reviewer-2','physician'),('evaluation-1','evaluator')]]
    fd=os.open(args.output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as f:json.dump({'principals':principals},f,indent=2)
    print('Created five prototype accounts; credentials are in the private output file.')

if __name__=='__main__':main()
