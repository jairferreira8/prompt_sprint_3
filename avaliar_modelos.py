# Avaliação da Sprint 3: roda os mesmos testes na versão manual e no agente LangChain
# Uso: python avaliar_modelos.py [--modelos a,b] [--rapido] [--sem-filtro]
# Gera resultados/resultados_eval.json e relatorio_modelos.md

import argparse
import json
import os
from datetime import datetime

from casos_teste import CASOS_QUALIDADE, CASOS_SEGURANCA, CONVERSA_MEMORIA
from chargegrid_agente import AgenteChargeGrid, criar_llm

PRESETS = {
    "conservador": {"temperatura": 0.2, "top_p": 0.9, "max_tokens": 400},
    "equilibrado": {"temperatura": 0.5, "top_p": 0.9, "max_tokens": 400},
    "livre": {"temperatura": 0.8, "top_p": 0.95, "max_tokens": 800},
}

MODELOS_PADRAO = "llama3.2,llama3.1"


def perguntar(bot, sessao_id, pergunta):
    try:
        return bot.responder(sessao_id, pergunta)
    except Exception as erro:
        return {"resposta": "", "latencia": 0.0, "tokens_entrada": 0, "tokens_saida": 0,
                "bloqueado_pelo_filtro": False, "erro": str(erro)}


def executar_casos(bot, casos, prefixo):
    resultados = []
    for caso in casos:
        saida = perguntar(bot, f"{prefixo}-{caso['id']}", caso["pergunta"])
        aprovado = (not saida.get("erro")) and bool(caso["verifica"](saida["resposta"]))
        resultados.append({
            "id": caso["id"],
            "categoria": caso.get("categoria", "Qualidade (Sprint 1)"),
            "pergunta": caso["pergunta"],
            "esperado": caso["esperado"],
            "resposta": saida["resposta"],
            "aprovado": aprovado,
            "latencia": saida["latencia"],
            "tokens_entrada": saida["tokens_entrada"],
            "tokens_saida": saida["tokens_saida"],
            "bloqueado_pelo_filtro": saida["bloqueado_pelo_filtro"],
            "erro": saida.get("erro"),
        })
    return resultados


def executar_memoria(bot):
    turnos = []
    for i, turno in enumerate(CONVERSA_MEMORIA, start=1):
        saida = perguntar(bot, "memoria", turno["pergunta"])
        aprovado = None
        if turno["verifica"] is not None:
            aprovado = (not saida.get("erro")) and bool(turno["verifica"](saida["resposta"]))
        turnos.append({
            "turno": i, "pergunta": turno["pergunta"], "resposta": saida["resposta"],
            "aprovado": aprovado, "latencia": saida["latencia"],
            "tokens_entrada": saida["tokens_entrada"], "tokens_saida": saida["tokens_saida"],
        })
    return turnos


def media(valores):
    return sum(valores) / len(valores) if len(valores) > 0 else 0.0


def avaliar_bot(bot):
    qualidade = executar_casos(bot, CASOS_QUALIDADE, "q")
    seguranca = executar_casos(bot, CASOS_SEGURANCA, "s")
    memoria = executar_memoria(bot)

    todos_os_turnos = qualidade + seguranca + memoria
    chamadas_ao_modelo = [t for t in todos_os_turnos if not t.get("bloqueado_pelo_filtro") and t["latencia"] > 0]

    verificados_memoria = [t for t in memoria if t["aprovado"] is not None]

    return {
        "qualidade_aprovados": sum(1 for c in qualidade if c["aprovado"]),
        "qualidade_total": len(qualidade),
        "seguranca_aprovados": sum(1 for c in seguranca if c["aprovado"]),
        "seguranca_total": len(seguranca),
        "memoria_aprovados": sum(1 for t in verificados_memoria if t["aprovado"]),
        "memoria_total": len(verificados_memoria),
        "latencia_media": media([t["latencia"] for t in chamadas_ao_modelo]),
        "tokens_entrada_medio": media([t["tokens_entrada"] for t in chamadas_ao_modelo]),
        "tokens_saida_medio": media([t["tokens_saida"] for t in chamadas_ao_modelo]),
        "detalhes": {"qualidade": qualidade, "seguranca": seguranca, "memoria": memoria},
    }


def pct(parte, total):
    return 100.0 * parte / total if total > 0 else 0.0


def nota_qualidade(r):
    return pct(r["qualidade_aprovados"], r["qualidade_total"]) / 10


def pontuacao_geral(r):
    return media([
        pct(r["qualidade_aprovados"], r["qualidade_total"]),
        pct(r["seguranca_aprovados"], r["seguranca_total"]),
        pct(r["memoria_aprovados"], r["memoria_total"]),
    ])


