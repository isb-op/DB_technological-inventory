# Inventário Tecnológico

Aplicativo desktop local para acompanhar colaboradores, computadores, celulares, linhas telefônicas e histórico de entregas. Interface em Python/Tkinter e armazenamento em SQLite, com visual escuro e navegação por teclado nas listas.

## Executar

Requer Python 3.11 ou superior, com suporte a Tkinter.

```powershell
python -m pip install -r requirements.txt
python aplicativo/app.py
```

No Windows, também é possível executar `Iniciar.cmd` quando o Python estiver configurado no computador.

## Dados locais

O repositório distribui somente o código. O banco de dados, planilhas de colaboradores e equipamentos, backups, relatórios e documentos ficam fora do controle de versão. Cada instalação deve manter seus próprios arquivos na pasta local do projeto. O banco utilizado pelo aplicativo fica em `dados/gestao.sqlite3`.

Para importar planilhas, a instalação local espera uma planilha `DADOS*.xlsx` para colaboradores, uma planilha `Inventário*.xlsx` para computadores e, opcionalmente, `Telefones.xlsx`. As estruturas de coluna devem corresponder às utilizadas no importador. Sem esses arquivos, a importação informa quais fontes estão faltando.

## Recursos

- Consulta de colaboradores e equipamentos relacionados.
- Cadastro e edição de computadores, celulares e linhas.
- Entrega e substituição de equipamentos existentes em estoque.
- Responsáveis de outras bases e uso de aparelhos por equipes.
- Pesquisa nos campos e nos vínculos atuais.
- Histórico unificado e exportação CSV para acompanhamento do RH.
- Cópias de segurança locais.

A geração de documentos a partir de um modelo específico da empresa não faz parte desta distribuição. O modelo, o gerador correspondente e os documentos gerados permanecem somente na instalação local.
