# Histórico de versões

## 7.0 — PULSE
- Novo nome e identidade visual: **PULSE — System Telemetry** (antes "Painel de Telemetria").
- Logo em SVG e PNG (fundo preto e transparente), ícone próprio do Windows e da bandeja, imagens do instalador (pasta `marca/`).
- Tela de inicialização animada: logo com respiração de 2,5 s (98% a 102%), brilho ciano suave e barra de progresso ligada às etapas reais. A janela de configuração só aparece quando está pronta, e a splash fecha sozinha se algo falhar.
- Botão **Sobre** na configuração: versão instalada, desenvolvedor, repositório, tecnologias e créditos.
- Janela, bandeja, atalhos ("PULSE"), instalador e "Adicionar ou remover programas" com o novo nome. A pasta `C:\PainelTelemetria`, a tarefa de inicialização e os temas continuam os mesmos, então a atualização mantém tudo.
- Instalador renomeado para `PULSE-Setup.exe`.

## 6.1
- Troca de tema quase instantânea, como no TURMO: o programa da tela não fecha mais; só redesenha o fundo e os valores (cerca de 0,1 s no simulador, mais o tempo de envio pela USB).
- Vale para "Aplicar na tela", "Usar agora" dos perfis, perfil e brilho pela bandeja e para a troca automática ao entrar e sair de jogos.
- Girar a tela 180° ou escolher um tema de outro tamanho/orientação ainda reinicia a tela.
- Todos os temas passam a ler os sensores no mesmo ritmo, e só os sensores que o tema mostra.

## 6.0
- Instalador `PainelTelemetria-Setup.exe` com desinstalação pelo Windows (opção de manter os temas).
- Janela de configuração própria (pywebview + WebView2), sem abrir o navegador.
- Ícone na bandeja: abrir configuração, perfil Trabalho/Jogos, troca automática, brilho, reiniciar e sair.
- A tela liga 5 s depois de entrar no Windows.

## 5.0
- Nome e modelo da CPU, GPU e RAM.
- Temperatura com cor dinâmica (verde / amarelo / vermelho, limites ajustáveis).
- Tema "Código", que parece um editor de programação.
- Perfis Trabalho e Jogos, com troca automática quando um jogo fica em tela cheia.
- Consumo de energia em watts (CPU, GPU e total).
- Áudio dividido: alto-falante e microfone.
- Novos temas a partir de modelos e aviso quando uma informação não cabe na tela.

## 4.0
- Vários temas do usuário (criar, duplicar, renomear, excluir).
- VRAM, média de FPS da sessão, fontes, estilos de cartão, medidor ou barra, imagem de fundo.
- Correção da tela branca causada pelo bloqueio de arquivos baixados da internet.

## 3.0
- Interface "Configurar painel" e gerador de temas, com os 38 temas de 3,5" da comunidade.

## 2.0
- Pacote com o programa embutido (sem baixar 1 GB do GitHub).

## 1.0
- Primeira versão: tema próprio, sensores extras (volume, FPS/frametime, SSD) e instalador em PowerShell.
