"""Local SQT diagrams. No model, network, PDF access, or scientific inference."""
import html
import json
import math
from pathlib import Path


class DrawingUnavailable(RuntimeError):
    pass


def _font(path=None):
    candidates = [Path(path)] if path else [
        Path('C:/Windows/Fonts/msyh.ttc'), Path('C:/Windows/Fonts/simhei.ttf'),
        Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),
        Path('/System/Library/Fonts/PingFang.ttc')]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise DrawingUnavailable('没有可用的中文字体；可通过 --font 指定字体文件')


def mermaid(model):
    """Escape labels and use generated identifiers, never raw input as syntax."""
    if model.get('format')=='compact':
        return _compact_module().mermaid(model)
    def label(value):
        return html.escape(str(value), quote=True).replace('\n', '<br/>')
    lines = ['flowchart TB']
    ids = {}
    for i, question in enumerate(model['questions']):
        qnode = f'q{i}'
        ids[question['id']] = qnode
        lines.append(f'    {qnode}["{label(question["label"] + " " + question["title"])}"]')
        for j, facet in enumerate(question['facets']):
            fnode = f'f{i}_{j}'
            text = facet['label'] + ' ' + facet['title'] + '\n' + '、'.join(facet['refs'])
            lines.append(f'    {fnode}["{label(text)}"]')
            lines.append(f'    {qnode} --- {fnode}')
    for relation in model['relations']:
        lines.append(f'    {ids[relation["from"]]} -.->|"{label(relation["text"])}"| {ids[relation["to"]]}')
    return '\n'.join(lines)


