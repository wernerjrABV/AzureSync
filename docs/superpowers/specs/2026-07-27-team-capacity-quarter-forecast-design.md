# Capacidade do Time e Previsão Trimestral — Design

## Objetivo

Disponibilizar, para cada Area Path (um time), uma visão confiável da sua
capacidade de entrega no quarter selecionado. A previsão será baseada no
throughput histórico de itens concluídos, não em estimativas de pontos. Tempos
de fluxo serão exibidos como diagnóstico dos fatores que explicam a capacidade.

## Escopo

- Uma Area Path corresponde a um time e é a fronteira de todos os cálculos.
- A análise usa uma janela móvel dos últimos 12 meses, com histórico mensal.
- A página apresenta uma faixa de previsão trimestral, capacidade por tipo de
  item e métricas de fluxo.
- A funcionalidade é somente leitura para o usuário.

Ficam fora de escopo a edição de estados, a configuração de times compostos,
a previsão por pontos e ajustes manuais de capacidade.

## Regras de fluxo

Estados finais padronizados: `Closed`, `Done` e `Resolved`. Itens em
`Canceled` são excluídos integralmente da análise.

| Grupo | Tipos de item | Backlog | Upstream | Ciclo / downstream |
|---|---|---|---|---|
| Desenvolvimento | User Story, Technical Story, Bug | `New`, `Waiting Development` | Não aplicável | `Development`, `Waiting Code Review`, `Code Review`, `Waiting Tests`, `Tests`, `Closed` |
| Descoberta e entrega ampliada | Feature, Technical Feature, Incident, Problem | `New` | `Requirements Analysis`, `Waiting Technical Analysis` | `Technical Analysis`, `Waiting Development`, `Development`, `Waiting Quality Analysis`, `Quality Analysis`, `Waiting Review`, `Review`, `Waiting Deployment`, `Deployment`, `Waiting Validation`, `Validation`, `Closed` |

No grupo de desenvolvimento, o ciclo cobre de `Development` até o estado final.
No grupo de descoberta e entrega ampliada, a análise separa upstream de
downstream; `Technical Analysis` e todos os estados seguintes, até o estado
final, pertencem ao downstream.

## Dados e métricas

O sync-service já conserva o histórico de revisões retornado pelo Azure DevOps.
Em cada sincronização e no backfill de histórico, ele reconstruirá intervalos
normalizados de status por item: Area Path, tipo do item, estado, início, fim e
duração. Se um item retornar a um mesmo estado, todos os seus intervalos serão
preservados e somados nas métricas por estado.

Um item entra no throughput somente uma vez: no mês em que alcança seu último
estado final. Caso seja reaberto, uma conclusão anterior deixa de contar e a
conclusão final substitui a anterior. Isso evita contar a mesma entrega duas
vezes em previsões diferentes.

Para cada Area Path e tipo de item elegível, o sistema calcula:

- throughput mensal dos últimos 12 meses;
- percentis 25, 50 (mediana) e 75 desse throughput mensal;
- previsão trimestral conservadora = percentil 25 × 3;
- previsão trimestral esperada = mediana × 3;
- previsão trimestral otimista = percentil 75 × 3;
- tempos medianos em cada status e, quando aplicável, em upstream,
  downstream e ciclo de desenvolvimento.

O total geral é exibido como soma dos tipos, mas a previsão por tipo permanece
visível. Isso impede que ciclos naturalmente diferentes, como Bugs e Features,
sejam interpretados como uma única classe de trabalho.

A previsão só é considerada confiável quando há pelo menos três meses com
entregas no período de 12 meses. Abaixo desse limiar, o produto apresenta o
histórico existente e declara a previsão indisponível.

## Arquitetura

`apps/sync-service` continua sendo o único escritor da base. O processamento
de intervalos normalizados de status pertence ao sync-service e ocorre dentro
do fluxo de sincronização/backfill; nenhuma aplicação de leitura emite SQL de
escrita.

`apps/api-read` expõe uma rota somente leitura:

```
GET /api/capacity?area_path_id=<id>&year=<yyyy>&quarter=<1..4>
```

A resposta contém a faixa trimestral, sinalização de confiabilidade,
throughput mensal, previsões por tipo, métricas de fluxo e avisos de qualidade
dos dados. A API usa apenas consultas `SELECT` sobre os dados já normalizados.

`apps/web-read` ganha a página **Capacity & Flow**, adicionada à navegação
existente. Ela usa exclusivamente componentes Astryx e contém:

1. Seletor de Area Path, quarter e janela histórica de 12 meses.
2. Três cards para previsão conservadora, esperada e otimista.
3. Tabela por tipo de item com as três previsões e ciclo mediano.
4. Histórico visual de throughput mensal.
5. Diagnóstico de gargalos, com tempo por estado e tempos agregados de fluxo.

O quarter atual é o padrão inicial. A página reutiliza os padrões atuais de
seleção de Area Path, carregamento, erro e estado vazio.

## Qualidade de dados e falhas

- Itens cancelados não geram intervalos, throughput ou previsão.
- Um intervalo sem estado ou data de revisão suficiente é excluído, sem
  invalidar os demais dados do item; a resposta informa a quantidade afetada.
- Quando não há itens elegíveis, o frontend apresenta `EmptyState`.
- Quando a API falha, o frontend apresenta `Banner` de erro e permite nova
  tentativa, seguindo o padrão existente.
- Enquanto uma sincronização ocorre, as leituras usam a última análise
  consistente disponível; a API nunca devolve uma agregação parcialmente
  gravada.

## Testes

- Sync-service: reconstrução de transições, reabertura, retorno a um mesmo
  estado, mapeamento dos dois fluxos e exclusão de cancelados.
- Cálculos: throughput por mês/tipo, último estado final, percentis,
  multiplicação trimestral e limiar de confiabilidade.
- API read-only: query por Area Path, validação de parâmetros, resposta de
  qualidade de dados e guarda contra SQL de escrita.
- Frontend: carregamento, erro, vazio, previsão indisponível, dados completos
  e apresentação por tipo.

## Evolução futura

Depois de comparar previsões e resultados reais por alguns quarters, o produto
poderá acrescentar ajustes explícitos por tendência de tempo de ciclo, WIP e
filas. Essa evolução não faz parte da primeira versão, para manter o modelo
inicial transparente e verificável.
