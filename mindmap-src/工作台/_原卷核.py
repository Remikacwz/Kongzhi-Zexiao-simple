"""回原卷核分值/题号（§113 A 方案：只读文字信息，不读题图内容）。"""
import pymupdf,re,sys,glob,io,os
ROOT=r'E:/真题思维导图'
def find_pdf(school):
    for pat in [f'{ROOT}/_to_cloud_P2/*{school}*.pdf', f'{ROOT}/【万人教育】*/**/*{school}*.pdf', f'{ROOT}/【万人教育】*/**/**/*{school}*.pdf']:
        for f in glob.glob(pat,recursive=True):
            if '品牌版' not in f: return f
    return None
def paper_pages(school, year):
    f=find_pdf(school)
    if not f: return None,[]
    d=pymupdf.open(f); res=[]
    for i in range(d.page_count):
        t=d[i].get_text()
        if re.search(rf'{year}\s*年', t) and '考生注意' in t and re.search(r'考试科目代码', t):
            res.append((i,t))
    return f,res
def scores(school, year, npages=3):
    f,pp=paper_pages(school,year)
    if not pp: return f,None
    i,t=pp[0]
    d=pymupdf.open(f); buf=t
    for j in range(i+1, min(i+npages, d.page_count)): buf+='\n'+d[j].get_text()
    got=re.findall(r'(?m)^\s*(\d{1,2})\s*[、.]\s*[（(]\s*(\d{1,3})\s*分', buf)
    # 也认「第N题（M分）」
    got+=re.findall(r'第\s*(\d{1,2})\s*题\s*[（(]\s*(\d{1,3})\s*分', buf)
    return f,got
if __name__=='__main__':
    for school,year in [('河海大学',2024),('浙江工业大学',2024),('大连理工大学',2024)]:
        f,g=scores(school,year)
        print(f'{school}_{year}: pdf={f}')
        print('   原卷逐题分值:', g)
