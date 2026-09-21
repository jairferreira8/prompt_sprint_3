# Versão manual da Sprint 2 (histórico montado na mão), usada como "antes" na comparação
# Se o prompt original do grupo era diferente, colar em PROMPT_SPRINT2 (chargegrid_agente.py)

import time

import ollama

from chargegrid_agente import PROMPT_SPRINT2


class ChatbotManual:
    def __init__(self, modelo, temperatura, top_p, max_tokens):
        self.modelo = modelo
        self.opcoes = {"temperature": temperatura, "top_p": top_p, "num_predict": max_tokens}
        self.historicos = {}  # sessao_id -> lista de mensagens

    def iniciar_historico(self):
        return [{"role": "system", "content": PROMPT_SPRINT2}]

    def limpar_sessao(self, sessao_id):
        self.historicos.pop(sessao_id, None)

    def responder(self, sessao_id, pergunta):
        if sessao_id not in self.historicos:
            self.historicos[sessao_id] = self.iniciar_historico()
        historico = self.historicos[sessao_id]

        historico.append({"role": "user", "content": pergunta})

        inicio = time.perf_counter()
        resposta = ollama.chat(model=self.modelo, messages=historico, options=self.opcoes)
        latencia = time.perf_counter() - inicio

        conteudo = resposta["message"]["content"]
        historico.append({"role": "assistant", "content": conteudo})

        return {
            "resposta": conteudo,
            "latencia": latencia,
            "tokens_entrada": resposta.get("prompt_eval_count", 0) or 0,
            "tokens_saida": resposta.get("eval_count", 0) or 0,
            "bloqueado_pelo_filtro": False,
        }
