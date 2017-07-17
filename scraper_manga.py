#!/usr/bin/env python
# -*- coding: utf-8 -*-

import requests,re,os,time,datetime,threading,copy,pickle,sys,paramiko,random,traceback
from lxml import html

def login():
	if os.path.exists("./cookies") :
		with open("./cookies","rb") as f:
			session_requests.cookies=pickle.load(f)
	r=session_requests.get(pixiv_root)
	if r.status_code==200 and re.search('not-logged-in',r.text)==None:
		print("loaded cookies")
		return
	
	login_url='https://accounts.pixiv.net/login'
	r=session_requests.get(login_url)

	tree=html.fromstring(r.text)
	authenticity_token=list(set(tree.xpath("//input[@name='post_key']/@value")))[0]
	with open("account","r") as f:	#account文件放在同目录下，包含一行:用户名(空格)密码
		account=f.read().split()
	payload={
		'pixiv_id':account[0],
		'password':account[1],
		'post_key':authenticity_token
	}
	r=session_requests.post(
		login_url,
		data=payload,
		headers=dict(referer=login_url)
	)
	r=session_requests.get(pixiv_root)
	if re.search('not-logged-in',r.text)!=None:raise IOError('login failed')
	else:
		print("log in")
		with open("./cookies","wb") as f:	#第一次登录后将存档cookies用来登录
			pickle.dump(session_requests.cookies,f)

def downloadImage(imgurl,filename,*,header=None,imgid=None,imgidext=None):
	print("%s is downloading %s"%(threading.current_thread().name,filename))
	try:
		if header : r=session_requests.get(imgurl,headers=header,timeout=30)
		else : r=session_requests.get(imgurl,timeout=30)
		if r.status_code==200:
			try:
				write_rlock.acquire()
				with open(filename,'wb') as f:
					f.write(r.content)
			finally:write_rlock.release()
		else:raise IOError('requestFailed')
	except Exception as e:
		print('FAIL %s failed to download %s'%(threading.current_thread().name,filename))
		if os.path.exists(filename) : os.remove(filename)
		faillog.append(filename)
		traceback.print_exc()
		return False
	else:
		print('SUCCESS %s has sucessfully downloaded %s'%(threading.current_thread().name,filename))
		try:
			garage_rlock.acquire()
			if imgidext:garage.add(imgidext)
			elif imgid:garage.add(imgid)
		finally:garage_rlock.release()
		return True

def listener():
	while(listen_active):
		x=input()
		if x=="q":
			try:
				garage_rlock.acquire()
				if os.path.exists("./garage") :
					with open("./garage","r") as f:
						garage.update(f.read().split())
				with open("./garage","w") as f:
					f.write(" ".join(garage))
				print("local garage update complete")
				synchronize_garage()
				break
			finally:garage_rlock.release()
		elif x=="e":
			break

def synchronize_garage():	#当你使用多台计算机下载图片时，你可能需要将你的garage文件同步到你的服务器上以免重复
	try:
		private_key = paramiko.RSAKey.from_private_key_file("C:/Users/HanYue/.ssh/id_rsa")
		transport = paramiko.Transport(("akaisora.tech",22))
		transport.connect(username="root",pkey=private_key)
		sftp = paramiko.SFTPClient.from_transport(transport)
		
		remotedir="/home/upload/pixiv_scrapy/"
		if "garage" not in sftp.listdir(remotedir):
			sftp.put("garage",remotedir+"garage")

		sftp.get(remotedir+"garage","tmp_garage")
		
		with open("tmp_garage","r") as f:
			garage.update(f.read().split())
		os.remove("tmp_garage")
		
		with open("garage","w") as f:
			f.write(" ".join(garage))
		
		sftp.put("garage",remotedir+"garage")
		
		print("synchronize garage successed")
	except Exception as e:
		print("synchronize garage failed")
		print(e)
	finally:
		try:
			transport.close()
		except Exception as e:
			pass

