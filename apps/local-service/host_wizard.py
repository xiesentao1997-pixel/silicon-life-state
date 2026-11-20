"""Owner-initiated host setup. Only fixed local config files and our own bridge may be used."""
import copy
import hashlib
import http.client
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

try:
    import tomllib
except ImportError:  # Supported Python 3.10
    from _vendor import tomli as tomllib

from account_profile import account_binding
from access import AccessError
from mcp_wire import PREFIX, VERSION

ROOT = Path(__file__).resolve().parents[2]
NAME = "silicon_life_state"
CONFIG_LIMIT = 2 * 1024 * 1024
BEGIN = "# BEGIN Silicon Life State MCP"
END = "# END Silicon Life State MCP"
MASK = "<私有凭据文件路径或分身令牌>"
PROBE = "silicon-life-state-wizard-probe"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class HostAdapter:
    format: str
    manual: str
    transport_type: bool = False

    @property
    def servers_key(self):
        return "mcp_servers" if self.format == "toml" else "mcpServers"


ADAPTERS = {
    "codex": HostAdapter("toml", "在个人 config.toml 合并此表，重新启动 Codex，使用 /mcp 检查工具。"),
    "claude": HostAdapter("json", "在 Claude Desktop 的设置 → 开发者 → 编辑配置合并条目，完全退出后重新启动。在 Customize → Skills 上传本版 Skill.zip。"),
    "cursor": HostAdapter("json", "在 Cursor Settings → Tools & MCP 打开个人 ~/.cursor/mcp.json，合并此 stdio 条目并重新加载。", True),
    "other": HostAdapter("manual", "按宿主说明填写本机 command、args 和 env。HTTP 方式填写 URL 和 Authorization。宿主不支持本机 MCP 时，请使用已支持的客户端。"),
}

def targets():
    home = Path.home()
    codex_dir = Path(os.environ.get("CODEX_HOME") or home / ".codex")
    exe = shutil.which("codex")
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData/Local")
        classic = Path(os.environ.get("APPDATA") or home / "AppData/Roaming") / "Claude"
        store = local / "Packages/Claude_pzs8sxrjxfjjc/LocalCache/Roaming/Claude"
        candidates = [p / "claude_desktop_config.json" for p in (classic, store)]
        matches = [p for p in candidates if p.exists()]
        ambiguous = len(matches) > 1
        claude = matches[0] if matches else candidates[1 if store.is_dir() else 0]
        app = next((p for p in (local/"Programs/claude/Claude.exe",local/"AnthropicClaude/claude.exe",
                                local/"Microsoft/WindowsApps/claude.exe") if p.is_file()), None)
    else:
        ambiguous = False
        claude_dir = home / ("Library/Application Support/Claude" if sys.platform == "darwin" else ".config/Claude")
        claude = claude_dir / "claude_desktop_config.json"
        if sys.platform == "darwin":
            app = next((p for p in (Path("/Applications/Claude.app"),home/"Applications/Claude.app") if p.is_dir()),None)
        else:
            app = shutil.which("claude-desktop")
    cursor = shutil.which("cursor")
    if not cursor and sys.platform == "win32":
        candidate = local / "Programs/cursor/Cursor.exe"
        cursor = candidate if candidate.is_file() else None
    if not cursor and sys.platform == "darwin":
        cursor = next((p for p in (Path("/Applications/Cursor.app"),home/"Applications/Cursor.app") if p.is_dir()),None)
    return {"codex": (codex_dir/"config.toml", exe, False), "claude": (claude, app, ambiguous),
            "cursor": (home/".cursor/mcp.json", cursor, False)}


