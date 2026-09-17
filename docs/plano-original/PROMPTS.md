# Prompt para Claude Code: GeoSGB MCP Connector

> **Nota (2026-09-17):** este documento faz parte do plano ORIGINAL de janeiro
> de 2026 e descreve o SDK 1.x (`from mcp.server.fastmcp import FastMCP`,
> retorno `-> dict`) e tools que não existem. O código vivo em `src/geosgb_mcp/`
> migrou para o SDK 2.x (`from mcp.server.mcpserver import MCPServer`), anota os
> retornos com modelos Pydantic (`outputSchema`) e recusa argumento
> desconhecido. Em caso de divergência, vale o código e
> `tests/test_output_contract.py`. A porta de entrada do repositório é o
> `README.md` da raiz.

## Prompt Inicial

```
Você vai implementar um MCP connector para acessar dados geológicos do Serviço Geológico do Brasil (SGB), focado em prospecção de Elementos Terras Raras (ETRs).

## Documentação de Referência

Há três documentos que guiam este projeto:

1. **geosgb-mcp-specification.md** - Especificação técnica da API, endpoints, campos e query patterns
2. **geosgb-mcp-code-reference.md** - Código de referência com snippets prontos para uso
3. **geosgb-mcp-implementation-plan.md** - Plano de implementação com etapas, testes e critérios de aceite

Leia estes documentos antes de começar. Eles estão no diretório atual ou em ~/Downloads/.

## Regras de Trabalho

1. **Desenvolvimento incremental**: implemente uma etapa por vez, conforme o plano
2. **Teste antes de avançar**: cada etapa tem um teste de validação - execute-o antes de prosseguir
3. **Não pule etapas**: se um teste falhar, corrija antes de continuar
4. **Use o código de referência**: os snippets estão prontos para uso, adapte conforme necessário
5. **Documente problemas**: se encontrar algo diferente do esperado na API, registre

## Comando Inicial

Comece pela **Fase 1, Etapa 1.1** do plano de implementação: criar a estrutura de diretórios do projeto.

Após cada etapa concluída, me informe o status e aguarde confirmação para prosseguir, OU continue automaticamente se o teste de validação passar.
```

---

## Prompt Alternativo (Modo Autônomo)

Se preferir que o Claude Code trabalhe de forma mais autônoma:

```
Você vai implementar um MCP connector para dados geológicos do SGB (Serviço Geológico do Brasil).

## Documentação

Leia os três documentos de referência no diretório atual:
- geosgb-mcp-specification.md (especificação da API)
- geosgb-mcp-code-reference.md (código de referência)
- geosgb-mcp-implementation-plan.md (plano com etapas e testes)

## Modo de Trabalho

Siga o plano de implementação sequencialmente (Fase 1 → Fase 6). Para cada etapa:

1. Implemente conforme o código de referência
2. Execute o teste de validação especificado
3. Se passar → avance para próxima etapa
4. Se falhar → corrija e reteste

Continue automaticamente até completar a Fase 5 (server MCP funcional). Pare antes da Fase 6 (integração Claude Desktop) e me avise.

## Iniciar

Comece agora. Primeiro, leia os documentos. Depois, execute a Fase 1.
```

---

## Prompt para Continuar Sessão Interrompida

```
Continuando a implementação do GeoSGB MCP Connector.

Verifique o estado atual do projeto:
1. Quais arquivos já existem em geosgb-mcp/?
2. Qual foi a última etapa concluída?
3. Quais testes passam atualmente?

Com base nisso, identifique a próxima etapa do plano de implementação e continue.
```

---

## Prompt para Debugging

```
O teste da etapa [X.X] está falhando com o seguinte erro:

[COLAR ERRO AQUI]

Analise o erro, consulte a especificação da API no documento geosgb-mcp-specification.md, e corrija o problema. Depois reteste.
```

---

## Prompt para Adicionar Nova Tool

```
Adicione uma nova tool ao GeoSGB MCP Connector:

**Nome:** get_occurrence_details
**Função:** Obter detalhes completos de uma ocorrência mineral pelo ID
**Parâmetro:** occurrence_id (int)
**Retorno:** Todos os campos disponíveis da ocorrência

Siga o padrão das tools existentes em src/geosgb_mcp/tools/occurrences.py e registre no server.py.
```

---

## Checklist de Arquivos para Disponibilizar ao Claude Code

Antes de iniciar, certifique-se de que estes arquivos estão acessíveis:

- [ ] `geosgb-mcp-specification.md`
- [ ] `geosgb-mcp-code-reference.md`
- [ ] `geosgb-mcp-implementation-plan.md`

Você pode colocá-los em:
- Diretório atual do projeto
- ~/Downloads/
- Ou colar o conteúdo diretamente na conversa

---

## Fluxo Esperado

```
┌─────────────────────────────────────────────────────────────┐
│  1. Usuário envia prompt inicial + documentos               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Claude Code lê os 3 documentos                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Executa Fase 1: estrutura + dependências                │
│     → Testa: imports funcionam                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Executa Fase 2: validação da API                        │
│     → Testa: python tests/test_api.py                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  5. Executa Fase 3: cliente HTTP                            │
│     → Testa: query básica funciona                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  6. Executa Fase 4: tools (uma por vez)                     │
│     → Testa: cada tool individualmente                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  7. Executa Fase 5: server MCP                              │
│     → Testa: server inicia sem erro                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  8. PARA e avisa usuário                                    │
│     → Usuário configura Claude Desktop manualmente          │
└─────────────────────────────────────────────────────────────┘
```

---

## Notas para o Usuário

### Onde executar o Claude Code

O Claude Code deve ser executado em um ambiente com:
- Python 3.10+
- Acesso à internet (para acessar API do SGB)
- Permissão para instalar pacotes pip

### Tempo estimado

- Fase 1-2: ~5 minutos
- Fase 3-4: ~15 minutos
- Fase 5: ~5 minutos
- **Total: ~25-30 minutos** (se tudo correr bem)

### Se a API do SGB estiver fora do ar

A Fase 2 falhará. Nesse caso:
1. Tente novamente mais tarde
2. Ou peça ao Claude Code para criar mocks temporários