def testrecommen():	#未完成功能
	r=session_requests.get(pixiv_root+"recommended.php")
	tree=html.fromstring(r.text)
	token=tree.xpath("/pixiv.context.token")
	print(token)
	# "//input[@name='post_key']/@value"

def complete_urllist(clsf):
	newclsf=[]
	for i in range(len(clsf)):
		if clsf[i][0]=="tag": 
			for tag,pagenum in clsf[i][1]:newclsf.append(("tag-"+tag,[url_tag_template%(tag,p) for p in range(1,pagenum+1)]))
		elif clsf[i][0]=="画师":
			for artistname,artistid,pagenum in clsf[i][1]:newclsf.append(("画师-"+artistname,[url_artist_template%(artistid,p) for p in range(1,pagenum+1)]))
		else: newclsf.append(clsf[i])
	return newclsf

def random_one_by_classfi(classi,label="fate"):
	try:
		if classi=="tag" and "r-18" not in label.lower():label+=" -r-18"
		
		if not os.path.exists(temp_save_root) : os.makedirs(temp_save_root)
		if classi.lower()=="normalrank":classification=[("normalRank",[pixiv_root+"ranking.php?mode=daily&p=1",pixiv_root+"ranking.php?mode=daily&p=2",pixiv_root+"ranking.php?mode=original"])]
		elif classi.lower()=="tag":classification=complete_urllist([("tag",[(label,5)])])
		elif classi.lower()=="r18rank":classification=complete_urllist([("r18Rank",[pixiv_root+"ranking.php?mode=daily_r18&p=1",pixiv_root+"ranking.php?mode=male_r18&p=1",pixiv_root+"ranking.php?mode=weekly_r18&p=1",pixiv_root+"ranking.php?mode=weekly_r18&p=2"])])
		else: return None
		
		try: login()
		except Exception as e:print(e);print('Connect failed');return None
		
		url=random.choice(classification[0][1])
		r=session_requests.get(url)
		if r.status_code!=200 and classi.lower()=='tag':
			url=random.choice(complete_urllist([("tag",[(label,1)])])[0][1])
			r=session_requests(url)
			if r.status_code!=200:return False
		imagelist=re.findall(r'(?<=img-master/img)(.*?)(?=_master)',r.text)
		img=random.choice(imagelist)
		imgid=re.search('\d+(?=\_)',img).group(0)
		toDownlist=imgid2source_url(imgid,"single",temp_save_root)
		if len(toDownlist)>0: orgurl,filename=toDownlist[0]
		else :return None
		if os.path.exists(filename): return filename
		refer=referpfx+imgid
		imgidext=os.path.splitext(os.path.basename(filename))[0]
		# print(orgurl,filename,refer,imgid,imgidext)
		# exit(0)
		if downloadImage(orgurl,filename,header={"referer":refer},imgid=imgid,imgidext=imgidext):
			return filename
		else:
			return None
	except Exception as e:
		traceback.print_exc()

def imgid2source_url(imgid,mode="single",local_save=None):
	if not local_save:local_save=local_save_root
	refer=referpfx+imgid
	try:
		toDownlist=[]
		r=session_requests.get(refer,timeout=25)
		match=re.search('(?<=data-src=").*?img-original.*?\.(jpg|png)',r.text)
		if match : toDownlist.append((match.group(0),local_save+os.path.split(match.group(0))[1]))
		else:
			for i in range(0,100 if mode=="manga" else 1):
				r=session_requests.get("https://www.pixiv.net/member_illust.php?mode=manga_big&illust_id="+imgid+"&page=%d"%i)
				if r.status_code!=200:break
				match=re.search('(?<=src=").*?img-original.*?\.(jpg|png)',r.text)
				if match : toDownlist.append((match.group(0),local_save+os.path.split(match.group(0))[1]))
		return toDownlist
	except Exception as e:
		faillog.append(imgid)
		print(e)
		return []

		
