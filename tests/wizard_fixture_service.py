"""Run the unmodified local HTTP service against two disposable host config targets."""
import argparse
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'apps/local-service'))
import server
import host_wizard


if __name__ == '__main__':
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--data-dir',required=True,type=Path)
    args,_=parser.parse_known_args()
    directory=args.data_dir.resolve().parent/'qa-hosts'
    if not directory.is_dir() or not (directory/'TEST-PROFILE').is_file():
        raise SystemExit('Create the private test configuration via dashboard_extra_browser.py first.')
    fixture={'claude':(directory/'claude_desktop_config.json',None,False),
             'codex':(directory/'config.toml',None,False)}
    with patch.object(host_wizard,'targets',return_value=fixture):
        raise SystemExit(server.main())
