# Histórico de versões

## 7.1
- **FPS sem números cortados e sem travar**:
  - os desenhos de cada sensor não se misturam mais na fila da tela (antes o comando de um podia receber os dados de outro e aparecer pedaço de número ou lixo);
  - ao trocar um valor por outro mais baixo (ex.: FPS de "144" para "--"), a parte que sobrava do valor anterior é apagada;
  - quando o driver deixa de mandar o FPS por um instante, o último valor fica até 3 s na tela em vez de piscar "--";
  - as leituras do LibreHardwareMonitor são feitas uma por vez e reaproveitadas no mesmo meio segundo: num jogo a placa de vídeo era lida 3 vezes por segundo, de threads diferentes, o que atrasava a tela e às vezes derrubava o programa (NullReferenceException).
- **Só o que mudou vai para a tela**: o PULSE guarda uma cópia da imagem da tela e manda só os pedaços que mudaram. Com valores parados nada é reenviado (antes: uns 55 KB/s o tempo todo, numa tela que recebe uns 250 KB/s).
- **Troca de tema mais rápida**: 1,3 s em vez de 1,8 s no simulador com a mesma velocidade da tela; a volta do modo gamer passou de 20 s para 5 s depois de sair do jogo, e a entrada de 5 s para 3 s (ajustáveis).
- **Temperatura da CPU**: o LibreHardwareMonitor 0.9.5 lê a CPU pelo driver **PawnIO**, que não vinha com o PULSE, e por isso a temperatura ficava vazia. O instalador agora instala o PawnIO 2.2.0 em silêncio, e a janela de configuração avisa e oferece instalar se ele faltar.
- **Modo gamer editável** (seção "Modo gamer" da configuração): tema, brilho próprio, tempo para ligar e desligar, botão **Editar este tema** e botão para ligar/desligar à mão. Na bandeja, "Perfil Jogos" virou **Modo gamer** (liga/desliga).
- **Ao sair do modo gamer, volta ao tema (e ao brilho) que estava antes**, em vez de ir sempre para o tema de Trabalho (dá para desligar essa opção).
- **TURMO fechado sozinho**: se o TURMO abrir (ele inicia com o Windows pela tarefa agendada dele e pega a porta da tela), o PULSE o fecha em até 2 s. Opção "Fechar o TURMO quando ele abrir" na seção Tela.
- Um valor estranho de um sensor (ex.: NaN no uso da CPU) não para mais de atualizar aquele item até reiniciar: o erro é registrado uma vez e a leitura segue.

## 7.0 — PULSE
- Novo nome e identidade visual: **PULSE — System Telemetry** (antes "Painel de Telemetria").
- Logo em SVG e PNG (fundo preto e transparente), ícone próprio do Windows e da bandeja, imagens do instalador (pasta `marca/`).
- Tela de inicialização animada: logo com respiração de 2,5 s (98% a 102%), brilho ciano suave e barra de progresso ligada às etapas reais. A janela de configuração só aparece quando está pronta, e a splash fecha sozinha se algo falhar.
- Botão **Sobre** na configuração: versão instalada, desenvolvedor, repositório, tecnologias e créditos.
- Janela, bandeja, atalhos ("PULSE"), instalador e "Adicionar ou remover programas" com o novo nome. A pasta `C:\PainelTelemetria`, a tarefa de inicialização e os temas continuam os mesmos, então a atualização mantém tudo.
- Instalador renomeado para `PULSE-Setup.exe`.
- Conexão com a tela USB mais confiável, em qualquer número de porta COM:
  - a tela é procurada pela VID 1A86 / PID 5722 (ou série USB35INCHIPSV2); um `COM_PORT` fixo continua valendo;
  - tela ausente ou porta ocupada (TURMO aberto, por exemplo) não fecham mais o programa: ele espera, tenta de novo e diz quem pode estar com a porta;
  - depois do reset da tela a porta é procurada de novo, mesmo que volte com outro número;
  - com várias telas compatíveis, prefere a que funcionou da última vez e registra a escolha;
  - cabo desconectado, erro de escrita ou envio travado: o programa da tela reabre na hora, reconecta e redesenha;
  - sem administrador a tela continua funcionando (só as leituras que exigem administrador ficam vazias).
- Placa de vídeo: com duas GPUs (ex.: Radeon integrada do Ryzen + RX dedicada) o PULSE usa a dedicada, e a janela de configuração ganhou a opção **Placa de vídeo** (Tela) para escolher outra. A escolha fica em `C:\PainelTelemetria\gpus.json` e vale depois de reinstalar.
- Corrigido o programa da tela que fechava sozinho a cada 1 ou 2 minutos (código 0xC0000005 em `_ctypes.pyd`, "COM method call without VTable") nos temas com volume do microfone: a leitura do áudio liberava o mesmo objeto do Windows duas vezes. Agora uma thread só cuida do áudio, cria os objetos uma vez e reaproveita.
- Quando o programa da tela fecha, a janela mostra o código de saída (ex.: travamento em código nativo) em vez de um aviso qualquer do log.
- Diagnóstico: log em português com cada etapa (procura, porta, conexão, envio da imagem) e o motivo técnico de cada falha; o `iniciar.log` diz por que o programa da tela fechou; estado da tela na janela de configuração e no ícone da bandeja (`tela.json`).

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
