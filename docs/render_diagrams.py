from PIL import Image, ImageDraw, ImageFont
F="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"; FB="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
font=ImageFont.truetype(F,14); fb=ImageFont.truetype(FB,16); fs=ImageFont.truetype(F,12)
LANES=[("Пользователь",0),("Сервис",1),("Данные",2)]; LH=190; PX=40; LX=PX+40; W=1700
def ly(l,h): return 30+l*LH+(LH-h)//2
E={}  # id:(type,name,x,y,w,h)
def add(i,t,n,lane,x,w=150,h=80):
    if t!="task": w=h=(36 if t.endswith("Event") else 50)
    E[i]=(t,n,x,ly(lane,h),w,h)
add("start","startEvent","Нужен товар",0,160)
add("t_input","task","Ввести описание в свободной форме",0,240)
add("t_parse","task","Разобрать текст (parser)",1,200)
add("t_unify","task","Унифицировать названия и единицы (unifier)",1,400)
add("t_index","task","Поиск в индексе КТРУ и портала (SQLite)",2,600)
add("t_match","task","Сузить коды и проверить значения (matcher, engine)",1,800)
add("t_resp","task","Сформировать ответ: подсказки, воронка, кандидаты",1,1000)
add("t_review","task","Просмотреть таблицу, подсказки и воронку",0,1000)
add("gw","exclusiveGateway","Всё верно?",0,1220)
add("t_edit","task","Отредактировать значение или применить подсказку",0,1300)
add("end","endEvent","Характеристики заполнены, код КТРУ выбран",0,1500)
# shift t_edit to be under? keep in user lane but place above loop: put at x 1180 lower? simple: same lane
E["t_edit"]=("task",E["t_edit"][1],1330,30+100,150,62)
E["gw"]=("exclusiveGateway","Всё верно?",1240,30+40,50,50)
E["t_review"]=("task",E["t_review"][1],1030,30+25,150,80)
E["end"]=("endEvent",E["end"][1],1600,30+47,36,36)
FL=[("f1","start","t_input",""),("f2","t_input","t_parse",""),("f3","t_parse","t_unify",""),("f4","t_unify","t_index",""),
("f5","t_index","t_match",""),("f6","t_match","t_resp",""),("f7","t_resp","t_review",""),("f8","t_review","gw",""),
("f9","gw","end","да"),("f10","gw","t_edit","нет"),("f11","t_edit","t_unify","пересчёт ≈600 мс")]
def c(i):t,n,x,y,w,h=E[i];return x+w/2,y+h/2
def pts(a,b,fid):
    _,_,xa,ya,wa,ha=E[a]; _,_,xb,yb,wb,hb=E[b]; ax,ay=c(a); bx,by=c(b)
    if fid=="f10": return [(ax,ya+ha),(ax,by),(xb,by)]
    if fid=="f11": return [(ax,ya+ha),(ax,30+178),(bx,30+178),(bx,yb)]
    if fid=="f4": return [(ax,ya+ha),(ax,by),(xb,by)]
    if fid=="f5": return [(xa+wa,ay),(bx,ay),(bx,yb+hb)]
    ta,_,xa,ya,wa,ha=E[a]; tb,_,xb,yb,wb,hb=E[b]
    ax,ay=c(a); bx,by=c(b)
    if fid=="f11": return [(xa,ay),(ax-560-150,ay),(ax-560-150, yb),(bx,yb)] if False else [(xa,ay),(bx,ay),(bx,yb)]
    if fid=="f10": return [(ax,ya+ha),(ax,yb+hb/2),(xb+wb+0,yb+hb/2)] if False else [(ax,ya+ha),(ax,yb)]
    if abs(ay-by)<1: return [(xa+wa,ay),(xb,by)]
    if fid in("f2","f4","f5","f7"):
        sy=(ya+ha) if by>ay else ya; ey=yb if by>ay else yb+hb
        if fid=="f7": return [(ax,ya),(ax,by),(xb+wb,by)] if False else [(ax,ya),(ax,yb+hb)]
        return [(ax,sy),(ax,(ay+by)/2),(bx,(ay+by)/2),(bx,ey)]
    return [(xa+wa,ay),(bx,ay),(bx,yb)]