class Canvas:
    """Measure before drawing; preserve font size when labels grow."""
    def __init__(self, font_path, width=1600):
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError as error:
            raise DrawingUnavailable('缺少Pillow，不能生成PNG') from error
        self.Image, self.ImageDraw, self.ImageFont = Image, ImageDraw, ImageFont
        self.font_path, self.width = str(font_path), width
        self.scale, self.commands, self.bounds = 2, [], []
        self.fonts = {}

    def font(self, size):
        if size not in self.fonts:
            try:
                self.fonts[size] = self.ImageFont.truetype(self.font_path, size * self.scale)
            except OSError as error:
                raise DrawingUnavailable('字体无法由Pillow加载') from error
        return self.fonts[size]

    def measure(self, text, size):
        return self.font(size).getlength(text) / self.scale

    def wrap(self, text, width, size):
        # A character-level fallback covers long English tokens as well as CJK.
        result = []
        for para in str(text).split('\n'):
            para_start=len(result)
            line = ''
            for char in para:
                if line and self.measure(line + char, size) > width:
                    result.append(line.strip()); line = char
                else:
                    line += char
            result.append(line.strip())
            # Avoid a final one-character row while preserving line count.
            if len(result)-para_start>1:
                while (self.measure(result[-1],size)<width*.30 and len(result[-2])>2):
                    candidate=result[-2][-1]+result[-1]
                    if self.measure(candidate,size)>width:break
                    result[-1]=candidate;result[-2]=result[-2][:-1].rstrip()
        return result

    def text(self, x, y, text, size=30, color='#24344a', align='middle'):
        box = self.font(size).getbbox(text, anchor='mm' if align == 'middle' else 'lm')
        actual = [x + box[0]/2, y + box[1]/2, x + box[2]/2, y + box[3]/2]
        if actual[0] < 0 or actual[2] > self.width or actual[1] < 0:
            raise ValueError('diagram text leaves canvas; split or wrap labels')
        self.bounds.append(dict(text=text, box=actual))
        self.commands.append(('text', x, y, text, size, color, align))

    def rect(self, x, y, w, h, fill='#f5f7fa', stroke='#d7dee7'):
        self.commands.append(('rect', x, y, w, h, fill, stroke))

    def line(self, points, color='#b2becd', dashed=False, arrow=False):
        self.commands.append(('line', points, color, dashed, arrow))

    def node_height(self, title, width, refs=None):
        return 32 + 46*len(self.wrap(title, width-40, 34)) + (
            38*len(self.wrap('、'.join(refs), width-40, 27))+8 if refs else 0)

    def node(self, x, y, width, title, refs=None, question=False, min_height=0):
        height = max(min_height,self.node_height(title, width, refs))
        self.rect(x, y, width, height, '#eaf2fd' if question else '#f5f7fa', '#9bb6d9' if question else '#d7dee7')
        at = y+24
        for line in self.wrap(title, width-40, 34):
            self.text(x+width/2, at+18, line, 34); at += 46
        if refs:
            at += 4
            for line in self.wrap('、'.join(refs), width-40, 27):
                self.text(x+width/2, at+15, line, 27, '#56667d'); at += 38
        return height

    def check_layout(self, height):
        for bound in self.bounds:
            if bound['box'][3] > height:
                raise ValueError('diagram text leaves bottom of canvas')
        # Measured text boxes must not intersect other measured text boxes.
        for i, a in enumerate(self.bounds):
            for b in self.bounds[i+1:]:
                x1,y1,x2,y2=a['box']; u1,v1,u2,v2=b['box']
                if min(x2,u2)>max(x1,u1)+1 and min(y2,v2)>max(y1,v1)+1:
                    raise ValueError('diagram text overlaps; split or wrap labels')

    def save(self, png_path, svg_path, height):
        self.check_layout(height)
        s=self.scale
        image=self.Image.new('RGB',(self.width*s,height*s),'white')
        draw=self.ImageDraw.Draw(image)
        xml=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{height}" viewBox="0 0 {self.width} {height}">',
             '<title>科学问题与回答侧面关系图</title>', '<rect width="100%" height="100%" fill="white"/>']
        for command in self.commands:
            if command[0]=='rect':
                _,x,y,w,h,fill,stroke=command
                draw.rounded_rectangle((x*s,y*s,(x+w)*s,(y+h)*s),radius=14*s,fill=fill,outline=stroke,width=2*s)
                xml.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
            elif command[0]=='text':
                _,x,y,text,size,color,align=command
                draw.text((x*s,y*s),text,font=self.font(size),fill=color,anchor='mm' if align=='middle' else 'lm')
                # SVG uses the same actual installed font family as PNG.
                family=html.escape(self.font(size).getname()[0],quote=True)
                xml.append(f'<text x="{x}" y="{y}" text-anchor="{align}" dominant-baseline="central" font-family="{family}, sans-serif" font-size="{size}" fill="{color}">{html.escape(text)}</text>')
            else:
                _,points,color,dashed,arrow=command
                for (x1,y1),(x2,y2) in zip(points,points[1:]):
                    length=math.hypot(x2-x1,y2-y1)
                    if dashed and length:
                        for k in range(0,math.ceil(length),15):
                            a=k/length;b=min(k+8,length)/length
                            draw.line(((x1+(x2-x1)*a)*s,(y1+(y2-y1)*a)*s,(x1+(x2-x1)*b)*s,(y1+(y2-y1)*b)*s),fill=color,width=3*s)
                    else:
                        draw.line((x1*s,y1*s,x2*s,y2*s),fill=color,width=2*s)
                xml.append('<polyline points="'+' '.join(f'{x},{y}' for x,y in points)+f'" fill="none" stroke="{color}" stroke-width="2"'+(' stroke-dasharray="8 7"' if dashed else '')+'/>')
                if arrow and len(points)>1:
                    (a,b),(x,y)=points[-2:]; angle=math.atan2(y-b,x-a)
                    head=[(x,y),(x-13*math.cos(angle)-7*math.sin(angle),y-13*math.sin(angle)+7*math.cos(angle)),
                          (x-13*math.cos(angle)+7*math.sin(angle),y-13*math.sin(angle)-7*math.cos(angle))]
                    draw.polygon([(u*s,v*s) for u,v in head],fill=color)
                    xml.append('<polygon points="'+' '.join(f'{u},{v}' for u,v in head)+f'" fill="{color}"/>')
        xml.append('</svg>')
        image.resize((self.width,height),self.Image.Resampling.LANCZOS).save(png_path)
        Path(svg_path).write_text('\n'.join(xml),encoding='utf-8')
        return dict(width=self.width,height=height,text_boxes=self.bounds,overlap_count=0,overflow_count=0)


def _combined(model, font_path):
    questions=model['questions']; canvas=Canvas(font_path)
    canvas.text(800,42,'科学问题与回答侧面',36)
    count=len(questions); starts=[190,870] if count==2 else [530]
    width=540
    qheight=max(canvas.node_height(q['label']+' '+q['title'],width) for q in questions)
    centers={q['id']:x+width/2 for q,x in zip(questions,starts)}
    for q,x in zip(questions,starts):
        canvas.node(x,95,width,q['label']+' '+q['title'],question=True,min_height=qheight)
    y=95+qheight+34
    for relation in model['relations']:
        lines=canvas.wrap(relation['text'],900,30)
        for text in lines:
            canvas.text(800,y+16,text,30,'#536982'); y+=42
        left=centers[relation['from']]; right=centers[relation['to']]
        canvas.line([(left,y),(right,y)],'#536982',True,True)
        # Endpoints connect to their actual Q, without implying a causal chain.
        canvas.line([(left,95+qheight),(left,y)],'#536982')
        canvas.line([(right,y),(right,95+qheight)],'#536982')
        y+=42
    start=y+48
    ends=[]
    for qi,(q,x) in enumerate(zip(questions,starts)):
        canvas.text(x+width/2,start-18,q['label']+'的回答侧面',29,'#56667d')
        cursor=start+22; midpoints=[]
        for f in q['facets']:
            h=canvas.node(x,cursor,width,f['label']+' '+f['title'],f['refs'])
            midpoints.append(cursor+h/2);cursor+=h+30
        if midpoints:
            edge=x+width if count==2 and qi==1 else x
            branch=edge+42 if count==2 and qi==1 else edge-42
            canvas.line([(edge,95+qheight/2),(branch,95+qheight/2),(branch,midpoints[-1])])
            for middle in midpoints:canvas.line([(branch,middle),(edge,middle)])
        ends.append(cursor)
    bottom=max(ends)+24
    canvas.text(800,bottom,'虚线：问题间关系；A/B等编号：回答侧面',27,'#66768b')
    return canvas,math.ceil(bottom+42)


