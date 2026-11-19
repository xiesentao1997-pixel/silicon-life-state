"""Read tool arguments from stdin. This is a protocol client, unrelated to model inference."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "mcp-server"))
from local_client import message, send

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", nargs="?", help="Tool name; omit to list tools. Tool arguments are JSON on stdin.")
    args=parser.parse_args()
    try:
        if args.tool:
            arguments=json.load(sys.stdin)
            if not isinstance(arguments,dict):
                raise ValueError("Tool arguments must be a JSON object")
            request=message("tools/call",{"name":args.tool,"arguments":arguments})
        else:
            request=message("tools/list")
        reply=send(request)
    except (ValueError,OSError) as exc:
        sys.stderr.write("Unable to call the local service: "+str(exc)+"\n")
        return 1
    sys.stdout.buffer.write((json.dumps(reply,ensure_ascii=False,indent=2)+"\n").encode("utf-8"))
    return int("error" in reply or reply.get("result",{}).get("isError",False))

if __name__ == "__main__":
    raise SystemExit(main())
