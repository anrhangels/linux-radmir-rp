#!/usr/bin/env python3
"""Original vector artwork for the Linux RP series. Standard pycairo only."""
from pathlib import Path
import cairo,math,random
P=Path(__file__).parent
BG='#11101B';INK='#F5EFEB';MUTED='#AEA5B9';ORANGE='#B7A5F5';LILAC='#FFB076';TEAL='#8FD0C4'
def col(c,h):c.set_source_rgb(*(int(h[i:i+2],16)/255 for i in (1,3,5)))
def rect(c,x,y,w,h,co):col(c,co);c.rectangle(x,y,w,h);c.fill()
def circle(c,x,y,r,co):col(c,co);c.arc(x,y,r,0,math.tau);c.fill()
def line(c,pts,co,w=1):
 col(c,co);c.set_line_width(w);c.move_to(*pts[0]);[c.line_to(*p) for p in pts[1:]];c.stroke()
def poly(c,pts,co):
 col(c,co);c.move_to(*pts[0]);[c.line_to(*p) for p in pts[1:]];c.close_path();c.fill()
def text(c,s,x,y,size,co=INK,font='Nimbus Sans',bold=False):
 c.select_font_face(font,0,cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL);c.set_font_size(size);col(c,co);c.move_to(x,y);c.show_text(s)
