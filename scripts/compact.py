"""Local connected diagrams; layout never invents scientific nodes or relations."""
import html
import json
import math
from pathlib import Path

COLORS={'construction':'#47678c','dependency':'#7756a6','support':'#247a59','limit':'#b74f3f','indirect':'#788795'}
FILLS={'construction':('#eef3fa','#a6b7ce'),'support':('#eff8f2','#a6c6b4'),
       'limit':('#fcf1ed','#d9aea3'),'indirect':('#f4f5f7','#b9c0c9')}
KINDS={'construction':'构造','dependency':'需求/依赖','support':'支持','limit':'限制','indirect':'间接线索'}

def mermaid(model):
    def esc(text):return html.escape(str(text),quote=True).replace('\n','<br/>')
    ids={};lines=['flowchart LR']
    for i,q in enumerate(model['questions']):
        ids[q['id']]=f'q{i}'
        lines.append(f'    {ids[q["id"]]}["{esc(q["label"]+" "+q["title"])}"]')
    for i,n in enumerate(model['nodes']):
        ids[n['id']]=f'n{i}'
        text=n['label']+' '+n['title']+'\n'+n['detail']+'\n'+'、'.join(n['refs'])
        lines.append(f'    {ids[n["id"]]}["{esc(text)}"]')
        lines.append(f'    {ids[n["question_id"]]} --- {ids[n["id"]]}')
    for e in model['relations']:
        arrow='-->' if e['kind'] in ('construction','dependency') else '-.->'
        lines.append(f'    {ids[e["from"]]} {arrow}|"{esc(KINDS[e["kind"]]+"："+e["text"])}"| {ids[e["to"]]}')
    return '\n'.join(lines)

def node_height(c,n,width):
    return (38+40*len(c.wrap(n['label']+' '+n['title'],width-44,30))
            +34*len(c.wrap(n['detail'],width-44,26))
            +30*len(c.wrap('、'.join(n['refs']),width-44,23))+20)

def node(c,n,box):
    x,y,w,h=box;fill,stroke=FILLS[n['kind']]
    c.rect(x,y,w,h,fill,stroke);at=y+30
    for text in c.wrap(n['label']+' '+n['title'],w-44,30):
        c.text(x+22,at,text,30,align='start');at+=40
    at+=2
    for text in c.wrap(n['detail'],w-44,26):
        c.text(x+22,at,text,26,'#46566c',align='start');at+=34
    at+=6
    for text in c.wrap('、'.join(n['refs']),w-44,23):
        c.text(x+22,at,text,23,'#607084',align='start');at+=30

def intersects(a,b,pad=0):
    x,y,w,h=a;u,v,z,t=b
    return min(x+w,u+z)+pad>max(x,u) and min(y+h,v+t)+pad>max(y,v)

def line_hits_box(points,box,pad=0):
    x,y,w,h=box;x-=pad;y-=pad;w+=2*pad;h+=2*pad
    for a,b in zip(points,points[1:]):
        if a[0]==b[0] and x<a[0]<x+w and min(a[1],b[1])<y+h and max(a[1],b[1])>y:return True
        if a[1]==b[1] and y<a[1]<y+h and min(a[0],b[0])<x+w and max(a[0],b[0])>x:return True
    return False

def label(c,edge,box,lines):
    x,y,w,h=box;c.rect(x,y,w,h,'#ffffff','#ffffff')
    for i,text in enumerate(lines):c.text(x+w/2,y+18+i*30,text,24,COLORS[edge['kind']])

def legend(c,y,width):
    text='蓝实线：构造　紫实线：需求/依赖　绿虚线：支持　红虚线：限制　灰虚线：间接线索'
    for line in c.wrap(text,width-80,24):c.text(width/2,y,line,24,'#52637a');y+=34
    c.text(width/2,y,'分组表示问题归属；箭头仅表示已核关系，依标注范围理解。',23,'#52637a')
    return y+35

