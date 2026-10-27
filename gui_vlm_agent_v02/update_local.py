"""Apply this release to an existing folder, with backup; never copy secrets."""
from pathlib import Path
import shutil
import zipfile
from datetime import datetime
import tkinter as tk
from tkinter import filedialog,messagebox
SOURCE=Path(__file__).resolve().parent
SKIP={'.venv','__pycache__','.git','.pytest_cache','logs','backups'}
def eligible(p):return not any(x in SKIP for x in p.parts) and p.name not in {'llm_secrets.env'} and p.suffix!='.pyc'
def main():
    root=tk.Tk();root.withdraw()
    selected=filedialog.askdirectory(title='选择原来的 gui_vlm_agent 文件夹（先关闭运行中的程序）')
    if not selected:return
    target=Path(selected).resolve()
    if target==SOURCE:
        messagebox.showerror('无法更新','请选择旧项目文件夹，不是本更新包所在文件夹。');return
    if not (target/'agent.py').exists():
        messagebox.showerror('无法更新','该文件夹没有 agent.py，请选择原项目根目录。');return
    if not messagebox.askyesno('更新项目',f'请先关闭旧程序。将备份代码并更新到：\n{target}\n密钥、环境和日志会保留。是否继续？'):return
    backup=target/'backups'/('code_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.zip');backup.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(backup,'w',zipfile.ZIP_DEFLATED) as z:
        for p in target.rglob('*'):
            rel=p.relative_to(target)
            if p.is_file() and eligible(rel):z.write(p,str(rel))
    for p in SOURCE.rglob('*'):
        rel=p.relative_to(SOURCE)
        if p.is_file() and eligible(rel):
            dest=target/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    messagebox.showinfo('更新完成',f'代码已更新。备份：{backup}\n双击 start_windows.bat 启动。')
if __name__=='__main__':main()
