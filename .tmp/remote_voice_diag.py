import paramiko

host = '209.74.67.95'
user = 'zomesnze'
key_path = r'C:\Users\Sajedur Rahman Fiad\.ssh\codex_zomesnze_main'
passphrase = 'abcd1234fiad'

key = paramiko.Ed25519Key.from_private_key_file(key_path, password=passphrase)
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(hostname=host, port=21098, username=user, pkey=key, timeout=20)

queries = [
    "select id, kind, status, attempts, ifnull(left(last_error,220), '') as last_error, created_at, updated_at from jobs order by id desc limit 20;",
    "select id, attachment_type, mime_type, storage_path, left(ifnull(transcript,''),140), detected_language, analysis_confidence, left(ifnull(json_unquote(json_extract(metadata_json,'$.clarification_reason')),''),220) as reason, created_at from attachments order by id desc limit 20;",
    "select id, role, source, status, left(text,180), left(ifnull(handoff_reason,''),180), created_at from messages order by id desc limit 30;"
]

for q in queries:
    cmd = "export MYSQL_PWD='admin@crossintbd'; mysql -N -u zomesnze_admin zomesnze_ai_support_system -e " + repr(q)
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8', 'ignore')
    err = stderr.read().decode('utf-8', 'ignore')
    print(f'---QUERY:{q}---')
    print(out.strip() or '<no rows>')
    if err.strip():
        print('ERR:' + err.strip())

ssh.close()