# t_review directly above t_resp: make x equal
E["t_review"]=("task",E["t_review"][1],1000,30+25,150,80)
# ---- XML
def esc(s):return s.replace("&","&amp;").replace('"',"&quot;").replace("<","&lt;")
lane_of={"start":0,"t_input":0,"t_review":0,"gw":0,"t_edit":0,"end":0,"t_parse":1,"t_unify":1,"t_match":1,"t_resp":1,"t_index":2}
x=['<?xml version="1.0" encoding="UTF-8"?>','<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Defs" targetNamespace="http://tenderhack.local/bpmn">',
'<bpmn:collaboration id="Collab"><bpmn:participant id="Pool" name="Заполнение характеристик СТЕ" processRef="Process"/></bpmn:collaboration>',
'<bpmn:process id="Process" isExecutable="false"><bpmn:laneSet id="LaneSet">']
for n,l in LANES:
    x.append(f'<bpmn:lane id="Lane{l}" name="{n}">'+"".join(f"<bpmn:flowNodeRef>{k}</bpmn:flowNodeRef>" for k,v in lane_of.items() if v==l)+"</bpmn:lane>")
x.append("</bpmn:laneSet>")
for k,(t,n,*_ ) in E.items():
    inc="".join(f"<bpmn:incoming>{f}</bpmn:incoming>" for f,a,b,_ in FL if b==k)+"".join(f"<bpmn:outgoing>{f}</bpmn:outgoing>" for f,a,b,_ in FL if a==k)
    x.append(f'<bpmn:{t} id="{k}" name="{esc(n)}">{inc}</bpmn:{t}>')
for f,a,b,n in FL: x.append(f'<bpmn:sequenceFlow id="{f}" name="{esc(n)}" sourceRef="{a}" targetRef="{b}"/>')
x.append('</bpmn:process><bpmndi:BPMNDiagram id="Diagram"><bpmndi:BPMNPlane id="Plane" bpmnElement="Collab">')
x.append(f'<bpmndi:BPMNShape id="Pool_di" bpmnElement="Pool" isHorizontal="true"><dc:Bounds x="{PX}" y="30" width="{W-PX}" height="{3*LH}"/></bpmndi:BPMNShape>')
for n,l in LANES: x.append(f'<bpmndi:BPMNShape id="Lane{l}_di" bpmnElement="Lane{l}" isHorizontal="true"><dc:Bounds x="{LX}" y="{30+l*LH}" width="{W-LX}" height="{LH}"/></bpmndi:BPMNShape>')
for k,(t,n,X,Y,w,h) in E.items(): x.append(f'<bpmndi:BPMNShape id="{k}_di" bpmnElement="{k}"><dc:Bounds x="{X}" y="{Y}" width="{w}" height="{h}"/></bpmndi:BPMNShape>')
for f,a,b,n in FL: x.append(f'<bpmndi:BPMNEdge id="{f}_di" bpmnElement="{f}">'+"".join(f'<di:waypoint x="{int(p)}" y="{int(q)}"/>' for p,q in pts(a,b,f))+"</bpmndi:BPMNEdge>")
x.append("</bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn:definitions>")
open("process.bpmn","w",encoding="utf-8").write("\n".join(x))
# ---- PNG
def wrap(d,t,f,mw):
    out=[];cur=""
    for wd in t.split():
        s=(cur+" "+wd).strip()
        if d.textlength(s,font=f)<=mw: cur=s
        else: out.append(cur);cur=wd
    out.append(cur);return out
def arrow(d,P,col="#333"):
    d.line(P,fill=col,width=2);(x1,y1),(x2,y2)=P[-2],P[-1]
    import math;a=math.atan2(y2-y1,x2-x1)
    d.polygon([(x2,y2),(x2-10*math.cos(a-0.4),y2-10*math.sin(a-0.4)),(x2-10*math.cos(a+0.4),y2-10*math.sin(a+0.4))],fill=col)
H=30+3*LH+30; im=Image.new("RGB",(W+20,H),"white"); d=ImageDraw.Draw(im)
d.rectangle([PX,30,W,30+3*LH],outline="#264b82",width=2); d.line([LX,30,LX,30+3*LH],fill="#264b82",width=2)
tl=Image.new("RGB",(3*LH,40),"white");td=ImageDraw.Draw(tl);t="Заполнение характеристик СТЕ";td.text(((3*LH-td.textlength(t,font=fb))/2,10),t,font=fb,fill="#264b82")
im.paste(tl.rotate(90,expand=True),(PX,30))
cols=["#f5f9ff","#ffffff","#f7f7f7"]
for n,l in LANES:
    y0=30+l*LH;d.rectangle([LX,y0,W,y0+LH],outline="#264b82",fill=cols[l],width=1)
    lb=Image.new("RGB",(LH,30),cols[l]);ld=ImageDraw.Draw(lb);ld.text(((LH-ld.textlength(n,font=fb))/2,6),n,font=fb,fill="#264b82")
    im.paste(lb.rotate(90,expand=True),(LX+2,y0))
