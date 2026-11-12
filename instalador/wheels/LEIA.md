# Pacotes Python prontos

Estes quatro pacotes só existem no PyPI como código-fonte e não compilam bem nas versões
novas do Python. Eles foram convertidos em wheels puras (`py3-none-any`) para o instalador
usar com `pip install --find-links wheels`:

| Pacote | Origem | Ajuste |
|---|---|---|
| `uptime 3.0.1` | PyPI | sem a extensão em C opcional (no Windows ela não é usada) |
| `GPUtil 1.4.0` | PyPI | `distutils.spawn.find_executable` trocado por `shutil.which` (o `distutils` saiu do Python 3.12) |
| `pyadl 0.1` | PyPI | nenhum |
| `proxy_tools 0.1.0` | PyPI | nenhum (dependência do pywebview) |
