import paramiko
import re

host = '209.74.67.95'
user = 'zomesnze'
key_path = r'C:\Users\Sajedur Rahman Fiad\.ssh\codex_zomesnze_main'
passphrase = 'abcd1234fiad'

pattern = re.compile(r'Traceback|Exception|ModuleNotFound|ImportError|SyntaxError|ERROR|spawn error|job-runner|Service Unavailable', re.I)

key = paramiko.Ed25519Key.from_private_key_file(key_path, password=passphrase)
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(hostname=host, port=21098, username=user, pkey=key, timeout=20)
sftp = ssh.open_sftp()
path = '/home/zomesnze/ai.sajedurrahmanfiad.me/stderr.log'
with sftp.open(path, 'r') as f:
    size = f.stat().st_size
    start = max(0, size - 1500000)
    f.seek(start)
    data = f.read().decode('utf-8', 'ignore')

lines = [ln for ln in data.splitlines() if pattern.search(ln)]
for ln in lines[-250:]:
    print(ln)

sftp.close()
ssh.close()
