from winpty import PtyProcess

command = (
    r'C:\Windows\System32\cmd.exe '
    r'/d /c '
    r'C:\Projetos\Backup_Auto\tests\test_list_job.bat'
)

process = PtyProcess.spawn(command)

output = []

while process.isalive():
    try:
        data = process.read(4096)
        if data:
            output.append(data)
    except EOFError:
        break

try:
    while True:
        data = process.read(4096)
        if not data:
            break
        output.append(data)
except EOFError:
    pass

print("".join(output))