def _overview(model,font_path):
    canvas=Canvas(font_path);canvas.text(800,42,'科学问题关系总图',36)
    y=100; positions={}
    for q in model['questions']:
        h=canvas.node(65,y,570,q['label']+' '+q['title'],question=True)
        positions[q['id']]=(635,y+h/2);y+=h+65
    legend_y=95
    for i,r in enumerate(model['relations']):
        x1,y1=positions[r['from']];x2,y2=positions[r['to']]
        lane=690+70*i
        canvas.line([(x1,y1),(lane,y1),(lane,y2),(x2,y2)],'#738399',True,True)
        # Lane identifiers correspond to the explicit relation legend.
        canvas.text(lane+3,(y1+y2)/2,f'R{i+1}',24,'#536982',align='start')
        title=f'R{i+1}  {next(q["label"] for q in model["questions"] if q["id"]==r["from"])} → {next(q["label"] for q in model["questions"] if q["id"]==r["to"])}：{r["text"]}'
        for text in canvas.wrap(title,560,30):
            canvas.text(1010,legend_y+18,text,30,align='start');legend_y+=43
        legend_y+=26
    if not model['relations']:
        canvas.text(1010,130,'未声明问题间依赖',30,align='start')
    bottom=max(y,legend_y)+20
    canvas.text(800,bottom,'虚线标明已复核的关系；各问题的回答侧面见后续局部图',27,'#66768b')
    return canvas,math.ceil(bottom+45)


def generate(model, directory, overwrite=False, font=None, protected=()):
    """Return report blocks + measured layout. Missing dependency -> Mermaid."""
    try:
        font_path=_font(font)
        # Validate the font and Pillow before creating any artifacts.
        Canvas(font_path).font(30)
    except DrawingUnavailable as error:
        return dict(blocks=['**配图降级**：'+str(error)+'。以下保留关系图源码。','',
                            '```mermaid',mermaid(model),'```',''],
                    artifacts=[],backend='mermaid',warnings=[str(error)],layout=[])
    if model.get('format')=='compact':
        return _compact_module().generate(model,directory,Canvas,font_path,overwrite,protected)
    compact=(len(model['questions'])<=2 and sum(len(q['facets']) for q in model['questions'])<=8
             and len(model['relations'])<=4)
    panels=[]
    if compact:
        panels.append(('relations',_combined(model,font_path)))
    else:
        if len(model['questions'])>1:
            chunks=[model['relations'][i:i+4] for i in range(0,len(model['relations']),4)] or [[]]
            for i,relations in enumerate(chunks,1):
                name='overview' if len(chunks)==1 else f'overview-{i}'
                panels.append((name,_overview(dict(questions=model['questions'],relations=relations),font_path)))
        for i,q in enumerate(model['questions'],1):
            panels.append((f'question-{i}',_combined(dict(questions=[q],relations=[]),font_path)))
    directory=Path(directory)
    paths=[directory/(name+ext) for name,_ in panels for ext in ['.png','.svg']]
    paths += [directory/'layout.json',directory/'relations.mmd']
    forbidden={Path(p).resolve() for p in protected}
    if any(p.resolve() in forbidden for p in paths):
        raise ValueError('diagram output must not replace a protected source or script')
    if any(p.exists() for p in paths) and not overwrite:
        raise ValueError('diagram output already exists; choose a new report path or --overwrite')
    # All panels are checked before writing, including a later dense panel.
    for _,(canvas,height) in panels:canvas.check_layout(height)
    directory.mkdir(parents=True,exist_ok=True)
    blocks=[]; layouts=[]
    for name,(canvas,height) in panels:
        png=directory/(name+'.png');svg=directory/(name+'.svg')
        layout=canvas.save(png,svg,height)
        layout['panel']=name; layouts.append(layout)
        blocks += [f'![科学问题与回答侧面：{name}](<{png.resolve().as_posix()}>)','']
    (directory/'layout.json').write_text(json.dumps(layouts,ensure_ascii=False,indent=2),encoding='utf-8')
    (directory/'relations.mmd').write_text(mermaid(model)+'\n',encoding='utf-8')
    return dict(blocks=blocks,artifacts=[str(p.resolve()) for p in paths],
                backend='pillow',warnings=[],layout=layouts)


def _compact_module():
    import importlib.util
    spec=importlib.util.spec_from_file_location('sqt_compact',Path(__file__).with_name('compact.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