#----------ARGS
pixiv_root="https://www.pixiv.net/"
referpfx=r'https://www.pixiv.net/member_illust.php?mode=medium&illust_id='
local_save_root="D:\Image\图站\pixiv\\"+datetime.datetime.now().strftime("%y.%m.%d")+"\\"
temp_save_root="./pixiv_temp/"
url_tag_template=pixiv_root+"search.php?word=%s&order=date_d&p=%d"
url_artist_template=pixiv_root+"member_illust.php?id=%s&type=all&p=%d"

#global vars
session_requests=requests.session()
write_rlock=threading.RLock()
garage_rlock=threading.RLock()
garage=set()
faillog=[]

def batch_download():
	global listen_active
	classification=[
		("normalRank",[
			pixiv_root+"ranking_area.php?type=detail&no=6",
			pixiv_root+"ranking.php?mode=daily&p=1",
			pixiv_root+"ranking.php?mode=daily&p=2",
			pixiv_root+"ranking.php?mode=original"]),
		("r18Rank",[
			pixiv_root+"ranking.php?mode=daily_r18&p=1",
			pixiv_root+"ranking.php?mode=male_r18&p=1",
			pixiv_root+"ranking.php?mode=weekly_r18&p=1",
			pixiv_root+"ranking.php?mode=weekly_r18&p=2"]),
		("bookmark",[
			pixiv_root+"bookmark_new_illust.php?p=%d"%i for i in range(1,10)]),
		("tag",[("栗山未来",3),("メガネ",2)]),
		("画师",[("小林ちさと","3016",5)]),
	]

	#----------PREDO
	# session_requests=requests.session()
	try: login()
	except Exception as e:print(e);print('Connect failed');exit(0)

	#testrecommen()

	if not os.path.exists(local_save_root) : os.makedirs(local_save_root)

	# garage=set()
	if os.path.exists("./garage") : #garage文档存放车库清单，避免文件重复
		with open("./garage","r") as f:
			garage.update(f.read().split())
	classification=complete_urllist(classification)
	# exit(0)
	synchronize_garage()


	# faillog=[]
	threads=[]
	# write_rlock=threading.RLock()
	# garage_rlock=threading.RLock()
	#----------MAINPROC
	listen_active=True
	t=threading.Thread(target=listener)
	t.start()
	for classi,urlList in classification:
		local_save=local_save_root+classi+"\\"
		if not os.path.exists(local_save) : os.makedirs(local_save)
		for pageUrl in urlList:	
			try:
				rankPage=session_requests.get(pageUrl)
				regex=r'(?<=img-master/img)(.*?)(?=_master)'
				imagelist=re.findall(regex,rankPage.text)
			except Exception as e:
				faillog.append(pageUrl+"Pagefail")
				continue
			for img in imagelist:
				try:
					imgid=re.search('\d+(?=\_)',img).group(0)
				except Exception as e:
					print('fail : '+img)
					faillog.append(img)
					continue
				refer=referpfx+imgid
				toDownlist=imgid2source_url(imgid,"manga" if "画师" in classi else "single",local_save)
				for orgurl,filename in toDownlist:
					imgidext=os.path.splitext(os.path.basename(filename))[0]
					if (imgidext in garage) and not ("画师" in classi):continue
					if os.path.exists(filename): 
						garage.add(imgidext)
						continue
					print("<"+orgurl+">")			
					t=threading.Thread(target=downloadImage,args=(orgurl,filename),kwargs={"header":{"referer":refer},"imgid":imgid,"imgidext":imgidext})
					threads.append(t)
					while sum(map(lambda x:1 if x.is_alive() else 0,threads))>=8 : time.sleep(1)
					t.start()

		for t in threads :
			if t.is_alive():t.join()

	#_______________AFTER
	print('-------------------------faillog-------------------------')
	for log in faillog:print(log)

	with open("./garage","w") as f:
		f.write(" ".join(garage))
		
	synchronize_garage()


	listen_active=False
	
	
if __name__=="__main__":
	batch_download()
	# print(random_one_by_classfi("normalRank"))