def grouped(model,Canvas,font):
    """Question columns, role-neutral ports, and routed/labelled actual edges."""
    qs=model['questions'];ns=model['nodes'];es=model['relations']
    if len(qs)>2 or len(ns)>8 or len(es)>8:raise ValueError('关系规模适合分图')
    qi={q['id']:i for i,q in enumerate(qs)}
    owner={q['id']:q['id'] for q in qs}|{n['id']:n['question_id'] for n in ns}
    same={i:[] for i in range(len(qs))};cross=[]
    for e in es:
        a,b=qi[owner[e['from']]],qi[owner[e['to']]]
        (same[a] if a==b else cross).append(e)
    margin=210+60*max([len(v) for v in same.values()] or [0]);w=500;gap=max(300,90+60*len(cross))
    width=2*margin+len(qs)*w+max(0,len(qs)-1)*gap
    c=Canvas(font,width=width);c.text(width/2,34,'科学问题与关键回答关系',34)
    header_h=max(48+38*len(c.wrap(q['label']+' '+q['title'],w-40,30)) for q in qs)
    boxes={};ends=[]
    for i,q in enumerate(qs):
        x=margin+i*(w+gap);box=(x,80,w,header_h);boxes[q['id']]=box
        c.rect(*box,'#f5f7fa','#a6b7ce')
        for j,text in enumerate(c.wrap(q['label']+' '+q['title'],w-40,30)):c.text(x+20,110+38*j,text,30,align='start')
        y=80+header_h+55
        for n in [n for n in ns if n['question_id']==q['id']]:
            h=node_height(c,n,w);boxes[n['id']]=(x,y,w,h);y+=h+70
        ends.append(y)
    # Ports depend on endpoint identity and column, never on construction/support roles.
    ports={};assign={}
    for e in es:
        a,b=qi[owner[e['from']]],qi[owner[e['to']]]
        sides=('right','left') if a<b else ('left','right') if a>b else (('left','left') if a==0 else ('right','right'))
        for key,side in zip(('from','to'),sides):
            ports.setdefault((e[key],side),[]).append((e['id'],key));assign[(e['id'],key)]=(e[key],side)
    def port(e,key):
        nid,side=assign[(e['id'],key)];x,y,z,h=boxes[nid];peers=ports[(nid,side)]
        k=peers.index((e['id'],key));f=.25+.5*(k+1)/(len(peers)+1)
        return (x if side=='left' else x+z,y+h*f)
    routes=[]
    for e in es:
        a,b=qi[owner[e['from']]],qi[owner[e['to']]];start,end=port(e,'from'),port(e,'to')
        if a!=b:lane=margin+w+gap*(cross.index(e)+1)/(len(cross)+1)
        else:
            k=same[a].index(e);x=boxes[e['from']][0]
            lane=x-150-k*60 if a==0 else x+w+150+k*60
        points=[start,(lane,start[1]),(lane,end[1]),end]
        for nid,box in boxes.items():
            if nid not in (e['from'],e['to']) and line_hits_box(points,box,5):raise ValueError('连线需要局部展开')
        routes.append((e,points))
    # Place each relation label on its route, avoiding nodes, labels and other routes.
    labels=[];bottom=max(ends or [250])+35
    for e,points in routes:
        candidates=[]
        for a,b in zip(points,points[1:]):
            length=abs(b[0]-a[0])+abs(b[1]-a[1])
            if length<70:continue
            horizontal=a[1]==b[1];maxw=min(210,length-24) if horizontal else 150
            lines=c.wrap(e['text'],maxw-12,24);lw=max(c.measure(t,24) for t in lines)+16;lh=30*len(lines)+8
            for f in (.5,.33,.67,.2,.8):
                x=a[0]+(b[0]-a[0])*f;y=a[1]+(b[1]-a[1])*f
                box=(x-lw/2,y-lh/2,lw,lh)
                if box[0]<10 or box[0]+lw>width-10 or box[1]<65 or box[1]+lh>bottom:continue
                if any(intersects(box,v,8) for v in boxes.values()):continue
                if any(intersects(box,v[1],10) for v in labels):continue
                if any(other['id']!=e['id'] and line_hits_box(route,box,4) for other,route in routes):continue
                candidates.append((box,lines))
        if not candidates:raise ValueError('关系标签需要局部展开')
        box,lines=candidates[0];labels.append((e,box,lines))
    for e,points in routes:c.line(points,COLORS[e['kind']],dashed=e['kind'] not in ('construction','dependency'),arrow=True)
    for n in ns:node(c,n,boxes[n['id']])
    for e,box,lines in labels:label(c,e,box,lines)
    height=math.ceil(legend(c,bottom,width)+25);c.check_layout(height)
    return [('compact',c,height,dict(layout_kind='connected',node_boxes={k:list(v) for k,v in boxes.items()},
        edge_routes=[dict(id=e['id'],**{'from':e['from'],'to':e['to']},kind=e['kind'],text=e['text'],points=p) for e,p in routes],
        edge_labels=[dict(id=e['id'],box=list(box)) for e,box,_ in labels]))]