for f,a,b,n in FL:
    P=pts(a,b,f);arrow(d,P)
    if n:
        j=1 if f=='f11' else 0; mx=(P[j][0]+P[j+1][0])/2; my=(P[j][1]+P[j+1][1])/2
        if f=='f10': mx,my=P[1][0]+10,P[1][1]-2
        d.text((mx+4,my-18),n,font=fs,fill="#c96a00")
for k,(t,n,X,Y,w,h) in E.items():
    if t=="task":
        d.rounded_rectangle([X,Y,X+w,Y+h],12,fill="#e8f1fc",outline="#1d6fd6",width=2)
        L=wrap(d,n,font,w-12);ty=Y+(h-len(L)*17)/2
        for s in L: d.text((X+(w-d.textlength(s,font=font))/2,ty),s,font=font,fill="#1f2a37");ty+=17
    else:
        if t=="exclusiveGateway":
            d.polygon([(X+w/2,Y),(X+w,Y+h/2),(X+w/2,Y+h),(X,Y+h/2)],fill="#fff3e2",outline="#c96a00");d.text((X+18,Y+14),"×",font=fb,fill="#c96a00")
        else:
            d.ellipse([X,Y,X+w,Y+h],fill="white",outline="#1e8e4f" if t=="startEvent" else "#d0342c",width=2 if t=="startEvent" else 4)
        L=wrap(d,n,fs,140);ty=Y+h+4
        for s in L: d.text((X+w/2-d.textlength(s,font=fs)/2,ty),s,font=fs,fill="#1f2a37");ty+=14
im.save("process.png")
# ---- component diagram
im=Image.new("RGB",(1300,640),"white");d=ImageDraw.Draw(im)
def box(x,y,w,h,title,sub,fill="#e8f1fc",ol="#1d6fd6"):
    d.rounded_rectangle([x,y,x+w,y+h],10,fill=fill,outline=ol,width=2)
    d.text((x+w/2-d.textlength(title,font=fb)/2,y+12),title,font=fb,fill="#1f2a37");ty=y+38
    for s in wrap(d,sub,fs,w-16): d.text((x+w/2-d.textlength(s,font=fs)/2,ty),s,font=fs,fill="#555");ty+=15
d.text((30,20),"Схема компонентов",font=ImageFont.truetype(FB,22),fill="#264b82")
box(40,90,220,110,"Веб-интерфейс","HTML/JS: таблица характеристик, подсказки, воронка, бейджи источников")
box(340,90,220,110,"FastAPI","app/main.py: POST /api/analyze, GET /api/demo-cases, статика",fill="#e6f5ec",ol="#1e8e4f")
mods=[("parser","Текст → пары характеристика/значение/единица"),("unifier","Синонимы, нормализация названий и единиц"),("matcher","Поиск кандидатов КТРУ по названию и ОКПД2"),("engine","Сужение кодов, проверка значений, подсказки")]
for i,(t,s) in enumerate(mods): box(640+(i%2)*300,60+(i//2)*140,260,110,t,s)
box(790,360,300,100,"SQLite-индекс","data/processed: коды КТРУ, характеристики, допустимые значения",fill="#f7f7f7",ol="#666")
box(340,360,300,100,"scripts/build_index.py","Офлайн-сборка индекса",fill="#fff3e2",ol="#c96a00")
box(40,330,220,70,"XML КТРУ","Справочник КТРУ",fill="#fff",ol="#666");box(40,430,220,70,"XLSX портала","Характеристики СТЕ портала",fill="#fff",ol="#666")
arrow(d,[(260,145),(340,145)]);d.text((268,120),"JSON",font=fs,fill="#555")
arrow(d,[(560,145),(640,115)]);arrow(d,[(560,145),(640,255)])
arrow(d,[(900,115),(940,115)]);arrow(d,[(770,170),(770,200)]);arrow(d,[(900,255),(940,255)])
arrow(d,[(1070,310),(1000,360)]);arrow(d,[(770,310),(880,360)])
arrow(d,[(260,365),(340,400)]);arrow(d,[(260,465),(340,420)]);arrow(d,[(640,410),(790,410)])
d.text((40,560),"Конвейер: parser → unifier → matcher → engine; индекс собирается заранее, запрос обслуживается локально без внешних сервисов.",font=font,fill="#333")
im.save("components.png")