def pixelpalm(c,x,y,size=1):
 c.save();c.translate(x,y);c.scale(size,size)
 for i in range(14):rect(c,i//3*3,-i*8,8,10,'#141421')
 for side in [-1,1]:
  for k in range(6):rect(c,12+side*k*11,-116+(k*k)//2,15,6,'#141421')
  for k in range(5):rect(c,12+side*k*8,-112+k*8,12,6,'#141421')
 c.restore()
def scene(c):
 rect(c,700,75,660,506,'#24263F');circle(c,1160,167,54,'#B7A5F5')
 random.seed(14)
 for _ in range(65):rect(c,random.randrange(710,1355),random.randrange(90,265),2,2,'#6F6C93')
 # Fictional city, built as vector pixel art for the series.
 for x,y,w,h,co in [(713,284,108,152,'#34334E'),(831,236,116,205,'#41415C'),(957,304,97,140,'#36354C'),(1062,259,116,192,'#46445D'),(1190,227,157,227,'#36374F')]:
  rect(c,x,y,w,h,co);rect(c,x+w-12,y,12,h,'#282A42')
  for yy in range(y+13,y+h-12,20):
   for xx in range(x+12,x+w-15,19):rect(c,xx,yy,7,10,'#B99787' if random.random()>.54 else '#676580')
  rect(c,x-3,y-4,w+6,5,'#666078')
 rect(c,700,443,660,138,'#181B2A')
 poly(c,[(1022,435),(1048,435),(1286,581),(784,581)],'#39394C')
 line(c,[(1022,438),(780,581)],'#67607D',2);line(c,[(1048,438),(1288,581)],'#67607D',2)
 for j in range(7):
  y=447+j*j*3;rect(c,1035-j*.5,y,2+j,2+j,ORANGE)
 # Street lights and low-poly car.
 for x,y in [(780,430),(1285,432),(893,439),(1183,439)]:
  rect(c,x,y-96,4,96,'#131725');rect(c,x-23,y-98,30,4,'#131725');rect(c,x-24,y-95,16,4,'#D9C6A5')
 poly(c,[(1002,498),(1015,478),(1062,478),(1081,498),(1087,523),(994,523)],'#111521')
 rect(c,1017,484,40,12,'#6E7188');rect(c,999,506,16,5,'#FFB076');rect(c,1067,506,16,5,'#FFB076')
 rect(c,1026,515,29,3,'#A9A1A5')
 rect(c,700,564,660,17,BG)
 for x in range(710,1360,12):rect(c,x,564,4,17,'#282335')
def hero(c):
 rect(c,0,0,1400,660,BG);text(c,'ANRHANGELS  /  LINUX RP SERIES',42,37,13,MUTED,'Nimbus Mono PS');text(c,'INSTALL RECORD  02',1145,37,13,ORANGE,'Nimbus Mono PS');line(c,[(42,57),(1358,57)],'#40344A')
 scene(c)
 text(c,'RADMIR',42,178,102,INK,'Nimbus Sans Narrow',True);text(c,'НА LINUX.',42,279,102,ORANGE,'Nimbus Sans Narrow',True)
 rect(c,44,315,35,3,ORANGE);text(c,'Новая графика. Музыка. Свой город.',42,362,27,INK)
 text(c,'Официальный клиент. Понятная установка.',42,408,20,MUTED);text(c,'Готовые исправления. Твой следующий запуск.',42,438,20,MUTED)
 for x,title,desc in [(43,'01 / ПОДГОТОВИТЬ','Flatpak + Faugus'),(270,'02 / НАСТРОИТЬ','Библиотеки + шрифты'),(490,'03 / ИГРАТЬ','Лаунчер + игра')]:
  text(c,title,x,519,12,ORANGE,'Nimbus Mono PS');text(c,desc,x,547,18,INK)
 line(c,[(42,595),(1358,595)],'#40344A');text(c,'RADMIR CRMP  ×  GE-PROTON  ×  FAUGUS',42,632,14,MUTED,'Nimbus Mono PS');text(c,'РУССКИЕ ИНСТРУКЦИИ / ОТКРЫТЫЙ КОД',943,632,13,MUTED,'Nimbus Mono PS')
def route(c):
 rect(c,0,0,1400,290,BG);text(c,'КАРТА МАРШРУТА',35,42,17,ORANGE,'Nimbus Mono PS');text(c,'От чистого окружения до первого входа.',35,77,24)
 for i,(name,desc) in enumerate([('СИСТЕМА','Flatpak · шрифты'),('НАСТРОЙКА','Proton · библиотеки'),('ЛАУНЧЕР','Официальный EXE'),('ТВОЙ СЕРВЕР','Загрузка клиента · вход')]):
  x=48+i*344;line(c,[(x+16,134),(min(1362,x+344),134)],'#4A3A56',2);circle(c,x+12,134,12,ORANGE if i<3 else TEAL);text(c,str(i+1),x+7,139,14,BG,'Nimbus Mono PS',True)
  text(c,name,x,186,22,INK,'Nimbus Sans Narrow',True);text(c,desc,x,221,16,MUTED)
 text(c,'Скрипт готовит окружение. Официальный лаунчер загружает игру. В аккаунт входишь ты.',35,267,15,MUTED)
def fixes(c):
 rect(c,0,0,1400,315,BG);text(c,'ГРАФИКА. МУЗЫКА. УДОБНЫЙ ЗАПУСК.',36,52,33,INK,'Nimbus Sans Narrow',True)
 text(c,'НАСТРОЙКИ ДЛЯ RADMIR CRMP',36,85,14,ORANGE,'Nimbus Mono PS')
 for x,label,sample,co in [(36,'БИБЛИОТЕКИ','Новая графика',ORANGE),(497,'АДРЕСА МУЗЫКИ','Кириллица в URL',TEAL),(958,'ОДНА КОМАНДА','radmir',LILAC)]:
  rect(c,x,115,407,148,'#201C2C');text(c,label,x+19,145,12,co,'Nimbus Mono PS');text(c,sample,x+19,208,32,INK,'Nimbus Sans',True)
 text(c,'UCRT / D3DX9 / D3DCompiler',55,240,13,MUTED)
 text(c,'Локальный помощник на время игры',516,240,13,MUTED)
 text(c,'Лаунчер, журнал и возврат настроек',977,240,13,MUTED)
 text(c,'Авторская схема компонентов; не скриншот игрового интерфейса.',36,298,13,MUTED)
for name,width,height,fn in [('hero',1400,660,hero),('route',1400,290,route),('fixes',1400,315,fixes)]:
 for fmt in ['svg','png']:
  surface=cairo.SVGSurface(str(P/f'{name}.svg'),width,height) if fmt=='svg' else cairo.ImageSurface(cairo.FORMAT_RGB24,width,height)
  fn(cairo.Context(surface))
  if fmt=='png':surface.write_to_png(str(P/f'{name}.png'))
  surface.finish()
print('Original illustrations rendered: hero, route, fixes')