def indexed(model,Canvas,font):
    """Bounded local diagrams retain both endpoints and a real labelled arrow."""
    qs={q['id']:q for q in model['questions']};ns={n['id']:n for n in model['nodes']}
    def endpoint(nid):
        if nid in ns:
            n=dict(ns[nid]);q=qs[n['question_id']]
            n['label']=q['label']+' · '+n['label'];n['detail']=q['title']+'\n'+n['detail'];return n
        q=qs[nid]
        return dict(id=nid,label=q['label'],title=q['title'],detail='科学问题；完整表述与回答见正文',refs=[],kind='construction',question_id=nid)
    panels=[];width=1600;w=540;gap=300;left=110;covered=set()
    for pi,chunk in enumerate([model['relations'][i:i+3] for i in range(0,len(model['relations']),3)],1):
        c=Canvas(font,width=width);c.text(width/2,35,f'关键关系局部图 {pi}',34);y=85;instances=[];routes=[];labels=[]
        for e in chunk:
            a,b=endpoint(e['from']),endpoint(e['to']);h=max(node_height(c,a,w),node_height(c,b,w))
            lines=c.wrap(KINDS[e['kind']]+'：'+e['text'],gap-35,24)
            h=max(h,30*len(lines)+60);ba=(left,y,w,h);bb=(left+w+gap,y,w,h)
            points=[(left+w,y+h/2),(left+w+gap,y+h/2)]
            c.line(points,COLORS[e['kind']],dashed=e['kind'] not in ('construction','dependency'),arrow=True)
            node(c,a,ba);node(c,b,bb)
            lw=max(c.measure(t,24) for t in lines)+16;lh=30*len(lines)+8;lb=(left+w+gap/2-lw/2,y+h/2-lh/2,lw,lh)
            label(c,e,lb,lines);labels.append(dict(id=e['id'],box=list(lb)))
            instances += [dict(id=e['from'],box=list(ba)),dict(id=e['to'],box=list(bb))]
            routes.append(dict(id=e['id'],**{'from':e['from'],'to':e['to']},kind=e['kind'],text=e['text'],points=points))
            covered.update((e['from'],e['to']));y+=h+65
        height=math.ceil(legend(c,y,width)+20);c.check_layout(height)
        panels.append((f'relations-{pi}',c,height,dict(layout_kind='connected-local',node_instances=instances,edge_routes=routes,edge_labels=labels)))
    # Unconnected selected nodes and questions without selected nodes remain visible; no invented edges.
    unlinked=[n for n in model['nodes'] if n['id'] not in covered]
    represented={n['question_id'] for n in model['nodes']}|{nid for nid in covered if nid in qs}
    unlinked += [endpoint(qid) for qid in qs if qid not in represented]
    if not panels and not unlinked:unlinked=[endpoint(qid) for qid in qs]
    for pi,start in enumerate(range(0,len(unlinked),4),1):
        c=Canvas(font,width=1200);c.text(600,35,'未声明连接的选定节点',32);y=85;boxes={}
        for n in unlinked[start:start+4]:
            n=endpoint(n['id']);h=node_height(c,n,1040);box=(80,y,1040,h);node(c,n,box);boxes[n['id']]=list(box);y+=h+30
        c.text(600,y,'无已核依据，不补画箭头；编号对应正文。',24,'#52637a');height=math.ceil(y+45);c.check_layout(height)
        panels.append((f'unlinked-{pi}',c,height,dict(layout_kind='unlinked',node_boxes=boxes,edge_routes=[])))
    return panels

def generate(model,directory,Canvas,font,overwrite=False,protected=()):
    mode=model.get('layout','auto');warnings=[];fallback=None
    if mode not in ('auto','grouped','indexed'):raise ValueError('compact layout: auto/grouped/indexed')
    if mode=='indexed':panels=indexed(model,Canvas,font)
    else:
        try:panels=grouped(model,Canvas,font)
        except ValueError as error:
            fallback=str(error);warnings.append('已拆为保留端点和连接线的局部图，全部已核关系保持可见。');panels=indexed(model,Canvas,font)
    out=Path(directory).resolve();paths=[out/(name+ext) for name,_,_,_ in panels for ext in ('.png','.svg')]
    paths += [out/'layout.json',out/'relations.mmd'];forbidden={Path(p).resolve() for p in protected}
    if any(p in forbidden for p in paths):raise ValueError('diagram must not overwrite a protected file')
    if any(p.exists() for p in paths) and not overwrite:raise ValueError('diagram already exists; choose new output or --overwrite')
    out.mkdir(parents=True,exist_ok=True);blocks=[];layouts=[]
    for warning in warnings:blocks += ['**排版说明**：'+warning,'']
    for name,c,height,meta in panels:
        png,svg=out/(name+'.png'),out/(name+'.svg');record=c.save(png,svg,height)
        record.update(meta);record['panel']=name
        if fallback:record['fallback_reason']=fallback
        layouts.append(record);blocks += [f'![关键回答及关系：{name}](<{png.as_posix()}>)','']
    (out/'layout.json').write_text(json.dumps(layouts,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'relations.mmd').write_text(mermaid(model)+'\n',encoding='utf-8')
    return dict(blocks=blocks,artifacts=[str(p) for p in paths],backend='pillow',warnings=warnings,layout=layouts)
