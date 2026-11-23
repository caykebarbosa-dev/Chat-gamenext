# GameNext

Aplicativo desktop para conversar com modelos de linguagem locais. A interface é feita com Python e PyQt6; a inferência local usa o servidor llama.cpp. O projeto também inclui integrações opcionais para APIs compatíveis e ferramentas configuráveis.

> Este projeto está em desenvolvimento. Recursos, compatibilidade e instruções podem mudar. Não há instalador `.exe` nesta versão.

## Requisitos

- Windows 10 ou 11 (o foco atual de desenvolvimento; outras plataformas não foram verificadas).
- Python 3.11 ou superior instalado e disponível no `PATH` ou pelo Python Launcher (`py`).
- Conexão com a internet e aproximadamente 5 GB livres na primeira inicialização para baixar dependências, runtime e modelos.
- GPU Vulkan compatível é opcional; o llama.cpp também pode executar em CPU, embora mais lentamente.

## Usar no Windows

1. Baixe o ZIP do repositório pelo botão **Code → Download ZIP** e extraia a pasta.
2. Dê dois cliques em `Iniciar GameNext.bat`.
3. Na primeira execução, o BAT cria um ambiente Python isolado, instala as dependências e baixa o runtime llama.cpp, o modelo GGUF inicial e o Whisper Tiny. O GGUF tem cerca de 2,1 GB. Aguarde os downloads terminarem.
4. O aplicativo abre. Vá a **Configurações → Modelos** e clique em **Carregar modelo**.

Nas próximas execuções, abra o mesmo BAT. O runtime e os modelos já baixados são mantidos localmente. É necessária conexão com a internet para instalar dependências e baixar os arquivos na primeira execução. Se um download for interrompido, execute o BAT novamente; o arquivo incompleto será baixado de novo.

## Instalação para desenvolvimento

No PowerShell, a partir da pasta do projeto:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python run.py
```

Na tela **Configurações → Modelos**, o instalador já deixa selecionáveis o runtime e o modelo padrão. Também é possível selecionar outro executável `llama-server` e qualquer pasta com modelos `.gguf`.

## Recursos

- Interface desktop de chat com streaming e cancelamento.
- Histórico local de conversas.
- Descoberta e configuração de modelos GGUF.
- Configuração de provedores de API, com credenciais guardadas no cofre do sistema quando disponível.
- Ferramentas e conexões MCP configuráveis.
- Ditado local e opções de transcrição por provedor externo.

Alguns recursos dependem de configuração externa e podem não funcionar sem credenciais ou serviços correspondentes. Consulte a interface e o código para o estado atual de cada integração.

## Dados e privacidade

O aplicativo pode ler arquivos ou acessar serviços externos quando o usuário habilita e utiliza as ferramentas correspondentes. Chamadas a provedores de API enviam dados ao provedor configurado. Revise as configurações antes de usar. Segredos, bancos de conversa, modelos baixados, logs e resultados locais não devem ser adicionados ao controle de versão. A primeira execução baixa runtime e modelos de llama.cpp e Hugging Face; eles ficam na pasta local do projeto.

## Desenvolvimento

Dependências: `pyproject.toml`; arquivo de lock: `uv.lock`.

```powershell
python -m unittest discover -s tests -v
python -m compileall -q src tests scripts run.py
```

## Licença

Este repositório ainda não declara uma licença. Até que uma licença seja adicionada, todos os direitos permanecem reservados; não presuma permissão para redistribuir ou reutilizar o código.