def safe_file(path):
    """Read a small regular file; avoid writing through symlinks/junctions."""
    for component in (path, *path.parents):
        if component.is_symlink() or getattr(component,"is_junction",lambda: False)():
            raise ValueError("配置路径包含链接。请用宿主的配置编辑器手动合并。")
    try:
        flags = os.O_RDONLY | getattr(os,"O_NOFOLLOW",0) | getattr(os,"O_NONBLOCK",0) | getattr(os,"O_BINARY",0)
        with os.fdopen(os.open(path,flags),"rb") as f:
            st = os.fstat(f.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_size > CONFIG_LIMIT:
                raise ValueError("配置须为 2 MiB 以内的普通文件。")
            data = f.read(CONFIG_LIMIT+1)
            if len(data)>CONFIG_LIMIT:
                raise ValueError("配置文件超过大小限制。")
            return data
    except FileNotFoundError:
        return None


def strict_json(text):
    def unique(pairs):
        out={}
        for k,v in pairs:
            if k in out:
                raise ValueError("JSON 中存在重复字段。")
            out[k]=v
        return out
    def invalid(_):
        raise ValueError("JSON 中存在非标准数字。")
    return json.loads(text,object_pairs_hook=unique,parse_constant=invalid)


def parse_config(host,raw):
    try:
        text = raw.decode("utf-8-sig")
        doc = tomllib.loads(text) if ADAPTERS[host].format=="toml" else strict_json(text)
    except (ValueError,UnicodeError,RecursionError) as exc:
        raise ValueError("现有配置语法无效。请先在宿主编辑器修正，原文件已保留。") from exc
    key = ADAPTERS[host].servers_key
    if not isinstance(doc,dict) or not isinstance(doc.get(key,{}),dict):
        raise ValueError("配置顶层与 MCP 服务列表必须是对象。")
    return doc


def snippet(host,entry):
    if ADAPTERS[host].format=="manual":
        # A transport description, not a universal host config file.
        return json.dumps(entry, ensure_ascii=False, indent=2)
    if ADAPTERS[host].format=="json":
        return json.dumps({ADAPTERS[host].servers_key:{NAME:entry}},ensure_ascii=False,indent=2)
    q = lambda s: json.dumps(s,ensure_ascii=False)
    return ("[mcp_servers."+NAME+"]\ncommand = "+q(entry["command"])+"\nargs = "+q(entry["args"])+
            "\n\n[mcp_servers."+NAME+".env]\n"+
            "".join(k+" = "+q(v)+"\n" for k,v in entry["env"].items()))


def merged(host,old,entry):
    doc = parse_config(host,old) if old is not None else {}
    key = ADAPTERS[host].servers_key
    servers = doc.get(key,{})
    legacy_name = "silicon-life-state"
    def known_bridge(value):
        if not isinstance(value,dict):
            return False
        args = value.get("args",[])
        env = value.get("env",{})
        return isinstance(args,list) and isinstance(env,dict) and bool({"SILICON_AGENT_TOKEN","SILICON_INSTALLATION_FILE","SILICON_ACCOUNT_GRANTS"} & env.keys()) and any(
            isinstance(arg,str) and arg.replace("\\","/").endswith("/packages/mcp-server/stdio.py") for arg in args)
    # 1.0.0 emitted the hyphenated JSON key. Only migrate entries identifiable
    # by our script and grant variable; other applications keep their own keys.
    migrate = host=="claude" and known_bridge(servers.get(legacy_name))
    if migrate and NAME in servers:
        raise ValueError("此配置存在两个本项目服务名。请手动选择要保留的绑定。")
    existing = servers.get(legacy_name if migrate else NAME)
    if existing == entry and not migrate:
        return old, "已匹配"
    expected = copy.deepcopy(doc)
    if migrate:
        del expected[key][legacy_name]
    expected.setdefault(key,{})[NAME]=entry
    if ADAPTERS[host].format=="toml":
        if isinstance(existing,dict) and (set(existing)-{"command","args","env"} or
                isinstance(existing.get("env"),dict) and set(existing["env"])-set(entry["env"])-{"SILICON_DEDICATED_PROFILE","SILICON_AGENT_TOKEN","SILICON_INSTALLATION_FILE","SILICON_ACCOUNT_GRANTS","SILICON_CODEX_PROFILE"}):
            raise ValueError("本项目的 Codex 条目含额外个人设置，请手动合并以保留这些设置。")
        text = old.decode("utf-8-sig") if old is not None else ""
        # Only remove a block produced by this wizard. Semantic verification below
        # ensures embedded comments or marker-like literals cannot swallow other TOML.
        block = re.compile(r"^"+re.escape(BEGIN)+r"\r?$.*?^"+re.escape(END)+r"\r?$(?:\n)?",re.M|re.S)
        matches = list(block.finditer(text))
        if existing is not None and len(matches)!=1:
            raise ValueError("同名 Codex 服务由其他工具维护。请在编辑器中手动合并本项目条目。")
        if len(matches)>1 or (matches and existing is None):
            raise ValueError("配置中的向导标记不唯一，请手动合并。")
        section = BEGIN+"\n"+snippet(host,entry).rstrip()+"\n"+END+"\n"
        if "\r\n" in text:
            section = section.replace("\n","\r\n")
        if matches:
            match=matches[0]
            updated=text[:match.start()]+section+text[match.end():]
        else:
            updated=text+("" if not text else "\n" if text.endswith("\n") else "\n\n")+section
    else:
        if existing is not None and not known_bridge(existing):
            raise ValueError("同名服务已有其他用途。原配置已保留，请手动选择服务名。")
        if isinstance(existing,dict):
            retained = {k:v for k,v in existing.get("env",{}).items() if k not in {"SILICON_AGENT_TOKEN","SILICON_INSTALLATION_TOKEN","SILICON_CONVERSATION_ID"}}
            expected[key][NAME]={**existing,**entry,"env":{**retained,**entry["env"]}}
        updated = json.dumps(expected,ensure_ascii=False,indent=2,allow_nan=False)+"\n"
    raw=updated.encode("utf-8")
    if parse_config(host,raw)!=expected:
        raise ValueError("合并校验未通过，请手动合并。")
    return raw,"更新本项目条目" if existing is not None else "新增本项目条目"


def fingerprint(data):
    return None if data is None else hashlib.sha256(data).hexdigest()


def atomic_install(path,expected,new):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    old=safe_file(path)
    if fingerprint(old)!=expected:
        raise AccessError(409,"CONFIG_CHANGED","配置在预览后已改变。请重新检查，再确认写入。")
    if old==new:
        return None
    def private_write(fd,data):
        with os.fdopen(fd,"wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    backup=None
    fd,name=tempfile.mkstemp(prefix=".sls-config-",dir=path.parent)
    tmp=Path(name)
    try:
        private_write(fd,new)
        if old is not None:
            backup=path.with_name(path.name+".sls-"+datetime.now().strftime("%Y%m%d-%H%M%S")+"-"+secrets.token_hex(3)+".bak")
            private_write(os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_BINARY",0),0o600),old)
        if safe_file(path)!=old:
            raise AccessError(409,"CONFIG_CHANGED","写入前发现配置变化。请重新预览。")
        if old is None:
            try:
                os.link(tmp,path)  # Atomic no-clobber creation.
            except FileExistsError as exc:
                raise AccessError(409,"CONFIG_CHANGED","目标配置已出现。请重新预览。") from exc
        else:
            os.replace(tmp,path)
        if os.name!="nt":
            parent=os.open(path.parent,os.O_RDONLY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        return str(backup) if backup else None
    finally:
        tmp.unlink(missing_ok=True)


class HostWizard:
    def __init__(self,store,base_url,paths=None):
        self.store=store
        self.url=base_url+"/mcp"
        self.user_home=Path.home() if paths is None else Path(paths["codex"]).parent.parent if "codex" in paths else None
        self.targets=targets() if paths is None else {k:(Path(p),None,False) for k,p in paths.items()}
        self.plans=OrderedDict()
        self.discoveries=OrderedDict()
        self.lock=threading.Lock()

    def entry(self,transport,credential,host="claude"):
        if transport=="http":
            return {"url":self.url,"headers":{"Authorization":"Bearer "+credential}}
        entry = {"command":sys.executable, "args":[str(ROOT/"packages/mcp-server/stdio.py")],
                 "env":{"SILICON_INSTALLATION_FILE":str(credential), "SILICON_MCP_URL":self.url,
                        "SILICON_DATA_DIR":str(self.store.files.home), "SILICON_HOST":host}}
        if ADAPTERS[host].transport_type:
            entry["type"] = "stdio"
        return entry

    def discovery(self,grant,msg):
        info=msg.get("params",{}).get("_meta",{}).get(PREFIX+"clientInfo",{})
        client=info.get("name","") if isinstance(info,dict) else ""
        if client==PROBE:
            return
        with self.lock:
            self.discoveries[grant]={"client":str(client)[:128] or "未提供客户端名称","at":now()}
            self.discoveries.move_to_end(grant)
            if len(self.discoveries)>512:
                self.discoveries.popitem(last=False)

    def status(self,plan):
        state=self.store.admin("snapshot",{"subject_id":plan["subject_id"]})
        grants=self.store.admin("list_agents",{})["grants"]
        installation = plan.get("installation_id")
        if plan["transport"]=="stdio":
            instances = {g["instance_id"] for g in grants if installation and g.get("installation_id")==installation}
            identity = installation
        else:
            instances = {plan["instance_id"]}
            identity = next((g["grant_id"] for g in grants if g["instance_id"] in instances),None)
        with self.lock:
            observed = self.discoveries.get(identity)
        report=next((ev for ev in state["events"] if ev["instance_id"] in instances
                     and ev["type"]=="report_state" and ev["source"]=="agent_direct"),None)
        return {"probe":plan.get("probe"),"host_discovery":observed,
                "report":{"event_id":report["event_id"],"at":report["created_at"],"model_version":report.get("model_version")} if report else None}

    def preview(self,owner,host,transport,iid,sid):
        if not isinstance(host,str) or host not in ADAPTERS or transport not in ("stdio","http") or (host!="other" and transport!="stdio"):
            raise AccessError(400,"INVALID_HOST","请选择支持的宿主和连接方式。")
        if not isinstance(sid,str) or not sid:
            raise AccessError(400,"SUBJECT_REQUIRED","请选择要授权的主体。")
        state=self.store.admin("snapshot",{"subject_id":sid})
        if transport=="http" and not any(i["instance_id"]==iid for i in state["instances"]):
            raise AccessError(400,"INVALID_INSTANCE","所选分身不属于当前主体。")
        path,install,ambiguous=self.targets.get(host,(None,None,False))
        manual=ADAPTERS[host].manual
        raw=None; reason=None; action=None
        installation = None
        bound_config = False
        if path:
            try:
                if ambiguous:
                    raise ValueError("检测到多个 Claude 配置，请使用 Claude Desktop 的“编辑配置”确认真实位置。")
                raw=safe_file(path)
                if raw:
                    existing=parse_config(host,raw).get(ADAPTERS[host].servers_key,{}).get(NAME,{})
                    bound_config=isinstance(existing,dict) and isinstance(existing.get("env"),dict) and "SILICON_CODEX_PROFILE" in existing["env"]
                    current=existing.get("env",{}).get("SILICON_INSTALLATION_FILE") if isinstance(existing,dict) and isinstance(existing.get("env",{}),dict) else None
                    for row in self.store.admin("list_installations",{})["installations"]:
                        owned_path=self.store.files.home/"host-grants"/(row["installation_id"]+".token")
                        if row["subject_id"]==sid and row["host"]==host and row["active"] and str(owned_path)==current:
                            installation=row["installation_id"]
                            break
                _,action=merged(host,raw,self.entry(transport,MASK,host))
            except (OSError,ValueError) as exc:
                reason=str(exc) if isinstance(exc,ValueError) else "无法读取目标配置，请检查文件权限。"
        else:
            reason="此宿主由你选择配置位置，可复制下方条目手动接入。"
        profile = path.parent if host == "codex" and path and transport == "stdio" else None
        account = account_binding(profile) if profile else None
        if bound_config and not account:
            reason="此账号配置需要原 Codex 登录。请登录后重新预览。"
        if account:
            for row in self.store.admin("list_installations",{})["installations"]:
                if row["account_binding"] == account and (row["subject_id"] != sid or not row["active"]):
                    reason="此账号已绑定其他主体或已撤销。请在原主体中管理或恢复授权。"
        skill_target = (self.user_home / ".agents" / "skills" / "silicon-life-state" / "SKILL.md") if profile else None
        if host=="cursor" and path and transport=="stdio":
            skill_target=path.parent/"skills"/"silicon-life-state"/"SKILL.md"
        pid=secrets.token_urlsafe(24)
        plan={"legacy_id":installation,"account":account,"profile":profile,"skill_target":skill_target,"owner":hashlib.sha256(owner.encode()).digest(),"instance_id":iid,"subject_id":sid,
              "host":host,"transport":transport,"installation_id":installation,"path":path,"digest":fingerprint(raw),"reason":reason,
              "expiry":time.monotonic()+900,"key":"host-wizard-"+pid}
        self.plans[pid]=plan
        while len(self.plans)>100:
            self.plans.popitem(last=False)
        return {"scope":"codex_account" if account else ("personal_profile" if transport=="stdio" else "instance"),
                "skill_target":str(skill_target) if skill_target else None,"plan_id":pid,"host":host,"os":sys.platform,"target":str(path) if path else None,
                "installation":str(install) if install else None,"existing_file":raw is not None,
                "can_write":bool(path and not reason),"action":action,"reason":reason,"manual":manual,
                "preview":snippet(host,self.entry(transport,MASK,host)),"status":self.status(plan)}

    def dispatch(self,owner,action,body):
        allowed={"host","transport","instance_id","subject_id"} if action=="preview" else {"plan_id","confirm"}
        if set(body)-allowed-{"idempotency_key"}:
            raise AccessError(400,"INVALID_INPUT","向导参数无效。")
        if action=="preview":
            return self.preview(owner,body.get("host"),body.get("transport","stdio"),body.get("instance_id"),body.get("subject_id"))
        plan_id=body.get("plan_id")
        plan=self.plans.get(plan_id) if isinstance(plan_id,str) else None
        if not plan or plan["expiry"]<time.monotonic() or plan["owner"]!=hashlib.sha256(owner.encode()).digest():
            raise AccessError(409,"PLAN_EXPIRED","预览已过期。请重新检查配置。")
        if action=="status":
            return self.status(plan)
        if action not in ("probe","apply","copy") or body.get("confirm") is not True:
            raise AccessError(400,"CONFIRM_REQUIRED","请确认本次向导操作。")
        if action=="apply" and (not plan["path"] or plan["reason"]):
            raise AccessError(409,"MANUAL_REQUIRED",plan["reason"] or "请使用手动配置。")
        if action=="apply":
            try:
                current_digest=fingerprint(safe_file(plan["path"]))
                if current_digest!=plan["digest"] and current_digest!=plan.get("installed",object()):
                    raise AccessError(409,"CONFIG_CHANGED","文件已改变。请重新检查配置。")
            except (OSError,ValueError) as exc:
                raise AccessError(409,"CONFIG_WRITE_FAILED","无法安全读取目标文件。请重新检查配置或手动合并。") from exc
        profile=plan["profile"]
        account=plan["account"]
        if profile and account_binding(profile)!=account:
            raise AccessError(409,"ACCOUNT_CHANGED","登录账号已改变。请重新预览。")
        if plan["reason"] and plan["reason"].startswith("此账号"):
            raise AccessError(409,"ACCOUNT_ALREADY_BOUND",plan["reason"])
        if plan["transport"]=="stdio":
            if account or not plan.get("installation_id"):
                params={"subject_id":plan["subject_id"],"host":plan["host"],"idempotency_key":plan["key"]}
                if account:
                    params["account_binding"]=account
                    if plan.get("legacy_id"):
                        params["previous_installation_id"]=plan["legacy_id"]
                grant=self.store.admin("issue_installation",params)
                plan["installation_id"]=grant["installation_id"]
            credential=self.store.host_grant_file(plan["installation_id"])
        else:
            grant=self.store.admin("connection_grant",{"instance_id":plan["instance_id"],"idempotency_key":plan["key"]})
            credential=grant["token"]
        entry=self.entry(plan["transport"],credential,plan["host"])
        if account:
            entry["env"].pop("SILICON_INSTALLATION_FILE")
            entry["env"].update(SILICON_CODEX_PROFILE=str(profile),SILICON_ACCOUNT_GRANTS=str(credential.parent))
        elif profile:
            entry["env"]["SILICON_DEDICATED_PROFILE"]=str(profile)
        if action=="copy":
            return {"config":snippet(plan["host"],entry)}
        if action=="apply":
            try:
                if plan["skill_target"]:
                    dest=plan["skill_target"]
                    old=safe_file(dest)
                    skill=(ROOT/"packages/agent-skill/silicon-life-state/SKILL.md").read_bytes()
                    atomic_install(dest,fingerprint(old),skill)
                raw=safe_file(plan["path"])
                if plan.get("installed") and fingerprint(raw)==plan["installed"]:
                    return {"saved":True,"backup":plan.get("backup"),"target":str(plan["path"])}
                if fingerprint(raw)!=plan["digest"]:
                    raise AccessError(409,"CONFIG_CHANGED","文件已改变。请重新检查配置。")
                new,_=merged(plan["host"],raw,entry)
                backup=atomic_install(plan["path"],plan["digest"],new)
            except (ValueError,OSError) as exc:
                reason=str(exc) if isinstance(exc,ValueError) else "写入失败，请检查文件权限或复制配置手动安装。"
                raise AccessError(409,"CONFIG_WRITE_FAILED",reason) from exc
            plan.update(installed=fingerprint(new),backup=backup)
            return {"saved":True,"target":str(plan["path"]),"backup":backup}
        self.probe(plan,entry)
        return self.status(plan)

    def probe(self,plan,entry):
        # Commands and URLs are always generated locally. Never execute an existing config,
        # a browser-provided executable or another user's MCP entry.
        if plan.get("installed"):
            if fingerprint(safe_file(plan["path"]))!=plan["installed"]:
                raise AccessError(409,"CONFIG_CHANGED","目标文件已有变化。请重新检查当前配置。")
        meta={PREFIX+"protocolVersion":VERSION,PREFIX+"clientCapabilities":{},
              PREFIX+"clientInfo":{"name":PROBE,"version":"1.0.5"}}
        req={"jsonrpc":"2.0","id":1,"method":"tools/list","params":{"_meta":meta}}
        try:
            if plan["transport"]=="stdio":
                env={k:v for k,v in os.environ.items() if k in ("SystemRoot","SYSTEMROOT","WINDIR","TEMP","TMP","LANG","LC_ALL")}
                env.update(entry["env"])
                run=subprocess.run([entry["command"],*entry["args"]],input=json.dumps(req).encode()+b"\n",
                                   env=env,capture_output=True,timeout=12,shell=False)
                if run.returncode:
                    raise ValueError("stdio 进程退出，请检查当前 Python 和桥接程序。")
                result=json.loads(run.stdout)
            else:
                u=urlsplit(self.url)
                conn=http.client.HTTPConnection("127.0.0.1",u.port,timeout=8)
                try:
                    conn.request("POST","/mcp",json.dumps(req),{**entry["headers"],"Content-Type":"application/json",
                                 "Accept":"application/json, text/event-stream","MCP-Protocol-Version":VERSION,"Mcp-Method":"tools/list"})
                    res=conn.getresponse()
                    if res.status!=200:
                        raise ValueError("HTTP 鉴权或请求失败，状态码 "+str(res.status)+"。")
                    result=json.loads(res.read())
                finally:
                    conn.close()
            names=[r["name"] for r in result.get("result",{}).get("tools",[])]
            if not {"report_state","express_boundary","get_own_state"}.issubset(names):
                raise ValueError("服务未返回必需工具。请检查本机服务、凭据和版本。")
        except (subprocess.TimeoutExpired,OSError,http.client.HTTPException,ValueError,KeyError,TypeError) as exc:
            plan.pop("probe",None)
            message=str(exc) if type(exc) is ValueError else "连接程序未返回有效 MCP 回执。请检查服务、路径及授权。"
            raise AccessError(422,"PROBE_FAILED",message) from exc
        plan["probe"]={"at":now(),"tools":names,"transport":plan["transport"]}
