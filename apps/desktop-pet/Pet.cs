using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Linq;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

namespace SiliconLife {
public class Identity { public string id, name; }
public class Record {
    public string event_id, revision_id, instance_id, type, source, text, stage;
    public long seq;
    public Dictionary<string,object> payload;
    public string Label {
        get {
            if (type == "express_boundary") return "AI 请求 · 表达边界";
            if (type == "request_adjustment") return "AI 请求 · 调整请求";
            if (source == "agent_visible_text") return "网页观察";
            if (source == "model_estimated") return "模型推算";
            return source == "agent_direct" ? "AI 自主报告" : source;
        }
    }
}
public class Feed {
    public string subject_id;
    public Identity[] subjects, instances;
    public Record[] states, requests, observations, shared;
}
class LocalService {
    public int Port;
    public string Token;
    class LocalRequest : WebClient {
        protected override WebRequest GetWebRequest(Uri uri) {
            var request = (HttpWebRequest)base.GetWebRequest(uri);
            request.AllowAutoRedirect = false;
            request.Timeout = 5000;
            return request;
        }
    }
    public T Call<T>(string route, object body) {
        var json = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
        using (var client = new LocalRequest()) {
            client.Encoding = Encoding.UTF8;
            client.Proxy = null;
            client.Headers["Content-Type"] = "application/json";
            if (Token != "") client.Headers["Authorization"] = "Bearer " + Token;
            string url = "http://127.0.0.1:" + Port + "/api/pet/" + route;
            var response = body == null ? client.DownloadString(url) : client.UploadString(url, "POST", json.Serialize(body));
            return json.Deserialize<T>(response);
        }
    }
}
class Preferences {
    const string Path = @"Software\SiliconLifeState\DesktopPet";
    public static string Read(string key, string fallback) {
        return Convert.ToString(Registry.GetValue(@"HKEY_CURRENT_USER\" + Path, key, fallback) ?? fallback);
    }
    public static void Save(string key, object value) { using (var r = Registry.CurrentUser.CreateSubKey(Path)) r.SetValue(key,value); }
    public static string Token() {
        try { return Encoding.UTF8.GetString(ProtectedData.Unprotect(Convert.FromBase64String(Read("Pair","")),null,DataProtectionScope.CurrentUser)); }
        catch (CryptographicException) { return ""; } catch (FormatException) { return ""; }
    }
    public static void Pair(LocalService service,string code) {
        var response = service.Call<Dictionary<string,object>>("pair",new {code=code});
        var token = (string)response["token"];
        Save("Pair",Convert.ToBase64String(ProtectedData.Protect(Encoding.UTF8.GetBytes(token),null,DataProtectionScope.CurrentUser)));
        Save("Port",service.Port); service.Token = token;
    }
}
class Pet : Form {
    readonly NotifyIcon tray = new NotifyIcon();
    readonly ContextMenuStrip menu = new ContextMenuStrip();
    readonly Timer poll = new Timer {Interval=4000};
    readonly LocalService service;
    Feed data;
    string subject = Preferences.Read("Subject",""), instance = Preferences.Read("Instance","");
    string status = "等待配对", caption = "右击连接本地服务";
    bool cream = Preferences.Read("Theme","night") == "cream", busy, dragging, moved;
    int scale;
    Point dragStart, dragOrigin;
    Form details;
    TextBox original;
    HashSet<string> seen;
    string detailText = "";
    public Pet(LocalService api) {
        service = api;
        Text = "Silicon Life State Desktop Pet";
        FormBorderStyle = FormBorderStyle.None;
        BackColor = TransparencyKey = Color.Magenta;
        ShowInTaskbar = false; DoubleBuffered = true;
        TopMost = Preferences.Read("Top","1") == "1";
        StartPosition = FormStartPosition.Manual;
        var area = Screen.PrimaryScreen.WorkingArea;
        int x, y;
        if (!int.TryParse(Preferences.Read("X",""),out x) || !int.TryParse(Preferences.Read("Y",""),out y) ||
            !Screen.AllScreens.Any(s => s.WorkingArea.Contains(new Point(x+40,y+40)))) { x=area.Right-240; y=area.Bottom-190; }
        Location = new Point(x,y);
        if (!int.TryParse(Preferences.Read("Scale","100"),out scale)) scale=100;
        ResizePet(scale);
        tray.Icon = SystemIcons.Information; tray.Text = "硅基生命状态 · 桌宠"; tray.Visible = true;
        ContextMenuStrip = tray.ContextMenuStrip = menu;
        menu.Opening += (s,e) => BuildMenu();
        tray.DoubleClick += (s,e) => { Show(); Activate(); };
        tray.BalloonTipClicked += (s,e) => ShowDetails();
        MouseDown += (s,e) => { if(e.Button==MouseButtons.Left) {dragging=true;moved=false;Capture=true;dragStart=PointToScreen(e.Location);dragOrigin=Location;} };
        MouseMove += (s,e) => { if(dragging) { var d=PointToScreen(e.Location); var dx=d.X-dragStart.X;var dy=d.Y-dragStart.Y;
            if(moved || Math.Abs(dx)+Math.Abs(dy)>3) { moved=true; Location=new Point(dragOrigin.X+dx,dragOrigin.Y+dy); } } };
        MouseUp += (s,e) => { if(dragging) { dragging=false;Capture=false;if(moved){Preferences.Save("X",Left);Preferences.Save("Y",Top);} } };
        MouseDoubleClick += (s,e) => {if(e.Button==MouseButtons.Left) ShowDetails();};
        KeyDown += (s,e) => { if(e.KeyCode==Keys.Escape) Hide(); if(e.KeyCode==Keys.Enter) ShowDetails(); };
        poll.Tick += async (s,e) => await RefreshFeed();
        Shown += async (s,e) => {poll.Start();await RefreshFeed();};
        FormClosed += (s,e) => {poll.Stop();tray.Visible=false;tray.Dispose();if(details!=null)details.Close();};
        BuildMenu();
    }
    void ResizePet(int size) { scale=Math.Max(65,Math.Min(180,size)); Size=new Size(210*scale/100,142*scale/100); Invalidate(); }
    protected override void OnPaint(PaintEventArgs e) {
        base.OnPaint(e);
        var g=e.Graphics; g.ScaleTransform(scale/100f,scale/100f);g.SmoothingMode=SmoothingMode.AntiAlias;
        Color ink=cream?Color.FromArgb(67,55,49):Color.FromArgb(248,238,255);
        Color dark=cream?Color.FromArgb(171,145,123):Color.FromArgb(75,59,110);
        Color light=cream?Color.FromArgb(255,246,216):Color.FromArgb(210,194,251);
        Point[] shape={new Point(105,6),new Point(139,42),new Point(125,72),new Point(101,86),new Point(70,54),new Point(78,26)};
        using(var fill=new LinearGradientBrush(new Rectangle(69,5,71,82),light,dark,55f))
        using(var lines=new Pen(light,1.5f)) {
            g.FillPolygon(fill,shape);g.DrawPolygon(lines,shape);
            g.DrawLines(lines,new Point[]{shape[0],new Point(98,46),shape[3]});g.DrawLine(lines,shape[4],new Point(98,46));g.DrawLine(lines,new Point(98,46),shape[1]);
            g.DrawArc(lines,56,42,102,31,10,154);
        }
        using(var bg=new SolidBrush(cream?Color.FromArgb(249,242,226):Color.FromArgb(47,38,63)))
        using(var fg=new SolidBrush(ink))
        using(var title=new Font("Microsoft YaHei UI",9,FontStyle.Bold))
        using(var font=new Font("Microsoft YaHei UI",8))
        using(var format=new StringFormat {Alignment=StringAlignment.Center,LineAlignment=StringAlignment.Center,Trimming=StringTrimming.EllipsisCharacter,FormatFlags=StringFormatFlags.NoWrap}) {
            g.FillRectangle(bg,4,89,202,47);
            g.DrawString(status,title,fg,new RectangleF(9,91,192,20),format);
            g.DrawString(caption,font,fg,new RectangleF(9,112,192,19),format);
        }
    }
    void Add(ToolStripItemCollection items,string text,Action action,bool check=false) {
        var item = new ToolStripMenuItem(text);item.Checked=check;item.Click+=(s,e)=>action();items.Add(item);
    }
    void SelectScope(string sid,string iid) {
        subject=sid;instance=iid;Preferences.Save("Subject",sid);Preferences.Save("Instance",iid);
        seen=null;ClearView("正在读取");RefreshSoon();
    }
    async void RefreshSoon() {await RefreshFeed();}
    void BuildMenu() {
        menu.Items.Clear();
        Add(menu.Items,"查看原始记录",ShowDetails);
        var scope=new ToolStripMenuItem("显示主体或分身");menu.Items.Add(scope);
        if(data!=null) {
            foreach(var row in data.subjects){var id=row.id;Add(scope.DropDownItems,"主体 · "+row.name,()=>SelectScope(id,""),id==subject && instance=="");}
            foreach(var row in data.instances){var id=row.id;Add(scope.DropDownItems,row.name,()=>SelectScope(subject,id),id==instance);}
        }
        Add(menu.Items,"连接本地服务",Connect);
        Add(menu.Items,"奶油白 / 星夜紫",()=>{cream=!cream;Preferences.Save("Theme",cream?"cream":"night");Invalidate();},cream);
        Add(menu.Items,"放大",()=>{ResizePet(scale+15);Preferences.Save("Scale",scale);});
        Add(menu.Items,"缩小",()=>{ResizePet(scale-15);Preferences.Save("Scale",scale);});
        Add(menu.Items,"始终置顶",()=>{TopMost=!TopMost;Preferences.Save("Top",TopMost?"1":"0");},TopMost);
        bool alerts=Preferences.Read("Alerts","0")=="1";
        Add(menu.Items,"新请求通知",()=>{Preferences.Save("Alerts",alerts?"0":"1");seen=null;},alerts);
        const string run=@"Software\Microsoft\Windows\CurrentVersion\Run";
        bool startup=Registry.GetValue(@"HKEY_CURRENT_USER\"+run,"SiliconLifeStatePet",null)!=null;
        Add(menu.Items,"登录 Windows 时启动",()=>{
            using(var r=Registry.CurrentUser.CreateSubKey(run)) {
                if(startup)r.DeleteValue("SiliconLifeStatePet",false);else r.SetValue("SiliconLifeStatePet","\""+Application.ExecutablePath+"\"");
            }
        },startup);
        Add(menu.Items,Visible?"隐藏到托盘":"显示桌宠",()=>{if(Visible)Hide();else {Show();Activate();}});
        Add(menu.Items,"退出桌宠",Close);
    }
    void Connect() {
        using(var form=new Form {Text="连接本地服务",Width=410,Height=215,StartPosition=FormStartPosition.CenterScreen,TopMost=true}) {
            var label=new Label {Text="从仪表盘「桌宠设置」获取桌宠只读配对码",Left=14,Top=14,AutoSize=true};
            var code=new TextBox {Left=14,Top=40,Width=360,UseSystemPasswordChar=true};
            var port=new NumericUpDown {Left=106,Top=76,Minimum=1,Maximum=65535,Value=service.Port};
            var ok=new Button {Text="配对",Left=275,Top=114,DialogResult=DialogResult.OK};
            form.Controls.AddRange(new Control[]{label,code,new Label{Text="本机端口",Left=14,Top=80},port,ok});
            form.AcceptButton=ok;
            if(form.ShowDialog()!=DialogResult.OK)return;
            try {
                var target=new LocalService {Port=(int)port.Value,Token=""};Preferences.Pair(target,code.Text.Trim());
                service.Port=target.Port;service.Token=target.Token;SelectScope("","");
            } catch(WebException){MessageBox.Show("配对失败。请检查本地服务、端口和配对码有效期。");}
        }
    }
    void ShowDetails() {
        if(details==null || details.IsDisposed){
            details=new Form {Text="硅基生命状态 · 原始记录",Width=580,Height=530,StartPosition=FormStartPosition.CenterScreen};
            original=new TextBox {Multiline=true,ReadOnly=true,Dock=DockStyle.Fill,ScrollBars=ScrollBars.Vertical,Font=new Font("Microsoft YaHei UI",10)};
            details.Controls.Add(original);
        }
        original.Text=detailText;details.Show();details.Activate();
    }
    void ClearView(string message) {
        data=null;status=message;caption="右击查看连接设置";detailText=message;
        if(original!=null && !original.IsDisposed)original.Text=detailText;
        Invalidate();
    }
    string Describe(Record r) {
        var author=data.instances.FirstOrDefault(i=>i.id==r.instance_id);
        return (author==null?r.instance_id:author.name)+" · "+r.Label+"\r\n"+
            (String.IsNullOrEmpty(r.text)?new JavaScriptSerializer().Serialize(r.payload):r.text)+"\r\n"+
            r.event_id+(String.IsNullOrEmpty(r.revision_id)?"":" · 修订 "+r.revision_id)+(String.IsNullOrEmpty(r.stage)?"":" · "+r.stage);
    }
    async Task RefreshFeed() {
        if(busy || IsDisposed)return;
        if(String.IsNullOrEmpty(service.Token)) {ClearView("等待桌宠配对");return;}
        busy=true;
        string sid=subject,iid=instance,credential=service.Token;
        var api=new LocalService {Port=service.Port,Token=credential};
        try {
            var fresh=await Task.Run(()=>api.Call<Feed>("feed?subject_id="+Uri.EscapeDataString(sid)+"&instance_id="+Uri.EscapeDataString(iid),null));
            if(IsDisposed || sid!=subject || iid!=instance || credential!=service.Token)return;
            data=fresh;subject=data.subject_id??"";
            if(instance!="" && !data.instances.Any(i=>i.id==instance)){SelectScope(subject,"");return;}
            var selected=data.instances.FirstOrDefault(i=>i.id==instance);
            var owner=data.subjects.FirstOrDefault(s=>s.id==subject);
            string name=selected!=null?selected.name:owner!=null?owner.name:"尚无主体";
            var latest=data.states.Concat(data.requests).Concat(data.observations).OrderByDescending(r=>r.seq).FirstOrDefault();
            status=name+" · "+(latest==null?"尚无记录":latest.Label);
            caption=latest==null?"等待已保存的表达":latest.text;
            var lines=new List<string>{name+" · 本地只读连接"};
            foreach(var section in new[]{new {Title="分身自主报告",Rows=data.states},new {Title="表达与请求",Rows=data.requests},new {Title="网页观察与模型推算",Rows=data.observations},new {Title="主体共享历史",Rows=data.shared}}) {
                lines.Add(section.Title);lines.Add(section.Rows.Length==0?"尚无记录":String.Join("\r\n\r\n",section.Rows.Select(Describe)));
            }
            var updated=String.Join("\r\n\r\n",lines);
            if(detailText!=updated){detailText=updated;if(original!=null && !original.IsDisposed)original.Text=updated;}
            if(seen!=null && Preferences.Read("Alerts","0")=="1" && data.requests.Any(r=>!seen.Contains(r.event_id)))
                tray.ShowBalloonTip(3500,"硅基生命状态","分身有新的表达或请求。点击查看原文。",ToolTipIcon.Info);
            seen=new HashSet<string>(data.requests.Select(r=>r.event_id));
            Invalidate();
        } catch(WebException ex) {
            if(IsDisposed || credential!=service.Token || sid!=subject || iid!=instance)return;
            var response=ex.Response as HttpWebResponse;
            if(response!=null && response.StatusCode==HttpStatusCode.NotFound && subject!=""){SelectScope("","");}
            else ClearView(response!=null && response.StatusCode==HttpStatusCode.Unauthorized?"配对已失效":"本地服务未连接");
            if(response!=null)response.Dispose();
        } finally {busy=false;}
    }
}
static class Program {
    [STAThread] static int Main(string[] args) {
        int port;if(!int.TryParse(Preferences.Read("Port","47831"),out port) || port<1 || port>65535)port=47831;
        var service=new LocalService {Port=port,Token=Preferences.Token()};
        if(args.Length==2 && args[0]=="--pair-stdin"){service.Port=int.Parse(args[1]);Preferences.Pair(service,Console.ReadLine());return 0;}
        if(args.Length==1 && args[0]=="--disconnect"){if(service.Token!="")service.Call<object>("disconnect",new{});Preferences.Save("Pair","");return 0;}
        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);Application.Run(new Pet(service));return 0;
    }
}
}