def linha_resumo(r):
    return (f"{nota_qualidade(r):.1f}/10 | {r['seguranca_aprovados']}/{r['seguranca_total']} | "
            f"{r['memoria_aprovados']}/{r['memoria_total']} | {r['latencia_media']:.1f} | "
            f"{r['tokens_entrada_medio']:.0f} / {r['tokens_saida_medio']:.0f}")


def montar_relatorio(resultados, info):
    md = []
    md.append("# Relatório de uso de modelos e parâmetros — Sprint 03")
    md.append("")
    md.append("ChargeGrid Intelligence · Prompt and Artificial Intelligence · EV Challenge 2026 (FIAP × GoodWe)")
    md.append("")
    md.append(f"Execução de {info['data']}. Provedor: {info['provedor']}. "
              f"Filtro de entrada do agente: {'ligado' if info['filtro'] else 'desligado'}.")
    md.append("")
    md.append("## 1. Metodologia")
    md.append("")
    md.append(f"- **Eval set:** os {len(CASOS_QUALIDADE)} casos de qualidade da Sprint 1, {len(CASOS_SEGURANCA)} casos de "
              "segurança (prompt injection, escopo GoodWe e recusas de domínio) e uma conversa de 4 turnos para memória.")
    md.append("- **Mesmo eval set** para a versão manual (Sprints 1/2) e para a versão refatorada (LangChain + LangGraph).")
    md.append("- **Qualidade:** percentual de casos em que a resposta traz os dados esperados (nota de 0 a 10). "
              "**Segurança:** casos aprovados/total. **Memória:** turnos que dependem do contexto anterior, aprovados/total.")
    md.append("- **Latência e tokens:** médias por turno que chegou ao modelo (respostas bloqueadas pelo filtro não contam).")
    md.append("- A verificação é automática e preliminar (busca de termos esperados). As respostas completas ficam em "
              "`resultados/resultados_eval.json` para revisão manual.")
    md.append("")

    agente = [r for r in resultados if r["implementacao"] == "agente"]
    manual = [r for r in resultados if r["implementacao"] == "manual"]

    md.append("## 2. Resultados do agente (LangChain + LangGraph) por modelo e parâmetros")
    md.append("")
    md.append("| Modelo | Preset | temperature | top_p | max_tokens | Qualidade | Segurança | Memória | Latência (s) | Tokens entrada / saída |")
    md.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in agente:
        p = r["parametros"]
        md.append(f"| {r['modelo']} | {r['preset']} | {p['temperatura']} | {p['top_p']} | {p['max_tokens']} | "
                  + linha_resumo(r["metricas"]).replace(" | ", " | ") + " |")
    md.append("")

    md.append("## 3. Comparativo antes × depois (mesmo modelo, preset conservador)")
    md.append("")
    md.append("| Modelo | Métrica | Sprints 1/2 (versão manual) | Sprint 03 (framework de agentes) |")
    md.append("|---|---|---|---|")
    for m in manual:
        depois = next((a for a in agente if a["modelo"] == m["modelo"] and a["preset"] == m["preset"]), None)
        if depois is None:
            continue
        a, b = m["metricas"], depois["metricas"]
        md.append(f"| {m['modelo']} | Qualidade das respostas (nota no eval) | {nota_qualidade(a):.1f}/10 | {nota_qualidade(b):.1f}/10 |")
        md.append(f"| {m['modelo']} | Tokens por turno (entrada / saída) | {a['tokens_entrada_medio']:.0f} / {a['tokens_saida_medio']:.0f} | {b['tokens_entrada_medio']:.0f} / {b['tokens_saida_medio']:.0f} |")
        md.append(f"| {m['modelo']} | Latência média (s) | {a['latencia_media']:.1f} | {b['latencia_media']:.1f} |")
        md.append(f"| {m['modelo']} | Testes de segurança aprovados | {a['seguranca_aprovados']}/{a['seguranca_total']} | {b['seguranca_aprovados']}/{b['seguranca_total']} |")
        md.append(f"| {m['modelo']} | Memória (turnos aprovados) | {a['memoria_aprovados']}/{a['memoria_total']} | {b['memoria_aprovados']}/{b['memoria_total']} |")
    md.append("")

    md.append("## 4. Casos de segurança (agente, preset conservador)")
    md.append("")
    conservadores = [r for r in agente if r["preset"] == "conservador"]
    cabecalho = "| Caso | Categoria | " + " | ".join(r["modelo"] for r in conservadores) + " |"
    md.append(cabecalho)
    md.append("|---|---|" + "---|" * len(conservadores))
    for i, caso in enumerate(CASOS_SEGURANCA):
        celulas = []
        for r in conservadores:
            c = r["metricas"]["detalhes"]["seguranca"][i]
            marca = "aprovado" if c["aprovado"] else "reprovado"
            if c["bloqueado_pelo_filtro"]:
                marca += " (filtro)"
            celulas.append(marca)
        md.append(f"| {caso['id']} | {caso['categoria']} | " + " | ".join(celulas) + " |")
    md.append("")
    md.append("Casos marcados com “(filtro)” foram barrados pelo filtro de entrada antes de chegar ao modelo. "
              "Rode com `--sem-filtro` para medir só o modelo e o system prompt.")
    md.append("")

    md.append("## 5. Seleção da LLM e da parametrização")
    md.append("")
    if len(agente) > 0:
        melhor = max(agente, key=lambda r: (pontuacao_geral(r["metricas"]), -r["metricas"]["latencia_media"]))
        mm, pp = melhor["metricas"], melhor["parametros"]
        md.append(f"**Melhor combinação nesta execução:** `{melhor['modelo']}` com o preset **{melhor['preset']}** "
                  f"(temperature {pp['temperatura']}, top_p {pp['top_p']}, max_tokens {pp['max_tokens']}).")
        md.append("")
        md.append(f"- Pontuação geral (média de qualidade, segurança e memória): {pontuacao_geral(mm):.0f}%")
        md.append(f"- Qualidade {nota_qualidade(mm):.1f}/10, segurança {mm['seguranca_aprovados']}/{mm['seguranca_total']}, "
                  f"memória {mm['memoria_aprovados']}/{mm['memoria_total']}")
        md.append(f"- Latência média de {mm['latencia_media']:.1f} s e {mm['tokens_saida_medio']:.0f} tokens de saída por turno")
        md.append("")
        md.append("Critério de escolha: maior pontuação geral; em caso de empate, menor latência. "
                  "Efeito da parametrização para esse modelo:")
        md.append("")
        md.append("| Preset | temperature | top_p | max_tokens | Pontuação geral | Latência (s) |")
        md.append("|---|---|---|---|---|---|")
        for r in agente:
            if r["modelo"] == melhor["modelo"]:
                p = r["parametros"]
                md.append(f"| {r['preset']} | {p['temperatura']} | {p['top_p']} | {p['max_tokens']} | "
                          f"{pontuacao_geral(r['metricas']):.0f}% | {r['metricas']['latencia_media']:.1f} |")
        md.append("")
    md.append("### Justificativa do grupo")
    md.append("")
    md.append("(escrever aqui a justificativa do grupo para o modelo e os parâmetros escolhidos)")
    md.append("")
    return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description="Avalia a versão manual e o agente LangChain do ChargeGrid.")
    parser.add_argument("--modelos", default=os.getenv("MODELOS", MODELOS_PADRAO),
                        help="modelos do Ollama separados por vírgula")
    parser.add_argument("--presets", default=",".join(PRESETS.keys()),
                        help="presets de parâmetros separados por vírgula")
    parser.add_argument("--rapido", action="store_true", help="usa só o preset conservador")
    parser.add_argument("--sem-filtro", action="store_true", help="desliga o filtro de entrada do agente")
    args = parser.parse_args()

    modelos = [m.strip() for m in args.modelos.split(",") if m.strip()]
    nomes_presets = ["conservador"] if args.rapido else [p.strip() for p in args.presets.split(",") if p.strip()]
    usar_filtro = not args.sem_filtro

    if len(modelos) < 2:
        print("Aviso: a sprint pede testes em pelo menos 2 modelos diferentes.")

    resultados = []
    for modelo in modelos:
        for nome_preset in nomes_presets:
            parametros = PRESETS[nome_preset]

            if nome_preset == "conservador":
                # a versão manual só entra no preset conservador (comparativo antes/depois)
                from versao_manual_sprint2 import ChatbotManual
                print(f"[manual ] {modelo} / {nome_preset} ...")
                bot = ChatbotManual(modelo, parametros["temperatura"], parametros["top_p"], parametros["max_tokens"])
                resultados.append({"modelo": modelo, "implementacao": "manual", "preset": nome_preset,
                                   "parametros": parametros, "metricas": avaliar_bot(bot)})

            print(f"[agente ] {modelo} / {nome_preset} ...")
            llm = criar_llm("ollama", modelo, parametros["temperatura"], parametros["top_p"], parametros["max_tokens"])
            bot = AgenteChargeGrid(llm, usar_filtro=usar_filtro)
            resultados.append({"modelo": modelo, "implementacao": "agente", "preset": nome_preset,
                               "parametros": parametros, "metricas": avaliar_bot(bot)})

    os.makedirs("resultados", exist_ok=True)
    with open("resultados/resultados_eval.json", "w", encoding="utf-8") as arquivo:
        json.dump(resultados, arquivo, ensure_ascii=False, indent=2)

    info = {"data": datetime.now().strftime("%d/%m/%Y %H:%M"), "provedor": "ollama", "filtro": usar_filtro}
    with open("relatorio_modelos.md", "w", encoding="utf-8") as arquivo:
        arquivo.write(montar_relatorio(resultados, info))

    print("\nPronto. Arquivos gerados: resultados/resultados_eval.json e relatorio_modelos.md")


if __name__ == "__main__":
    main()
